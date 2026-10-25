"""Exact external-recipe ingredient mapping from reviewed data-engineering aliases only."""

import csv
import re
import unicodedata
from collections import defaultdict
from dataclasses import dataclass
from pathlib import Path


def normalize_alias(value: str) -> str:
    folded = unicodedata.normalize("NFKD", value).casefold()
    return " ".join(re.findall(r"[\w]+", folded, flags=re.UNICODE)).replace("_", " ")


@dataclass(frozen=True)
class IngredientMappingResult:
    status: str
    canonical_id: str | None = None
    confidence: float = 0.0


class ReviewedIngredientMapper:
    """Resolve only unique exact aliases; fuzzy matcher outputs are deliberately not auto-applied."""

    def __init__(self, aliases: dict[str, set[str]]) -> None:
        self.aliases = aliases

    @classmethod
    def from_csv_files(cls, base_aliases: Path, v2_additions: Path) -> "ReviewedIngredientMapper":
        values: dict[str, set[str]] = defaultdict(set)
        with base_aliases.open(encoding="utf-8-sig", newline="") as handle:
            for row in csv.DictReader(handle):
                cls._add(values, row.get("alias", ""), row.get("ingredient_id", ""))
        with v2_additions.open(encoding="utf-8-sig", newline="") as handle:
            for row in csv.DictReader(handle):
                if row.get("action") == "alias":
                    cls._add(values, row.get("alias", ""), row.get("ingredient_id", ""))
        return cls(dict(values))

    @staticmethod
    def _add(values: dict[str, set[str]], alias: str, ingredient_id: str) -> None:
        key = normalize_alias(alias)
        target = ingredient_id.removeprefix("ING_").casefold()
        if key and target:
            values[key].add(target)

    def resolve(self, source_name: str) -> IngredientMappingResult:
        candidates = self.aliases.get(normalize_alias(source_name), set())
        if len(candidates) == 1:
            return IngredientMappingResult("matched", next(iter(candidates)), 1.0)
        if candidates:
            return IngredientMappingResult("ambiguous")
        return IngredientMappingResult("unmatched")
