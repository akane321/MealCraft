"""Task B (enrichment-work-package.md): map each canonical ingredient to a
USDA FoodData Central food, with recorded evidence, per ADR-0024 section 1 --
a ranked candidate list is not an accuracy score, so this records why the
chosen candidate beat the others, not just its id.

Priority order (tier 1 of the work package's four-layer table): try
Foundation Foods first (curated, highest quality), then SR Legacy, then
FNDDS -- stop at the first tier with any candidate, since a later tier is
never preferred over an earlier one once a candidate exists.

Ranking within a tier: every candidate whose *own* token set is a superset
of the canonical ingredient name's tokens is eligible (same matching logic
used for the earlier coverage measurement). Candidates are ranked by how few
*extra* descriptive tokens they carry beyond the name -- "chicken breast"
should prefer "Chicken, breast, raw" (2 extra tokens: raw + implied) over
"Chicken, breast, meat only, cooked, roasted" (far more qualifiers the
canonical name never asked for). Ties break alphabetically for
determinism, not by any hidden randomness.

Confidence is a direct function of the extra-token count -- 0 extra tokens
scores 0.95, decaying by 0.08 per extra token, floored at 0.4. This is a
declared, reviewable formula, not a per-item guess, and the floor value
itself is the confidence-threshold decision enrichment-work-package.md
section 5 delegates to this pipeline: entries below CONFIDENCE_FLOOR are
still recorded but flagged `needs_review`, rather than silently accepted.

"X or Y" composite canonicals (e.g. "butter or margarine") are routed
directly to `unresolved` with reason `or_composite` -- picking either half
of an explicit alternative would misrepresent what the source recipe
actually used, and the work package's own priority table says composites
should go through the compute-from-components layer, not a single lookup.
"""
from __future__ import annotations

import csv
import json
import re
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
ALIASES_CSV = ROOT / "config" / "ingredient_aliases.csv"
OUT_JSON = ROOT / "data" / "enrichment" / "nutrition_mapping.json"

TIERS = [
    (
        "fdc",
        "foundation",
        ROOT
        / "data/reference/downloads/usda-foundation-2026-04-30"
        / "FoodData_Central_foundation_food_csv_2026-04-30/food.csv",
        "foundation_food",
    ),
    (
        "fdc",
        "sr_legacy",
        ROOT
        / "data/reference/downloads/usda-sr-legacy-2018-04"
        / "FoodData_Central_sr_legacy_food_csv_2018-04/food.csv",
        "sr_legacy_food",
    ),
    (
        "fdc",
        "fndds",
        ROOT
        / "data/reference/downloads/usda-fndds-2024-10-31"
        / "FoodData_Central_survey_food_csv_2024-10-31/food.csv",
        "survey_fndds_food",
    ),
]

STOP = {"and", "or", "of", "the", "a", "an", "style", "plain", "fresh"}

# Extra descriptor words that represent a normal prep/cultivar variation of
# the SAME food (so are safe to auto-accept) rather than a different product
# category. USDA's raw-commodity naming is verbose ("Peaches, yellow, raw")
# while its prepared-dish naming is terse ("Pie, peach"), so "fewest extra
# words" alone systematically favors pies/muffins/bagels/lunchmeat/meatless
# substitutes over the plain ingredient -- this whitelist is what actually
# tells them apart. A candidate whose extra words are not all in this list
# is never auto-mapped, no matter how low its extra-word count is.
BENIGN_QUALIFIERS = {
    "raw", "dried", "ground", "whole", "table", "iodized",
    "seedless", "seeded", "skin", "stalk", "bulb", "seed", "seeds",
    "peeled", "unpeeled", "shelled", "husked", "dehusked", "cooked",
    "boiled", "drained", "canned", "frozen", "light", "extra",
    "green", "red", "yellow", "white", "black", "brown", "salted", "unsalted",
    "stick", "root", "leaf", "leaves", "powder", "powdered", "flake", "flakes",
}
CONFIDENCE_FLOOR = 0.4


def singularize(word: str) -> str:
    if word.endswith("ies") and len(word) > 4:
        return word[:-3] + "y"
    if word.endswith("oes") and len(word) > 4:
        return word[:-2]
    if word.endswith("s") and not word.endswith(("ss", "us")) and len(word) > 3:
        return word[:-1]
    return word


