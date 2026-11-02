"""Data release v3, step 1: pick the new RecipeNLG candidates (Knowledge ADR-0103 section 3, MealCraft issue #390).

    python scripts/select_v3_candidates.py [--total 12400] [--loss 0.25]

Release v3 is every release v2.2 recipe, verbatim, plus recipes added from two places: the built-but-over-quota
v2.1 recipes (rebuilt with the current rules, then the v2.2 unit-weight corrections), and new candidates picked
here from `data/staging/v2_pool.jsonl` that were never selected in v2. This script computes how many new ones are
needed and picks them. Everything is deterministic: a fixed hash order, no clock.

A pool candidate qualifies when, in this order:

1. it was not selected for v2 (not in `v2_candidates.jsonl`) and its triage cuisine is neither `american` nor in the
   American bucket (`southern_us`, `cajun_creole`): those families are already near the cap through the over-quota leg;
2. every ingredient line maps to an ingredient of release v2.2, directly or through the stage-3 decisions
   (`prepare_v2_inputs.resolve_lines`), so v3 adds no ingredient id;
3. every line's ingredient form exists in the v2.2 `ingredients.jsonl` and every quantified line converts to grams, so
   the build cannot fail for weight;
4. every ingredient is priced by the planner's own rule (`priceable_names`, the committed files that
   `backend/app/planning/grocery_estimator.py priceable_ingredients()` reads);
5. its lower-cased, whitespace-normalised title is not a title already in v2.2 or in the over-quota leg;
6. the completeness check does not flag it, or a review kept it (an unreviewed flagged recipe is dropped, as in the
   build).

New candidates are shared out over the quota buckets of `config/v2_quotas.json` (the American bucket gets none), in
proportion to their targets and capped by supply, so no label approaches the 20% cap. Local Malaysian and Singaporean
candidates that qualify are all taken. Within a bucket mains come first and other courses only when the mains run
out (sides, soups, salads and breakfasts before the rest), then recipes whose servings the source states, then a
fixed hash order.

Outputs: `data/staging/v3_selected.jsonl` (git-ignored; candidate records in the shape of `v2_enrich_set.jsonl`),
and committed `data/enrichment/v3_selection_summary.json` and `v3_selected.csv`.
"""

from __future__ import annotations

import argparse
import collections
import csv
import hashlib
import json
import math
import re
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "scripts"))

import build_release_v2 as build  # noqa: E402
import correct_release_v22 as correct  # noqa: E402
from build_v2_candidates import QUOTAS, course_group  # noqa: E402
from prepare_v2_inputs import alias_corrections, needs_amount, read_jsonl, resolve_lines  # noqa: E402
from recipe_completeness import kept_by_review, reviews, unlisted_allergens  # noqa: E402
from v2_vocab import resolver  # noqa: E402

STAGING = ROOT / "data" / "staging"
POOL = STAGING / "v2_pool.jsonl"
CANDIDATES = STAGING / "v2_candidates.jsonl"
SELECTED = STAGING / "v3_selected.jsonl"
ENRICHMENT = ROOT / "data" / "enrichment"
SUMMARY = ENRICHMENT / "v3_selection_summary.json"
SELECTED_CSV = ENRICHMENT / "v3_selected.csv"
V22 = ROOT / "data" / "release" / "v2.2"
PRODUCTS = ROOT.parent / "data" / "products"
CURATED = ROOT.parent / "data" / "ingredients" / "ingredients.json"
SEED = "v3-5105"
CAP = 0.20
AMERICAN_BUCKET = "american"
LOCAL = "malaysian_singaporean"
# Over-quota recipes above a label's cap: the ones a planner can use come first.
KEEP_ORDER = ("main", "side", "soup", "salad", "breakfast")


def title_key(title: str) -> str:
    return re.sub(r"\s+", " ", title.lower()).strip()


def priceable_names() -> frozenset[str]:
    """`priceable_ingredients()` of the backend, read from the files it reads (no console overrides)."""
    curated = {item["normalized_name"] for item in json.loads(CURATED.read_text(encoding="utf-8"))}
    names = set(curated)
    for file, wanted in (("fairprice-v2-snapshot.json", None), ("cold-storage-v1-snapshot.json", "mapped")):
        entries = json.loads((PRODUCTS / file).read_text(encoding="utf-8"))["ingredients"]
        names |= {n for n, e in entries.items() if (e["status"] == wanted if wanted else e["status"] != "removed")}
    return frozenset(names)


