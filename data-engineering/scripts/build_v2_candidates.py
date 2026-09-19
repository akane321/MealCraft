"""Stage 2 of release v2: build the candidate pool and pick it by quota.

Sources, all converted to one candidate shape:
- the 9,282 recipes of release v1.1 (already parsed and mapped);
- other RecipeNLG `Gathered` rows whose triaged cuisine is not American
  (American dishes come from v1.1, which already has more than the quota);
- Wikibooks Cookbook pages and TheMealDB meals fetched by
  fetch_supplementary_sources.py, whose cuisine comes from their own category or area.

A candidate must parse: the recipe has steps; at most MAX_UNQUANTIFIED
ingredient lines lack a usable quantity and unit ("salt to taste", "oil for
frying", "juice of 2 lemons"), and those get an estimated amount with evidence
during enrichment; and at most MAX_UNMAPPED lines name an ingredient outside the
current alias table (those names drive the vocabulary extension in stage 3). Servings may be missing; they
are filled with evidence during enrichment (ADR-0030).

Duplicates are removed by normalized title plus ingredient names. Each quota
bucket then takes `target x candidate_oversample` candidates, split by course so
the release can meet the course mix, preferring curated sources, then recipes
with fewer unmapped lines, then a seeded shuffle.

Outputs:
- data/staging/v2_candidates.jsonl   full candidate records (git-ignored)
- data/enrichment/v2_candidates.csv  the selected ids with source and triage (committed)
- data/enrichment/v2_candidates_summary.json  supply, selection and unmapped names (committed)

Run: python scripts/build_v2_candidates.py
"""

from __future__ import annotations

import collections
import csv
import hashlib
import html
import json
import random
import re
import sys
import time
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))
sys.path.insert(0, str(ROOT / "scripts"))

from mealcraft_data.config import load_config  # noqa: E402
from mealcraft_data.parsing import parse_ingredient  # noqa: E402
from mealcraft_data.pipeline import _is_note_only  # noqa: E402
from mealcraft_data.servings import extract_servings  # noqa: E402
from v2_triage import course_of, cuisine_of  # noqa: E402

RAW = ROOT / "data" / "raw"
RELEASE_V11 = ROOT / "data" / "release" / "v1.1" / "recipes.jsonl"
QUOTAS = json.loads((ROOT / "config" / "v2_quotas.json").read_text(encoding="utf-8"))
SEED = 5105
MAX_UNMAPPED = 3
MAX_UNQUANTIFIED = 3
MIN_INGREDIENTS, MAX_INGREDIENTS = 3, 25
QUANTIFIED = {"mass", "volume", "count"}
SOURCE_PRIORITY = {"wikibooks": 0, "themealdb": 1, "recipenlg_v1.1": 2, "recipenlg": 3}

LICENCES = {
    "recipenlg": "RecipeNLG: non-commercial research and educational use only",
    "wikibooks": "CC BY-SA 4.0 (Wikibooks Cookbook)",
    "themealdb": "TheMealDB terms of use (attribution; non-commercial course use)",
}

