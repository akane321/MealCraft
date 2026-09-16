from __future__ import annotations

import ast
import csv
import json
import random
import sys
from pathlib import Path
from typing import Any, Iterator


def parse_list_cell(value: str | None) -> list[str]:
    if not value:
        return []
    stripped = value.strip()
    for parser in (json.loads, ast.literal_eval):
        try:
            parsed = parser(stripped)
        except (ValueError, SyntaxError, json.JSONDecodeError):
            continue
        if isinstance(parsed, (list, tuple)):
            return [str(item).strip() for item in parsed]
    return [part.strip() for part in stripped.split("|") if part.strip()]


def iter_recipenlg(path: Path, source_filter: str | None = None) -> Iterator[dict[str, Any]]:
    csv.field_size_limit(min(sys.maxsize, 10_000_000))
    with path.open("r", encoding="utf-8-sig", newline="") as handle:
        reader = csv.DictReader(handle)
        required = {"title", "ingredients", "directions", "link", "source"}
        missing = required.difference(reader.fieldnames or [])
        if missing:
            raise ValueError(f"RecipeNLG CSV is missing columns: {sorted(missing)}")

        for row_number, row in enumerate(reader, start=2):
            source = (row.get("source") or "").strip()
            if source_filter and source.casefold() != source_filter.casefold():
                continue
            yield {
                "row_number": row_number,
                "title": (row.get("title") or "").strip(),
                "ingredients": parse_list_cell(row.get("ingredients")),
                "directions": parse_list_cell(row.get("directions")),
                "link": (row.get("link") or "").strip(),
                "source": source,
                "ner": parse_list_cell(row.get("NER") or row.get("ner")),
            }


def reservoir_sample(
    rows: Iterator[dict[str, Any]], sample_size: int, seed: int
) -> tuple[list[dict[str, Any]], int]:
    if sample_size <= 0:
        raise ValueError("sample_size must be positive")
    rng = random.Random(seed)
    sample: list[dict[str, Any]] = []
    seen = 0
    for seen, row in enumerate(rows, start=1):
        if len(sample) < sample_size:
            sample.append(row)
            continue
        replacement = rng.randint(1, seen)
        if replacement <= sample_size:
            sample[replacement - 1] = row
    return sample, seen
