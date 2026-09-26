from datetime import UTC, datetime
from pathlib import Path

from app.retrieval.tutorials import (
    FixtureTutorialProvider,
    TutorialCandidate,
    TutorialProviderError,
    build_tutorial_query,
    rank_tutorial_candidates,
)
from app.schemas.recipe import (
    RecipeDetailResponse,
    RecipeIngredientResponse,
    RecipeNutritionResponse,
    RecipeStepResponse,
)
from app.services.tutorial import TutorialRecommendationService

FIXTURE_PATH = Path("data/fixtures/youtube-tutorials.json")


class RecipeServiceStub:
    def get_recipe(self, slug: str) -> RecipeDetailResponse | None:
        if slug != "lemon-chicken":
            return None
        return RecipeDetailResponse(
            id=1,
            slug="lemon-chicken",
            title="Lemon Chicken",
            description="Fixture recipe",
            cuisine="Mediterranean-inspired",
            meal_type="main",
            servings=2,
            total_time_minutes=30,
            dietary_tags=["high-protein"],
            nutrition=RecipeNutritionResponse(
                calories_kcal=480,
                protein_g=42,
                carbohydrate_g=36,
                fat_g=18,
                sodium_mg=590,
                sugar_g=5,
            ),
            ingredients=[
                RecipeIngredientResponse(
                    name="Chicken breast",
                    normalized_name="chicken_breast",
                    quantity=300,
                    unit="g",
                    preparation=None,
                    allergens=[],
                ),
                RecipeIngredientResponse(
                    name="Lemon",
                    normalized_name="lemon",
                    quantity=1,
                    unit="whole",
                    preparation=None,
                    allergens=[],
                ),
            ],
            steps=[RecipeStepResponse(step_number=1, instruction="Cook.")],
        )


class FailingLiveTutorialProvider:
    def search(self, query: str, *, limit: int):
        raise TutorialProviderError("simulated YouTube outage")


def test_query_is_the_dish_name_as_a_person_would_search() -> None:
    assert build_tutorial_query(recipe_title=" Lemon Chicken ") == "Lemon Chicken recipe"


def test_titles_match_across_plurals_and_accents() -> None:
    from app.retrieval.tutorials import tokenize

    assert tokenize("Shish Kebabs") == tokenize("shish kebab")
    assert tokenize("Chả lụa") == {"cha", "lua"}
    assert tokenize("Croquettes") == tokenize("croquette")


def _candidate(video_id: str, title: str, seconds: int) -> TutorialCandidate:
    return TutorialCandidate(
        video_id=video_id,
        title=title,
        channel_title="C",
        duration_seconds=seconds,
        embeddable=True,
        language_hint="en",
        source="fixture",
        fetched_at=datetime(2026, 9, 25, tzinfo=UTC),
    )


def test_ranking_v2_sinks_shorts_ignores_staples_and_keeps_youtubes_order_on_ties() -> None:
    ranked = rank_tutorial_candidates(
        recipe_title="Stir-Fry Chicken",
        cuisine="chinese",
        ingredient_names=["vegetable oil", "soy sauce", "chicken breast"],
        language="en",
        candidates=[
            _candidate("short", "Chicken Stir Fry Recipe #shorts", 45),
            _candidate("sauce", "Chicken Stir Fry in Oyster Sauce Recipe", 300),
            _candidate("first", "Chicken Stir Fry Recipe", 300),
            _candidate("second", "Chicken Stir Fry Recipe", 300),
        ],
    )
    # "sauce" is a staple, so sharing it with the recipe earns nothing; equal scores keep YouTube's order.
    assert [item[2].video_id for item in ranked] == ["sauce", "first", "second", "short"]
    assert "too short to follow" in ranked[-1][1]


def test_generic_words_in_a_dish_name_cannot_qualify_a_video() -> None:
    ranked = rank_tutorial_candidates(
        recipe_title="Easy Thai Chicken",
        cuisine="thai",
        ingredient_names=["chicken"],
        language="en",
        candidates=[_candidate("curry", "Easy Thai Curry Recipe", 300)],
    )
    assert ranked == []  # only "thai" is the dish; "easy" says nothing


def test_ranker_filters_non_embeddable_candidates_and_prefers_recipe_overlap() -> None:
    fetched_at = datetime.now(UTC)
    candidates = [
        TutorialCandidate(
            video_id="blocked-best-title",
            title="Perfect Lemon Chicken Cooking Tutorial",
            channel_title="Blocked",
            duration_seconds=600,
            embeddable=False,
            language_hint="en",
            source="fixture",
            fetched_at=fetched_at,
        ),
        TutorialCandidate(
            video_id="available-match",
            title="Lemon Chicken Cooking Tutorial",
            channel_title="Available",
            duration_seconds=600,
            embeddable=True,
            language_hint="en",
            source="fixture",
            fetched_at=fetched_at,
        ),
        TutorialCandidate(
            video_id="available-decoy",
            title="Chocolate Cake Tutorial",
            channel_title="Available",
            duration_seconds=600,
            embeddable=True,
            language_hint="en",
            source="fixture",
            fetched_at=fetched_at,
        ),
    ]

    ranked = rank_tutorial_candidates(
        recipe_title="Lemon Chicken",
        cuisine="Mediterranean",
        ingredient_names=["Chicken breast", "Lemon"],
        language="en",
        candidates=candidates,
    )

    # The cake video shares nothing with the dish, so generic points cannot select it.
    assert [item[2].video_id for item in ranked] == ["available-match"]


