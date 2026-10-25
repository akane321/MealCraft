"""Shared pieces of the in-person sampled reviews of a release (03 plan 2.5 and 2.7): the stratified allocation, the
Wilson interval and the release reader. Used by `allergen_review.py` and `manual_check.py`."""

from __future__ import annotations

import json
import math
from pathlib import Path

REPOSITORY = Path(__file__).resolve().parents[2]
RELEASE = REPOSITORY / "data-engineering/data/release/v2.2"
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


def checked(value) -> bool:
    return str(value or "").strip() == "是"


def percent(value: float | None) -> str:
    return "n/a" if value is None else f"{value:.1%}"


def interval(bounds: list[float] | None) -> str:
    return "n/a" if bounds is None else f"{bounds[0]:.1%}–{bounds[1]:.1%}"
