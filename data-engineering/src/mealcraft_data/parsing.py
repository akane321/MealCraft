from __future__ import annotations

import re
from dataclasses import asdict, dataclass
from functools import lru_cache

from .config import CleaningConfig
from .constants import INFORMAL_QUANTITY_TERMS, UNICODE_FRACTIONS
from .utils import stable_id

WORD_NUMBERS = {
    "a": 1.0,
    "an": 1.0,
    "one": 1.0,
    "two": 2.0,
    "three": 3.0,
    "four": 4.0,
    "five": 5.0,
    "six": 6.0,
    "seven": 7.0,
    "eight": 8.0,
    "nine": 9.0,
    "ten": 10.0,
    "eleven": 11.0,
    "twelve": 12.0,
}

FRACTION_CHARS = "".join(UNICODE_FRACTIONS)
WORD_NUMBER_PATTERN = "|".join(WORD_NUMBERS)
# Order matters: the hyphenated and spaced mixed-number forms (``2-1/2``,
# ``2 1/2``) must be tried before the bare-integer form so ``2-1/2`` is read as
# two-and-a-half rather than a ``2``-to-``1/2`` range.
NUMBER_TOKEN = (
    rf"(?:\d+\s*-\s*\d+/\d+|\d+\s+\d+/\d+|\d+/\d+"
    rf"|\d+(?:\.\d+)?(?:[{FRACTION_CHARS}])?"
    rf"|[{FRACTION_CHARS}]|(?:{WORD_NUMBER_PATTERN})\b)"
)
MIXED_HYPHEN_RE = re.compile(r"^(\d+)\s*-\s*(\d+)/(\d+)$")
# ``to``/``or`` are only range separators when they stand alone between spaces
# with a number on both sides (QUANTITY_RE only tries this right after the low
# number), otherwise ``4 toasted buns`` misreads as a ``4``-to-``a`` range and
# ``3 or 4 bananas`` never recognizes "or" as meaning "3 to 4".
RANGE_SEPARATOR = r"(?:\s*(?:--?|–|—)\s*|\s+to\s+|\s+or\s+)"
# Matches a quantity followed by a bare, case-significant "T" or "t" token
# (tablespoon vs teaspoon), read from the original text before it is casefolded.
LEADING_T_UNIT_RE = re.compile(r"^\s*[\d./\s-]*\d[\d./\s-]*\s+([Tt])\.?\s+[a-zA-Z]")
QUANTITY_RE = re.compile(
    rf"^\s*(?P<low>{NUMBER_TOKEN})(?:{RANGE_SEPARATOR}(?P<high>{NUMBER_TOKEN}))?"
    rf"(?=\s|[a-zA-Z]|$)",
    flags=re.IGNORECASE,
)


@dataclass(frozen=True)
class ParsedIngredient:
    original_text: str
    quantity_min: float | None
    quantity_max: float | None
    unit_raw: str | None
    unit_normalized: str | None
    unit_dimension: str | None
    ingredient_text: str
    canonical_ingredient_id: str | None
    canonical_name: str | None
    preparation: list[str]
    optional: bool
    allergens: list[str]
    normalization_status: str
    confidence: float
    source_ner_match: bool | None
    review_reasons: list[str]

    def to_dict(self) -> dict[str, object]:
        return asdict(self)


def _parse_number(token: str) -> float:
    token = token.casefold().strip()
    if token in WORD_NUMBERS:
        return WORD_NUMBERS[token]

    unicode_value = 0.0
    for char, value in UNICODE_FRACTIONS.items():
        if char in token:
            unicode_value += value
            token = token.replace(char, "")
    token = token.strip()
    if not token:
        return unicode_value

    mixed_hyphen = MIXED_HYPHEN_RE.match(token)
    if mixed_hyphen:
        whole, numerator, denominator = mixed_hyphen.groups()
        return (
            float(whole)
            + float(numerator) / float(denominator)
            + unicode_value
        )
    if " " in token and "/" in token:
        whole, fraction = token.split(None, 1)
        numerator, denominator = fraction.split("/", 1)
        return float(whole) + float(numerator) / float(denominator) + unicode_value
    if "/" in token:
        numerator, denominator = token.split("/", 1)
        return float(numerator) / float(denominator) + unicode_value
    return float(token) + unicode_value


def _singularize(word: str) -> str:
    """Naive English depluralisation for a single word."""
    if word.endswith("ies") and len(word) > 4:
        return word[:-3] + "y"
    if word.endswith("oes") and len(word) > 4:
        return word[:-2]
    if word.endswith(("ches", "shes", "sses", "xes", "zes")) and len(word) > 4:
        return word[:-2]
    if word.endswith("s") and not word.endswith(("ss", "us", "is")) and len(word) > 3:
        return word[:-1]
    return word


