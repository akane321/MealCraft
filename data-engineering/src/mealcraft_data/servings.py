"""Conservative servings extraction from free-text cooking instructions.

RecipeNLG has no dedicated servings field; a serving count only ever appears
inline in the instruction text ("Serves 4.", "Makes 8 servings."). Most
"serve"/"make(s)" mentions are NOT a serving count - the dominant failure
modes found while building this module:

    "If desired, serve over rice. Serves 4."   -> only the second half counts
    "Add water to make 2 cups."                -> a volume, not a serving count
    "Makes about 24 pieces."                    -> a yield of pieces, not servings
    "Serves 10 to 12."                          -> a range, not one exact value

Loosening the match to raise the extraction rate reproduces exactly the
failure this module exists to avoid: a wrong servings count silently rescales
every ingredient quantity and every nutrition value downstream, with no error
raised. So a value is only ever returned when the source is explicit, and a
range is handled by taking its lower bound rather than discarded, because the
error that introduces is one-directional and safe for a diet-planning app:

  - scaling ingredients from an undercount yields a bit more food, not less;
  - dividing total nutrition by an undercount overstates calories/macros per
    serving, which is the conservative direction for someone tracking a limit.

The distinction is preserved rather than hidden: callers get `basis` alongside
the value, so a range-derived estimate is never silently equated with a
recipe that states an exact count.
"""

from __future__ import annotations

import re
from typing import NamedTuple

_RANGE_SEP = r"(?:to|-|–|—|or)"

_SERVES_RANGE_RE = re.compile(
    rf"\bserves?\s+(\d+)\s*{_RANGE_SEP}\s*(\d+)\b", re.IGNORECASE
)
_SERVES_RE = re.compile(r"\bserves?\s+(\d+)\b", re.IGNORECASE)
_MAKES_RANGE_RE = re.compile(
    rf"\b(?:makes|yields?)\s*:?\s+(?:about|approximately)?\s*(\d+)\s*{_RANGE_SEP}\s*(\d+)"
    r"\s*(?:servings?|portions?)\b",
    re.IGNORECASE,
)
_MAKES_RE = re.compile(
    r"\b(?:makes|yields?)\s*:?\s+(?:about|approximately)?\s*(\d+)\s*(?:servings?|portions?)\b",
    re.IGNORECASE,
)
# A number immediately followed by one of these is a quantity/yield/duration,
# not a serving count, even though it matched "serves"/"makes N".
_NON_SERVING_UNIT_RE = re.compile(
    r"^\s*(dozen|cups?|pieces?|cookies?|tablespoons?|teaspoons?|quarts?|pints?|"
    r"gallons?|bars?|balls?|muffins?|rolls?|biscuits?|slices?|minutes?|hours?|"
    r"inch(?:es)?|degrees?|calories?|pounds?|ounces?|grams?)\b",
    re.IGNORECASE,
)

_MAX_PLAUSIBLE_SERVINGS = 500


class ServingsResult(NamedTuple):
    value: int
    basis: str  # "stated_exact" | "range_lower_bound"


def _plausible(value: int) -> bool:
    return 0 < value <= _MAX_PLAUSIBLE_SERVINGS


def extract_servings(instruction_text: str) -> ServingsResult | None:
    """Return the servings count the source supports, or None when nothing
    conservatively certain is present. A range ("Serves 10 to 12") yields its
    lower bound with basis="range_lower_bound"; an exact statement
    ("Serves 8.") yields basis="stated_exact". Never a guess beyond that."""
    range_match = _SERVES_RANGE_RE.search(instruction_text) or _MAKES_RANGE_RE.search(
        instruction_text
    )
    if range_match:
        low, high = int(range_match.group(1)), int(range_match.group(2))
        if low <= high and _plausible(low) and _plausible(high):
            return ServingsResult(low, "range_lower_bound")
        return None

    match = _SERVES_RE.search(instruction_text) or _MAKES_RE.search(instruction_text)
    if not match:
        return None
    tail = instruction_text[match.end() : match.end() + 15]
    if _NON_SERVING_UNIT_RE.match(tail):
        return None
    value = int(match.group(1))
    if not _plausible(value):
        return None
    return ServingsResult(value, "stated_exact")
