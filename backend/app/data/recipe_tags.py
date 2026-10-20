"""Tag every catalog recipe and ingredient for the Sprint 2 planner (layer 08; ADR-0070, ADR-0076).

`python -m app.data.recipe_tags` writes two reviewed data files, which the importers copy onto the
catalog rows (`app.data.tag_files`):

- `data/recipes/recipe-tags-v1.json`, keyed by release `external_id` or curated slug: `meal_role`,
  `contains_staple`, `protein_sources`, `cooking_methods`, `equipment`, `flavor_tags`, and
  `estimated` (how each field was decided: `rule` or `llm`, its batch, `reviewed`);
- `data/ingredients/ingredient-tags-v1.json`, keyed by `normalized_name`: `food_group`, `perishable`,
  `basic_seasoning`, and `methods` (where each value came from).

It also writes the owner's spot-check packet and the coverage report in `data-engineering/docs`.

Deterministic rules decide first, from the course, the ingredients' release food groups and dietary
origin, the ingredient hierarchy, gram shares, title words and step keywords. The language model
(`--llm`) may decide an allowed meal role; unknown animal identity and missing quantities are not
sent to it to guess. A value the rules and the model both leave open stays null,
which the planner reads as untagged. Allergen, halal and diet labels are never estimated here.

The rules, and why:

- **Meal role.** A fixed course decides it: breakfast, dessert, sauce, drink, snack, salad. A recipe that
  is a part of a dish, not a dish (a dough, crust, batter, filling, topping, sauce, marinade, rub, dressing,
  gravy, stock, broth, paste or seasoning by its title's final head noun: `component`) is a `sauce`, the role of every
  such part, so it never fills a meal; "Chicken In Tarragon Sauce" and "Cauliflower Crust Pizza" stay
  dishes. A salad
  stays a salad whatever it holds, since a salad only ever fills the vegetable side (ADR-0070); the
  planner's vegetable-led check still decides whether it may. A hearty salad (not vegetable-led, with a
  main protein) therefore fills no slot; the owner reviews them as their own stratum of the sample packet
  before deciding whether one may be a main. A dish is `vegetable` only when it is
  vegetable-led (`app.planning.vegetable_led`, ADR-0054), so the role and the planner's rule agree.
  A main or soup that carries its own staple (rice, noodles, pasta, bread or other grain staples:
  `staple_share`) is `one_bowl`; a main made mostly of a staple with no protein is a `staple`. A
  main with a main protein is a `protein_main`; one led by vegetables without one is a `vegetable`.
  A soup whose noodles, rice or pasta are a tenth of it is `one_bowl` too. Baked goods go by title words
  and sugar. Grey zones go to the model, which may not make a side, or a dish with no main protein, a
  `protein_main`, and may answer null when no allowed role fits.
- **Contains staple** is true exactly for `one_bowl` and `staple` dishes, so it follows the role.
- **Protein sources** are the sources whose ingredients make at least 5 % (meat, poultry, fish,
  seafood) or 10 % (egg, soy, legumes) of the dish's counted raw grams, so an egg that binds a
  meatloaf or bacon bits on a salad are not its protein. A line with no weight counts. Seasonings,
  stocks and fats made from meat or fish are not protein (`SEASONING_FROM_FLESH`). Turkey and other
  poultry count as chicken, goose as duck, goat as lamb, veal as beef, so the no-repeat rule errs
  towards strictness. Explicit ingredient wording, including parentheses, refines a generic meat id.
  A title is only a missing-line check, never proof that meat exists. Generic meat stays unknown;
  a combined weight for different animals does not prove either animal's main-protein share.
  These evidence gaps are not sent to a model to guess. Desserts, sauces and drinks have none:
  the eggs of a cake are not its main protein.
- **Cooking methods** come from step and title keywords; a dish with no heating step is `raw`, and
  one that heats without a listed method (a microwave dish) has none. The "fried" of a deep-fried
  dish is not also a pan fry.
- **Equipment** comes from keywords (ADR-0068: every household has every appliance until it says
  otherwise): an oven, an air fryer, or both as one any-of group when the recipe offers either; a
  steamer; a microwave; a blender or food processor. A Dutch oven is a pot, not an oven.
- **Flavour tags**: `spicy` from hot ingredients by weight per serving or title words; `fragrant`
  from at least three aromatics (alliums, ginger, fresh herbs, whole spices); `rich` from fat at
  least half of the energy, 35 g of fat a serving or a coconut-milk base; `light` from at most 30 %
  of energy from fat, at most 450 kcal a serving and no deep frying. Rich and light never meet;
  sauces and drinks get neither.
- **Ingredients.** `food_group` is the release's, or for a curated id the release ingredient it is
  the same as or a variety of. `perishable` is ADR-0068's short-lived class only (leafy greens, bean
  and pea sprouts, fresh fish, fresh shellfish); every true value is confirmed by the owner.
  `basic_seasoning` is `data/ingredients/basic-seasonings-v1.json`.
"""

from __future__ import annotations

import argparse
import json
import random
import re
from collections import Counter
from dataclasses import dataclass, field
from pathlib import Path
from typing import get_args

from app.core.paths import repository_root
from app.data.catalog import load_catalog
from app.data.release_v2 import LINE_CORRECTIONS, release_dir
from app.data.tag_files import INGREDIENT_TAGS, RECIPE_TAGS
from app.planning.recipe_quality import missing_named_protein, reviewed_source_conflict
from app.planning.vegetable_led import (
    COOKED_STAPLES,
    COOKED_YIELD,
    MEAT_WORDS,
    SEASONING_FROM_FLESH,
    UNCOUNTED,
    UNCOUNTED_GROUPS,
    food_groups,
    vegetable_led,
)
from app.schemas.catalog_tags import CookingMethod, FlavorTag, MealRole, ProteinSource

VERSION = "recipe-tags-v1"
INGREDIENT_VERSION = "ingredient-tags-v1"
RULE_BATCH = f"{VERSION}/rules"
LLM_BATCH = f"{VERSION}/llm"
SAMPLE = "data-engineering/docs/recipe-tags-v1-sample.json"
REPORT = "data-engineering/docs/recipe-tags-v1-report.md"
BASIC_SEASONINGS = "data/ingredients/basic-seasonings-v1.json"
SEED = 20261018

MEAL_ROLES: tuple[str, ...] = get_args(MealRole)
FIXED_COURSE_ROLES = {
    "breakfast": "breakfast",
    "dessert": "dessert",
    "sauce_condiment": "sauce",
    "drink": "drink",
    "snack_appetizer": "snack",
    "salad": "salad",
}

