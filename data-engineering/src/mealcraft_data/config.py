from __future__ import annotations

import csv
from dataclasses import dataclass
from pathlib import Path


@dataclass(frozen=True)
class UnitRule:
    alias: str
    normalized_unit: str
    dimension: str
    multiplier_to_base: float


@dataclass(frozen=True)
class IngredientRule:
    ingredient_id: str
    canonical_name: str
    alias: str
    food_group: str
    allergens: tuple[str, ...]


@dataclass(frozen=True)
class CleaningConfig:
    units: dict[str, UnitRule]
    ingredients: dict[str, IngredientRule]
    preparation_terms: tuple[str, ...]


def load_config(project_root: Path) -> CleaningConfig:
    units: dict[str, UnitRule] = {}
    with (project_root / "config" / "units.csv").open("r", encoding="utf-8-sig", newline="") as handle:
        for row in csv.DictReader(handle):
            alias = row["alias"].casefold().strip().rstrip(".")
            units[alias] = UnitRule(
                alias=alias,
                normalized_unit=row["normalized_unit"],
                dimension=row["dimension"],
                multiplier_to_base=float(row["multiplier_to_base"]),
            )

    ingredients: dict[str, IngredientRule] = {}
    with (project_root / "config" / "ingredient_aliases.csv").open("r", encoding="utf-8-sig", newline="") as handle:
        for row in csv.DictReader(handle):
            alias = row["alias"].casefold().strip()
            ingredients[alias] = IngredientRule(
                ingredient_id=row["ingredient_id"],
                canonical_name=row["canonical_name"],
                alias=alias,
                food_group=row["food_group"],
                allergens=tuple(item.strip() for item in row["allergens"].split(";") if item.strip()),
            )

    prep_lines = (project_root / "config" / "preparation_terms.txt").read_text(encoding="utf-8")
    preparation_terms = tuple(
        sorted(
            (line.strip().casefold() for line in prep_lines.splitlines() if line.strip()),
            key=len,
            reverse=True,
        )
    )
    return CleaningConfig(
        units=units,
        ingredients=ingredients,
        preparation_terms=preparation_terms,
    )
