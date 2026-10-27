"""Aggregate-only report for the Sprint 2 held-out run (ADR-0074, ADR-0092).

It takes one outcome per (system, run, case) and returns counts and rates by category, language and source. A
case reference is used only to check that every system and run saw the same cases with the same void flag; it is
never written to the output. No question text, gold or provenance is accepted: unknown fields are rejected.
"""

from __future__ import annotations

import json
from collections import defaultdict
from collections.abc import Iterable
from typing import Literal, get_args

from pydantic import BaseModel, ConfigDict, Field, field_validator

Category = Literal["planning", "intent", "multi_turn", "adversarial"]
Language = Literal["zh", "en"]
Source = Literal["forum", "authored"]
Status = Literal["success", "failure", "timeout", "error", "missing"]
STATUSES = ("success", "failure", "timeout", "error", "missing")


class CaseOutcome(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)

    case_ref: str = Field(min_length=1)  # opaque, checked for consistency, never reported
    system_id: str = Field(min_length=1)
    run: int = Field(ge=1)
    category: Category
    language: Language
    source: Source
    status: Status
    voided: bool = False


class ExpectedManifest(BaseModel):
    """Aggregate counts the sealed side expects, so an omission shared by every system and run is caught.

    Counts only: no case reference or text. `cells` maps "category|language|source" to the declared number of cases in
    it, voided ones included; `voided` is the declared number of voided cases in the whole set.
    """

    model_config = ConfigDict(extra="forbid", frozen=True)

    systems: list[str] = Field(min_length=1)
    runs: int = Field(ge=1)
    cells: dict[str, int] = Field(min_length=1)
    voided: int = Field(ge=0)

    @field_validator("cells")
    @classmethod
    def _cells(cls, value: dict[str, int]) -> dict[str, int]:
        categories, languages, sources = (set(get_args(t)) for t in (Category, Language, Source))
        for key, count in value.items():
            parts = key.split("|")
            if len(parts) != 3 or parts[0] not in categories or parts[1] not in languages or parts[2] not in sources:
                raise ValueError("a cell is written category|language|source with the known labels")
            if count < 1:
                raise ValueError("a cell holds at least one case")
        return value


def _counts(rows: list[CaseOutcome]) -> dict:
    live = [r for r in rows if not r.voided]
    counts = {f"{s}_n": sum(r.status == s for r in live) for s in STATUSES}
    return {
        "declared_n": len(rows),
        "voided_n": len(rows) - len(live),
        "remaining_n": len(live),
        **counts,
    }


def _mean(values: list[int]) -> int | float:
    mean = sum(values) / len(values)
    return int(mean) if mean == int(mean) else round(mean, 6)


def _summary(rows_by_run: dict[int, list[CaseOutcome]]) -> dict:
    """Per-run counts, with status counts averaged over runs. Timeouts, errors and missing outputs stay in the
    denominator. Declared, voided and remaining counts are the same in every run (checked in _validate)."""
    per_run = [_counts(rows_by_run[run]) for run in sorted(rows_by_run)]
    rates = [c["success_n"] / c["remaining_n"] if c["remaining_n"] else None for c in per_run]
    known = [r for r in rates if r is not None]
    first = per_run[0]
    return {
        "declared_n": first["declared_n"],
        "voided_n": first["voided_n"],
        "remaining_n": first["remaining_n"],
        **{f"{s}_n": _mean([c[f"{s}_n"] for c in per_run]) for s in STATUSES},
        "runs": len(per_run),
        "per_run_success_rate": [None if r is None else round(r, 6) for r in rates],
        "success_rate": round(sum(known) / len(known), 6) if known and len(known) == len(rates) else None,
    }