# Grain staples a dish can carry, as release ids. Dry ones count at COOKED_YIELD, as in vegetable_led.
STAPLES = COOKED_STAPLES | {
    "bread",
    "baguette",
    "tortilla",
    "pita_bread",
    "dinner_roll",
    "hamburger_bun",
    "hot_dog_bun",
    "english_muffin",
    "pizza_crust",
    "frozen_bread_dough",
    "taco_shell",
    "shirataki_noodles",
    "mac_and_cheese",
    "rice_paper",
}
# Starchy sides that serve as a meal's staple when they are the dish (mashed potatoes), never inside a main.
STARCHY = frozenset(
    {"potato", "sweet_potato", "mashed_potatoes", "instant_mashed_potato", "hash_brown", "tater_tots", "french_fries"}
)
ONE_BOWL_SHARE = 0.15  # a main's staple share from which it carries its staple
STAPLE_ONLY_SHARE = 0.6  # a protein-less main this much staple is the staple itself
GREY_SHARE = 0.05  # below this a main holds no staple; between the two the model decides
SOUP_ONE_BOWL_SHARE = 0.3
SOUP_GREY_SHARE = 0.1
SIDE_STAPLE_SHARE = 0.5
RICE_GRAINS = COOKED_STAPLES & {"rice", "brown_rice", "glutinous_rice", "wild_rice", "long_grain_wild_rice_mix"}
RICE_DISH = re.compile(r"\b(?:rice|risotto|pilaf|paella)\s*$")
# The noodles, rice and pasta that make a soup a one-bowl meal; barley or quinoa in a soup leave it to the model.
SOUP_STAPLES = COOKED_STAPLES - {
    "barley", "quinoa", "oats", "grits", "bulgur", "wheat_berries", "buckwheat", "wild_rice",
    "long_grain_wild_rice_mix", "couscous",
}  # fmt: skip
NOODLE_SOUP = re.compile(
    r"\b(?:pho|laksa|ramen|noodles?|udon|soba|congee|porridge|jook|juk|bubur|mee|bee hoon|kway teow|kuey teow"
    r"|sopas|arroz caldo|lugaw|mohinga|khao soi|bun bo|wonton noodle)\b"
)
BREAD_TITLE = re.compile(
    r"\b(?:breads?|loaf|loaves|rolls?|buns?|baguettes?|naan|roti|chapatis?|paratha|pitas?|focaccia|ciabatta"
    r"|brioche|tortillas?|flatbreads?|pandesal|pan de sal|challah|cornbread|biscuits?|farls?|crumpets?)\b"
)
BREAKFAST_TITLE = re.compile(r"\b(?:muffins?|scones?|pancakes?|waffles?|granola|croissants?|bagels?|danish)\b")
PIZZA_TITLE = re.compile(r"\b(?:pizzas?|calzones?)\b")
# A dish that is a part of another (a dough, crust, sauce, marinade, stock ...) by its title's final head noun.
# Doughs, crusts and batters are one even after "and" ("Garlic And Oregano Pizza Dough") or in brackets
# ("Masa De Empanadas (Empanada Dough)"); a sauce after "and" belongs to a dish ("Meatballs And Marinara Sauce").
COMPONENT = re.compile(
    r"\b(?:(doughs?|crusts?|batters?|fillings?|toppings?)|sauces?|marinades?|rubs?|dressings?|grav(?:y|ies)|stocks?|broths?|pastes?"
    r"|seasonings?)$"
)
DISH_LINK = re.compile(r"\b(?:with|in|on|over)\b")
AND_LINK = re.compile(r"\b(?:and|n)\b|&")
TITLE_TAIL = re.compile(r"\s+-\s.*$|\s+for\b.*$")  # "Spaghetti Sauce - Slow Cooker", "Meatballs For Spaghetti Sauce"
TITLE_SUFFIX = re.compile(r"(?:\s+(?:recipe|i{1,3}))+$")
WRAPPED_MEAL = re.compile(r"\b(?:pasties|pasty|empanadas?|pierogi|ravioli|tortellini|wontons?|meat pies?)\b")
SANDWICH = re.compile(r"\b(?:sandwich(?:es)?|banh mi|burgers?)\b")
BREAD_CARRIERS = frozenset(
    {"bread", "baguette", "hamburger_bun", "hot_dog_bun", "dinner_roll", "pita_bread", "english_muffin"}
)
COOKED_WORD = re.compile(r"\b(?:cooked|prepared|leftover|boiled|steamed)\b", re.I)
MASS_UNIT = re.compile(r"(?<![a-z])(?:oz|ounces?|lbs?|pounds?|g|grams?|kg|kilograms?)\b", re.I)
VOLUME_UNIT = re.compile(
    r"(?<![a-z])(?:cups?|c\.?|tbsp|tsp|tablespoons?|teaspoons?|pints?|quarts?|gallons?|ml|litres?|liters?)\b", re.I
)
SUBSTITUTION_NOTE = re.compile(r"\b(?:substitut\w*|instead|may|alternativ\w*)\b", re.I)
DOUGH_FLOUR = frozenset({"flour", "bread_flour", "whole_wheat_flour", "self_rising_flour", "semolina"})
BAKED_SIDE = re.compile(r"\b(?:au gratin|gratins?|bakes?|casseroles?|roasts?)\b")
SOUP_TITLE = re.compile(r"\b(?:soups?|broths?|chowders?|bisques?|stews?)\b")
CRITICAL_MODEL_FIELDS = ("meal_role", "contains_staple", "protein_sources")

PROTEIN_SOURCES: tuple[str, ...] = get_args(ProteinSource)
FLESH_SOURCES = frozenset({"chicken", "duck", "pork", "beef", "lamb", "fish", "shellfish"})
SWEET_OR_CONDIMENT = frozenset({"dessert", "drink", "sauce"})
FLESH_SHARE = 0.05
PLANT_EGG_SHARE = 0.10
_SOURCE_IDS = {
    "chicken": "chicken chicken_breast chicken_thigh chicken_wings cooked_chicken cornish_hen chicken_or_turkey turkey"
    " turkey_bacon",
    "duck": "duck goose",
    "pork": "pork pork_belly pork_chop ground_pork bacon ham pancetta prosciutto chorizo pepperoni sausage hot_dog"
    " pork_fatback gyoza",
    "beef": "beef beef_heart beef_steak chipped_beef corned_beef ground_beef pastrami beef_or_turkey veal",
    "lamb": "lamb lamb_chop goat mutton",
    "fish": "fish anchovy catfish cod fish_cake fish_fillet hake halibut milkfish red_snapper salmon salt_cod sardine"
    " smoked_haddock swordfish trout tuna imitation_crab salmon_fillet canned_tuna",
    "shellfish": "shellfish shrimp clam crab lobster mussel oyster scallop squid octopus seafood_mix",
    "soy": "soybean tofu firm_tofu tempeh edamame fermented_soybeans vegetarian_ham vegetarian_sausage",
    "egg": "egg egg_white egg_yolk quail_egg egg_substitute",
    "legume": "adzuki_bean baked_beans black_beans black_bean black_eyed_peas cannellini chickpea fava_bean"
    " kidney_beans lentil red_lentil lima_beans mung_bean pinto_beans refried_beans split_peas toor_dal falafel",
}
SOURCE_OF = {name: source for source, names in _SOURCE_IDS.items() for name in names.split()}
# The source a `MEAT_WORDS` title word names. Sausage is left out: a chicken sausage is not pork.
_TITLE_WORDS = {
    "chicken": "chicken turkey",
    "duck": "duck",
    "pork": "pork bacon ham salami pepperoni chorizo prosciutto pancetta",
    "beef": "beef veal",
    "lamb": "lamb mutton",
    "fish": "fish salmon tuna cod anchovy anchovies sardine sardines",
    "shellfish": "shrimp shrimps prawn prawns crab crabs crabmeat lobster lobsters clam clams mussel mussels oyster"
    " oysters scallop scallops squid octopus",
}
TITLE_SOURCE = {word: source for source, words in _TITLE_WORDS.items() for word in words.split()}
SERVED_WITH = re.compile(r"\b(?:for|(?:great|good|served|serve) with)\b.*", re.IGNORECASE)
QUOTE = re.compile("[\"'\u201c\u2018\ufffd]")

