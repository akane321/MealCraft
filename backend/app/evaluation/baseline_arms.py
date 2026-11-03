"""Run the rebuilt baseline arms through the conversation harness (ADR-0092; 02-baselines.md; issue #396).

Every arm is a `Responder` of `app.evaluation.conversation_adapter`: it receives the original user strings, its
own earlier exchanges and the shared instructions, and returns one `UnifiedOutput`. Nothing of an episode except
its user strings reaches an arm: no gold, category, household profile, pool or products.

After the conversation, a plan is turned into the ingredient-level `BaselineResponse` (each dish's ingredient
lines, steps and time come from its `evidence`) and scored by the same shared layers as the pure-LLM arm
(`pure_llm_baseline.score`: mapping, coverage, recomputation, allergen safety, the product validator). This module
changes none of them.

Cost rules are the pure-LLM runner's (ADR-0086, US$5 per arm including development runs): dry run by default,
`--live` for a paid call, `--max-usd` and `--max-tokens` stop before a call whose worst case could pass them, spend
is counted across resumed runs into the same output, and held-out paths are refused without `--allow-heldout`.
An arm without paid calls (strong rules) runs without `--live`.

    python -m app.evaluation.baseline_arms --arm strong-rule \\
        --episodes data/evaluation/dev/v3-meal-day-week/episodes --anchor-date 2026-09-28 \\
        --output docs/evaluation/baselines/dev/strong-rule.jsonl
    python -m app.evaluation.baseline_arms --arm strong-rule --fingerprint
"""

from __future__ import annotations

import argparse
import hashlib
import json
import sys
import time
from collections.abc import Callable
from dataclasses import dataclass
from datetime import UTC, date, datetime
from pathlib import Path
from typing import Any

from pydantic import ValidationError

from app.core.paths import repository_root
from app.evaluation.baseline_output import BaselineResponse
from app.evaluation.baseline_resources import BaselineResources, load_resources
from app.evaluation.conversation_adapter import (
    ConversationHarness,
    ConversationResult,
    Responder,
    RuntimeConfig,
    UnifiedOutput,
)
from app.evaluation.pure_llm_baseline import (
    DEFAULT_MAX_TOKENS,
    DEFAULT_MAX_USD,
    Budget,
    BudgetExhausted,
    Usage,
    _digest,
    _json,
    episode_id_of,
    load_episodes,
    price_usd,
    read_records,
    score,
    summarise,
)

WEEKDAY_SLOTS = ("mon", "tue", "wed", "thu", "fri", "sat", "sun")


@dataclass(frozen=True)
class ArmContext:
    """What one case's responder may use: the frozen resources, and for a paid arm its model and budget."""

    resources: BaselineResources
    budget: Budget | None = None
    model: Any = None


@dataclass(frozen=True)
class Arm:
    system_id: str
    paid: bool
    fingerprint: Callable[[], dict[str, str]]
    # A fresh responder for one case (the harness's rule: one responder serves one case).
    responder: Callable[[ArmContext], Responder]
    # Dry run: (calls, input tokens, worst-case USD) for one case's user strings; None for an arm with no paid call.
    estimate: Callable[[list[str], str, str], tuple[int, int, float]] | None = None
    # A paid arm's model client, built only for a live run.
    model_factory: Callable[[str], Any] | None = None


def arms() -> dict[str, Arm]:
    from app.evaluation import rag_baseline, strong_rule_baseline

    registry = [strong_rule_baseline.ARM, rag_baseline.ARM]
    return {arm.system_id: arm for arm in registry}


def episode_turns(episode: dict[str, Any]) -> list[str]:
    """The user's own strings in order: earlier user turns, then the request. Never an assistant turn or gold."""
    scenario = episode.get("scenario", episode)
    turns = [
        str(turn.get("content") or "")
        for turn in scenario.get("conversation_history") or []
        if isinstance(turn, dict) and turn.get("role") == "user"
    ]
    return [turn for turn in [*turns, str(scenario.get("user_request") or "")] if turn]


