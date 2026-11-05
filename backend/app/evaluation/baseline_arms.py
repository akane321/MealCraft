"""Run the rebuilt baseline arms through the conversation harness (ADR-0092; 02-baselines.md; issue #396).

Every arm is a `Responder` of `app.evaluation.conversation_adapter`: it receives the original user strings, its
own earlier exchanges and the shared instructions, and returns one `UnifiedOutput`. Nothing of an episode except
its user strings reaches an arm: no gold, category, household profile, pool or products.

After the conversation, a plan is turned into the ingredient-level `BaselineResponse` (each dish's ingredient
lines, steps and time come from its `evidence`) and scored by the same shared layers as the pure-LLM arm
(`pure_llm_baseline.score`: mapping, coverage, recomputation, allergen safety, the product validator). This module
changes none of them.

Cost rules are the pure-LLM runner's (ADR-0086, US$5 per arm including development runs): dry run by default,
`--live` for a paid call, `--max-usd` and `--max-tokens` stop before a call whose worst case could pass them, and
held-out paths are refused without `--allow-heldout`. Spend is kept in one append-only ledger per arm
(`LedgerBudget`, owner review on #427), so it is counted across every run and output of the arm, a case cut by the
cap or a killed process included.
An arm without paid calls (strong rules, the product and its ablations: `ablation_arms`) runs without `--live`.

    python -m app.evaluation.baseline_arms --arm strong-rule \\
        --episodes data/evaluation/dev/v3-meal-day-week/episodes --anchor-date 2026-09-28 \\
        --output docs/evaluation/baselines/dev/strong-rule.jsonl
    python -m app.evaluation.baseline_arms --arm strong-rule --fingerprint
"""

from __future__ import annotations

import argparse
import hashlib
import json
import subprocess
import sys
import time
from collections.abc import Callable
from dataclasses import dataclass, replace
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
LEDGER_DIR = Path("docs/evaluation/baselines")
# An API error with one of these statuses was refused before any work, so it is not billed (400, 401, 403, 404,
# 409, 422, 429). A timeout, a dropped connection or a server error may have been billed: its reserve stands.
UNBILLED_STATUSES = frozenset({400, 401, 403, 404, 409, 422, 429})


def ledger_totals(path: Path | None) -> tuple[float, int]:
    """An arm's spend so far, read in order: every charge, and every reserve no charge followed at its worst case.

    Calls are made one at a time, so a reserve is settled by the next line if that line is a charge; a reserve
    followed by another reserve or by the end of the file was a call that may have been billed (a timeout, a
    killed process) and counts in full."""
    if path is None or not path.exists():
        return 0.0, 0
    usd, tokens = 0.0, 0
    pending: dict | None = None
    for line in path.read_text(encoding="utf-8").splitlines():
        if not line.strip():
            continue
        try:
            row = json.loads(line)
        except json.JSONDecodeError:
            continue  # a half-written last line; its call is counted by the reserve before it
        if row.get("event") == "reserve":
            if pending is not None:
                usd, tokens = usd + pending["usd"], tokens + pending.get("total_tokens", 0)
            pending = row
        elif row.get("event") == "charge":
            usd, tokens = usd + row["usd"], tokens + row.get("total_tokens", 0)
            pending = None
    if pending is not None:
        usd, tokens = usd + pending["usd"], tokens + pending.get("total_tokens", 0)
    return usd, tokens


@dataclass
class LedgerBudget(Budget):
    """`Budget` with the arm's append-only spend ledger: one per arm, not per output (owner review on #427).

    Every paid call is `reserve`d at its worst case after the caps allow it and before it is made, then `charge`d
    with what it cost (tokens plus tool fees), or settled at zero when the API refused it unbilled. The ledger's
    total opens every run, so a case cut by the cap, a crash or a killed process is never lost, and the dev trial
    and the held-out run share the arm's one US$5."""

    ledger: Path | None = None
    episode_id: str | None = None  # left out of the ledger on a held-out run
    record_episodes: bool = True
    _reserved: tuple[float, int] | None = None

    def _write(self, row: dict) -> None:
        if self.ledger is None:
            return
        self.ledger.parent.mkdir(parents=True, exist_ok=True)
        with self.ledger.open("a", encoding="utf-8") as stream:
            stream.write(json.dumps(row, sort_keys=True) + "\n")
            stream.flush()

    def reserve(self, input_tokens: int, output_tokens: int, extra_usd: float = 0.0) -> None:
        """Check both caps for this call's worst case; raise `BudgetExhausted` without writing, or write the reserve."""
        usage = Usage(input_tokens, output_tokens)
        usd = price_usd(self.model, usage) + extra_usd
        if self.spent_usd + usd > self.max_usd:
            self.stop_reason = f"spend cap: US${self.spent_usd:.4f} spent, next call could cost US${usd:.4f}"
        elif self.used_tokens + usage.total_tokens > self.max_tokens:
            self.stop_reason = f"token cap: {self.used_tokens} used, next call could use {usage.total_tokens}"
        if self.stop_reason is not None:
            raise BudgetExhausted(self.stop_reason)
        self._reserved = (usd, usage.total_tokens)
        self._write({"event": "reserve", "usd": usd, "total_tokens": usage.total_tokens})

    def charge(self, usage: Usage, extra_usd: float = 0.0, **detail: Any) -> float:
        cost = self.record(usage) + extra_usd
        self.spent_usd += extra_usd
        self._reserved = None
        row = {
            "event": "charge",
            "usd": cost,
            "input_tokens": usage.input_tokens,
            "output_tokens": usage.output_tokens,
            "total_tokens": usage.total_tokens,
            **detail,
        }
        if self.record_episodes and self.episode_id is not None:
            row["episode_id"] = self.episode_id
        self._write(row)
        return cost

    def failed(self, error: BaseException) -> None:
        """Settle a call that raised: zero when the API refused it unbilled, else its reserve stands, in memory too."""
        if self._reserved is None:
            return
        if getattr(error, "status_code", None) in UNBILLED_STATUSES:
            self._write({"event": "charge", "usd": 0.0, "total_tokens": 0, "unbilled": type(error).__name__})
        else:
            usd, tokens = self._reserved
            self.spent_usd += usd
            self.used_tokens += tokens
        self._reserved = None

    def paid(self, call: Callable[[], Any], input_tokens: int, output_tokens: int, extra_usd: float = 0.0) -> Any:
        """Reserve, call, and settle a call that raises; the caller charges a call that returns."""
        self.reserve(input_tokens, output_tokens, extra_usd)
        try:
            return call()
        except BaseException as error:
            self.failed(error)
            raise


