"""The formal Sprint 3 evaluation in one command: every arm on the same questions, then aggregates only.

    python -m app.evaluation.formal_run --episodes <dir> --anchor-date <date> --out <dir>            # dry run
    python -m app.evaluation.formal_run --episodes <dir> --anchor-date <date> --out <dir> --live --allow-heldout
    python -m app.evaluation.formal_run --freeze-record --anchor-date <date>       # docs/evaluation/sprint3-freeze.md

Arms (ADR-0118): strong rules, the pure LLM on the conversation protocol (`pure_llm_baseline.conversation_arm`),
RAG and the general agent, then the product "mealcraft" and its six ablations back to back, so the parser's prompt
prefix stays in OpenAI's cache. Every arm runs through `baseline_arms.main` with its own spend ledger and cap
(ADR-0115: US$5 each, the general agent US$15); the product arms use the OpenAI parser and are metered from the
product's own recorded cost (`ablation_arms.openai_arms`). The episodes may be per-file episodes or the held-out
authoring interchange (`{"cases": [...]}`, `pure_llm_baseline.case_episode`).

- The default is a dry run: per arm its questions, worst case, projected spend (the measured rates of ADR-0118 a
  user turn), its ledger and its cap, and the total against `--credit-usd`. Nothing is called.
- `--live` runs the arms in order. Each resumes from its own records, stops before its cap and the run goes on
  with the next arm. Each arm's `--max-usd` is also held to what the credit has left, so the run as a whole never
  passes `--credit-usd`. `--no-paid` is the free rehearsal: strong rules and the product arms with the fixture
  parser only.
- `--allow-heldout` needs a clean checkout at a commit (the spend ledgers aside) and keeps the per-case records in
  `.local/evaluation/` (ADR-0115 item 4). Only aggregates and the run manifest go to `--out`.

Outcomes (`SCORING`, a draft for the owner to register before the run): an arm's case is `missing` with no record
(not reached, or cut by the cap), `error` when the call or the scorer failed, `failure` for an invalid output. Then
two aggregates by category, language and source, small cells withheld (`heldout_report`, ADR-0100 item 5):
- `action`: success when the final output takes the action the gold expects (plan, clarify, refuse or food_qa);
  a case whose gold names no action is voided for every arm.
- `strict`: success only where the code checks the whole gold: an intent case passes `intent_scorer` (its
  not-scorable verdict is not a success). Every other case is voided for every arm: a held-out plan, question or
  replan needs the sealed catalog adjudication or a rubric, and the v3 development episodes lack the multi-dish
  gold the validator reads (the dev rehearsal showed every arm's validation skipped).
Each also gets the paired comparison of the product with every other arm (`heldout_statistics.compare`, overall
only). `--select-failures N` writes N product failures, round robin over categories and first where a baseline
succeeded, with their records, to the local folder for the failure analyses.
"""

from __future__ import annotations

import argparse
import hashlib
import json
from collections import Counter
from datetime import UTC, date, datetime
from functools import cache
from pathlib import Path
from typing import Any

from app.core.config import ABLATIONS
from app.core.paths import repository_root
from app.evaluation import baseline_arms
from app.evaluation.baseline_resources import BaselineResources, load_resources
from app.evaluation.conversation_adapter import UnifiedOutput
from app.evaluation.heldout_report import CaseOutcome, ExpectedManifest, aggregate, render
from app.evaluation.heldout_statistics import compare
from app.evaluation.intent_scorer import observed_action, score_intent
from app.evaluation.pure_llm_baseline import _digest, episode_id_of, load_episodes, read_records

