import html
import json
import re
import unicodedata
from datetime import UTC, datetime
from pathlib import Path
from typing import Protocol
from urllib.error import HTTPError, URLError
from urllib.parse import urlencode
from urllib.request import Request, urlopen

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


def singular(token: str) -> str:
    """Kebabs and kebab, croquettes and croquette are one word to a title match."""
    if len(token) > 4 and token.endswith("ies"):
        return token[:-3] + "y"
    if len(token) > 4 and token.endswith(("ches", "shes", "xes", "sses")):
        return token[:-2]
    if len(token) > 3 and token.endswith("s") and not token.endswith("ss"):
        return token[:-1]
    return token


def tokenize(value: str) -> set[str]:
    folded = unicodedata.normalize("NFKD", value).encode("ascii", "ignore").decode().casefold()  # Chả lụa: cha lua
    return {singular(token) for token in TOKEN_PATTERN.findall(folded)}


def build_tutorial_query(*, recipe_title: str) -> str:
    """The dish's name and "recipe", as a person would search. On the labelled developer dishes the longer
    query (cuisine, three ingredients, language, "cooking tutorial") found no video at all for three
    dishes and half as many right Top-1s (docs/design/external-retrieval-rag.md, ranking v2)."""
    return f"{recipe_title.strip()} recipe"


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


YOUTUBE_API = "https://www.googleapis.com/youtube/v3"
ISO_DURATION = re.compile(r"P(?:(\d+)D)?(?:T(?:(\d+)H)?(?:(\d+)M)?(?:(\d+)S)?)?")


def parse_iso_duration(value: str | None) -> int | None:
    """Seconds in a YouTube ISO-8601 duration; None for a live stream's P0D or anything unparsable."""
    match = ISO_DURATION.fullmatch(value or "")
    if not match:
        return None
    days, hours, minutes, seconds = (int(part or 0) for part in match.groups())
    total = ((days * 24 + hours) * 60 + minutes) * 60 + seconds
    return total or None


class YouTubeDataApiProvider:
    """Live YouTube Data API v3: one search call, then one videos call for duration and embeddability.

    A search costs 100 quota units and the videos call 1, so a default daily quota of 10,000 allows about
    99 searches; the service caches results for that reason. The key travels in a header, never in a URL,
    so no error message, log line or trace can carry it.
    """

    def __init__(self, *, api_key: str | None, timeout_seconds: float) -> None:
        self.api_key = api_key
        self.timeout_seconds = timeout_seconds

    def _get(self, endpoint: str, params: dict[str, str | int]) -> dict:
        request = Request(
            f"{YOUTUBE_API}/{endpoint}?{urlencode(params)}",
            headers={"X-Goog-Api-Key": self.api_key or "", "Accept": "application/json"},
        )
        try:
            with urlopen(request, timeout=self.timeout_seconds) as response:  # noqa: S310
                return json.loads(response.read().decode("utf-8"))
        except HTTPError as error:
            try:
                reasons = {item.get("reason") for item in json.loads(error.read()).get("error", {}).get("errors", [])}
            except (ValueError, AttributeError):
                reasons = set()
            if reasons & {"quotaExceeded", "dailyLimitExceeded", "rateLimitExceeded"}:
                raise TutorialProviderError("YouTube quota for today is used up") from None
            if reasons & {"keyInvalid", "keyExpired"} or error.code in (400, 401, 403):
                raise TutorialProviderError(f"YouTube refused the request (HTTP {error.code})") from None
            raise TutorialProviderError(f"YouTube request failed (HTTP {error.code})") from None
        except (URLError, TimeoutError, OSError) as error:
            raise TutorialProviderError(f"YouTube could not be reached: {type(error).__name__}") from None
        except ValueError:
            raise TutorialProviderError("YouTube answered with something that is not JSON") from None

    def search(self, query: str, *, limit: int) -> list[TutorialCandidate]:
        if not self.api_key:
            raise TutorialProviderError("YOUTUBE_API_KEY is not configured")
        found = self._get(
            "search",
            {
                "part": "snippet",
                "type": "video",
                "q": query,
                "maxResults": max(1, min(limit, 50)),
                "videoEmbeddable": "true",
                "safeSearch": "strict",
            },
        )
        try:
            ids = [item["id"]["videoId"] for item in found.get("items", [])]
        except (KeyError, TypeError):
            raise TutorialProviderError("YouTube search results were not in the expected shape") from None
        if not ids:
            return []
        details = self._get("videos", {"part": "snippet,contentDetails,status", "id": ",".join(ids)})
        fetched_at = datetime.now(UTC)
        by_id = {item.get("id"): item for item in details.get("items", [])}
        candidates: list[TutorialCandidate] = []
        for video_id in ids:  # keep YouTube's own relevance order
            item = by_id.get(video_id)
            if item is None:  # removed or private between the two calls
                continue
            snippet = item.get("snippet", {})
            if snippet.get("liveBroadcastContent", "none") != "none":
                continue
            language = snippet.get("defaultAudioLanguage") or snippet.get("defaultLanguage")
            thumbnails = snippet.get("thumbnails", {})
            sizes = [size for size in ("medium", "high", "default") if size in thumbnails]
            thumbnail = thumbnails[sizes[0]].get("url") if sizes else None
            try:
                candidates.append(
                    TutorialCandidate(
                        video_id=video_id,
                        title=html.unescape(snippet.get("title", ""))[:300],
                        channel_title=html.unescape(snippet.get("channelTitle", ""))[:200],
                        thumbnail_url=thumbnail,
                        duration_seconds=parse_iso_duration(item.get("contentDetails", {}).get("duration")),
                        embeddable=bool(item.get("status", {}).get("embeddable", False)),
                        language_hint=language.split("-")[0].casefold() if language else None,
                        source="youtube",
                        fetched_at=fetched_at,
                    )
                )
            except ValueError:  # an empty title or channel: not a candidate we can show
                continue
        return candidates