# Cooking-method keywords over the lower-cased title and steps. Deep and stir frying, air frying and the Dutch
# oven are taken out before the plainer words are looked for, so "deep-fry" is not also a pan fry.
DEEP_FRY = re.compile(
    r"deep[- ]?fr(?:y|ied|ies|ying|yer)|deep[- ]fat|oil (?:to|reaches|registers) 3[2-9]\d|(?:inch|inches|cm) of oil"
    r"|oil for (?:deep )?frying|fry (?:them |it )?in (?:hot )?oil until"
)
STIR_FRY = re.compile(r"stir[- ]?fr(?:y|ied|ies|ying)|\bwok\b")
AIR_FRY = re.compile(r"air[- ]?fr(?:y|ied|ies|ying|yer)")
DUTCH_OVEN = re.compile(r"dutch ovens?")
PAN_FRY = re.compile(
    r"\b(?:saut[eé]e?[ds]?|saut[eé]ing|sear(?:ed|ing|s)?|pan[- ]?fr\w*|shallow[- ]?fr\w*"
    r"|skillet|frying pan|brown (?:the|meat|beef|chicken|pork|lamb|on all sides))\b"
)
# A bare "fry" or "fried" is a pan fry only in a dish that is not deep-fried ("Fried Chicken").
FRY = re.compile(r"\b(?:fry|fries|fried|frying)\b")
STEAM = re.compile(
    r"\bsteamer\b|\bsteam(?:ed|ing)?\s+(?:for|until|over|in|on|the|it|them|covered|about|gently)\b"
    r"|\bsteaming (?:basket|rack|tray)"
)
BOIL = re.compile(r"\b(?:boil\w*|simmer\w*|poach\w*|blanch\w*|parboil\w*)\b")
BRAISE = re.compile(r"\b(?:brais\w*|stew(?:ed|ing)?|slow[- ]?cook\w*|crock[- ]?pot|pressure[- ]cook\w*|instant pot)\b")
BAKE = re.compile(r"\b(?:bak(?:e|ed|es|ing)(?! (?:soda|powder))|roast\w*|oven)\b")
GRILL = re.compile(r"\b(?:grill\w*|broil\w*|barbecue\w*|barbeque\w*|bbq|char[- ]?grill\w*|griddle)\b")
HEAT = re.compile(r"\b(?:cook\w*|heat\w*|warm\w*|melt\w*|toast\w*|microwav\w*|fire|flame|temperature|scald\w*)\b")
OVEN = re.compile(
    r"\boven\b|\bbak(?:e|ed|es)\b|\bbaking (?:dish|sheet|pan|tray|tin)\b"
    r"|\broast(?:ed|ing)? (?:in|at|for|until)\b|\bbroil"
)
MICROWAVE = re.compile(r"\bmicrowav")
BLENDER = re.compile(
    r"\bblender\b|food processor|\bprocessor\b|liquidi[sz]e|\bblitz|\bblend (?:until|till|on high|on low|to a)"
    r"|pur[eé]e (?:in|until|the|it|with|them)"
)

HOT = frozenset(
    {
        "chili_pepper",
        "green_chili",
        "jalapeno",
        "habanero_pepper",
        "scotch_bonnet",
        "chipotle_pepper",
        "chipotle_in_adobo",
        "gochugaru",
        "gochujang",
        "gochujang_sauce",
        "sambal_oelek",
        "sriracha",
        "hot_sauce",
        "chili_oil",
        "chili_paste",
        "chili_sauce",
        "chili_garlic_sauce",
        "harissa",
        "curry_paste",
        "laksa_paste",
        "tom_yum_paste",
        "szechwan_pepper",
        "wasabi",
        "berbere",
        "jerk_seasoning",
    }
)
HOT_POWDER = frozenset({"cayenne", "chili_powder"})
HOT_GRAMS = 1.0  # grams a serving of a hot ingredient that make a dish spicy
HOT_POWDER_GRAMS = 0.5
SPICY_TITLE = re.compile(
    r"\b(?:spicy|hot and sour|hot & sour|chil(?:i|li|e)|sichuan|szechuan|szechwan|buffalo|jerk|vindaloo|sambal"
    r"|mala|kung pao|diablo|arrabbiata|piri|peri|harissa|fiery|gochujang|tom yum|tom yam|rendang|phaal)\b"
)
AROMATICS = frozenset(
    {
        "garlic",
        "ginger",
        "galangal",
        "green_onion",
        "shallot",
        "leek",
        "chives",
        "lemongrass",
        "kaffir_lime_leaf",
        "curry_leaf",
        "pandan_leaf",
        "basil",
        "thai_basil",
        "cilantro",
        "mint",
        "perilla",
        "dill",
        "rosemary",
        "thyme",
        "sage",
        "tarragon",
        "anise",
        "cinnamon",
        "cloves_spice",
        "cardamom",
        "cumin",
        "coriander",
        "fennel_seed",
        "garam_masala",
        "curry_powder",
        "chinese_five_spice",
        "sesame_oil",
        "saffron",
        "turmeric",
        "szechwan_pepper",
    }
)
FRAGRANT_COUNT = 3
COCONUT_BASE = frozenset({"coconut_milk", "coconut_cream"})
COCONUT_SHARE = 0.15
RICH_FAT_SHARE = 0.5
RICH_FAT_GRAMS = 35.0
LIGHT_FAT_SHARE = 0.3
LIGHT_KCAL = 450.0
NO_RICHNESS_ROLES = frozenset({"sauce", "drink"})

LEAFY = frozenset(
    {
        "arugula",
        "bok_choy",
        "collard",
        "gai_lan",
        "kale",
        "lettuce",
        "spinach",
        "swiss_chard",
        "watercress",
        "pea_shoots",
        "radish_sprouts",
        "bean_sprouts",
    }
)
FRESH_FISH = frozenset(
    {"catfish", "cod", "fish_fillet", "hake", "halibut", "milkfish", "red_snapper", "salmon", "swordfish", "trout"}
)
FRESH_SHELLFISH = frozenset(
    {"shrimp", "clam", "crab", "lobster", "mussel", "oyster", "scallop", "squid", "octopus", "seafood_mix"}
)
PERISHABLE = LEAFY | FRESH_FISH | FRESH_SHELLFISH
PRESERVED = re.compile(r"(?:^|_)(?:canned|dried|smoked|salt|salted|frozen|pickled|cured)(?:_|$)")


@dataclass
class Line:
    name: str
    grams: float | None
    text: str | None


@dataclass
class Dish:
    key: str
    title: str
    course: str
    cuisine: str
    servings: int
    kcal: float | None
    fat_g: float | None
    sugar_g: float | None
    carbohydrate_g: float | None
    lines: list[Line]
    steps: str
    curated: bool = False


@dataclass
class Tags:
    values: dict = field(default_factory=dict)
    methods: dict = field(default_factory=dict)
    # What the model is asked to decide: "meal_role", "protein_sources".
    open: list[str] = field(default_factory=list)
    allowed_roles: tuple[str, ...] = MEAL_ROLES
    # Only protein sources supported by ingredient lines; a title is not ingredient evidence.
    allowed_sources: frozenset[str] = frozenset(PROTEIN_SOURCES)
    incomplete_reason: str | None = None


def release_name(name: str) -> str:
    """The release id an ingredient is, or is the same as or a variety of (`baby_spinach` is `spinach`)."""
    return food_groups().get(name, (name, None, None))[0]


def group_of(name: str) -> str | None:
    return food_groups().get(name, (name, None, None))[1]


def origin_of(name: str) -> str | None:
    return food_groups().get(name, (name, None, None))[2]


def counted(line: Line) -> bool:
    return release_name(line.name) not in UNCOUNTED and group_of(line.name) not in UNCOUNTED_GROUPS


def source_of(name: str) -> str | None:
    """A main-protein source, `"?"` for meat or fish the table cannot name, or None."""
    # Not the hierarchy's made_from links: soy sauce is made from soybeans and broth from chicken; neither is protein.
    if release_name(name) in SEASONING_FROM_FLESH:
        return None
    for candidate in (name, release_name(name)):
        if candidate in SOURCE_OF:
            return SOURCE_OF[candidate]
    return "?" if origin_of(name) == "flesh" else None


