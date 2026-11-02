"""Data release v3, step 2 (rest of wave 2): enrich recipes with Claude subagents instead of the OpenAI API.

    python scripts/enrich_v3_agents.py export [--batch-size 25]
    python scripts/enrich_v3_agents.py check ANSWERS.jsonl
    python scripts/enrich_v3_agents.py import [--model claude-sonnet-5-5]

The OpenAI run stopped on the account credit; this finishes wave 2 with the same instructions, schema, recipe input
and checks as `enrich_v3_openai.py` (its functions are reused), so an agent answer is judged exactly like a model
answer.

- `export` writes `data/staging/agent-enrich/instructions.md` and `batch-NNN.jsonl`, one line per pending recipe:
  {"candidate_id", "input"}, where `input` is what the OpenAI enricher sends. Pending = every wave-2 pick of
  `v3_selected.jsonl` not in `v3_merged.recipes.jsonl` (OpenAI failures included, asked once more).
- `check` reads answer lines {"candidate_id", "answer"} and prints PASS or the errors of each. It writes nothing.
- `import` reads every `agent-enrich/answers-NNN.jsonl` and appends each passing answer of a recipe not yet merged
  to `v3_merged.recipes.jsonl` (`enriched_by` "claude/<model>"), a failing one to `v3_enrich_failed.jsonl` (once per
  recipe and enricher), then refreshes the committed summary. Re-running it adds nothing new.
"""

from __future__ import annotations

import argparse
import csv
import json
import sys
from datetime import UTC, datetime
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "scripts"))

import enrich_v3_openai as oa  # noqa: E402
import v2_packet  # noqa: E402
from prepare_v2_inputs import read_jsonl, recipe_item  # noqa: E402

WORK = oa.STAGING / "agent-enrich"
WAVE1_CSV = ROOT / "data" / "enrichment" / "v3_selected_wave1.csv"
MODEL = "claude-sonnet-5-5"

ANSWER_FORMAT = """## Answer lines

Write one JSON object per line, one line per recipe of the batch, in a file `answers-NNN.jsonl` (NNN = the batch
number):

    {"candidate_id": "<the candidate_id of the batch line>", "answer": {<an object of the schema above>}}

The answer has every property of the schema and no other. Check a file with
`python scripts/enrich_v3_agents.py check data/staging/agent-enrich/answers-NNN.jsonl` and fix each line that does not
say PASS.
"""


def items() -> dict[str, dict]:
    """candidate_id -> the recipe input, for every selected recipe, in selection order."""
    return {r["candidate_id"]: recipe_item(r) for r in read_jsonl(oa.SELECTED)}


def pending() -> list[dict]:
    with WAVE1_CSV.open(encoding="utf-8", newline="") as handle:
        wave1 = {row["candidate_id"] for row in csv.DictReader(handle)}
    done = {r["candidate_id"] for r in oa.existing(oa.MERGED)}
    return [item for cid, item in items().items() if cid not in wave1 and cid not in done]


def instructions_text() -> str:
    schema = json.dumps(oa.response_schema(), ensure_ascii=False, indent=2)
    return f"{oa.instructions()}\n## Answer schema\n\n```json\n{schema}\n```\n\n{ANSWER_FORMAT}"


def export(batch_size: int) -> list[Path]:
    WORK.mkdir(parents=True, exist_ok=True)
    for old in WORK.glob("batch-*.jsonl"):
        old.unlink()
    (WORK / "instructions.md").write_text(instructions_text(), encoding="utf-8", newline="\n")
    todo, paths = pending(), []
    for start in range(0, len(todo), batch_size):
        path = WORK / f"batch-{start // batch_size + 1:03d}.jsonl"
        lines = [{"candidate_id": item["candidate_id"], "input": item} for item in todo[start : start + batch_size]]
        path.write_text(
            "".join(json.dumps(line, ensure_ascii=False) + "\n" for line in lines), encoding="utf-8", newline="\n"
        )
        paths.append(path)
    print(f"{len(todo)} pending in {len(paths)} batches")
    return paths


def judge(known: dict[str, dict], line: dict, by: str) -> tuple[dict | None, list[str]]:
    """The result of one answer line and its errors (the result is None when it cannot be built)."""
    item = known.get(line.get("candidate_id"))
    if item is None:
        return None, ["candidate_id is not a selected recipe"]
    answer = line.get("answer")
    if not isinstance(answer, dict):
        return None, ["answer must be a JSON object"]
    unknown = set(answer) - set(oa.response_schema()["properties"])
    result = {**oa.to_result(item, answer, MODEL), "enriched_by": by}
    errors = v2_packet.check_recipe(item, result)
    return result, ([f"unknown fields {sorted(unknown)}"] if unknown else []) + errors


def read_answers(path: Path) -> list[dict]:
    """Answer lines; a line that is not a JSON object becomes {} so it is reported, not skipped."""
    rows = []
    for text in path.read_text(encoding="utf-8").splitlines():
        if not text.strip():
            continue
        try:
            row = json.loads(text)
        except ValueError:
            row = {}
        rows.append(row if isinstance(row, dict) else {})
    return rows


def check(path: Path) -> int:
    known = items()
    for line in read_answers(path):
        _, errors = judge(known, line, f"claude/{MODEL}")
        print(f"{line.get('candidate_id')}: " + ("PASS" if not errors else "; ".join(errors)))
    return 0


def import_answers(model: str) -> dict:
    by = f"claude/{model}"
    known = items()
    done = {r["candidate_id"] for r in oa.existing(oa.MERGED)}
    failed = {r["candidate_id"] for r in oa.existing(oa.FAILED) if r.get("by") == by}
    counts = {"added": 0, "failed": 0, "skipped": 0}
    for path in sorted(WORK.glob("answers-*.jsonl")):
        for line in read_answers(path):
            cid = line.get("candidate_id")
            if cid in done:
                counts["skipped"] += 1
                continue
            result, errors = judge(known, line, by)
            if not errors:
                oa.append(oa.MERGED, [result])
                done.add(cid)
                counts["added"] += 1
            elif cid in known and cid not in failed:
                now = datetime.now(UTC).isoformat(timespec="seconds")
                oa.append(oa.FAILED, [{"candidate_id": cid, "errors": errors, "at": now, "by": by}])
                failed.add(cid)
                counts["failed"] += 1
            else:
                counts["skipped"] += 1
    oa.write_summary()
    print(f"import: {counts}")
    return counts


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    commands = parser.add_subparsers(dest="command", required=True)
    commands.add_parser("export").add_argument("--batch-size", type=int, default=25)
    commands.add_parser("check").add_argument("answers", type=Path)
    commands.add_parser("import").add_argument("--model", default=MODEL, help="the agent model, for enriched_by")
    args = parser.parse_args()
    if args.command == "export":
        for path in export(args.batch_size):
            print(path)
        return 0
    if args.command == "check":
        return check(args.answers)
    import_answers(args.model)
    return 0


if __name__ == "__main__":
    sys.exit(main())
