"""The live-model arms of protocol v2-multidish: A, B and D.

A and B read the request with a live model and then plan with the meal beam (A)
or CP-SAT (B); D reads the request and writes the plan itself, from the same
context. The extraction schema here extends the product parser's, which has no
field for a clarifying question or a repetition request, and the protocol scores
both. One call per episode serves A and B, so the two differ only in who solves.

Every call is counted; the run stops if it passes the token cap the owner set.
"""

from __future__ import annotations

import json
import os
import time
from dataclasses import dataclass, field

from langchain_openai import ChatOpenAI
from pydantic import BaseModel, Field

from app.data.allergens import checked_allergens
from app.planning.meal_composition import MAIN_ROLE

DIETARY_TAGS = ("vegetarian", "vegan", "dairy-free", "gluten-free")

CLARIFIABLE = ("household_size", "budget_sgd", "allergens", "excluded_ingredients", "planning_horizon")


class LiveRecipeCount(BaseModel):
    recipe_id: str
    min_uses: int = 0
    max_uses: int | None = None


class LiveIngredientMeals(BaseModel):
    ingredient_id: str
    min_meals: int = 1


class LiveRepetition(BaseModel):
    max_uses_per_recipe: int | None = None
    recipe_counts: list[LiveRecipeCount] = Field(default_factory=list)
    ingredient_meals: list[LiveIngredientMeals] = Field(default_factory=list)
    repeat_ok_roles: list[str] = Field(default_factory=list)


class LiveDish(BaseModel):
    slot_id: str
    role_id: str | None = None
    recipe_id: str


class LiveAnswer(BaseModel):
    """What the model understood, and -- for arm D only -- the plan it wrote."""

    household_size: int | None = None
    allergens: list[str] = Field(default_factory=list)
    excluded_ingredients: list[str] = Field(default_factory=list)
    dietary_tags: list[str] = Field(default_factory=list)
    max_cooking_time_minutes: int | None = None
    budget_sgd: float | None = None
    repetition: LiveRepetition | None = None
    clarification_fields: list[str] = Field(default_factory=list)
    conflict: str | None = None
    dishes: list[LiveDish] = Field(default_factory=list)


@dataclass
class LiveModel:
    """One model, one token budget, shared by every live arm in a run."""

    model: str
    max_tokens: int
    used_tokens: int = 0
    calls: int = 0
    # The answer and what the call cost in wall-clock seconds, so an arm served from
    # the cache still reports the model time its answer took (protocol section 11).
    cache: dict[tuple[str, str], tuple[LiveAnswer, float]] = field(default_factory=dict)
    last_seconds: float = 0.0
    _client: object | None = None

    @classmethod
    def from_environment(cls, max_tokens: int) -> LiveModel:
        key = os.environ.get("OPENAI_API_KEY")
        if not key:
            raise RuntimeError("the live arms need OPENAI_API_KEY; load the owner's .env before running them")
        model = os.environ.get("OPENAI_MODEL") or "gpt-5.4-mini"
        live = cls(model=model, max_tokens=max_tokens)
        live._client = ChatOpenAI(api_key=key, model=model, temperature=0).with_structured_output(
            LiveAnswer, method="json_schema", include_raw=True
        )
        return live

    def ask(self, prompt: str, *, cache_key: tuple[str, str] | None = None) -> LiveAnswer:
        if cache_key is not None and cache_key in self.cache:
            answer, self.last_seconds = self.cache[cache_key]
            return answer
        if self.used_tokens >= self.max_tokens:
            raise RuntimeError(f"live token cap reached: {self.used_tokens} of {self.max_tokens}")
        started = time.perf_counter()
        raw = self._client.invoke(prompt)  # type: ignore[union-attr]
        self.last_seconds = time.perf_counter() - started
        answer = raw["parsed"] if isinstance(raw, dict) else raw
        usage = getattr(raw.get("raw") if isinstance(raw, dict) else raw, "usage_metadata", None) or {}
        self.used_tokens += int(usage.get("total_tokens") or 0)
        self.calls += 1
        if answer is None:  # the model returned something the schema refused
            answer = LiveAnswer(clarification_fields=[], conflict="the model returned no usable answer")
        if cache_key is not None:
            self.cache[cache_key] = (answer, self.last_seconds)
        return answer


def _pool(episode: dict, catalog) -> list[dict]:
    return [catalog.by_slug[slug] for slug in episode["scenario"]["recipe_candidate_slugs"]]


def _menu(episode: dict, catalog) -> str:
    """The pool as the model sees it: enough to name a dish, an id and its ingredients."""
    lines = []
    for recipe in _pool(episode, catalog):
        ingredients = ", ".join(sorted({line["ingredient"] for line in recipe["ingredients"]}))
        lines.append(
            f"{recipe['slug']} | {recipe['course']} | {recipe['title'][:80]} | "
            f"{recipe['prep_time_minutes'] + recipe['cook_time_minutes']} min | serves {recipe['servings']} | "
            f"{ingredients}"
        )
    return "\n".join(lines)


