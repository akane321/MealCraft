import argparse
from pathlib import Path

from app.evaluation.runner import evaluate, write_reports


def main() -> None:
    parser = argparse.ArgumentParser(description="Run the repeatable MealCraft MVP quality evaluation.")
    parser.add_argument("--ingredients", type=Path, default=Path("data/ingredients/ingredients.json"))
    parser.add_argument("--recipes", type=Path, default=Path("data/recipes/recipes.json"))
    parser.add_argument("--scenarios", type=Path, default=Path("data/evaluation/dev/planning-v1.json"))
    parser.add_argument("--fixtures", type=Path, default=Path("data/fixtures/fairprice-products.json"))
    parser.add_argument("--json-report", type=Path, default=Path("docs/evaluation/latest.json"))
    parser.add_argument("--markdown-report", type=Path, default=Path("docs/evaluation/latest.md"))
    args = parser.parse_args()

    report = evaluate(
        ingredient_path=args.ingredients,
        recipe_path=args.recipes,
        scenario_path=args.scenarios,
        fixture_path=args.fixtures,
    )
    write_reports(report, args.json_report, args.markdown_report)
    print(f"MealCraft evaluation: {'PASS' if report['passed'] else 'FAIL'}")
    for name, value in report["metrics"].items():
        print(f"  {name}: {value}")
    if not report["passed"]:
        raise SystemExit(1)


if __name__ == "__main__":
    main()