def test_ranker_rejects_a_video_for_a_protein_the_dish_does_not_contain() -> None:
    fetched_at = datetime(2026, 9, 19, tzinfo=UTC)
    chicken = TutorialCandidate(
        video_id="lemon-chicken",
        title="Lemon Chicken Cooking Tutorial",
        channel_title="Fixture",
        duration_seconds=540,
        embeddable=True,
        language_hint="en",
        source="fixture",
        fetched_at=fetched_at,
    )
    ranked = rank_tutorial_candidates(
        recipe_title="Lemon Chickpea Salad",
        cuisine="Mediterranean",
        ingredient_names=["Chickpeas", "Lemon", "Cucumber"],
        language="en",
        candidates=[chicken],
    )
    assert ranked == []


def test_tutorial_service_returns_only_the_best_fixture_candidate() -> None:
    service = TutorialRecommendationService(
        recipe_service=RecipeServiceStub(),
        fixture_provider=FixtureTutorialProvider(str(FIXTURE_PATH)),
        live_provider=FailingLiveTutorialProvider(),
    )

    result = service.recommend("lemon-chicken", live=False, language="en")

    assert result is not None
    assert result.selected_video is not None
    assert result.selected_video.video_id == "fixture-lemon-chicken-best"
    assert result.retrieval.candidate_count == 3
    assert result.retrieval.selected_external_id == "fixture-lemon-chicken-best"


def test_live_tutorial_failure_is_explicit_and_falls_back_to_fixture() -> None:
    service = TutorialRecommendationService(
        recipe_service=RecipeServiceStub(),
        fixture_provider=FixtureTutorialProvider(str(FIXTURE_PATH)),
        live_provider=FailingLiveTutorialProvider(),
    )

    result = service.recommend("lemon-chicken", live=True, language="en")

    assert result is not None
    assert result.selected_video is not None
    assert result.retrieval.status == "degraded"
    assert result.retrieval.provider_used == "fixture"
    assert "simulated YouTube outage" in result.warning


# --- live YouTube Data API provider -------------------------------------------------

import io  # noqa: E402
import json  # noqa: E402
from urllib.error import HTTPError  # noqa: E402

import pytest  # noqa: E402

from app.retrieval import tutorials  # noqa: E402
from app.retrieval.tutorials import YouTubeDataApiProvider, parse_iso_duration  # noqa: E402
from app.services import tutorial as tutorial_service  # noqa: E402

SECRET = "test-key-that-must-not-leak"


class FakeResponse(io.BytesIO):
    def __enter__(self):
        return self

    def __exit__(self, *args) -> None:
        self.close()


def fake_youtube(monkeypatch, seen: list) -> None:
    search = {"items": [{"id": {"videoId": vid}} for vid in ("live-now", "gone", "good", "blocked")]}
    videos = {
        "items": [
            {
                "id": "live-now",
                "snippet": {"title": "Lemon Chicken LIVE", "channelTitle": "C", "liveBroadcastContent": "live"},
                "contentDetails": {"duration": "P0D"},
                "status": {"embeddable": True},
            },
            {
                "id": "good",
                "snippet": {
                    "title": "Lemon Chicken &amp; Rice Recipe",
                    "channelTitle": "Chef&#39;s Table",
                    "defaultAudioLanguage": "en-GB",
                    "liveBroadcastContent": "none",
                    "thumbnails": {"medium": {"url": "https://i.ytimg.com/good.jpg"}},
                },
                "contentDetails": {"duration": "PT12M5S"},
                "status": {"embeddable": True},
            },
            {
                "id": "blocked",
                "snippet": {"title": "Lemon Chicken", "channelTitle": "B", "liveBroadcastContent": "none"},
                "contentDetails": {"duration": "PT3M"},
                "status": {"embeddable": False},
            },
        ]
    }

    def opener(request, timeout):
        seen.append(request)
        return FakeResponse(json.dumps(search if "/search?" in request.full_url else videos).encode())

    monkeypatch.setattr(tutorials, "urlopen", opener)


def test_iso_durations_parse_and_a_live_stream_has_none() -> None:
    assert parse_iso_duration("PT12M5S") == 725
    assert parse_iso_duration("PT1H") == 3600
    assert parse_iso_duration("P1DT2S") == 86402
    assert parse_iso_duration("P0D") is None
    assert parse_iso_duration("garbage") is None


