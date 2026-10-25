"""The one HTTP client every request to the OpenAI API goes through: the parser's chat model and both embedders.

It counts each request it sends (retries included) for the Agent run being served, which records them as
`agent_runs.used_llm_calls`, and notes when a request failed and the turn went on without the model. A request
no run records (a console replay, a swap preview asked of the plan API directly) is counted for the process
instead, which the console shows beside the runs. It keeps its connections open between requests. `warm` loads
at start-up what the first request would otherwise load, so the first message or swap after a start is not the
slow one.
"""

import threading
from collections.abc import Iterator
from contextlib import contextmanager
from contextvars import ContextVar
from dataclasses import dataclass
from functools import lru_cache


@dataclass
class Tally:
    requests: int = 0
    fell_back: bool = False
    input_tokens: int = 0
    output_tokens: int = 0
    cached_input_tokens: int = 0
    embedding_tokens: int = 0
    max_requests: int | None = None
    sent: int = 0


class ModelCallLimitReached(RuntimeError):
    pass


_turn: ContextVar[Tally | None] = ContextVar("model_requests", default=None)
# Since the process started: requests sent outside a counted turn, or in one whose run never recorded them.
_unrecorded = Tally()
_lock = threading.Lock()  # LangGraph's workers and concurrent requests share the tallies


def _count(request) -> None:
    tally = _turn.get()
    with _lock:
        if tally is not None and tally.max_requests is not None and tally.sent >= tally.max_requests:
            tally.fell_back = True
            raise ModelCallLimitReached("This turn's model request budget is exhausted.")
        if tally is not None:
            tally.sent += 1
        (tally if tally is not None else _unrecorded).requests += 1


def note_fallback() -> None:
    """A model request failed and the turn went on without it: rules read the message, or words stood in for
    embeddings."""
    tally = _turn.get()
    if tally is not None:
        tally.fell_back = True


def note_usage(response) -> None:
    """Accumulate provider-reported chat token usage for the current run, when exposed by LangChain."""
    tally = _turn.get()
    if tally is None:
        return
    usage = response if isinstance(response, dict) else getattr(response, "usage_metadata", None)
    if not usage:
        usage = getattr(response, "response_metadata", {}).get("token_usage", {})
    if not usage:
        return
    details = (
        usage.get("input_token_details", usage.get("prompt_tokens_details", {})) if isinstance(usage, dict) else {}
    )
    tally.input_tokens += int(usage.get("input_tokens", usage.get("prompt_tokens", 0)) or 0)
    tally.output_tokens += int(usage.get("output_tokens", usage.get("completion_tokens", 0)) or 0)
    tally.cached_input_tokens += int(details.get("cache_read", details.get("cached_tokens", 0)) or 0)


def _count_response_usage(response) -> None:
    """Read usage from non-streaming OpenAI responses, including embedding requests."""
    tally = _turn.get()
    if tally is None:
        return
    try:
        if "text/event-stream" in response.headers.get("content-type", ""):
            return  # This hook accounts for non-streaming JSON responses only.
        response.read()  # HTTPX response hooks run before the response body is read.
        payload = response.json()
        usage = payload.get("usage") or {}
        if response.request.url.path.rstrip("/").endswith("/embeddings"):
            tally.embedding_tokens += int(usage.get("prompt_tokens", usage.get("total_tokens", 0)) or 0)
        else:
            note_usage(usage)
    except Exception:  # noqa: BLE001 - usage accounting must never fail an otherwise valid model call
        return


@lru_cache(maxsize=1)
def http_client():
    import openai

    return openai.DefaultHttpxClient(event_hooks={"request": [_count], "response": [_count_response_usage]})


@contextmanager
def counting(*, max_requests: int | None = None) -> Iterator[None]:
    """Counts the model requests made inside the block, by this thread and the work it hands to others
    (LangGraph copies the context into its workers). Also a decorator. What the block does not take is
    counted as unrecorded."""
    token = _turn.set(Tally(max_requests=max_requests))
    try:
        yield
    finally:
        left = take()
        with _lock:
            _unrecorded.requests += left.requests
        _turn.reset(token)


def take() -> Tally:
    """What the current block counted since the last take, which starts again from nothing; empty outside one."""
    tally = _turn.get()
    if tally is None:
        return Tally()
    with _lock:
        taken = Tally(
            requests=tally.requests,
            fell_back=tally.fell_back,
            input_tokens=tally.input_tokens,
            output_tokens=tally.output_tokens,
            cached_input_tokens=tally.cached_input_tokens,
            embedding_tokens=tally.embedding_tokens,
        )
        tally.requests = 0
        tally.input_tokens = 0
        tally.output_tokens = 0
        tally.cached_input_tokens = 0
        tally.embedding_tokens = 0
        tally.fell_back = False
    return taken


def unrecorded_requests() -> int:
    """Requests this process sent that no run records, since it started."""
    return _unrecorded.requests


def warm(api_key: str, model: str) -> None:
    """Builds the chat model and both embedders as a request would, and drops them: the OpenAI library loads
    its API modules on first use (seconds in the container), and the catalog vectors load once. No request
    is sent."""
    from app.agent.ingredient_matcher import catalog_embedder as ingredient_embedder
    from app.agent.parser import OpenAIConstraintParser
    from app.planning.recipe_similarity import catalog_embedder as recipe_embedder

    OpenAIConstraintParser(api_key=api_key, model=model)
    ingredient_embedder(api_key)
    recipe_embedder(api_key)
