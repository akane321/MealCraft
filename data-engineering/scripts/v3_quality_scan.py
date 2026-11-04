# ruff: noqa: E501 - the detector regexes read best one per line.
"""Deterministic failure-pattern scan of a data release (default: v3). No LLM, no network, standard library only.

    python data-engineering/scripts/v3_quality_scan.py --out data-engineering/docs/v3-quality-scan-20261104

Each pattern is a plain regex rule over the steps, the ingredient lines and their grams (see PATTERNS for the rule
text). A hit says "this recipe matches the rule", not "this recipe is wrong": the trivial patterns (salt, pepper,
greasing fat, juice/zest at whole-fruit weight) and benign water patterns hit many recipes a human would call
correct. Writes three files into --out: report.md (per-pattern rule, count, share, origin split, examples, unions and
the caveats), hits.csv (one row per recipe and pattern, for picking work) and README.md (how to read and rerun).
Output is deterministic: sorted rows, a fixed shuffle seed for the examples, no timestamps.

Reads `release/v3/recipes.jsonl` and `ingredients.jsonl`, `release/v2.2/recipes.jsonl` (to tell v2.2 recipes from
added ones) and `enrichment/v3_selected_wave1.csv`. The planning-pool gates (price, completeness, meal role) need the
backend and are not computed here; `docs/planning-pool-report.json` has the pool totals only.
From the repository root; takes about ten seconds for 18,335 recipes.
"""

from __future__ import annotations

import argparse
import collections
import csv
import json
import random
import re
import sys
from pathlib import Path

REPOSITORY = Path(__file__).resolve().parents[2]
DATA = REPOSITORY / "data-engineering/data"
RELEASE = DATA / "release/v3"
BEFORE = DATA / "release/v2.2"
WAVE1 = DATA / "enrichment/v3_selected_wave1.csv"
# Recipes of the over-quota leg carry these enrichers in `enrichment.by` (the v3 build text names the leg; the
# prefixes are the scan's own way to find it).
OVERQUOTA_BY = ("claude/akane321", "claude/DuJiayu")
EXAMPLES = 5
EXAMPLE_SEED = 11


def I(p):  # noqa: E743
    return re.compile(p, re.I)


def snippet(text, m, w=70):
    a = max(0, m.start() - w)
    b = min(len(text), m.end() + w)
    return text[a:b].replace("\n", " ")


def qty(line):
    lo, hi = line["quantity_min"], line["quantity_max"]
    if lo is None:
        return None
    return (lo + hi) / 2 if hi is not None else lo


def fkey(line):
    return line["canonical_ingredient_id"] + ("#cooked" if "cooked" in (line.get("preparation") or []) else "")


def weights(line, forms):
    f = forms.get(fkey(line))
    return {u["unit"]: u["grams"] for u in f["unit_grams"]} if f else {}


def counted_as(line, unit, forms):
    """True when the line's grams are exactly qty x the standard weight of `unit` for the ingredient."""
    q = qty(line)
    w = weights(line, forms)
    return bool(q) and unit in w and abs(line["grams"] - round(q * w[unit], 1)) <= 0.06


# ---------- P1 pantry basics used in steps, not listed ----------
NOT_FAT = I(
    r"peanut butter|almond butter|apple butter|nut butter|cocoa butter|butterscotch|buttermilk|butternut|butter bean|butter lettuce|shea"
)
FAT_WORD = I(
    r"\b(oil|butter|margarine|shortening|lard|ghee|drippings|grease|cooking spray|spray|fat|bacon fat|schmaltz)\b"
)
WATER_LISTED = I(r"\bwater\b(?! chestnut| cress|cress)|ING_WATER\b|ING_MILK_OR_WATER|ING_ICE\b")
PEPPER_PRE = r"(?<!bell )(?<!red )(?<!green )(?<!chili )(?<!chile )(?<!chilli )(?<!hot )(?<!sweet )(?<!yellow )(?<!orange )(?<!jalapeno )(?<!cayenne )(?<!banana )(?<!poblano )(?<!roasted )(?<!pimiento )"
PEPPER_WORD = I(
    PEPPER_PRE
    + r"\bpepper\b(?!s\b|corns?\b)(?!\s+(?:strips?|rings?|slices?|halves|flakes|sauce|jack|steak|pot|cheese))|peppercorn"
)
PEPPER_EXPL = I(
    r"\bsalt\b[^.;]{0,12}\bpepper\b(?!s\b)|\bpepper\b(?:\s*,\s*|\s+and\s+)salt\b|\bpepper to taste|\b(?:black|white|ground|cracked|coarse|freshly ground|fresh ground|lemon|pinch of|dash of)\s+pepper\b|\b\d[\d/. ]*\s*(?:tsp|teaspoons?|pinch|dash)\.?\s+(?:of\s+)?pepper\b|\bseason\w*[^.;]{0,25}\bpepper\b(?!s\b)"
)
SALT_WORD = I(r"(?<!pork )(?<!cod )\bsalt\b(?! pork| cod| substitute|-free)")
SALT_LISTED = I(r"\bsalt\b(?! cod| pork)|ING_SALT|ING_SEASONED_SALT")
ICE_STEP = I(r"\bice\b(?![- ]?cream|[- ]?pop|[- ]?box|[- ]?cube tray|\s+tray)")
ICE_LISTED = I(r"\bice\b(?![- ]?cream)|ING_ICE\b")
SUGAR_LISTED = I(
    r"sugar(?! snap| cane)|ING_SUGAR(?!_SNAP|_CANE)|ING_POWDERED_SUGAR|confectioner|icing sugar|ING_HONEY|\bhoney\b|syrup|splenda|sweetener"
)
POW_LISTED = I(r"powdered sugar|confectioner|icing sugar|ING_POWDERED_SUGAR")

WATER_Q = I(
    r"\b(\d[\d/. ]*|a|one|two|three|four|another|more|additional|extra)\s*[- ]?(?:cups?|c\.|tbsp|tablespoons?|tsp|teaspoons?|quarts?|qts?|gallons?|pints?|ml|liters?|oz|ounces?)\s+(?:of\s+)?(?:cold |hot |warm |boiling |lukewarm |ice |tepid |additional |more |fresh |cool |salted )*water\b"
)
WATER_ADD = I(
    r"\b(?:add|adding|pour|stir in|mix in|whisk in|blend in|combine with|dissolve[^.]{0,40} in|cover[^.]{0,30} with|fill[^.]{0,30} with|thin with|moisten with|sprinkle with|dilute with)\s+(?:in\s+)?(?:the\s+|some\s+|enough\s+|more\s+|a little\s+|a bit of\s+|a few (?:tablespoons|drops) of\s+|\d[\d/. ]*\s*\w*\s+)?(?:cold |hot |warm |boiling |lukewarm |ice |fresh |cool )?water\b"
)
WATER_BOIL = I(
    r"\b(?:boiling|boiled|salted|simmering) water\b|\b(?:pot|saucepan|kettle|pan|large pot|skillet) of (?:boiling |salted |cold )?water\b|\bwater (?:to|come to|comes to) (?:a |the )?boil|\bbring[^.]{0,30}water\b|\bin water\b"
)
NONDISH_WATER = I(
    r"steam|bath|soak|double boiler|bain|reserv|inch(?:es)? of water|boil(?:ing)? water to|water to (?:a )?boil|pot of|blanch|cover(?:ed)? with|simmering water|ice water|ice-water"
)
WATER_STEP_EXCLUDE = I(
    r"water chestnut|watercress|rose water|orange blossom water|coconut water|lye water|water bath|waterproof|water-?packed|packed in water|water baths?"
)

