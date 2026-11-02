"""Shared pieces of the in-person sampled reviews of a release (03 plan 2.5 and 2.7): the stratified allocation, the
Wilson interval and the release reader. Used by `allergen_review.py` and `manual_check.py`."""

from __future__ import annotations

import csv
import json
import math
from pathlib import Path

REPOSITORY = Path(__file__).resolve().parents[2]
RELEASE = REPOSITORY / "data-engineering/data/release/v2.2"
# Data release v3's added recipes are reviewed apart (issue #392), with their own seed and dated folders: wave 1 is
# the first v3 build's added recipes (2026-11-03), wave 2 the extra wave added after it (2026-11-04).
V3 = REPOSITORY / "data-engineering/data/release/v3"
FIRST_BUILD = REPOSITORY / "data-engineering/data/enrichment/v3_first_build_lines.tsv"
SELECTED = REPOSITORY / "data-engineering/data/enrichment/v3_selected.csv"
NEW_SEED = 20261103
WAVE_SEEDS = {1: NEW_SEED, 2: 20261104}
CHECKED = "已亲自核对（填 是）"


def allocate(sizes: dict[str, int], size: int, minimum: int) -> dict[str, int]:
    """At least `minimum` recipes per stratum (all of a smaller one), the rest by stratum size, largest remainder
    first, ties by name."""
    take = {name: min(minimum, n) for name, n in sizes.items()}
    left = size - sum(take.values())
    rest = {name: n - take[name] for name, n in sizes.items()}
    shares = {name: left * n / sum(rest.values()) for name, n in rest.items()}
    for name in take:
        take[name] += int(shares[name])
    by_remainder = sorted(shares, key=lambda name: (-(shares[name] - int(shares[name])), name))
    for name in by_remainder[: size - sum(take.values())]:
        take[name] += 1
    return take


def wilson(k: int, n: int, z: float = 1.96) -> list[float] | None:
    """The Wilson 95% interval of k successes in n, rounded to three places; None when nothing was checked."""
    if n == 0:
        return None
    p = k / n
    centre = (p + z * z / (2 * n)) / (1 + z * z / n)
    half = z * math.sqrt(p * (1 - p) / n + z * z / (4 * n * n)) / (1 + z * z / n)
    return [round(centre - half, 3), round(centre + half, 3)]


def release_recipes(release: Path = RELEASE) -> tuple[str, list[dict]]:
    """The release's version and recipes."""
    version = json.loads((release / "release_manifest.json").read_text(encoding="utf-8"))["release_version"]
    lines = (release / "recipes.jsonl").read_text(encoding="utf-8").splitlines()
    return version, [json.loads(line) for line in lines if line.strip()]


def new_recipes(release: Path = V3, before: Path = RELEASE, wave: int = 1) -> tuple[str, list[dict]]:
    """The recipes of `release` that `before` does not have, under a version label that says so. Wave 1 is those of
    the first v3 build (`v3_first_build_lines.tsv`); wave 2 is the extra wave's picks (`v3_selected.csv` wave 2)."""
    version, recipes = release_recipes(release)
    old_version, old = release_recipes(before)
    known = {recipe["recipe_id"] for recipe in old}
    if wave == 1:
        first = {row.split("\t")[0] for row in FIRST_BUILD.read_text(encoding="utf-8").splitlines()[1:] if row}
        label = f"{version} (new recipes, not in {old_version})"
        return label, [r for r in recipes if r["recipe_id"] not in known and r["recipe_id"] in first]
    with SELECTED.open(encoding="utf-8", newline="") as handle:
        picks = {row["candidate_id"] for row in csv.DictReader(handle) if row["wave"] == str(wave)}
    label = f"{version} (wave {wave} new recipes, not in the first v3 build)"
    return label, [r for r in recipes if r["recipe_id"] not in known and r["source"]["candidate_id"] in picks]


def combined(parts: list[dict]) -> dict:
    """Strata {"name", "population", "k", "n"} -> each stratum's rate and Wilson 95% interval, and the rate weighted
    by population over the strata with a checked row (a point estimate: no interval for the weighted rate)."""
    strata, weighted, covered = [], 0.0, 0
    for part in parts:
        rate = round(part["k"] / part["n"], 3) if part["n"] else None
        strata.append({**part, "rate": rate, "wilson95": wilson(part["k"], part["n"])})
        if part["n"]:
            weighted += part["k"] / part["n"] * part["population"]
            covered += part["population"]
    return {
        "strata": strata,
        "weighted": round(weighted / covered, 3) if covered else None,
        "cover": {"recipes": covered, "of": sum(part["population"] for part in parts)},
    }


def checked(value) -> bool:
    return str(value or "").strip() == "是"


def percent(value: float | None) -> str:
    return "n/a" if value is None else f"{value:.1%}"


def interval(bounds: list[float] | None) -> str:
    return "n/a" if bounds is None else f"{bounds[0]:.1%}–{bounds[1]:.1%}"


def combined_lines(combo: dict, what: str, hits: str) -> list[str]:
    """The report section of `combined`: each wave's strata and the weighted rate."""
    lines = [
        "",
        "## Both waves",
        "",
        f"Both v3 waves together, the {what} weighted by each stratum's recipes: **{percent(combo['weighted'])}** "
        f"(strata covering {combo['cover']['recipes']} of {combo['cover']['of']} recipes). A point estimate only; "
        "each stratum carries its own Wilson 95% interval.",
        "",
        f"| Stratum | Recipes | Checked | {hits} | Rate | Wilson 95% |",
        "| --- | ---: | ---: | ---: | ---: | --- |",
    ]
    for part in combo["strata"]:
        lines.append(
            f"| {part['name']} | {part['population']} | {part['n']} | {part['k']} | {percent(part['rate'])} "
            f"| {interval(part['wilson95'])} |"
        )
    return lines