def test_live_provider_normalises_results_and_keeps_the_key_out_of_urls(monkeypatch) -> None:
    seen: list = []
    fake_youtube(monkeypatch, seen)

    candidates = YouTubeDataApiProvider(api_key=SECRET, timeout_seconds=3).search("lemon chicken", limit=10)

    # The live broadcast and the video that vanished between calls are dropped; YouTube's order is kept.
    assert [c.video_id for c in candidates] == ["good", "blocked"]
    good = candidates[0]
    assert (good.title, good.channel_title) == ("Lemon Chicken & Rice Recipe", "Chef's Table")
    assert (good.duration_seconds, good.language_hint, good.source) == (725, "en", "youtube")
    assert good.thumbnail_url == "https://i.ytimg.com/good.jpg"
    assert candidates[1].embeddable is False  # filtering is the ranker's job, not the provider's
    assert all(SECRET not in r.full_url and r.get_header("X-goog-api-key") == SECRET for r in seen)


def test_quota_exhaustion_is_named_and_never_carries_the_key(monkeypatch) -> None:
    body = json.dumps({"error": {"errors": [{"reason": "quotaExceeded"}]}}).encode()

    def opener(request, timeout):
        raise HTTPError(request.full_url, 403, "Forbidden", {}, io.BytesIO(body))

    monkeypatch.setattr(tutorials, "urlopen", opener)
    with pytest.raises(TutorialProviderError) as raised:
        YouTubeDataApiProvider(api_key=SECRET, timeout_seconds=3).search("lemon chicken", limit=5)
    assert "quota" in str(raised.value)
    assert SECRET not in str(raised.value)


def test_service_goes_live_when_a_key_exists_and_serves_repeats_from_cache(monkeypatch) -> None:
    seen: list = []
    fake_youtube(monkeypatch, seen)
    monkeypatch.setattr(tutorial_service, "_live_cache", {})
    service = TutorialRecommendationService(
        recipe_service=RecipeServiceStub(),
        fixture_provider=FixtureTutorialProvider(str(FIXTURE_PATH)),
        live_provider=YouTubeDataApiProvider(api_key=SECRET, timeout_seconds=3),
        live_by_default=True,
    )

    first = service.recommend("lemon-chicken", live=None, language="en")
    second = service.recommend("lemon-chicken", live=None, language="en")

    assert first.retrieval.mode == "live" and first.retrieval.provider_used == "youtube"
    assert first.selected_video.video_id == "good"
    assert second.retrieval.mode == "cache" and second.selected_video.video_id == "good"
    assert second.retrieval.fetched_at == first.retrieval.fetched_at  # the observation's age, not the read's
    assert len(seen) == 2  # one search + one videos call, both for the first request only


def test_a_failed_live_lookup_is_not_cached(monkeypatch) -> None:
    monkeypatch.setattr(tutorial_service, "_live_cache", {})
    service = TutorialRecommendationService(
        recipe_service=RecipeServiceStub(),
        fixture_provider=FixtureTutorialProvider(str(FIXTURE_PATH)),
        live_provider=FailingLiveTutorialProvider(),
        live_by_default=True,
    )
    service.recommend("lemon-chicken", live=None, language="en")
    assert tutorial_service._live_cache == {}


def test_a_source_with_nothing_for_the_dish_is_no_match_not_an_outage() -> None:
    class EmptyProvider:
        def search(self, query: str, *, limit: int):
            return []

    service = TutorialRecommendationService(
        recipe_service=RecipeServiceStub(),
        fixture_provider=EmptyProvider(),
        live_provider=FailingLiveTutorialProvider(),
    )
    result = service.recommend("lemon-chicken", live=False, language="en")
    assert result.selected_video is None
    assert result.retrieval.status == "no_match"


def test_the_shown_tutorial_carries_a_digest_of_its_evidence() -> None:
    from app.retrieval.evidence import packet_digest, tutorial_packet

    service = TutorialRecommendationService(
        recipe_service=RecipeServiceStub(),
        fixture_provider=FixtureTutorialProvider(str(FIXTURE_PATH)),
        live_provider=FailingLiveTutorialProvider(),
    )
    first = service.recommend("lemon-chicken", live=False, language="en")
    second = service.recommend("lemon-chicken", live=False, language="en")

    packet = tutorial_packet(first.selected_video, first.retrieval, recipe_slug="lemon-chicken")
    assert first.evidence_digest == packet_digest(packet)
    assert [item.external_id for item in packet.items] == ["fixture-lemon-chicken-best"]
    assert packet.items[0].facts["mode"] == first.retrieval.mode
    # The digest is over the evidence, not when it was assembled, so the same video gives the same digest.
    assert packet_digest(tutorial_packet(second.selected_video, first.retrieval, recipe_slug="lemon-chicken")) == (
        first.evidence_digest
    )
