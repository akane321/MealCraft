"""Mechanical checks for the public documentation set.

AGENTS.md states two rules that a reader cannot be relied on to enforce:

  1. mutable state (a `main` SHA, whether a numbered pull request has merged, a
     "last verified" date, current metric values) belongs only to
     `docs/current-status.md` and the generated evaluation reports;
  2. every internal documentation link must resolve.

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
# Documents whose job is to state the rule have to quote the forbidden shapes.
RULE_DEFINING_DOCUMENTS = {
    "AGENTS.md",
    "CONTRIBUTING.md",
    "docs/README.md",
    "docs/memory-bootstrap.md",
}

SCAN_ROOTS = ["docs", "data"]
SCAN_FILES = ["README.md", "AGENTS.md", "CONTRIBUTING.md"]

VOLATILE_PATTERNS = {
    "pull request reference": re.compile(r"(?:\bPR\s*#\d+|/pull/\d+)"),
    "commit SHA": re.compile(r"\b[0-9a-f]{40}\b"),
    # A claim, not a cross-reference: requires a value after the label.
    "dated verification claim": re.compile(r"(?i)last verified[^.\n]{0,40}:\s*\S"),
}
EXEMPT_LINE = re.compile(r"(?i)(?:must not|never|do not|<number>|YYYY-MM-DD|123)")

LINK_PATTERN = re.compile(r"\[[^\]]*\]\(([^)#]+?)(?:#[^)]*)?\)")


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


def main() -> int:
    errors: list[str] = []
    check_volatile_state(errors)
    check_links(errors)
    check_status_freshness(errors)
    if errors:
        print("Documentation integrity check failed:")
        for error in errors:
            print(f"- {error}")
        return 1
    print("Documentation integrity check passed.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