def line_sources(line: Line) -> set[str]:
    """Explicit ingredient wording refines generic meat; titles never fill a lost line."""
    source = source_of(line.name)
    if release_name(line.name) in SEASONING_FROM_FLESH:
        return set()
    if release_name(line.name) == "imitation_crab":
        return {"fish"}  # The catalog's surimi product, not real crab just because its wording contains "crab".
    text = re.sub(r"\([^)]*\b(?:substitut\w*|instead|may|alternativ\w*)\b[^)]*\)", " ", line.text or "", flags=re.I)
    named = title_sources(text)
    if (
        source in FLESH_SOURCES
        and SUBSTITUTION_NOTE.search(text)
        and not (len(named) > 1 and re.search(r"\bor\b", text, re.I))
    ):
        return {source}  # A stated alternative is not a second animal in a concrete ingredient.
    if named and (source == "?" or source in FLESH_SOURCES):
        # Alternatives are not two animals known to be present.
        if len(named) > 1 and re.search(r"\bor\b", text, re.I):
            return {"?"}
        return named
    return {source} if source is not None else set()


def protein_sources(dish: Dish) -> list[str] | None:
    """Main sources in vocabulary order; None for an unknown animal or inseparable multi-animal weight."""
    total = sum(line.grams for line in dish.lines if line.grams and counted(line))
    grams: Counter[str] = Counter()
    unweighed: set[str] = set()
    for line in dish.lines:
        sources = line_sources(line)
        if not sources:
            continue
        # A combined pork/chicken weight does not tell us either animal's share.
        if len(sources) > 1:
            return None
        source = next(iter(sources))
        if line.grams:
            grams[source] += line.grams
        else:
            unweighed.add(source)
    found = set(unweighed)
    for source, weight in grams.items():
        threshold = PLANT_EGG_SHARE if source in {"soy", "egg", "legume"} else FLESH_SHARE
        if total and weight / total >= threshold:
            found.add(source)
    if "?" in found:
        return None
    # The owner keeps tiny seafood garnishes known, but a named land-meat main below its threshold is uncertain.
    named_meat = title_sources(dish.title) & {"chicken", "duck", "pork", "beef", "lamb"}
    if any(0 < grams[source] < total * FLESH_SHARE for source in named_meat):
        return None
    return [source for source in PROTEIN_SOURCES if source in found]


def title_sources(title: str) -> set[str]:
    """The sources a title names, leaving out a quoted mock meat (Tempeh "Bacon") and what it is served with."""
    title = SERVED_WITH.sub("", title)
    return {
        TITLE_SOURCE[m.group(0).lower()]
        for m in MEAT_WORDS.finditer(title)
        if m.group(0).lower() in TITLE_SOURCE and not QUOTE.match(title[m.start() - 1 : m.start()])
    }


def model_sources(dish: Dish) -> frozenset[str]:
    """Only explicitly supported animals, not every possible animal for an unnamed meat line."""
    held = set().union(*(line_sources(line) for line in dish.lines))
    return frozenset(held - {"?"})


def staple_share(dish: Dish, names: frozenset[str] | set[str] = STAPLES) -> float:
    """The staples' share of a dish's counted grams, dry ones at their cooked weight (as `vegetable_share`)."""
    total = part = 0.0
    for line in dish.lines:
        if not line.grams or not counted(line):
            continue
        name = release_name(line.name)
        text = line.text or ""
        # Mass-unit recipes usually weigh dry noodles then instruct "cooked and drained". Unit wins over wording.
        mass, volume = MASS_UNIT.search(text), VOLUME_UNIT.search(text)
        primary_mass = mass is not None and (volume is None or mass.start() < volume.start())
        already_cooked = (
            COOKED_WORD.search(text)
            and not primary_mass
            and (
                volume
                or re.search(
                    r"\b(?:cooked|prepared|leftover|boiled|steamed)\s+(?:white\s+|brown\s+)?"
                    r"(?:rice|pasta|noodles|macaroni|spaghetti|fettuccine|ziti|basmati)\b",
                    text,
                    re.I,
                )
            )
        )
        weight = line.grams * (COOKED_YIELD if name in COOKED_STAPLES and not already_cooked else 1.0)
        total += weight
        # Flour is a carrier in a complete wrapped meal, not every fried coating or meatloaf binder.
        if name in names or (names == STAPLES and WRAPPED_MEAL.search(dish.title.lower()) and name in DOUGH_FLOUR):
            part += weight
    return part / total if total else 0.0


def dish_vegetable_led(dish: Dish) -> bool:
    return vegetable_led((line.name, line.grams, line.text) for line in dish.lines)


def component(title: str, course: str) -> bool:
    """A recipe that is a part of a dish, not a dish: a dough, crust, batter, filling, topping, sauce, marinade,
    rub, dressing,
    gravy, stock, broth, paste or seasoning by the final head noun of its title, with no "with", "in", "on" or
    "over" before it ("Chicken In Tarragon Sauce" is a dish). A side's dressing is a stuffing, a dish."""
    title = title.lower()
    bare = TITLE_TAIL.sub("", re.sub(r"\([^)]*\)", " ", title)).strip(" \"'!.,;")
    candidates = [(TITLE_SUFFIX.sub("", bare), True)]
    candidates += [(inner.strip(), False) for inner in re.findall(r"\(([^)]*)\)", title)]
    for text, whole in candidates:
        match = COMPONENT.search(text)
        if match is None or (not whole and match.group(1) is None):
            continue
        before = text[: match.start()]
        if DISH_LINK.search(before) or (match.group(1) is None and AND_LINK.search(before)):
            continue
        if match.group(0).startswith("dressing") and course == "side":
            continue
        return True
    return False


def meal_role(dish: Dish, sources: list[str] | None, led: bool) -> tuple[str | None, tuple[str, ...]]:
    """The rule's role, or None with the roles the model may choose from."""
    title = dish.title.lower()
    open_roles = tuple(role for role in MEAL_ROLES if led or role not in {"vegetable", "salad"})
    if component(dish.title, dish.course):
        return "sauce", ()  # `sauce` is every non-meal part of a dish, a dough or stock as much as a sauce
    if dish.course in FIXED_COURSE_ROLES:
        return FIXED_COURSE_ROLES[dish.course], ()
    has_protein = sources is None or bool(sources)
    if dish.course == "baked_good":
        sweet = bool(dish.carbohydrate_g) and (dish.sugar_g or 0) / dish.carbohydrate_g >= 0.3
        if PIZZA_TITLE.search(title):
            return "one_bowl", ()
        if BREAKFAST_TITLE.search(title):
            return "breakfast", ()
        if BREAD_TITLE.search(title) and dish.carbohydrate_g and (dish.sugar_g or 0) / dish.carbohydrate_g < 0.2:
            return "staple", ()
        if sweet:
            return "dessert", ()
        return None, ("breakfast", "dessert", "staple", "snack", "one_bowl", "protein_main")
    share = staple_share(dish)
    if share == 0:
        open_roles = tuple(role for role in open_roles if role not in {"one_bowl", "staple"})
    if SANDWICH.search(title) and any(release_name(line.name) in BREAD_CARRIERS for line in dish.lines):
        return "one_bowl", ()
    if dish.course == "soup":
        # A noodle soup by its title, a soup this much staple, or one whose noodles or rice are a tenth of it.
        cooked = staple_share(dish, SOUP_STAPLES) >= SOUP_GREY_SHARE
        if (NOODLE_SOUP.search(title) and share > 0) or share >= SOUP_ONE_BOWL_SHARE or cooked:
            return "one_bowl", ()
        if share < SOUP_GREY_SHARE:
            return "soup", ()
        return None, ("soup", "one_bowl")
    if dish.course == "side":
        # A rice dish may have been filed as a side; its real rice carrier still fills the staple.
        if RICE_DISH.search(title) and staple_share(dish, RICE_GRAINS) >= ONE_BOWL_SHARE:
            return ("one_bowl" if has_protein else "staple"), ()
        if led:
            return "vegetable", ()
        if staple_share(dish, STAPLES | STARCHY) >= SIDE_STAPLE_SHARE:
            return "staple", ()
        # A side is never the meal's main, even with bacon in it; one that is not vegetable-led may stay null.
        return None, tuple(
            role
            for role in open_roles
            if role != "protein_main"
            and not (role == "soup" and BAKED_SIDE.search(title) and not SOUP_TITLE.search(title))
        )
    # main, and the curated catalog's mains
    if share >= ONE_BOWL_SHARE:
        return ("staple" if not has_protein and share >= STAPLE_ONLY_SHARE else "one_bowl"), ()
    if share >= GREY_SHARE and not sources:
        return None, ("staple", *(("vegetable",) if led else ()))
    if has_protein:
        return "protein_main", ()
    if led:
        return "vegetable", ()
    return None, open_roles