def _validate(records: list[CaseOutcome]) -> None:
    seen: set[tuple[str, int, str]] = set()
    labels: dict[str, tuple[str, str, str]] = {}
    voids: dict[str, bool] = {}
    cases: dict[tuple[str, int], set[str]] = defaultdict(set)
    for r in records:
        key = (r.system_id, r.run, r.case_ref)
        if key in seen:
            raise ValueError("duplicate record for one system, run and case")
        seen.add(key)
        if labels.setdefault(r.case_ref, (r.category, r.language, r.source)) != (r.category, r.language, r.source):
            raise ValueError("a case carries different labels in different records")
        if voids.setdefault(r.case_ref, r.voided) != r.voided:
            raise ValueError("void flags differ for one case: exclusions must be identical for every system and run")
        cases[(r.system_id, r.run)].add(r.case_ref)
    if len({frozenset(v) for v in cases.values()}) > 1:
        raise ValueError("every system and run must cover the same cases; use status 'missing' for no output")


def _check_manifest(records: list[CaseOutcome], expected: ExpectedManifest) -> None:
    if {r.system_id for r in records} != set(expected.systems):
        raise ValueError("the systems in the records differ from the expected systems")
    for system_id in expected.systems:
        if {r.run for r in records if r.system_id == system_id} != set(range(1, expected.runs + 1)):
            raise ValueError("the runs of a system differ from the expected runs")
    cells: dict[str, set[str]] = defaultdict(set)
    voided: set[str] = set()
    for r in records:
        cells[f"{r.category}|{r.language}|{r.source}"].add(r.case_ref)
        if r.voided:
            voided.add(r.case_ref)
    if {k: len(v) for k, v in cells.items()} != expected.cells:
        raise ValueError("the cells in the records differ from the expected cells")
    if len(voided) != expected.voided:
        raise ValueError("the number of voided cases differs from the expected number")


def _withhold_small(system: dict, minimum: int) -> None:
    """Withhold what could identify a question (ADR-0100 item 5, proposed).

    A cell with fewer than `minimum` remaining cases hides its whole category's cell breakdown: the other cells of that
    category would otherwise let a reader subtract the small cell from the category total. A total under the minimum
    shows no figures. This lowers the risk of identifying a question; it is not a proof that none is possible.
    """
    withheld = {}
    for key, summary in system["cells"].items():
        if summary["remaining_n"] < minimum:
            withheld[key.split("|")[0]] = f"a cell has fewer than {minimum} remaining cases"
    system["cells"] = {key: value for key, value in system["cells"].items() if key.split("|")[0] not in withheld}
    for part in ("by_category", "by_language", "by_source"):
        for name, summary in system[part].items():
            if summary["remaining_n"] < minimum:
                system[part][name] = {"withheld": f"fewer than {minimum} remaining cases"}
    system["withheld_categories"] = dict(sorted(withheld.items()))


def aggregate(
    records: Iterable[CaseOutcome], expected: ExpectedManifest | None = None, *, min_cell_n: int | None = None
) -> dict:
    if min_cell_n is not None and (isinstance(min_cell_n, bool) or not isinstance(min_cell_n, int) or min_cell_n < 1):
        raise ValueError("the minimum cell size is a positive whole number")
    records = list(records)
    if not records:
        raise ValueError("no outcomes")
    _validate(records)
    if expected is not None:
        _check_manifest(records, expected)
    by_system: dict[str, dict[int, list[CaseOutcome]]] = defaultdict(lambda: defaultdict(list))
    for r in records:
        by_system[r.system_id][r.run].append(r)

    def group(runs: dict[int, list[CaseOutcome]], pick) -> dict[str, dict]:
        names = sorted({pick(r) for rows in runs.values() for r in rows})
        return {
            name: _summary({run: [r for r in rows if pick(r) == name] for run, rows in runs.items()}) for name in names
        }

    systems = {}
    for system_id in sorted(by_system):
        runs = by_system[system_id]
        systems[system_id] = {
            "overall": _summary(runs),
            "by_category": group(runs, lambda r: r.category),
            "by_language": group(runs, lambda r: r.language),
            "by_source": group(runs, lambda r: r.source),
            "cells": group(runs, lambda r: f"{r.category}|{r.language}|{r.source}"),
        }
        if min_cell_n is not None:
            _withhold_small(systems[system_id], min_cell_n)
    return {
        "note": "Counts only. Timeouts, errors and missing outputs stay in the denominator and are never successes.",
        "systems": systems,
    }


def render(report: dict) -> str:
    return json.dumps(report, ensure_ascii=False, indent=2, sort_keys=True, allow_nan=False) + "\n"