PRODUCT = "mealcraft"
ORDER = ("strong-rule", "pure-llm", "rag", "general-agent", PRODUCT, *(f"{PRODUCT}/ablation/{n}" for n in ABLATIONS))
# Measured US$ a question, upper end, on development episodes (ADR-0118); counted once per user turn.
MEASURED_USD = {"pure-llm": 0.0153, "rag": 0.0118, "general-agent": 0.0545, PRODUCT: 0.005}
LOCAL = Path(".local/evaluation/formal")
FREEZE_RECORD = Path("docs/evaluation/sprint3-freeze.md")
SCORING = "formal-outcome-draft-1"
CATEGORIES = ("planning", "intent", "multi_turn", "adversarial")
SOURCES = ("forum", "authored")
DISPOSITION_ACTION = {
    "feasible": "plan",
    "catalog_dependent": "plan",
    "clarify": "clarify",
    "answer": "food_qa",
    "refuse": "refuse",
}


def registry(no_paid: bool = False) -> dict[str, baseline_arms.Arm]:
    """Every arm; the product arms with the OpenAI parser, or with `no_paid` the free arms alone."""
    from app.evaluation import ablation_arms

    available = baseline_arms.arms()
    if no_paid:
        return {key: arm for key, arm in available.items() if not arm.paid}
    return available | ablation_arms.openai_arms()


def _absolute(path: Path) -> Path:
    return path if path.is_absolute() else repository_root() / path


def _heldout(path: Path) -> bool:
    return "heldout" in "".join(ch for ch in str(path).lower() if ch.isalnum())


def file_name(system_id: str) -> str:
    return system_id.replace("/", "__")


def ledger(ledger_dir: Path, system_id: str) -> Path:
    return ledger_dir / f"{system_id}.spend.jsonl"


def labels(episode: dict[str, Any], *, heldout: bool) -> tuple[str, str, str]:
    """Category, language and source as the report knows them. A development episode has its own categories
    and no source: it counts as an authored planning case. A held-out one must carry the report's labels."""
    category, language, source = episode.get("category"), episode.get("language"), episode.get("source")
    if not heldout:
        category = category if category in CATEGORIES else "planning"
        source = source if source in SOURCES else "authored"
    if category not in CATEGORIES or language not in ("zh", "en") or source not in SOURCES:
        raise ValueError(f"{episode_id_of(episode)} has labels outside the report's: {category}, {language}, {source}")
    return category, language, source


def expected_action(gold: dict[str, Any] | None) -> str | None:
    if not gold:
        return None
    if gold.get("kind") == "intent":
        return (gold.get("expected_fields") or {}).get("action")
    if "disposition" in gold:  # the held-out authoring interchange
        return DISPOSITION_ACTION.get(gold["disposition"])
    return {"feasible": "plan", "clarification": "clarify"}.get(gold.get("class"))  # the development gold


def final_output(record: dict[str, Any]) -> UnifiedOutput | None:
    exchanges = record.get("exchanges") or []
    return UnifiedOutput.model_validate(exchanges[-1]["output"]) if exchanges else None


def judge(episode: dict[str, Any], record: dict[str, Any] | None) -> tuple[str, str, bool, bool]:
    """(action status, strict status, strict voided, intent not scorable) for one arm's case (`SCORING`)."""
    gold = episode.get("gold") or {}
    want = expected_action(gold)
    strict_void = gold.get("kind") != "intent"
    if record is None:
        return "missing", "missing", strict_void, False
    if record.get("status") != "answered" or "error" in (record.get("scored") or {}):
        return "error", "error", strict_void, False
    output = final_output(record)
    if not record.get("valid_output") or output is None:
        return "failure", "failure", strict_void, False
    action = "success" if want is not None and observed_action(output) == want else "failure"
    if gold.get("kind") == "intent":
        verdict = score_intent(gold, output).outcome
        return action, "success" if verdict == "pass" else "failure", False, verdict == "not_scorable"
    return action, "failure", strict_void, False  # voided: the code cannot check the whole gold


