"""Write scripts/build_nutrition_mapping.py's output back onto the ingredient
catalog: `fdc_id` is only set for `status == "mapped"` rows (the ones with
recorded evidence and no known-bad qualifier), and every row that has a
nutrition_mapping result at all -- mapped, needs_review, or unresolved --
gets the full evidence record attached, per ADR-0024 section 1's "record why,
not just what" requirement. Candidate (CAND_*) ingredients were never in
scope for Task B and are left untouched.

Streams the (potentially large) ingredients.jsonl line by line rather than
loading it into memory, matching this project's established pattern
(run_full_dataset.py, cut_release.py).
"""

from __future__ import annotations

import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
MAPPING_JSON = ROOT / "data" / "enrichment" / "nutrition_mapping.json"


def main() -> None:
    if len(sys.argv) != 3:
        print("usage: apply_nutrition_mapping.py <in_ingredients.jsonl> <out_ingredients.jsonl>", file=sys.stderr)
        raise SystemExit(2)
    in_path, out_path = Path(sys.argv[1]), Path(sys.argv[2])

    mapping = json.loads(MAPPING_JSON.read_text(encoding="utf-8"))

    counts = {"fdc_id_set": 0, "evidence_attached": 0, "untouched": 0, "total": 0}
    with in_path.open(encoding="utf-8") as fin, out_path.open("w", encoding="utf-8") as fout:
        for line in fin:
            record = json.loads(line)
            counts["total"] += 1
            entry = mapping.get(record["ingredient_id"])
            if entry is None:
                counts["untouched"] += 1
                fout.write(line if line.endswith("\n") else line + "\n")
                continue

            record["nutrition_mapping"] = entry
            if entry.get("status") == "mapped":
                record["fdc_id"] = entry["fdc_id"]
                counts["fdc_id_set"] += 1
            counts["evidence_attached"] += 1
            fout.write(json.dumps(record, ensure_ascii=False) + "\n")

    print(json.dumps(counts, indent=2))


if __name__ == "__main__":
    main()