def tokens(text: str) -> frozenset[str]:
    return frozenset(
        singularize(w) for w in re.findall(r"[a-z]+", text.lower()) if w not in STOP and len(w) > 2
    )


def load_tier(path: Path, want_type: str) -> list[tuple[int, str, frozenset[str]]]:
    if not path.is_file():
        return []
    out = []
    with path.open(encoding="utf-8") as fh:
        for row in csv.DictReader(fh):
            if row["data_type"] != want_type:
                continue
            desc = row["description"]
            out.append((int(row["fdc_id"]), desc, tokens(desc)))
    return out


def head_word(description: str) -> str:
    """USDA descriptions are "HeadNoun, qualifier, qualifier..." -- the word
    before the first comma is what the food actually *is*."""
    first_segment = description.split(",", 1)[0]
    words = re.findall(r"[a-z]+", first_segment.lower())
    return singularize(words[0]) if words else ""


def rank_candidates(
    name_tokens: frozenset[str],
    candidates: list[tuple[int, str, frozenset[str]]],
    other_ingredient_names: frozenset[str],
):
    eligible = []
    for fdc_id, desc, desc_tokens in candidates:
        if not (name_tokens <= desc_tokens):
            continue
        head = head_word(desc)
        # A description headed by a DIFFERENT canonical ingredient's own name
        # ("Almond butter, creamy" for target "butter") is a different food
        # wearing the target's word as a qualifier, not the target itself --
        # reject it rather than let token-subset matching alone accept it.
        if head and head in other_ingredient_names and head not in name_tokens:
            continue
        extra = desc_tokens - name_tokens
        non_benign_count = len(extra - BENIGN_QUALIFIERS)
        eligible.append((fdc_id, desc, desc_tokens, len(extra)))
        eligible[-1] = eligible[-1] + (non_benign_count,)
    # Prefer candidates whose extra words are ALL benign prep/cultivar terms
    # over ones with fewer extra words but a non-benign one ("Pie, peach" has
    # only 1 extra word, but it is not a prep variation of a peach -- it is a
    # different food -- so it must rank behind "Peaches, yellow, raw" despite
    # that candidate's higher raw extra-word count).
    eligible.sort(key=lambda item: (item[4], item[3], item[1]))
    return [item[:4] for item in eligible]


def confidence_for(extra_token_count: int) -> float:
    return max(CONFIDENCE_FLOOR, round(0.95 - 0.08 * extra_token_count, 2))


