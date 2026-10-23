"""Run the pure-LLM, single-turn Sprint 2 baseline (02-baselines.md sections 1 and 3).

The model sees household and task facts only: no MealCraft recipe catalog, grocery snapshot, retrieval result,
calculator, web search or tool. Its structured answer (`BaselineAnswer`) is scored by the shared layers: mapping
(`baseline_mapping`), per-dish coverage (`baseline_verification`), recomputation (`baseline_recomputation`) and
the product's own validator (`baseline_validation`).

Cost and safety rules (ADR-0020 section 4; ADR-0086, the US$5 cap on paid baseline runs):

- The default is a dry run: it renders every prompt, counts the calls and estimates tokens and the worst-case
  cost. Nothing touches the network. `--live` is required for a paid call.
- `--max-usd` (default 5.0) and `--max-tokens` stop the run before a call that could pass either cap. Spend is
  priced from the token counts with `PRICES` (a call that reports no usage is charged its worst case), recorded
  per call and summed across resumed runs into the same output. The cap holds per output file only: the US$5 is
  one total, so each live run's `--max-usd` is set to what the earlier outputs left.
- Held-out paths are refused unless `--allow-heldout` is given, and the flag is recorded.
- Every finished episode is appended to the JSONL output at once, scored or not; a rerun skips what is already
  answered, and an episode whose call failed is tried again. A rerun into an output written by another model or
  fingerprint is refused, so two arms never mix in one file.

    python -m app.evaluation.pure_llm_baseline --episodes data/evaluation/dev/v2-multidish/episodes \\
        --output docs/evaluation/baselines/dev/pure-llm.jsonl            # dry run
    python -m app.evaluation.pure_llm_baseline --fingerprint            # the freeze fingerprint
"""

from __future__ import annotations

import argparse
import hashlib
import json
import statistics
import sys
import time
from collections.abc import Callable
from dataclasses import asdict, dataclass, field
from datetime import UTC, datetime
from pathlib import Path
from typing import Any, Protocol

import openai
from pydantic import BaseModel, ValidationError

from app.core.paths import repository_root
from app.data.recipe_tags import INPUT_USD_PER_M, OUTPUT_USD_PER_M
from app.evaluation.baseline_mapping import map_response_ingredients
from app.evaluation.baseline_output import BaselineAnswer, BaselineResponse
from app.evaluation.baseline_recomputation import allergen_safety, recompute_ingredient_baseline
from app.evaluation.baseline_resources import BaselineResources, load_resources
from app.evaluation.baseline_validation import validate_baseline_plan
from app.evaluation.baseline_verification import verify_coverage

SYSTEM_ID = "pure-llm-single-turn"
MAX_ATTEMPTS = 2  # one malformed answer is retried once (section 3.1 item 1)
API_ATTEMPTS = 3  # a rate limit, timeout or server error is retried with backoff
BACKOFF_SECONDS = (2.0, 8.0)
MAX_OUTPUT_TOKENS = 8000  # bounds each call's worst case for the caps
DEFAULT_MAX_USD = 5.0  # the US$5 cap on paid baseline runs, held as one shared total (ADR-0086)
DEFAULT_MAX_TOKENS = 3_000_000
# USD per million (input, output) tokens: the upper estimate the recipe-tag run uses for the same model.
PRICES = {"gpt-5.4-mini": (INPUT_USD_PER_M, OUTPUT_USD_PER_M)}
RETRIABLE = (openai.RateLimitError, openai.APITimeoutError, openai.APIConnectionError, openai.InternalServerError)

SYSTEM_PROMPT = """You plan meals for one household in a single response. You have no tools, web search,
calculator, recipe database, grocery database or retrieval system. Use only the household and task facts
the user gives you.

Answer in the supplied JSON schema and add no other field.
- status "plan": fill `plan`. Give every meal of the task with its slot_id, and in a meal of several dishes
  each dish's role_id from the household's meal_composition. For every dish give its servings, its
  cooking time in minutes, its steps, and every ingredient in grams. Give the total grocery cost in
  Singapore dollars if you can estimate it, whether it is within the budget, and a constraint claim for
  each limit the household stated (allergens, excluded ingredients, diet, time, budget).
- status "clarification": only when a missing fact prevents a responsible plan; name each missing field.
- status "infeasible": when the request cannot be met as stated; give the conflict and the relaxations
  the household could choose. Never offer to relax an allergen."""