GREASE = I(
    r"\b(?:grease|greased|greasing|oil|oiled|oiling|spray|sprayed|coat|coated|butter|buttered|buttering)\s+(?:the |an? |a lightly |lightly |your |each |two |both |all )?(?:\d+[- ]?(?:by|x)[- ]?\d+[- ]?(?:inch)?\s*)?(?:\w+[- ]){0,3}?(?:pan|pans|dish|dishes|skillet|baking sheet|sheet|griddle|grill|grate|grates|rack|molds?|tins?|cups|muffin|loaf|casserole|ramekins?|bowl|cookie sheets?|wok|pot|cake|skewers)\b|\bnon-?stick (?:cooking )?spray\b|\bcooking spray\b|\bgreased\b|(?<!drain )(?<!drain off )(?<!off )(?<!excess )(?<!the )(?<!remove )(?<!discard )(?<!and discard )(?<!pour off )\bgrease\b(?! from| and drain|,? drain)|\bbrush(?:ed)?[^.]{0,40}\b(?:with|using)\s+(?:the |some |a little |a bit of |melted |olive |vegetable |cooking )*(?:oil|butter|margarine|fat)\b"
)
FRY = I(
    r"\b(?:fry|fried|frying|deep[- ]fry\w*|saut[eé]\w*|sear\w*|pan[- ]fr\w*|shallow[- ]fr\w*|stir[- ]fr\w*|brown\w*)[^.;]{0,30}\b(?:in|using|with)\s+(?:the |some |a little |a bit of |hot |\d[\d/. ]*\s*\w+\s+(?:of )?)*(?:oil|butter|margarine|fat|shortening|lard)\b|\bheat(?:ed)?\s+(?:the |some |\d[\d/. ]*\s*\w+\s+(?:of )?)?(?:oil|butter|margarine|fat|shortening|lard)\b|\bmelt(?:ed)?\s+(?:the |some |\d[\d/. ]*\s*\w+\s+(?:of )?)?(?:butter|margarine)\b|\bhot (?:oil|fat)\b|\bdeep[- ]fat\b|\b(?:add|in|with)\s+(?:the |some |\d[\d/. ]*\s*(?:tbsp|tablespoons?|tsp|teaspoons?|cups?)\s+(?:of )?)(?:oil|butter|margarine)\b"
)
DUST = I(
    r"\b(?:dust|dusted|dusting|sprinkle|sprinkled|sprinkling|roll|rolled|coat|coated|top|topped|garnish|garnished)\b[^.;]{0,50}\b(?P<s>powdered sugar|confectioners'? sugar|confectioner's sugar|icing sugar|granulated sugar|brown sugar|sugar)\b"
)


def listed_blob(r):
    return " ".join(
        i["original_text"] + " " + i["canonical_ingredient_id"] + " " + i["canonical_name"] for i in r["ingredients"]
    )


# ---------- P2 serve with / over a carrier not listed ----------
CARRIER = {
    "rice": (r"rice", I(r"\brice\b|ING_\w*RICE|ING_RISOTTO|pilaf")),
    "pasta": (
        r"pasta|noodles?|spaghetti|macaroni|linguine|fettuccine|penne|orzo|vermicelli|egg noodles",
        I(
            r"pasta|noodle|spaghetti|macaroni|linguine|fettuccine|penne|orzo|vermicelli|ramen|lasagn|ravioli|tortellini|udon|soba|gnocchi|ING_PASTA"
        ),
    ),
    "pita": (r"pitas?|pita bread", I(r"\bpita")),
    "tortillas": (
        r"tortillas?|taco shells?|flatbread|naan|wraps?",
        I(r"tortilla|taco shell|flatbread|naan|wrap|roti|chapati|chapatti|paratha|lavash|ING_TORTILLA"),
    ),
    "bread": (
        r"(?:crusty |french |italian |garlic |toasted |warm |fresh |buttered )*(?:bread|toast|baguette|buns?|rolls?|biscuits?|crackers?|croutons?)",
        I(
            r"bread|toast|baguette|\bbuns?\b|\brolls?\b|biscuit|cracker|crouton|bagel|muffin|cornbread|pita|naan|tortilla|ING_BREAD"
        ),
    ),
    "couscous/polenta": (
        r"couscous|polenta|grits|quinoa|bulgur",
        I(r"couscous|polenta|grits|quinoa|bulgur|cornmeal|barley"),
    ),
    "potatoes": (r"(?:mashed |boiled |baked )?potatoes", I(r"potato|ING_POTATO|ING_MASHED")),
}
SERVE = I(
    r"\bserv(?:e|ed|es|ing)\b(?P<mid>[^.;!?]{0,70}?)\b(?:over|on|with|alongside|beside|atop|on top of|accompanied by|and|in|between|into|along with)\s+(?:(?:a|an|the|some|your|each|warm|hot|cold|cooked|steamed|fresh|favorite|crusty|toasted|buttered|white|brown|long[- ]grain|boiled|mashed|fluffy|plain|hot cooked|prepared|freshly cooked|freshly|baked|pre-cooked|leftover|bowl of|bed of|\d+|cup|cups|slices?|of|warmed)\s+)*(?P<c>"
    + "|".join("(?:" + v[0] + ")" for v in CARRIER.values())
    + r")\b"
)
OPTION = I(
    r"\bif (?:desired|you like|wanted|you wish|preferred|you want)|\boptional|\bor (?:other|any)\b|\bwith or without|\bcan be served|\bmay be served|\bcould be served|\bgood (?:over|with|on)|\bdelicious (?:over|with)|\bserve it as|\bleftover"
)

# ---------- P3 sub-recipe / sauce not listed ----------
SUBRX = I(
    r"\b(?:serve|served|top|topped|drizzle|drizzled|spoon|spooned|smother|smothered|accompan\w+)\b[^.;]{0,45}?\b(?:with|over|in|into|on|and)\s+(?:the |your |a |an |some |any |remaining |reserved |prepared |warm |hot |cold |favorite |favourite |homemade |bottled |store-bought |purchased |leftover )*(?P<ph>(?:[a-z][a-z'-]+ ){0,2}?(?:sauce|salsa|gravy|dressing|chutney|relish|pesto|vinaigrette|marinara|guacamole|aioli|glaze|frosting))\b"
)
SUB_EXPLICIT = I(
    r"\b(?:recipe for|see recipe|your favorite|prepared according|according to (?:the )?(?:recipe|package)|from (?:the )?(?:recipe|above)|recipe (?:below|above|follows))\b[^.;]{0,50}\b(?P<ph>(?:[a-z][a-z'-]+ ){0,2}(?:sauce|salsa|gravy|dressing|chutney|relish|pesto|vinaigrette|marinara|guacamole|aioli|glaze|frosting|filling|dough|crust|batter|sub-?recipe))\b"
)
GENERIC_TOK = set(
    "their plenty thickened additional little dab bit juices own enough rest accumulated pan the your a an some any remaining reserved prepared warm hot cold favorite favourite homemade bottled store bought purchased leftover sauce salsa gravy dressing chutney relish pesto vinaigrette marinara guacamole aioli glaze frosting filling dough crust batter stock broth this that it its of and with extra more final first second pan cooking dipping serving main meat pasta".split()
)