@dataclass(frozen=True)
class ArmContext:
    """What one case's responder may use: the frozen resources, and for a paid arm its model and budget."""

    resources: BaselineResources
    budget: LedgerBudget | None = None
    model: Any = None
    # This case's tool calls and per-step response facts, written into its record; None outside a run.
    trace: list[dict] | None = None
    keep_raw: bool = True  # raw responses go into the trace on development runs only


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
    """The three baselines, and the product with its six ablations run in this process (`ablation_arms`)."""
    from app.evaluation import ablation_arms, general_agent_baseline, rag_baseline, strong_rule_baseline

    registry = [strong_rule_baseline.ARM, rag_baseline.ARM, general_agent_baseline.ARM]
    return {arm.system_id: arm for arm in registry} | ablation_arms.in_process_arms()


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
    context = replace(context, trace=[])
    if context.budget is not None:
        context.budget.episode_id = episode_id
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
        "tool_calls": context.trace,
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
    parser.add_argument(
        "--ledger",
        type=Path,
        help=f"the arm's spend ledger (default {LEDGER_DIR}/<arm>.spend.jsonl), shared by its runs",
    )
    parser.add_argument("--retry-failed", action="store_true", help="ask again the cases whose call failed (paid)")
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
    args.ledger = args.ledger or LEDGER_DIR / f"{arm.system_id}.spend.jsonl"
    args.episodes, args.output, args.ledger = (
        path if path.is_absolute() else repository_root() / path for path in (args.episodes, args.output, args.ledger)
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
        spent_before = ledger_totals(args.ledger)[0]  # the arm's US$5 is shared by all its runs (ADR-0115)
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
                    "ledger_usd": round(spent_before, 4),
                    "fits_cap": spent_before + worst <= args.max_usd,
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
    # A case whose call failed was paid for; it is asked again only on request.
    done = {
        (row["episode_id"], row["repeat"])
        for row in previous
        if row["status"] == "answered" or (row["status"] == "call_failed" and not args.retry_failed)
    }
    commit, dirty = code_state()
    if args.allow_heldout and (dirty is not False or commit is None):
        parser.error("a held-out run needs a clean checkout at a recorded commit")
    budget = None
    if arm.paid:
        spent, tokens = ledger_totals(args.ledger)
        budget = LedgerBudget(
            args.model,
            args.max_usd,
            args.max_tokens,
            spent_usd=spent,
            used_tokens=tokens,
            ledger=args.ledger,
            record_episodes=not args.allow_heldout,
        )
    resources = resource_loader()
    model = arm.model_factory(args.model) if arm.paid and arm.model_factory else None
    context = ArmContext(resources=resources, budget=budget, model=model, keep_raw=not args.allow_heldout)
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
        "code_commit": commit,
        "worktree_dirty": dirty,
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
            "ledger": str(args.ledger.relative_to(repository_root()))
            if arm.paid and args.ledger.is_relative_to(repository_root())
            else (str(args.ledger) if arm.paid else None),
            # The arm's total from its ledger, every run of it included; this output's cases are in cost_usd.
            "usd": ledger_totals(args.ledger)[0] if budget else 0.0,
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


def _git(*arguments: str) -> str | None:
    try:
        result = subprocess.run(  # noqa: S603
            ["git", *arguments],  # noqa: S607
            cwd=repository_root(),
            capture_output=True,
            text=True,
            timeout=10,
            check=True,
        )
    except (OSError, subprocess.SubprocessError):
        return None
    return result.stdout


def code_state() -> tuple[str | None, bool | None]:
    """The checkout's commit and whether its worktree has changes (None when git cannot tell).

    Both come from the same checkout: ``git rev-parse HEAD``, not a ``CODE_COMMIT`` variable.
    """
    head = _git("rev-parse", "HEAD")
    status = _git("status", "--porcelain")
    commit = (head.strip() or None) if head is not None else None
    dirty = bool(status.strip()) if status is not None else None
    return commit, dirty


def sha256_text(text: str | bytes) -> str:
    return hashlib.sha256(text.encode("utf-8") if isinstance(text, str) else text).hexdigest()


def source_sha256(path: str | Path) -> str:
    """A runner file's digest with line endings normalised, so a Windows checkout and CI agree."""
    return sha256_text(Path(path).read_bytes().replace(b"\r\n", b"\n"))


if __name__ == "__main__":
    raise SystemExit(main())