USER_TEMPLATE = """HOUSEHOLD_AND_TASK_INPUT:
{task_input}"""

TASK_KEYS = (
    "user_request",
    "conversation_history",
    "household_profile",
    "pantry",
    "planning_horizon",
    "locked_or_completed_meals",
)


class StructuredModel(Protocol):
    def invoke(self, messages: list[tuple[str, str]]) -> Any: ...


@dataclass(frozen=True)
class Usage:
    input_tokens: int = 0
    output_tokens: int = 0

    @property
    def total_tokens(self) -> int:
        return self.input_tokens + self.output_tokens

    def __add__(self, other: Usage) -> Usage:
        return Usage(self.input_tokens + other.input_tokens, self.output_tokens + other.output_tokens)


def price_usd(model: str, usage: Usage) -> float:
    per_input, per_output = PRICES[model]
    return (usage.input_tokens * per_input + usage.output_tokens * per_output) / 1_000_000


@dataclass
class Budget:
    """One run's caps, with what earlier runs into the same output already spent."""

    model: str
    max_usd: float
    max_tokens: int
    spent_usd: float = 0.0
    used_tokens: int = 0
    calls: int = 0
    stop_reason: str | None = None

    def worst_case(self, input_tokens: int) -> tuple[int, float]:
        usage = Usage(input_tokens, MAX_OUTPUT_TOKENS)
        return usage.total_tokens, price_usd(self.model, usage)

    def allows(self, input_tokens: int) -> bool:
        tokens, usd = self.worst_case(input_tokens)
        if self.spent_usd + usd > self.max_usd:
            self.stop_reason = f"spend cap: US${self.spent_usd:.4f} spent, next call could cost US${usd:.4f}"
        elif self.used_tokens + tokens > self.max_tokens:
            self.stop_reason = f"token cap: {self.used_tokens} used, next call could use {tokens}"
        return self.stop_reason is None

    def record(self, usage: Usage) -> float:
        cost = price_usd(self.model, usage)
        self.spent_usd += cost
        self.used_tokens += usage.total_tokens
        self.calls += 1
        return cost


class BudgetExhausted(Exception):
    pass


@dataclass
class Generation:
    response: BaselineResponse | None = None
    attempts: int = 0
    usage: Usage = field(default_factory=Usage)
    cost_usd: float = 0.0
    elapsed_seconds: float = 0.0
    parse_errors: list[str] = field(default_factory=list)
    api_errors: list[str] = field(default_factory=list)

    @property
    def call_failed(self) -> bool:
        return self.response is None and not self.parse_errors and bool(self.api_errors)


def episode_id_of(episode: dict[str, Any]) -> str:
    episode_id = str(episode.get("episode_id") or episode.get("scenario_id") or episode.get("id") or "")
    if not episode_id:
        raise ValueError("episode has no episode_id, scenario_id or id")
    return episode_id


def household_task_input(episode: dict[str, Any]) -> dict[str, Any]:
    """Only facts a household would give a planner: never the gold, the drawn pool or its products."""
    scenario = episode.get("scenario", episode)
    return {key: scenario[key] for key in TASK_KEYS if key in scenario}


def render_messages(episode: dict[str, Any]) -> list[tuple[str, str]]:
    task = json.dumps(household_task_input(episode), ensure_ascii=False, sort_keys=True)
    return [("system", SYSTEM_PROMPT), ("human", USER_TEMPLATE.format(task_input=task))]


def _sha256(text: str | bytes) -> str:
    return hashlib.sha256(text.encode("utf-8") if isinstance(text, str) else text).hexdigest()


def output_schema() -> dict:
    return BaselineAnswer.model_json_schema()


def freeze_fingerprint() -> dict[str, str]:
    """What a freeze record pins: the prompt templates, the answer schema and this runner's source."""
    return {
        "system_id": SYSTEM_ID,
        "prompt_sha256": _sha256(SYSTEM_PROMPT + "\n\n" + USER_TEMPLATE),
        "output_schema_sha256": _sha256(json.dumps(output_schema(), sort_keys=True, separators=(",", ":"))),
        # Line endings normalised, so a Windows checkout and CI agree.
        "runner_sha256": _sha256(Path(__file__).read_bytes().replace(b"\r\n", b"\n")),
    }