def cooking_methods(dish: Dish) -> list[str]:
    text = f"{dish.title}\n{dish.steps}".lower()
    found = []
    if DEEP_FRY.search(text):
        found.append("deep_fry")
    if STIR_FRY.search(text):
        found.append("stir_fry")
    plain = DUTCH_OVEN.sub("pot", AIR_FRY.sub("air-crisp", STIR_FRY.sub("", DEEP_FRY.sub("", text))))
    if PAN_FRY.search(plain) or (FRY.search(plain) and "deep_fry" not in found):
        found.append("pan_fry")
    for method, pattern in (("steam", STEAM), ("boil", BOIL), ("braise", BRAISE)):
        if pattern.search(plain):
            found.append(method)
    if BAKE.search(plain) or AIR_FRY.search(text):
        found.append("bake")
    if GRILL.search(plain):
        found.append("grill")
    if not found and not HEAT.search(plain):
        found.append("raw")
    return found


def equipment(dish: Dish) -> list[list[str]]:
    text = DUTCH_OVEN.sub("pot", f"{dish.title}\n{dish.steps}".lower())
    oven = bool(OVEN.search(AIR_FRY.sub("", text)))
    air = bool(AIR_FRY.search(text))
    needs = []
    if oven or air:
        needs.append([name for name, used in (("oven", oven), ("air_fryer", air)) if used])
    if STEAM.search(text):
        needs.append(["steamer"])
    if MICROWAVE.search(text):
        needs.append(["microwave"])
    if BLENDER.search(text):
        needs.append(["blender"])
    return needs


def flavor_tags(dish: Dish, role: str | None, methods: list[str]) -> list[str]:
    title = dish.title.lower()
    per_serving: Counter[str] = Counter()
    names = set()
    for line in dish.lines:
        name = release_name(line.name)
        names.add(name)
        if line.grams:
            per_serving[name] += line.grams / max(dish.servings, 1)
    hot = sum(per_serving[n] for n in HOT) >= HOT_GRAMS or sum(per_serving[n] for n in HOT_POWDER) >= HOT_POWDER_GRAMS
    tags = []
    if len(names & AROMATICS) >= FRAGRANT_COUNT:
        tags.append("fragrant")
    if hot or SPICY_TITLE.search(title):
        tags.append("spicy")
    if role in NO_RICHNESS_ROLES or not dish.kcal:
        return tags
    fat_share = (dish.fat_g or 0) * 9 / dish.kcal
    total = sum(line.grams for line in dish.lines if line.grams and counted(line))
    coconut = sum(line.grams for line in dish.lines if line.grams and release_name(line.name) in COCONUT_BASE)
    rich = fat_share >= RICH_FAT_SHARE or (dish.fat_g or 0) >= RICH_FAT_GRAMS
    rich = rich or bool(total) and coconut / (total + coconut) >= COCONUT_SHARE
    if rich:
        tags.append("rich")
    elif fat_share <= LIGHT_FAT_SHARE and dish.kcal <= LIGHT_KCAL and "deep_fry" not in methods:
        tags.append("light")
    return tags


def rule_tags(dish: Dish) -> Tags:
    tags = Tags()
    led = dish_vegetable_led(dish)
    sources = protein_sources(dish)
    role, allowed = meal_role(dish, sources, led)
    if not dish.curated and (conflict := reviewed_source_conflict(dish.key)):
        tags.incomplete_reason, sources = conflict, None
    elif not dish.curated and dish.course in {"main", "side", "soup"} and not component(dish.title, dish.course):
        tags.incomplete_reason = missing_named_protein(dish.title, [(line.name, line.text) for line in dish.lines])
        if tags.incomplete_reason:
            role, allowed, sources = None, (), None
    if sources == []:  # a dish with no main protein is never a protein main, whatever the model would say
        allowed = tuple(name for name in allowed if name != "protein_main")
    if role in SWEET_OR_CONDIMENT:
        sources = []  # the eggs of a cake are not its main protein
    methods = cooking_methods(dish)
    decided = {
        "meal_role": role,
        "contains_staple": None if role is None else role in {"one_bowl", "staple"},
        "protein_sources": sources,
        "cooking_methods": methods,
        "equipment": equipment(dish),
        "flavor_tags": flavor_tags(dish, role, methods),
    }
    for name, value in decided.items():
        tags.values[name] = value
        if value is not None:
            tags.methods[name] = "rule"
    if role is None and allowed:
        tags.open.append("meal_role")
        tags.allowed_roles = allowed
    # Unspecified meat and missing flesh lines are evidence gaps, not questions for a model to guess.
    tags.allowed_sources = model_sources(dish)
    return tags


# --- the catalog -------------------------------------------------------------------------------------------


def release_dishes(directory: Path | None = None) -> list[Dish]:
    """Every release recipe the importer loads, with its lines as the importer corrects them."""
    directory = directory or release_dir()
    corrections = json.loads((repository_root() / LINE_CORRECTIONS).read_text(encoding="utf-8"))["corrections"]
    corrected = {(c["recipe_id"], c["original_text"]): c["ingredient"]["normalized_name"] for c in corrections}
    dishes = []
    with (directory / "recipes.jsonl").open(encoding="utf-8") as handle:
        for record in map(json.loads, filter(str.strip, handle)):
            steps = [step["text"].strip() for step in record["instructions"] if step["text"].strip()]
            if len(record["ingredients"]) < 2 or not steps:
                continue
            lines = [
                Line(
                    corrected.get(
                        (record["recipe_id"], line["original_text"]), line["canonical_ingredient_id"][4:].lower()
                    ),
                    float(round(line["grams"], 2)) or None,
                    line["original_text"],
                )
                for line in record["ingredients"]
            ]
            nutrition = record["nutrition"]
            dishes.append(
                Dish(
                    key=record["recipe_id"],
                    title=record["title"],
                    course=record["course"],
                    cuisine=record["cuisine"],
                    servings=int(record["servings"]),
                    kcal=nutrition["energy_kcal"],
                    fat_g=nutrition["fat_g"],
                    sugar_g=nutrition["sugar_g"],
                    carbohydrate_g=nutrition["carbohydrate_g"],
                    lines=lines,
                    steps="\n".join(steps),
                )
            )
    return dishes


def curated_dishes() -> list[Dish]:
    data = repository_root() / "data"
    catalog = load_catalog(data / "ingredients/ingredients.json", data / "recipes/recipes.json")
    return [
        Dish(
            key=recipe.slug,
            title=recipe.title,
            course=recipe.meal_type,
            cuisine=recipe.cuisine,
            servings=recipe.servings,
            kcal=recipe.nutrition.calories_kcal,
            fat_g=recipe.nutrition.fat_g,
            sugar_g=recipe.nutrition.sugar_g,
            carbohydrate_g=recipe.nutrition.carbohydrate_g,
            # Only gram lines are weighed, as `app.planning.vegetable_led.weighed` reads the curated catalog.
            lines=[
                Line(item.ingredient, item.quantity if item.unit == "g" else None, None) for item in recipe.ingredients
            ],
            steps="\n".join(recipe.steps),
            curated=True,
        )
        for recipe in catalog.recipes
    ]


