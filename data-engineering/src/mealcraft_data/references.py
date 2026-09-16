from __future__ import annotations

import csv
import difflib
import json
import os
import re
import time
import urllib.parse
import urllib.request
import zipfile
from pathlib import Path
from typing import Any

from .utils import read_jsonl, sha256_file, slugify, utc_now_iso, write_json

FOODON_SYNONYMS_URL = (
    "https://raw.githubusercontent.com/FoodOntology/foodon/master/foodon-synonyms.tsv"
)
FDC_SEARCH_URL = "https://api.nal.usda.gov/fdc/v1/foods/search"
USDA_FOUNDATION_URL = (
    "https://fdc.nal.usda.gov/fdc-datasets/"
    "FoodData_Central_foundation_food_csv_2026-04-30.zip"
)
USER_AGENT = "MealCraft-DSS5105-data-research/0.1"


def _download(url: str, output: Path) -> None:
    output.parent.mkdir(parents=True, exist_ok=True)
    request = urllib.request.Request(url, headers={"User-Agent": USER_AGENT})
    with urllib.request.urlopen(request, timeout=120) as response, output.open("wb") as handle:
        while chunk := response.read(1024 * 1024):
            handle.write(chunk)


def fetch_foodon(project_root: Path) -> dict[str, Any]:
    output = project_root / "data" / "reference" / "downloads" / "foodon-synonyms.tsv"
    _download(FOODON_SYNONYMS_URL, output)
    manifest = {
        "source": "FoodOn",
        "source_url": FOODON_SYNONYMS_URL,
        "license": "CC BY 4.0",
        "retrieved_at": utc_now_iso(),
        "local_path": str(output.relative_to(project_root)),
        "bytes": output.stat().st_size,
        "sha256": sha256_file(output),
    }
    write_json(project_root / "data" / "reference" / "foodon-manifest.json", manifest)
    return manifest


def fetch_usda_foundation(project_root: Path) -> dict[str, Any]:
    download_dir = project_root / "data" / "reference" / "downloads"
    archive = download_dir / "FoodData_Central_foundation_food_csv_2026-04-30.zip"
    extract_dir = download_dir / "usda-foundation-2026-04-30"
    _download(USDA_FOUNDATION_URL, archive)
    extract_dir.mkdir(parents=True, exist_ok=True)
    with zipfile.ZipFile(archive) as bundle:
        unsafe = [
            name
            for name in bundle.namelist()
            if Path(name).is_absolute() or ".." in Path(name).parts
        ]
        if unsafe:
            raise ValueError(f"Unsafe paths in USDA archive: {unsafe[:3]}")
        bundle.extractall(extract_dir)
    extracted_files = sorted(
        str(path.relative_to(project_root))
        for path in extract_dir.rglob("*")
        if path.is_file()
    )
    manifest = {
        "source": "USDA FoodData Central Foundation Foods",
        "source_url": USDA_FOUNDATION_URL,
        "source_version": "2026-04-30",
        "license": "CC0 1.0 / public domain",
        "retrieved_at": utc_now_iso(),
        "archive_path": str(archive.relative_to(project_root)),
        "archive_bytes": archive.stat().st_size,
        "archive_sha256": sha256_file(archive),
        "extracted_files": extracted_files,
    }
    write_json(project_root / "data" / "reference" / "usda-foundation-manifest.json", manifest)
    return manifest


def _singularize_token(token: str) -> str:
    irregular = {
        "tomatoes": "tomato",
        "potatoes": "potato",
        "leaves": "leaf",
        "loaves": "loaf",
        "knives": "knife",
    }
    if token in irregular:
        return irregular[token]
    if token.endswith("ies") and len(token) > 4:
        return token[:-3] + "y"
    if token.endswith("s") and not token.endswith(("ss", "us")) and len(token) > 3:
        return token[:-1]
    return token


def _normalized_food_name(value: str) -> str:
    value = value.casefold()
    value = re.sub(r"[^a-z0-9]+", " ", value)
    return " ".join(_singularize_token(token) for token in value.split())