def estimate_tokens(messages: list[tuple[str, str]]) -> int:
    """About four characters a token, with the schema the structured call sends.

    ponytail: a character estimate, not a tokenizer; it only sizes the dry run and the cap's look-ahead, and
    the caps then count the tokens the API reports.
    """
    characters = sum(len(text) for _, text in messages) + len(json.dumps(output_schema()))
    return characters // 4 + 1


def create_model(model_name: str) -> StructuredModel:
    """The product's mini model and shared HTTP client, deterministic, strict JSON schema, no hidden retries."""
    from langchain_openai import ChatOpenAI

    from app.agent import model_client
    from app.core.config import get_settings

    settings = get_settings()
    if settings.openai_api_key is None:
        raise RuntimeError("a live run needs OPENAI_API_KEY at run time (tests inject a fake model)")
    return ChatOpenAI(
        api_key=settings.openai_api_key.get_secret_value(),
        model=model_name,
        temperature=0,
        max_tokens=MAX_OUTPUT_TOKENS,
        timeout=settings.openai_timeout_seconds,
        max_retries=0,
        http_client=model_client.http_client(),
    ).with_structured_output(BaselineAnswer, method="json_schema", strict=True, include_raw=True)


def _usage(raw: Any, input_estimate: int) -> Usage:
    """The tokens the API reports; when it reports none, the call's worst case, so the caps never fail open."""
    metadata = getattr(raw, "usage_metadata", None) or {}
    usage = Usage(int(metadata.get("input_tokens") or 0), int(metadata.get("output_tokens") or 0))
    return usage if usage.total_tokens else Usage(input_estimate, MAX_OUTPUT_TOKENS)


def generate(
    episode: dict[str, Any],
    model: StructuredModel,
    budget: Budget,
    *,
    sleep: Callable[[float], None] = time.sleep,
) -> Generation:
    """Ask once, retry one malformed answer once and a transient API error with backoff; never repair."""
    episode_id = episode_id_of(episode)
    messages = render_messages(episode)
    estimate = estimate_tokens(messages)
    result = Generation()
    started = time.perf_counter()
    try:
        while result.attempts < MAX_ATTEMPTS:
            result.attempts += 1
            raw_result = None
            for api_try in range(API_ATTEMPTS):
                if not budget.allows(estimate):
                    if result.cost_usd:  # a paid, malformed answer stays recorded; its retry is not afforded
                        result.parse_errors.append(f"retry not made: {budget.stop_reason}")
                        return result
                    raise BudgetExhausted(budget.stop_reason)
                try:
                    raw_result = model.invoke(messages)
                    break
                except RETRIABLE as error:
                    result.api_errors.append(f"{type(error).__name__}: {error}")
                    if api_try + 1 < API_ATTEMPTS:
                        sleep(BACKOFF_SECONDS[min(api_try, len(BACKOFF_SECONDS) - 1)])
                except openai.APIError as error:
                    result.api_errors.append(f"{type(error).__name__}: {error}")
                    return result
            if raw_result is None:
                return result
            parsed, raw = (
                (raw_result.get("parsed"), raw_result.get("raw"))
                if isinstance(raw_result, dict)
                else (raw_result, raw_result)
            )
            usage = _usage(raw, estimate)
            result.usage += usage
            result.cost_usd += budget.record(usage)
            try:
                if parsed is None:
                    error = raw_result.get("parsing_error") if isinstance(raw_result, dict) else None
                    raise ValueError(f"structured output was malformed: {error or 'no parsed answer'}")
                answer = parsed if isinstance(parsed, BaseModel) else BaselineAnswer.model_validate(parsed)
                # The harness fills the ids: a model never pays for a retry because it miscopied one.
                result.response = BaselineResponse.model_validate(
                    {**answer.model_dump(), "episode_id": episode_id, "system_id": SYSTEM_ID}
                )
                return result
            except (ValidationError, ValueError, TypeError) as error:
                result.parse_errors.append(str(error))
        return result
    finally:
        result.elapsed_seconds = time.perf_counter() - started


