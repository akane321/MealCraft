"""Data release v3 (Knowledge ADR-0103 section 3, MealCraft issue #390): release v2.2 verbatim plus added recipes.

    python scripts/build_release_v3.py             # reads data/release/v2.2/ and data/staging/, writes data/release/v3/
    python scripts/build_release_v3.py --out DIR   # the same files into DIR (two runs give the same bytes)

"Data release v3" is the data release; it is not the v3 held-out evaluation protocol. The decisions are the owner's
2026-11-02 instruction ("just do it; a medium-quality version is fine"), recorded in the manifest's `change_notes`:

1. Every release v2.2 record is copied byte for byte (same ids, wording and fields), and `ingredients.jsonl` is v2.2's
   701 ingredients unchanged, so v3 adds no ingredient id.
2. Added recipes come from three legs, all through the same `build_release_v2.build_recipe` rules and then the v2.2
   unit-weight corrections (`correct_release_v22.correct_recipe`, weighed against v2.2's ingredient forms):
   the built-but-over-quota v2.1 recipes (the v2 enrichment set rebuilt from `data/staging/v2_merged.*`), and the
   new RecipeNLG candidates picked by `select_v3_candidates.py`, split into wave 1
   (`data/enrichment/v3_selected_wave1.csv`, enriched by `enrich_v3_openai.py`) and the extra wave 2 (owner
   2026-11-02 ~14:45, enriched partly by `enrich_v3_openai.py` and partly by Claude subagents through
   `enrich_v3_agents.py`, same instructions and validation; `enrichment.by` names which).
3. An added recipe is not released when it uses an ingredient id outside v2.2, its cuisine is in no quota bucket
   (`international`, ADR-0034), an ingredient form is missing from v2.2, its per-serving energy is implausible after
   the correction, it is below the importer floor (2 ingredient lines and a step), or its lower-cased,
   whitespace-normalised title is already in the release (v2.2 first, then the over-quota leg, then wave 1, then
   wave 2, each in recipe_id order). A completeness-flagged recipe with no review verdict is dropped by the build,
   as before.
4. No cuisine label is above 20% of the final release: over a label's room the added recipes a planner can use stay
   first (main, side, soup, salad, breakfast, then the rest), ties by recipe_id; wave 2 only takes the room the
   earlier legs leave, so the cap cuts wave 2 first; the room is recomputed from the final total until it no longer
   moves.
5. Every record of the first v3 build (2026-11-03: 12,895 recipes; the added ones' line sha256 are in
   `data/enrichment/v3_first_build_lines.tsv`) stays byte for byte, and recipes.jsonl stays under 95,000,000 bytes
   (GitHub refuses files over 100 MB); either failing stops the build.
6. Reviewed corrections (`data/enrichment/v3-corrections.csv`, checked by `v3_corrections.py`, issue #408): the
   cuisine, course and servings rows go into the added recipes' enrichment results before they are built, so the
   cap, the checks and the per-serving nutrition see the reviewed values; only the corrected recipes are exempt from
   rule 5. Withdraw rows stay released (`v3_corrections.py withdraw` keeps them out of plans). An empty table
   changes nothing.

Every candidate not released is in `dropped.jsonl` with its reason. The manifest carries the sha256 of every input
and a `fingerprint` over recipes.jsonl, ingredients.jsonl and the manifest itself without that field. Nothing reads
a clock or a random source.
"""

from __future__ import annotations

import argparse
import collections
import hashlib
import json
import re
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "scripts"))

import build_release_v2 as build  # noqa: E402
import correct_release_v22 as correct  # noqa: E402
import v3_corrections as reviewed  # noqa: E402
from build_v2_candidates import QUOTAS  # noqa: E402
from prepare_v2_inputs import stated_durations  # noqa: E402
from select_v3_candidates import CAP, cap_by_label, title_key  # noqa: E402
from v2_release_report import attribution  # noqa: E402

