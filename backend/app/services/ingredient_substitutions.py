"""Deterministic safety gate for model-proposed ingredient substitutes."""

import json
import re
from collections.abc import Iterable
from dataclasses import dataclass

from openai import APIError, OpenAI
from pydantic import BaseModel, ConfigDict, Field, ValidationError
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.agent import model_client
from app.agent.ingredient_matcher import names_of
from app.core.paths import repository_root
from app.data.allergens import allergen_conflicts
from app.data.external_ingredient_mapping import ReviewedIngredientMapper, normalize_alias
from app.data.ingredient_hierarchy import expand_exclusions
from app.models.recipe import Ingredient
from app.schemas.agent import AgentConstraintState


@dataclass(frozen=True)
class SafeSubstitute:
    ingredient_id: str
    display_name: str


class _SubstituteNames(BaseModel):
    model_config = ConfigDict(extra="forbid")
    candidates: list[str] = Field(min_length=1, max_length=8)


def reviewed_ingredient_mapper() -> ReviewedIngredientMapper:
    root = repository_root()
    mapper = ReviewedIngredientMapper.from_csv_files(
        root / "data-engineering/config/ingredient_aliases.csv",
        root / "data-engineering/config/ingredient_aliases_v2_additions.csv",
    )
    for ingredient_id, aliases in names_of("zh_names").items():
        canonical_id = ingredient_id.removeprefix("ING_").casefold()
        for alias in aliases:
            mapper.aliases.setdefault(normalize_alias(alias), set()).add(canonical_id)
    return mapper


class OpenAISubstituteGenerator:
    """Ask the model for ingredient names; the result is untrusted until catalog-filtered."""

    def __init__(self, *, api_key: str, model: str, client=None) -> None:
        self.model = model
        self.client = client or OpenAI(api_key=api_key, http_client=model_client.http_client())

    def suggest(self, source_ingredient: str, *, use_context: str | None = None) -> list[str]:
        prompt = (
            "Suggest up to six plausible culinary ingredient substitutes for this ingredient. "
            "Return only a JSON object with a candidates array of short ingredient names. Do not claim the "
            "options are safe for allergies, dietary rules, or halal; the application will check catalog facts. "
            f"Ingredient: {source_ingredient}"
        )
        if use_context:
            prompt += f"\nRecipe context: {use_context}"
        response = self.client.responses.create(
            model=self.model,
            input=prompt,
            instructions="Return valid JSON only. Do not include explanations or safety claims.",
        )
        raw = getattr(response, "output_text", "")
        try:
            parsed = _SubstituteNames.model_validate(json.loads(raw))
        except (json.JSONDecodeError, ValidationError) as error:
            raise ValueError("Substitute model returned an invalid candidate list") from error
        return list(dict.fromkeys(name.strip() for name in parsed.candidates if name.strip()))


