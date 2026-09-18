"""Split the (large) RecipeNLG CSV into fixed-size, Gathered-only chunks.

The full pipeline holds every recipe it processes in memory at once, which is
fine up to ~300,000 rows on a 16GB machine but crashes (MemoryError) on the
full 1,643,098-row Gathered set. Splitting the input lets the existing,
already-validated pipeline run unmodified on each chunk; run_full_dataset.py
then merges the per-chunk outputs with a streaming pass that never holds more
than one chunk's worth of data in memory.

Run from the project root:

    python scripts/split_recipenlg.py --chunk-size 250000
"""

from __future__ import annotations

import argparse
import csv
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--input", type=Path, default=ROOT / "data/raw/recipenlg/full_dataset.csv")
    parser.add_argument("--out-dir", type=Path, default=ROOT / "data/raw/recipenlg/chunks")
    parser.add_argument("--chunk-size", type=int, default=250_000)
    parser.add_argument("--source-filter", default="Gathered")
    args = parser.parse_args()

    csv.field_size_limit(min(sys.maxsize, 10_000_000))
    args.out_dir.mkdir(parents=True, exist_ok=True)
    for old in args.out_dir.glob("gathered_chunk_*.csv"):
        old.unlink()

    chunk_index = 0
    row_in_chunk = 0
    total = 0
    writer = None
    out_handle = None
    with args.input.open("r", encoding="utf-8-sig", newline="") as handle:
        reader = csv.DictReader(handle)
        fieldnames = reader.fieldnames
        for row in reader:
            if args.source_filter and (row.get("source") or "").strip() != args.source_filter:
                continue
            if row_in_chunk == 0:
                if out_handle:
                    out_handle.close()
                chunk_path = args.out_dir / f"gathered_chunk_{chunk_index:02d}.csv"
                out_handle = chunk_path.open("w", encoding="utf-8", newline="")
                writer = csv.DictWriter(out_handle, fieldnames=fieldnames)
                writer.writeheader()
                chunk_index += 1
            writer.writerow(row)
            row_in_chunk += 1
            total += 1
            if row_in_chunk >= args.chunk_size:
                row_in_chunk = 0
    if out_handle:
        out_handle.close()

    print(
        f"wrote {chunk_index} chunks, {total} '{args.source_filter}' rows total, "
        f"~{args.chunk_size} rows/chunk -> {args.out_dir}"
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