MEALDB_AREA = {
    "Chinese": "chinese",
    "Japanese": "japanese",
    "Thai": "thai",
    "Vietnamese": "vietnamese",
    "Malaysian": "malaysian_singaporean",
    "Filipino": "filipino",
    "India": "indian",
    "Indian": "indian",
    "Turkish": "turkish",
    "Saudi Arabian": "middle_eastern",
    "Syrian": "middle_eastern",
    "Egyptian": "north_african",
    "Moroccan": "north_african",
    "Algerian": "north_african",
    "Tunisian": "north_african",
    "Italian": "italian",
    "France": "french",
    "French": "french",
    "Spanish": "spanish_portuguese",
    "Portuguese": "spanish_portuguese",
    "Greek": "greek",
    "Polish": "eastern_european",
    "Russian": "eastern_european",
    "Ukrainian": "eastern_european",
    "Croatian": "eastern_european",
    "Slovakia": "eastern_european",
    "British": "british_irish",
    "Irish": "british_irish",
    "Norway": "scandinavian",
    "Netherlands": "german",
    "United States": "american",
    "American": "american",
    "Canadian": "american",
    "Australian": "british_irish",
    "Mexican": "mexican",
    "Jamaican": "caribbean",
    "Argentina": "latin_american",
    "Venezuela": "latin_american",
    "Uruguayan": "latin_american",
    "Kenyan": "african",
}
WIKIBOOKS_CATEGORY = {
    "Chinese recipes": "chinese",
    "Japanese recipes": "japanese",
    "Korean recipes": "korean",
    "Malaysian recipes": "malaysian_singaporean",
    "Singaporean recipes": "malaysian_singaporean",
    "Indonesian recipes": "indonesian",
    "Thai recipes": "thai",
    "Vietnamese recipes": "vietnamese",
    "Filipino recipes": "filipino",
    "Indian recipes": "indian",
    "Middle Eastern recipes": "middle_eastern",
    "Lebanese recipes": "middle_eastern",
    "Turkish recipes": "turkish",
    "Iranian recipes": "middle_eastern",
    "Israeli recipes": "middle_eastern",
    "Arab recipes": "middle_eastern",
    "Moroccan recipes": "north_african",
    "Egyptian recipes": "north_african",
}

CONFIG = load_config(ROOT)


# --------------------------------------------------------------------------- parsing
def parse_lines(lines: list[str], ner: list[str] | None = None) -> tuple[list[dict], dict] | None:
    """Parse ingredient lines; return (items, stats) or None if the recipe fails the relaxed gate."""
    items = []
    for line in lines:
        parsed = parse_ingredient(line, CONFIG, ner)
        if _is_note_only(parsed):
            continue
        items.append(parsed)
    if not MIN_INGREDIENTS <= len(items) <= MAX_INGREDIENTS:
        return None
    unmapped = [p.ingredient_text for p in items if p.normalization_status != "mapped"]
    if len(unmapped) > MAX_UNMAPPED:
        return None
    unquantified = [p.original_text for p in items if p.quantity_min is None or p.unit_dimension not in QUANTIFIED]
    if len(unquantified) > MAX_UNQUANTIFIED:
        return None
    return [p.to_dict() for p in items], {"unmapped": unmapped, "unquantified": unquantified}


def candidate(
    source: str,
    source_id: str,
    title: str,
    url: str | None,
    lines: list[str],
    steps: list[str],
    cuisine: str,
    cuisine_basis: str,
    servings,
    servings_basis,
    ner=None,
    extra=None,
) -> dict | None:
    title = re.sub(r"\s+", " ", title).strip()
    steps = [s.strip() for s in steps if s and s.strip()]
    if not title or not steps or sum(len(s) for s in steps) < 40:
        return None
    parsed = parse_lines(lines, ner)
    if parsed is None:
        return None
    items, stats = parsed
    licence_key = "recipenlg" if source.startswith("recipenlg") else source
    return {
        "candidate_id": f"{source}:{source_id}",
        "source": source,
        "source_id": source_id,
        "source_url": url,
        "source_license": LICENCES[licence_key],
        "title": title,
        "ingredients": items,
        "instructions": [{"step_number": i, "text": s} for i, s in enumerate(steps, 1)],
        "servings": servings,
        "servings_basis": servings_basis,
        "triage": {"cuisine": cuisine, "cuisine_basis": cuisine_basis, "course": course_of(title)},
        "unmapped": stats["unmapped"],
        "unquantified": stats["unquantified"],
        **(extra or {}),
    }


# --------------------------------------------------------------------------- sources
def from_release_v11() -> list[dict]:
    out = []
    with RELEASE_V11.open(encoding="utf-8") as handle:
        for line in handle:
            recipe = json.loads(line)
            text = " ".join(i["original_text"] for i in recipe["ingredients"])
            cuisine, basis = cuisine_of(recipe["title"], text)
            out.append(
                {
                    "candidate_id": f"recipenlg_v1.1:{recipe['recipe_id']}",
                    "source": "recipenlg_v1.1",
                    "source_id": recipe["recipe_id"],
                    "source_url": recipe["source"].get("source_url"),
                    "source_row": recipe["source"].get("source_row"),
                    "source_license": LICENCES["recipenlg"],
                    "title": recipe["title"],
                    "ingredients": recipe["ingredients"],
                    "instructions": [
                        {"step_number": s["step_number"], "text": s["text"]} for s in recipe["instructions"]
                    ],
                    "servings": recipe["servings"],
                    "servings_basis": recipe["servings_basis"],
                    "triage": {"cuisine": cuisine, "cuisine_basis": basis, "course": course_of(recipe["title"])},
                    "unmapped": [],
                    "unquantified": [],
                }
            )
    return out


