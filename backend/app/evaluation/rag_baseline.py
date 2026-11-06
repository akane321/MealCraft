"""The RAG baseline arm: retrieved catalog candidates in the prompt, the model plans (02-baselines.md section 1; #396).

"大模型 + 我们的数据": the model gets the same shared instructions as every arm (ADR-0092) plus its registered
source, a list of recipe candidates retrieved for this conversation from the frozen release v3 catalog with their
frozen-snapshot price estimates. It picks the dishes, portions and total itself: there is no planner, validator or
repair step of ours.

Retrieval: the user's strings so far (Chinese food words followed by their English, as the product does) are
embedded with the model the recipe vectors were made with (`data/recipes/embeddings-v1`), and the
`PER_GROUP` most similar priced recipes of each course group (breakfast, main, side or salad, soup) are listed,
each with its id, course, meal types, servings, minutes, allergens, diet tags, energy and protein per serving and
estimated cost per serving. Retrieval does not filter by the household's limits: that is the model's job here.

A dish naming a listed candidate in `recipe_reference` gets that recipe's ingredient lines, steps and time as
its evidence, scaled to the dish's servings, so the shared layers score what the catalog says the dish is. A dish
the model invents must carry its own lines in `evidence` or it cannot be scored.

Cost (ADR-0086): every chat call is checked against the arm's budget before it is made, at its worst case
(rendered input plus `MAX_OUTPUT_TOKENS`), reserved in the arm's ledger, and charged from the tokens the API
reports (`baseline_arms.LedgerBudget`). The embedding call is
charged at the chat model's input price, an overestimate, so the cap never fails open.
"""

from __future__ import annotations

import json
import re
from array import array
from collections.abc import Callable
from dataclasses import dataclass
from functools import lru_cache
from pathlib import Path
from typing import Any

from pydantic import ValidationError

from app.core.paths import repository_root
from app.evaluation import baseline_arms
from app.evaluation.baseline_resources import RELEASE
from app.evaluation.conversation_adapter import Exchange, Responder, UnifiedOutput
from app.evaluation.pure_llm_baseline import (
    API_ATTEMPTS,
    BACKOFF_SECONDS,
    MAX_ATTEMPTS,
    RETRIABLE,
    Usage,
    price_usd,
)
from app.evaluation.release_catalog import load_release_catalog
from app.planning.recipe_similarity import VECTORS, in_english

SYSTEM_ID = "rag"
# A week's confirmation turn hit 6,000 on a development episode (dev trial on #396), so owner, 2026-11-06: 12,000.
MAX_OUTPUT_TOKENS = 12000
PER_GROUP = 12
GROUPS = {
    "breakfast": ("breakfast", "baked_good"),
    "main": ("main",),
    "side or salad": ("side", "salad"),
    "soup": ("soup",),
}
CONFIGURATION = """Your registered configuration: retrieval from a recipe catalog. Below are candidate recipes
retrieved for this conversation, with estimated grocery cost per serving in Singapore dollars from a frozen
supermarket price snapshot. They were retrieved by similarity only and are not filtered by the household's limits:
check allergens, diet, time and budget yourself.
For a dish taken from the list, put its id in recipe_reference and set servings; its ingredients and steps are
taken from the catalog, so leave evidence empty. For any other dish, give evidence.ingredients as a list of
{"name": ..., "quantity_g": ...}, evidence.steps and evidence.cooking_time_minutes.
Give total_cost_sgd as your estimate of the groceries for the whole plan.

CANDIDATES (id | title | course | meal types | serves | minutes | allergens | diet | kcal, protein g per serving |
S$ per serving):
{candidates}"""

Embed = Callable[[list[str]], list[list[float]]]


@dataclass(frozen=True)
class Catalog:
    recipes: dict[str, dict]
    per_gram: dict[str, float]
    steps: dict[str, list[str]]
    allergens: dict[str, tuple[str, ...]]
    vectors: dict[str, array]


@lru_cache(maxsize=1)
def catalog(root: Path | None = None) -> Catalog:
    root = root or repository_root()
    release = load_release_catalog(root, RELEASE)
    per_gram: dict[str, float] = {}
    for product in release.products:
        if product["package_size"] > 0:
            price = product["price_sgd"] / product["package_size"]
            per_gram[product["ingredient_id"]] = min(price, per_gram.get(product["ingredient_id"], price))
    steps, allergens = {}, {}
    for line in (root / RELEASE / "recipes.jsonl").read_text(encoding="utf-8").splitlines():
        record = json.loads(line)
        steps[record["recipe_id"]] = [str(s) for s in record.get("instructions") or [] if str(s).strip()]
        allergens[record["recipe_id"]] = tuple(record.get("allergens") or ())
    base = root / VECTORS
    meta = json.loads(base.with_suffix(".json").read_text(encoding="utf-8"))
    rows = base.with_suffix(".bin").read_bytes()
    size = meta["dimensions"]
    recipes = {row["slug"]: row for row in release.recipes}
    vectors = {}
    for i, key in enumerate(meta["keys"]):
        if key in recipes:
            vectors[key] = array("b", rows[i * size : (i + 1) * size])
    return Catalog(recipes, per_gram, steps, allergens, vectors)


