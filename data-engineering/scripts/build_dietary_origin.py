"""Task A of the enrichment work package: classify each canonical ingredient's
dietary origin so recipe-level dietary tags can be derived deterministically.

Design note (deviation from the work package's literal wording): the task doc
describes this as a binary "animal vs plant" judgment, but the tag rules it
also specifies ("vegetarian allows dairy/eggs/honey") only work if dairy/egg/
honey-type ingredients are distinguished from meat/fish/gelatin-type
ingredients -- a flesh-origin item blocks both vegetarian and vegan, a
secretion-origin item (dairy, eggs, honey) blocks vegan only. A naive binary
scheme would either wrongly block vegetarian on eggs/honey, or wrongly allow
vegan on them. So this classifies into three buckets:

    flesh      - meat, poultry, fish, shellfish, gelatin -> blocks vegetarian AND vegan
    secretion  - dairy, eggs, honey                       -> blocks vegan only
    plant      - everything else                          -> blocks neither

Only the ingredients that need a judgment call are listed explicitly below:
- the 187 canonical ingredients whose food_group is protein/condiment/fat/
  flavoring/prepared (ambiguous by food_group alone), plus
- 12 ingredients that live in an otherwise-safe food_group (grain, sweetener,
  beverage) but were found (by cross-checking every auto-bucket ingredient's
  allergen tag, plus manual culinary knowledge for honey/marshmallow which
  carry no allergen tag at all) to actually contain egg, dairy or gelatin.

Everything else is derived by a simple rule: food_group == "dairy" -> secretion,
any other food_group -> plant. That covers the remaining ~340 ingredients
without needing them individually listed.
"""
from __future__ import annotations

import csv
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
ALIASES_CSV = ROOT / "config" / "ingredient_aliases.csv"
OUT_CSV = ROOT / "config" / "ingredient_dietary_origin.csv"