def from_recipenlg(skip_rows: set[int]) -> tuple[list[dict], collections.Counter]:
    csv.field_size_limit(10**9)
    out, seen = [], collections.Counter()
    with (RAW / "recipenlg" / "full_dataset.csv").open(encoding="utf-8", newline="") as handle:
        reader = csv.reader(handle)
        next(reader)
        for row in reader:
            row_number, title, ingredients, directions, link, source, ner = row
            if source != "Gathered" or int(row_number) in skip_rows:
                continue
            lines = json.loads(ingredients)
            cuisine, basis = cuisine_of(title, " ".join(lines))
            if cuisine == "american":
                continue
            seen[cuisine] += 1
            steps = json.loads(directions)
            servings = extract_servings(" ".join(steps))
            record = candidate(
                "recipenlg",
                row_number,
                title,
                link or None,
                lines,
                steps,
                cuisine,
                basis,
                servings.value if servings else None,
                servings.basis if servings else None,
                ner=json.loads(ner),
                extra={"source_row": int(row_number)},
            )
            if record:
                out.append(record)
    return out, seen


def from_themealdb() -> list[dict]:
    out = []
    for meal in json.loads((RAW / "themealdb" / "themealdb.json").read_text(encoding="utf-8")):
        cuisine = MEALDB_AREA.get(meal.get("strArea") or "")
        if not cuisine:
            continue
        lines = [
            f"{(meal.get(f'strMeasure{i}') or '').strip()} {(meal.get(f'strIngredient{i}') or '').strip()}".strip()
            for i in range(1, 21)
            if (meal.get(f"strIngredient{i}") or "").strip()
        ]
        steps = [
            s
            for s in re.split(r"\r?\n+", meal.get("strInstructions") or "")
            if s.strip() and not re.fullmatch(r"\s*(step\s*)?\d+\.?\s*", s, re.I)
        ]
        record = candidate(
            "themealdb",
            meal["idMeal"],
            meal["strMeal"],
            f"https://www.themealdb.com/meal/{meal['idMeal']}",
            lines,
            steps,
            cuisine,
            "source_area",
            None,
            None,
            extra={"video_url": meal.get("strYoutube") or None},
        )
        if record:
            out.append(record)
    return out


LINK = re.compile(r"\[\[(?:[^|\]]*\|)?([^\]]*)\]\]")


def clean_wikitext(text: str) -> str:
    text = re.sub(r"<ref[^>]*?/>|<ref.*?</ref>", "", text, flags=re.S)
    text = re.sub(r"\[\[(?:File|Image):[^\]]*\]\]", "", text)
    text = LINK.sub(r"\1", text)
    text = re.sub(r"\{\{[^{}]*\}\}", "", text)
    text = re.sub(r"'{2,}", "", text)
    text = re.sub(r"<[^>]+>", "", text)
    return html.unescape(text).strip()


def wikibooks_section(text: str, names: str) -> list[str]:
    match = re.search(rf"^==\s*(?:{names})\s*==\s*$", text, re.I | re.M)
    if not match:
        return []
    rest = text[match.end() :]
    end = re.search(r"^==[^=].*?[^=]==\s*$", rest, re.M)
    return (rest[: end.start()] if end else rest).splitlines()