def _food_similarity(query: str, description: str) -> float:
    query_form = _normalized_food_name(query)
    description_form = _normalized_food_name(description)
    if query_form == description_form:
        return 1.0
    query_tokens = set(query_form.split())
    description_tokens = set(description_form.split())
    overlap = len(query_tokens & description_tokens)
    token_recall = overlap / len(query_tokens) if query_tokens else 0.0
    token_precision = overlap / len(description_tokens) if description_tokens else 0.0
    sequence = difflib.SequenceMatcher(None, query_form, description_form).ratio()
    query_words = query_form.split()
    starts = 1.0 if description_form.split()[: len(query_words)] == query_words else 0.0
    score = 0.50 * token_recall + 0.15 * token_precision + 0.20 * sequence + 0.15 * starts
    processed = {"juice", "butter", "flour", "milk", "sauce", "powder", "oil"}
    if not (query_tokens & processed) and description_tokens & processed:
        score -= 0.20
    if "raw" in description_tokens and "raw" not in query_tokens:
        score += 0.08
    return max(0.0, min(1.0, score))


def create_usda_foundation_candidates(
    project_root: Path,
    ingredient_path: Path,
    foundation_dir: Path | None = None,
    limit: int | None = None,
) -> dict[str, Any]:
    foundation_dir = foundation_dir or (
        project_root / "data" / "reference" / "downloads" / "usda-foundation-2026-04-30"
    )
    food_files = list(foundation_dir.rglob("food.csv"))
    foundation_files = list(foundation_dir.rglob("foundation_food.csv"))
    if not food_files or not foundation_files:
        raise FileNotFoundError(
            "USDA Foundation Foods CSV files are missing; run fetch-usda-foundation first."
        )

    with foundation_files[0].open("r", encoding="utf-8-sig", newline="") as handle:
        foundation_ids = {row["fdc_id"] for row in csv.DictReader(handle)}
    foods: list[dict[str, str]] = []
    with food_files[0].open("r", encoding="utf-8-sig", newline="") as handle:
        for row in csv.DictReader(handle):
            if row["fdc_id"] in foundation_ids:
                foods.append(row)

    all_ingredients = read_jsonl(ingredient_path)
    ingredients = [
        ingredient
        for ingredient in all_ingredients
        if ingredient["mapping_status"] == "internal_mapped"
    ]
    if limit is not None:
        ingredients = ingredients[:limit]

    candidate_rows: list[dict[str, Any]] = []
    for ingredient in ingredients:
        scored = sorted(
            (
                (_food_similarity(ingredient["canonical_name"], food["description"]), food)
                for food in foods
            ),
            key=lambda item: (-item[0], item[1]["fdc_id"]),
        )
        scored = [item for item in scored if item[0] >= 0.35][:5]
        for rank, (score, food) in enumerate(scored, start=1):
            candidate_rows.append(
                {
                    "ingredient_id": ingredient["ingredient_id"],
                    "canonical_name": ingredient["canonical_name"],
                    "rank": rank,
                    "fdc_id": food["fdc_id"],
                    "description": food["description"],
                    "data_type": "Foundation",
                    "similarity": round(score, 4),
                    "publication_date": food.get("publication_date", ""),
                    "review_decision": "",
                    "reviewer_notes": "",
                }
            )

    output = project_root / "data" / "review" / "usda_foundation_candidates.csv"
    fields = [
        "ingredient_id",
        "canonical_name",
        "rank",
        "fdc_id",
        "description",
        "data_type",
        "similarity",
        "publication_date",
        "review_decision",
        "reviewer_notes",
    ]
    with output.open("w", encoding="utf-8-sig", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=fields)
        writer.writeheader()
        writer.writerows(candidate_rows)

    report = {
        "source": "USDA FoodData Central Foundation Foods",
        "license": "CC0 1.0 / public domain",
        "foundation_food_records": len(foods),
        "ingredient_queries": len(ingredients),
        "unreviewed_candidates_skipped": len(all_ingredients) - len(
            [item for item in all_ingredients if item["mapping_status"] == "internal_mapped"]
        ),
        "candidate_rows": len(candidate_rows),
        "automatic_acceptance": False,
        "output": str(output.relative_to(project_root)),
    }
    write_json(project_root / "reports" / "usda-foundation-matching.json", report)
    return report