# A video that names one of these but the recipe doesn't is for a different dish:
# a lemon chicken tutorial is not a how-to for a lemon chickpea salad.
PROTEIN_WORDS = frozenset(
    {
        "beef",
        "chicken",
        "duck",
        "egg",
        "eggs",
        "fish",
        "lamb",
        "mutton",
        "pork",
        "prawn",
        "prawns",
        "salmon",
        "shrimp",
        "tofu",
        "tuna",
        "turkey",
    }
)


# Words in a recipe's name that say nothing about which dish it is, so they cannot qualify a video.
DISH_NOISE = frozenset(
    tokenize("easy best quick simple style homemade classic perfect recipe the and with of in a my ww point")
)
# Pantry staples: sharing one with a video title says nothing about the dish either.
STAPLES = frozenset(
    tokenize(
        "oil vegetable olive salt pepper black white sugar granulated brown water sauce powder flour all purpose "
        "butter vinegar ground fresh dried garlic onion cornstarch stock broth"
    )
)
SHORT_SECONDS = 90  # a Short cannot be cooked along to; the reviewers score it "too short to follow"


def rank_tutorial_candidates(
    *,
    recipe_title: str,
    cuisine: str,
    ingredient_names: list[str],
    language: str,
    candidates: list[TutorialCandidate],
) -> list[tuple[float, list[str], TutorialCandidate]]:
    """Ranking policy v2. Candidates arrive in YouTube's relevance order, which breaks ties."""
    recipe_tokens = tokenize(recipe_title) - DISH_NOISE
    cuisine_tokens = tokenize(cuisine)
    all_ingredient_tokens = set().union(*(tokenize(name) for name in ingredient_names)) if ingredient_names else set()
    ingredient_tokens = all_ingredient_tokens - STAPLES - recipe_tokens
    language_token = language.casefold().strip()

    ranked: list[tuple[float, int, list[str], TutorialCandidate]] = []
    for position, candidate in enumerate(candidates):
        if not candidate.embeddable:
            continue

        title_tokens = tokenize(candidate.title)
        if title_tokens.intersection(PROTEIN_WORDS) - recipe_tokens - all_ingredient_tokens:
            continue
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
        elif candidate.duration_seconds is not None and candidate.duration_seconds < SHORT_SECONDS:
            score -= 8.0
            reasons.append("too short to follow")

        if language_token and candidate.language_hint == language_token:
            score += 1.0
            reasons.append("language match")

        # Generic points (intent, duration, language) never qualify a video, and
        # one shared word is not the same dish: "Lemon Chicken" is no how-to for
        # "Chicken Broccoli Rice". The video title must carry two words of the
        # dish's name (all of them for a one-word name).
        if title_matches < min(2, len(recipe_tokens)):
            continue
        ranked.append((score, position, reasons, candidate))

    ranked.sort(key=lambda item: (-item[0], item[1]))
    return [(score, reasons, candidate) for score, _, reasons, candidate in ranked]