def catalog_ingredients() -> list[str]:
    """Every ingredient `normalized_name` an import can create: release, curated and line-correction targets."""
    root = repository_root()
    names = {
        line["ingredient_id"][4:].lower()
        for line in map(
            json.loads,
            filter(str.strip, (release_dir() / "ingredients.jsonl").read_text(encoding="utf-8").splitlines()),
        )
    }
    names |= {
        item["normalized_name"]
        for item in json.loads((root / "data/ingredients/ingredients.json").read_text(encoding="utf-8"))
    }
    corrections = json.loads((root / LINE_CORRECTIONS).read_text(encoding="utf-8"))["corrections"]
    names |= {c["ingredient"]["normalized_name"] for c in corrections}
    return sorted(names)


def ingredient_entry(name: str, basics: set[str]) -> dict:
    groups = food_groups()
    release, group, _ = groups.get(name, (name, None, None))
    perishable = (name in PERISHABLE or release in PERISHABLE) and not PRESERVED.search(name)
    return {
        "food_group": group,
        "perishable": perishable,
        "basic_seasoning": name in basics,
        "methods": {
            "food_group": "release" if release == name and group else ("hierarchy" if group else "none"),
            "perishable": "rule",
            "basic_seasoning": "basic-seasonings-v1",
        },
    }


# --- the language model ------------------------------------------------------------------------------------

# USD per million tokens, an upper estimate for gpt-5.4-mini; the cap stops the run on this estimate.
INPUT_USD_PER_M = 0.75
OUTPUT_USD_PER_M = 4.5
BATCH_SIZE = 20
PROMPT = """You tag recipes for a Singapore household meal planner. For each recipe, decide only the fields listed in
"decide". Use only the allowed values.

meal_role: what the dish is in a meal.
- protein_main: a dish built on meat, fish, seafood, tofu, egg or legumes, eaten with rice or another staple.
- one_bowl: a complete dish that carries its own staple (rice, noodles, pasta, bread), e.g. fried rice, laksa, a
  sandwich, a pasta dish.
- staple: the meal's starch on its own (rice, noodles, bread, flatbread, potatoes as a side).
- vegetable: a vegetable side dish. soup: a soup served beside the meal. breakfast: breakfast-only food.
- snack, dessert, sauce, drink: never a lunch or dinner dish.
- Egg rolls, spring rolls, dumplings, fritters, dips and other finger food are snack, not protein_main.
- A soup with noodles, rice or dumplings as a large part of it is one_bowl, not soup.
- A title may signal a missing ingredient, but never proves that the ingredient exists. Do not fill a lost line.
- When none of "allowed_meal_roles" fits the dish (a vegetable side when vegetable is not allowed), answer null.
protein_sources: the main protein sources of the dish, from "allowed_protein_sources" only; [] when it has no
main protein. Name only sources the ingredient lines explicitly support: never add legume without a bean, lentil
or pea line, nor egg or soy without an egg or soy line. Turkey and other poultry are chicken, goose is duck,
goat or mutton is lamb, veal is beef. An unnamed animal or a line that is only "meat" stays unknown: answer null,
never infer beef and pork, never guess the closest animal from cuisine or the title.

Recipes (JSON):
{recipes}
"""


def _llm_payload(dish: Dish, tags: Tags) -> dict:
    return {
        "key": dish.key,
        "title": dish.title,
        "course": dish.course,
        "cuisine": dish.cuisine,
        "ingredients": [f"{line.name} {round(line.grams) if line.grams else '?'} g" for line in dish.lines][:25],
        "steps": dish.steps[:500],
        "decide": tags.open,
        "allowed_meal_roles": list(tags.allowed_roles) if "meal_role" in tags.open else [],
        "allowed_protein_sources": [s for s in PROTEIN_SOURCES if s in tags.allowed_sources]
        if "protein_sources" in tags.open
        else [],
    }


def ask_model(open_dishes: list[tuple[Dish, Tags]], max_usd: float, log) -> dict:
    """The model's answers by recipe key, batched, stopping once the estimated spend would pass `max_usd`."""
    from langchain_openai import ChatOpenAI
    from pydantic import BaseModel

    from app.core.config import get_settings

    settings = get_settings()
    usage = {"calls": 0, "input_tokens": 0, "output_tokens": 0, "usd": 0.0, "stopped": False, "model": None}
    if settings.openai_api_key is None:
        log("No OpenAI key configured; the open fields stay null.")
        return {"answers": {}, "usage": usage}

    class Answer(BaseModel):
        key: str
        meal_role: MealRole | None
        protein_sources: list[ProteinSource] | None

    class Answers(BaseModel):
        recipes: list[Answer]

    usage["model"] = settings.openai_model
    model = ChatOpenAI(
        api_key=settings.openai_api_key.get_secret_value(), model=settings.openai_model, temperature=0, timeout=120
    ).with_structured_output(Answers, method="json_schema", include_raw=True)
    answers: dict[str, dict] = {}
    for start in range(0, len(open_dishes), BATCH_SIZE):
        batch = open_dishes[start : start + BATCH_SIZE]
        if usage["calls"]:
            per_call = usage["usd"] / usage["calls"]
            if usage["usd"] + per_call > max_usd:
                usage["stopped"] = True
                log(f"Spend cap reached at an estimated US${usage['usd']:.3f}; {len(open_dishes) - start} left null.")
                break
        payload = json.dumps([_llm_payload(dish, tags) for dish, tags in batch], ensure_ascii=False)
        result = model.invoke(PROMPT.format(recipes=payload))
        meta = getattr(result["raw"], "usage_metadata", None) or {}
        usage["calls"] += 1
        usage["input_tokens"] += meta.get("input_tokens", 0)
        usage["output_tokens"] += meta.get("output_tokens", 0)
        usage["usd"] = (usage["input_tokens"] * INPUT_USD_PER_M + usage["output_tokens"] * OUTPUT_USD_PER_M) / 1_000_000
        log(
            f"model batch {usage['calls']}: {meta.get('input_tokens', 0)} in, {meta.get('output_tokens', 0)} out,"
            f" US${usage['usd']:.4f} so far"
        )
        parsed = result.get("parsed")
        for answer in parsed.recipes if parsed else []:
            answers[answer.key] = answer.model_dump()
    return {"answers": answers, "usage": usage}


def merge_answer(tags: Tags, answer: dict) -> None:
    """Take the model's open fields when they are allowed; anything else stays null.

    A protein the dish's lines do not support (a legume with no bean line) is dropped, and a role
    the model makes sweet or a condiment has no protein, as with the rules.
    """
    role = answer.get("meal_role")
    if "meal_role" in tags.open and role in tags.allowed_roles:
        tags.values["meal_role"] = role
        tags.values["contains_staple"] = role in {"one_bowl", "staple"}
        tags.methods["meal_role"] = tags.methods["contains_staple"] = "llm"
        if role in SWEET_OR_CONDIMENT:
            tags.values["protein_sources"] = []
            tags.methods["protein_sources"] = "llm"
            return
    sources = answer.get("protein_sources")
    if "protein_sources" in tags.open and sources is not None and set(sources) <= set(PROTEIN_SOURCES):
        tags.values["protein_sources"] = [s for s in PROTEIN_SOURCES if s in sources and s in tags.allowed_sources]
        tags.methods["protein_sources"] = "llm"


# --- writing -----------------------------------------------------------------------------------------------