def priced(ingredient_id: str, names: frozenset[str]) -> bool:
    """The importer's `normalized_name` of a release ingredient id, looked up in the priceable names."""
    return ingredient_id[4:].lower() in names


class Context:
    """What every check reads, loaded once."""

    def __init__(self) -> None:
        self.v22 = read_jsonl(V22 / "recipes.jsonl")
        self.entries = {row["ingredient_id"]: row for row in read_jsonl(V22 / "ingredients.jsonl")}
        self.forms = {key: form for row in self.entries.values() for key, form in row["forms"].items()}
        self.rules = build.ingredient_rules()
        self.priceable = priceable_names()
        self.titles = {title_key(r["title"]) for r in self.v22}


# ---------------------------------------------------------------------------------------- over-quota leg
def over_quota(ctx: Context) -> tuple[list[dict], dict]:
    """The built v2.1 recipes outside v2.2 that v3 may add, v2.2-corrected, in recipe_id order, with the funnel."""
    enrich_set = {r["candidate_id"]: r for r in read_jsonl(STAGING / "v2_enrich_set.jsonl")}
    for part in "ABC":
        for item in read_jsonl(ROOT / "enrichment-work" / f"part-{part}" / "recipes.input.jsonl"):
            if item["candidate_id"] in enrich_set:
                enrich_set[item["candidate_id"]]["stated_durations"] = item.get("stated_durations") or []
    results = {r["candidate_id"]: r for r in read_jsonl(STAGING / "v2_merged.recipes.jsonl")}
    forms = {r["ingredient_id"]: r for r in read_jsonl(STAGING / "v2_merged.ingredients.jsonl")}
    released = {r["recipe_id"] for r in ctx.v22}
    funnel: collections.Counter = collections.Counter()
    kept, titles = [], set(ctx.titles)
    built = []
    for candidate_id, record in enrich_set.items():
        result = results.get(candidate_id)
        if result is None or "exclude" in result:
            continue
        recipe, _ = build.build_recipe(record, result, forms, ctx.rules)
        if recipe is not None:
            built.append(recipe)
    funnel["built with the current rules"] = len(built)
    for recipe in sorted((r for r in built if r["recipe_id"] not in released), key=lambda r: r["recipe_id"]):
        funnel["built and not in v2.2"] += 1
        if not {line["canonical_ingredient_id"] for line in recipe["ingredients"]} <= set(ctx.entries):
            funnel["excluded: ingredient id not in v2.2"] += 1
        elif recipe["cuisine"] == "international":
            funnel["excluded: cuisine international"] += 1
        else:
            try:
                recipe, _ = correct.correct_recipe(recipe, ctx.forms, ctx.entries)
            except KeyError:
                funnel["excluded: ingredient form not in v2.2"] += 1
                continue
            kcal = recipe["nutrition"]["energy_kcal"]
            if not build.ENERGY_PER_SERVING[0] <= kcal <= build.ENERGY_PER_SERVING[1]:
                funnel["excluded: energy after the v2.2 correction"] += 1
            elif title_key(recipe["title"]) in titles:
                funnel["excluded: title already in the release"] += 1
            else:
                titles.add(title_key(recipe["title"]))
                kept.append(recipe)
    funnel["kept"] = len(kept)
    return kept, dict(funnel)


def cap_by_label(base: collections.Counter, added: list[dict], limit: int) -> tuple[list[dict], collections.Counter]:
    """Keep `added` recipes so no cuisine label passes `limit`; over a label's room, usable courses stay first."""
    rank = {course: i for i, course in enumerate(KEEP_ORDER)}
    by_label = collections.defaultdict(list)
    for recipe in added:
        by_label[recipe["cuisine"]].append(recipe)
    kept, cut = [], collections.Counter()
    for label, recipes in by_label.items():
        room = max(limit - base[label], 0)
        ordered = sorted(recipes, key=lambda r: (rank.get(r["course"], len(rank)), r["recipe_id"]))
        kept += ordered[:room]
        cut[label] = len(ordered) - len(ordered[:room])
    return sorted(kept, key=lambda r: r["recipe_id"]), +cut


# ------------------------------------------------------------------------------------------- pool scan
def weighs(record: dict, forms: dict[str, dict]) -> bool:
    """Every line has an ingredient form, and a quantified line converts to grams: the build cannot fail for weight."""
    for line in record["ingredients"]:
        form = forms.get(correct.form_key(line))
        if form is None:
            return False
        if (
            not needs_amount(line)
            and build.line_grams(line, {u["unit"]: u["grams"] for u in form["unit_grams"]}, None)[0] is None
        ):
            return False
    return True