def slot_id(day: date, meal_type: str) -> str:
    """`mon-dinner`: the slot names the development episodes use."""
    return f"{WEEKDAY_SLOTS[day.weekday()]}-{meal_type}"


def to_baseline_response(output: UnifiedOutput, *, episode_id: str, system_id: str) -> BaselineResponse:
    """The final output as the shared scoring layers read it.

    A plan's dishes carry their ingredient lines in `evidence` (`ingredients`: name and grams; `steps`;
    `cooking_time_minutes`). A dish without them cannot be scored and raises: it is an invalid output, never a
    feasible or infeasible answer. No plan with a question is a clarification; no plan otherwise is infeasible.
    """
    if output.plan is None:
        if output.clarification:
            return BaselineResponse(
                episode_id=episode_id,
                system_id=system_id,
                status="clarification",
                clarification=[{"field": "unspecified", "question": text} for text in output.clarification],
            )
        conflict = output.refusal or output.answer or "no plan was given"
        return BaselineResponse(
            episode_id=episode_id, system_id=system_id, status="infeasible", infeasible={"conflict": conflict}
        )
    meals = []
    for meal in output.plan.meals:
        dishes = []
        for dish in meal.dishes:
            evidence = dish.evidence
            dishes.append(
                {
                    "name": dish.name,
                    "role_id": dish.role,
                    "servings": dish.servings or output.plan.household_size or 1,
                    "cooking_time_minutes": evidence.get("cooking_time_minutes"),
                    "steps": evidence.get("steps"),
                    "ingredients": evidence.get("ingredients"),
                }
            )
        meals.append({"slot_id": slot_id(meal.date, meal.meal_type), "dishes": dishes})
    return BaselineResponse(
        episode_id=episode_id,
        system_id=system_id,
        status="plan",
        plan={"meals": meals, "total_cost_sgd": output.plan.total_cost_sgd},
    )


def run_case(
    arm: Arm, episode: dict[str, Any], repeat: int, *, config: RuntimeConfig, context: ArmContext
) -> dict[str, Any]:
    episode_id = episode_id_of(episode)
    spent_before = context.budget.spent_usd if context.budget else 0.0
    tokens_before = context.budget.used_tokens if context.budget else 0
    calls_before = context.budget.calls if context.budget else 0
    started = time.perf_counter()
    conversation: ConversationResult | None = None
    response: BaselineResponse | None = None
    errors: list[str] = []
    scored: dict[str, Any] = {}
    try:
        conversation = ConversationHarness(config).run(arm.system_id, episode_turns(episode), arm.responder(context))
    except BudgetExhausted:
        raise
    except Exception as error:  # a failed case is recorded and the run goes on; it is never an infeasible answer
        errors.append(f"{type(error).__name__}: {error}")
    if conversation is not None:
        try:
            response = to_baseline_response(conversation.final, episode_id=episode_id, system_id=arm.system_id)
        except (ValidationError, ValueError, TypeError) as error:
            errors.append(f"invalid output: {error}")
        if response is not None:
            try:
                scored = score(episode, response, context.resources)
            except Exception as error:
                scored = {"error": f"{type(error).__name__}: {error}"}
    budget = context.budget
    return {
        "episode_id": episode_id,
        "repeat": repeat,
        "system_id": arm.system_id,
        "model": budget.model if budget else None,
        "fingerprint": arm.fingerprint(),
        "anchor_date": config.anchor_date.isoformat(),
        "category": episode.get("category"),
        "language": episode.get("language"),
        "status": "answered" if conversation is not None else "call_failed",
        "valid_output": response is not None,
        "errors": errors,
        "confirmations": conversation.confirmation_count if conversation else 0,
        "calls": (budget.calls - calls_before) if budget else 0,
        "usage": {"total_tokens": (budget.used_tokens - tokens_before) if budget else 0},
        "cost_usd": (budget.spent_usd - spent_before) if budget else 0.0,
        "elapsed_seconds": round(time.perf_counter() - started, 3),
        "exchanges": [item.model_dump(mode="json") for item in conversation.exchanges] if conversation else [],
        "response": response.model_dump(mode="json") if response else None,
        "scored": scored,
    }