def _lookup_ingredient(text: str, config: CleaningConfig):
    """Exact alias match first, then a hyphen- and plural-normalised retry."""
    rule = config.ingredients.get(text)
    if rule:
        return rule
    variants = {text.replace("-", " "), text.replace("-", "")}
    words = text.split()
    if words:
        variants.add(" ".join(words[:-1] + [_singularize(words[-1])]))
        variants.add(" ".join(_singularize(w) for w in words))
    for variant in variants:
        variant = re.sub(r"\s+", " ", variant).strip()
        if variant and variant != text:
            rule = config.ingredients.get(variant)
            if rule:
                return rule
    return None


def _clean_text(value: str) -> str:
    value = value.casefold().replace("–", "-").replace("—", "-")
    value = re.sub(r"\s+", " ", value)
    # Collapse punctuation left behind when a hyphenated modifier is stripped
    # ("extra-virgin olive oil" -> " - olive oil").
    value = re.sub(r"\s+-\s+", " ", value)
    return value.strip(" \t\r\n,.;:-#*_/")


@lru_cache(maxsize=2048)
def _phrase_pattern(phrase: str) -> re.Pattern[str]:
    return re.compile(rf"(?<!\w){re.escape(phrase)}(?!\w)", flags=re.IGNORECASE)


def _remove_phrase(value: str, phrase: str) -> tuple[str, bool]:
    updated, count = _phrase_pattern(phrase).subn(" ", value)
    return re.sub(r"\s+", " ", updated).strip(" ,"), bool(count)