def qualifies(record: dict, ctx: Context, resolve, corrections: dict, taken: set[str]) -> str | None:
    """Why the pool record is not a v3 candidate (None: it qualifies); resolves its lines in place."""
    triage = record["triage"]["cuisine"]
    if triage == "american" or triage in QUOTAS["buckets"][AMERICAN_BUCKET]["cuisines"]:
        return "american bucket"
    if resolve_lines(record, resolve, corrections) is not None:
        return "unmapped ingredient name"
    ids = {line["canonical_ingredient_id"] for line in record["ingredients"]}
    if not ids <= set(ctx.entries):
        return "ingredient id not in v2.2"
    if any(ctx.rules[i]["allergen_status"] != "confirmed" for i in ids):
        return "allergen rule not confirmed"
    if not all(priced(i, ctx.priceable) for i in ids):
        return "unpriced ingredient"
    if not weighs(record, ctx.forms):
        return "no ingredient form or unit weight"
    if title_key(record["title"]) in taken:
        return "title already in the release"
    recipe_id = "RCP2_" + hashlib.sha256(record["candidate_id"].encode()).hexdigest()[:12].upper()
    listed = {a for line in record["ingredients"] for a in ctx.rules[line["canonical_ingredient_id"]]["allergens"]}
    reviewed = reviews().get(recipe_id)
    flagged = unlisted_allergens(record, listed)
    if (reviewed is not None and reviewed["verdict"] == "incomplete") or (flagged and not kept_by_review(recipe_id)):
        return "completeness flagged"
    return None


def order_key(row: dict) -> tuple:
    digest = hashlib.sha256(f"{SEED}:{row['candidate_id']}".encode()).hexdigest()
    usable = {"main": 0, "side_soup_salad": 1, "breakfast": 1}  # then desserts, snacks, sauces and drinks
    return (usable.get(row["course"], 2), row["servings"] is None, digest)


def scan_pool(ctx: Context, taken: set[str]) -> tuple[list[dict], collections.Counter]:
    """One light row per qualifying pool record (with its byte offset), and why the others did not qualify."""
    resolve, corrections = resolver(), alias_corrections()
    selected_before = {json.loads(line)["candidate_id"] for line in CANDIDATES.open(encoding="utf-8")}
    bucket_of = {c: b for b, spec in QUOTAS["buckets"].items() for c in spec["cuisines"]}
    rows, why = [], collections.Counter()
    with POOL.open("rb") as handle:
        handle.readline()  # the summary header
        while True:
            offset = handle.tell()
            line = handle.readline()
            if not line:
                break
            record = json.loads(line)
            if record["candidate_id"] in selected_before:
                why["selected for v2"] += 1
                continue
            reason = qualifies(record, ctx, resolve, corrections, taken)
            if reason:
                why[reason] += 1
                continue
            why["qualifies"] += 1
            cuisine = record["triage"]["cuisine"]
            rows.append(
                {
                    "candidate_id": record["candidate_id"],
                    "offset": offset,
                    "cuisine": cuisine,
                    "bucket": bucket_of[cuisine],
                    "course": course_group(record["triage"]["course"]),
                    "triage_course": record["triage"]["course"],
                    "servings": record["servings"],
                    "source": record["source"],
                    "title": title_key(record["title"]),
                }
            )
    return rows, why


# ----------------------------------------------------------------------------------------- allocation
def allocate(rows: list[dict], count: int) -> list[dict]:
    """Share `count` picks out over the non-American buckets by their v2 targets, capped by supply."""
    pools: dict[str, list[dict]] = collections.defaultdict(list)
    for row in sorted(rows, key=order_key):
        pools[row["bucket"]].append(row)
    weight = {b: spec["target"] for b, spec in QUOTAS["buckets"].items() if b != AMERICAN_BUCKET}
    picked: list[dict] = []
    titles: set[str] = set()

    def take(bucket: str, limit: int) -> int:
        taken = 0
        pool = pools[bucket]
        while pool and taken < limit:
            row = pool.pop(0)
            if row["title"] not in titles:
                titles.add(row["title"])
                picked.append(row)
                taken += 1
        return taken

    # Local Malaysian and Singaporean dishes are always taken when they qualify.
    local = [r for r in pools["southeast_asian"] if r["cuisine"] == LOCAL]
    pools["southeast_asian"] = [r for r in pools["southeast_asian"] if r["cuisine"] != LOCAL]
    for row in local:
        if row["title"] not in titles:
            titles.add(row["title"])
            picked.append(row)
    remaining = count - len(picked)
    active = {b for b in weight if pools[b]}
    while remaining > 0 and active:
        total = sum(weight[b] for b in active)
        quotas = {b: max(1, math.floor(remaining * weight[b] / total)) for b in sorted(active)}
        for bucket, quota in quotas.items():
            remaining -= take(bucket, min(quota, remaining))
            if not pools[bucket]:
                active.discard(bucket)
            if remaining <= 0:
                break
    return sorted(picked, key=lambda r: r["candidate_id"])