# ingredient_id -> (origin, evidence)
# evidence is required for anything not immediately obvious from the name.
OVERRIDES: dict[str, tuple[str, str]] = {
    # -- hidden animal content inside otherwise-auto-plant food_groups -----
    "ING_HONEY": ("secretion", "Bee product; not on FDA allergen list so carries no allergen tag, but explicitly named as a vegan-exclusion in the work package's own rule table."),
    "ING_MARSHMALLOW": ("flesh", "Standard commercial marshmallow is gelatin-set (animal collagen); gelatin is not an FDA allergen so it carries no allergen tag. Treated as flesh-equivalent (excludes vegetarian too), matching mainstream vegetarian conventions."),
    "ING_CARAMEL": ("secretion", "milk allergen tag (cream-based)."),
    "ING_BUTTERSCOTCH_TOPPING": ("secretion", "milk allergen tag."),
    "ING_EGGNOG": ("secretion", "eggs;milk allergen tags; no meat, so vegetarian-safe, vegan-excluded."),
    "ING_EGG_NOODLES": ("secretion", "eggs allergen tag."),
    "ING_LADYFINGERS": ("secretion", "eggs allergen tag."),
    "ING_WONTON_WRAPPER": ("secretion", "eggs allergen tag (traditional wonton wrappers are egg-enriched)."),
    "ING_ANGEL_FOOD_CAKE": ("secretion", "eggs allergen tag (egg-white based)."),
    "ING_POUND_CAKE": ("secretion", "eggs;milk allergen tags."),
    "ING_COOKIE_DOUGH": ("secretion", "eggs allergen tag."),
    "ING_BUTTERED_BREADCRUMBS": ("secretion", "milk allergen tag (butter)."),

    # -- protein: flesh (meat / poultry / fish / shellfish) ---------------
    "ING_ANCHOVY": ("flesh", ""), "ING_BACON": ("flesh", ""), "ING_BEEF": ("flesh", ""),
    "ING_BEEF_OR_TURKEY": ("flesh", "Both named alternatives are flesh."),
    "ING_CHICKEN": ("flesh", ""), "ING_CHICKEN_BREAST": ("flesh", ""),
    "ING_CHICKEN_OR_TURKEY": ("flesh", "Both named alternatives are flesh."),
    "ING_CHICKEN_THIGH": ("flesh", ""), "ING_CHICKEN_WINGS": ("flesh", ""),
    "ING_CLAM": ("flesh", ""), "ING_COOKED_CHICKEN": ("flesh", ""), "ING_CORNED_BEEF": ("flesh", ""),
    "ING_CRAB": ("flesh", ""), "ING_CHIPPED_BEEF": ("flesh", ""), "ING_FISH_FILLET": ("flesh", ""),
    "ING_GROUND_BEEF": ("flesh", ""), "ING_GROUND_PORK": ("flesh", ""), "ING_GROUND_TURKEY": ("flesh", ""),
    "ING_HAM": ("flesh", ""), "ING_HOT_DOG": ("flesh", ""),
    "ING_IMITATION_CRAB": ("flesh", "Surimi is fish-based (see round-6 allergen fix)."),
    "ING_LOBSTER": ("flesh", ""), "ING_MEAT": ("flesh", "Generic term."), "ING_MEATBALL": ("flesh", ""),
    "ING_MUSSEL": ("flesh", ""), "ING_OYSTER": ("flesh", ""), "ING_PANCETTA": ("flesh", ""),
    "ING_PEPPERONI": ("flesh", ""), "ING_PORK": ("flesh", ""), "ING_PORK_CHOP": ("flesh", ""),
    "ING_PROSCIUTTO": ("flesh", ""), "ING_RABBIT": ("flesh", ""), "ING_SALMON": ("flesh", ""),
    "ING_SAUSAGE": ("flesh", ""), "ING_SCALLOP": ("flesh", ""), "ING_SHRIMP": ("flesh", ""),
    "ING_BEEF_STEAK": ("flesh", ""), "ING_TUNA": ("flesh", ""), "ING_TURKEY": ("flesh", ""),

    # -- protein: secretion (eggs) -----------------------------------------
    "ING_EGG": ("secretion", ""), "ING_EGG_WHITE": ("secretion", ""), "ING_EGG_YOLK": ("secretion", ""),
    "ING_EGG_SUBSTITUTE": ("secretion", "Era-typical usage (RecipeNLG is pre-2020) is liquid egg substitute (e.g. Egg Beaters), which is egg-white based, not a plant substitute. Flagged as the more uncertain call in this file."),

    # -- protein: plant (nuts / seeds / legumes / tofu) --------------------
    "ING_ALMOND": ("plant", ""), "ING_ALMOND_BUTTER": ("plant", ""), "ING_BAKED_BEANS": ("plant", ""),
    "ING_BLACK_BEANS": ("plant", ""), "ING_BLACK_EYED_PEAS": ("plant", ""), "ING_CASHEW": ("plant", ""),
    "ING_CHIA": ("plant", ""), "ING_CHICKPEA": ("plant", ""), "ING_EDAMAME": ("plant", ""),
    "ING_FLAX": ("plant", ""), "ING_HAZELNUT": ("plant", ""), "ING_KIDNEY_BEANS": ("plant", ""),
    "ING_LENTIL": ("plant", ""), "ING_LIMA_BEANS": ("plant", ""), "ING_MACADAMIA_NUT": ("plant", ""),
    "ING_MIXED_NUTS": ("plant", ""), "ING_PEANUT": ("plant", ""), "ING_PEANUT_BUTTER": ("plant", ""),
    "ING_PECAN": ("plant", ""), "ING_PECAN_OR_WALNUT": ("plant", "Both alternatives plant."),
    "ING_PINE_NUT": ("plant", ""), "ING_PINTO_BEANS": ("plant", ""), "ING_PISTACHIO": ("plant", ""),
    "ING_PUMPKIN_SEED": ("plant", ""), "ING_REFRIED_BEANS": ("plant", ""), "ING_SUNFLOWER_SEED": ("plant", ""),
    "ING_TOFU": ("plant", ""), "ING_WALNUT": ("plant", ""), "ING_CANNELLINI": ("plant", ""),

    # -- condiment: flesh ----------------------------------------------------
    "ING_FISH_SAUCE": ("flesh", "fish allergen tag."),
    "ING_OYSTER_SAUCE": ("flesh", "molluscs allergen tag."),
    "ING_STEAK_SAUCE": ("flesh", "Conventionally Worcestershire-based (anchovy-derived); no allergen tag exists on this entry, so this is a genuine inference call, not a rule lookup -- flagged for spot-check."),
    "ING_WORCESTERSHIRE": ("flesh", "fish allergen tag."),

    # -- condiment: secretion (dairy / egg) -----------------------------------
    "ING_NUTELLA": ("secretion", "milk allergen tag."), "ING_MAYO": ("secretion", "eggs allergen tag."),
    "ING_MAYO_OR_DRESSING": ("secretion", "eggs allergen tag."),
    "ING_PESTO": ("secretion", "milk allergen tag (parmesan)."),
    "ING_RANCH_DRESSING": ("secretion", "eggs;milk allergen tags."),
    "ING_SALAD_DRESSING": ("secretion", "Generic bucket covers both vinaigrette (plant) and creamy/mayo-based dressings; conservatively assumed to possibly contain egg/dairy rather than certified plant, to avoid a false vegan/vegetarian claim. Flagged for spot-check."),

    # -- condiment: plant (vinegars, tomato/chili/soy-based sauces) --------
    "ING_APPLE_BUTTER": ("plant", ""), "ING_CIDER_VINEGAR": ("plant", ""), "ING_BALSAMIC": ("plant", ""),
    "ING_BBQ_SAUCE": ("plant", ""), "ING_KITCHEN_BOUQUET": ("plant", ""), "ING_CAPERS": ("plant", ""),
    "ING_CHILI_SAUCE": ("plant", ""), "ING_CURRY_PASTE": ("plant", "Assumed Indian-style spice paste (dataset is majority Western recipes); Thai shrimp-based curry paste would be flesh. Flagged for spot-check."),
    "ING_DIJON": ("plant", ""), "ING_ENCHILADA_SAUCE": ("plant", ""), "ING_GINGER_GARLIC": ("plant", ""),
    "ING_HOISIN": ("plant", ""), "ING_HORSERADISH": ("plant", ""), "ING_HOT_SAUCE": ("plant", ""),
    "ING_ITALIAN_DRESSING": ("plant", ""), "ING_JAM": ("plant", ""), "ING_KETCHUP": ("plant", ""),
    "ING_LIQUID_SMOKE": ("plant", ""), "ING_MARINARA": ("plant", ""), "ING_PEANUT_SAUCE": ("plant", ""),
    "ING_RELISH": ("plant", ""), "ING_PIZZA_SAUCE": ("plant", ""), "ING_POMEGRANATE_MOLASSES": ("plant", ""),
    "ING_MUSTARD": ("plant", ""), "ING_RED_WINE_VINEGAR": ("plant", ""), "ING_RICE_VINEGAR": ("plant", ""),
    "ING_SALSA": ("plant", ""), "ING_SHERRY_VINEGAR": ("plant", ""), "ING_SOY_SAUCE": ("plant", ""),
    "ING_SWEET_SOUR_SAUCE": ("plant", ""), "ING_SWEET_CHILI_SAUCE": ("plant", ""), "ING_TACO_SAUCE": ("plant", ""),
    "ING_SESAME_TAHINI": ("plant", ""), "ING_TERIYAKI": ("plant", ""), "ING_VINEGAR": ("plant", ""),
    "ING_WHITE_WINE_VINEGAR": ("plant", ""),

    # -- fat: secretion (dairy) ----------------------------------------------
    "ING_BUTTER_OR_MARGARINE": ("secretion", "At least one named alternative (butter) is dairy."),
    "ING_BUTTER_OR_SHORTENING": ("secretion", "milk allergen tag."),
    "ING_BUTTER_OR_VEG_OIL": ("secretion", "milk allergen tag."),
    "ING_GHEE": ("secretion", "milk allergen tag (clarified butter)."),

    # -- fat: flesh ------------------------------------------------------------
    "ING_LARD": ("flesh", "Rendered pork fat."),

    # -- fat: plant --------------------------------------------------------
    "ING_COCONUT_OIL": ("plant", ""), "ING_COOKING_SPRAY": ("plant", ""), "ING_GRAPESEED_OIL": ("plant", ""),
    "ING_MARGARINE": ("plant", "Standard margarine is vegetable-oil based; not milk-tagged in config."),
    "ING_OLIVE_OIL": ("plant", ""), "ING_PEANUT_OIL": ("plant", ""), "ING_SESAME_OIL": ("plant", ""),
    "ING_SHORTENING": ("plant", "Modern vegetable shortening, not lard."), "ING_SHORTENING_OR_OIL": ("plant", ""),
    "ING_SUNFLOWER_OIL": ("plant", ""), "ING_VEGETABLE_OIL": ("plant", ""), "ING_VEG_OR_OLIVE_OIL": ("plant", ""),
    "ING_WALNUT_OIL": ("plant", ""),

    # -- flavoring: secretion (chocolate/dairy) -----------------------------
    "ING_BAKING_CHOCOLATE": ("secretion", "milk allergen tag."),
    "ING_BUTTERSCOTCH_CHIPS": ("secretion", "milk allergen tag."),
    "ING_CHOCOLATE_CHIPS": ("secretion", "milk allergen tag."),
    "ING_DARK_CHOCOLATE": ("secretion", "milk allergen tag."),
    "ING_MILK_CHOCOLATE": ("secretion", "milk allergen tag."),
    "ING_TOFFEE_BITS": ("secretion", "milk allergen tag."),
    "ING_WHITE_CHOCOLATE": ("secretion", "milk allergen tag."),

    # -- flavoring: plant ----------------------------------------------------
    "ING_ALMOND_EXTRACT": ("plant", ""), "ING_BUTTER_FLAVORING": ("plant", "Synthetic flavor, not milk-tagged."),
    "ING_COCOA": ("plant", ""), "ING_COCONUT_EXTRACT": ("plant", ""), "ING_COCONUT_FLAVORING": ("plant", ""),
    "ING_ESPRESSO_POWDER": ("plant", ""), "ING_FOOD_COLORING": ("plant", ""), "ING_LEMON_EXTRACT": ("plant", ""),
    "ING_MAPLE_EXTRACT": ("plant", ""), "ING_MINT_EXTRACT": ("plant", ""), "ING_ORANGE_BLOSSOM": ("plant", ""),
    "ING_ORANGE_EXTRACT": ("plant", ""), "ING_PEANUT_BUTTER_CHIPS": ("plant", ""), "ING_ROSE_WATER": ("plant", ""),
    "ING_RUM_EXTRACT": ("plant", ""), "ING_SPRINKLES": ("plant", "Not milk-tagged; sugar-based."),
    "ING_VANILLA_BEAN": ("plant", ""), "ING_VANILLA": ("plant", ""),

    # -- prepared: flesh (meat/fish stocks, gelatin) ------------------------
    "ING_AU_JUS_MIX": ("flesh", "Au jus is beef drippings by definition."),
    "ING_BEEF_BROTH": ("flesh", ""),
    "ING_BOUILLON": ("flesh", "Default assumption is beef/chicken bouillon (most common); vegetable bouillon exists but isn't distinguished by this canonical id. Flagged for spot-check."),
    "ING_BROTH": ("flesh", "Generic term defaults to meat-based stock, the dataset-era norm. Flagged for spot-check."),
    "ING_GRAVY_MIX": ("flesh", "\"Brown gravy\" is conventionally beef-derived; some commercial mixes are actually meat-free but this isn't distinguishable here. Flagged for spot-check."),
    "ING_CHICKEN_RICE_SOUP": ("flesh", ""), "ING_CHICKEN_BROTH": ("flesh", ""),
    "ING_CHICKEN_OR_VEG_BROTH": ("flesh", "At least one named alternative (chicken broth) is flesh."),
    "ING_CLAM_JUICE": ("flesh", "fish allergen tag (molluscs)."),
    "ING_CHICKEN_SOUP": ("flesh", "Cream of chicken soup contains chicken stock."),
    "ING_ONION_SOUP_MIX": ("flesh", "Commercial dry onion soup mix conventionally includes beef flavoring/fat; formulations vary. Flagged for spot-check."),
    "ING_GELATIN": ("flesh", "Animal collagen; not an FDA allergen so carries no allergen tag."),
    "ING_SOUP": ("flesh", "Generic term, defaults conservative (most soups use meat stock). Flagged for spot-check."),

    # -- prepared: secretion (dairy) ------------------------------------------
    "ING_CHEESE_SOUP": ("secretion", "milk allergen tag."),
    "ING_CELERY_SOUP": ("secretion", "Cream of celery soup is cream-based; not milk-tagged in config (a pre-existing allergen-tagging gap, not fixed here per ADR-0024's ban on agent-inferred allergen tags -- noted separately)."),
    "ING_MUSHROOM_SOUP": ("secretion", "Cream of mushroom soup is cream-based, no meat. Same pre-existing allergen-tagging gap as celery soup."),
    "ING_CONDENSED_CREAM_OF_POTATO_SOUP": ("secretion", "Cream-based. Same pre-existing allergen-tagging gap."),
    "ING_MAC_AND_CHEESE": ("secretion", "milk allergen tag."),

    # -- prepared: plant -----------------------------------------------------
    "ING_ALMOND_PASTE": ("plant", ""), "ING_FRUIT_PIE_FILLING": ("plant", ""),
    "ING_PUDDING_MIX": ("plant", "Dry mix; milk is added separately when preparing, not an ingredient of the mix itself."),
    "ING_PISTACHIO_PUDDING": ("plant", "Dry mix, same reasoning as instant pudding mix."),
    "ING_RANCH_MIX": ("plant", "Dry seasoning packet; buttermilk/mayo is added separately when preparing."),
    "ING_TOMATO_SOUP": ("plant", "Classic condensed tomato soup recipe has no dairy or meat."),
    "ING_VEGETABLE_BROTH": ("plant", ""), "ING_XANTHAN_GUM": ("plant", "Produced by bacterial fermentation of plant sugars."),
}