def cost_per_serving(recipe: dict, per_gram: dict[str, float]) -> float:
    total = sum(line["quantity"] * per_gram.get(line["ingredient"], 0.0) for line in recipe["ingredients"])
    return total / recipe["servings"]


def query_text(turns: list[str]) -> str:
    return in_english(" ".join(turns))


def retrieve(query: list[float], data: Catalog, per_group: int = PER_GROUP) -> list[str]:
    """The most similar recipes of each course group, best first, ids only; ties by id."""
    norm = sum(x * x for x in query) ** 0.5 or 1.0
    scored = []
    for key, row in data.vectors.items():
        dot = sum(q * b for q, b in zip(query, row, strict=True))
        scored.append((dot / (norm * (sum(b * b for b in row) ** 0.5 or 1.0)), key))
    scored.sort(key=lambda item: (-item[0], item[1]))
    chosen: list[str] = []
    for courses in GROUPS.values():
        chosen += [key for _, key in scored if data.recipes[key]["course"] in courses][:per_group]
    return chosen


def render_candidates(keys: list[str], data: Catalog) -> str:
    lines = []
    for key in keys:
        recipe = data.recipes[key]
        nutrients = recipe["nutrients"]
        lines.append(
            " | ".join(
                [
                    key,
                    recipe["title"],
                    recipe["course"],
                    ",".join(recipe["meal_types"]),
                    str(recipe["servings"]),
                    str(recipe["prep_time_minutes"] + recipe["cook_time_minutes"]),
                    ",".join(data.allergens.get(key, ())) or "none",
                    ",".join(recipe["dietary_tags"]) or "-",
                    f"{nutrients['calories_kcal']:.0f}, {nutrients['protein_g']:.0f}",
                    f"{cost_per_serving(recipe, data.per_gram):.2f}",
                ]
            )
        )
    return "\n".join(lines)


def system_prompt(instructions: str, candidates: str) -> str:
    return instructions + "\n\n" + CONFIGURATION.replace("{candidates}", candidates)


def messages_for(system: str, own_history: tuple[Exchange, ...], message: str) -> list[tuple[str, str]]:
    messages = [("system", system)]
    for item in own_history:
        messages.append(("human", item.message))
        messages.append(("ai", item.output.model_dump_json(exclude_defaults=True)))
    messages.append(("human", message))
    return messages


def estimate_tokens(messages: list[tuple[str, str]]) -> int:
    """About four characters a token; it only sizes the look-ahead, and the caps count reported tokens."""
    return sum(len(text) for _, text in messages) // 4 + 1


def fill_evidence(output: UnifiedOutput, data: Catalog, names: dict[str, str]) -> UnifiedOutput:
    """A dish naming a catalog recipe gets the recipe's own lines, scaled to the dish's servings."""
    if output.plan is None:
        return output
    payload = output.model_dump(mode="json")
    people = output.plan.household_size or 1
    for meal in payload["plan"]["meals"]:
        for dish in meal["dishes"]:
            recipe = data.recipes.get(dish.get("recipe_reference") or "")
            if recipe is None or (dish.get("evidence") or {}).get("ingredients"):
                continue
            servings = dish.get("servings") or people
            scale = servings / recipe["servings"]
            dish["servings"] = servings
            dish["evidence"] = {
                "ingredients": [
                    {"name": names.get(line["ingredient"], line["ingredient"]), "quantity_g": grams}
                    for line in recipe["ingredients"]
                    if (grams := round(line["quantity"] * scale, 1)) > 0
                ],
                "steps": data.steps.get(recipe["slug"]) or [recipe["title"]],
                "cooking_time_minutes": recipe["prep_time_minutes"] + recipe["cook_time_minutes"],
                "source": "catalog",
            }
    return UnifiedOutput.model_validate(payload)


def parse_output(content: Any) -> UnifiedOutput:
    text = content if isinstance(content, str) else json.dumps(content)
    text = re.sub(r"^```(?:json)?\s*|\s*```$", "", text.strip())
    return UnifiedOutput.model_validate_json(text)


def _usage(raw: Any, input_estimate: int) -> Usage:
    metadata = getattr(raw, "usage_metadata", None) or {}
    usage = Usage(int(metadata.get("input_tokens") or 0), int(metadata.get("output_tokens") or 0))
    return usage if usage.total_tokens else Usage(input_estimate, MAX_OUTPUT_TOKENS)


