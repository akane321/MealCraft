"""Run the pure-LLM, single-turn Sprint 2 baseline.

The model sees household and task facts only.  It receives no MealCraft recipe
catalog, grocery snapshot, retrieval result, calculator, web search, or tool.
Its structured answer is then scored through the shared baseline mapping,
coverage verification, and deterministic recomputation layers.
"""

from __future__ import annotations

import argparse
import json
import time
from collections.abc import Callable, Iterable
from dataclasses import asdict, dataclass
from pathlib import Path
from typing import Any, Protocol

from langchain_openai import ChatOpenAI
from pydantic import ValidationError

from app.agent import model_client
from app.agent.ingredient_matcher import IngredientMatcher, catalog_aliases
from app.core.config import get_settings
from app.core.paths import repository_root
from app.data.release_v2 import map_allergens
from app.evaluation.baseline_mapping import CoverageResult, map_response_ingredients
from app.evaluation.baseline_output import BaselineResponse
from app.evaluation.baseline_recomputation import (
    BaselineRecomputation,
    IngredientEvaluationFacts,
    recompute_ingredient_baseline,
)
from app.evaluation.baseline_verification import VerificationResult, verify_coverage
from app.evaluation.release_catalog import NOT_PURCHASED, load_release_catalog
from app.schemas.planning_v2 import PlanningNutrients, PlanningProductOption

SYSTEM_ID = "pure-llm-single-turn"
MAX_ATTEMPTS = 2
RELEASE_INGREDIENTS = Path("data-engineering/data/release/v2.1/ingredients.jsonl")


class StructuredModel(Protocol):
    def invoke(self, prompt: str) -> Any: ...


@dataclass(frozen=True)
class ModelUsage:
    input_tokens: int | None = None
    output_tokens: int | None = None
    total_tokens: int | None = None
    cost_usd: float | None = None


@dataclass(frozen=True)
class GenerationResult:
    response: BaselineResponse | None
    attempts: int
    elapsed_seconds: float
    usage: ModelUsage
    parse_errors: tuple[str, ...]


@dataclass(frozen=True)
class BaselineResources:
    names: dict[str, str]
    aliases: dict[str, list[str]]
    matcher: IngredientMatcher
    ingredient_facts: dict[str, IngredientEvaluationFacts]
    frozen_products: list[PlanningProductOption]
    not_purchased: frozenset[str]


@dataclass(frozen=True)
class EpisodeResult:
    episode_id: str
    system_id: str
    valid_output: bool
    generation: GenerationResult
    coverage: CoverageResult | None = None
    verification: VerificationResult | None = None
    recomputation: BaselineRecomputation | None = None


PROMPT = """You are planning meals for one household in a single response. You have no tools,
web search, calculator, recipe database, grocery database, retrieval system, or hidden MealCraft
context. Use only the household and task facts below.

Return an answer matching the supplied JSON schema. For a plan, provide every ingredient in grams
and a cooking time for every dish. Use the supplied slot IDs and role IDs where the household task
defines them. Ask for clarification only when a missing fact prevents a responsible plan, and report
infeasibility rather than claiming an impossible plan. Do not add fields outside the schema.

Fixed identifiers for this answer:
- episode_id: {episode_id}
- system_id: {system_id}

HOUSEHOLD_AND_TASK_INPUT:
{task_input}
"""


def household_task_input(episode: dict[str, Any]) -> dict[str, Any]:
    """Select only facts a household would supply to a planner."""
    scenario = episode.get("scenario", episode)
    allowed = (
        "user_request",
        "conversation_history",
        "household_profile",
        "pantry",
        "planning_horizon",
        "locked_or_completed_meals",
    )
    return {key: scenario[key] for key in allowed if key in scenario}


def render_prompt(episode: dict[str, Any]) -> str:
    episode_id = str(episode.get("episode_id") or episode.get("scenario_id") or episode.get("id") or "")
    if not episode_id:
        raise ValueError("episode has no episode_id, scenario_id, or id")
    return PROMPT.format(
        episode_id=episode_id,
        system_id=SYSTEM_ID,
        task_input=json.dumps(household_task_input(episode), ensure_ascii=False, sort_keys=True),
    )