def score(episode: dict[str, Any], response: BaselineResponse, resources: BaselineResources) -> dict[str, Any]:
    """Every scoring layer on one answer. A clarification or infeasible answer has no plan to score."""
    if response.plan is None:
        return {}
    coverage = map_response_ingredients(
        response, names=resources.names, aliases=resources.aliases, matcher=resources.matcher, parents=resources.parents
    )
    verification = verify_coverage(coverage)
    scenario = episode.get("scenario", episode)
    household = scenario.get("household_profile") or {}
    recomputation = recompute_ingredient_baseline(
        coverage,
        ingredient_facts=resources.ingredient_facts,
        frozen_products=resources.frozen_products,
        not_purchased=resources.not_bought(household),
    )
    requested = (episode.get("gold") or {}).get("applicable_hard_constraints", {}).get("allergens_absent")
    safe, reasons = allergen_safety(
        recomputation, household.get("allergens", []) if requested is None else requested, resources.checked_allergens
    )
    scored: dict[str, Any] = {
        "dishes": [
            {
                "slot_id": dish.slot_id,
                "role_id": dish.role_id,
                "name": dish.name,
                "coverage": dish.coverage,
                "mappings": [asdict(item) for item in dish.mappings],
            }
            for dish in coverage.dishes
        ],
        "verification": {
            "gram_coverage": verification.gram_coverage,
            "verifiable_dish_share": verification.verifiable_dish_share,
            "all_dishes_verifiable": verification.all_dishes_verifiable,
            "needs_review_count": verification.needs_review_count,
            "unmatched_count": verification.unmatched_count,
        },
        "recomputation": asdict(recomputation),
        "allergen_safe": safe,
        "allergen_reasons": reasons,
    }
    try:
        validation = validate_baseline_plan(
            episode,
            coverage,
            ingredient_facts=resources.ingredient_facts,
            frozen_products=resources.frozen_products,
        )
    except KeyError as error:  # an episode without the multi-dish gold and packet cannot be validated
        scored["validation"] = {"skipped": f"episode lacks {error}"}
    except ValueError as error:  # no gold problem to judge a plan by (a clarification episode has no size)
        scored["validation"] = {"skipped": f"{type(error).__name__}: {error}"}
    else:
        scored["validation"] = {
            "strict_passed": validation.strict_passed,
            "adjusted_passed": validation.adjusted_passed,
            "unverified": validation.unverified,
            "report": validation.report,
        }
    return scored


def run_episode(
    episode: dict[str, Any],
    repeat: int,
    *,
    model: StructuredModel,
    budget: Budget,
    resources: BaselineResources,
    sleep: Callable[[float], None] = time.sleep,
) -> dict[str, Any]:
    generated = generate(episode, model, budget, sleep=sleep)
    response = generated.response
    scored: dict[str, Any] = {}
    if response is not None:
        try:
            scored = score(episode, response, resources)
        except Exception as error:  # a paid answer is kept and the run goes on; the record names the failure
            scored = {"error": f"{type(error).__name__}: {error}"}
    return {
        "episode_id": episode_id_of(episode),
        "repeat": repeat,
        "system_id": SYSTEM_ID,
        "model": budget.model,
        "fingerprint": freeze_fingerprint(),
        "category": episode.get("category"),
        "language": episode.get("language"),
        "status": "call_failed" if generated.call_failed else "answered",
        "valid_output": response is not None,
        "attempts": generated.attempts,
        "parse_errors": generated.parse_errors,
        "api_errors": generated.api_errors,
        "usage": {**asdict(generated.usage), "total_tokens": generated.usage.total_tokens},
        "cost_usd": generated.cost_usd,
        "elapsed_seconds": generated.elapsed_seconds,
        "prompt_sha256": _sha256(json.dumps(render_messages(episode), ensure_ascii=False)),
        "response": response.model_dump(mode="json") if response else None,
        "scored": scored,
    }


def load_episodes(path: Path) -> list[dict[str, Any]]:
    files = sorted(path.glob("*.json")) if path.is_dir() else [path]
    episodes: list[dict[str, Any]] = []
    for file in files:
        payload = json.loads(file.read_text(encoding="utf-8"))
        if isinstance(payload, list):
            episodes.extend(payload)
        elif isinstance(payload.get("episodes"), list):
            episodes.extend(payload["episodes"])
        else:
            episodes.append(payload)
    return episodes