def main(
    argv: list[str] | None = None,
    *,
    registry: Callable[[], dict[str, Arm]] = arms,
    resource_loader: Callable[[], BaselineResources] = load_resources,
) -> int:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("--arm", required=True)
    parser.add_argument("--episodes", type=Path)
    parser.add_argument("--output", type=Path, help="JSONL of case records; the report is written beside it")
    parser.add_argument("--anchor-date", type=date.fromisoformat, help="the one global clock date (ADR-0092)")
    parser.add_argument("--live", action="store_true", help="make paid model calls (default: dry run)")
    parser.add_argument("--repeats", type=int, default=1)
    parser.add_argument("--max-usd", type=float, default=DEFAULT_MAX_USD)
    parser.add_argument("--max-tokens", type=int, default=DEFAULT_MAX_TOKENS)
    parser.add_argument("--model", default="gpt-5.4-mini")
    parser.add_argument("--allow-heldout", action="store_true")
    parser.add_argument("--fingerprint", action="store_true", help="print the freeze fingerprint and exit")
    args = parser.parse_args(argv)

    available = registry()
    if args.arm not in available:
        parser.error(f"unknown arm {args.arm!r}; available: {', '.join(sorted(available))}")
    arm = available[args.arm]
    if args.fingerprint:
        print(json.dumps(arm.fingerprint(), indent=2))
        return 0
    if args.episodes is None or args.output is None or args.anchor_date is None:
        parser.error("--episodes, --output and --anchor-date are required")
    args.episodes, args.output = (
        path if path.is_absolute() else repository_root() / path for path in (args.episodes, args.output)
    )
    if args.repeats < 1:
        parser.error("--repeats must be at least 1")
    for path in (args.episodes, args.output):
        if "heldout" in "".join(ch for ch in str(path).lower() if ch.isalnum()) and not args.allow_heldout:
            parser.error(f"{path} is a held-out path; pass --allow-heldout only for the frozen run")

    from app.evaluation.pure_llm_baseline import PRICES

    if arm.paid and args.model not in PRICES:
        parser.error(f"no price for {args.model}; add it to PRICES before any run so the cap can hold")
    config = RuntimeConfig(anchor_date=args.anchor_date)
    episodes = load_episodes(args.episodes)
    plan = [(episode, repeat) for repeat in range(args.repeats) for episode in episodes]
    if arm.paid and not args.live:
        instructions = ConversationHarness(config).instructions
        estimates = [arm.estimate(episode_turns(episode), instructions, args.model) for episode, _ in plan]  # type: ignore[misc]
        worst = sum(usd for _, _, usd in estimates)
        print(
            json.dumps(
                {
                    "dry_run": True,
                    "arm": arm.system_id,
                    "episodes": len(episodes),
                    "repeats": args.repeats,
                    "max_calls": sum(calls for calls, _, _ in estimates),
                    "estimated_input_tokens": sum(tokens for _, tokens, _ in estimates),
                    "worst_case_usd": round(worst, 4),
                    "max_usd": args.max_usd,
                    "fits_cap": worst <= args.max_usd,
                },
                indent=2,
            )
        )
        return 0

    previous = read_records(args.output)
    fingerprint = arm.fingerprint()
    model_name = args.model if arm.paid else None
    if any(row.get("model") != model_name or row.get("fingerprint") != fingerprint for row in previous):
        parser.error(f"{args.output} holds records of another model, prompt or runner; use a new --output")
    if any(row.get("anchor_date") != config.anchor_date.isoformat() for row in previous):
        parser.error(f"{args.output} holds records of another anchor date; use a new --output")
    if args.output.exists() and not args.output.read_bytes().endswith(b"\n"):
        with args.output.open("a", encoding="utf-8") as stream:
            stream.write("\n")
    done = {(row["episode_id"], row["repeat"]) for row in previous if row["status"] == "answered"}
    budget = None
    if arm.paid:
        budget = Budget(
            args.model,
            args.max_usd,
            args.max_tokens,
            spent_usd=sum(row["cost_usd"] for row in previous),
            used_tokens=sum(row["usage"]["total_tokens"] for row in previous),
        )
    resources = resource_loader()
    model = arm.model_factory(args.model) if arm.paid and arm.model_factory else None
    context = ArmContext(resources=resources, budget=budget, model=model)
    args.output.parent.mkdir(parents=True, exist_ok=True)
    for episode, repeat in plan:
        if (episode_id_of(episode), repeat) in done:
            continue
        try:
            record = run_case(arm, episode, repeat, config=config, context=context)
        except BudgetExhausted:
            break
        with args.output.open("a", encoding="utf-8") as stream:
            stream.write(json.dumps(record, ensure_ascii=False, default=_json) + "\n")

    records = read_records(args.output)
    report = {
        "system_id": arm.system_id,
        "model": model_name,
        "run_date": datetime.now(UTC).isoformat(timespec="seconds"),
        "anchor_date": config.anchor_date.isoformat(),
        "fingerprint": fingerprint,
        "release_version": resources.release_version,
        "data_digests": dict(resources.data_digests),
        "episodes_path": str(args.episodes.relative_to(repository_root()))
        if args.episodes.is_relative_to(repository_root())
        else str(args.episodes),
        "episodes_sha256": _digest(args.episodes),
        "allow_heldout": args.allow_heldout,
        "repeats": args.repeats,
        "planned_cases": len(plan),
        "answered": sum(row["status"] == "answered" for row in records),
        "call_failed": sum(row["status"] == "call_failed" for row in records),
        "spend": {
            "usd": budget.spent_usd if budget else 0.0,
            "tokens": budget.used_tokens if budget else 0,
            "calls_this_run": budget.calls if budget else 0,
            "max_usd": args.max_usd if arm.paid else None,
            "stop_reason": budget.stop_reason if budget else None,
        },
        "summary": summarise(records, args.repeats),
    }
    report_path = args.output.with_suffix(".report.json")
    report_path.write_text(json.dumps(report, ensure_ascii=False, indent=2, default=_json) + "\n", encoding="utf-8")
    print(f"{arm.system_id}: {report['answered']}/{len(plan)} answered, US${report['spend']['usd']:.4f} spent")
    if budget and budget.stop_reason:
        print(f"stopped: {budget.stop_reason}", file=sys.stderr)
    return 0


def affordable(budget: Budget, input_tokens: int, output_tokens: int) -> bool:
    """Whether a call of this worst case fits what is left of both caps; sets the budget's stop reason if not."""
    usage = Usage(input_tokens, output_tokens)
    usd = price_usd(budget.model, usage)
    if budget.spent_usd + usd > budget.max_usd:
        budget.stop_reason = f"spend cap: US${budget.spent_usd:.4f} spent, next call could cost US${usd:.4f}"
    elif budget.used_tokens + usage.total_tokens > budget.max_tokens:
        budget.stop_reason = f"token cap: {budget.used_tokens} used, next call could use {usage.total_tokens}"
    return budget.stop_reason is None


def sha256_text(text: str | bytes) -> str:
    return hashlib.sha256(text.encode("utf-8") if isinstance(text, str) else text).hexdigest()


def source_sha256(path: str | Path) -> str:
    """A runner file's digest with line endings normalised, so a Windows checkout and CI agree."""
    return sha256_text(Path(path).read_bytes().replace(b"\r\n", b"\n"))


if __name__ == "__main__":
    raise SystemExit(main())