def _foodon_value(value: str) -> str:
    value = value.strip()
    if value.startswith('"'):
        closing = value.rfind('"')
        if closing > 0:
            value = value[1:closing]
    return re.sub(r"@[a-zA-Z-]+$", "", value.strip())


def _foodon_id(uri: str) -> str:
    return uri.rstrip(">").rsplit("/", 1)[-1].replace("_", ":", 1)


def _foodon_match_form(value: str) -> str:
    value = value.casefold().strip()
    for suffix in (" food product", " (raw)", " (whole or pieces)"):
        if value.endswith(suffix):
            value = value[: -len(suffix)]
    return " ".join(_singularize_token(token) for token in value.split())


def create_foodon_candidates(
    project_root: Path,
    ingredient_path: Path,
    synonyms_path: Path | None = None,
    limit: int | None = None,
) -> dict[str, Any]:
    synonyms_path = synonyms_path or (
        project_root / "data" / "reference" / "downloads" / "foodon-synonyms.tsv"
    )
    if not synonyms_path.exists():
        raise FileNotFoundError("FoodOn synonym file is missing; run fetch-foodon first.")

    terms: list[dict[str, str]] = []
    with synonyms_path.open("r", encoding="utf-8-sig", newline="") as handle:
        for row in csv.DictReader(handle, delimiter="\t"):
            class_uri = (row.get("?class") or "").strip()
            term_type = _foodon_value(row.get("?type") or "")
            label = _foodon_value(row.get("?label") or "")
            if "FOODON_" not in class_uri or not label or term_type not in {
                "label",
                "synonym (exact)",
                "synonym (broad)",
                "synonym (related)",
                "synonym (narrow)",
            }:
                continue
            terms.append(
                {
                    "foodon_id": _foodon_id(class_uri),
                    "label": label,
                    "term_type": term_type,
                    "match_form": _foodon_match_form(label),
                }
            )

    ingredients = read_jsonl(ingredient_path)
    if limit is not None:
        ingredients = ingredients[:limit]
    candidate_rows: list[dict[str, Any]] = []
    for ingredient in ingredients:
        query = _foodon_match_form(ingredient["canonical_name"])
        scored: list[tuple[float, dict[str, str]]] = []
        for term in terms:
            if term["match_form"] == query:
                score = 1.0 if term["term_type"] == "synonym (exact)" else 0.98
            elif query in term["match_form"] or term["match_form"] in query:
                score = 0.82
            else:
                score = difflib.SequenceMatcher(None, query, term["match_form"]).ratio()
                if score < 0.72:
                    continue
            scored.append((score, term))
        scored.sort(key=lambda item: (-item[0], item[1]["foodon_id"], item[1]["label"]))
        used_ids: set[str] = set()
        rank = 0
        for score, term in scored:
            if term["foodon_id"] in used_ids:
                continue
            used_ids.add(term["foodon_id"])
            rank += 1
            candidate_rows.append(
                {
                    "ingredient_id": ingredient["ingredient_id"],
                    "canonical_name": ingredient["canonical_name"],
                    "rank": rank,
                    "foodon_id": term["foodon_id"],
                    "foodon_label": term["label"],
                    "matched_term_type": term["term_type"],
                    "similarity": round(score, 4),
                    "review_decision": "",
                    "reviewer_notes": "",
                }
            )
            if rank == 5:
                break

    output = project_root / "data" / "review" / "foodon_mapping_candidates.csv"
    fields = [
        "ingredient_id",
        "canonical_name",
        "rank",
        "foodon_id",
        "foodon_label",
        "matched_term_type",
        "similarity",
        "review_decision",
        "reviewer_notes",
    ]
    with output.open("w", encoding="utf-8-sig", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=fields)
        writer.writeheader()
        writer.writerows(candidate_rows)

    report = {
        "source": "FoodOn",
        "license": "CC BY 4.0",
        "reference_terms_loaded": len(terms),
        "ingredient_queries": len(ingredients),
        "candidate_rows": len(candidate_rows),
        "automatic_acceptance": False,
        "output": str(output.relative_to(project_root)),
    }
    write_json(project_root / "reports" / "foodon-matching.json", report)
    return report