def parse_ingredient(
    original_text: str,
    config: CleaningConfig,
    source_ner: list[str] | None = None,
) -> ParsedIngredient:
    original = original_text.strip()
    # "T" (tablespoon) vs "t" (teaspoon) is a real 3x quantity difference that
    # _clean_text's casefold would erase, so read it off the original casing
    # before anything downstream lowercases the string.
    case_sensitive_t_unit: str | None = None
    leading_t_match = LEADING_T_UNIT_RE.match(original)
    if leading_t_match:
        case_sensitive_t_unit = "tbsp" if leading_t_match.group(1) == "T" else "tsp"
    text = _clean_text(original)
    review_reasons: list[str] = []
    preparation: list[str] = []

    if not text:
        return ParsedIngredient(
            original_text=original,
            quantity_min=None,
            quantity_max=None,
            unit_raw=None,
            unit_normalized=None,
            unit_dimension=None,
            ingredient_text="",
            canonical_ingredient_id=None,
            canonical_name=None,
            preparation=[],
            optional=False,
            allergens=[],
            normalization_status="unresolved",
            confidence=0.0,
            source_ner_match=None,
            review_reasons=["empty_ingredient"],
        )

    optional = "optional" in text
    quantity_min: float | None = None
    quantity_max: float | None = None
    quantity_match = QUANTITY_RE.match(text)
    remainder = text
    if quantity_match:
        quantity_min = _parse_number(quantity_match.group("low"))
        quantity_max = (
            _parse_number(quantity_match.group("high"))
            if quantity_match.group("high")
            else quantity_min
        )
        # Some recipes write a range high-to-low ("1/4 to 1/8 tsp nutmeg"). The
        # two numbers are still the range's bounds; swap them so min <= max
        # rather than keeping textual left-to-right order.
        if quantity_max < quantity_min:
            quantity_min, quantity_max = quantity_max, quantity_min
        remainder = text[quantity_match.end() :].lstrip(" .")
        if quantity_min != quantity_max:
            review_reasons.append("quantity_range")
    else:
        review_reasons.append("missing_quantity")

    # Pull parenthetical size notes ("1 (8 oz.) can tomatoes") out before unit
    # detection so the real unit ("can") is the first token that remains.
    parenthetical_notes = re.findall(r"\(([^)]*)\)", remainder)
    if parenthetical_notes:
        preparation.extend(note.strip() for note in parenthetical_notes if note.strip())
        remainder = re.sub(r"\s*\([^)]*\)\s*", " ", remainder).strip()

    unit_raw: str | None = None
    unit_normalized: str | None = None
    unit_dimension: str | None = None
    first_word_match = re.match(r"^([a-zA-Z]+)\.?\b", remainder)
    if first_word_match:
        candidate = first_word_match.group(1).casefold()
        if candidate == "t" and case_sensitive_t_unit:
            unit_rule = config.units.get(case_sensitive_t_unit)
        else:
            unit_rule = config.units.get(candidate)
        if unit_rule:
            unit_raw = first_word_match.group(0).strip()
            unit_normalized = unit_rule.normalized_unit
            unit_dimension = unit_rule.dimension
            remainder = remainder[first_word_match.end() :].lstrip(" ,.")
        elif quantity_min is not None:
            # A bare number in front of a food word is a count: "2 eggs",
            # "1 onion". This is the conventional reading, not a missing unit,
            # so it is recorded as a count rather than flagged for review.
            unit_normalized = "piece"
            unit_dimension = "count"
    elif quantity_min is not None:
        review_reasons.append("unit_missing_or_unknown")

    if remainder.startswith("of "):
        remainder = remainder[3:]

    # A comma-separated ingredient string mixes the food name with preparation
    # notes in either order ("flour, sifted" but also "diced, cooked chicken").
    # Strip preparation/informal terms from every segment first, then take the
    # first segment that still has a food name; the rest become preparation.
    segments = [segment.strip() for segment in remainder.split(",") if segment.strip()]
    if not segments:
        segments = [remainder.strip()]

    reduced: list[str] = []
    for segment in segments:
        for phrase in INFORMAL_QUANTITY_TERMS:
            segment, found = _remove_phrase(segment, phrase)
            if found:
                preparation.append(phrase)
                review_reasons.append("informal_quantity")
        for term in config.preparation_terms:
            segment, found = _remove_phrase(segment, term)
            if found:
                preparation.append(term)
        segment = _clean_text(segment)
        segment = re.sub(r"\s+and\s*$", "", segment).strip()
        # A dangling "or" left over once its partner word is stripped is noise,
        # not a real alternative: "salt or to taste" loses "to taste" as an
        # informal-quantity phrase and must not keep the "or" it leaves behind.
        segment = re.sub(r"^\s*or\s+|\s+or\s*$", "", segment, flags=re.IGNORECASE).strip()
        if segment.casefold() == "or":
            segment = ""
        reduced.append(segment)

    ingredient_text = ""
    for index, segment in enumerate(reduced):
        if segment:
            ingredient_text = segment
            preparation.extend(other for j, other in enumerate(reduced) if j != index and other)
            break

    preparation = sorted(set(preparation))

    # Check every stripped segment, not just the one picked as ingredient_text:
    # "beef, pork or chicken" must still be flagged even though the alternative
    # ("pork or chicken") ends up in a dropped/preparation segment. Checking the
    # *stripped* segments (rather than the raw pre-strip remainder) avoids
    # false positives from "or" inside a phrase already resolved elsewhere -
    # "salt or to taste" (an informal-quantity phrase) and "fresh or thawed,
    # frozen broccoli" (a prep-word idiom) both reduce to no "or" surviving.
    if any(re.search(r"\bor\b", segment, flags=re.IGNORECASE) for segment in reduced):
        review_reasons.append("ambiguous_alternative")

    rule = _lookup_ingredient(ingredient_text, config)
    if rule:
        status = "mapped"
        canonical_id = rule.ingredient_id
        canonical_name = rule.canonical_name
        allergens = list(rule.allergens)
        confidence = 0.96
        if quantity_min is None:
            confidence -= 0.08
        if unit_normalized is None:
            confidence -= 0.04
        if "ambiguous_alternative" in review_reasons:
            confidence -= 0.25
    elif ingredient_text:
        status = "candidate"
        canonical_id = stable_id("CAND", ingredient_text, length=12)
        canonical_name = ingredient_text
        allergens = []
        confidence = 0.5
        review_reasons.append("unmapped_ingredient")
    else:
        status = "unresolved"
        canonical_id = None
        canonical_name = None
        allergens = []
        confidence = 0.0
        review_reasons.append("empty_after_parsing")

    source_ner_match: bool | None = None
    if source_ner:
        normalized_ner = {_clean_text(item) for item in source_ner}
        source_ner_match = any(
            ingredient_text == item
            or ingredient_text in item
            or item in ingredient_text
            for item in normalized_ner
            if item
        )
        if not source_ner_match:
            review_reasons.append("ner_mismatch")

    return ParsedIngredient(
        original_text=original,
        quantity_min=quantity_min,
        quantity_max=quantity_max,
        unit_raw=unit_raw,
        unit_normalized=unit_normalized,
        unit_dimension=unit_dimension,
        ingredient_text=ingredient_text,
        canonical_ingredient_id=canonical_id,
        canonical_name=canonical_name,
        preparation=preparation,
        optional=optional,
        allergens=allergens,
        normalization_status=status,
        confidence=max(0.0, round(confidence, 3)),
        source_ner_match=source_ner_match,
        review_reasons=sorted(set(review_reasons)),
    )