class IngredientSubstitutionFoodQuestionAnswerer:
    """Answer explicit replacement questions using model ideas filtered by current chat constraints."""

    _patterns = (
        re.compile(r"\binstead of\s+([^?.!,;]+)", re.IGNORECASE),
        re.compile(r"\bsubstitute for\s+([^?.!,;]+)", re.IGNORECASE),
        re.compile(r"\breplace\s+([^?.!,;]+?)\s+with\b", re.IGNORECASE),
        re.compile(r"(?:没有|缺少)\s*(.{1,24}?)(?:了)?\s*(?:的话)?[，,]?\s*(?:可以)?用什么代替"),
        re.compile(r"用什么(?:来)?代替\s*(.{1,48}?)(?:[？?。！!，,]|$)"),
        re.compile(r"(.{1,24}?)(?:可以|能)用什么代替"),
    )

    def __init__(
        self,
        session: Session,
        *,
        generator: OpenAISubstituteGenerator,
        mapper: ReviewedIngredientMapper | None = None,
    ) -> None:
        self.session = session
        self.generator = generator
        self.mapper = mapper or self._load_mapper()

    @staticmethod
    def _load_mapper() -> ReviewedIngredientMapper:
        return reviewed_ingredient_mapper()

    def answer(self, message: str, lang: str, constraints: AgentConstraintState) -> str | None:
        source = next(
            (match.group(1).strip() for pattern in self._patterns if (match := pattern.search(message))),
            None,
        )
        if source is None:
            return None
        resolved = self.mapper.resolve(source)
        if resolved.canonical_id is None:
            normalized_source = normalize_alias(source)
            matching_aliases = [alias for alias in self.mapper.aliases if normalized_source.startswith(f"{alias} ")]
            if matching_aliases:
                longest = max(map(len, matching_aliases))
                best = {self.mapper.resolve(alias).canonical_id for alias in matching_aliases if len(alias) == longest}
                best.discard(None)
                if len(best) == 1:
                    resolved = self.mapper.resolve(next(alias for alias in matching_aliases if len(alias) == longest))
        if resolved.canonical_id is None:
            return None
        # Ingredient-level catalog facts do not certify vegan/vegetarian status. Fail closed for these requests.
        if constraints.dietary_preferences:
            if lang == "zh":
                return "我无法核实替代食材是否满足家庭的饮食偏好，因此不会推荐未经核验的选项。"
            return (
                "I can’t verify that substitute options meet the household’s dietary preferences, "
                "so I won’t suggest unverified options."
            )

        try:
            proposed = self.generator.suggest(source)
        except (APIError, ValueError):
            return None
        names = {self.mapper.resolve(item).canonical_id for item in proposed}
        names.discard(None)
        catalog = list(self.session.scalars(select(Ingredient).where(Ingredient.normalized_name.in_(names))))
        exclusions = expand_exclusions([*constraints.excluded_ingredients, resolved.canonical_id])
        safe = filter_safe_substitutes(
            catalog,
            household_allergens=constraints.allergens,
            excluded_ingredients=exclusions,
            requires_halal=constraints.requires_halal,
        )
        if not safe:
            return (
                "目录中没有找到通过家庭限制核验的替代食材。"
                if lang == "zh"
                else "I couldn’t find a catalog substitute verified against the household’s constraints."
            )
        options = ", ".join(item.display_name for item in safe)
        if lang == "zh":
            return f"可考虑：{options}。这些选项已按食材目录中的过敏原、忌口和清真信息筛选。"
        return f"Possible options: {options}. These were filtered using catalog allergen, exclusion, and halal data."


def filter_safe_substitutes(
    candidates: Iterable[object],
    *,
    household_allergens: Iterable[str] = (),
    excluded_ingredients: Iterable[str] = (),
    requires_halal: bool = False,
) -> list[SafeSubstitute]:
    """Return only catalog candidates that satisfy the caller's hard ingredient constraints.

    The function is intended to run after a model proposes options and before any
    option is shown to a household. Missing allergen data fails closed when that
    household has declared allergens; halal must be explicitly verified when
    requested.
    """
    wanted_allergens = list(household_allergens)
    excluded = {item.casefold() for item in excluded_ingredients}
    safe: list[SafeSubstitute] = []
    for ingredient in candidates:
        ingredient_id = str(getattr(ingredient, "normalized_name", "")).casefold()
        if not ingredient_id or ingredient_id in excluded:
            continue

        allergens = getattr(ingredient, "allergens", None)
        if allergens is None and wanted_allergens:
            continue
        present, unverifiable = allergen_conflicts(wanted_allergens, allergens or [])
        if present or unverifiable:
            continue

        if requires_halal and getattr(ingredient, "halal_status", None) != "halal":
            continue

        safe.append(
            SafeSubstitute(
                ingredient_id=ingredient_id,
                display_name=str(getattr(ingredient, "display_name", ingredient_id)),
            )
        )
    return safe