def _fdc_search(query: str, api_key: str, page_size: int = 3) -> dict[str, Any]:
    parameters = urllib.parse.urlencode(
        {
            "api_key": api_key,
            "query": query,
            "pageSize": page_size,
            "dataType": "Foundation,SR Legacy",
        }
    )
    request = urllib.request.Request(
        f"{FDC_SEARCH_URL}?{parameters}", headers={"User-Agent": USER_AGENT}
    )
    with urllib.request.urlopen(request, timeout=60) as response:
        return json.loads(response.read().decode("utf-8"))


def create_usda_candidates(
    project_root: Path,
    ingredient_path: Path,
    limit: int,
    sleep_seconds: float = 0.1,
    include_unreviewed_candidates: bool = False,
) -> dict[str, Any]:
    api_key = os.environ.get("FDC_API_KEY")
    if not api_key:
        raise RuntimeError("FDC_API_KEY is required; use DEMO_KEY only for exploration.")
    all_ingredients = read_jsonl(ingredient_path)
    ingredients = [
        ingredient
        for ingredient in all_ingredients
        if include_unreviewed_candidates or ingredient["mapping_status"] == "internal_mapped"
    ][:limit]
    cache_dir = project_root / "data" / "reference" / "downloads" / "usda-cache"
    cache_dir.mkdir(parents=True, exist_ok=True)
    candidate_rows: list[dict[str, Any]] = []
    errors: list[dict[str, str]] = []

    for ingredient in ingredients:
        name = ingredient["canonical_name"]
        cache_path = cache_dir / f"{slugify(name)}.json"
        try:
            if cache_path.exists():
                response = json.loads(cache_path.read_text(encoding="utf-8"))
            else:
                response = _fdc_search(name, api_key=api_key)
                write_json(cache_path, response)
                time.sleep(sleep_seconds)
        except Exception as exc:  # Network/API failures belong in the audit report.
            errors.append({"ingredient_id": ingredient["ingredient_id"], "error": str(exc)})
            continue

        for rank, food in enumerate(response.get("foods", [])[:3], start=1):
            candidate_rows.append(
                {
                    "ingredient_id": ingredient["ingredient_id"],
                    "canonical_name": name,
                    "rank": rank,
                    "fdc_id": food.get("fdcId", ""),
                    "description": food.get("description", ""),
                    "data_type": food.get("dataType", ""),
                    "score": food.get("score", ""),
                    "query": name,
                    "retrieved_at": utc_now_iso(),
                    "review_decision": "",
                    "reviewer_notes": "",
                }
            )

    output = project_root / "data" / "review" / "usda_mapping_candidates.csv"
    output.parent.mkdir(parents=True, exist_ok=True)
    fields = [
        "ingredient_id",
        "canonical_name",
        "rank",
        "fdc_id",
        "description",
        "data_type",
        "score",
        "query",
        "retrieved_at",
        "review_decision",
        "reviewer_notes",
    ]
    with output.open("w", encoding="utf-8-sig", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=fields)
        writer.writeheader()
        writer.writerows(candidate_rows)

    report = {
        "source": "USDA FoodData Central",
        "license": "CC0 1.0",
        "ingredient_queries": len(ingredients),
        "unreviewed_candidates_skipped": len(all_ingredients) - len(
            [item for item in all_ingredients if item["mapping_status"] == "internal_mapped"]
        )
        if not include_unreviewed_candidates
        else 0,
        "candidate_rows": len(candidate_rows),
        "errors": errors,
        "live_api_used": True,
        "automatic_acceptance": False,
        "output": str(output.relative_to(project_root)),
    }
    write_json(project_root / "reports" / "usda-enrichment.json", report)
    return report