def call_model(
    model: Any, messages: list[tuple[str, str]], budget: baseline_arms.LedgerBudget, sleep, trace: list | None = None
) -> UnifiedOutput:
    """One answer: a malformed one is asked again once, a transient API error retried with backoff."""
    estimate = estimate_tokens(messages)
    errors: list[str] = []
    for _ in range(MAX_ATTEMPTS):
        raw = None
        for api_try in range(API_ATTEMPTS):
            try:  # every attempt is reserved, and settled if it raises (ADR-0086, the arm's ledger)
                raw = budget.paid(lambda: model.invoke(messages), estimate, MAX_OUTPUT_TOKENS)
                break
            except RETRIABLE as error:
                errors.append(f"{type(error).__name__}: {error}")
                if api_try + 1 < API_ATTEMPTS:
                    sleep(BACKOFF_SECONDS[min(api_try, len(BACKOFF_SECONDS) - 1)])
        if raw is None:
            raise RuntimeError("; ".join(errors) or "no answer")
        usage = _usage(raw, estimate)
        budget.charge(usage, call="chat")
        if trace is not None:
            trace.append({"tool": "chat", "input_tokens": usage.input_tokens, "output_tokens": usage.output_tokens})
        try:
            return parse_output(raw.content)
        except (ValidationError, ValueError) as error:
            errors.append(f"malformed: {error}")
    raise ValueError("; ".join(errors))


def make_responder(context: baseline_arms.ArmContext, *, embed: Embed | None = None, sleep=None) -> Responder:
    import time

    data = catalog()
    model, budget = context.model, context.budget
    if model is None or budget is None:
        raise RuntimeError("the RAG arm needs a model and a budget (a live run)")
    embed = embed or model.embed
    sleep = sleep or time.sleep
    names = context.resources.names

    def respond(message: str, own_history: tuple[Exchange, ...], instructions: str) -> UnifiedOutput:
        turns = [item.message for item in own_history if not item.automatic_confirmation] + [message]
        text = query_text(turns)
        tokens = len(text) // 4 + 1
        (query,) = budget.paid(lambda: embed([text]), tokens, 0)
        budget.charge(Usage(tokens, 0), call="embedding")
        keys = retrieve(query, data)
        if context.trace is not None:
            context.trace.append({"tool": "retrieval", "query": text, "candidates": keys})
        system = system_prompt(instructions, render_candidates(keys, data))
        output = call_model(model, messages_for(system, own_history, message), budget, sleep, context.trace)
        return fill_evidence(output, data, names)

    return respond


def estimate(turns: list[str], instructions: str, model: str) -> tuple[int, int, float]:
    """Worst case of one case without the network: every turn answered and confirmed, each call retried once.

    The candidate list is sized by the longest rendering of `PER_GROUP` recipes per group, and each later call
    carries the earlier exchanges at their worst-case output size."""
    data = catalog()
    longest = sorted(data.recipes, key=lambda key: -len(render_candidates([key], data)))
    candidates = render_candidates(longest[: PER_GROUP * len(GROUPS)], data)
    base = estimate_tokens([("system", system_prompt(instructions, candidates))])
    calls = tokens = history = 0
    usd = price_usd(model, Usage(len(" ".join(turns)) // 4 + 1, 0)) * len(turns)  # the retrieval embeddings
    for turn in turns:
        for _ in range(2):  # the turn and its possible confirmation
            input_tokens = base + history + len(turn) // 4 + 1
            calls += MAX_ATTEMPTS
            tokens += MAX_ATTEMPTS * input_tokens
            usd += MAX_ATTEMPTS * price_usd(model, Usage(input_tokens, MAX_OUTPUT_TOKENS))
            history += MAX_OUTPUT_TOKENS + len(turn) // 4 + 1
    return calls, tokens, usd


class LiveModel:
    """The product's mini model in JSON mode, with the recipe vectors' embedding model for retrieval."""

    def __init__(self, model_name: str):
        from langchain_openai import ChatOpenAI

        from app.agent import model_client
        from app.core.config import get_settings
        from app.planning.recipe_similarity import catalog_embedder

        settings = get_settings()
        if settings.openai_api_key is None:
            raise RuntimeError("a live run needs OPENAI_API_KEY at run time (tests inject a fake model)")
        key = settings.openai_api_key.get_secret_value()
        self.chat = ChatOpenAI(
            api_key=key,
            model=model_name,
            temperature=0,
            max_tokens=MAX_OUTPUT_TOKENS,
            timeout=settings.openai_timeout_seconds,
            max_retries=0,
            http_client=model_client.http_client(),
            model_kwargs={"response_format": {"type": "json_object"}},
        )
        embedder = catalog_embedder(key)
        if embedder is None:
            raise RuntimeError("the recipe vectors are missing")
        self.embed = embedder

    def invoke(self, messages):
        return self.chat.invoke(messages)


def fingerprint() -> dict[str, str]:
    return {
        "system_id": SYSTEM_ID,
        "configuration_sha256": baseline_arms.sha256_text(CONFIGURATION),
        "runner_sha256": baseline_arms.source_sha256(__file__),
    }


ARM = baseline_arms.Arm(
    system_id=SYSTEM_ID,
    paid=True,
    fingerprint=fingerprint,
    responder=make_responder,
    estimate=estimate,
    model_factory=LiveModel,
    max_usd=8.0,  # owner, 2026-11-06 (ADR-0120): two dev trials put the 280 questions near US$5
)
