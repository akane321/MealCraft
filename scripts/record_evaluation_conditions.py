"""Record what a published evaluation report was actually computed over.

`ADR-0020` section 3 requires every generated report to carry the path and
SHA-256 of its datasets. The workbench now records them in every report it
generates; this script exists for the v1 report that was published before it
did, which carried metric values with no record of the catalog behind them.
A report in that state stays byte-identical while the data underneath it
changes, and afterwards nobody can say which world a
published number came from - not even that it moved.

This script closes that gap for a report that has already been published. It
does not re-run the evaluation. Instead it digests the inputs as they stand and
**proves** the digests describe the published run, by checking that no input has
been committed since the report itself was. Without that check the output would
be a hope rather than a record, so a failed check is a hard error.

    python scripts/record_evaluation_conditions.py --label v1

Newly generated reports carry their own `inputs` block and do not need this.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]

# The defaults of `app.evaluation.workbench`, which is what produced latest.json.
INPUTS = {
    "ingredients": "data/ingredients/ingredients.json",
    "recipes": "data/recipes/recipes.json",
    "developer": "data/evaluation/dev/planning-v1.json",
    "heldout": "data/evaluation/heldout/planning-v1.json",
    "agent": "data/evaluation/agent/fixture-v1.json",
    "scope": "data/evaluation/agent-orchestration/scope-developer-v1.json",
    "grounding": "data/evaluation/agent-orchestration/grounding-developer-v1.json",
    "fixtures": "data/fixtures/fairprice-products.json",
}
REPORT = "docs/evaluation/workbench/latest.json"
# A larger-catalog condition (`--release`) also ran on the release and its products.
RELEASE_INPUTS = {
    "release_manifest": "data-engineering/data/release/v2.1/release_manifest.json",
    "release_recipes": "data-engineering/data/release/v2.1/recipes.jsonl",
    "release_ingredients": "data-engineering/data/release/v2.1/ingredients.jsonl",
    "release_products": "data/products/fairprice-v2-snapshot.json",
}


def git(*args: str) -> str:
    return subprocess.run(["git", "-C", str(ROOT), *args], capture_output=True, text=True, check=True).stdout.strip()


def last_commit(path: str) -> str:
    commit = git("log", "-1", "--format=%H", "--", path)
    if not commit:
        raise SystemExit(f"{path} has no commit history; cannot attest to it.")
    return commit


def is_ancestor(candidate: str, descendant: str) -> bool:
    result = subprocess.run(
        ["git", "-C", str(ROOT), "merge-base", "--is-ancestor", candidate, descendant],
        capture_output=True,
    )
    return result.returncode == 0


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--label", required=True, help="the version these conditions belong to, e.g. v1")
    parser.add_argument("--report", default=REPORT)
    parser.add_argument("--out", type=Path, default=None)
    parser.add_argument("--with-release", action="store_true", help="the report was generated with --release")
    parser.add_argument("--developer", default=None, help="the developer scenarios, when not the default")
    parser.add_argument("--heldout", default=None, help="the held-out scenarios, when not the default")
    args = parser.parse_args()
    inputs = {**INPUTS, **(RELEASE_INPUTS if args.with_release else {})}
    inputs.update({key: value for key, value in (("developer", args.developer), ("heldout", args.heldout)) if value})

    report_commit = last_commit(args.report)
    entries: dict[str, dict[str, str]] = {}
    drifted: list[str] = []

    for name, relative in sorted(inputs.items()):
        path = ROOT / relative
        if not path.is_file():
            raise SystemExit(f"missing input: {relative}")
        input_commit = last_commit(relative)
        if not is_ancestor(input_commit, report_commit):
            drifted.append(f"{relative} (last changed in {input_commit[:12]})")
        entries[name] = {
            "path": relative,
            "sha256": hashlib.sha256(path.read_bytes()).hexdigest(),
            "last_changed_commit": input_commit,
        }

    if drifted:
        print(
            f"Refusing to attest. These inputs changed after {args.report} was generated "
            f"in {report_commit[:12]}, so the files on disk are not what it ran on:",
            file=sys.stderr,
        )
        for item in drifted:
            print(f"  - {item}", file=sys.stderr)
        print(
            "\nRecover them from the report's commit before recording conditions.",
            file=sys.stderr,
        )
        return 1

    out = ROOT / (args.out or f"docs/evaluation/workbench/conditions-{args.label}.json")
    document = {
        "schema_version": "evaluation-conditions-v1",
        "label": args.label,
        "report": args.report,
        "report_commit": report_commit,
        "attestation": (
            "Every input below was last committed at or before the commit that produced the "
            "report, verified with git merge-base --is-ancestor. The digests therefore describe "
            "the data the published numbers were computed over."
        ),
        "inputs": entries,
    }
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text(json.dumps(document, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")

    print(f"Wrote {out.relative_to(ROOT).as_posix()}")
    print(f"  report generated in {report_commit[:12]}; {len(entries)} inputs attested")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