def from_wikibooks() -> list[dict]:
    out = []
    for page in json.loads((RAW / "wikibooks" / "wikibooks.json").read_text(encoding="utf-8")):
        categories = [c for c in page["fetched_from_categories"] if c in WIKIBOOKS_CATEGORY]
        cuisine = WIKIBOOKS_CATEGORY[categories[0]] if categories else None
        if not cuisine:
            continue
        text = page["wikitext"]
        lines = [
            clean_wikitext(line.lstrip("*").strip())
            for line in wikibooks_section(text, r"ingredients?")
            if line.lstrip().startswith("*")
        ]
        steps = [
            clean_wikitext(line.lstrip("#").strip())
            for line in wikibooks_section(text, r"procedure|directions?|method|preparation|instructions?")
            if line.lstrip().startswith("#")
        ]
        servings = None
        summary = re.search(r"\|\s*(?:servings|yield)\s*=\s*(\d+)", text, re.I)
        if summary and 0 < int(summary.group(1)) <= 100:
            servings = int(summary.group(1))
        title = page["title"].removeprefix("Cookbook:")
        record = candidate(
            "wikibooks",
            str(page["pageid"]),
            title,
            page["url"],
            [x for x in lines if x],
            steps,
            cuisine,
            "source_category",
            servings,
            "stated_exact" if servings else None,
            extra={"source_revision": page["revid"]},
        )
        if record:
            out.append(record)
    return out


# --------------------------------------------------------------------------- selection
def dedupe_key(record: dict) -> str:
    title = " ".join(sorted(re.findall(r"[a-z]+", record["title"].casefold())))
    names = sorted({(i.get("canonical_ingredient_id") or i["ingredient_text"]) for i in record["ingredients"]})
    return hashlib.sha1(f"{title}|{'|'.join(names)}".encode()).hexdigest()


def course_group(course: str) -> str:
    for group, spec in QUOTAS["course_mix"].items():
        if not group.startswith("_") and course in spec.get("courses", [group]):
            return group
    return "main"


def select(pool: list[dict], factor: float | None = None) -> list[dict]:
    """Pick each bucket by course mix; `factor` overrides every bucket's oversample."""
    rng = random.Random(SEED)
    rng.shuffle(pool)
    basis_rank = {"source_category": 0, "source_area": 0, "title": 0, "ingredients": 1, "default": 2}
    pool.sort(
        key=lambda r: (
            SOURCE_PRIORITY[r["source"]],
            basis_rank[r["triage"]["cuisine_basis"]],
            len(r["unmapped"]) + len(r["unquantified"]),
        )
    )
    bucket_of = {c: b for b, spec in QUOTAS["buckets"].items() for c in spec["cuisines"]}
    shares = {"main": 0.50, "side_soup_salad": 0.25, "breakfast": 0.08, "dessert_baked": 0.10, "other": 0.07}
    by_bucket: dict[str, list[dict]] = collections.defaultdict(list)
    for record in pool:
        by_bucket[bucket_of[record["triage"]["cuisine"]]].append(record)
    chosen = []
    for bucket, spec in QUOTAS["buckets"].items():
        want = round(spec["target"] * (factor or spec.get("oversample", QUOTAS["candidate_oversample"])))
        records = by_bucket.get(bucket, [])
        groups = collections.defaultdict(list)
        for record in records:
            groups[course_group(record["triage"]["course"])].append(record)
        picked = []
        for group, share in shares.items():
            picked += groups[group][: round(want * share)]
        # Fill what a thin course group left over with mains, then sides, never desserts or extras.
        taken = {r["candidate_id"] for r in picked}
        for group in ("main", "side_soup_salad", "breakfast"):
            for record in groups[group]:
                if len(picked) >= want:
                    break
                if record["candidate_id"] not in taken:
                    picked.append(record)
                    taken.add(record["candidate_id"])
        for record in picked:
            record["quota_bucket"] = bucket
        chosen += picked
    return chosen