# ---------- P4 size modifiers ----------
FRUITS = r"(?:lemon|lime|orange|grapefruit|tangerine|apple|tomato|cucumber|onion|pineapple|banana|mango|peach|pear)s?"
MINI = I(
    r"\b(?:cherry|grape|baby|mini|miniature|teardrop|pearl)\s+(?:\w+\s+)?(?:tomato|tomatoes|carrots?|potato|potatoes|eggplants?|onions?|squash|zucchini|peppers?|cucumbers?|beets?|beetroots?|artichokes?|pattypan|bananas?|turnips?|radish(?:es)?|leeks?|corn|new potatoes)\b"
)
SLICES = I(
    r"^\W*(?:[\d/ .\-–]+|one|two|three|four|five|six|a|an)?\s*(?:\w+\s+){0,2}?(?:"
    + FRUITS
    + r")\s+(?:slices?|wedges?|rounds?|twists?|halves)\b|\b(?:slices?|wedges?|rounds?|twists?) of (?:a |an |the )?(?:"
    + FRUITS
    + r")\b"
)
JUICEZEST = I(
    r"\b(?:juice of|juiced|zest of|zested|grated zest|grated rind|rind of|juice only|for (?:the )?juice|juice and zest|zest and juice|juice from|zest from|squeezed|grated peel|peel of)\b|\b(?:zest|rind|peel)\b(?!\s*(?:strips?))"
)
CITRUS_IDS = {
    "ING_LEMON",
    "ING_LIME",
    "ING_ORANGE",
    "ING_GRAPEFRUIT",
    "ING_TANGERINE",
    "ING_MANDARIN",
    "ING_CLEMENTINE",
}
CHILI_SMALL = I(
    r"\b(?:thai|bird'?s?[- ]?eye|birdeye|serrano|tiny|small|dried|piquin|pequin|habanero|scotch bonnet|cayenne)\b[^,;]{0,25}\b(?:chil(?:i|e|li)(?:e?s)?|chilli(?:es)?|peppers?)\b|\b(?:chil(?:i|e|li)(?:e?s)?|peppers?)\b[^,;]{0,20}\b(?:thai|bird'?s?[- ]?eye|birdeye|serrano)\b"
)
SIZE = I(r"\b(small|large|extra[- ]large|jumbo|big|huge)\b")
PAREN_W = re.compile(
    r"\((?:about |approximately |approx\.? |approx |~|roughly )?(\d+(?:\.\d+)?)\s*(?:-\s*\d+(?:\.\d+)?\s*)?(lbs?\.?|pounds?|oz\.?|ounces?|g\b|grams?|kg)\b",
    re.I,
)
PW_G = {
    "lb": 453.6,
    "lbs": 453.6,
    "pound": 453.6,
    "pounds": 453.6,
    "oz": 28.35,
    "ounce": 28.35,
    "ounces": 28.35,
    "g": 1,
    "gram": 1,
    "grams": 1,
    "kg": 1000,
}

# ---------- P5 cooked / liquid mapped to dry / concentrate ----------
COOKED_AFTER = I(
    r"\b(?:rice|pasta|spaghetti|macaroni|noodles?|beans?|lentils?|quinoa|couscous|orzo|barley|chickpeas?|farro|bulgur)\b[^,;]{0,12},?\s*(?:cooked|steamed|boiled|prepared)\b"
)
COOKED_NEG = I(
    r"uncooked|not cooked|raw|dry|when cooked|makes|yields?|to make|after cooking|before cooking|package|pkg|box|instructions|directions|cooked weight|will cook|until cooked|to be cooked"
)
COOKED_ITEM = I(
    r"\b(?:cooked|steamed|boiled|leftover|left-over|day-old|prepared|precooked|pre-cooked|hot cooked|cold cooked)\b[^,;]{0,25}\b(?:rice|pasta|spaghetti|macaroni|noodles?|beans?|lentils?|quinoa|couscous|orzo|barley|chickpeas?|farro|bulgur|penne|rotini|fettuccine|linguine|vermicelli)\b"
)
DRYABLE = {
    "ING_RICE",
    "ING_BROWN_RICE",
    "ING_WILD_RICE",
    "ING_PASTA",
    "ING_MACARONI",
    "ING_EGG_NOODLES",
    "ING_RICE_NOODLES",
    "ING_RAMEN",
    "ING_ORZO",
    "ING_COUSCOUS",
    "ING_QUINOA",
    "ING_LENTIL",
    "ING_BLACK_BEANS",
    "ING_KIDNEY_BEANS",
    "ING_PINTO_BEANS",
    "ING_CHICKPEA",
    "ING_CANNELLINI",
    "ING_LIMA_BEANS",
    "ING_BARLEY",
    "ING_SOBA_NOODLES",
    "ING_LONG_GRAIN_WILD_RICE_MIX",
    "ING_BLACK_EYED_PEAS",
    "ING_MUNG_BEAN",
}
BOUILLON_SOLID = I(
    r"cubes?|granules?|powder|paste|crystals?|concentrate|base|envelopes?|packets?|teaspoons?|tsp|tablespoons?|tbsp|dissolved|crumbled|instant"
)
BOUILLON_LIQUID = I(
    r"\b(?:cups?|c\.|ml|liters?|quarts?|pints?|cans?|fl\.? ?oz)\b|\bliquid\b|\bbroth\b|\bstock\b|\bconsomm"
)

# ---------- P7 token helpers ----------
STOP = set(
    """cup cups tbsp tablespoon tablespoons tsp teaspoon teaspoons oz ounce ounces lb lbs pound pounds g gram grams kg ml l can cans package packages pkg jar box bottle container pinch dash large small medium fresh frozen chopped diced sliced minced grated shredded crushed ground peeled cut finely coarsely thinly into inch inches pieces piece cubed cooked uncooked raw dried canned drained rinsed softened melted divided optional taste for garnish about or and of the a an with without plus more extra whole half halved lightly packed heaping level boneless skinless lean free low sodium reduced unsalted salted sweetened unsweetened plain all purpose white black red green yellow brown ripe firm thin thick pure good quality fine your favorite style kind type mix mixed cold hot warm room temperature bunch handful sprig sprigs stalk stalks clove cloves head heads slice slices strip strips stick sticks sheet sheets ring rings round rounds wedge wedges drop drops none stems stem leaves leaf trimmed seeded cored pitted quartered chunks chunk dice cubes cube thawed beaten separated bite size sized tbs pt qt gal such as like brand one two three four five six seven eight nine ten""".split()
)

SYN = {
    "yoghurt": "yogurt",
    "chilli": "chili",
    "chile": "chili",
    "chilie": "chili",
    "courgette": "zucchini",
    "aubergine": "eggplant",
    "scallion": "onion",
    "coriander": "cilantro",
    "capsicum": "pepper",
    "garbanzo": "chickpea",
    "prawn": "shrimp",
    "mince": "ground",
    "hamburg": "ground",
}


def stem(w):
    w = SYN.get(w.lower(), w.lower())
    if len(w) > 4 and w.endswith("ies"):
        return w[:-3] + "y"
    if len(w) > 4 and re.search(r"(ss|x|ch|sh|o)es$", w):
        return w[:-2]
    if len(w) > 3 and w.endswith("s") and not w.endswith("ss"):
        return w[:-1]
    return {"chilly": "chili", "chily": "chili", "chilli": "chili"}.get(w, w)


def toks(s):
    s = re.sub(r"\([^)]*\)", " ", s.lower())
    return {stem(w) for w in re.findall(r"[a-z]+", s) if w not in STOP and len(w) >= 3}


