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
                    allergen=None,
                ),
                RecipeIngredientResponse(
                    name="Lemon",
                    normalized_name="lemon",
                    quantity=1,
                    unit="whole",
                    preparation=None,
                    allergen=None,
                ),
            ],
            steps=[RecipeStepResponse(step_number=1, instruction="Cook.")],
        )


class FailingLiveTutorialProvider:
    def search(self, query: str, *, limit: int):
        raise TutorialProviderError("simulated YouTube outage")


def test_query_builder_keeps_recipe_context_and_execution_intent() -> None:
    query = build_tutorial_query(
        recipe_title="Lemon Chicken",
        cuisine="Mediterranean",
        ingredient_names=["Chicken breast", "Lemon"],
        language="en",
    )

    assert query == "Lemon Chicken Mediterranean Chicken breast Lemon en cooking tutorial"


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

    assert [item[2].video_id for item in ranked] == ["available-match", "available-decoy"]


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
