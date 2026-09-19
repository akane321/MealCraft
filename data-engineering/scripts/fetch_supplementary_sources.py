"""Fetch the two supplementary recipe sources for release v2 into data/raw/.

- TheMealDB: every meal, through the public search endpoint (letters a-z), with
  its area, measures, ingredients and instructions. Terms: content may be copied
  and modified through the official endpoints, keeping attribution.
- Wikibooks Cookbook: every recipe page in the cuisine categories listed below
  and their sub-categories, as wikitext with its revision id. Licence: CC BY-SA 4.0.

Raw payloads stay local (data/raw is git-ignored); each source gets a
raw_manifest.json with the retrieval time, counts and SHA-256, which is committed.

Run: python scripts/fetch_supplementary_sources.py
"""

from __future__ import annotations

import hashlib
import json
import string
import time
import urllib.error
import urllib.parse
import urllib.request
from datetime import UTC, datetime
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
RAW = ROOT / "data" / "raw"
USER_AGENT = "MealCraft-course-project/0.1 (NUS DSS5105; non-commercial)"

WIKIBOOKS_API = "https://en.wikibooks.org/w/api.php"
WIKIBOOKS_CATEGORIES = [
    "Chinese recipes",
    "Japanese recipes",
    "Korean recipes",
    "Malaysian recipes",
    "Singaporean recipes",
    "Indonesian recipes",
    "Thai recipes",
    "Vietnamese recipes",
    "Filipino recipes",
    "Indian recipes",
    "Middle Eastern recipes",
    "Lebanese recipes",
    "Turkish recipes",
    "Iranian recipes",
    "Israeli recipes",
    "Arab recipes",
    "Moroccan recipes",
    "Egyptian recipes",
]


def get_json(url: str) -> dict:
    """GET with a polite one-second pause, honouring Retry-After on 429."""
    request = urllib.request.Request(url, headers={"User-Agent": USER_AGENT})
    for attempt in range(8):
        time.sleep(1.0)
        try:
            with urllib.request.urlopen(request, timeout=30) as response:
                return json.loads(response.read().decode("utf-8"))
        except urllib.error.HTTPError as error:
            if error.code not in {429, 500, 502, 503} or attempt == 7:
                raise
            time.sleep(float(error.headers.get("Retry-After") or 10 * (attempt + 1)))
        except OSError:
            if attempt == 7:
                raise
            time.sleep(5 * (attempt + 1))
    raise AssertionError("unreachable")


def write_source(name: str, payload: list[dict], manifest: dict) -> None:
    folder = RAW / name
    folder.mkdir(parents=True, exist_ok=True)
    data = json.dumps(payload, ensure_ascii=False, indent=1).encode("utf-8")
    (folder / f"{name}.json").write_bytes(data)
    manifest.update(
        {
            "retrieved_at": datetime.now(UTC).isoformat(timespec="seconds"),
            "local_path": f"data/raw/{name}/{name}.json",
            "committed_to_git": False,
            "record_count": len(payload),
            "file_sha256": hashlib.sha256(data).hexdigest(),
        }
    )
    (folder / "raw_manifest.json").write_text(json.dumps(manifest, indent=2) + "\n", encoding="utf-8")
    print(f"{name}: {len(payload)} records")


def fetch_themealdb() -> None:
    meals: dict[str, dict] = {}
    for letter in string.ascii_lowercase:
        data = get_json(f"https://www.themealdb.com/api/json/v1/1/search.php?f={letter}")
        for meal in data.get("meals") or []:
            meals[meal["idMeal"]] = meal
    write_source(
        "themealdb",
        sorted(meals.values(), key=lambda m: int(m["idMeal"])),
        {
            "source": "TheMealDB",
            "source_url": "https://www.themealdb.com/",
            "source_license": "TheMealDB terms of use: content may be copied and modified via the official "
            "API endpoints; attribution to TheMealDB is kept. Non-commercial course use.",
            "terms_url": "https://www.themealdb.com/terms_of_use.php",
        },
    )


def category_pages(category: str, seen_categories: set[str]) -> set[str]:
    """Page titles in a category and, recursively, its sub-categories."""
    if category in seen_categories:
        return set()
    seen_categories.add(category)
    pages: set[str] = set()
    params = {
        "action": "query",
        "format": "json",
        "list": "categorymembers",
        "cmlimit": "500",
        "cmtitle": f"Category:{category}",
        "cmtype": "page|subcat",
    }
    while True:
        data = get_json(f"{WIKIBOOKS_API}?{urllib.parse.urlencode(params)}")
        for member in data.get("query", {}).get("categorymembers", []):
            if member["ns"] == 14:
                pages |= category_pages(member["title"].removeprefix("Category:"), seen_categories)
            elif member["title"].startswith("Cookbook:"):
                pages.add(member["title"])
        if "continue" not in data:
            return pages
        params.update(data["continue"])


def fetch_wikibooks() -> None:
    seen: set[str] = set()
    by_title: dict[str, set[str]] = {}
    for category in WIKIBOOKS_CATEGORIES:
        for title in category_pages(category, seen):
            by_title.setdefault(title, set()).add(category)
    titles = sorted(by_title)
    records = []
    for start in range(0, len(titles), 50):
        batch = titles[start : start + 50]
        params = {
            "action": "query",
            "format": "json",
            "prop": "revisions|categories",
            "rvprop": "ids|content",
            "rvslots": "main",
            "cllimit": "max",
            "titles": "|".join(batch),
        }
        data = get_json(f"{WIKIBOOKS_API}?{urllib.parse.urlencode(params)}")
        for page in data["query"]["pages"].values():
            if "revisions" not in page:
                continue
            revision = page["revisions"][0]
            records.append(
                {
                    "title": page["title"],
                    "pageid": page["pageid"],
                    "revid": revision["revid"],
                    "url": "https://en.wikibooks.org/wiki/" + urllib.parse.quote(page["title"].replace(" ", "_")),
                    "fetched_from_categories": sorted(by_title[page["title"]]),
                    "categories": [c["title"].removeprefix("Category:") for c in page.get("categories", [])],
                    "wikitext": revision["slots"]["main"]["*"],
                }
            )
    write_source(
        "wikibooks",
        sorted(records, key=lambda r: r["title"]),
        {
            "source": "Wikibooks Cookbook",
            "source_url": "https://en.wikibooks.org/wiki/Cookbook:Table_of_Contents",
            "source_license": "CC BY-SA 4.0; each record keeps its page URL and revision id for attribution.",
            "categories": WIKIBOOKS_CATEGORIES,
        },
    )


if __name__ == "__main__":
    if not (RAW / "themealdb" / "themealdb.json").exists():
        fetch_themealdb()
    fetch_wikibooks()