GENERIC_STEP = I(
    r"\bingredients?\b|\bcomponents\b|\ball together\b|\bcombine all\b|\bmix all\b|\bevery ?thing\b|\bthe rest\b|\bremaining\b|\ball of the above\b|\bthe above\b|\b(?:mix|combine|blend|stir|whisk|toss)(?: well| lightly| gently)?(?: all)? together\b|\bnext \d\b|\bfirst \d\b"
)
HYPER = {
    "meat": set(
        "meat beef pork lamb veal steak sirloin hamburger chuck roast patty patties brisket rib ribs tenderloin loin chop mince sausage chorizo frank frankfurter hotdog kielbasa bratwurst salami pepperoni link andouille ham bacon chicken turkey poultry hen duck bird breast thigh drumstick wing fish fillet salmon tuna cod tilapia seafood shrimp crab lobster scallop tofu protein cutlet meatball ground".split()
    ),
    "noodle": set(
        "noodle pasta spaghetti macaroni linguine fettuccine penne vermicelli orzo rotini lasagna ravioli shell rigatoni angel ziti tortellini mein".split()
    ),
    "cream": set("cream half milk dairy".split()),
    "veg": set("vegetable veggie veggies veggy".split()),
    "fruit": set("fruit".split()),
    "herb": set("herb herbs spice spices seasoning seasonings season".split()),
    "egg": set("egg eggs yolk yolks white whites".split()),
    "cheese": set("cheese parmesan cheddar mozzarella".split()),
    "nut": set("nut walnut pecan almond cashew peanut pistachio hazelnut macadamia".split()),
    "berry": set("berry blueberry strawberry raspberry blackberry cranberry fruit".split()),
}
FG_HYPER = {
    "protein": "meat",
    "vegetable": "veg",
    "fruit": "fruit",
    "herb": "herb",
    "seasoning": "herb",
    "dairy": "cream",
}
FAT_STEP = I(r"oil|butter|margarine|fat|grease|spray|shortening|lard|saut|fry|fried|frying|brown|sear|ghee|drippings")
SEAS_STEP = I(r"season|salt|pepper|taste|spice|seasoning|herb|sprinkle|flavor")
SWEET_STEP = I(r"sugar|sweeten|sweet|syrup|honey")
WATER_STEP = I(r"water|liquid|boil|simmer")
SKIP_P7 = {"ING_SALT", "ING_BLACK_PEPPER", "ING_SALT_AND_PEPPER", "ING_WATER", "ING_ICE"}

OVEN_VERB = I(
    r"\b(?:bake|baked|bakes|roast|roasted|roasting|broil|broiled|broiling)\b|\boven\b(?!-?proof| mitt|-safe| safe)"
)
OVEN_SIGNAL = I(r"\boven\b(?!\s*-?\s*(?:proof|safe))|\bbake\b")
NONOVEN = I(
    r"griddle|skillet|dry pan|waffle|\biron\b|lefse|grill|crock|slow cooker|microwave|stove|stovetop|pan-roast|dry roast|baked beans|baked potato|baking (?:powder|soda|mix)|great on baked|steam|oven chicken|dutch[- ]oven|from (?:the |your )?oven|out of (?:the |your )?oven|power|nu-?wave|on warm|or stir|oven set on warm|keep (?:them |it )?warm|warm in|low oven|toast|bread machine|air fryer|pressure cooker|instant pot|rice cooker"
)
OVEN_NOISE = I(
    r"dutch oven|microwave oven|toaster oven|roast beef|pot roast|roast pork|roast chicken (?:breast|meat)|roasted (?:red pepper|peppers|garlic|peanuts|nuts|almonds|sesame|chicken)|oven-?proof|oven mitt"
)
TEMP = I(
    r"\b\d{2,3}\s*(?:°|º|\*|o\s?[FfCc]\b|['’]\s?[FfCc]\b|degrees?|deg\b|[FfCc]\b)|\b(?:at|to|oven to|temperature (?:of|to)|bake|baked|preheat\w*|roast\w*)\s+(?:[a-z]+\s+){0,4}?(?:to |at )?\d{3}\b(?!\s*(?:g\b|grams|ml\b|oz\b|lb|minutes|mins?\b|cals?|calories|-?inch|x\b))|gas mark|\b(?:moderate|slow|hot|very hot|quick|medium|moderately hot|low|high|brisk)\s+oven|\b\d{3}\s*-\s*\d{3}\b|\bbroil\w*\b|\bmicrowave"
)
TIME = I(
    r"\b(?:\d+|one|two|three|four|five|six|half|an|a)(?:\s*(?:-|to|–|or)\s*(?:\d+|one|two|three|four|five|six))?\s*(?:minutes?|mins?\.?|hours?|hrs?\.?|h\b)|\bovernight\b|\bhalf an hour\b|\ban hour\b"
)
ELSEWHERE = I(
    r"rest of the recipe|full recipe|for (?:the )?(?:recipe|directions|instructions)\b|see (?:the )?(?:original|recipe)|click|\bvisit\b|www\.|https?:|\.com\b"
)
COOK_VERB = I(
    r"\b(?:add|mix|combine|cook|bake|stir|heat|blend|place|put|pour|bring|boil|simmer|fry|saut\w+|whisk|toss|serve|spread|roll|cut|chop|slice|season|grill|broil|steam|beat|fold|knead|marinate|marinade|soak|drain|preheat|process|puree|shake|chill|refrigerate|cover|top|layer|arrange|brown|toast|mash|stuff|dip|coat|dissolve|melt|sprinkle|garnish|dice|mince|peel|wash|rinse|spoon|drizzle|squeeze|crush|grind|rub|brush|stack|fill|remove|reduce|let|set|freeze|thaw|warm|microwave|bring|prepare|make|use|dredge|sear|roast|scramble|poach|blanch|whip|cream|sift|stew|braise|ferment|pickle|dry)\b"
)
DANGLE = I(r"(?:\b(?:and|or|the|a|an|to|with|until|in|of|for|then|add|on|into|about|at|is|are)|,|\.\.\.|…|-|\()\s*$")

THRESH = {
    "main": 1200,
    "side": 800,
    "soup": 800,
    "salad": 900,
    "breakfast": 1000,
    "dessert": 900,
    "baked_good": 900,
    "snack_appetizer": 700,
    "sauce_condiment": 400,
    "drink": 500,
}