def recipe_entry(tags: Tags, previous: dict | None = None) -> dict:
    """The tag file's entry; a value the owner accepted (`--accept-batch`) stays reviewed while it is unchanged."""
    previous = previous or {}
    entry = {name: tags.values[name] for name in tags.values}
    entry["estimated"] = {}
    for name, method in tags.methods.items():
        batch = RULE_BATCH if method == "rule" else LLM_BATCH
        held = previous.get("estimated", {}).get(name, {})
        same = held.get("batch") == batch and held.get("method") == method and previous.get(name) == entry[name]
        entry["estimated"][name] = {"method": method, "batch": batch, "reviewed": bool(same and held.get("reviewed"))}
    return entry


def accept_batch(batch: str) -> int:
    """Mark every model-decided value of `batch` in the recipe tag file reviewed, after the owner's spot check of
    its sample (data-engineering/README.md); the importer then carries `reviewed` onto the rows and the planner
    reads the values. Returns how many values were accepted."""
    path = repository_root() / RECIPE_TAGS
    data = json.loads(path.read_text(encoding="utf-8"))
    accepted = 0
    for entry in data["recipes"].values():
        for estimate in entry.get("estimated", {}).values():
            if estimate["batch"] == batch and estimate["method"] == "llm" and not estimate["reviewed"]:
                estimate["reviewed"] = True
                accepted += 1
    header = {name: value for name, value in data.items() if name != "recipes"}
    write_keyed(path, header, "recipes", data["recipes"])
    return accepted


def write_keyed(path: Path, header: dict, key: str, entries: dict[str, dict]) -> None:
    """One entry per line, so a change to one recipe is a one-line diff."""
    body = ",\n".join(
        f"    {json.dumps(name)}: {json.dumps(entry, ensure_ascii=False, sort_keys=True)}"
        for name, entry in entries.items()
    )
    head = json.dumps(header, indent=2, ensure_ascii=False)[:-2]
    path.write_text(f"{head},\n  {json.dumps(key)}: {{\n{body}\n  }}\n}}\n", encoding="utf-8", newline="\n")


NO_USAGE = {"calls": 0, "input_tokens": 0, "output_tokens": 0, "usd": 0.0, "asked": 0, "stopped": False, "model": None}


def previous_file() -> dict:
    path = repository_root() / RECIPE_TAGS
    return json.loads(path.read_text(encoding="utf-8")) if path.exists() else {}


def previous_answers(previous: dict) -> dict[str, dict]:
    """The model's earlier decisions, so a re-run asks only for what is still open."""
    kept = {}
    for key, entry in previous.get("recipes", {}).items():
        llm = [name for name, estimate in entry.get("estimated", {}).items() if estimate["method"] == "llm"]
        if llm:
            kept[key] = {name: entry[name] for name in llm}
    return kept


def build(use_llm: bool, max_usd: float, log=print, reask: bool = False) -> dict:
    dishes = curated_dishes() + release_dishes()
    tagged = [(dish, rule_tags(dish)) for dish in dishes]
    previous = previous_file()
    earlier = {} if reask else previous_answers(previous)
    for dish, tags in tagged:
        if dish.key in earlier and tags.open:
            merge_answer(tags, earlier[dish.key])
        # Keep the failed, unreviewed model batch frozen. Better rules do not silently release those recipes.
        if not reask:
            entry = previous.get("recipes", {}).get(dish.key, {})
            for name in CRITICAL_MODEL_FIELDS:
                estimate = entry.get("estimated", {}).get(name, {})
                if estimate.get("method") == "llm" and not estimate.get("reviewed"):
                    tags.values[name] = entry[name]
                    tags.methods[name] = "llm"
    still_open = [(dish, tags) for dish, tags in tagged if any(tags.values[name] is None for name in tags.open)]
    # The model's spend over every run, kept in the tag file's header.
    usage = dict(NO_USAGE) | previous.get("llm_usage", {})
    if use_llm and still_open:
        result = ask_model(still_open, max_usd, log)
        run = result["usage"]
        for name in ("calls", "input_tokens", "output_tokens", "usd"):
            usage[name] += run[name]
        usage.update(
            asked=usage["asked"] + (len(still_open) if run["calls"] else 0),
            stopped=run["stopped"],
            model=run["model"] or usage["model"],
        )
        for dish, tags in still_open:
            if dish.key in result["answers"]:
                merge_answer(tags, result["answers"][dish.key])
    usage["usd"] = round(usage["usd"], 4)
    return {"tagged": tagged, "usage": usage, "open": len(still_open)}


def ingredient_entries() -> dict[str, dict]:
    basics = {
        item["normalized_name"]
        for item in json.loads((repository_root() / BASIC_SEASONINGS).read_text(encoding="utf-8"))["items"]
    }
    return {name: ingredient_entry(name, basics) for name in catalog_ingredients()}


def hearty_salad(dish: Dish, tags: Tags) -> bool:
    """A salad the vegetable side cannot take (not vegetable-led) that carries a main protein."""
    return tags.values["meal_role"] == "salad" and bool(tags.values["protein_sources"]) and not dish_vegetable_led(dish)


def sample_packet(tagged: list[tuple[Dish, Tags]], ingredients: dict[str, dict]) -> dict:
    """At least 100 recipes stratified by meal role and how it was decided, plus 50 ingredients."""
    rng = random.Random(SEED)
    strata: dict[tuple, list] = {}
    for dish, tags in tagged:
        strata.setdefault((str(tags.values["meal_role"]), tags.methods.get("meal_role", "open")), []).append(
            (dish, tags)
        )
    total = len(tagged)
    picked = []
    for stratum in sorted(strata):
        members = strata[stratum]
        count = min(len(members), max(4, round(110 * len(members) / total)))
        picked.extend((*pair, f"meal_role {stratum[0]} by {stratum[1]}") for pair in rng.sample(members, count))
    # Two strata the owner must review before the planner reads these values: the model's protein answers
    # (they feed the hard no-repeat rule), and hearty salads, which as `salad` only ever fill the vegetable side.
    extra = {
        "llm protein_sources": [pair for pair in tagged if pair[1].methods.get("protein_sources") == "llm"],
        "hearty salad": [pair for pair in tagged if hearty_salad(*pair)],
    }
    chosen = {dish.key for dish, _, _ in picked}
    for why, members in extra.items():
        members = [pair for pair in members if pair[0].key not in chosen]
        more = rng.sample(members, min(len(members), 20))
        picked.extend((*pair, why) for pair in more)
        chosen |= {dish.key for dish, _ in more}
    recipes = [
        {
            "key": dish.key,
            "title": dish.title,
            "course": dish.course,
            "cuisine": dish.cuisine,
            "ingredients": [line.text or line.name for line in dish.lines],
            "tags": {name: tags.values[name] for name in tags.values},
            "methods": dict(tags.methods),
            "why": why,
            "verdict": {name: None for name in tags.values} | {"note": ""},
        }
        for dish, tags, why in picked
    ]
    perishable = sorted(name for name, entry in ingredients.items() if entry["perishable"])
    basic = sorted(name for name, entry in ingredients.items() if entry["basic_seasoning"])
    rest = sorted(set(ingredients) - set(perishable) - set(basic))
    others = rng.sample(rest, max(0, 50 - len(perishable) - len(basic)) + 10)
    return {
        "version": f"{VERSION}-sample",
        "seed": SEED,
        "how_to_review": "data-engineering/README.md, section 'Reviewing recipe and ingredient tags'",
        "recipes": recipes,
        "ingredients": [
            {
                "normalized_name": name,
                "tags": {key: ingredients[name][key] for key in ("food_group", "perishable", "basic_seasoning")},
                "why": "every perishable" if name in perishable else ("every basic" if name in basic else "random"),
                "verdict": {"perishable": None, "basic_seasoning": None, "note": ""},
            }
            for name in perishable + basic + sorted(others)
        ],
    }