RELEASE_VERSION = "v3"
SCHEMA_VERSION = "mealcraft.recipe.v2"
CREATED_AT = "2026-11-03T00:00:00+00:00"  # fixed, so a rerun writes the same bytes
MINIMUM_RELEASED = 18000  # owner 2026-11-02 ~14:45: grow v3 toward 18,280 (the build gives 18,335)
MAX_RECIPES_BYTES = 95_000_000  # GitHub refuses files over 100 MB
RELEASES = ROOT / "data" / "release"
V21, V22, OUT = RELEASES / "v2.1", RELEASES / "v2.2", RELEASES / RELEASE_VERSION
STAGING = ROOT / "data" / "staging"
PACKETS = ROOT / "enrichment-work"
ENRICHMENT = ROOT / "data" / "enrichment"
WAVE1_CSV = ENRICHMENT / "v3_selected_wave1.csv"
FIRST_BUILD = ENRICHMENT / "v3_first_build_lines.tsv"  # recipe_id and line sha256 of the first build's added records
CORRECTIONS = reviewed.TABLE  # data/enrichment/v3-corrections.csv
STAGING_INPUTS = (
    "v2_enrich_set.jsonl",
    "v2_merged.recipes.jsonl",
    "v2_merged.ingredients.jsonl",
    "v3_selected.jsonl",
    "v3_merged.recipes.jsonl",
    "v3_enrich_failed.jsonl",
)
LABELS = ("built", "v3")  # before and after in corrections.jsonl: the rebuilt record, and what v3 releases
BUCKETED = {cuisine for spec in QUOTAS["buckets"].values() for cuisine in spec["cuisines"]}
LOCAL = "malaysian_singaporean"
ENRICHER = "excluded by enricher"
FAILED, NOT_ENRICHED = "enrichment failed validation", "not enriched"  # dropped.jsonl reason buckets
CHANGE_NOTES = [
    "Data release v3 = every release v2.2 record copied verbatim (same ids, wording and fields) plus added recipes; "
    "ingredients.jsonl is v2.2's 701 ingredients unchanged, so no ingredient id is new (recipe_occurrences still "
    "count v2.2's recipes).",
    "Added recipes: the built-but-over-quota v2.1 recipes rebuilt from the v2 staging inputs with the current build "
    "rules, and new RecipeNLG (Gathered) candidates never selected in v2 (select_v3_candidates.py); both then take the "
    "v2.2 unit-weight corrections (correct_release_v22.correct_recipe), listed in corrections.jsonl.",
    "New candidates qualify only when every line maps to a v2.2 ingredient, every ingredient is priced by the planner "
    "rule (backend priceable_ingredients: FairPrice not removed, Cold Storage mapped, curated; no at-home exemption), "
    "every ingredient form and unit weight exists, and the triage cuisine is not in the American bucket (american, "
    "southern_us, cajun_creole); mains first. Pool lines may resolve through stage-3 alias decisions that land on one "
    "of the 701 ids.",
    "New candidates are enriched by the OpenAI API (gpt-5.4-mini, reasoning effort low) with the v2 recipe field set, "
    "vocabulary, instructions and validation (enrich_v3_openai.py); this amends ADR-0030's choice of agent sessions. "
    "Their records say enrichment.by 'openai/gpt-5.4-mini'.",
    "Not released: an ingredient id outside v2.2, cuisine international (ADR-0034, not relabelled), a completeness-"
    "flagged recipe with no review verdict (no new completeness review), implausible energy after the correction, "
    "below the importer floor, or a title equal (lower-cased, whitespace-normalised) to one already in the release.",
    "No cuisine label is above 20% of the final total; over a label's room usable courses stay first (main, side, "
    "soup, salad, breakfast, then the rest), ties by recipe_id.",
    "Wave 2 (owner 2026-11-02 ~14:45: grow v3 toward 19,000 recipes, medium quality is fine): more new candidates "
    "picked by the same rules after the frozen wave-1 picks (v3_selected_wave1.csv), target 18,280 so recipes.jsonl "
    "stays under 95,000,000 bytes. Titles are de-duplicated in the order v2.2, over-quota, wave 1, wave 2, and wave 2 "
    "only takes the label room the earlier legs leave, so every record of the first v3 build (12,895) stays byte for "
    "byte.",
    "Wave 2 enrichment (owner 2026-11-02 ~16:10): part by the OpenAI API (gpt-5.4-mini, as wave 1) until that run "
    "stopped, the rest by Claude subagents (enrich_v3_agents.py: the OpenAI enricher's instructions, schema, input "
    "and validation); their records say enrichment.by 'claude/<model>'. The OpenAI API is not used for enrichment "
    "again.",
    "Composite substitutes ('half-and-half = milk + cream') are not built: the release schema has no field. Open.",
    "Quality targets for the later human checks of the new recipes (issue #392): 'at least 95%' is the point "
    "estimate, reported with Wilson 95% intervals.",
]
SHORTCUTS = [
    "No new completeness review: a flagged new recipe with no verdict is dropped, not reviewed.",
    "No new ingredients, prices, halal labels or hierarchy entries: candidates were limited to v2.2's priced ids.",
    "New recipes are enriched by one model pass (gpt-5.4-mini at low reasoning effort, or a Claude subagent for part "
    "of wave 2), not by sessions with an overlap agreement check; the {failed} recipes that failed validation twice "
    "are dropped, not fixed by hand.",
    "The near-twin guard is an exact title match after lower-casing and whitespace; near-identical recipes with "
    "different titles stay.",
    "The release total is what passes the checks, not trimmed to a target.",
    "{not_enriched} selected candidates were never enriched and are in dropped.jsonl as 'not enriched'.",
    "ingredients.jsonl is v2.2's file byte for byte, so its recipe_occurrences count v2.2's recipes only.",
    "Composite substitutes are not built (no schema field).",
    "The cuisine labels of the model-enriched recipes are unreviewed model output (some are debatable).",
    "Wave 2's cuisine labels and course labels are unreviewed model output too; its human checks are the 2026-11-04 "
    "draws (manual-check-20261104/, allergen-review-20261104/).",
]


def read_jsonl(path: Path) -> list[dict]:
    return [json.loads(line) for line in path.read_text(encoding="utf-8").splitlines() if line.strip()]