def main() -> None:
    rows = list(csv.DictReader(ALIASES_CSV.open(encoding="utf-8")))
    by_id: dict[str, tuple[str, str, str]] = {}
    for row in rows:
        by_id[row["ingredient_id"]] = (row["canonical_name"], row["food_group"], row["allergens"])

    out_rows = []
    unclassified = []
    for cid, (name, food_group, allergens) in sorted(by_id.items()):
        if cid in OVERRIDES:
            origin, evidence = OVERRIDES[cid]
            basis = "override"
        elif food_group == "dairy":
            origin, evidence, basis = "secretion", "", "food_group=dairy"
        elif food_group in {
            "vegetable", "fruit", "grain", "plant_milk", "herb", "seasoning",
            "sweetener", "leavening", "liquid", "beverage",
        }:
            origin, evidence, basis = "plant", "", f"food_group={food_group}"
        else:
            unclassified.append((cid, name, food_group))
            continue
        out_rows.append((cid, name, food_group, origin, basis, evidence))

    if unclassified:
        raise SystemExit(f"{len(unclassified)} canonical ingredients have no origin classification: {unclassified}")

    with OUT_CSV.open("w", encoding="utf-8", newline="") as fh:
        writer = csv.writer(fh)
        writer.writerow(["ingredient_id", "canonical_name", "food_group", "dietary_origin", "basis", "evidence"])
        writer.writerows(out_rows)

    print(f"wrote {len(out_rows)} dietary-origin rows -> {OUT_CSV}")
    from collections import Counter
    print("origin distribution:", Counter(r[3] for r in out_rows))
    print("override count:", sum(1 for r in out_rows if r[4] == "override"))


if __name__ == "__main__":
    main()
