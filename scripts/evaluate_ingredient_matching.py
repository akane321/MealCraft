"""Compare ingredient suggestion by spelling and by embedding on a labelled term set.

    PYTHONPATH=backend python scripts/evaluate_ingredient_matching.py [CASES.json]

Reports, over the cases that have an acceptable id: how often the first suggestion is acceptable (top-1),
and how often any of the four offered is (top-4, what the household actually sees). Terms with no
acceptable id are listed with what would be offered, for reading, not scored.
"""

import json
import sys
from pathlib import Path

from app.agent.ingredient_matcher import IngredientMatcher, catalog_aliases, catalog_vectors
from embed_ingredients import catalog_names, embedder

CASES = Path(sys.argv[1] if len(sys.argv) > 1 else "data/evaluation/agent/ingredient-matching-dev.json")


def main() -> None:
    cases = json.loads(CASES.read_text(encoding="utf-8"))["cases"]
    names = catalog_names()
    client = embedder()
    cache: dict[str, list[float]] = {}

    def embed(texts: list[str]) -> list[list[float]]:
        missing = [t for t in texts if t not in cache]
        if missing:
            cache.update(zip(missing, client.embed_documents(missing), strict=True))
        return [cache[t] for t in texts]

    scored = [c for c in cases if c["accept"]]
    print(f"{CASES.name}: {len(scored)} scored terms, {len(cases) - len(scored)} with no acceptable id\n")
    print(f"{'mode':10} {'top-1':>8} {'top-4':>8}")
    misses: dict[str, list[str]] = {}
    for mode in ("spelling", "embedding"):
        matcher = IngredientMatcher(names, vectors=catalog_vectors(), embed=embed, aliases=catalog_aliases(), mode=mode)
        top1 = top4 = 0
        for case in scored:
            offered = matcher.suggest(case["term"])
            top1 += offered[0] in case["accept"]
            hit = any(o in case["accept"] for o in offered)
            top4 += hit
            if not hit:
                misses.setdefault(mode, []).append(f"{case['term']} -> {', '.join(offered)}")
        print(f"{mode:10} {top1:>4}/{len(scored)} {top4:>4}/{len(scored)}")
    for mode, rows in misses.items():
        print(f"\n{mode} misses ({len(rows)}):")
        for row in rows:
            print("  ", row)
    matcher = IngredientMatcher(names, vectors=catalog_vectors(), embed=embed, aliases=catalog_aliases())
    for case in cases:
        if not case["accept"]:
            print(f"\nno acceptable id: {case['term']} -> {', '.join(matcher.suggest(case['term']))}")


if __name__ == "__main__":
    main()
