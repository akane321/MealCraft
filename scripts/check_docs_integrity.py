"""Mechanical checks for the public documentation set.

AGENTS.md states two rules that a reader cannot be relied on to enforce:

  1. mutable state (a `main` SHA, whether a numbered pull request has merged, a
     "last verified" date, current metric values) belongs only to
     `docs/current-status.md` and the generated evaluation reports;
  2. every internal documentation link, and every backtick-quoted repository
     path, must resolve.

Rule 1 exists because a stale "PR #22 is not merged yet" line sits in the first
paragraph a contributor reads and stays wrong forever. Rule 2 exists because a
reading path that points at a moved file silently becomes a shorter reading
path.

Run: `python scripts/check_docs_integrity.py`
"""

from __future__ import annotations

import re
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]

# The only documents allowed to assert mutable state.
DATED_STATE_DOCUMENTS = {
    "docs/current-status.md",
    "docs/evaluation/latest.md",
    "docs/evaluation/workbench/latest.md",
}
# Generated per-release reports record the commit they were built from.
GENERATED_REPORT_PREFIXES = ("data-engineering/data/release/",)
# Documents whose job is to state the rule have to quote the forbidden shapes.
RULE_DEFINING_DOCUMENTS = {
    "AGENTS.md",
    "CONTRIBUTING.md",
    "docs/README.md",
    "docs/memory-bootstrap.md",
}

SCAN_ROOTS = ["docs", "data", "data-engineering", ".github"]
SCAN_FILES = ["README.md", "AGENTS.md", "CONTRIBUTING.md"]

VOLATILE_PATTERNS = {
    "pull request reference": re.compile(r"(?:\bPR\s*#\d+|/pull/\d+)"),
    "commit SHA": re.compile(r"\b[0-9a-f]{40}\b"),
    # A named evaluation metric followed by a value; values live in the generated reports.
    "metric value": re.compile(
        r"(?i)\b(?:exact_case_rate|field_recall|field_precision|expectation_rate"
        r"|failure_case_count|strict_success(?:_rate)?)`?\s*(?:=|:)\s*`?\d"
    ),
    # A claim, not a cross-reference: requires a value after the label.
    "dated verification claim": re.compile(r"(?i)last verified[^.\n]{0,40}:\s*\S"),
}
EXEMPT_LINE = re.compile(r"(?i)(?:must not|never|do not|<number>|YYYY-MM-DD|123)")

LINK_PATTERN = re.compile(r"\[[^\]]*\]\(([^)#]+?)(?:#[^)]*)?\)")
# A backtick-quoted path rooted at a top-level directory, e.g. `docs/x.md`.
REPO_PATH_PATTERN = re.compile(r"`((?:docs|backend|frontend|scripts|data|data-engineering|evaluation)/[\w./-]+)`")
# Generated or local-only output; a quoted path there need not exist in a checkout.
GENERATED_PREFIXES = (
    "data-engineering/data/raw/",
    "data-engineering/data/staging/",
    "data-engineering/data/curated/",
    "data-engineering/data/review/",
    "data-engineering/reports/",
    "frontend/.output/",
    "frontend/node_modules/",
)

REQUIRED_PRODUCT_CONTRACT_SNIPPETS = {
    "docs/architecture.md": (
        "| Worker | Python 3.12 (`python -m app.worker`) |",
        "-> keep the checked week with the exact request",
        "-> offer Plan my week",
    ),
    "docs/development.md": ("They are mocked-API browser acceptance, not a real-stack test.",),
    "README.md": ("docs/evaluation/v3-meal-day-week/dev/latest.md",),
}

FORBIDDEN_STALE_SNIPPETS = {
    "docs/design/planning-engine.md": ("current implementation produces seven persisted main meals",),
    "docs/design/ingredient-hierarchy.md": (
        "being written in three work packages",
        'a household that says "no pork" today still gets bacon',
    ),
    "docs/design/frontend-human-evaluation.md": ("in edge panels\nand overlays",),
    "docs/design/planning-product-path.md": (
        "current-status.md#planning-p1-branch-work",
        "requested dinner dates",
    ),
    "docs/current-status.md": ("| Recipe catalog | 30 validated recipes and 34 normalized ingredients",),
}


def documents() -> list[Path]:
    found: list[Path] = []
    for name in SCAN_FILES:
        path = ROOT / name
        if path.exists():
            found.append(path)
    for root in SCAN_ROOTS:
        found.extend(sorted((ROOT / root).rglob("*.md")))
    return found