# pattern id -> rule text. Order is the report's order. HP = the high-precision list (the union the report headlines);
# CORE = HP without the trivial or half-benign patterns.
PATTERNS = {
    "P1a_water_quantified": 'Steps add a measured amount of water ("2 cups water"); no ingredient line is water, ice or milk-or-water. Sentences about steaming, baths, soaking, blanching, reserved liquid or covering with water are skipped.',
    "P1a3_water_added_no_amount": "Steps say add/pour/stir in/cover with water with no amount; no water line, and not P1a.",
    "P1a2_water_cooking_medium": "Only cooking-medium water (boiling or salted water, a pot of water, bring to a boil, in water); no water line. Benign.",
    "P1b_salt": "Steps mention salt (not salt pork, salt cod, salt substitute); no salt line.",
    "P1c_pepper": "Steps season with pepper (salt and pepper, black/white/ground pepper, pepper to taste, a tsp of pepper); no pepper line. Chili, bell and red pepper phrases are skipped.",
    "P1d_fat_greasing": "Steps grease, oil, butter or spray a pan, dish, sheet, rack or mold, use cooking spray, or brush with oil/butter; no fat or oil line (peanut butter, buttermilk etc. do not count as fat).",
    "P1e_fat_frying_or_adding": "Steps fry, saute or brown in, heat or melt oil, butter, margarine or fat; no fat line; not P1d.",
    "P1f_ice_in_drink_or_dish": "Steps use ice (not ice cream, ice pop, ice cube tray) outside a bath or cooling context; no ice line.",
    "P1f2_ice_bath_or_cooling": "Same as P1f but the nearby words say bath, plunge, shock, cool or chill. Benign.",
    "P1g_sugar_dusting": "Steps dust, sprinkle, roll, coat, top or garnish with (powdered, granulated or brown) sugar; no matching sugar or sweetener line.",
    "P2_serve_carrier_not_listed": "Steps serve over/with/on rice, pasta, pita, tortillas, bread, couscous/polenta or potatoes; no such carrier line. Skipped when the sentence marks it as optional or a suggestion (if desired, optional, can be served, good over, leftover).",
    "P3_named_subrecipe_not_listed": "Steps serve/top/drizzle with a named sauce, salsa, gravy, dressing, chutney, pesto, glaze or frosting (or refer to a recipe for one) whose name words are in no ingredient line, mentioned once, not made in the steps.",
    "P4a_mini_item_whole_weight": "Cherry/baby/mini vegetable or fruit line whose grams equal quantity x the standard whole-piece weight.",
    "P4b_fruit_slices_wedges_whole_weight": "Fruit slices, wedges, rounds, twists or halves line whose grams equal quantity x the standard whole-fruit weight.",
    "P4c_juice_zest_whole_fruit_weight": "Lemon/lime/orange/grapefruit/tangerine line that says juice, zest or rind but whose grams equal quantity x the whole-fruit weight.",
    "P4d_small_large_ignored_LOW": "Line says small/large/jumbo etc. but its grams equal quantity x the standard piece weight. Low impact; informational.",
    "P4e_small_chili_standard_weight": "Thai, bird's-eye, serrano, small or dried chili on ING_CHILI_PEPPER/ING_GREEN_CHILI at the standard piece weight (not a sauce, paste, powder, flakes or can).",
    "P4f_parenthetical_weight_ignored": 'Line text has a package weight in parentheses ("(14 oz)") and the grams are more than 20% off both that weight and quantity x that weight; unit is piece, can, package, jar, box, bottle, bag, head, bunch or none, and basis is not stated_package.',
    "P5a_cooked_item_dry_form": "Line says cooked/steamed/boiled/leftover rice, pasta, beans, grains etc. but maps to the dry form, whose kcal/100 g is at least 1.5x the cooked form's.",
    "P5a2_cooked_after_noun_ambiguous": 'Same as P5a with the wording "rice, cooked" (could be the amount after cooking). Ambiguous.',
    "P5b_liquid_bouillon_as_cube": "ING_BOUILLON line described as a liquid (cups, broth, stock) with no cube/powder/teaspoon wording, or over 40 g without such wording.",
    "P6_energy_outlier": "kcal per serving above the course threshold (soft; THRESH).",
    "P6h_energy_outlier_hard_1.5x": "kcal per serving above 1.5x the course threshold.",
    "P7_ingredient_never_in_steps": 'A non-optional line of 3 g or more (not salt, pepper, water, ice) shares no word with the steps, after exemptions for generic wording ("all ingredients"), hypernyms (meat, vegetables), seasoning, fat and liquid words. Not checked when the steps are under 80 characters or use generic wording (ingredients, together, the rest, remaining).',
    "P7b_two_or_more_unused": "P7 with two or more such lines.",
    "P7c_major_ingredient_unused_50g": "P7 where an unused line weighs 50 g or more.",
    "P8a_oven_without_temperature": "A sentence says oven or bake (not a Dutch oven, microwave, grill, slow cooker etc.) and no step has an oven temperature.",
    "P8b_fewer_than_2_steps": "Fewer than two instruction steps.",
    "P8b2_single_short_step_lt200ch": "One step, shorter than 200 characters.",
    "P8c_oven_without_any_time": "Same oven/bake sentence as P8a and no step has a time.",
    "P8d_truncated_steps": 'A step ends with "...", or the last step ends with a dangling word (and, or, the, a, to, with, until, in, of...), a comma, a dash or an open bracket.',
    "P8e_steps_point_elsewhere": "Steps send the reader elsewhere (click, visit, www, http, .com, rest of the recipe, see the original). MyPlate boilerplate is skipped.",
    "P8f_no_cooking_verb_in_steps": "No cooking verb (add, mix, cook, bake...) anywhere in the steps.",
}
HP = [
    "P1a_water_quantified",
    "P1b_salt",
    "P1c_pepper",
    "P1d_fat_greasing",
    "P1e_fat_frying_or_adding",
    "P2_serve_carrier_not_listed",
    "P3_named_subrecipe_not_listed",
    "P4a_mini_item_whole_weight",
    "P4b_fruit_slices_wedges_whole_weight",
    "P4c_juice_zest_whole_fruit_weight",
    "P4e_small_chili_standard_weight",
    "P4f_parenthetical_weight_ignored",
    "P5a_cooked_item_dry_form",
    "P5b_liquid_bouillon_as_cube",
    "P6h_energy_outlier_hard_1.5x",
    "P7b_two_or_more_unused",
    "P8a_oven_without_temperature",
    "P8c_oven_without_any_time",
    "P8e_steps_point_elsewhere",
    "P8f_no_cooking_verb_in_steps",
]
TRIVIAL = (
    "P1b_salt",
    "P1c_pepper",
    "P1d_fat_greasing",
    "P4c_juice_zest_whole_fruit_weight",
    "P8c_oven_without_any_time",
)
CORE = [p for p in HP if p not in TRIVIAL]
FAMILIES = [
    ("any high-precision pattern (HP)", HP),
    ("core (HP without salt, pepper, greasing fat, juice/zest, oven-no-time)", CORE),
    ("completeness (P1, P2, P3 in HP)", [p for p in HP if p.startswith(("P1", "P2", "P3"))]),
    ("portion and nutrition (P4, P5, P6 in HP)", [p for p in HP if p.startswith(("P4", "P5", "P6"))]),
    ("steps (P7b, P8 in HP)", [p for p in HP if p.startswith(("P7", "P8"))]),
]
GROUPS = {"v2.2": "v2.2", "overquota": "over-quota", "wave1": "new", "wave2": "new"}  # origin -> report column
COLUMNS = ["v2.2", "over-quota", "new"]


