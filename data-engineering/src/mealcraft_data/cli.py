from __future__ import annotations

import argparse
import json
from pathlib import Path

from .pipeline import run_pipeline
from .references import (
    create_foodon_candidates,
    create_usda_candidates,
    create_usda_foundation_candidates,
    fetch_foodon,
    fetch_usda_fndds,
    fetch_usda_foundation,
    fetch_usda_sr_legacy,
)
from .validation import validate_outputs


def _project_root(value: str | None) -> Path:
    return Path(value).resolve() if value else Path(__file__).resolve().parents[2]


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="mealcraft-data",
        description="MealCraft recipe and ingredient data-cleaning demonstration",
    )
    parser.add_argument("--project-root", help="Override the data-engineering directory")
    subparsers = parser.add_subparsers(dest="command", required=True)

    run = subparsers.add_parser("run", help="Run the RecipeNLG cleaning pipeline")
    run.add_argument("--input", required=True, type=Path)
    run.add_argument("--sample-size", type=int, default=5000)
    run.add_argument("--seed", type=int, default=5105)
    run.add_argument("--source-filter")
    run.add_argument("--review-limit", type=int, default=200)

    validate = subparsers.add_parser("validate", help="Validate curated JSONL outputs")
    validate.add_argument("--recipes", required=True, type=Path)
    validate.add_argument("--ingredients", required=True, type=Path)

    subparsers.add_parser("fetch-foodon", help="Download the FoodOn synonym release")
    subparsers.add_parser("fetch-usda-foundation", help="Download and extract USDA Foundation Foods CSV")
    subparsers.add_parser("fetch-usda-sr-legacy", help="Download and extract USDA SR Legacy CSV")
    subparsers.add_parser("fetch-usda-fndds", help="Download and extract USDA FNDDS CSV")

    foodon = subparsers.add_parser("match-foodon", help="Create human-review candidates from a local FoodOn release")
    foodon.add_argument("--ingredients", required=True, type=Path)
    foodon.add_argument("--synonyms", type=Path)
    foodon.add_argument("--limit", type=int)

    usda = subparsers.add_parser("enrich-usda", help="Create human-review candidates from USDA FoodData Central")
    usda.add_argument("--ingredients", required=True, type=Path)
    usda.add_argument("--limit", type=int, default=25)
    usda.add_argument(
        "--include-unreviewed-candidates",
        action="store_true",
        help="Also query unresolved internal candidate names; disabled by default",
    )
    usda_local = subparsers.add_parser(
        "match-usda-foundation",
        help="Create mapping candidates from the downloaded Foundation Foods CSV",
    )
    usda_local.add_argument("--ingredients", required=True, type=Path)
    usda_local.add_argument("--foundation-dir", type=Path)
    usda_local.add_argument("--limit", type=int)
    return parser


def main(argv: list[str] | None = None) -> int:
    parser = build_parser()
    args = parser.parse_args(argv)
    root = _project_root(args.project_root)

    if args.command == "run":
        report = run_pipeline(
            project_root=root,
            input_path=args.input.resolve(),
            sample_size=args.sample_size,
            seed=args.seed,
            source_filter=args.source_filter,
            review_limit=args.review_limit,
        )
        print(json.dumps(report, ensure_ascii=False, indent=2))
        return 0 if all(report["quality_gate"].values()) else 1

    if args.command == "validate":
        errors = validate_outputs(args.recipes.resolve(), args.ingredients.resolve())
        if errors:
            print("Validation failed:")
            for error in errors:
                print(f"- {error}")
            return 1
        print("Validation passed.")
        return 0

    if args.command == "fetch-foodon":
        print(json.dumps(fetch_foodon(root), ensure_ascii=False, indent=2))
        return 0

    if args.command == "fetch-usda-foundation":
        print(json.dumps(fetch_usda_foundation(root), ensure_ascii=False, indent=2))
        return 0

    if args.command == "fetch-usda-sr-legacy":
        print(json.dumps(fetch_usda_sr_legacy(root), ensure_ascii=False, indent=2))
        return 0

    if args.command == "fetch-usda-fndds":
        print(json.dumps(fetch_usda_fndds(root), ensure_ascii=False, indent=2))
        return 0

    if args.command == "match-foodon":
        report = create_foodon_candidates(
            project_root=root,
            ingredient_path=args.ingredients.resolve(),
            synonyms_path=args.synonyms.resolve() if args.synonyms else None,
            limit=args.limit,
        )
        print(json.dumps(report, ensure_ascii=False, indent=2))
        return 0

    if args.command == "enrich-usda":
        report = create_usda_candidates(
            project_root=root,
            ingredient_path=args.ingredients.resolve(),
            limit=args.limit,
            include_unreviewed_candidates=args.include_unreviewed_candidates,
        )
        print(json.dumps(report, ensure_ascii=False, indent=2))
        return 1 if report["errors"] else 0

    if args.command == "match-usda-foundation":
        report = create_usda_foundation_candidates(
            project_root=root,
            ingredient_path=args.ingredients.resolve(),
            foundation_dir=args.foundation_dir.resolve() if args.foundation_dir else None,
            limit=args.limit,
        )
        print(json.dumps(report, ensure_ascii=False, indent=2))
        return 0

    parser.error(f"Unknown command: {args.command}")
    return 2


if __name__ == "__main__":
    raise SystemExit(main())