def sha256(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def table_sha256(path: Path) -> str:
    """sha256 of a committed table with LF line endings, so an Excel (CRLF) copy hashes as the file git stores."""
    return sha256(path.read_bytes().replace(b"\r\n", b"\n"))


def bucket(reason: str) -> str:
    """The summary bucket of a raw reason, as build_release_v2 counts it (the ops console reads it the same way)."""
    return re.sub(r"ING_\S+|\d+(\.\d+)?|\([^)]*\)", "#", reason).split(":")[0].strip()


def drop(record: dict, reason: str, counted: str | None = None) -> dict:
    return {
        "candidate_id": record["candidate_id"],
        "title": record["title"],
        "reason": reason[:500],
        "_bucket": counted or bucket(reason),
    }


def rebuild(records: dict[str, dict], results: dict[str, dict], forms: dict, rules: dict, failed: dict[str, str]):
    """Every candidate through `build_release_v2.build_recipe`: (built recipes, drops), in candidate_id order."""
    built, drops = [], []
    for candidate_id in sorted(records):
        record, result = records[candidate_id], results.get(candidate_id)
        if result is None:
            reason = failed.get(candidate_id)
            drops.append(drop(record, f"enrichment failed validation: {reason}" if reason else "not enriched"))
        elif "exclude" in result:
            drops.append(drop(record, result["exclude"], ENRICHER))
        else:
            recipe, reason = build.build_recipe(record, result, forms, rules)
            if recipe is None:
                drops.append(drop(record, reason))
            else:
                built.append(recipe)
    return built, drops


def admit(recipe: dict, entries: dict, forms: dict) -> tuple[dict | None, str, list[dict]]:
    """The recipe as v3 releases it (unit weights corrected), or the reason it is not released."""
    ids = {line["canonical_ingredient_id"] for line in recipe["ingredients"]}
    if not ids <= set(entries):
        return None, "new ingredient id: " + ", ".join(sorted(ids - set(entries))), []
    if recipe["cuisine"] not in BUCKETED:
        return None, f"cuisine not in a quota bucket: {recipe['cuisine']}", []
    missing = sorted({correct.form_key(line) for line in recipe["ingredients"]} - set(forms))
    if missing:
        return None, "ingredient form missing from the release ingredients: " + ", ".join(missing), []
    corrected, changes = correct.correct_recipe(recipe, forms, entries, LABELS)
    kcal = corrected["nutrition"]["energy_kcal"]
    if not build.ENERGY_PER_SERVING[0] <= kcal <= build.ENERGY_PER_SERVING[1]:
        return None, f"implausible energy after the unit-weight correction: {kcal} kcal per serving", []
    if len(corrected["ingredients"]) < 2 or not corrected["instructions"]:
        return None, "below the importer floor: fewer than two ingredient lines or no step", []
    return corrected, "", changes


def capped(base: collections.Counter, tiers: list[list[dict]]) -> tuple[list[dict], int]:
    """`cap_by_label` with the room taken from the final total: shrink it until it no longer moves. A later tier only
    takes the room the earlier ones leave, so the cap cuts the last tier first."""
    limit = int(CAP * (sum(base.values()) + sum(map(len, tiers))))
    while True:
        counts, kept = collections.Counter(base), []
        for tier in tiers:
            more, _ = cap_by_label(counts, tier, limit)
            counts.update(r["cuisine"] for r in more)
            kept += more
        settled = int(CAP * (sum(base.values()) + len(kept)))
        if settled == limit:
            return sorted(kept, key=lambda r: r["recipe_id"]), limit
        limit = settled


def choose(v22: list[dict], legs: list[tuple[str, list[dict]]], entries: dict):
    """(added recipes, drops, corrections, leg of each added recipe) from each leg's built recipes, in leg order."""
    forms = {key: form for row in entries.values() for key, form in row["forms"].items()}
    released = {r["recipe_id"] for r in v22}
    titles = {title_key(r["title"]) for r in v22}
    candidates, drops, changes, leg_of = [], [], {}, {}
    for leg, recipes in legs:
        for recipe in sorted(recipes, key=lambda r: r["recipe_id"]):
            if recipe["recipe_id"] in released:
                continue  # released verbatim from v2.2
            record = {"candidate_id": recipe["source"]["candidate_id"], "title": recipe["title"]}
            out, reason, changed = admit(recipe, entries, forms)
            if out is None:
                drops.append(drop(record, reason))
                continue
            if title_key(out["title"]) in titles:
                drops.append(drop(record, f"title already in the release: {title_key(out['title'])}"))
                continue
            titles.add(title_key(out["title"]))
            leg_of[out["recipe_id"]] = leg
            changes[out["recipe_id"]] = changed
            candidates.append(out)
    tiers = [[r for r in candidates if leg_of[r["recipe_id"]] != "extra"]]
    tiers.append([r for r in candidates if leg_of[r["recipe_id"]] == "extra"])
    kept, limit = capped(collections.Counter(r["cuisine"] for r in v22), tiers)
    total = len(v22) + len(kept)
    chosen = {r["recipe_id"] for r in kept}
    for recipe in candidates:
        if recipe["recipe_id"] not in chosen:
            reason = f"cuisine label cap: {recipe['cuisine']} held at {limit} of {total} recipes ({CAP:.0%})"
            drops.append(drop({"candidate_id": recipe["source"]["candidate_id"], "title": recipe["title"]}, reason))
    corrections = [c for r in kept for c in changes[r["recipe_id"]]]
    return kept, drops, corrections, {r["recipe_id"]: leg_of[r["recipe_id"]] for r in kept}


def recipe_id_of(candidate_id: str) -> str:
    """The recipe id `build_release_v2.build_recipe` gives a candidate."""
    return "RCP2_" + sha256(candidate_id.encode())[:12].upper()


def apply_reviews(results: dict[str, dict], fixes: dict[str, list[dict]]) -> tuple[list[str], set[str]]:
    """Put the reviewed cuisine, course and servings rows into the enrichment results they name, so that
    `build_recipe` computes nutrition per serving from the reviewed servings. The field's evidence says who reviewed
    it and why, its confidence is 1.0. Returns the problems (old_value is not the built value) and the ids found."""
    problems, found = [], set()
    for candidate_id, result in results.items():
        rid = recipe_id_of(candidate_id)
        if rid not in fixes or "exclude" in result:
            continue
        found.add(rid)
        result = results[candidate_id] = {
            **result,
            "evidence": dict(result["evidence"]),
            "confidence": dict(result["confidence"]),
        }
        for row in fixes[rid]:
            field, old = row["field"], row["old_value"]
            if str(result[field]) != old:
                problems.append(f"row {row['row']}: old_value {old!r} is not the built {field} {result[field]!r}")
            result[field] = reviewed.new_value(row)
            result["evidence"][field] = f"reviewed by {row['reviewer']}: {row['reason']} (was {old})"
            result["confidence"][field] = 1.0
    return problems, found


def legs_from_staging(
    staging: Path, packets: Path, rules: dict, fixes: dict[str, list[dict]] | None = None
) -> tuple[dict, list[tuple[str, list]], list]:
    """Rebuild the v2 enrichment set (over-quota leg) and the v3 selection (new leg) from the staging inputs, with
    the reviewed corrections applied (`fixes`: recipe_id -> its cuisine, course and servings rows)."""
    v2_set = {r["candidate_id"]: r for r in read_jsonl(staging / "v2_enrich_set.jsonl")}
    # As build_release_v2: the durations the packet showed the enricher decide whether a time may be "stated".
    for part in ("A", "B", "C"):
        for item in read_jsonl(packets / f"part-{part}" / "recipes.input.jsonl"):
            if item["candidate_id"] in v2_set:
                v2_set[item["candidate_id"]]["stated_durations"] = item.get("stated_durations") or []
    v2_results = {r["candidate_id"]: r for r in read_jsonl(staging / "v2_merged.recipes.jsonl")}
    forms = {r["ingredient_id"]: r for r in read_jsonl(staging / "v2_merged.ingredients.jsonl")}
    new_set = {r["candidate_id"]: r for r in read_jsonl(staging / "v3_selected.jsonl")}
    wave1 = {line.split(",")[0] for line in WAVE1_CSV.read_text(encoding="utf-8").splitlines()[1:]}
    for record in new_set.values():
        record["stated_durations"] = stated_durations(record["instructions"])  # what enrich_v3_openai showed
    new_results = {r["candidate_id"]: r for r in read_jsonl(staging / "v3_merged.recipes.jsonl")}
    failed = {r["candidate_id"]: "; ".join(r["errors"]) for r in read_jsonl(staging / "v3_enrich_failed.jsonl")}
    fixes = fixes or {}
    problems, found = [], set()
    for results in (v2_results, new_results):
        more, ids = apply_reviews(results, fixes)
        problems, found = problems + more, found | ids
    problems += [f"row {fixes[rid][0]['row']}: {rid} is not a recipe this build makes" for rid in set(fixes) - found]
    if problems:
        raise SystemExit("v3 corrections: " + "; ".join(sorted(problems)))
    over, over_drops = rebuild(v2_set, v2_results, forms, rules, {})
    new, new_drops = rebuild(new_set, new_results, forms, rules, failed)
    first = [r for r in new if r["source"]["candidate_id"] in wave1]
    extra = [r for r in new if r["source"]["candidate_id"] not in wave1]
    sizes = {"v2_enrichment_set": len(v2_set), "v3_selected": len(new_set), "v3_selected_wave_1": len(wave1)}
    return sizes, [("over_quota", over), ("new", first), ("extra", extra)], over_drops + new_drops


def tally(values) -> dict:
    return dict(collections.Counter(values).most_common())


def share(part: int, whole: int) -> float:
    return round(part / max(whole, 1), 4)


def in_range(recipe: dict) -> bool:
    return build.ENERGY_PER_SERVING[0] <= recipe["nutrition"]["energy_kcal"] <= build.ENERGY_PER_SERVING[1]


def line_hashes(lines: list[str]) -> dict[str, str]:
    """recipe_id -> sha256 of the line as written (no newline)."""
    return {json.loads(line)["recipe_id"]: sha256(line.encode()) for line in lines}


def read_first_build(path: Path = FIRST_BUILD) -> dict[str, str]:
    rows = path.read_text(encoding="utf-8").splitlines()[1:]
    return dict(row.split("	") for row in rows if row)


def verify(lines: list[str], v22_lines: list[str], added: list[dict], entries: dict, rules: dict, limits: dict) -> dict:
    """The release checks; a failure stops the build. Returns what each check counted."""
    recipes = [json.loads(line) for line in lines]
    problems = []
    if not set(v22_lines) <= set(lines):
        problems.append("a v2.2 record is not byte-identical in v3")
    hashes, first = line_hashes(lines), limits["first_build"]
    exempt = {row["recipe_id"] for row in limits["reviews"] if row["field"] != "withdraw"}
    changed = sorted(key for key, digest in first.items() if key not in exempt and hashes.get(key) != digest)
    if changed:
        problems.append(f"{len(changed)} first-build records missing or changed, e.g. {changed[:3]}")
    by_id = {r["recipe_id"]: r for r in added}
    unapplied = [
        row
        for row in limits["reviews"]
        if row["field"] != "withdraw" and by_id.get(row["recipe_id"], {}).get(row["field"]) != reviewed.new_value(row)
    ]
    if unapplied:
        # A servings change can make the per-serving nutrition fail a gate; the drop reason says so.
        why = [f"{r['row']} ({limits['dropped_ids'].get(r['recipe_id'], 'not released')})" for r in unapplied[:5]]
        problems.append(f"corrections not in the released recipes, table rows {', '.join(why)}")
    size = sum(len(line.encode()) + 1 for line in lines)
    if size > limits["max_bytes"]:
        problems.append(f"recipes.jsonl is {size} bytes > {limits['max_bytes']}")
    outside = {line["canonical_ingredient_id"] for r in recipes for line in r["ingredients"]} - set(entries)
    if outside:
        problems.append(f"ingredient ids outside v2.2: {sorted(outside)}")
    top, top_n = collections.Counter(r["cuisine"] for r in recipes).most_common(1)[0]
    if top_n > CAP * len(recipes):
        problems.append(f"cuisine {top} is {top_n} of {len(recipes)}")
    if len(recipes) < limits["minimum"]:
        problems.append(f"released {len(recipes)} < {limits['minimum']}")
    if len({r["recipe_id"] for r in recipes}) != len(recipes):
        problems.append("duplicate recipe ids")
    failing = {
        "below the importer floor": [r for r in added if len(r["ingredients"]) < 2 or not r["instructions"]],
        "energy out of range": [r for r in added if not in_range(r)],
        "allergens not from the rule table": [
            r
            for r in added
            if any(
                line["allergens"] != rules[line["canonical_ingredient_id"]]["allergens"] for line in r["ingredients"]
            )
            or r["allergens"] != sorted({a for line in r["ingredients"] for a in line["allergens"]})
        ],
    }
    problems += [f"added recipes {name}: {[r['recipe_id'] for r in rs][:5]}" for name, rs in failing.items() if rs]
    if problems:
        raise SystemExit("release v3 checks failed: " + "; ".join(problems))
    return {
        "v2_2_records_byte_identical": len(v22_lines),
        "first_build_records_byte_identical": len(
            (set(first) - exempt) | {json.loads(line)["recipe_id"] for line in v22_lines}
        ),
        "recipes_bytes": size,
        "max_bytes": limits["max_bytes"],
        "largest_label": {"cuisine": top, "recipes": top_n, "share": share(top_n, len(recipes))},
        "released_at_least": limits["minimum"],
        "v2_2_energy_outside_range": sum(not in_range(json.loads(line)) for line in v22_lines),
    }


def fingerprint(recipes: bytes, ingredients: bytes, manifest: bytes) -> str:
    """sha256 of the lines "<sha256>  <name>" of recipes.jsonl, ingredients.jsonl and the manifest without the field."""
    names = ("recipes.jsonl", "ingredients.jsonl", "release_manifest.json")
    listing = "".join(
        f"{sha256(data)}  {name}\n" for data, name in zip((recipes, ingredients, manifest), names, strict=True)
    )
    return sha256(listing.encode())


def jsonl(rows, **options) -> bytes:
    return "".join(json.dumps(row, ensure_ascii=False, **options) + "\n" for row in rows).encode()


def pretty(value: dict) -> bytes:
    return (json.dumps(value, ensure_ascii=False, indent=2) + "\n").encode()


def assemble(
    v22_lines: list[str],
    ingredients: bytes,
    rules: dict,
    sizes: dict,
    legs: list[tuple[str, list[dict]]],
    build_drops: list[dict],
    inputs_sha256: dict,
    minimum: int = MINIMUM_RELEASED,
    first_build: dict[str, str] | None = None,
    max_bytes: int = MAX_RECIPES_BYTES,
    reviews: list[dict] = (),
) -> dict[str, bytes]:
    """Every file of data/release/v3 as bytes, from v2.2's records and ingredients and the built recipes of each leg."""
    v22 = [json.loads(line) for line in v22_lines]
    entries = {row["ingredient_id"]: row for row in (json.loads(line) for line in ingredients.decode().splitlines())}
    built = {r["recipe_id"] for r in v22} | {r["recipe_id"] for _, recipes in legs for r in recipes}
    unbucketed = sum(r["cuisine"] not in BUCKETED for _, recipes in legs for r in recipes)
    # A v2.2 candidate the current rules would not build stays released verbatim, so it is not a drop.
    v22_candidates = {r["source"]["candidate_id"] for r in v22}
    added, drops, corrections, leg_of = choose(v22, legs, entries)
    drops = sorted(
        [d for d in build_drops if d["candidate_id"] not in v22_candidates] + drops, key=lambda d: d["candidate_id"]
    )
    corrections.sort(key=lambda c: (c["recipe_id"], c["line"]))

    by_id = {r["recipe_id"]: line for r, line in zip(v22, v22_lines, strict=True)}
    by_id.update({r["recipe_id"]: json.dumps(r, ensure_ascii=False, sort_keys=True) for r in added})
    lines = [by_id[key] for key in sorted(by_id)]
    recipes = [json.loads(line) for line in lines]
    dropped_ids = {recipe_id_of(d["candidate_id"]): d["reason"] for d in drops}  # names why a corrected recipe is gone
    limits = {
        "minimum": minimum,
        "first_build": first_build or {},
        "max_bytes": max_bytes,
        "reviews": reviews,
        "dropped_ids": dropped_ids,
    }
    checks = verify(lines, v22_lines, added, entries, rules, limits)
    enrichment_set = sizes["v2_enrichment_set"] + sizes["v3_selected"]
    if len(recipes) + len(drops) != enrichment_set:
        raise SystemExit(f"released {len(recipes)} + dropped {len(drops)} != enrichment set {enrichment_set}")

    total = len(recipes)
    dropped_by_reason = tally(d["_bucket"] for d in drops)
    counts = {
        "released_recipes": total,
        "built_before_quota": len(built),
        "enrichment_set": enrichment_set,
        "released_ingredients": len(entries),
        "unbucketed_cuisine": unbucketed,
        "dropped_by_reason": dropped_by_reason,
        "by_cuisine": tally(r["cuisine"] for r in recipes),
        "by_course": tally(r["course"] for r in recipes),
        "by_source": tally(r["source"]["dataset"] for r in recipes),
        "servings_estimated": sum(r["servings_basis"] == "estimated" for r in recipes),
        "time_estimated": sum(r["time_basis"] == "estimated" for r in recipes),
        "lines_with_estimated_amount": sum(
            line["grams_basis"] == "estimated" for r in recipes for line in r["ingredients"]
        ),
        "from_v2_2": len(v22),
        "added_over_quota": sum(leg == "over_quota" for leg in leg_of.values()),
        "added_new": sum(leg in ("new", "extra") for leg in leg_of.values()),
        "added_new_wave_1": sum(leg == "new" for leg in leg_of.values()),
        "added_new_wave_2": sum(leg == "extra" for leg in leg_of.values()),
        # One model pass per new recipe: the OpenAI API, or a Claude subagent (part of wave 2).
        "model_enriched": sum(leg in ("new", "extra") for leg in leg_of.values()),
        "enriched_by_wave_1": tally(r["enrichment"]["by"] for r in added if leg_of[r["recipe_id"]] == "new"),
        "enriched_by_wave_2": tally(r["enrichment"]["by"] for r in added if leg_of[r["recipe_id"]] == "extra"),
    }
    manifest = {
        "release_version": RELEASE_VERSION,
        "schema_version": SCHEMA_VERSION,
        "decision": "ADR-0030; Knowledge ADR-0103 section 3 (issue #390); owner 2026-11-02",
        "created_at": CREATED_AT,
        "counts": counts,
        "licensing": "Each record keeps its own licence in source.license; the release is a collection, not "
        "relicensed. Non-commercial use only. See ATTRIBUTION.md.",
        "derived_from": {
            "release_version": "v2.2",
            "step": "scripts/build_release_v3.py",
            "inputs": sizes,
            "corrected_lines": len(corrections),
            "corrected_recipes": len({c["recipe_id"] for c in corrections}),
            "corrected_lines_by_class": dict(sorted(collections.Counter(c["class"] for c in corrections).items())),
            **inputs_sha256,
        },
        "change_notes": CHANGE_NOTES,
    }
    if reviews:  # an empty table leaves the manifest as it was
        manifest["derived_from"]["reviewed_corrections"] = {
            "rows_by_field": tally(row["field"] for row in reviews),
            "recipes_corrected": len({row["recipe_id"] for row in reviews if row["field"] != "withdraw"}),
        }
    files = {
        "recipes.jsonl": "".join(line + "\n" for line in lines).encode(),
        "ingredients.jsonl": ingredients,
        "dropped.jsonl": jsonl({k: d[k] for k in ("candidate_id", "title", "reason")} for d in drops),
        "corrections.jsonl": jsonl(corrections, sort_keys=True),
    }
    manifest["fingerprint"] = fingerprint(files["recipes.jsonl"], ingredients, pretty(manifest))
    files["release_manifest.json"] = pretty(manifest)

    corrected = collections.Counter(
        line["grams_correction"] for r in recipes for line in r["ingredients"] if "grams_correction" in line
    )
    summary = {
        "release_version": RELEASE_VERSION,
        "created_at": CREATED_AT,
        "coverage": {
            "released_recipes": total,
            "enrichment_set": enrichment_set,
            "released_ingredients": len(entries),
            "recipes_with_every_field": total,
        },
        "by_cuisine": counts["by_cuisine"],
        "by_course": counts["by_course"],
        "by_source": counts["by_source"],
        "estimated_share": {
            "servings": share(counts["servings_estimated"], total),
            "times": share(counts["time_estimated"], total),
            "ingredient_amounts": share(
                counts["lines_with_estimated_amount"], sum(len(r["ingredients"]) for r in recipes)
            ),
        },
        "dropped_by_reason": dropped_by_reason,
        "allergen_rules_pending_human": sum(1 for rule in rules.values() if rule.get("allergen_status") != "confirmed"),
        "nutrition_per_serving": {
            "median_energy_kcal": sorted(r["nutrition"]["energy_kcal"] for r in recipes)[total // 2]
        },
        # The whole release's corrected lines by class: v2.2's own corrections plus those of the added recipes.
        "unit_weight_corrections": dict(sorted(corrected.items())),
    }
    files["quality_summary.json"] = pretty(summary)
    text = attribution(recipes, list(entries.values()))
    text = text.replace("# Release v2 attribution", "# Data release v3 attribution", 1).replace(
        "Generated by `scripts/v2_release_report.py`.",
        "Generated by `scripts/build_release_v3.py` (`v2_release_report.attribution`).",
        1,
    )
    files["ATTRIBUTION.md"] = text.encode()
    digests = {name: sha256(data) for name, data in files.items()}
    files["quality_report.md"] = report(manifest, summary["estimated_share"], checks, added, digests).encode()
    return files


def report(manifest: dict, estimated: dict, checks: dict, added: list[dict], digests: dict[str, str]) -> str:
    counts, derived = manifest["counts"], manifest["derived_from"]
    total = counts["released_recipes"]
    labels = "\n".join(f"| `{label}` | {n} | {n / total:.1%} |" for label, n in counts["by_cuisine"].items())
    drops = "\n".join(f"| {reason} | {n} |" for reason, n in counts["dropped_by_reason"].items())
    classes = "\n".join(f"| `{k}` | {v} |" for k, v in derived["corrected_lines_by_class"].items()) or "| none | 0 |"
    added_lines = sum(len(r["ingredients"]) for r in added)
    added_share = {
        "servings": share(sum(r["servings_basis"] == "estimated" for r in added), len(added)),
        "times": share(sum(r["time_basis"] == "estimated" for r in added), len(added)),
        "ingredient_amounts": share(
            sum(line["grams_basis"] == "estimated" for r in added for line in r["ingredients"]), added_lines
        ),
    }
    estimates = "\n".join(
        f"| {name.replace('_', ' ')} | {estimated[name]:.1%} | {added_share[name]:.1%} |" for name in estimated
    )
    notes = "\n".join(f"{i}. {note}" for i, note in enumerate(manifest["change_notes"], 1))
    dropped = counts["dropped_by_reason"]
    shortcuts = "\n".join(
        f"- {s}".format(failed=dropped.get(FAILED, 0), not_enriched=dropped.get(NOT_ENRICHED, 0)) for s in SHORTCUTS
    )
    files = "\n".join(f"| `{name}` | `{digest}` |" for name, digest in digests.items())
    local, local_added = counts["by_cuisine"].get(LOCAL, 0), sum(r["cuisine"] == LOCAL for r in added)
    model = counts["model_enriched"]
    sources = "\n".join(
        f"| {wave} | `{by}` | {n} |"
        for wave, key in (("wave 1", "enriched_by_wave_1"), ("wave 2", "enriched_by_wave_2"))
        for by, n in counts[key].items()
    )
    largest = checks["largest_label"]
    review = derived.get("reviewed_corrections")
    corrected = ""
    if review:  # an empty table leaves the report as it was
        rows = "\n".join(f"| `{field}` | {n} |" for field, n in review["rows_by_field"].items())
        corrected = f"""## Reviewed corrections

From `data/enrichment/v3-corrections.csv` (checked by `scripts/v3_corrections.py`; its sha256 is in the manifest's
`committed_sha256`): {review["recipes_corrected"]} added recipes corrected (exempt from check 2), and each corrected
field's evidence names the reviewer and the reason. Withdrawn: {review["rows_by_field"].get("withdraw", 0)}; they
stay released, and `data/recipes/withdrawn.json` keeps them out of plans (`v3_corrections.py withdraw`).

| Field | Rows |
| --- | ---: |
{rows}

"""
    return f"""# Data release v3 quality report

Generated by `scripts/build_release_v3.py` from `data/release/v2.2/` and the git-ignored staging inputs whose sha256
are in `release_manifest.json` (`derived_from`). Do not hand-edit. "Data release v3" is this data release, not the v3
held-out evaluation protocol. Decision: Knowledge ADR-0103 section 3 (issue #390), owner instruction 2026-11-02.

## Counts

| Part | Recipes |
| --- | ---: |
| From release v2.2, verbatim | {counts["from_v2_2"]} |
| Added: over-quota v2.1 recipes, rebuilt and corrected | {counts["added_over_quota"]} |
| Added: new RecipeNLG candidates, wave 1 | {counts["added_new_wave_1"]} |
| Added: new RecipeNLG candidates, wave 2 (the extra wave) | {counts["added_new_wave_2"]} |
| **Released** | **{total}** |

Candidates {counts["enrichment_set"]} (v2 enrichment set {derived["inputs"]["v2_enrichment_set"]} + v3 selection
{derived["inputs"]["v3_selected"]}, of which wave 1 {derived["inputs"]["v3_selected_wave_1"]}); built by the rules
{counts["built_before_quota"]}; not released
{counts["enrichment_set"] - total}, each in `dropped.jsonl` with its reason:

| Reason | Candidates |
| --- | ---: |
{drops}

## Cuisine labels (cap {CAP:.0%} of {total} = {int(CAP * total)} recipes)

| Cuisine | Recipes | Share |
| --- | ---: | ---: |
{labels}

Local Malaysian and Singaporean (`{LOCAL}`): {local} recipes, {local_added} of them added.

## Courses and sources

By course: {", ".join(f"{k} {v}" for k, v in counts["by_course"].items())}.

By source: {", ".join(f"{k} {v}" for k, v in counts["by_source"].items())}.

## Enrichment and estimated fields

Enriched by one model pass (the new RecipeNLG recipes): {model} of {total} released recipes
({share(model, total):.1%}); the others were enriched in agent sessions for release v2 (ADR-0030). By source
(`enrichment.by`):

| Wave | Enriched by | Recipes |
| --- | --- | ---: |
{sources}

`openai/...` is the OpenAI API (`enrich_v3_openai.py`); `claude/claude-...` is a Claude subagent with the same
instructions and validation (`enrich_v3_agents.py`).
Estimated values carry their evidence and confidence per field in `enrichment` (ADR-0076).

| Estimated | Whole release | Added recipes |
| --- | ---: | ---: |
{estimates}

## Unit-weight corrections of the added recipes

The v2.2 correction (`scripts/correct_release_v22.py`, owner 2026-10-23) applied to the added recipes:
{derived["corrected_lines"]} lines in {derived["corrected_recipes"]} recipes, each in `corrections.jsonl` with its
built and v3 grams. The v2.2 records keep their own v2.2 corrections (v2.2 `corrections.jsonl`).

| Class | Lines |
| --- | ---: |
{classes}

{corrected}## Checks

All pass, or the build stops:

1. Every v2.2 record is byte-identical in v3 ({checks["v2_2_records_byte_identical"]}).
2. Every record of the first v3 build is present and byte-identical (by recipe_id and line sha256;
   {checks["first_build_records_byte_identical"]} records).
3. recipes.jsonl is {checks["recipes_bytes"]} bytes <= {checks["max_bytes"]}.
4. No ingredient id outside v2.2's {counts["released_ingredients"]}.
5. No cuisine label above {CAP:.0%}: the largest is `{largest["cuisine"]}` at {largest["recipes"]}
   ({largest["share"]:.1%}).
6. Released {total} >= {checks["released_at_least"]}.
7. No duplicate recipe ids.
8. Every added recipe has at least two ingredient lines and a step.
9. Every added recipe's per-serving energy is within {build.ENERGY_PER_SERVING[0]}-{build.ENERGY_PER_SERVING[1]} kcal.
10. Every added recipe's allergens come only from the rule table.
11. Released + not released = candidates.

v2.2 records outside the energy range, kept verbatim: {checks["v2_2_energy_outside_range"]}.

## Decisions

{notes}

## Shortcuts (for teammates to refine later)

{shortcuts}

## Files

`fingerprint` (manifest) is the sha256 of the lines "<sha256>  <name>" for `recipes.jsonl`, `ingredients.jsonl` and
`release_manifest.json` without its `fingerprint` field: `{manifest["fingerprint"]}`.

| File | sha256 |
| --- | --- |
{files}
"""


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--out", type=Path, default=OUT, help="output directory (default data/release/v3)")
    args = parser.parse_args()
    v22_lines = [line for line in (V22 / "recipes.jsonl").read_text(encoding="utf-8").splitlines() if line.strip()]
    rules = build.ingredient_rules()
    reviews = reviewed.read_table(CORRECTIONS)
    problems = reviewed.check_rows(reviews, {json.loads(line)["recipe_id"] for line in v22_lines})
    if problems:
        raise SystemExit("v3 corrections: " + "; ".join(problems))
    fixes = collections.defaultdict(list)
    for row in reviews:
        if row["field"] != "withdraw":
            fixes[row["recipe_id"]].append(row)
    sizes, legs, build_drops = legs_from_staging(STAGING, PACKETS, rules, fixes)
    staging = {name: sha256((STAGING / name).read_bytes()) for name in STAGING_INPUTS}
    tables = (WAVE1_CSV, FIRST_BUILD, CORRECTIONS) if reviews else (WAVE1_CSV, FIRST_BUILD)
    committed = {f"data/enrichment/{path.name}": table_sha256(path) for path in tables}
    for part in ("A", "B", "C"):
        staging[f"enrichment-work/part-{part}/recipes.input.jsonl"] = sha256(
            (PACKETS / f"part-{part}" / "recipes.input.jsonl").read_bytes()
        )
    inputs = {
        "v2_1_sha256": {n: sha256((V21 / n).read_bytes()) for n in ("recipes.jsonl", "ingredients.jsonl")},
        "v2_2_sha256": {
            n: sha256((V22 / n).read_bytes()) for n in ("recipes.jsonl", "ingredients.jsonl", "release_manifest.json")
        },
        "staging_sha256": staging,
        "committed_sha256": committed,
    }
    ingredients = (V22 / "ingredients.jsonl").read_bytes()
    files = assemble(
        v22_lines, ingredients, rules, sizes, legs, build_drops, inputs, first_build=read_first_build(), reviews=reviews
    )
    args.out.mkdir(parents=True, exist_ok=True)
    for name, data in files.items():
        (args.out / name).write_bytes(data)
    manifest = json.loads(files["release_manifest.json"])
    print(json.dumps({k: v for k, v in manifest["counts"].items() if not isinstance(v, dict)}))
    print(
        json.dumps(
            {"dropped_by_reason": manifest["counts"]["dropped_by_reason"], "fingerprint": manifest["fingerprint"]}
        )
    )
    return 0


if __name__ == "__main__":
    sys.exit(main())