def create_model() -> StructuredModel:
    """Build the same configured mini chat model and shared HTTP client as the product."""
    settings = get_settings()
    if settings.openai_api_key is None:
        raise RuntimeError("pure LLM baseline requires OPENAI_API_KEY (unit tests inject a mocked model)")
    return ChatOpenAI(
        api_key=settings.openai_api_key.get_secret_value(),
        model=settings.openai_model,
        temperature=0,
        timeout=settings.openai_timeout_seconds,
        max_retries=0,
        http_client=model_client.http_client(),
    ).with_structured_output(BaselineResponse, method="json_schema", include_raw=True)


def generate(episode: dict[str, Any], model: StructuredModel) -> GenerationResult:
    """Call once, retry one malformed answer once, and never repair model content."""
    episode_id = str(episode.get("episode_id") or episode.get("scenario_id") or episode.get("id") or "")
    prompt = render_prompt(episode)
    errors: list[str] = []
    usages: list[ModelUsage] = []
    started = time.perf_counter()
    for attempt in range(1, MAX_ATTEMPTS + 1):
        try:
            result = model.invoke(prompt)
            parsed, raw = _parsed_and_raw(result)
            usages.append(_usage(raw))
            response = BaselineResponse.model_validate(parsed)
            if response.episode_id != episode_id or response.system_id != SYSTEM_ID:
                raise ValueError("response identifiers do not match the requested episode and system")
            return GenerationResult(
                response=response,
                attempts=attempt,
                elapsed_seconds=time.perf_counter() - started,
                usage=_sum_usage(usages),
                parse_errors=tuple(errors),
            )
        except (ValidationError, ValueError, TypeError, json.JSONDecodeError) as error:
            errors.append(str(error))
    return GenerationResult(
        response=None,
        attempts=MAX_ATTEMPTS,
        elapsed_seconds=time.perf_counter() - started,
        usage=_sum_usage(usages),
        parse_errors=tuple(errors),
    )


def run_episode(
    episode: dict[str, Any],
    *,
    model: StructuredModel,
    resources: BaselineResources,
) -> EpisodeResult:
    generated = generate(episode, model)
    episode_id = str(episode.get("episode_id") or episode.get("scenario_id") or episode.get("id") or "")
    if generated.response is None:
        return EpisodeResult(episode_id, SYSTEM_ID, False, generated)
    coverage = map_response_ingredients(
        generated.response,
        names=resources.names,
        aliases=resources.aliases,
        matcher=resources.matcher,
    )
    return EpisodeResult(
        episode_id=episode_id,
        system_id=SYSTEM_ID,
        valid_output=True,
        generation=generated,
        coverage=coverage,
        verification=verify_coverage(coverage),
        recomputation=recompute_ingredient_baseline(
            coverage,
            ingredient_facts=resources.ingredient_facts,
            frozen_products=resources.frozen_products,
            not_purchased=resources.not_purchased,
        ),
    )


def load_resources(root: Path | None = None) -> BaselineResources:
    root = root or repository_root()
    release = load_release_catalog(root)
    names = {row["normalized_name"]: row["display_name"] for row in release.ingredients}
    aliases = {key: values for key, values in catalog_aliases().items() if key in names}
    facts = _ingredient_facts(root)
    products = [
        PlanningProductOption(
            ingredient_id=row["ingredient_id"],
            product_id=row["external_id"],
            package_quantity=row["package_size"],
            package_unit=row["package_unit"],
            price_sgd=row["price_sgd"],
            available=row["in_stock"],
        )
        for row in release.products
    ]
    return BaselineResources(
        names=names,
        aliases=aliases,
        matcher=IngredientMatcher(names, aliases=aliases, mode="spelling"),
        ingredient_facts=facts,
        frozen_products=products,
        not_purchased=frozenset(NOT_PURCHASED),
    )