def scan_recipe(r, forms, fg, hit):
    rid = r["recipe_id"]
    steps = r["steps"]
    stext = " ".join(steps)
    lines = r["ingredients"]
    blob = listed_blob(r)
    blob_nf = NOT_FAT.sub(" ", blob)
    # ---- P1
    ws = WATER_STEP_EXCLUDE.sub(" ", stext)
    if not WATER_LISTED.search(blob):
        m = None
        for sent in re.split(r"(?<=[.;!?])\s+", ws):
            if NONDISH_WATER.search(sent):
                continue
            m = WATER_Q.search(sent)
            if m:
                hit("P1a_water_quantified", rid, snippet(sent, m, 90))
                break
        if m is None:
            m = WATER_ADD.search(ws)
            if m:
                hit("P1a3_water_added_no_amount", rid, snippet(ws, m))
            else:
                m = WATER_BOIL.search(ws)
                if m:
                    hit("P1a2_water_cooking_medium", rid, snippet(ws, m))
    if not SALT_LISTED.search(blob):
        m = SALT_WORD.search(stext)
        if m:
            hit("P1b_salt", rid, snippet(stext, m))
    if not (
        PEPPER_WORD.search(blob)
        or re.search(r"ING_(BLACK|WHITE)_PEPPER|ING_SALT_AND_PEPPER|ING_LEMON_PEPPER|ING_PEPPERCORN", blob)
    ):
        for m in PEPPER_EXPL.finditer(stext):
            if re.search(
                r"(?:red|chili|chile|hot|bell|green|cayenne|sweet|chilli)\s+pepper|pepper\s+(?:sauce|flakes|jack)",
                m.group(0) + stext[m.end() : m.end() + 8],
                re.I,
            ):
                continue
            hit("P1c_pepper", rid, snippet(stext, m))
            break
    if not FAT_WORD.search(blob_nf):
        m = GREASE.search(stext)
        if m:
            hit("P1d_fat_greasing", rid, snippet(stext, m))
        else:
            m = FRY.search(stext)
            if m:
                hit("P1e_fat_frying_or_adding", rid, snippet(stext, m))
    if not ICE_LISTED.search(blob):
        m = ICE_STEP.search(stext)
        if m:
            sn = snippet(stext, m, 70)
            hit(
                "P1f2_ice_bath_or_cooling"
                if re.search(r"bath|plunge|immers|stop (?:the )?cooking|shock|ice water|ice-water|cool|chill", sn, re.I)
                else "P1f_ice_in_drink_or_dish",
                rid,
                sn,
            )
    m = DUST.search(stext)
    if m:
        s = m.group("s").lower()
        if (re.search(r"powdered|confectioner|icing", s) and not POW_LISTED.search(blob)) or (
            not re.search(r"powdered|confectioner|icing", s) and not SUGAR_LISTED.search(blob)
        ):
            hit("P1g_sugar_dusting", rid, snippet(stext, m))
    # ---- P2
    for sm in SERVE.finditer(stext):
        if OPTION.search(sm.group(0)) or OPTION.search(stext[sm.end() : sm.end() + 50]):
            continue
        c = sm.group("c").lower()
        key = None
        for k, (pat, _listed) in CARRIER.items():
            if re.fullmatch(pat, c):
                key = k
                break
        if key is None:
            continue
        if not CARRIER[key][1].search(blob):
            hit("P2_serve_carrier_not_listed", rid, f"[{key}] " + snippet(stext, sm, 50))
            break
    # ---- P3
    title_blob = blob.lower()
    title_stems = {stem(t) for t in re.findall(r"[a-z]+", title_blob)}
    low = stext.lower()
    for sm in list(SUBRX.finditer(stext)) + list(SUB_EXPLICIT.finditer(stext)):
        ph = sm.group("ph").lower()
        words = re.findall(r"[a-z']+", ph)
        spec = {stem(w) for w in words if w not in GENERIC_TOK}
        if not spec:
            continue  # only "the sauce": no named sub-recipe
        if spec & title_stems:
            continue  # an ingredient line carries the name
        if len(re.findall(re.escape(ph), low)) > 1:
            continue  # mentioned more than once in the steps: made there
        if re.search(
            r"\b(?:make|prepare|combine|whisk|mix|stir together|blend|cook)\b[^.]{0,60}\b"
            + re.escape(words[-1])
            + r"\b",
            low,
        ):
            continue
        hit("P3_named_subrecipe_not_listed", rid, snippet(stext, sm, 40))
        break
    # ---- P4
    for ln in lines:
        t = ln["original_text"]
        q = qty(ln)
        if ln["unit"] in ("piece", None) and q:
            if MINI.search(t) and counted_as(ln, "piece", forms):
                hit(
                    "P4a_mini_item_whole_weight",
                    rid,
                    f"'{t}' -> {ln['grams']} g = {q:g} x std piece {weights(ln, forms)['piece']} g ({ln['canonical_ingredient_id']})",
                )
            if SLICES.search(t) and counted_as(ln, "piece", forms):
                hit(
                    "P4b_fruit_slices_wedges_whole_weight",
                    rid,
                    f"'{t}' -> {ln['grams']} g = {q:g} x std piece {weights(ln, forms)['piece']} g",
                )
            if ln["canonical_ingredient_id"] in CITRUS_IDS and JUICEZEST.search(t) and counted_as(ln, "piece", forms):
                hit(
                    "P4c_juice_zest_whole_fruit_weight",
                    rid,
                    f"'{t}' -> {ln['grams']} g = {q:g} x whole {weights(ln, forms)['piece']} g",
                )
            if (
                CHILI_SMALL.search(t)
                and ln["canonical_ingredient_id"] in {"ING_CHILI_PEPPER", "ING_GREEN_CHILI"}
                and "piece" in weights(ln, forms)
                and counted_as(ln, "piece", forms)
                and not re.search(r"sauce|paste|powder|flakes|oil|pickle|jar|can", t, re.I)
            ):
                hit(
                    "P4e_small_chili_standard_weight",
                    rid,
                    f"'{t}' -> {ln['grams']} g = {q:g} x std piece {weights(ln, forms)['piece']} g ({ln['canonical_ingredient_id']})",
                )
            if SIZE.search(t) and counted_as(ln, "piece", forms) and not MINI.search(t):
                hit(
                    "P4d_small_large_ignored_LOW",
                    rid,
                    f"'{t}' -> {ln['grams']} g = std piece {weights(ln, forms)['piece']} g",
                )
        pm = PAREN_W.search(t)
        if (
            pm
            and q
            and ln["unit"] in ("piece", "can", "package", "jar", "box", "bottle", "bag", "head", "bunch", None)
            and not re.search(
                r"drained|rinsed|net wt|\bor\b|\bbone|skin|\bdiscard", t[pm.end() : pm.end() + 14] + " " + t, re.I
            )
            and not re.search(r"\d\s*(?:lbs?|pounds?)\.?\s*\d|solid cream", t, re.I)
            and ln["grams_basis"] != "stated_package"
            and "CHICKEN" not in ln["canonical_ingredient_id"]
        ):
            mg = float(pm.group(1)) * PW_G[pm.group(2).lower().rstrip(".")]
            if mg > 20 and abs(ln["grams"] - mg) / mg > 0.2 and abs(ln["grams"] - q * mg) / (q * mg) > 0.2:
                hit(
                    "P4f_parenthetical_weight_ignored",
                    rid,
                    f"'{t}' -> {ln['grams']} g, text says {mg:.0f} g (x{q:g}) basis={ln['grams_basis']}",
                )
    # ---- P5
    for ln in lines:
        t = ln["original_text"]
        if (
            ln["canonical_ingredient_id"] in DRYABLE
            and "cooked" not in (ln.get("preparation") or [])
            and (ln["canonical_ingredient_id"] + "#cooked") in forms
            and not COOKED_NEG.search(t)
            and (COOKED_ITEM.search(t) or COOKED_AFTER.search(t))
            and forms[ln["canonical_ingredient_id"]]["nutrition_per_100g"]["energy_kcal"]
            >= 1.5 * forms[ln["canonical_ingredient_id"] + "#cooked"]["nutrition_per_100g"]["energy_kcal"]
        ):
            hit(
                "P5a_cooked_item_dry_form" if COOKED_ITEM.search(t) else "P5a2_cooked_after_noun_ambiguous",
                rid,
                f"'{t}' -> {ln['canonical_ingredient_id']} {ln['grams']} g, prep={ln.get('preparation')}, dry {forms[ln['canonical_ingredient_id']]['nutrition_per_100g']['energy_kcal']} vs cooked {forms[ln['canonical_ingredient_id'] + '#cooked']['nutrition_per_100g']['energy_kcal']} kcal/100g",
            )
        if (
            ln["canonical_ingredient_id"] == "ING_BOUILLON"
            and BOUILLON_LIQUID.search(t)
            and not BOUILLON_SOLID.search(t)
        ):
            hit("P5b_liquid_bouillon_as_cube", rid, f"'{t}' -> ING_BOUILLON {ln['grams']} g (260 kcal/100g dry cube)")
        elif ln["canonical_ingredient_id"] == "ING_BOUILLON" and ln["grams"] > 40 and not BOUILLON_SOLID.search(t):
            hit("P5b_liquid_bouillon_as_cube", rid, f"'{t}' -> ING_BOUILLON {ln['grams']} g (>40 g of dry bouillon)")
    # ---- P6
    kcal = r["nutrition"]["energy_kcal"]
    th = THRESH.get(r["course"])
    if th and kcal > th:
        hit(
            "P6_energy_outlier",
            rid,
            f"{r['course']} {kcal} kcal/serving > {th}; servings={r['servings']} ({r['servings_basis']})",
        )
        if kcal > 1.5 * th:
            hit(
                "P6h_energy_outlier_hard_1.5x",
                rid,
                f"{r['course']} {kcal} kcal/serving > 1.5x{th}; servings={r['servings']} ({r['servings_basis']})",
            )
    # ---- P7
    if not GENERIC_STEP.search(stext) and len(stext) >= 80:
        st = {stem(w) for w in re.findall(r"[a-z]+", low)}
        unused = []
        unused_g = []
        for ln in lines:
            if ln.get("optional") or ln["canonical_ingredient_id"] in SKIP_P7 or ln["grams"] < 3:
                continue
            tk = toks(ln["original_text"]) | toks(ln["canonical_name"])
            if not tk or tk & st:
                continue
            if any(len(s) >= 4 and t.endswith(s) for s in st for t in tk):
                continue
            if any(tk & g and st & g for g in HYPER.values()):
                continue
            fh = FG_HYPER.get(fg.get(ln["canonical_name"]))
            if fh and st & HYPER[fh]:
                continue
            if fg.get(ln["canonical_name"]) in ("grain", "leavening") and re.search(
                r"dough|batter|mixture|dry|bake|baked|mix", low
            ):
                continue
            if fg.get(ln["canonical_name"]) in (
                "condiment",
                "prepared",
                "beverage",
                "flavoring",
                "sweetener",
                "plant_milk",
            ) and re.search(r"sauce|liquid|marinade|dressing|juice|mixture|syrup|glaze|season|flavor|sweeten", low):
                continue
            if FAT_WORD.search(NOT_FAT.sub(" ", ln["original_text"] + " " + ln["canonical_name"])) and FAT_STEP.search(
                low
            ):
                continue
            if re.search(
                r"salt|pepper|spice|seasoning|herb|powder|cumin|paprika|oregano|basil|thyme|parsley|cinnamon|nutmeg|garlic|ginger",
                ln["original_text"] + ln["canonical_name"],
                re.I,
            ) and SEAS_STEP.search(low):
                continue
            if re.search(r"sugar|honey|syrup|sweetener|molasses", ln["canonical_name"], re.I) and SWEET_STEP.search(
                low
            ):
                continue
            if re.search(
                r"broth|stock|bouillon|juice|wine|vinegar|milk|cream|beer|liquor|rum|brandy",
                ln["canonical_name"] + ln["original_text"],
                re.I,
            ) and WATER_STEP.search(low):
                continue
            unused.append(ln["original_text"])
            unused_g.append((ln["original_text"], ln["grams"]))
        if unused:
            hit("P7_ingredient_never_in_steps", rid, f"{len(unused)} unused: " + " | ".join(unused[:3]))
            if len(unused) >= 2:
                hit("P7b_two_or_more_unused", rid, f"{len(unused)} unused: " + " | ".join(unused[:3]))
            if any(g >= 50 for _, g in unused_g):
                hit("P7c_major_ingredient_unused_50g", rid, f"{len(unused)} unused: " + " | ".join(unused[:3]))
    # ---- P8
    if len(steps) < 2:
        hit("P8b_fewer_than_2_steps", rid, f"{len(steps)} step(s): " + stext[:120])
        if len(stext) < 200:
            hit("P8b2_single_short_step_lt200ch", rid, f"{len(stext)} chars: " + stext[:150])
    ov = OVEN_NOISE.sub(" ", stext)
    osent = [s for s in re.split(r"(?<=[.;!?])\s+", ov) if OVEN_SIGNAL.search(s) and not NONOVEN.search(s)]
    if osent and not TEMP.search(stext) and not re.search(r"@\s*\d{3}", stext):
        hit("P8a_oven_without_temperature", rid, osent[0][:200])
    if osent and not TIME.search(stext):
        hit("P8c_oven_without_any_time", rid, osent[0][:200])
    last = steps[-1].strip() if steps else ""
    if any(s.strip().endswith(("...", "…")) for s in steps) or (steps and DANGLE.search(last)):
        hit("P8d_truncated_steps", rid, "last step: " + last[-100:])
    m = ELSEWHERE.search(stext)
    if m and not re.search(r"healthy plate|choosemyplate", stext, re.I):
        hit("P8e_steps_point_elsewhere", rid, snippet(stext, m, 60))
    if not COOK_VERB.search(stext):
        hit("P8f_no_cooking_verb_in_steps", rid, stext[:150])