def main() -> None:
    rows = list(csv.DictReader(ALIASES_CSV.open(encoding="utf-8")))
    canon: dict[str, str] = {}
    for row in rows:
        canon.setdefault(row["ingredient_id"], row["canonical_name"])

    single_word_names = frozenset(
        singularize(name) for name in canon.values() if " " not in name and "-" not in name
    )

    tier_data = [(source_tier, label, load_tier(path, want_type)) for source_tier, label, path, want_type in TIERS]
    for _, label, data in tier_data:
        print(f"loaded {label}: {len(data)} candidate foods")

    results: dict[str, dict] = {}
    counts = {"mapped": 0, "needs_review": 0, "unresolved_or_composite": 0, "unresolved_no_match": 0}

    for cid, name in sorted(canon.items()):
        name_tokens = tokens(name)
        if not name_tokens:
            results[cid] = {"canonical_name": name, "status": "unresolved", "reason": "empty_name"}
            counts["unresolved_no_match"] += 1
            continue

        if " or " in f" {name} ":
            results[cid] = {
                "canonical_name": name,
                "status": "unresolved",
                "reason": "or_composite",
                "note": (
                    "Name is an explicit 'X or Y' alternative; a single FDC lookup would "
                    "misrepresent whichever half a given recipe actually used. Route to "
                    "the compute-from-components layer or resolve per-recipe, not here."
                ),
            }
            counts["unresolved_or_composite"] += 1
            continue

        # Rank every tier before choosing one. A tier's *first* match isn't
        # necessarily its *best*: SR Legacy's terse "Pie, peach" can win that
        # tier's internal ranking over nothing at all, while FNDDS -- checked
        # later under a naive stop-at-first-tier rule -- actually holds a
        # plain "Peach, raw". So gather every tier's ranked list, then prefer
        # the highest-priority tier that has a purely-benign top candidate;
        # only fall back to the first tier with any match at all if no tier
        # offers a benign one anywhere.
        tier_rankings = []
        for source_tier, label, candidates in tier_data:
            ranked = rank_candidates(name_tokens, candidates, single_word_names)
            if ranked:
                tier_rankings.append((label, ranked))

        chosen = None
        source_tier_label = None
        for label, ranked in tier_rankings:
            top_extra = ranked[0][2] - name_tokens
            if not (top_extra - BENIGN_QUALIFIERS):
                chosen, source_tier_label = ranked, label
                break
        if chosen is None and tier_rankings:
            source_tier_label, chosen = tier_rankings[0][0], tier_rankings[0][1]

        if not chosen:
            results[cid] = {
                "canonical_name": name,
                "status": "unresolved",
                "reason": "no_catalog_match",
                "note": (
                    "No Foundation/SR Legacy/FNDDS entry's description is a superset of "
                    "this name's tokens. Needs layer 3 (compute from components, if this "
                    "is itself composite) or layer 4 (web, dated + URL) review."
                ),
            }
            counts["unresolved_no_match"] += 1
            continue

        best_fdc_id, best_desc, best_desc_tokens, best_extra = chosen[0]
        confidence = confidence_for(best_extra)
        extra_words = sorted(best_desc_tokens - name_tokens)
        evidence = (
            f"Matched every word of '{name}' inside the FDC description; "
            f"{best_extra} additional descriptor word(s) beyond the name "
            f"({', '.join(extra_words) if extra_words else 'none'})."
        )

        rejected = []
        for fdc_id, desc, desc_tokens, extra in chosen[1:4]:
            rejected.append(
                {
                    "fdc_id": fdc_id,
                    "name": desc,
                    "why": (
                        f"{extra} extra descriptor word(s) vs. the chosen candidate's "
                        f"{best_extra} -- a less exact match for the same ingredient name."
                        if extra != best_extra
                        else "Equally exact match; chosen candidate kept for a deterministic "
                        "tie-break (alphabetical description), not a quality judgement."
                    ),
                }
            )

        # A generic/category name (nuts, broth, meat, soup...) has no single
        # correct FDC analog: many distinct tied-best candidates that are
        # genuinely different foods (not just salted/unsalted variants of the
        # same one), or the only candidate available is a narrow, tangential
        # match. Either pattern means auto-picking one misrepresents the
        # ingredient rather than approximating it, so this is surfaced for a
        # human pick rather than silently resolved.
        tied = [c for c in chosen if c[3] == best_extra]
        distinct_variants = {tuple(sorted(desc_tokens - name_tokens)) for _, _, desc_tokens, _ in tied}
        non_benign_extra = sorted((best_desc_tokens - name_tokens) - BENIGN_QUALIFIERS)
        ambiguous_reason = None
        if non_benign_extra:
            ambiguous_reason = "non_benign_qualifier"
        elif len(distinct_variants) >= 3:
            ambiguous_reason = "generic_term_multiple_variants"
        elif len(chosen) <= 2 and best_extra >= 3:
            ambiguous_reason = "sparse_weak_match"

        if ambiguous_reason:
            status = "needs_review"
        else:
            status = "mapped" if confidence >= 0.6 else "needs_review"
        counts[status] += 1

        results[cid] = {
            "canonical_name": name,
            "status": status,
            "fdc_id": best_fdc_id,
            "chosen_name": best_desc,
            "source_tier": source_tier_label,
            "confidence": confidence if not ambiguous_reason else min(confidence, 0.5),
            "evidence": evidence,
            "rejected": rejected,
            **({"ambiguous_reason": ambiguous_reason} if ambiguous_reason else {}),
        }

    OUT_JSON.parent.mkdir(parents=True, exist_ok=True)
    with OUT_JSON.open("w", encoding="utf-8") as fh:
        json.dump(results, fh, ensure_ascii=False, indent=2)

    total = len(canon)
    print(f"\nwrote {total} nutrition_mapping rows -> {OUT_JSON}")
    for key, value in counts.items():
        print(f"  {key}: {value} ({value / total * 100:.1f}%)")


if __name__ == "__main__":
    main()
