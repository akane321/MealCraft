import json
import re
from datetime import UTC, datetime
from pathlib import Path
from typing import Protocol

from pydantic import BaseModel, Field

TOKEN_PATTERN = re.compile(r"[a-z0-9]+")
GENERIC_QUERY_TOKENS = {"cooking", "food", "how", "recipe", "the", "to", "tutorial"}


class TutorialProviderError(RuntimeError):
    """Raised when a tutorial provider cannot return usable candidates."""


class TutorialCandidate(BaseModel):
    video_id: str = Field(min_length=1, max_length=64)
    title: str = Field(min_length=1, max_length=300)
    channel_title: str = Field(min_length=1, max_length=200)
    thumbnail_url: str | None = None
    duration_seconds: int | None = Field(default=None, ge=0)
    embeddable: bool = True
    language_hint: str | None = None
    source: str
    fetched_at: datetime

    @property
    def watch_url(self) -> str:
        return f"https://www.youtube.com/watch?v={self.video_id}"

    @property
    def embed_url(self) -> str:
        return f"https://www.youtube-nocookie.com/embed/{self.video_id}"


class TutorialSearchProvider(Protocol):
    def search(self, query: str, *, limit: int) -> list[TutorialCandidate]: ...


def tokenize(value: str) -> set[str]:
    return set(TOKEN_PATTERN.findall(value.casefold()))


def build_tutorial_query(
    *,
    recipe_title: str,
    cuisine: str,
    ingredient_names: list[str],
    language: str,
) -> str:
    parts = [recipe_title.strip(), cuisine.strip(), *[name.strip() for name in ingredient_names[:3]]]
    if language.strip():
        parts.append(language.strip())
    parts.append("cooking tutorial")
    return " ".join(part for part in parts if part)


class FixtureTutorialProvider:
    def __init__(self, fixture_path: str) -> None:
        self.fixture_path = Path(fixture_path)

    def search(self, query: str, *, limit: int) -> list[TutorialCandidate]:
        try:
            records = json.loads(self.fixture_path.read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError) as error:
            raise TutorialProviderError(f"Tutorial fixtures could not be loaded: {error}") from error

        query_tokens = tokenize(query).difference(GENERIC_QUERY_TOKENS)
        fetched_at = datetime.now(UTC)
        candidates: list[TutorialCandidate] = []
        for record in records:
            searchable = " ".join(
                [
                    str(record.get("title", "")),
                    str(record.get("channel_title", "")),
                    " ".join(record.get("query_terms", [])),
                ]
            )
            if query_tokens and not query_tokens.intersection(tokenize(searchable)):
                continue
            candidates.append(
                TutorialCandidate.model_validate(
                    {
                        **record,
                        "source": "fixture",
                        "fetched_at": fetched_at,
                    }
                )
            )
        return candidates[:limit]


class YouTubeDataApiProvider:
    """Extension point for the teammate-owned live YouTube Data API adapter.

    The fixture-backed contract, ranking policy, API response, and fallback are
    deliberately runnable now. The live request, pagination, quota handling,
    and response normalization remain the Retrieval work package.
    """

    def __init__(self, *, api_key: str | None, timeout_seconds: float) -> None:
        self.api_key = api_key
        self.timeout_seconds = timeout_seconds

    def search(self, query: str, *, limit: int) -> list[TutorialCandidate]:
        if not self.api_key:
            raise TutorialProviderError("YOUTUBE_API_KEY is not configured")
        raise TutorialProviderError("Live YouTube Data API retrieval is a scaffold hand-off and is not implemented")


def rank_tutorial_candidates(
    *,
    recipe_title: str,
    cuisine: str,
    ingredient_names: list[str],
    language: str,
    candidates: list[TutorialCandidate],
) -> list[tuple[float, list[str], TutorialCandidate]]:
    recipe_tokens = tokenize(recipe_title)
    cuisine_tokens = tokenize(cuisine)
    ingredient_tokens = set().union(*(tokenize(name) for name in ingredient_names[:3])) if ingredient_names else set()
    language_token = language.casefold().strip()

    ranked: list[tuple[float, list[str], TutorialCandidate]] = []
    for candidate in candidates:
        if not candidate.embeddable:
            continue

        title_tokens = tokenize(candidate.title)
        score = 0.0
        reasons: list[str] = []

        title_matches = len(recipe_tokens.intersection(title_tokens))
        if title_matches:
            score += title_matches * 10.0
            reasons.append(f"recipe title overlap: {title_matches}")

        cuisine_matches = len(cuisine_tokens.intersection(title_tokens))
        if cuisine_matches:
            score += cuisine_matches * 3.0
            reasons.append(f"cuisine overlap: {cuisine_matches}")

        ingredient_matches = len(ingredient_tokens.intersection(title_tokens))
        if ingredient_matches:
            score += ingredient_matches * 2.0
            reasons.append(f"ingredient overlap: {ingredient_matches}")

        if title_tokens.intersection({"tutorial", "recipe", "cook", "cooking"}):
            score += 4.0
            reasons.append("tutorial intent")

        if candidate.duration_seconds is not None and 120 <= candidate.duration_seconds <= 1800:
            score += 2.0
            reasons.append("practical duration")

        if language_token and candidate.language_hint == language_token:
            score += 1.0
            reasons.append("language match")

        ranked.append((score, reasons, candidate))

    ranked.sort(key=lambda item: (-item[0], item[2].video_id))
    return ranked