def outcomes(
    episodes: list[dict[str, Any]], records: dict[str, dict[str, dict]], *, heldout: bool
) -> tuple[list[CaseOutcome], list[CaseOutcome], Counter]:
    action_rows, strict_rows, not_scorable = [], [], Counter()
    for episode in episodes:
        case = episode_id_of(episode)
        category, language, source = labels(episode, heldout=heldout)
        no_action = expected_action(episode.get("gold")) is None
        for system_id, by_case in records.items():
            action, strict, voided, unknown = judge(episode, by_case.get(case))
            not_scorable[system_id] += unknown
            common = {"case_ref": case, "system_id": system_id, "run": 1, "category": category}
            common |= {"language": language, "source": source}
            action_rows.append(CaseOutcome(**common, status=action, voided=no_action))
            strict_rows.append(CaseOutcome(**common, status=strict, voided=voided))
    return action_rows, strict_rows, not_scorable


def expected_manifest(rows: list[CaseOutcome], systems: list[str]) -> ExpectedManifest:
    """The counts the episodes declare, so a case some arm lost entirely is caught (`heldout_report`)."""
    cells: dict[str, set[str]] = {}
    for row in rows:
        cells.setdefault(f"{row.category}|{row.language}|{row.source}", set()).add(row.case_ref)
    voided = {row.case_ref for row in rows if row.voided}
    return ExpectedManifest(systems=systems, runs=1, cells={k: len(v) for k, v in cells.items()}, voided=len(voided))


def comparison(rows: list[CaseOutcome]) -> dict:
    try:
        return compare(rows, product_system_id=PRODUCT)
    except ValueError as error:  # no product, no baseline, or nothing left to pair
        return {"not_computed": str(error)}


def select_failures(
    episodes: list[dict[str, Any]], action_rows: list[CaseOutcome], records: dict[str, dict[str, dict]], count: int
) -> list[dict[str, Any]]:
    """Product failures, round robin over categories, a case some baseline got right first; with their records."""
    status = {(row.system_id, row.case_ref): row.status for row in action_rows if not row.voided}
    by_id = {episode_id_of(episode): episode for episode in episodes}
    failed = sorted(case for (system, case), value in status.items() if system == PRODUCT and value != "success")
    beaten = {case for case in failed if any(value == "success" for (s, c), value in status.items() if c == case)}
    queues: dict[str, list[str]] = {}
    for case in sorted(failed, key=lambda case: (case not in beaten, case)):
        queues.setdefault(str(by_id[case].get("category")), []).append(case)
    chosen: list[str] = []
    while len(chosen) < count and any(queues.values()):
        for queue in queues.values():
            if queue and len(chosen) < count:
                chosen.append(queue.pop(0))
    return [
        {
            "episode": by_id[case],
            "statuses": {system: value for (system, c), value in status.items() if c == case},
            "product_record": records[PRODUCT].get(case),
        }
        for case in chosen
    ]


def dry_run(arms: list[baseline_arms.Arm], episodes: list[dict[str, Any]], args: argparse.Namespace) -> dict[str, Any]:
    from app.evaluation.conversation_adapter import ConversationHarness, RuntimeConfig

    instructions = ConversationHarness(RuntimeConfig(anchor_date=args.anchor_date)).instructions
    turns = [baseline_arms.episode_turns(episode) for episode in episodes]
    rows = {}
    for arm in arms:
        spent = baseline_arms.ledger_totals(ledger(args.ledger_dir, arm.system_id))[0] if arm.paid else 0.0
        estimates = [arm.estimate(t, instructions, args.model) for t in turns] if arm.paid and arm.estimate else []
        rate = MEASURED_USD.get(arm.system_id, MEASURED_USD[PRODUCT] if arm.system_id.startswith(PRODUCT) else 0.0)
        if arm.system_id.endswith("rule_only_parser"):
            rate = 0.0  # no parser call (ADR-0118); its ledger still meters anything it sends
        projected = rate * sum(map(len, turns)) if arm.paid else 0.0
        rows[arm.system_id] = {
            "paid": arm.paid,
            "questions": len(episodes),
            "max_calls": sum(calls for calls, _, _ in estimates),
            "worst_case_usd": round(sum(usd for _, _, usd in estimates), 4),
            "projected_usd": round(projected, 4),
            "ledger_usd": round(spent, 4),
            "cap_usd": arm.max_usd if arm.paid else None,
            "projected_fits_cap": spent + projected <= arm.max_usd if arm.paid else True,
        }
    projected = sum(row["projected_usd"] for row in rows.values())
    bound = sum(max(0.0, row["cap_usd"] - row["ledger_usd"]) for row in rows.values() if row["paid"])
    return {
        "dry_run": True,
        "arms": rows,
        "total": {
            "projected_usd": round(projected, 4),
            "caps_left_usd": round(bound, 4),
            "credit_usd": args.credit_usd,
            "projected_fits_credit": projected <= args.credit_usd,
            # Each arm's cap is also held to the credit left when it starts, so the run never passes the credit.
            "caps_left_fit_credit": bound <= args.credit_usd,
        },
    }