def scan(recipes, ingredients):
    """hits[pattern][recipe_id] = evidence, over recipes that carry a `steps` list of texts."""
    forms = {k: v for r in ingredients for k, v in r["forms"].items()}
    fg = {r["canonical_name"]: r.get("food_group") for r in ingredients}
    hits = collections.defaultdict(dict)

    def hit(pattern, rid, evidence):
        hits[pattern].setdefault(rid, evidence[:300])

    for r in recipes:
        scan_recipe(r, forms, fg, hit)
    unknown = set(hits) - set(PATTERNS)
    if unknown:
        raise SystemExit(f"patterns without a rule text: {sorted(unknown)}")
    return hits


def read_jsonl(path):
    with path.open(encoding="utf-8") as handle:
        return [json.loads(line) for line in handle if line.strip()]


def load(release=RELEASE, before=BEFORE, wave1=WAVE1):
    """The release's recipes with `origin` (v2.2, overquota, wave1, wave2) and `steps`, and its ingredients."""
    old = {r["recipe_id"] for r in read_jsonl(before / "recipes.jsonl")}
    with wave1.open(encoding="utf-8", newline="") as handle:
        first = {row["candidate_id"] for row in csv.DictReader(handle)}
    recipes = read_jsonl(release / "recipes.jsonl")
    for r in recipes:
        by = (r.get("enrichment") or {}).get("by", "")
        if r["recipe_id"] in old:
            r["origin"] = "v2.2"
        elif by.startswith(OVERQUOTA_BY):
            r["origin"] = "overquota"
        elif r["source"].get("candidate_id") in first:
            r["origin"] = "wave1"
        else:
            r["origin"] = "wave2"
        r["steps"] = [s["text"] for s in r["instructions"]]
    version = json.loads((release / "release_manifest.json").read_text(encoding="utf-8"))["release_version"]
    return version, recipes, read_jsonl(release / "ingredients.jsonl")


def tidy(text):
    return " ".join(str(text).split())


def pct(n, d):
    return f"{100 * n / d:.1f}%" if d else "-"


CAVEATS = """\
- Counts are pattern matches, not defect rates. A recipe can match and still be correct, and a wrong recipe can match nothing.
- The trivial patterns P1b (salt), P1c (pepper), P1d (greasing fat) and P4c (juice or zest at whole-fruit weight) are not defects by themselves: the missing amount is tiny. Benign water (P1a2 cooking-medium water, P1f2 ice bath) is not a defect either. P8c (oven, no time) often has a doneness cue instead. That is why the core union leaves them out.
- Precision was only eyeballed on small samples by one reader when the rules were written; this tool does not measure it.
- In an earlier comparison against the 2026-10-25 manual check of release v2.2 (`data-engineering/docs/manual-check-20261025/`) about 30% of the recipes humans called correct were also hit, mostly by water, serve-with and greasing patterns. That comparison was made outside this tool and is not recomputed here.
- Hits are a worklist, not a verdict: read the evidence before changing a recipe.
- The planning-pool gates (price, completeness, meal role) need the backend and are not computed here, so there is no plannable column.
"""