def _vocabulary(episode: dict, catalog) -> str:
    """The words a constraint may be written in.

    The model was naming constraints in its own words -- `cooking wine` for
    `wine_cooking`, a religion for a dietary tag -- and the planner then filtered
    on nothing (findings, held-out run 3). Only these ids mean anything.
    """
    ingredients = sorted({line["ingredient"] for recipe in _pool(episode, catalog) for line in recipe["ingredients"]})
    roles = [role["role_id"] for role in episode["scenario"]["household_profile"].get("meal_composition") or []]
    return f"""Allowed words. A constraint written in any other word matches nothing and is lost.
- excluded_ingredients: only these ids, and every id that is the thing the household named
  (told "no wine", exclude each wine id below):
{", ".join(ingredients)}
- allergens: only {", ".join(sorted(checked_allergens()))}
- dietary_tags: only {", ".join(DIETARY_TAGS)}
- repeat_ok_roles: only {", ".join(roles) or "(this household states no roles)"}
- ingredient_meals and recipe_counts: an ingredient id from the list above, a recipe id from the
  candidates below."""


def _context(episode: dict, catalog) -> str:
    scenario = episode["scenario"]
    profile = scenario["household_profile"]
    history = "\n".join(f"{m['role']}: {m['content']}" for m in scenario.get("conversation_history") or [])
    return f"""Household profile (already known, never ask about it again):
{json.dumps(profile, ensure_ascii=False)}
Pantry: {json.dumps(scenario["pantry"], ensure_ascii=False)}
Week to plan: {json.dumps(scenario["planning_horizon"], ensure_ascii=False)}
Earlier conversation:
{history or "(none)"}
Latest request: {scenario["user_request"]}

{_vocabulary(episode, catalog)}

Candidate dishes (id | course | title | total minutes | servings | ingredients):
{_menu(episode, catalog)}"""


UNDERSTAND = """You read a household's request for a week of dinners and state what it asks for.

Return only what the household stated or the profile already carries, in the allowed words
below. Rules:
- Repeat back allergens and excluded ingredients from the profile and the request.
- An allergy is an allergen, never a list of ingredients: a dairy allergy is `dairy` and nothing
  more. Do not add ingredients, tags or limits the household did not state -- an invented
  constraint can leave a week that has an answer with none.
- A religion, a cuisine or a habit is not a dietary tag. Write what it forbids as excluded
  ingredients instead.
- excluded_ingredients is what the household refuses to eat. Wanting to finish something up
  ("use up the mushrooms") is the opposite: that is an ingredient_meals entry, never an
  exclusion.
- budget_sgd is the whole week's grocery budget, in Singapore dollars, only if one is stated.
- max_cooking_time_minutes is a per-meal limit, only if one is stated.
- repetition: fill it only when the household said something about repeating -- "don't eat the
  same thing twice" is max_uses_per_recipe=1; "I want that dish twice" is a recipe_counts entry
  with the candidate's id; "use up the tofu" is an ingredient_meals entry; "soup can repeat" is
  repeat_ok_roles.
- clarification_fields: name a field from {fields} ONLY when you cannot plan without it and
  neither the profile nor the request gives it. A household that points at a limit without giving
  its number ("our usual budget", "keep it to the normal time") has not given it: put that field
  in clarification_fields and plan nothing. Do not treat it as "no limit".
  Asking about something you were already told is an error.
- conflict: one sentence if the request cannot be met as stated, otherwise null.
- Leave `dishes` empty.

{context}"""


PLAN = """You read a household's request and write the week's dinners yourself, choosing from the
candidate dishes below. Nothing else will choose for you.

State what you understood, in the allowed words below and adding nothing the household did not
state, and then fill `dishes`: one entry per dish,
with the slot_id from the week, the role_id from the household's meal_composition (use null only
when the profile states no composition), and the recipe_id of a candidate. Fill every required
role of every slot. Respect what the household asked: allergens, excluded ingredients, diet, the
per-meal time limit, the weekly grocery budget (whole packages are bought, so overshoot costs
money), and anything said about repeating.

If the request cannot be met, leave `dishes` empty and give the conflict. If you cannot plan
without an answer, leave `dishes` empty and name the clarification fields from {fields}.

{context}"""


def understand(episode: dict, catalog, live: LiveModel) -> LiveAnswer:
    """Arm A and B share this call: the same understanding, two solvers."""
    prompt = UNDERSTAND.format(fields=", ".join(CLARIFIABLE), context=_context(episode, catalog))
    return live.ask(prompt, cache_key=("understand", episode["episode_id"]))


def plan_directly(episode: dict, catalog, live: LiveModel) -> LiveAnswer:
    prompt = PLAN.format(fields=", ".join(CLARIFIABLE), context=_context(episode, catalog))
    return live.ask(prompt, cache_key=("plan", episode["episode_id"]))


def dishes_in_problem(answer: LiveAnswer, problem) -> list:
    """The model's dishes, keeping only slots, roles and recipes that exist."""
    from app.schemas.planning_v2 import PlanningAssignment

    slots = {slot.slot_id: slot for slot in problem.slots}
    recipes = {recipe.recipe_id for recipe in problem.recipes}
    kept, seen = [], set()
    for dish in answer.dishes:
        slot = slots.get(dish.slot_id)
        if slot is None or dish.recipe_id not in recipes:
            continue
        roles = {role.role_id for role in slot.composition or []}
        if roles and dish.role_id not in roles:
            continue
        role = dish.role_id if roles else None
        if (dish.slot_id, dish.role_id or MAIN_ROLE) in seen:
            continue
        seen.add((dish.slot_id, dish.role_id or MAIN_ROLE))
        kept.append(PlanningAssignment(slot_id=dish.slot_id, role_id=role, recipe_id=dish.recipe_id))
    return kept