def report(tagged: list[tuple[Dish, Tags]], ingredients: dict[str, dict], usage: dict) -> str:
    fields = ("meal_role", "contains_staple", "protein_sources", "cooking_methods", "equipment", "flavor_tags")
    lines = [
        "# Recipe and ingredient tags v1: coverage",
        "",
        "Generated by `python -m app.data.recipe_tags` (rules in `backend/app/data/recipe_tags.py`); do not edit.",
        f"Recipes: {len(tagged)} (release v2.1 recipes the importer loads, and the curated catalog). "
        f"Ingredients: {len(ingredients)}.",
        "",
        "## How each recipe field was decided",
        "",
        "| Field | rule | llm | open (null) |",
        "| --- | ---: | ---: | ---: |",
    ]
    for name in fields:
        methods = Counter(tags.methods.get(name, "open") for _, tags in tagged)
        lines.append(f"| `{name}` | {methods['rule']} | {methods['llm']} | {methods['open']} |")
    lines += ["", "## Meal role by method", "", "| Meal role | rule | llm |", "| --- | ---: | ---: |"]
    roles = Counter((tags.values["meal_role"], tags.methods.get("meal_role", "open")) for _, tags in tagged)
    for role in (*MEAL_ROLES, None):
        lines.append(f"| {role or 'open (null)'} | {roles[(role, 'rule')]} | {roles[(role, 'llm')]} |")
    value_counts = {
        "protein_sources": PROTEIN_SOURCES,
        "cooking_methods": get_args(CookingMethod),
        "flavor_tags": get_args(FlavorTag),
    }
    for name, values in value_counts.items():
        counts = Counter(value for _, tags in tagged for value in tags.values[name] or [])
        empty = sum(1 for _, tags in tagged if tags.values[name] == [])
        lines += ["", f"## `{name}` values (recipes carrying each)", "", "| Value | Recipes |", "| --- | ---: |"]
        lines += [f"| {value} | {counts[value]} |" for value in values]
        lines.append(f"| none (`[]`) | {empty} |")
    staple = Counter(tags.values["contains_staple"] for _, tags in tagged)
    groups = Counter(str(tuple(group)) for _, tags in tagged for group in tags.values["equipment"])
    lines += ["", "## `contains_staple` and `equipment`", "", "| Value | Recipes |", "| --- | ---: |"]
    lines += [f"| contains_staple {value} | {staple[value]} |" for value in (True, False, None)]
    lines += [f"| equipment {group} | {count} |" for group, count in sorted(groups.items())]
    lines.append(f"| no equipment (`[]`) | {sum(1 for _, t in tagged if t.values['equipment'] == [])} |")
    lines += [
        "",
        f"Hearty salads (`salad`, not vegetable-led, with a main protein): {sum(hearty_salad(*p) for p in tagged)}. "
        "As salads they fill only the vegetable side, which their vegetable-led check refuses, so they fill no slot: "
        "the owner decided on 2026-10-19 that a salad with meat is not a main. The sample packet carries them as "
        "their own stratum, as it does the model's protein answers. The planner reads no model-decided value "
        "before its batch sample is reviewed.",
    ]
    blocked = [(dish, tags) for dish, tags in tagged if tags.incomplete_reason]
    lines += [
        "",
        "## Incomplete recipe evidence",
        "",
        "A meat-bearing title with no matching ingredient line is incomplete, not a protein inference. "
        "The planner uses the same missing-line check. Frozen unreviewed model fields may still show their "
        "historical value, but remain gated; no batch is accepted by this regeneration.",
        "",
        "| Recipe | Title | Missing-line reason |",
        "| --- | --- | --- |",
    ]
    lines += [f"| {dish.key} | {dish.title.replace('|', '/')} | {tags.incomplete_reason} |" for dish, tags in blocked]
    perishable = sorted(name for name, entry in ingredients.items() if entry["perishable"])
    origin = Counter(entry["methods"]["food_group"] for entry in ingredients.values())
    lines += [
        "",
        "## Ingredients",
        "",
        "| Field | Value | Count |",
        "| --- | --- | ---: |",
        f"| `food_group` | from the release | {origin['release']} |",
        f"| `food_group` | from the release ingredient it is the same as (hierarchy) | {origin['hierarchy']} |",
        f"| `food_group` | none (null) | {origin['none']} |",
        f"| `perishable` | true (rule; every one is confirmed by the owner) | {len(perishable)} |",
        f"| `perishable` | false | {len(ingredients) - len(perishable)} |",
        f"| `basic_seasoning` | true | {sum(1 for e in ingredients.values() if e['basic_seasoning'])} |",
        "",
        f"Perishable: {', '.join(perishable)}.",
        "",
        "## Language model",
        "",
        f"Recipe questions sent to the model over all runs: {usage['asked']} (recipes with a field the rules left "
        f"open). Model: {usage['model'] or 'not called'}; calls: {usage['calls']}; "
        f"input tokens: {usage['input_tokens']}; "
        f"output tokens: {usage['output_tokens']}; estimated cost: US${usage['usd']:.3f} at US${INPUT_USD_PER_M} "
        f"and US${OUTPUT_USD_PER_M} per million input and output tokens; spend cap hit in the last run: "
        f"{usage['stopped']}. "
        "Earlier model answers are kept in the tag file and reused, so a re-run asks only for what is still open.",
        "",
    ]
    return "\n".join(lines)


def main() -> None:
    parser = argparse.ArgumentParser(description="Tag every catalog recipe and ingredient (recipe-tags-v1).")
    parser.add_argument("--llm", action="store_true", help="ask the configured OpenAI model for the open fields")
    parser.add_argument(
        "--max-usd", type=float, default=5.0, help="estimated spend at which the model is no longer asked"
    )
    parser.add_argument("--reask", action="store_true", help="drop the model's earlier answers and ask again")
    parser.add_argument(
        "--accept-batch",
        metavar="BATCH",
        help=f"mark the model's values of a reviewed batch ({LLM_BATCH}) reviewed in the tag file, and stop",
    )
    args = parser.parse_args()

    root = repository_root()
    if args.accept_batch:
        print(f"Accepted {accept_batch(args.accept_batch)} model-decided values of {args.accept_batch}.")
        return
    previous = previous_file().get("recipes", {})
    result = build(args.llm, args.max_usd, reask=args.reask)
    tagged = result["tagged"]
    write_keyed(
        root / RECIPE_TAGS,
        {
            "version": VERSION,
            "generated_by": "python -m app.data.recipe_tags",
            "rules": "backend/app/data/recipe_tags.py",
            "key": "release external_id (RCP2_...) or curated slug",
            "note": "estimated says how each field was decided (rule or llm) and in which batch; null is untagged.",
            "llm_usage": result["usage"],
        },
        "recipes",
        {dish.key: recipe_entry(tags, previous.get(dish.key)) for dish, tags in tagged},
    )
    ingredients = ingredient_entries()
    write_keyed(
        root / INGREDIENT_TAGS,
        {
            "version": INGREDIENT_VERSION,
            "generated_by": "python -m app.data.recipe_tags",
            "rules": "backend/app/data/recipe_tags.py",
            "key": "ingredient normalized_name",
            "note": "perishable is ADR-0068's short-lived class; every true value needs the owner's confirmation.",
        },
        "ingredients",
        ingredients,
    )
    sample = root / SAMPLE
    if sample.exists():
        print(f"{SAMPLE} is a frozen audit packet; left as it is. Generate a separate changed-case review.")
    else:
        sample.write_text(
            json.dumps(sample_packet(tagged, ingredients), indent=2, ensure_ascii=False) + "\n",
            encoding="utf-8",
            newline="\n",
        )
    (root / REPORT).write_text(report(tagged, ingredients, result["usage"]), encoding="utf-8", newline="\n")
    open_count = sum(1 for _, tags in tagged if any(value is None for value in tags.values.values()))
    print(f"Tagged {len(tagged)} recipes and {len(ingredients)} ingredients; {open_count} recipes keep a null field.")


if __name__ == "__main__":
    main()
