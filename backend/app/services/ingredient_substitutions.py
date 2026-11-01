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
from app.agent.replies import listed, word
from app.core.paths import repository_root
from app.data.allergens import allergen_conflicts
from app.data.external_ingredient_mapping import ReviewedIngredientMapper, normalize_alias
from app.data.halal import needs_certification
from app.data.ingredient_hierarchy import expand_exclusions
from app.models.recipe import Ingredient
from app.planning.vegetable_led import food_groups
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

    def __init__(self, *, api_key: str, model: str, timeout_seconds: float = 60.0, client=None) -> None:
        self.model = model
        self.client = client or OpenAI(api_key=api_key, timeout=timeout_seconds, http_client=model_client.http_client())

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
            return self._unverified(lang)
        members = constraints.household.members if constraints.household and constraints.household.members else []
        # Every diet at the table, and whose it is (None: the household's own); each candidate must suit all of them.
        diets = [(None, diet) for diet in constraints.dietary_preferences] + [
            (member.name, diet) for member in members for diet in member.dietary_preferences
        ]

        try:
            proposed = self.generator.suggest(source)
        except (APIError, ValueError, TimeoutError, ConnectionError):
            return self._unverified(lang)
        names = {self.mapper.resolve(item).canonical_id for item in proposed}
        names.discard(None)
        catalog = list(self.session.scalars(select(Ingredient).where(Ingredient.normalized_name.in_(names))))
        exclusions = expand_exclusions(
            [
                *constraints.excluded_ingredients,
                resolved.canonical_id,
                *(item for member in members for item in member.excluded_ingredients),
            ]
        )
        safe = filter_safe_substitutes(
            catalog,
            household_allergens=[*constraints.allergens, *(item for member in members for item in member.allergens)],
            excluded_ingredients=exclusions,
            requires_halal=constraints.requires_halal,
        )
        # A candidate that breaks a diet is dropped; one the catalog cannot vouch for is dropped and said.
        by_id = {str(item.normalized_name).casefold(): item for item in catalog}
        kept, unknown = [], set()
        for item in safe:
            verdicts = {(who, diet): suits_diet(by_id[item.ingredient_id], diet) for who, diet in diets}
            if False in verdicts.values():
                continue
            if None in verdicts.values():
                unknown.update(key for key, verdict in verdicts.items() if verdict is None)
                continue
            kept.append(item)
        note = self._unverified_diets([key for key in dict.fromkeys(diets) if key in unknown], lang, others=bool(kept))
        if not kept:
            return (
                "目录中没有找到通过家庭限制核验的替代食材。"
                if lang == "zh"
                else "I couldn’t find a catalog substitute verified against the household’s constraints."
            ) + note
        options = ", ".join(item.display_name for item in kept)
        if lang == "zh":
            if diets:
                return (
                    f"可考虑：{options}。这些选项已按食材目录中的过敏原、饮食来源和清真信息，"
                    f"核对了每位家庭成员的过敏原、饮食和忌口。{note}"
                )
            return f"可考虑：{options}。这些选项已按食材目录中的过敏原、忌口和清真信息筛选。"
        if diets:
            return (
                f"Possible options: {options}. These were checked against every member’s allergens, diet, and "
                f"exclusions using catalog allergen, dietary-origin, and halal data.{note}"
            )
        return f"Possible options: {options}. These were filtered using catalog allergen, exclusion, and halal data."

    @staticmethod
    def _unverified_diets(diets: list[tuple[str | None, str]], lang: str, *, others: bool) -> str:
        """The sentence naming whose diets some suggestions could not be verified for, or "" when none."""
        if not diets:
            return ""
        whose: dict[str | None, list[str]] = {}
        for who, diet in diets:
            whose.setdefault(who, []).append(word(diet, lang))
        if lang == "zh":
            named = listed([f"{who or '家庭'}的{listed(names, lang)}饮食" for who, names in whose.items()], lang)
            return f"{'其他' if others else '部分'}建议未列出，因为我无法核实它们是否符合{named}。"
        named = listed([f"{who or 'the household'}’s {listed(names, lang)} diet" for who, names in whose.items()], lang)
        return (
            f" {'Other' if others else 'Some'} suggestions were left out because I couldn’t verify they suit {named}."
        )

    @staticmethod
    def _unverified(lang: str) -> str:
        return (
            "我无法按目录和家庭限制核实这项替代建议，因此不会提供未经核验的选项。"
            if lang == "zh"
            else "I couldn't verify this substitution against the catalog and household constraints, "
            "so I won't suggest unverified options."
        )


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

        allergens = _confirmed_allergens(ingredient)
        if allergens is None and wanted_allergens:
            continue
        present, unverifiable = allergen_conflicts(wanted_allergens, allergens or [])
        if present or unverifiable:
            continue

        if requires_halal and getattr(ingredient, "halal_status", None) != "halal":
            continue
        display_name = str(getattr(ingredient, "display_name", ingredient_id))
        if requires_halal and needs_certification(ingredient_id):  # meat, sausage, gelatin ... (ADR-0108)
            display_name += " (only as a Halal-marked product)"

        safe.append(SafeSubstitute(ingredient_id=ingredient_id, display_name=display_name))
    return safe


def _confirmed_allergens(ingredient: object) -> list[str] | None:
    """The catalog's allergens for an ingredient; None (unknown) when it has none recorded or the release holds it
    with an allergen status other than confirmed."""
    release = food_groups().get(str(getattr(ingredient, "normalized_name", "")).casefold())
    if release is not None and release[3] != "confirmed":
        return None
    return getattr(ingredient, "allergens", None)


def suits_diet(ingredient: object, diet: str) -> bool | None:
    """Whether catalog facts show an ingredient suits one diet: True, False, or None when they cannot tell.

    The rules are the ones that tag release recipes (data-engineering/scripts/derive_dietary_tags.py), read on
    the release's `dietary_origin` and food group and the catalog's checked allergens:

    - vegetarian: not of `flesh` origin (dairy, eggs and honey are `secretion` and allowed);
    - vegan: of `plant` origin only;
    - dairy-free: not in the `dairy` food group and no dairy allergen;
    - gluten-free: no gluten allergen (the release's `gluten_candidate` is imported as gluten).

    An ingredient the release does not hold has no known origin or food group, and one without confirmed
    allergens has none known: unknown is never read as suiting a diet (ADR-0076). A diet with no rule here is
    unknown for every ingredient.
    """
    _, group, origin, _ = food_groups().get(str(getattr(ingredient, "normalized_name", "")).casefold(), (None,) * 4)
    allergens = _confirmed_allergens(ingredient)
    if diet == "vegetarian":
        return None if origin is None else origin != "flesh"
    if diet == "vegan":
        return None if origin is None else origin == "plant"
    if diet == "dairy-free":
        if group == "dairy" or (allergens is not None and {"dairy", "milk"} & set(allergens)):
            return False
        return None if group is None or allergens is None else True
    if diet == "gluten-free":
        return None if allergens is None else "gluten" not in allergens
    return None