def tally(values) -> dict:
    return dict(collections.Counter(values).most_common())


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument(
        "--total", type=int, default=12400, help="target size of release v3 (ADR-0103 asks for 12,000+)"
    )
    parser.add_argument("--loss", type=float, default=0.25, help="share of new candidates assumed lost in enrichment")
    args = parser.parse_args()

    ctx = Context()
    added, funnel = over_quota(ctx)
    base = collections.Counter(r["cuisine"] for r in ctx.v22)
    limit = int(CAP * args.total)
    kept, cut = cap_by_label(base, added, limit)
    need = args.total - len(ctx.v22) - len(kept)
    count = math.ceil(need / (1 - args.loss))
    print(f"v2.2 {len(ctx.v22)} + over-quota {len(added)} (after the {limit} label cap {len(kept)}) -> need {need} new")
    print(f"selecting {count} to allow a {args.loss:.0%} loss in enrichment and build")

    taken = ctx.titles | {title_key(r["title"]) for r in added}
    rows, why = scan_pool(ctx, taken)
    picked = allocate(rows, count)
    print(f"qualifying pool candidates {len(rows)}; picked {len(picked)}")

    records = []
    resolve, corrections = resolver(), alias_corrections()
    with POOL.open("rb") as handle:
        for row in sorted(picked, key=lambda r: r["offset"]):
            handle.seek(row["offset"])
            record = json.loads(handle.readline())
            assert record["candidate_id"] == row["candidate_id"]
            assert resolve_lines(record, resolve, corrections) is None
            record["quota_bucket"] = row["bucket"]
            records.append(record)
    records.sort(key=lambda r: r["candidate_id"])
    SELECTED.write_text(
        "".join(json.dumps(r, ensure_ascii=False, sort_keys=True) + "\n" for r in records),
        encoding="utf-8",
        newline="\n",
    )
    with SELECTED_CSV.open("w", encoding="utf-8", newline="") as out:
        writer = csv.writer(out, lineterminator="\n")
        writer.writerow(["candidate_id", "source", "triage_cuisine", "triage_course", "quota_bucket"])
        for r in records:
            writer.writerow(
                [r["candidate_id"], r["source"], r["triage"]["cuisine"], r["triage"]["course"], r["quota_bucket"]]
            )

    final = collections.Counter(base)
    final.update(r["cuisine"] for r in kept)
    final.update(r["triage"]["cuisine"] for r in records)
    summary = {
        "parameters": {"total": args.total, "assumed_loss": args.loss, "label_cap": CAP, "seed": SEED},
        "projection": {
            "v2_2_recipes": len(ctx.v22),
            "over_quota_funnel": funnel,
            "over_quota_cut_by_label_cap": dict(cut),
            "over_quota_added": len(kept),
            "label_cap_recipes": limit,
            "new_needed": need,
            "new_selected": len(records),
            "largest_label_share_if_all_selected_keep_their_triage_label": {
                label: round(n / args.total, 4) for label, n in final.most_common(3)
            },
        },
        "pool_scan": dict(why.most_common()),
        "qualifying": {
            "by_bucket": tally(r["bucket"] for r in rows),
            "mains": sum(r["course"] == "main" for r in rows),
        },
        "selected": {
            "by_triage_cuisine": tally(r["triage"]["cuisine"] for r in records),
            "by_quota_bucket": tally(r["quota_bucket"] for r in records),
            "by_triage_course": tally(r["triage"]["course"] for r in records),
            "by_source": tally(r["source"] for r in records),
            "servings_stated": sum(r["servings"] is not None for r in records),
            "malaysian_singaporean": sum(r["triage"]["cuisine"] == LOCAL for r in records),
        },
        "over_quota_added_by_cuisine": tally(r["cuisine"] for r in kept),
        "over_quota_added_by_course": tally(r["course"] for r in kept),
    }
    SUMMARY.write_text(json.dumps(summary, ensure_ascii=False, indent=2) + "\n", encoding="utf-8", newline="\n")
    print(json.dumps(summary, ensure_ascii=False, indent=1))
    return 0


if __name__ == "__main__":
    sys.exit(main())