def freeze_record(arms: dict[str, baseline_arms.Arm], args: argparse.Namespace, resources: BaselineResources) -> str:
    from app.data.release_v2 import release_digest, release_dir
    from app.evaluation import ablation_arms

    commit, dirty = baseline_arms.code_state()
    lines = [
        "# Sprint 3 formal evaluation: freeze record",
        "",
        f"Computed by `python -m app.evaluation.formal_run --freeze-record` on {datetime.now(UTC):%Y-%m-%d %H:%M} UTC;"
        " not hand-written. Compare it with a fresh one before the held-out run.",
        "",
        f"- Code commit: `{commit}`" + (" (uncommitted changes)" if dirty else ""),
        f"- Anchor date: {args.anchor_date.isoformat()}",
        f"- Release: {resources.release_version}, digest `{release_digest(release_dir())}`",
        f"- Data tree: `{ablation_arms._tree('data')}`; release tree: "
        f"`{ablation_arms._tree(release_dir().relative_to(repository_root()).as_posix())}`",
        *(f"- `{Path(path).as_posix()}`: `{digest}`" for path, digest in resources.data_digests),
        f"- Scoring: {SCORING}",
    ]
    if args.episodes is not None:
        lines.append(f"- Episodes digest: `{_digest(_absolute(args.episodes))}`")
    lines += ["", "| Arm | Paid | Cap (US$) | Parser or model | Fingerprint SHA-256 |", "| --- " * 5 + "|"]
    prints = {}
    for system_id in ORDER:
        arm = arms[system_id]
        prints[system_id] = found = arm.fingerprint()
        parser = found.get("parser_provider") and f"{found['parser_provider']} parser, {found.get('parser_model')}"
        if system_id.endswith("rule_only_parser"):
            parser = "rule parser (switch), no parser call"
        mode = parser or ("rules, no model" if not arm.paid else args.model)
        digest = hashlib.sha256(json.dumps(prints[system_id], sort_keys=True).encode()).hexdigest()
        lines.append(f"| {system_id} | {arm.paid} | {arm.max_usd if arm.paid else '-'} | {mode} | `{digest[:16]}` |")
    lines += ["", "```json", json.dumps(prints, indent=2, sort_keys=True), "```", ""]
    return "\n".join(lines)