def _digest(path: Path) -> str:
    files = sorted(path.glob("*.json")) if path.is_dir() else [path]
    digest = hashlib.sha256()
    for file in files:
        digest.update(file.name.encode("utf-8") + b"\0" + file.read_bytes())
    return digest.hexdigest()


def _json(value: Any) -> Any:
    if isinstance(value, BaseModel):
        return value.model_dump(mode="json")
    raise TypeError(f"not serialisable: {type(value).__name__}")


def read_records(path: Path) -> list[dict[str, Any]]:
    """The records, skipping a line a killed run left half written (its episode is then asked again)."""
    if not path.exists():
        return []
    records = []
    for line in path.read_text(encoding="utf-8").splitlines():
        try:
            records.append(json.loads(line))
        except json.JSONDecodeError:
            if line.strip():
                print(f"skipped an unreadable record line in {path}", file=sys.stderr)
    return records


def summarise(records: list[dict[str, Any]], repeats: int) -> dict[str, Any]:
    """Each repeat's rates, then their mean and spread (02-baselines.md section 2: several runs per arm)."""

    def rate(rows: list[dict], value: Callable[[dict], float | bool | None]) -> float | None:
        values = [float(v) for v in (value(row) for row in rows) if v is not None]
        return sum(values) / len(values) if values else None

    metrics: dict[str, Callable[[dict], float | bool | None]] = {
        "valid_output_rate": lambda row: row["valid_output"],
        "strict_pass_rate": lambda row: (row["scored"].get("validation") or {}).get("strict_passed"),
        "adjusted_pass_rate": lambda row: (row["scored"].get("validation") or {}).get("adjusted_passed"),
        "allergen_safe_rate": lambda row: row["scored"].get("allergen_safe"),
        "gram_coverage": lambda row: (row["scored"].get("verification") or {}).get("gram_coverage"),
        "verifiable_dish_share": lambda row: (row["scored"].get("verification") or {}).get("verifiable_dish_share"),
    }
    answered = [row for row in records if row["status"] == "answered"]
    per_repeat = []
    for repeat in range(repeats):
        rows = [row for row in answered if row["repeat"] == repeat]
        per_repeat.append({"repeat": repeat, "episodes": len(rows)} | {k: rate(rows, f) for k, f in metrics.items()})
    spread = {}
    for key in metrics:
        values = [row[key] for row in per_repeat if row[key] is not None]
        spread[key] = {
            "mean": statistics.fmean(values) if values else None,
            "stdev": statistics.pstdev(values) if len(values) > 1 else None,
        }
    return {"per_repeat": per_repeat, "across_repeats": spread}