def report(version, recipes, hits):
    by_id = {r["recipe_id"]: r for r in recipes}

    def group(rid):
        return GROUPS[by_id[rid]["origin"]]

    total = collections.Counter(GROUPS[r["origin"]] for r in recipes)
    n = len(recipes)
    out = [f"# Data release {version}: quality scan", ""]
    out.append(
        f"{n:,} recipes ({', '.join(f'{c} {total[c]:,}' for c in COLUMNS)}); {sum(len(v) for v in hits.values()):,} "
        f"pattern hits on {len(set().union(*hits.values())):,} recipes. "
        "`new` is wave 1 plus wave 2; `over-quota` is the built-but-over-quota v2.1 leg (see README)."
    )
    out += ["", "## Caveats", "", CAVEATS]
    out += [
        "## Unions",
        "",
        "| recipes hit by | all | share | v2.2 | over-quota | new |",
        "|---|---:|---:|---:|---:|---:|",
    ]
    unions = {}
    for name, pats in FAMILIES:
        ids = set().union(*(set(hits.get(p, {})) for p in pats))
        unions[name] = ids
        c = collections.Counter(group(i) for i in ids)
        cells = " | ".join(f"{c[g]:,} ({pct(c[g], total[g])})" for g in COLUMNS)
        out.append(f"| {name} | {len(ids):,} | {pct(len(ids), n)} | {cells} |")
    out += [
        "",
        "## Patterns",
        "",
        "HP = in the high-precision list; core = HP without the trivial patterns; info = not in HP.",
        "",
    ]
    out += [
        "| pattern | tier | all | share | v2.2 | over-quota | new | share v2.2 | share new |",
        "|---|---|---:|---:|---:|---:|---:|---:|---:|",
    ]
    for p in PATTERNS:
        ids = hits.get(p, {})
        c = collections.Counter(group(i) for i in ids)
        tier = "core" if p in CORE else "HP" if p in HP else "info"
        out.append(
            f"| {p} | {tier} | {len(ids):,} | {pct(len(ids), n)} | {c['v2.2']:,} | {c['over-quota']:,} | {c['new']:,} "
            f"| {pct(c['v2.2'], total['v2.2'])} | {pct(c['new'], total['new'])} |"
        )
    out += [
        "",
        "## Rules and examples",
        "",
        f"Five examples per pattern, picked with a fixed shuffle (seed {EXAMPLE_SEED}).",
        "",
    ]
    for p, rule in PATTERNS.items():
        ids = sorted(hits.get(p, {}))
        random.Random(EXAMPLE_SEED).shuffle(ids)
        out += [f"### {p} (n={len(ids):,})", "", f"Rule: {rule}", ""]
        for i in ids[:EXAMPLES]:
            r = by_id[i]
            out.append(f"- {i} {tidy(r['title'])[:45]} [{r['origin']}]: {tidy(hits[p][i])[:200]}")
        out.append("")
    out += [
        "## Share of recipes hit by the HP union, by course",
        "",
        "| course | hit | recipes | share |",
        "|---|---:|---:|---:|",
    ]
    hp = unions[FAMILIES[0][0]]
    hit_by = collections.Counter(by_id[i]["course"] for i in hp)
    all_by = collections.Counter(r["course"] for r in recipes)
    for k in sorted(all_by, key=str):
        out.append(f"| {k} | {hit_by[k]:,} | {all_by[k]:,} | {pct(hit_by[k], all_by[k])} |")
    return "\n".join(out) + "\n"


def readme(version):
    return f"""# Data release {version}: quality scan

A rule-based scan of the release's recipes for patterns that point at an incomplete recipe, a wrong portion or
weight, or broken steps. No model reads the recipes: every rule is a regex or a number check in
`data-engineering/scripts/v3_quality_scan.py`, so the same release always gives the same hits.

- `report.md`: per pattern the rule, the count, the share, the split by origin, five examples with evidence; the
  union counts; the caveats. Read the caveats first.
- `hits.csv`: one row per recipe and pattern: `recipe_id,title,origin,course,pattern,evidence`, sorted by recipe_id
  then pattern, UTF-8 without BOM, evidence on one line (at most 300 characters).

## Rerun

From the repository root, standard library only (any Python 3.11 or newer):

```bash
python -X utf8 data-engineering/scripts/v3_quality_scan.py --out data-engineering/docs/v3-quality-scan-<date>
```

Reads `data/release/v3/recipes.jsonl`, `ingredients.jsonl`, `release_manifest.json`, `data/release/v2.2/recipes.jsonl`
and `data/enrichment/v3_selected_wave1.csv`. Run it again after a rebuild of the release (the 11-05 corrections, the
11-07 freeze) into a new dated folder and compare the counts. The output has no timestamps; two runs on the same
release are byte-identical.

## Pick work from the CSV

1. Filter `pattern` to one in the `core` tier of `report.md` (the high-precision list without the trivial patterns), or to
   a family: P1 to P3 completeness (water, fat, pepper, serve-with carrier, named sauce), P4 to P6 portions and
   nutrition, P7 and P8 steps.
2. Read `evidence` and open the recipe. A match is only a candidate; the trivial patterns (P1b salt, P1c pepper,
   P1d greasing fat, P4c juice or zest) and the benign water patterns (P1a2, P1f2) are not defects by themselves.
3. A recipe with several rows (filter by `recipe_id`) is hit by several patterns and usually worth looking at first.
4. `origin` is `v2.2` (carried over from the v2.2 release), `overquota`, `wave1` or `wave2`. `overquota` is found
   by the enricher name in the recipe's `enrichment.by` (`claude/akane321`, `claude/DuJiayu`), the rest by
   `v3_selected_wave1.csv`.
5. Fixes go through the reviewed corrections table (`data/enrichment/v3-corrections.csv`, `scripts/v3_corrections.py`),
   not by editing this output.

## Not included

The planning-pool gates (priced, complete, meal role) are computed by the backend; this tool does not import it, so
the report has no plannable column. `docs/planning-pool-report.json` has the pool totals.
"""


def main():
    ap = argparse.ArgumentParser(description=__doc__.split("\n")[0])
    ap.add_argument("--out", required=True, type=Path, help="folder for report.md, hits.csv and README.md")
    ap.add_argument("--release", type=Path, default=RELEASE, help="release folder (default: data release v3)")
    args = ap.parse_args()

    version, recipes, ingredients = load(args.release)
    hits = scan(recipes, ingredients)
    by_id = {r["recipe_id"]: r for r in recipes}

    args.out.mkdir(parents=True, exist_ok=True)
    (args.out / "report.md").write_text(report(version, recipes, hits), encoding="utf-8", newline="\n")
    (args.out / "README.md").write_text(readme(version), encoding="utf-8", newline="\n")
    rows = sorted((i, p) for p, ids in hits.items() for i in ids)
    with (args.out / "hits.csv").open("w", encoding="utf-8", newline="") as handle:
        writer = csv.writer(handle, lineterminator="\n")
        writer.writerow(["recipe_id", "title", "origin", "course", "pattern", "evidence"])
        for i, p in rows:
            r = by_id[i]
            writer.writerow([i, tidy(r["title"]), r["origin"], r["course"], p, tidy(hits[p][i])])

    union = set().union(*(set(hits.get(p, {})) for p in HP))
    core = set().union(*(set(hits.get(p, {})) for p in CORE))
    print(f"{len(recipes)} recipes, {len(rows)} hits; HP union {len(union)}, core union {len(core)}")
    for p in PATTERNS:
        print(f"  {p} {len(hits.get(p, {}))}")
    print(f"wrote {args.out}")


if __name__ == "__main__":
    sys.exit(main())
