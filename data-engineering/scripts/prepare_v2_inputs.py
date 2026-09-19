"""Turn the selected v2 candidates into work-packet input items.

    python scripts/prepare_v2_inputs.py recipes       # needs data/staging/v2_candidates.jsonl
    python scripts/prepare_v2_inputs.py ingredients   # also needs the extended alias table (stage 3)

Each writes data/staging/v2_<kind>_items.jsonl; `v2_packet.py build-inputs`
then splits them into parts A, B and C.
"""

from __future__ import annotations

import collections
import json
import re
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
STAGING = ROOT / "data" / "staging"
CANDIDATES = STAGING / "v2_candidates.jsonl"
QUANTIFIED = {"mass", "volume", "count"}

DURATION = re.compile(
    r"(\d+(?:\.\d+)?)(?:\s*(?:to|-|–|or)\s*(\d+(?:\.\d+)?))?\s*(minutes?|mins?|hours?|hrs?)\b", re.IGNORECASE
)


def stated_durations(steps: list[dict]) -> list[str]:
    """Durations written in the steps, as `step N: <text>`, for the enricher to use."""
    found = []
    for step in steps:
        for match in DURATION.finditer(step["text"]):
            found.append(f"step {step['step_number']}: {match.group(0)}")
    return found


def needs_amount(line: dict) -> bool:
    return line.get("quantity_min") is None or line.get("unit_dimension") not in QUANTIFIED


def read_candidates() -> list[dict]:
    return [json.loads(line) for line in CANDIDATES.read_text(encoding="utf-8").splitlines() if line]


def recipes() -> list[dict]:
    items = []
    for record in read_candidates():
        items.append(
            {
                "candidate_id": record["candidate_id"],
                "title": record["title"],
                "servings": record["servings"],
                "ingredients": [
                    {"index": index, "text": line["original_text"], "needs_amount": needs_amount(line)}
                    for index, line in enumerate(record["ingredients"], 1)
                ],
                "steps": [f"{s['step_number']}. {s['text']}" for s in record["instructions"]],
                "stated_durations": stated_durations(record["instructions"]),
                "cuisine_hint": record["triage"]["cuisine"],
            }
        )
    return items


def write(kind: str, items: list[dict]) -> None:
    path = STAGING / f"v2_{kind}_items.jsonl"
    path.write_text(
        "".join(json.dumps(i, ensure_ascii=False, sort_keys=True) + "\n" for i in items), encoding="utf-8", newline="\n"
    )
    counts = collections.Counter(len(i.get("ingredients", [])) for i in items)
    print(
        f"{kind}: {len(items)} items -> {path.relative_to(ROOT)}"
        + (f"; ingredient lines {sum(k * v for k, v in counts.items())}" if kind == "recipes" else "")
    )


def main() -> int:
    kind = sys.argv[1] if len(sys.argv) > 1 else ""
    if kind == "recipes":
        write("recipes", recipes())
        return 0
    raise SystemExit("usage: prepare_v2_inputs.py recipes|ingredients (ingredients comes with stage 3)")


if __name__ == "__main__":
    sys.exit(main())
