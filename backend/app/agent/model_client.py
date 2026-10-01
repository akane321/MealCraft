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


_turn: ContextVar[Tally | None] = ContextVar("model_requests", default=None)
# Since the process started: requests sent outside a counted turn, or in one whose run never recorded them.
_unrecorded = Tally()
_lock = threading.Lock()  # LangGraph's workers and concurrent requests share the tallies


def _count(request) -> None:
    tally = _turn.get()
    with _lock:
        (tally if tally is not None else _unrecorded).requests += 1


def note_fallback() -> None:
    """A model request failed and the turn went on without it: rules read the message, or words stood in for
    embeddings."""
    tally = _turn.get()
    if tally is not None:
        tally.fell_back = True


@lru_cache(maxsize=1)
def http_client():
    import openai

    return openai.DefaultHttpxClient(event_hooks={"request": [_count]})


@contextmanager
def counting() -> Iterator[None]:
    """Counts the model requests made inside the block, by this thread and the work it hands to others
    (LangGraph copies the context into its workers). Also a decorator. What the block does not take is
    counted as unrecorded."""
    token = _turn.set(Tally())
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
        taken = Tally(tally.requests, tally.fell_back)
        tally.requests, tally.fell_back = 0, False
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