def check_volatile_state(errors: list[str]) -> None:
    for path in documents():
        relative = path.relative_to(ROOT).as_posix()
        if relative in DATED_STATE_DOCUMENTS or relative in RULE_DEFINING_DOCUMENTS:
            continue
        if relative.startswith(GENERATED_REPORT_PREFIXES):
            continue
        for number, line in enumerate(path.read_text(encoding="utf-8").splitlines(), 1):
            if EXEMPT_LINE.search(line):
                continue
            for label, pattern in VOLATILE_PATTERNS.items():
                if pattern.search(line):
                    errors.append(
                        f"{relative}:{number} asserts a {label} outside a dated-state "
                        "document. Point at a path plus a decision id (AGENTS.md, "
                        '"One fact, one carrier").'
                    )


def check_links(errors: list[str]) -> None:
    for path in documents():
        relative = path.relative_to(ROOT).as_posix()
        for number, line in enumerate(path.read_text(encoding="utf-8").splitlines(), 1):
            for target in LINK_PATTERN.findall(line):
                target = target.strip()
                if not target or target.startswith(("http://", "https://", "mailto:")):
                    continue
                if (path.parent / target).resolve().exists():
                    continue
                errors.append(f"{relative}:{number} links to a missing path: {target}")
            for target in REPO_PATH_PATTERN.findall(line):
                if any(c in target for c in "<*"):
                    continue
                # data-engineering documents quote paths relative to their own folder.
                bases = [""] + (["data-engineering/"] if relative.startswith("data-engineering/") else [])
                if any((base + target).startswith(GENERATED_PREFIXES) for base in bases):
                    continue
                if not any((ROOT / (base + target).rstrip("/")).exists() for base in bases):
                    errors.append(f"{relative}:{number} names a missing path: {target}")


def check_status_freshness(errors: list[str]) -> None:
    """`docs/current-status.md` must name the commit it was verified against."""
    path = ROOT / "docs" / "current-status.md"
    if not path.exists():
        errors.append("Missing docs/current-status.md")
        return
    text = path.read_text(encoding="utf-8")
    if not re.search(r"Verified remote `main`:\s*`[0-9a-f]{7,40}`", text):
        errors.append(
            "docs/current-status.md must record the verified remote main commit as: Verified remote `main`: `<sha>`"
        )
    if not re.search(r"Last verified public snapshot:\s*20\d\d-\d\d-\d\d", text):
        errors.append("docs/current-status.md must record a Last verified public snapshot date")


def check_product_contract_consistency(errors: list[str]) -> None:
    """Keep demo-facing contracts from regressing to the stale forms found in WP6."""
    for relative, snippets in REQUIRED_PRODUCT_CONTRACT_SNIPPETS.items():
        text = (ROOT / relative).read_text(encoding="utf-8")
        for snippet in snippets:
            if snippet not in text:
                errors.append(f"{relative} is missing the required product-contract text: {snippet}")

    for relative, snippets in FORBIDDEN_STALE_SNIPPETS.items():
        text = (ROOT / relative).read_text(encoding="utf-8")
        for snippet in snippets:
            if snippet in text:
                errors.append(f"{relative} still contains stale product-contract text: {snippet}")

    api_contract = (ROOT / "docs" / "api-contracts.md").read_text(encoding="utf-8")
    endpoint_inventory = api_contract.split("Available endpoints:", 1)[-1].split("\n##", 1)[0]
    for endpoint in (
        "PATCH /api/plans/{plan_id}/meals/{day_index}/{meal_type}",
        "POST /api/plans/{plan_id}/shape/preview",
    ):
        if f"- {endpoint}" not in endpoint_inventory:
            errors.append(f"docs/api-contracts.md endpoint inventory is missing: {endpoint}")

    for path in sorted((ROOT / "docs" / "evaluation").rglob("latest.md")):
        opening = path.read_text(encoding="utf-8").splitlines()[:10]
        if not any(line.startswith("> Scope:") for line in opening):
            errors.append(f"{path.relative_to(ROOT).as_posix()} must identify its scope in its opening lines")


def main() -> int:
    errors: list[str] = []
    check_volatile_state(errors)
    check_links(errors)
    check_status_freshness(errors)
    check_product_contract_consistency(errors)
    if errors:
        print("Documentation integrity check failed:")
        for error in errors:
            print(f"- {error}")
        return 1
    print("Documentation integrity check passed.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