def main() -> int:
    start = time.monotonic()
    staging = ROOT / "data" / "staging"
    staging.mkdir(parents=True, exist_ok=True)
    pool_path = staging / "v2_pool.jsonl"
    if "--reuse-pool" in sys.argv and pool_path.exists():
        cached = json.loads(pool_path.read_text(encoding="utf-8").split("\n", 1)[0])
        pool = [json.loads(line) for line in pool_path.read_text(encoding="utf-8").splitlines()[1:] if line]
        return finish(pool, cached, start)
    v11 = from_release_v11()
    skip_rows = {r["source_row"] for r in v11 if r.get("source_row") is not None}
    print(f"v1.1: {len(v11)}", flush=True)
    wiki = from_wikibooks()
    meal = from_themealdb()
    print(f"wikibooks: {len(wiki)}  themealdb: {len(meal)}", flush=True)
    nlg, triaged = from_recipenlg(skip_rows)
    print(
        f"recipenlg non-american candidates: {len(nlg)} passed of {sum(triaged.values())} triaged "
        f"({time.monotonic() - start:.0f}s)",
        flush=True,
    )

    pool, seen, duplicates = [], set(), 0
    for record in sorted(wiki + meal + v11 + nlg, key=lambda r: SOURCE_PRIORITY[r["source"]]):
        key = dedupe_key(record)
        if key in seen:
            duplicates += 1
            continue
        seen.add(key)
        pool.append(record)

    counts = {
        "sources_passing_gate": {
            "recipenlg_v1.1": len(v11),
            "recipenlg_new": len(nlg),
            "wikibooks": len(wiki),
            "themealdb": len(meal),
        },
        "recipenlg_triaged_non_american": dict(triaged.most_common()),
        "duplicates_removed": duplicates,
    }
    with pool_path.open("w", encoding="utf-8", newline="\n") as out:
        out.write(json.dumps(counts) + "\n")
        for record in pool:
            out.write(json.dumps(record, ensure_ascii=False) + "\n")
    return finish(pool, counts, start)


def finish(pool: list[dict], counts: dict, start: float) -> int:
    chosen = select(pool)
    staging = ROOT / "data" / "staging"
    with (staging / "v2_candidates.jsonl").open("w", encoding="utf-8", newline="\n") as out:
        for record in chosen:
            out.write(json.dumps(record, ensure_ascii=False, sort_keys=True) + "\n")
    enrichment = ROOT / "data" / "enrichment"
    with (enrichment / "v2_candidates.csv").open("w", encoding="utf-8", newline="") as out:
        writer = csv.writer(out, lineterminator="\n")
        writer.writerow(
            [
                "candidate_id",
                "source",
                "quota_bucket",
                "triage_cuisine",
                "triage_cuisine_basis",
                "triage_course",
                "unmapped_lines",
                "unquantified_lines",
                "title",
            ]
        )
        for r in sorted(chosen, key=lambda r: r["candidate_id"]):
            writer.writerow(
                [
                    r["candidate_id"],
                    r["source"],
                    r["quota_bucket"],
                    r["triage"]["cuisine"],
                    r["triage"]["cuisine_basis"],
                    r["triage"]["course"],
                    len(r["unmapped"]),
                    len(r["unquantified"]),
                    r["title"],
                ]
            )

    supply = collections.Counter(r["triage"]["cuisine"] for r in pool)
    unmapped = collections.Counter(name for r in chosen for name in r["unmapped"])
    summary = {
        "seed": SEED,
        **counts,
        "pool_by_cuisine": dict(supply.most_common()),
        "selected_total": len(chosen),
        "selected_by_bucket": {
            b: {"target": s["target"], "selected": sum(1 for r in chosen if r["quota_bucket"] == b)}
            for b, s in QUOTAS["buckets"].items()
        },
        "selected_by_source": dict(collections.Counter(r["source"] for r in chosen).most_common()),
        "selected_by_course": dict(collections.Counter(r["triage"]["course"] for r in chosen).most_common()),
        "selected_with_unmapped": sum(1 for r in chosen if r["unmapped"]),
        "selected_missing_servings": sum(1 for r in chosen if not r["servings"]),
        "selected_with_unquantified": sum(1 for r in chosen if r["unquantified"]),
        "distinct_unmapped_names": len(unmapped),
        "top_unmapped_names": unmapped.most_common(300),
    }
    (enrichment / "v2_candidates_summary.json").write_text(
        json.dumps(summary, ensure_ascii=False, indent=1) + "\n", encoding="utf-8", newline="\n"
    )
    print(json.dumps({k: v for k, v in summary.items() if k != "top_unmapped_names"}, indent=1))
    print(f"done in {time.monotonic() - start:.0f}s")
    return 0


if __name__ == "__main__":
    sys.exit(main())
