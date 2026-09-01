import argparse
from pathlib import Path

from app.data.catalog import import_catalog, load_catalog
from app.db.session import SessionLocal


def main() -> None:
    parser = argparse.ArgumentParser(description="Validate and idempotently import the MealCraft reference catalog.")
    parser.add_argument("--ingredients", type=Path, default=Path("data/ingredients/ingredients.json"))
    parser.add_argument("--recipes", type=Path, default=Path("data/recipes/recipes.json"))
    parser.add_argument("--validate-only", action="store_true")
    args = parser.parse_args()

    catalog = load_catalog(args.ingredients, args.recipes)
    if args.validate_only:
        print(f"Catalog valid: {len(catalog.ingredients)} ingredients, {len(catalog.recipes)} recipes")
        return

    with SessionLocal() as session:
        ingredient_count, recipe_count = import_catalog(session, catalog)
    print(f"Catalog imported: {ingredient_count} ingredients, {recipe_count} recipes")


if __name__ == "__main__":
    main()