def _ingredient_facts(root: Path) -> dict[str, IngredientEvaluationFacts]:
    facts: dict[str, IngredientEvaluationFacts] = {}
    for line in (root / RELEASE_INGREDIENTS).read_text(encoding="utf-8").splitlines():
        row = json.loads(line)
        ingredient_id = row["ingredient_id"].removeprefix("ING_").lower()
        form = (row.get("forms") or {}).get(row["ingredient_id"], {})
        nutrition = form.get("nutrition_per_100g")
        nutrients = None
        if nutrition is not None:
            nutrients = PlanningNutrients(
                calories_kcal=nutrition["energy_kcal"],
                protein_g=nutrition["protein_g"],
                carbohydrate_g=nutrition["carbohydrate_g"],
                fat_g=nutrition["fat_g"],
                sodium_mg=nutrition["sodium_mg"],
                sugar_g=nutrition["sugar_g"],
            )
        allergens = (
            tuple(sorted(map_allergens(row["allergens"]))) if row.get("allergen_status") == "confirmed" else None
        )
        facts[ingredient_id] = IngredientEvaluationFacts(allergens=allergens, nutrition_per_100g=nutrients)
    return facts


def _parsed_and_raw(result: Any) -> tuple[Any, Any]:
    if isinstance(result, dict) and "parsed" in result:
        parsed = result.get("parsed")
        if parsed is None:
            error = result.get("parsing_error")
            raise ValueError(f"structured output was malformed: {error or 'no parsed response'}")
        return parsed, result.get("raw")
    return result, result


def _usage(raw: Any) -> ModelUsage:
    metadata = getattr(raw, "usage_metadata", None) or {}
    response_metadata = getattr(raw, "response_metadata", None) or {}
    token_usage = response_metadata.get("token_usage") or {}
    cost = metadata.get("cost_usd") or response_metadata.get("cost_usd") or token_usage.get("cost_usd")
    return ModelUsage(
        input_tokens=_integer(metadata.get("input_tokens") or token_usage.get("prompt_tokens")),
        output_tokens=_integer(metadata.get("output_tokens") or token_usage.get("completion_tokens")),
        total_tokens=_integer(metadata.get("total_tokens") or token_usage.get("total_tokens")),
        cost_usd=float(cost) if cost is not None else None,
    )


def _integer(value: Any) -> int | None:
    return int(value) if value is not None else None


def _sum_usage(usages: Iterable[ModelUsage]) -> ModelUsage:
    rows = list(usages)

    def total(field: str) -> int | float | None:
        values = [getattr(row, field) for row in rows if getattr(row, field) is not None]
        return sum(values) if values else None

    return ModelUsage(
        input_tokens=total("input_tokens"),  # type: ignore[arg-type]
        output_tokens=total("output_tokens"),  # type: ignore[arg-type]
        total_tokens=total("total_tokens"),  # type: ignore[arg-type]
        cost_usd=total("cost_usd"),  # type: ignore[arg-type]
    )


def load_episodes(path: Path) -> list[dict[str, Any]]:
    files = sorted(path.glob("*.json")) if path.is_dir() else [path]
    episodes: list[dict[str, Any]] = []
    for file in files:
        payload = json.loads(file.read_text(encoding="utf-8"))
        if isinstance(payload, list):
            episodes.extend(payload)
        elif "episodes" in payload and isinstance(payload["episodes"], list):
            episodes.extend(payload["episodes"])
        else:
            episodes.append(payload)
    return episodes


def result_payload(result: EpisodeResult) -> dict[str, Any]:
    payload = asdict(result)
    response = result.generation.response
    payload["generation"]["response"] = response.model_dump(mode="json") if response is not None else None
    return payload


def main(model_factory: Callable[[], StructuredModel] = create_model) -> int:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("--episodes", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    model = model_factory()
    resources = load_resources()
    results = [run_episode(episode, model=model, resources=resources) for episode in load_episodes(args.episodes)]
    report = {
        "system_id": SYSTEM_ID,
        "model": get_settings().openai_model,
        "episodes": [result_payload(result) for result in results],
    }
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(json.dumps(report, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    print(f"pure LLM baseline: {sum(result.valid_output for result in results)}/{len(results)} valid outputs")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