def main(
    argv: list[str] | None = None,
    *,
    arms_for=registry,
    resource_loader=load_resources,
    run_arm=baseline_arms.main,
) -> int:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("--episodes", type=Path)
    parser.add_argument("--anchor-date", type=date.fromisoformat)
    parser.add_argument("--out", type=Path, help="public folder for the aggregates and the run manifest")
    parser.add_argument("--live", action="store_true", help="run the arms (default: dry run)")
    parser.add_argument("--allow-heldout", action="store_true")
    parser.add_argument("--arms", nargs="+", help=f"a subset, run in the fixed order; default all: {' '.join(ORDER)}")
    parser.add_argument("--no-paid", action="store_true", help="rehearsal: free arms only, product with fixture parser")
    parser.add_argument("--credit-usd", type=float, default=58.0, help="what the OpenAI credit has left")
    parser.add_argument("--min-cell-n", type=int, default=5, help="small-cell rule of the aggregates (ADR-0100)")
    parser.add_argument("--select-failures", type=int, default=0, metavar="N")
    parser.add_argument("--local", type=Path, help=f"per-case records (default {LOCAL}/<episodes>-<anchor>)")
    parser.add_argument("--ledger-dir", type=Path, default=baseline_arms.LEDGER_DIR)
    parser.add_argument("--model", default="gpt-5.4-mini")
    parser.add_argument("--freeze-record", nargs="?", const=FREEZE_RECORD, type=Path, metavar="PATH")
    args = parser.parse_args(argv)

    if args.anchor_date is None:
        parser.error("--anchor-date is required")
    available = arms_for(args.no_paid)
    loader = cache(resource_loader)
    args.ledger_dir = _absolute(args.ledger_dir)
    if args.freeze_record is not None:
        missing = [system_id for system_id in ORDER if system_id not in available]
        if missing:
            parser.error(f"a freeze record needs every arm; missing {missing}")
        text = freeze_record(available, args, loader())
        target = _absolute(args.freeze_record)
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_text(text, encoding="utf-8", newline="\n")
        print(text)
        return 0
    if args.episodes is None or args.out is None:
        parser.error("--episodes and --out are required")
    wanted = args.arms or list(ORDER)
    unknown = [name for name in wanted if name not in ORDER]
    if unknown:
        parser.error(f"unknown arms {unknown}; known: {', '.join(ORDER)}")
    order = [name for name in ORDER if name in wanted and name in available]
    args.episodes, args.out = _absolute(args.episodes), _absolute(args.out)
    tag = f"{args.episodes.name}-{args.anchor_date.isoformat()}" + ("-no-paid" if args.no_paid else "")
    args.local = _absolute(args.local or LOCAL / tag)
    for path in (args.episodes, args.out, args.local):
        if _heldout(path) and not args.allow_heldout:
            parser.error(f"{path} is a held-out path; pass --allow-heldout only for the frozen run")
    if args.allow_heldout:
        if not args.local.is_relative_to(repository_root() / ".local/evaluation"):
            parser.error("a held-out run keeps its per-case records under .local/evaluation/ (ADR-0115 item 4)")
        commit, dirty = baseline_arms.code_state()
        if dirty is not False or commit is None:
            parser.error("a held-out run needs a clean checkout at a recorded commit")
    episodes = load_episodes(args.episodes)
    try:
        for episode in episodes:
            labels(episode, heldout=args.allow_heldout)  # refuse before any spend, not after
    except ValueError as error:
        parser.error(str(error))
    if not args.live:
        print(json.dumps(dry_run([available[name] for name in order], episodes, args), indent=2))
        return 0

    paid = [name for name in order if available[name].paid]
    started = {name: baseline_arms.ledger_totals(ledger(args.ledger_dir, name))[0] for name in paid}
    runs: dict[str, dict[str, Any]] = {}
    for name in order:
        arm = available[name]
        output = args.local / f"{file_name(name)}.jsonl"
        argv_arm = ["--arm", name, "--episodes", str(args.episodes), "--anchor-date", args.anchor_date.isoformat()]
        argv_arm += ["--output", str(output), "--ledger", str(ledger(args.ledger_dir, name))]
        run: dict[str, Any] = {"paid": arm.paid, "cap_usd": arm.max_usd if arm.paid else None}
        if arm.paid:
            spent = sum(baseline_arms.ledger_totals(ledger(args.ledger_dir, n))[0] - started[n] for n in paid)
            own = baseline_arms.ledger_totals(ledger(args.ledger_dir, name))[0]
            run["max_usd"] = round(min(arm.max_usd, own + args.credit_usd - spent), 6)
            if run["max_usd"] <= own:
                run["stop_reason"] = "credit guard: no credit left for this arm"
                runs[name] = run
                continue
            argv_arm += ["--live", "--max-usd", str(run["max_usd"]), "--model", args.model]
        if args.allow_heldout:
            argv_arm.append("--allow-heldout")
        try:
            run_arm(argv_arm, registry=lambda: available, resource_loader=loader)
        except SystemExit as error:  # the arm's runner refused (another configuration's records, say)
            run["refused"] = f"exit status {error.code}"
        report = output.with_suffix(".report.json")
        if report.exists():
            body = json.loads(report.read_text(encoding="utf-8"))
            run |= {"answered": body["answered"], "call_failed": body["call_failed"]}
            run["stop_reason"] = (body.get("spend") or {}).get("stop_reason")
        runs[name] = run

    # Aggregates only from here on: nothing below writes a case to --out.
    heldout = args.allow_heldout
    records = {  # a refused arm's file may hold another configuration's records: its cases are missing
        name: {}
        if "refused" in runs[name]
        else {row["episode_id"]: row for row in read_records(args.local / f"{file_name(name)}.jsonl")}
        for name in order
    }
    action_rows, strict_rows, not_scorable = outcomes(episodes, records, heldout=heldout)
    args.out.mkdir(parents=True, exist_ok=True)
    for kind, rows in (("action", action_rows), ("strict", strict_rows)):
        report = aggregate(rows, expected_manifest(rows, order), min_cell_n=args.min_cell_n)
        report["scoring"] = SCORING
        (args.out / f"aggregate-{kind}.json").write_text(render(report), encoding="utf-8", newline="\n")
        comparison_text = render(comparison(rows))
        (args.out / f"comparison-{kind}.json").write_text(comparison_text, encoding="utf-8", newline="\n")
    resources = loader()
    commit, dirty = baseline_arms.code_state()
    for name in order:
        rows = list(records[name].values())
        spent = baseline_arms.ledger_totals(ledger(args.ledger_dir, name))[0] if name in started else 0.0
        runs[name] |= {
            "fingerprint": available[name].fingerprint(),
            "records": len(rows),
            "valid_output": sum(bool(row.get("valid_output")) for row in rows),
            "intent_not_scorable": not_scorable[name],
            "ledger_usd": round(spent, 6),
            "spent_this_run_usd": round(spent - started.get(name, 0.0), 6),
        }
    manifest = {
        "run_date": datetime.now(UTC).isoformat(timespec="seconds"),
        "code_commit": commit,
        "worktree_dirty": dirty,
        "anchor_date": args.anchor_date.isoformat(),
        "allow_heldout": heldout,
        "episodes_sha256": _digest(args.episodes),
        "questions": len(episodes),
        "release_version": resources.release_version,
        "data_digests": {Path(path).as_posix(): digest for path, digest in resources.data_digests},
        "scoring": SCORING,
        "min_cell_n": args.min_cell_n,
        "credit_usd": args.credit_usd,
        "spent_this_run_usd": round(sum(run.get("spent_this_run_usd", 0.0) for run in runs.values()), 6),
        "arms": runs,
    }
    (args.out / "manifest.json").write_text(
        json.dumps(manifest, ensure_ascii=False, indent=2, sort_keys=True) + "\n", encoding="utf-8", newline="\n"
    )
    if args.select_failures:
        if PRODUCT not in records:
            parser.error("--select-failures needs the mealcraft arm")
        chosen = select_failures(episodes, action_rows, records, args.select_failures)
        target = args.local / "failures.json"
        target.write_text(json.dumps(chosen, ensure_ascii=False, indent=2) + "\n", encoding="utf-8", newline="\n")
        print(f"{len(chosen)} failure cases for analysis in {target} (local only)")
    for name, run in runs.items():
        stop = f", stopped: {run['stop_reason']}" if run.get("stop_reason") else ""
        print(f"{name}: {run.get('answered', 0)}/{len(episodes)} answered{stop}")
    print(f"aggregates and manifest in {args.out}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
