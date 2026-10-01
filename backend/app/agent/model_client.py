"""The one HTTP client every request to the OpenAI API goes through: the parser's chat model and both embedders.

It counts each request it sends (retries included) for the Agent run being served, which records them as
`agent_runs.used_llm_calls`, and it keeps its connections open between requests. `warm` loads at start-up
what the first request would otherwise load, so the first message or swap after a start is not the slow one.
"""

from collections.abc import Iterator
from contextlib import contextmanager
from contextvars import ContextVar
from functools import lru_cache

_counted: ContextVar[list[int] | None] = ContextVar("model_requests", default=None)


def _count(request) -> None:
    counter = _counted.get()
    if counter is not None:
        counter[0] += 1


@lru_cache(maxsize=1)
def http_client():
    import openai

    return openai.DefaultHttpxClient(event_hooks={"request": [_count]})


@contextmanager
def counting() -> Iterator[None]:
    """Counts the model requests made inside the block, by this thread and the work it hands to others
    (LangGraph copies the context into its workers). Also a decorator."""
    token = _counted.set([0])
    try:
        yield
    finally:
        _counted.reset(token)


def take_count() -> int:
    """The requests counted since the last take in the current block; 0 outside one."""
    counter = _counted.get()
    if counter is None:
        return 0
    count, counter[0] = counter[0], 0
    return count


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
