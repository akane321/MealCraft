import time
from datetime import UTC, datetime

from app.repositories.recipe import RecipeRepository
from app.retrieval.tutorials import (
    FixtureTutorialProvider,
    TutorialProviderError,
    TutorialSearchProvider,
    YouTubeDataApiProvider,
    build_tutorial_query,
    rank_tutorial_candidates,
)
from app.schemas.retrieval import RetrievalTrace, TutorialRecommendationResponse, TutorialVideoResponse
from app.services.recipe import RecipeService

# A search costs 100 of the 10,000 daily quota units, so repeated opens of the same dish must not search again.
# ponytail: per-process cache, lost on restart; a retrieval_observations table when ADR review settles its fields.
LIVE_CACHE_SECONDS = 24 * 3600
LIVE_CACHE_SIZE = 512
_live_cache: dict[str, tuple[float, list]] = {}


def create_tutorial_service(repository: RecipeRepository) -> "TutorialRecommendationService":
    from app.core.config import get_settings

    settings = get_settings()
    api_key = settings.youtube_api_key.get_secret_value() if settings.youtube_api_key else None
    return TutorialRecommendationService(
        recipe_service=RecipeService(repository),
        fixture_provider=FixtureTutorialProvider(settings.youtube_fixture_path),
        live_provider=YouTubeDataApiProvider(
            api_key=api_key,
            timeout_seconds=settings.youtube_timeout_seconds,
        ),
        live_by_default=api_key is not None,
    )


class TutorialRecommendationService:
    def __init__(
        self,
        *,
        recipe_service: RecipeService,
        fixture_provider: TutorialSearchProvider,
        live_provider: TutorialSearchProvider,
        live_by_default: bool = False,
    ) -> None:
        self.recipe_service = recipe_service
        self.fixture_provider = fixture_provider
        self.live_provider = live_provider
        self.live_by_default = live_by_default

    def recommend(
        self,
        recipe_slug: str,
        *,
        live: bool | None,
        language: str,
        candidate_limit: int = 10,
    ) -> TutorialRecommendationResponse | None:
        if live is None:
            live = self.live_by_default
        recipe = self.recipe_service.get_recipe(recipe_slug)
        if recipe is None:
            return None

        ingredient_names = [item.name for item in recipe.ingredients]
        query = build_tutorial_query(
            recipe_title=recipe.title,
            cuisine=recipe.cuisine,
            ingredient_names=ingredient_names,
            language=language,
        )

        warning: str | None = None
        provider_used = "youtube" if live else "fixture"
        mode = "live" if live else "fixture"
        status = "success"
        cached = _live_cache.get(query) if live else None
        try:
            if cached and time.monotonic() - cached[0] < LIVE_CACHE_SECONDS:
                candidates, mode = cached[1], "cache"  # fetched_at stays the original observation's
            elif live:
                candidates = self.live_provider.search(query, limit=candidate_limit)
                if len(_live_cache) >= LIVE_CACHE_SIZE:
                    del _live_cache[min(_live_cache, key=lambda key: _live_cache[key][0])]
                _live_cache[query] = (time.monotonic(), candidates)
            else:
                candidates = self.fixture_provider.search(query, limit=candidate_limit)
        except TutorialProviderError as error:
            warning = f"Live YouTube lookup was unavailable; tutorial fixtures were used. ({error})"
            candidates = self.fixture_provider.search(query, limit=candidate_limit)
            provider_used = "fixture"
            mode = "fixture"
            status = "degraded"

        ranked = rank_tutorial_candidates(
            recipe_title=recipe.title,
            cuisine=recipe.cuisine,
            ingredient_names=ingredient_names,
            language=language,
            candidates=candidates,
        )
        fetched_at = max((candidate.fetched_at for candidate in candidates), default=datetime.now(UTC))

        selected_video: TutorialVideoResponse | None = None
        selected_external_id: str | None = None
        if ranked:
            score, reasons, candidate = ranked[0]
            selected_external_id = candidate.video_id
            selected_video = TutorialVideoResponse(
                video_id=candidate.video_id,
                title=candidate.title,
                channel_title=candidate.channel_title,
                watch_url=candidate.watch_url,
                embed_url=candidate.embed_url,
                thumbnail_url=candidate.thumbnail_url,
                duration_seconds=candidate.duration_seconds,
                language_hint=candidate.language_hint,
                relevance_score=score,
                match_reasons=reasons,
            )
        elif status == "success":
            status = "no_match"  # the source answered; nothing in it is this dish (ADR-0022 section 3)
            warning = "No embeddable tutorial candidate passed the current ranking policy."

        trace = RetrievalTrace(
            requested_source="youtube",
            provider_used=provider_used,
            mode=mode,
            status=status,
            query=query,
            fetched_at=fetched_at,
            parser_version="youtube-fixture-v1" if provider_used == "fixture" else "youtube-data-api-v1",
            candidate_count=len(candidates),
            selected_external_id=selected_external_id,
            warnings=[warning] if warning else [],
        )
        return TutorialRecommendationResponse(
            recipe_slug=recipe.slug,
            recipe_title=recipe.title,
            query=query,
            selected_video=selected_video,
            retrieval=trace,
            warning=warning,
        )