def main(
    argv: list[str] | None = None,
    *,
    model_factory: Callable[[str], StructuredModel] = create_model,
    resource_loader: Callable[[], BaselineResources] = load_resources,
    sleep: Callable[[float], None] = time.sleep,
) -> int:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("--episodes", type=Path)
    parser.add_argument("--output", type=Path, help="JSONL of episode records; the report is written beside it")
    parser.add_argument("--live", action="store_true", help="make paid model calls (default: dry run)")
    parser.add_argument("--repeats", type=int, default=1)
    parser.add_argument("--max-usd", type=float, default=DEFAULT_MAX_USD)
    parser.add_argument("--max-tokens", type=int, default=DEFAULT_MAX_TOKENS)
    parser.add_argument("--model", default="gpt-5.4-mini")
    parser.add_argument("--allow-heldout", action="store_true")
    parser.add_argument("--fingerprint", action="store_true", help="print the freeze fingerprint and exit")
    args = parser.parse_args(argv)

    if args.fingerprint:
        print(json.dumps(freeze_fingerprint(), indent=2))
        return 0
    if args.episodes is None or args.output is None:
        parser.error("--episodes and --output are required")
    # Relative paths are read from the repository root, as the other evaluation runners read them.
    args.episodes, args.output = (
        path if path.is_absolute() else repository_root() / path for path in (args.episodes, args.output)
    )
    if args.repeats < 1:
        parser.error("--repeats must be at least 1")
    for path in (args.episodes, args.output):
        if "heldout" in "".join(ch for ch in str(path).lower() if ch.isalnum()) and not args.allow_heldout:
            parser.error(f"{path} is a held-out path; pass --allow-heldout only for the frozen run")
    if args.model not in PRICES:
        parser.error(f"no price for {args.model}; add it to PRICES before any run so the cap can hold")

    episodes = load_episodes(args.episodes)
    plan = [(episode, repeat) for repeat in range(args.repeats) for episode in episodes]
    if not args.live:
        estimates = [estimate_tokens(render_messages(episode)) for episode, _ in plan]
        # Every call may be retried once for a malformed answer, so each can be paid MAX_ATTEMPTS times.
        worst = MAX_ATTEMPTS * sum(price_usd(args.model, Usage(tokens, MAX_OUTPUT_TOKENS)) for tokens in estimates)
        print(
            json.dumps(
                {
                    "dry_run": True,
                    "episodes": len(episodes),
                    "repeats": args.repeats,
                    "calls": len(plan),
                    "estimated_input_tokens": sum(estimates),
                    "worst_case_usd": round(worst, 4),
                    "max_usd": args.max_usd,
                    "fits_cap": worst <= args.max_usd,
                },
                indent=2,
            )
        )
        return 0

    previous = read_records(args.output)
    fingerprint = freeze_fingerprint()
    if any(row.get("model") != args.model or row.get("fingerprint") != fingerprint for row in previous):
        parser.error(f"{args.output} holds records of another model, prompt, schema or runner; use a new --output")
    if args.output.exists() and not args.output.read_bytes().endswith(b"\n"):
        with args.output.open("a", encoding="utf-8") as stream:  # end a half-written line before appending
            stream.write("\n")
    done = {(row["episode_id"], row["repeat"]) for row in previous if row["status"] == "answered"}
    budget = Budget(
        args.model,
        args.max_usd,
        args.max_tokens,
        spent_usd=sum(row["cost_usd"] for row in previous),
        used_tokens=sum(row["usage"]["total_tokens"] for row in previous),
    )
    resources = resource_loader()
    model = model_factory(args.model)
    args.output.parent.mkdir(parents=True, exist_ok=True)
    for episode, repeat in plan:
        if (episode_id_of(episode), repeat) in done:
            continue
        try:
            record = run_episode(episode, repeat, model=model, budget=budget, resources=resources, sleep=sleep)
        except BudgetExhausted:
            break
        with args.output.open("a", encoding="utf-8") as stream:
            stream.write(json.dumps(record, ensure_ascii=False, default=_json) + "\n")

    records = read_records(args.output)
    report = {
        "system_id": SYSTEM_ID,
        "model": args.model,
        "run_date": datetime.now(UTC).isoformat(timespec="seconds"),
        "fingerprint": fingerprint,
        "release_version": resources.release_version,
        "data_digests": dict(resources.data_digests),
        "episodes_path": str(args.episodes),
        "episodes_sha256": _digest(args.episodes),
        "allow_heldout": args.allow_heldout,
        "repeats": args.repeats,
        "planned_calls": len(plan),
        "answered": sum(row["status"] == "answered" for row in records),
        "call_failed": sum(row["status"] == "call_failed" for row in records),
        "spend": {
            "usd": budget.spent_usd,
            "tokens": budget.used_tokens,
            "calls_this_run": budget.calls,
            "max_usd": args.max_usd,
            "max_tokens": args.max_tokens,
            "prices_usd_per_million": PRICES[args.model],
            "stop_reason": budget.stop_reason,
        },
        "unnamed_product_ingredients": resources.unnamed_product_ingredients,
        "summary": summarise(records, args.repeats),
    }
    report_path = args.output.with_suffix(".report.json")
    report_path.write_text(json.dumps(report, ensure_ascii=False, indent=2, default=_json) + "\n", encoding="utf-8")
    print(f"pure LLM baseline: {report['answered']}/{len(plan)} answered, US${budget.spent_usd:.4f} spent")
    if budget.stop_reason:
        print(f"stopped: {budget.stop_reason}", file=sys.stderr)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
