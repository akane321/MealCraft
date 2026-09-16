"""Regenerate config/ingredient_aliases.csv from a reviewable mapping table.

The base alias table is large enough that a flat hand-edited CSV is hard to
audit. This script keeps the mapping decisions grouped and commented here; the
CSV it emits stays the artifact the pipeline loads and reviewers can still edit
by hand afterwards.

Each entry: canonical_id -> (canonical_name, food_group, allergens, [aliases]).
Allergens use the project vocabulary: eggs, milk, gluten, gluten_candidate,
soy, peanuts, tree_nuts, crustaceans, fish, sesame. Only assign an allergen
when the mapping itself is unambiguous; compound or uncertain phrases are left
without one and still reach human review through the pipeline's own reasons.

Run:  python scripts/build_ingredient_aliases.py
"""

from __future__ import annotations

import csv
from pathlib import Path

# fmt: off
TABLE: dict[str, tuple[str, str, str, list[str]]] = {
    # --- water and basic liquids ---------------------------------------------
    "ING_WATER": ("water", "liquid", "", [
        "water", "cold water", "hot water", "warm water", "boiling water",
        "ice water", "lukewarm water", "warm water divided", "very warm water",
    ]),

    # --- alliums ------------------------------------------------------------
    "ING_ONION": ("onion", "vegetable", "", [
        "onion", "onions", "yellow onion", "white onion", "sweet onion",
        "cooking onion", "spanish onion", "vidalia onion",
    ]),
    "ING_RED_ONION": ("red onion", "vegetable", "", ["red onion", "red onions", "purple onion"]),
    "ING_GREEN_ONION": ("green onion", "vegetable", "", [
        "green onion", "green onions", "scallion", "scallions", "spring onion", "spring onions",
    ]),
    "ING_SHALLOT": ("shallot", "vegetable", "", ["shallot", "shallots"]),
    "ING_LEEK": ("leek", "vegetable", "", ["leek", "leeks"]),
    "ING_GARLIC": ("garlic", "vegetable", "", [
        "garlic", "garlic clove", "garlic cloves", "clove garlic", "cloves garlic",
        "fresh garlic", "minced garlic",
    ]),
    "ING_GARLIC_POWDER": ("garlic powder", "seasoning", "", ["garlic powder", "granulated garlic"]),
    "ING_GARLIC_SALT": ("garlic salt", "seasoning", "", ["garlic salt"]),

    # --- other vegetables --------------------------------------------------
    "ING_TOMATO": ("tomato", "vegetable", "", [
        "tomato", "tomatoes", "plum tomato", "plum tomatoes", "roma tomato", "roma tomatoes",
        "cherry tomatoes", "grape tomatoes", "fresh tomatoes", "vine ripened tomatoes",
    ]),
    "ING_CANNED_TOMATOES": ("canned tomatoes", "vegetable", "", [
        "can tomatoes", "canned tomatoes", "diced tomatoes", "can diced tomatoes",
        "crushed tomatoes", "whole tomatoes", "stewed tomatoes", "can stewed tomatoes",
        "petite diced tomatoes",
    ]),
    "ING_TOMATO_PASTE": ("tomato paste", "vegetable", "", ["tomato paste", "can tomato paste"]),
    "ING_TOMATO_SAUCE": ("tomato sauce", "vegetable", "", ["tomato sauce", "can tomato sauce"]),
    "ING_TOMATO_SOUP": ("condensed tomato soup", "prepared", "", ["tomato soup", "can tomato soup", "condensed tomato soup"]),
    "ING_CELERY": ("celery", "vegetable", "", [
        "celery", "celery stalk", "celery stalks", "stalk celery", "stalks celery",
        "celery rib", "celery ribs", "rib celery", "ribs celery", "chopped celery",
    ]),
    "ING_CARROT": ("carrot", "vegetable", "", [
        "carrot", "carrots", "baby carrots", "shredded carrots", "grated carrots",
        "carrot shredded", "large carrot", "large carrots",
    ]),
    "ING_POTATO": ("potato", "vegetable", "", [
        "potato", "potatoes", "russet potatoes", "baking potatoes", "white potatoes",
        "red potatoes", "new potatoes", "peeled potatoes",
    ]),
    "ING_SWEET_POTATO": ("sweet potato", "vegetable", "", ["sweet potato", "sweet potatoes", "yam", "yams"]),
    "ING_BELL_PEPPER": ("bell pepper", "vegetable", "", [
        "bell pepper", "bell peppers", "green bell pepper", "green bell peppers",
        "red bell pepper", "red bell peppers", "yellow bell pepper", "sweet pepper", "sweet peppers",
        "green pepper", "green peppers", "green bell peppers",
    ]),
    "ING_JALAPENO": ("jalapeno pepper", "vegetable", "", [
        "jalapeno", "jalapenos", "jalapeno pepper", "jalapeno peppers", "jalapeno chiles",
    ]),
    "ING_GREEN_CHILI": ("green chili", "vegetable", "", [
        "green chili", "green chilies", "green chiles", "can green chilies", "diced green chilies",
    ]),
    "ING_MUSHROOM": ("mushroom", "vegetable", "", [
        "mushroom", "mushrooms", "button mushrooms", "white mushrooms", "cremini mushrooms",
        "baby bella mushrooms", "sliced mushrooms", "can mushrooms", "mushrooms sliced",
    ]),
    "ING_MUSHROOM_SOUP": ("condensed cream of mushroom soup", "prepared", "", [
        "cream of mushroom soup", "can cream of mushroom soup", "mushroom soup",
        "condensed cream of mushroom soup",
    ]),
    "ING_CHICKEN_SOUP": ("condensed cream of chicken soup", "prepared", "", [
        "cream of chicken soup", "can cream of chicken soup", "condensed cream of chicken soup",
    ]),
    "ING_CELERY_SOUP": ("condensed cream of celery soup", "prepared", "", [
        "cream of celery soup", "can cream of celery soup", "condensed cream of celery soup",
    ]),
    "ING_BROCCOLI": ("broccoli", "vegetable", "", [
        "broccoli", "broccoli florets", "chopped broccoli", "pkg broccoli", "package broccoli",
        "frozen broccoli", "broccoli spears",
    ]),
    "ING_CAULIFLOWER": ("cauliflower", "vegetable", "", ["cauliflower", "head cauliflower", "cauliflower florets"]),
    "ING_SPINACH": ("spinach", "vegetable", "", [
        "spinach", "baby spinach", "fresh spinach", "chopped spinach", "pkg spinach",
        "package spinach", "frozen spinach", "spinach leaves",
    ]),
    "ING_LETTUCE": ("lettuce", "vegetable", "", [
        "lettuce", "head lettuce", "iceberg lettuce", "romaine lettuce", "leaf lettuce",
        "shredded lettuce",
    ]),
    "ING_CABBAGE": ("cabbage", "vegetable", "", [
        "cabbage", "head cabbage", "green cabbage", "shredded cabbage", "napa cabbage",
    ]),
    "ING_CUCUMBER": ("cucumber", "vegetable", "", ["cucumber", "cucumbers", "english cucumber"]),
    "ING_ZUCCHINI": ("zucchini", "vegetable", "", ["zucchini", "zucchinis", "courgette"]),
    "ING_YELLOW_SQUASH": ("yellow squash", "vegetable", "", ["yellow squash", "summer squash", "crookneck squash"]),
    "ING_BUTTERNUT_SQUASH": ("butternut squash", "vegetable", "", ["butternut squash"]),
    "ING_CORN": ("corn", "vegetable", "", [
        "corn", "whole kernel corn", "kernel corn", "corn kernels", "sweet corn",
        "frozen corn", "can corn", "can whole kernel corn",
    ]),
    "ING_CREAMED_CORN": ("cream style corn", "vegetable", "", ["cream style corn", "creamed corn", "can cream style corn"]),
    "ING_PEAS": ("peas", "vegetable", "", ["peas", "green peas", "frozen peas", "sweet peas", "english peas"]),
    "ING_GREEN_BEANS": ("green beans", "vegetable", "", [
        "green beans", "green bean", "can green beans", "frozen green beans", "french green beans",
        "cut green beans",
    ]),
    "ING_ASPARAGUS": ("asparagus", "vegetable", "", ["asparagus", "asparagus spears"]),
    "ING_EGGPLANT": ("eggplant", "vegetable", "", ["eggplant", "aubergine"]),
    "ING_AVOCADO": ("avocado", "fruit", "", ["avocado", "avocados", "ripe avocado", "hass avocado"]),
    "ING_PUMPKIN": ("pumpkin", "vegetable", "", ["pumpkin", "can pumpkin", "pumpkin puree", "canned pumpkin"]),
    "ING_CUCUMBER_PICKLE": ("pickle", "vegetable", "", ["pickle", "pickles", "dill pickle", "dill pickles"]),
    "ING_WATER_CHESTNUT": ("water chestnut", "vegetable", "", ["water chestnut", "water chestnuts", "can water chestnuts"]),
    "ING_OLIVE": ("olive", "vegetable", "", [
        "olive", "olives", "black olives", "can black olives", "ripe olives", "green olives",
        "sliced olives", "kalamata olives",
    ]),
    "ING_PIMENTO": ("pimento", "vegetable", "", ["pimento", "pimentos", "pimiento", "jar pimento", "jar pimentos"]),
    "ING_MIXED_VEGETABLES": ("mixed vegetables", "vegetable", "", [
        "mixed vegetables", "frozen mixed vegetables", "vegetables", "veggies",
    ]),

    # --- fresh herbs -----------------------------------------------------
    "ING_PARSLEY": ("parsley", "herb", "", [
        "parsley", "fresh parsley", "parsley flakes", "dried parsley", "chopped parsley",
        "flat leaf parsley", "flat-leaf parsley", "italian parsley", "curly parsley",
    ]),
    "ING_CILANTRO": ("cilantro", "herb", "", ["cilantro", "fresh cilantro", "cilantro leaves", "coriander leaves"]),
    "ING_BASIL": ("basil", "herb", "", ["basil", "fresh basil", "dried basil", "basil leaves", "sweet basil"]),
    "ING_MINT": ("mint", "herb", "", ["mint", "fresh mint", "mint leaves", "spearmint"]),
    "ING_CHIVES": ("chives", "herb", "", ["chives", "fresh chives", "chopped chives"]),
    "ING_DILL": ("dill", "herb", "", ["dill", "fresh dill", "dill weed", "dried dill"]),
    "ING_ROSEMARY": ("rosemary", "herb", "", ["rosemary", "fresh rosemary", "dried rosemary"]),
    "ING_THYME": ("thyme", "herb", "", ["thyme", "fresh thyme", "dried thyme", "thyme leaves", "sprigs thyme", "sprig thyme"]),
    "ING_OREGANO": ("oregano", "herb", "", ["oregano", "dried oregano", "fresh oregano", "mexican oregano"]),
    "ING_SAGE": ("sage", "herb", "", ["sage", "dried sage", "fresh sage", "rubbed sage"]),
    "ING_TARRAGON": ("tarragon", "herb", "", ["tarragon", "dried tarragon"]),
    "ING_MARJORAM": ("marjoram", "herb", "", ["marjoram", "dried marjoram"]),
    "ING_BAY_LEAF": ("bay leaf", "herb", "", ["bay leaf", "bay leaves", "dried bay leaf"]),

    # --- dried spices ---------------------------------------------------
    "ING_SALT": ("salt", "seasoning", "", [
        "salt", "table salt", "kosher salt", "sea salt", "coarse salt", "fine salt",
        "iodized salt", "flaky salt", "salt to taste",
    ]),
    "ING_SALT_AND_PEPPER": ("salt and pepper", "seasoning", "", [
        "salt and pepper", "salt and black pepper", "salt & pepper", "salt & black pepper",
        "salt and ground black pepper", "salt and freshly ground black pepper",
        "salt & freshly ground black pepper", "kosher salt and pepper", "salt and white pepper",
        "salt pepper", "salt and freshly ground pepper",
    ]),
    "ING_SEASONED_SALT": ("seasoned salt", "seasoning", "", ["seasoned salt", "seasoning salt", "lawry's seasoned salt"]),
    "ING_CELERY_SALT": ("celery salt", "seasoning", "", ["celery salt"]),
    "ING_BLACK_PEPPER": ("black pepper", "seasoning", "", [
        "pepper", "black pepper", "ground black pepper", "ground pepper", "cracked black pepper",
        "coarse black pepper", "coarsely ground black pepper", "fresh ground black pepper",
        "fresh ground pepper", "freshly ground black pepper", "freshly ground pepper",
        "pepper to taste", "white pepper",
    ]),
    "ING_CAYENNE": ("cayenne pepper", "seasoning", "", [
        "cayenne", "cayenne pepper", "ground cayenne", "ground red pepper", "red pepper flakes",
        "crushed red pepper", "crushed red pepper flakes", "red pepper flake",
    ]),
    "ING_CHILI_POWDER": ("chili powder", "seasoning", "", ["chili powder", "chile powder"]),
    "ING_PAPRIKA": ("paprika", "seasoning", "", [
        "paprika", "sweet paprika", "smoked paprika", "hungarian paprika", "spanish paprika",
    ]),
    "ING_CUMIN": ("cumin", "seasoning", "", ["cumin", "ground cumin", "cumin seed", "cumin seeds"]),
    "ING_CORIANDER": ("coriander", "seasoning", "", ["coriander", "ground coriander", "coriander seed"]),
    "ING_TURMERIC": ("turmeric", "seasoning", "", ["turmeric", "ground turmeric"]),
    "ING_CINNAMON": ("cinnamon", "seasoning", "", [
        "cinnamon", "ground cinnamon", "cinnamon stick", "cinnamon sticks", "stick cinnamon",
    ]),
    "ING_NUTMEG": ("nutmeg", "seasoning", "", ["nutmeg", "ground nutmeg", "freshly grated nutmeg"]),
    "ING_CLOVES_SPICE": ("cloves", "seasoning", "", ["cloves", "ground cloves", "whole cloves"]),
    "ING_ALLSPICE": ("allspice", "seasoning", "", ["allspice", "ground allspice"]),
    "ING_GINGER": ("ginger", "seasoning", "", [
        "ginger", "fresh ginger", "ground ginger", "gingerroot", "ginger root", "grated ginger",
    ]),
    "ING_CARDAMOM": ("cardamom", "seasoning", "", ["cardamom", "ground cardamom"]),
    "ING_CURRY_POWDER": ("curry powder", "seasoning", "", ["curry powder", "curry"]),
    "ING_ITALIAN_SEASONING": ("italian seasoning", "seasoning", "", ["italian seasoning", "italian herb seasoning"]),
    "ING_POULTRY_SEASONING": ("poultry seasoning", "seasoning", "", ["poultry seasoning"]),
    "ING_ONION_POWDER": ("onion powder", "seasoning", "", ["onion powder"]),
    "ING_DRY_MUSTARD": ("mustard powder", "seasoning", "", ["dry mustard", "ground mustard", "mustard powder", "powdered mustard"]),
    "ING_CREAM_OF_TARTAR": ("cream of tartar", "seasoning", "", ["cream of tartar"]),
    "ING_PEPPERCORN": ("peppercorn", "seasoning", "", ["peppercorn", "peppercorns", "whole peppercorns"]),
    "ING_FENNEL_SEED": ("fennel seed", "seasoning", "", ["fennel seed", "fennel seeds"]),
    "ING_SESAME_SEED": ("sesame seed", "seasoning", "sesame", ["sesame seed", "sesame seeds", "toasted sesame seeds"]),
    "ING_POPPY_SEED": ("poppy seed", "seasoning", "", ["poppy seed", "poppy seeds"]),
    "ING_CELERY_SEED": ("celery seed", "seasoning", "", ["celery seed", "celery seeds"]),
    "ING_BAKING_POWDER": ("baking powder", "leavening", "", ["baking powder", "double acting baking powder"]),
    "ING_BAKING_SODA": ("baking soda", "leavening", "", ["baking soda", "soda", "bicarbonate of soda", "sodium bicarbonate"]),
    "ING_YEAST": ("yeast", "leavening", "", [
        "yeast", "active dry yeast", "dry yeast", "instant yeast", "rapid rise yeast",
        "pkg yeast", "package yeast", "pkg dry yeast", "bread machine yeast",
    ]),

    # --- dairy and eggs ------------------------------------------------
    "ING_MILK": ("milk", "dairy", "milk", [
        "milk", "whole milk", "2% milk", "1% milk", "skim milk", "reduced fat milk",
        "low fat milk", "nonfat milk", "fresh milk",
    ]),
    "ING_BUTTERMILK": ("buttermilk", "dairy", "milk", ["buttermilk", "cultured buttermilk"]),
    "ING_EVAPORATED_MILK": ("evaporated milk", "dairy", "milk", ["evaporated milk", "can evaporated milk"]),
    "ING_CONDENSED_MILK": ("sweetened condensed milk", "dairy", "milk", [
        "sweetened condensed milk", "condensed milk", "can sweetened condensed milk",
        "eagle brand milk", "can condensed milk",
    ]),
    "ING_CREAM": ("cream", "dairy", "milk", [
        "cream", "heavy cream", "heavy whipping cream", "whipping cream", "light cream",
        "table cream", "double cream",
    ]),
    "ING_SOUR_CREAM": ("sour cream", "dairy", "milk", [
        "sour cream", "carton sour cream", "light sour cream", "reduced fat sour cream",
        "pkg sour cream", "container sour cream",
    ]),
    "ING_YOGURT": ("yogurt", "dairy", "milk", [
        "yogurt", "plain yogurt", "greek yogurt", "plain greek yogurt", "vanilla yogurt",
        "natural yogurt", "yoghurt",
    ]),
    "ING_BUTTER": ("butter", "dairy", "milk", [
        "butter", "unsalted butter", "salted butter", "sweet cream butter", "stick butter",
        "sticks butter", "butter softened", "butter melted", "real butter",
    ]),
    "ING_MARGARINE": ("margarine", "fat", "", [
        "margarine", "oleo", "stick margarine", "sticks margarine", "stick oleo",
        "soft margarine",
    ]),
    "ING_BUTTER_OR_MARGARINE": ("butter or margarine", "fat", "", [
        "butter or margarine", "margarine or butter", "butter or oleo", "oleo or butter",
        "stick butter or margarine",
    ]),
    "ING_CREAM_CHEESE": ("cream cheese", "dairy", "milk", [
        "cream cheese", "pkg cream cheese", "package cream cheese", "block cream cheese",
        "softened cream cheese", "light cream cheese", "neufchatel", "philadelphia cream cheese",
        "weight cream cheese", "whipped cream cheese",
    ]),
    "ING_CHEESE": ("cheese", "dairy", "milk", ["cheese", "shredded cheese", "grated cheese"]),
    "ING_CHEDDAR": ("cheddar cheese", "dairy", "milk", [
        "cheddar", "cheddar cheese", "sharp cheddar", "sharp cheddar cheese", "sharp cheese",
        "mild cheddar", "shredded cheddar", "shredded cheddar cheese", "grated cheddar",
    ]),
    "ING_MOZZARELLA": ("mozzarella cheese", "dairy", "milk", [
        "mozzarella", "mozzarella cheese", "shredded mozzarella", "part skim mozzarella cheese",
        "fresh mozzarella", "part-skim mozzarella cheese",
    ]),
    "ING_PARMESAN": ("parmesan cheese", "dairy", "milk", [
        "parmesan", "parmesan cheese", "grated parmesan", "grated parmesan cheese",
        "parmigiano reggiano", "shredded parmesan", "parmesan cheese grated",
    ]),
    "ING_MONTEREY_JACK": ("monterey jack cheese", "dairy", "milk", [
        "monterey jack", "monterey jack cheese", "pepper jack", "pepper jack cheese", "jack cheese",
    ]),
    "ING_SWISS_CHEESE": ("swiss cheese", "dairy", "milk", ["swiss cheese", "swiss"]),
    "ING_FETA": ("feta cheese", "dairy", "milk", ["feta", "feta cheese", "crumbled feta cheese", "crumbled feta"]),
    "ING_RICOTTA": ("ricotta cheese", "dairy", "milk", ["ricotta", "ricotta cheese", "part skim ricotta"]),
    "ING_COTTAGE_CHEESE": ("cottage cheese", "dairy", "milk", ["cottage cheese", "small curd cottage cheese"]),
    "ING_PARMESAN_ROMANO": ("romano cheese", "dairy", "milk", ["romano cheese", "pecorino romano"]),
    "ING_AMERICAN_CHEESE": ("american cheese", "dairy", "milk", ["american cheese", "processed cheese", "velveeta", "velveeta cheese"]),
    "ING_GOAT_CHEESE": ("goat cheese", "dairy", "milk", ["goat cheese", "chevre"]),
    "ING_EGG": ("egg", "protein", "eggs", [
        "egg", "eggs", "large egg", "large eggs", "whole egg", "whole eggs", "extra large eggs",
        "egg beaten", "eggs beaten", "beaten egg", "beaten eggs", "hard boiled eggs",
        "hard cooked eggs",
    ]),
    "ING_EGG_WHITE": ("egg white", "protein", "eggs", ["egg white", "egg whites"]),
    "ING_EGG_YOLK": ("egg yolk", "protein", "eggs", ["egg yolk", "egg yolks", "yolk", "yolks"]),

    # --- meat, poultry, seafood --------------------------------------
    "ING_CHICKEN": ("chicken", "protein", "", [
        "chicken", "whole chicken", "cut up chicken", "fryer chicken", "chicken pieces",
    ]),
    "ING_CHICKEN_BREAST": ("chicken breast", "protein", "", [
        "chicken breast", "chicken breasts", "boneless chicken breast", "boneless chicken breasts",
        "boneless skinless chicken breast", "boneless skinless chicken breasts",
        "chicken breast halves", "split chicken breasts", "skinless boneless chicken breasts",
    ]),
    "ING_CHICKEN_THIGH": ("chicken thigh", "protein", "", [
        "chicken thigh", "chicken thighs", "boneless chicken thighs", "boneless skinless chicken thighs",
    ]),
    "ING_COOKED_CHICKEN": ("cooked chicken", "protein", "", [
        "cooked chicken", "diced cooked chicken", "shredded chicken", "shredded cooked chicken",
        "chopped cooked chicken", "rotisserie chicken",
    ]),
    "ING_GROUND_BEEF": ("ground beef", "protein", "", [
        "ground beef", "lean ground beef", "extra lean ground beef", "ground chuck", "ground round",
        "hamburger", "hamburger meat", "ground sirloin", "80/20 ground beef",
    ]),
    "ING_BEEF": ("beef", "protein", "", [
        "beef", "beef chuck", "chuck", "chuck roast", "beef roast", "stew beef", "beef stew meat",
        "stewing beef", "beef cubes", "sirloin", "beef tips", "round steak", "beef brisket",
        "brisket",
    ]),
    "ING_CHICKEN_WINGS": ("chicken wings", "protein", "", ["chicken wings", "chicken wing", "wingettes", "chicken drumettes"]),
    "ING_BEEF_STEAK": ("steak", "protein", "", ["steak", "steaks", "flank steak", "sirloin steak", "ribeye", "rib eye steak"]),
    "ING_PORK": ("pork", "protein", "", ["pork", "pork loin", "pork shoulder", "pork roast", "pork tenderloin", "pork butt"]),
    "ING_PORK_CHOP": ("pork chop", "protein", "", ["pork chop", "pork chops", "boneless pork chops"]),
    "ING_GROUND_PORK": ("ground pork", "protein", "", ["ground pork"]),
    "ING_BACON": ("bacon", "protein", "", ["bacon", "bacon slices", "bacon strips", "thick cut bacon", "cooked bacon", "crumbled bacon"]),
    "ING_HAM": ("ham", "protein", "", ["ham", "cooked ham", "diced ham", "ham steak", "deli ham", "cubed ham"]),
    "ING_SAUSAGE": ("sausage", "protein", "", [
        "sausage", "pork sausage", "italian sausage", "breakfast sausage", "ground sausage",
        "bulk sausage", "smoked sausage", "kielbasa",
    ]),
    "ING_PEPPERONI": ("pepperoni", "protein", "", ["pepperoni", "pepperoni slices", "turkey pepperoni"]),
    "ING_PROSCIUTTO": ("prosciutto", "protein", "", ["prosciutto", "parma ham"]),
    "ING_GROUND_TURKEY": ("ground turkey", "protein", "", ["ground turkey", "lean ground turkey"]),
    "ING_TURKEY": ("turkey", "protein", "", ["turkey", "turkey breast", "cooked turkey", "roast turkey", "diced turkey"]),
    "ING_CHIPPED_BEEF": ("dried beef", "protein", "", ["dried beef", "chipped beef", "jar dried beef"]),
    "ING_SHRIMP": ("shrimp", "protein", "crustaceans", [
        "shrimp", "medium shrimp", "large shrimp", "raw shrimp", "cooked shrimp", "peeled shrimp",
        "jumbo shrimp", "prawns",
    ]),
    "ING_SALMON": ("salmon", "protein", "fish", ["salmon", "salmon fillet", "salmon fillets", "salmon steak", "can salmon", "canned salmon"]),
    "ING_TUNA": ("tuna", "protein", "fish", ["tuna", "can tuna", "canned tuna", "tuna fish", "albacore tuna", "chunk light tuna"]),
    "ING_CRAB": ("crab", "protein", "crustaceans", ["crab", "crabmeat", "crab meat", "lump crabmeat", "imitation crab"]),
    "ING_FISH_FILLET": ("fish fillet", "protein", "fish", ["fish", "fish fillet", "fish fillets", "white fish", "cod", "tilapia", "haddock"]),
    "ING_ANCHOVY": ("anchovy", "protein", "fish", ["anchovy", "anchovies", "anchovy paste", "anchovy fillets"]),

    # --- legumes, nuts, seeds ---------------------------------------
    "ING_BLACK_BEANS": ("black beans", "protein", "", ["black beans", "can black beans", "black bean"]),
    "ING_KIDNEY_BEANS": ("kidney beans", "protein", "", ["kidney beans", "can kidney beans", "red kidney beans", "dark red kidney beans"]),
    "ING_PINTO_BEANS": ("pinto beans", "protein", "", ["pinto beans", "can pinto beans"]),
    "ING_CANNELLINI": ("white beans", "protein", "", ["white beans", "cannellini beans", "great northern beans", "navy beans"]),
    "ING_BAKED_BEANS": ("baked beans", "protein", "", ["baked beans", "can baked beans", "pork and beans"]),
    "ING_CHICKPEA": ("chickpea", "protein", "", ["chickpea", "chickpeas", "garbanzo beans", "can chickpeas"]),
    "ING_LENTIL": ("lentil", "protein", "", ["lentil", "lentils", "red lentils", "green lentils", "brown lentils"]),
    "ING_REFRIED_BEANS": ("refried beans", "protein", "", ["refried beans", "can refried beans"]),
    "ING_BEAN_SPROUTS": ("bean sprouts", "vegetable", "soy", ["bean sprouts", "bean sprout", "mung bean sprouts"]),
    "ING_PEANUT": ("peanut", "protein", "peanuts", ["peanut", "peanuts", "dry roasted peanuts", "salted peanuts", "spanish peanuts"]),
    "ING_PEANUT_BUTTER": ("peanut butter", "protein", "peanuts", [
        "peanut butter", "creamy peanut butter", "crunchy peanut butter", "chunky peanut butter",
        "natural peanut butter", "smooth peanut butter",
    ]),
    "ING_ALMOND": ("almond", "protein", "tree_nuts", [
        "almond", "almonds", "sliced almonds", "slivered almonds", "chopped almonds",
        "whole almonds", "blanched almonds", "toasted almonds", "ground almonds",
    ]),
    "ING_WALNUT": ("walnut", "protein", "tree_nuts", ["walnut", "walnuts", "chopped walnuts", "walnut halves", "walnut pieces", "english walnuts"]),
    "ING_PECAN": ("pecan", "protein", "tree_nuts", ["pecan", "pecans", "chopped pecans", "pecan halves", "pecan pieces", "toasted pecans"]),
    "ING_CASHEW": ("cashew", "protein", "tree_nuts", ["cashew", "cashews", "cashew nuts", "roasted cashews"]),
    "ING_PISTACHIO": ("pistachio", "protein", "tree_nuts", ["pistachio", "pistachios", "shelled pistachios"]),
    "ING_HAZELNUT": ("hazelnut", "protein", "tree_nuts", ["hazelnut", "hazelnuts", "filberts"]),
    "ING_PINE_NUT": ("pine nut", "protein", "tree_nuts", ["pine nut", "pine nuts", "pignoli"]),
    "ING_MIXED_NUTS": ("nuts", "protein", "tree_nuts", ["nuts", "chopped nuts", "mixed nuts", "nut pieces", "broken nuts"]),
    "ING_SUNFLOWER_SEED": ("sunflower seed", "protein", "", ["sunflower seed", "sunflower seeds", "sunflower kernels"]),
    "ING_PUMPKIN_SEED": ("pumpkin seed", "protein", "", ["pumpkin seed", "pumpkin seeds", "pepitas"]),
    "ING_FLAX": ("flaxseed", "protein", "", ["flaxseed", "flax seed", "ground flaxseed", "flax seeds"]),
    "ING_CHIA": ("chia seed", "protein", "", ["chia seed", "chia seeds"]),
    "ING_TOFU": ("tofu", "protein", "soy", ["tofu", "firm tofu", "silken tofu", "extra firm tofu", "soft tofu"]),
    "ING_WHEAT_GERM": ("wheat germ", "grain", "gluten", ["wheat germ", "toasted wheat germ"]),

    # --- grains, flours, baking ------------------------------------
    "ING_FLOUR": ("all-purpose flour", "grain", "gluten", [
        "flour", "all purpose flour", "all-purpose flour", "plain flour", "unbleached flour",
        "sifted flour", "sifted all purpose flour", "white flour", "unbleached all purpose flour",
    ]),
    "ING_SELF_RISING_FLOUR": ("self-rising flour", "grain", "gluten", ["self rising flour", "self-rising flour", "self raising flour"]),
    "ING_WHOLE_WHEAT_FLOUR": ("whole wheat flour", "grain", "gluten", ["wheat flour", "whole wheat flour", "whole-wheat flour", "graham flour"]),
    "ING_BREAD_FLOUR": ("bread flour", "grain", "gluten", ["bread flour"]),
    "ING_CAKE_FLOUR": ("cake flour", "grain", "gluten", ["cake flour"]),
    "ING_CORNSTARCH": ("cornstarch", "grain", "", ["cornstarch", "corn starch", "cornflour"]),
    "ING_CORNMEAL": ("cornmeal", "grain", "", ["cornmeal", "corn meal", "yellow cornmeal", "stone ground cornmeal"]),
    "ING_CORN_FLOUR_MASA": ("masa harina", "grain", "", ["masa harina", "masa"]),
    "ING_RICE": ("rice", "grain", "", [
        "rice", "white rice", "long grain rice", "long grain white rice", "jasmine rice",
        "basmati rice", "uncooked rice", "cooked rice", "minute rice", "instant rice",
    ]),
    "ING_BROWN_RICE": ("brown rice", "grain", "", ["brown rice", "long grain brown rice"]),
    "ING_OATS": ("oats", "grain", "gluten_candidate", [
        "oats", "rolled oats", "old fashioned oats", "old-fashioned oats", "quick oats",
        "quick cooking oats", "quick-cooking oats", "oatmeal", "instant oats",
    ]),
    "ING_QUINOA": ("quinoa", "grain", "", ["quinoa"]),
    "ING_BARLEY": ("barley", "grain", "gluten", ["barley", "pearl barley", "pearled barley"]),
    "ING_COUSCOUS": ("couscous", "grain", "gluten", ["couscous"]),
    "ING_PASTA": ("pasta", "grain", "gluten", [
        "pasta", "spaghetti", "penne", "rigatoni", "linguine", "fettuccine", "rotini",
        "bow tie pasta", "farfalle", "ziti", "angel hair pasta", "lasagna noodles",
    ]),
    "ING_MACARONI": ("macaroni", "grain", "gluten", ["macaroni", "elbow macaroni", "elbow noodles", "macaroni noodles"]),
    "ING_EGG_NOODLES": ("egg noodles", "grain", "gluten;eggs", ["egg noodles", "wide egg noodles", "medium egg noodles", "noodles"]),
    "ING_BREAD": ("bread", "grain", "gluten", [
        "bread", "white bread", "sliced bread", "sandwich bread", "bread slices", "day old bread",
        "italian bread", "french bread", "sourdough bread",
    ]),
    "ING_BREADCRUMBS": ("bread crumbs", "grain", "gluten", [
        "bread crumbs", "breadcrumbs", "dry bread crumbs", "fine bread crumbs", "soft bread crumbs",
        "panko", "panko bread crumbs", "italian bread crumbs", "seasoned bread crumbs",
    ]),
    "ING_CRACKER_CRUMBS": ("cracker crumbs", "grain", "gluten", [
        "cracker crumbs", "ritz crackers", "saltine crackers", "crushed crackers", "graham crackers",
        "graham cracker crumbs", "crushed graham crackers",
    ]),
    "ING_CROUTONS": ("croutons", "grain", "gluten", ["croutons", "seasoned croutons"]),
    "ING_TORTILLA": ("tortilla", "grain", "", [
        "tortilla", "tortillas", "flour tortillas", "corn tortillas", "flour tortilla", "corn tortilla",
    ]),
    "ING_TORTILLA_CHIPS": ("tortilla chips", "grain", "", ["tortilla chips", "corn chips"]),
    "ING_STUFFING_MIX": ("stuffing mix", "grain", "gluten", [
        "stuffing mix", "herb stuffing mix", "seasoned stuffing mix", "cornbread stuffing mix",
        "stove top stuffing", "herb seasoned stuffing mix",
    ]),
    "ING_BISCUIT_MIX": ("baking mix", "grain", "gluten", ["baking mix", "biscuit mix", "bisquick", "buttermilk baking mix"]),
    "ING_CAKE_MIX": ("cake mix", "grain", "gluten", [
        "cake mix", "yellow cake mix", "white cake mix", "chocolate cake mix", "box cake mix",
        "box yellow cake mix", "devils food cake mix", "spice cake mix", "german chocolate cake mix",
    ]),
    "ING_PUDDING_MIX": ("instant pudding mix", "prepared", "", [
        "pudding mix", "instant pudding mix", "vanilla pudding mix", "vanilla pudding",
        "instant vanilla pudding", "chocolate pudding mix", "pkg vanilla pudding",
        "instant pudding", "pkg instant pudding",
    ]),
    "ING_GELATIN": ("gelatin", "prepared", "", ["gelatin", "unflavored gelatin", "knox gelatin", "jello", "jell-o", "flavored gelatin"]),
    "ING_PIE_CRUST": ("pie crust", "grain", "gluten", [
        "pie crust", "unbaked pie crust", "pie shell", "unbaked pie shell", "pastry shell",
        "graham cracker crust", "graham cracker pie crust", "deep dish pie crust",
        "pie crusts", "refrigerated pie crust",
    ]),
    "ING_PUFF_PASTRY": ("puff pastry", "grain", "gluten", ["puff pastry", "puff pastry sheets"]),
    "ING_CRESCENT_ROLLS": ("crescent rolls", "grain", "gluten", ["crescent rolls", "crescent roll dough", "can crescent rolls"]),
    "ING_PHYLLO": ("phyllo dough", "grain", "gluten", ["phyllo dough", "phyllo", "filo dough", "phyllo sheets"]),
    "ING_HAMBURGER_BUN": ("hamburger bun", "grain", "gluten", ["hamburger bun", "hamburger buns", "burger buns", "sandwich buns"]),
    "ING_HOT_DOG_BUN": ("hot dog bun", "grain", "gluten", ["hot dog bun", "hot dog buns"]),
    "ING_DINNER_ROLL": ("dinner roll", "grain", "gluten", ["dinner roll", "dinner rolls", "rolls"]),
    "ING_CEREAL_RICE": ("crisp rice cereal", "grain", "", ["crisp rice cereal", "rice krispies", "rice crispies", "crispy rice cereal"]),
    "ING_CEREAL_CORNFLAKE": ("corn flakes", "grain", "", ["corn flakes", "cornflakes", "crushed corn flakes"]),
    "ING_SHREDDED_WHEAT": ("shredded wheat", "grain", "gluten", ["shredded wheat", "shredded rice biscuits", "bite size shredded rice biscuits"]),

    # --- fats and oils ---------------------------------------------
    "ING_VEGETABLE_OIL": ("vegetable oil", "fat", "", [
        "oil", "vegetable oil", "cooking oil", "salad oil", "canola oil", "corn oil",
        "wesson oil", "frying oil", "neutral oil",
    ]),
    "ING_OLIVE_OIL": ("olive oil", "fat", "", [
        "olive oil", "extra virgin olive oil", "extra-virgin olive oil", "light olive oil",
        "pure olive oil",
    ]),
    "ING_SESAME_OIL": ("sesame oil", "fat", "sesame", ["sesame oil", "toasted sesame oil", "dark sesame oil"]),
    "ING_PEANUT_OIL": ("peanut oil", "fat", "peanuts", ["peanut oil"]),
    "ING_COCONUT_OIL": ("coconut oil", "fat", "", ["coconut oil", "virgin coconut oil"]),
    "ING_SHORTENING": ("shortening", "fat", "", ["shortening", "vegetable shortening", "crisco", "butter flavored shortening"]),
    "ING_COOKING_SPRAY": ("cooking spray", "fat", "", ["cooking spray", "nonstick cooking spray", "non stick spray", "pam"]),
    "ING_LARD": ("lard", "fat", "", ["lard"]),

    # --- sweeteners ---------------------------------------------
    "ING_SUGAR": ("granulated sugar", "sweetener", "", [
        "sugar", "white sugar", "granulated sugar", "cane sugar", "caster sugar", "superfine sugar",
    ]),
    "ING_BROWN_SUGAR": ("brown sugar", "sweetener", "", [
        "brown sugar", "light brown sugar", "dark brown sugar", "packed brown sugar",
        "firmly packed brown sugar", "golden brown sugar",
    ]),
    "ING_POWDERED_SUGAR": ("powdered sugar", "sweetener", "", [
        "powdered sugar", "confectioners sugar", "confectioners' sugar", "icing sugar",
        "10x sugar", "box powdered sugar", "sifted powdered sugar",
    ]),
    "ING_HONEY": ("honey", "sweetener", "", ["honey", "raw honey", "clover honey", "local honey"]),
    "ING_MAPLE_SYRUP": ("maple syrup", "sweetener", "", ["maple syrup", "pure maple syrup", "real maple syrup"]),
    "ING_CORN_SYRUP": ("corn syrup", "sweetener", "", ["corn syrup", "light corn syrup", "dark corn syrup", "karo syrup"]),
    "ING_MOLASSES": ("molasses", "sweetener", "", ["molasses", "dark molasses", "blackstrap molasses", "unsulphured molasses"]),
    "ING_AGAVE": ("agave nectar", "sweetener", "", ["agave", "agave nectar", "agave syrup"]),

    # --- chocolate, cocoa, baking flavors -------------------------
    "ING_VANILLA": ("vanilla extract", "flavoring", "", [
        "vanilla", "vanilla extract", "pure vanilla extract", "vanilla flavoring",
        "imitation vanilla", "real vanilla",
    ]),
    "ING_ALMOND_EXTRACT": ("almond extract", "flavoring", "tree_nuts", ["almond extract", "pure almond extract"]),
    "ING_LEMON_EXTRACT": ("lemon extract", "flavoring", "", ["lemon extract"]),
    "ING_COCOA": ("cocoa powder", "flavoring", "", [
        "cocoa", "cocoa powder", "unsweetened cocoa", "unsweetened cocoa powder", "baking cocoa",
        "dutch process cocoa", "hershey's cocoa",
    ]),
    "ING_CHOCOLATE_CHIPS": ("chocolate chips", "flavoring", "milk", [
        "chocolate chips", "semisweet chocolate chips", "semi sweet chocolate chips",
        "semi-sweet chocolate chips", "milk chocolate chips", "mini chocolate chips",
        "pkg chocolate chips", "chocolate morsels",
    ]),
    "ING_BAKING_CHOCOLATE": ("baking chocolate", "flavoring", "milk", [
        "baking chocolate", "unsweetened chocolate", "bittersweet chocolate", "semisweet chocolate",
        "german chocolate", "chocolate squares", "unsweetened baking chocolate", "plain chocolate",
    ]),
    "ING_WHITE_CHOCOLATE": ("white chocolate", "flavoring", "milk", ["white chocolate", "white chocolate chips", "white baking chips"]),

    # --- condiments, sauces --------------------------------------
    "ING_MAYO": ("mayonnaise", "condiment", "eggs", ["mayonnaise", "mayo", "real mayonnaise", "light mayonnaise", "miracle whip"]),
    "ING_MUSTARD": ("prepared mustard", "condiment", "", ["mustard", "prepared mustard", "yellow mustard", "spicy brown mustard"]),
    "ING_DIJON": ("dijon mustard", "condiment", "", ["dijon mustard", "dijon", "grainy mustard", "whole grain mustard"]),
    "ING_KETCHUP": ("ketchup", "condiment", "", ["ketchup", "catsup", "tomato ketchup"]),
    "ING_WORCESTERSHIRE": ("worcestershire sauce", "condiment", "fish", ["worcestershire sauce", "worcestershire", "worchestershire sauce"]),
    "ING_SOY_SAUCE": ("soy sauce", "condiment", "soy;gluten", ["soy sauce", "light soy sauce", "dark soy sauce", "low sodium soy sauce", "tamari"]),
    "ING_HOT_SAUCE": ("hot sauce", "condiment", "", [
        "hot sauce", "hot pepper sauce", "tabasco", "tabasco sauce", "louisiana hot sauce",
        "franks red hot", "frank's redhot", "sriracha",
    ]),
    "ING_BBQ_SAUCE": ("barbecue sauce", "condiment", "", ["barbecue sauce", "bbq sauce", "barbeque sauce"]),
    "ING_SALSA": ("salsa", "condiment", "", ["salsa", "picante sauce", "chunky salsa", "jar salsa"]),
    "ING_CHILI_SAUCE": ("chili sauce", "condiment", "", ["chili sauce", "heinz chili sauce"]),
    "ING_HORSERADISH": ("horseradish", "condiment", "", ["horseradish", "prepared horseradish", "horseradish sauce"]),
    "ING_RELISH": ("pickle relish", "condiment", "", ["relish", "pickle relish", "sweet pickle relish", "dill relish"]),
    "ING_FISH_SAUCE": ("fish sauce", "condiment", "fish", ["fish sauce", "nam pla"]),
    "ING_OYSTER_SAUCE": ("oyster sauce", "condiment", "molluscs", ["oyster sauce"]),
    "ING_TERIYAKI": ("teriyaki sauce", "condiment", "soy;gluten", ["teriyaki sauce", "teriyaki"]),
    "ING_PESTO": ("pesto", "condiment", "tree_nuts;milk", ["pesto", "basil pesto", "prepared pesto"]),
    "ING_MARINARA": ("marinara sauce", "condiment", "", ["marinara sauce", "marinara", "pasta sauce", "spaghetti sauce", "jar spaghetti sauce"]),
    "ING_CAPERS": ("capers", "condiment", "", ["capers", "caper"]),
    "ING_JAM": ("jam", "condiment", "", ["jam", "jelly", "preserves", "fruit preserves", "strawberry jam", "grape jelly", "apricot preserves"]),
    "ING_NUTELLA": ("chocolate hazelnut spread", "condiment", "tree_nuts;milk", ["nutella", "chocolate hazelnut spread"]),

    # --- vinegars, wine, broth ----------------------------------
    "ING_VINEGAR": ("vinegar", "condiment", "", ["vinegar", "white vinegar", "distilled vinegar", "distilled white vinegar"]),
    "ING_CIDER_VINEGAR": ("apple cider vinegar", "condiment", "", ["cider vinegar", "apple cider vinegar"]),
    "ING_RED_WINE_VINEGAR": ("red wine vinegar", "condiment", "", ["red wine vinegar"]),
    "ING_WHITE_WINE_VINEGAR": ("white wine vinegar", "condiment", "", ["white wine vinegar"]),
    "ING_BALSAMIC": ("balsamic vinegar", "condiment", "", ["balsamic vinegar", "balsamic"]),
    "ING_RICE_VINEGAR": ("rice vinegar", "condiment", "", ["rice vinegar", "rice wine vinegar", "seasoned rice vinegar"]),
    "ING_RED_WINE": ("red wine", "beverage", "sulfites", ["red wine", "dry red wine", "burgundy", "cabernet"]),
    "ING_WHITE_WINE": ("white wine", "beverage", "sulfites", ["white wine", "dry white wine", "dry sherry", "sherry", "marsala", "marsala wine"]),
    "ING_BEER": ("beer", "beverage", "gluten", ["beer", "lager", "ale"]),
    "ING_VODKA": ("vodka", "beverage", "", ["vodka"]),
    "ING_RUM": ("rum", "beverage", "", ["rum", "dark rum", "light rum"]),
    "ING_CHICKEN_BROTH": ("chicken broth", "prepared", "", [
        "chicken broth", "chicken stock", "can chicken broth",
        "low sodium chicken broth", "chicken base",
    ]),
    "ING_BEEF_BROTH": ("beef broth", "prepared", "", ["beef broth", "beef stock", "can beef broth", "beef consomme"]),
    "ING_VEGETABLE_BROTH": ("vegetable broth", "prepared", "", ["vegetable broth", "vegetable stock", "veggie broth"]),
    # Bouillon (cube/granule/powder concentrate) is not the same product as
    # prepared broth - different form and a different dilution ratio - so it
    # gets its own canonical rather than being folded into chicken/beef broth.
    "ING_BOUILLON": ("bouillon cube", "prepared", "", [
        "bouillon cube", "bouillon", "bouillon cubes", "chicken bouillon cube",
        "chicken bouillon", "instant chicken bouillon", "beef bouillon", "beef bouillon cube",
        "vegetable bouillon", "bouillon granules",
    ]),

    # --- fruits --------------------------------------------------
    "ING_LEMON": ("lemon", "fruit", "", ["lemon", "lemons", "fresh lemon"]),
    "ING_LEMON_JUICE": ("lemon juice", "fruit", "", ["lemon juice", "fresh lemon juice", "juice of lemon", "bottled lemon juice"]),
    "ING_LEMON_ZEST": ("lemon zest", "fruit", "", ["lemon zest", "lemon peel", "lemon rind", "grated lemon peel", "grated lemon rind"]),
    "ING_LIME": ("lime", "fruit", "", ["lime", "limes"]),
    "ING_LIME_JUICE": ("lime juice", "fruit", "", ["lime juice", "fresh lime juice", "juice of lime"]),
    "ING_ORANGE": ("orange", "fruit", "", ["orange", "oranges", "navel orange", "mandarin oranges", "can mandarin oranges"]),
    "ING_ORANGE_JUICE": ("orange juice", "fruit", "", ["orange juice", "fresh orange juice", "oj"]),
    "ING_ORANGE_ZEST": ("orange zest", "fruit", "", ["orange zest", "orange peel", "grated orange peel", "orange rind"]),
    "ING_APPLE": ("apple", "fruit", "", [
        "apple", "apples", "granny smith apples", "granny smith apple", "gala apples",
        "honeycrisp apples", "cooking apples", "tart apples",
    ]),
    "ING_APPLESAUCE": ("applesauce", "fruit", "", ["applesauce", "apple sauce", "unsweetened applesauce"]),
    "ING_BANANA": ("banana", "fruit", "", ["banana", "bananas", "ripe bananas", "ripe banana", "mashed banana", "mashed bananas"]),
    "ING_STRAWBERRY": ("strawberry", "fruit", "", ["strawberry", "strawberries", "fresh strawberries", "frozen strawberries", "sliced strawberries"]),
    "ING_BLUEBERRY": ("blueberry", "fruit", "", ["blueberry", "blueberries", "fresh blueberries", "frozen blueberries"]),
    "ING_RASPBERRY": ("raspberry", "fruit", "", ["raspberry", "raspberries", "fresh raspberries", "frozen raspberries"]),
    "ING_CRANBERRY": ("cranberry", "fruit", "", ["cranberry", "cranberries", "fresh cranberries", "dried cranberries", "craisins"]),
    "ING_CRANBERRY_SAUCE": ("cranberry sauce", "fruit", "", ["cranberry sauce", "whole cranberry sauce", "jellied cranberry sauce", "can cranberry sauce"]),
    "ING_PEACH": ("peach", "fruit", "", ["peach", "peaches", "sliced peaches", "can peaches", "frozen peaches", "fresh peaches"]),
    "ING_PINEAPPLE": ("pineapple", "fruit", "", [
        "pineapple", "crushed pineapple", "can crushed pineapple", "pineapple chunks",
        "can pineapple", "pineapple tidbits", "pineapple slices",
    ]),
    "ING_PINEAPPLE_JUICE": ("pineapple juice", "fruit", "", ["pineapple juice"]),
    "ING_GRAPE": ("grape", "fruit", "", ["grape", "grapes", "seedless grapes", "red grapes", "green grapes"]),
    "ING_CHERRY": ("cherry", "fruit", "", ["cherry", "cherries", "maraschino cherries", "dried cherries", "frozen cherries"]),
    "ING_FRUIT_PIE_FILLING": ("fruit pie filling", "prepared", "", [
        "cherry pie filling", "can cherry pie filling", "apple pie filling", "blueberry pie filling",
        "peach pie filling", "lemon pie filling", "strawberry pie filling",
    ]),
    "ING_RAISIN": ("raisin", "fruit", "", ["raisin", "raisins", "golden raisins", "seedless raisins"]),
    "ING_DATE": ("date", "fruit", "", ["date", "dates", "pitted dates", "chopped dates", "medjool dates"]),
    "ING_COCONUT": ("coconut", "fruit", "", [
        "coconut", "shredded coconut", "flaked coconut", "sweetened coconut",
        "sweetened shredded coconut", "unsweetened coconut", "coconut flakes", "desiccated coconut",
    ]),
    "ING_COCONUT_MILK": ("coconut milk", "plant_milk", "", ["coconut milk", "can coconut milk", "light coconut milk"]),
    "ING_MANGO": ("mango", "fruit", "", ["mango", "mangoes", "mangos"]),
    "ING_KIWI": ("kiwi", "fruit", "", ["kiwi", "kiwifruit", "kiwis"]),

    # --- misc pantry --------------------------------------------
    "ING_BROWNIE_MIX": ("brownie mix", "grain", "gluten", ["brownie mix", "box brownie mix", "fudge brownie mix"]),
    "ING_MARSHMALLOW": ("marshmallow", "sweetener", "", [
        "marshmallow", "marshmallows", "miniature marshmallows", "mini marshmallows",
        "large marshmallows", "marshmallow creme", "marshmallow fluff",
    ]),
    "ING_WHIPPED_TOPPING": ("whipped topping", "dairy", "milk", [
        "whipped topping", "cool whip", "frozen whipped topping", "container cool whip",
        "carton cool whip", "tub cool whip", "whipped cream", "extra creamy cool whip",
    ]),
    "ING_PEANUT_BUTTER_CHIPS": ("peanut butter chips", "flavoring", "peanuts", ["peanut butter chips", "peanut butter morsels"]),
    "ING_BUTTERSCOTCH_CHIPS": ("butterscotch chips", "flavoring", "milk", ["butterscotch chips", "butterscotch morsels"]),
    "ING_TOFFEE_BITS": ("toffee bits", "flavoring", "milk", ["toffee bits", "heath bits", "english toffee bits"]),
    "ING_SPRINKLES": ("sprinkles", "flavoring", "", ["sprinkles", "jimmies", "candy sprinkles", "nonpareils"]),
    "ING_FOOD_COLORING": ("food coloring", "flavoring", "", ["food coloring", "food color", "gel food coloring"]),
    "ING_ICE": ("ice", "liquid", "", ["ice", "ice cubes", "crushed ice"]),
    "ING_COFFEE": ("coffee", "beverage", "", ["coffee", "brewed coffee", "strong coffee", "hot coffee", "cold coffee", "espresso"]),
    "ING_INSTANT_COFFEE": ("instant coffee", "beverage", "", ["instant coffee", "instant coffee granules"]),
    "ING_TEA": ("tea", "beverage", "", ["tea", "black tea", "tea bags", "brewed tea"]),
    "ING_COLA": ("cola", "beverage", "", ["cola", "coca cola", "coke", "pepsi", "soda pop"]),
    "ING_GINGER_ALE": ("ginger ale", "beverage", "", ["ginger ale", "ginger soda"]),
    "ING_LEMON_LIME_SODA": ("lemon-lime soda", "beverage", "", ["lemon lime soda", "lemon-lime soda", "sprite", "7-up", "7 up", "sierra mist"]),
    "ING_CLUB_SODA": ("club soda", "beverage", "", ["club soda", "soda water", "seltzer", "sparkling water", "carbonated water"]),
    "ING_BROTH_TOMATO_JUICE": ("tomato juice", "beverage", "", ["tomato juice", "v8 juice", "vegetable juice"]),
    "ING_CHOW_MEIN_NOODLES": ("chow mein noodles", "grain", "gluten", ["chow mein noodles", "crispy chow mein noodles"]),
    "ING_SESAME_TAHINI": ("tahini", "condiment", "sesame", ["tahini", "sesame paste", "tahini paste"]),
    "ING_CURRY_PASTE": ("curry paste", "condiment", "", ["curry paste", "red curry paste", "green curry paste", "thai curry paste"]),
    "ING_GINGER_GARLIC": ("ginger garlic paste", "condiment", "", ["ginger garlic paste"]),

    # --- packaged seasoning and soup mixes -----------------------
    "ING_ONION_SOUP_MIX": ("dry onion soup mix", "prepared", "", [
        "onion soup mix", "dry onion soup mix", "dried onion soup mix", "envelope onion soup mix",
        "lipton onion soup mix", "pkg onion soup mix", "onion soup",
    ]),
    "ING_TACO_SEASONING": ("taco seasoning mix", "seasoning", "", [
        "taco seasoning", "taco seasoning mix", "pkg taco seasoning", "envelope taco seasoning",
    ]),
    "ING_RANCH_MIX": ("ranch dressing mix", "prepared", "milk", [
        "ranch dressing mix", "ranch mix", "dry ranch dressing mix", "hidden valley ranch mix",
        "ranch salad dressing mix",
    ]),
    "ING_GRAVY_MIX": ("brown gravy mix", "prepared", "", [
        "gravy mix", "brown gravy mix", "pkg gravy mix",
    ]),
    # Au jus is a thin meat-drippings-based sauce, not brown gravy - different
    # flavor base and consistency, so it gets its own canonical.
    "ING_AU_JUS_MIX": ("au jus mix", "prepared", "", [
        "au jus mix", "au jus gravy mix", "pkg au jus mix", "au jus seasoning mix",
    ]),
    "ING_CHEESE_SOUP": ("condensed cheddar cheese soup", "prepared", "milk", [
        "cheddar cheese soup", "can cheddar cheese soup", "cheese soup", "nacho cheese soup",
        "fiesta nacho cheese soup", "condensed cheddar cheese soup",
    ]),
    "ING_ITALIAN_DRESSING": ("italian dressing", "condiment", "", [
        "italian dressing", "italian salad dressing", "zesty italian dressing",
        "italian dressing mix", "dry italian dressing mix",
    ]),
    "ING_RANCH_DRESSING": ("ranch dressing", "condiment", "eggs;milk", ["ranch dressing", "prepared ranch dressing"]),

    # --- more produce -------------------------------------------
    "ING_RHUBARB": ("rhubarb", "vegetable", "", ["rhubarb", "diced rhubarb", "frozen rhubarb"]),
    "ING_LIMA_BEANS": ("lima beans", "protein", "", ["lima beans", "baby lima beans", "butter beans", "frozen lima beans"]),
    "ING_SQUASH": ("squash", "vegetable", "", ["squash", "acorn squash", "winter squash"]),
    "ING_SPAGHETTI_SQUASH": ("spaghetti squash", "vegetable", "", ["spaghetti squash"]),
    "ING_PEAR": ("pear", "fruit", "", ["pear", "pears", "bartlett pears", "bosc pears", "canned pears"]),
    "ING_ARTICHOKE": ("artichoke heart", "vegetable", "", [
        "artichoke", "artichokes", "artichoke heart", "artichoke hearts", "can artichoke hearts",
        "marinated artichoke hearts", "quartered artichoke hearts",
    ]),
    "ING_FENNEL": ("fennel", "vegetable", "", ["fennel", "fennel bulb", "fennel bulbs"]),
    "ING_OKRA": ("okra", "vegetable", "", ["okra", "frozen okra", "sliced okra"]),
    "ING_BRUSSELS_SPROUTS": ("brussels sprouts", "vegetable", "", ["brussels sprouts", "brussel sprouts"]),
    "ING_BEET": ("beet", "vegetable", "", ["beet", "beets", "can beets", "canned beets"]),
    "ING_TURNIP": ("turnip", "vegetable", "", ["turnip", "turnips"]),
    "ING_PARSNIP": ("parsnip", "vegetable", "", ["parsnip", "parsnips"]),
    "ING_RADISH": ("radish", "vegetable", "", ["radish", "radishes"]),
    "ING_COLLARD": ("collard greens", "vegetable", "", ["collard greens", "collards", "mustard greens", "turnip greens"]),
    "ING_KALE": ("kale", "vegetable", "", ["kale", "chopped kale", "baby kale"]),
    "ING_CANTALOUPE": ("cantaloupe", "fruit", "", ["cantaloupe", "muskmelon"]),
    "ING_WATERMELON": ("watermelon", "fruit", "", ["watermelon"]),
    "ING_APRICOT": ("apricot", "fruit", "", ["apricot", "apricots", "dried apricots", "canned apricots"]),
    "ING_PLUM": ("plum", "fruit", "", ["plum", "plums"]),
    "ING_FIG": ("fig", "fruit", "", ["fig", "figs", "dried figs"]),
    "ING_PROD_TOMATILLO": ("tomatillo", "vegetable", "", ["tomatillo", "tomatillos"]),
    "ING_RED_CABBAGE": ("red cabbage", "vegetable", "", ["red cabbage", "purple cabbage"]),

    # --- more pantry / baking ----------------------------------
    "ING_TOMATO_PUREE": ("tomato puree", "vegetable", "", ["tomato puree", "can tomato puree", "strained tomatoes", "tomato passata"]),
    "ING_ICE_CREAM": ("vanilla ice cream", "dairy", "milk", [
        "ice cream", "vanilla ice cream", "chocolate ice cream", "softened ice cream",
    ]),
    "ING_BLUE_CHEESE": ("blue cheese", "dairy", "milk", ["blue cheese", "bleu cheese", "gorgonzola", "gorgonzola cheese", "blue cheese crumbles"]),
    "ING_PROVOLONE": ("provolone cheese", "dairy", "milk", ["provolone", "provolone cheese"]),
    "ING_MASCARPONE": ("mascarpone", "dairy", "milk", ["mascarpone", "mascarpone cheese"]),
    "ING_VANILLA_WAFER": ("vanilla wafers", "grain", "gluten", ["vanilla wafers", "nilla wafers", "crushed vanilla wafers"]),
    "ING_LADYFINGERS": ("ladyfingers", "grain", "gluten;eggs", ["ladyfingers", "lady fingers"]),
    "ING_APPLE_JUICE": ("apple juice", "beverage", "", ["apple juice", "apple cider", "unfiltered apple juice"]),
    "ING_LEMONADE": ("lemonade concentrate", "beverage", "", [
        "lemonade", "lemonade concentrate", "frozen lemonade concentrate", "pink lemonade concentrate",
    ]),
    "ING_LIMEADE": ("limeade concentrate", "beverage", "", ["limeade", "limeade concentrate", "frozen limeade concentrate"]),
    "ING_ORANGE_JUICE_CONC": ("orange juice concentrate", "beverage", "", ["orange juice concentrate", "frozen orange juice concentrate"]),
    "ING_GRAPE_JUICE": ("grape juice", "beverage", "", ["grape juice", "white grape juice"]),
    "ING_CRANBERRY_JUICE": ("cranberry juice", "beverage", "", ["cranberry juice", "cranberry juice cocktail"]),
    "ING_BOURBON": ("bourbon", "beverage", "", ["bourbon", "whiskey", "whisky"]),
    "ING_BRANDY": ("brandy", "beverage", "", ["brandy", "cognac"]),
    "ING_KAHLUA": ("coffee liqueur", "beverage", "", ["coffee liqueur", "kahlua"]),
    "ING_GRAND_MARNIER": ("orange liqueur", "beverage", "", ["orange liqueur", "grand marnier", "triple sec", "cointreau"]),
    "ING_WINE_COOKING": ("cooking wine", "beverage", "", ["cooking wine", "cooking sherry"]),
    "ING_CARAWAY": ("caraway seed", "seasoning", "", ["caraway seed", "caraway seeds", "caraway"]),
    "ING_MUSTARD_SEED": ("mustard seed", "seasoning", "", ["mustard seed", "mustard seeds", "yellow mustard seed"]),
    "ING_DILL_SEED": ("dill seed", "seasoning", "", ["dill seed", "dill seeds"]),
    "ING_ANISE": ("anise", "seasoning", "", ["anise", "anise seed", "star anise"]),
    "ING_SAFFRON": ("saffron", "seasoning", "", ["saffron", "saffron threads"]),
    "ING_JERK_SEASONING": ("jerk seasoning", "seasoning", "", ["jerk seasoning", "jamaican jerk seasoning"]),
    "ING_CAJUN_SEASONING": ("cajun seasoning", "seasoning", "", ["cajun seasoning", "creole seasoning", "cajun spice"]),
    "ING_OLD_BAY": ("old bay seasoning", "seasoning", "", ["old bay", "old bay seasoning"]),
    "ING_CHINESE_FIVE_SPICE": ("five spice powder", "seasoning", "", ["five spice powder", "chinese five spice", "5 spice powder"]),
    "ING_PUMPKIN_PIE_SPICE": ("pumpkin pie spice", "seasoning", "", ["pumpkin pie spice", "pumpkin spice"]),
    "ING_APPLE_PIE_SPICE": ("apple pie spice", "seasoning", "", ["apple pie spice"]),
    "ING_LEMON_PEPPER": ("lemon pepper seasoning", "seasoning", "", ["lemon pepper", "lemon pepper seasoning"]),
    "ING_MEAT_TENDERIZER": ("meat tenderizer", "seasoning", "", ["meat tenderizer"]),
    "ING_MSG": ("msg", "seasoning", "", ["msg", "accent seasoning", "monosodium glutamate"]),
    "ING_LIQUID_SMOKE": ("liquid smoke", "condiment", "", ["liquid smoke"]),
    "ING_KITCHEN_BOUQUET": ("browning sauce", "condiment", "", ["browning sauce", "kitchen bouquet", "gravy master"]),
    "ING_ROTEL": ("diced tomatoes and green chilies", "vegetable", "", ["rotel", "ro-tel", "can rotel", "diced tomatoes and green chilies", "diced tomatoes with green chilies"]),
    "ING_ENCHILADA_SAUCE": ("enchilada sauce", "condiment", "", ["enchilada sauce", "red enchilada sauce", "can enchilada sauce"]),
    "ING_TACO_SAUCE": ("taco sauce", "condiment", "", ["taco sauce"]),
    "ING_HOISIN": ("hoisin sauce", "condiment", "soy;gluten", ["hoisin sauce", "hoisin"]),
    "ING_STEAK_SAUCE": ("steak sauce", "condiment", "", ["steak sauce", "a1 sauce", "a.1. sauce", "a-1 sauce"]),
    "ING_SWEET_CHILI_SAUCE": ("sweet chili sauce", "condiment", "", ["sweet chili sauce", "thai sweet chili sauce"]),
    "ING_APPLE_BUTTER": ("apple butter", "condiment", "", ["apple butter"]),
    "ING_PEANUT_SAUCE": ("peanut sauce", "condiment", "peanuts", ["peanut sauce", "thai peanut sauce"]),
    "ING_COCONUT_CREAM": ("cream of coconut", "plant_milk", "", ["cream of coconut", "coconut cream", "can cream of coconut"]),
    "ING_PRETZEL": ("pretzel", "grain", "gluten", ["pretzel", "pretzels", "pretzel sticks", "crushed pretzels"]),
    "ING_POTATO_CHIP": ("potato chips", "grain", "", ["potato chips", "crushed potato chips", "potato chip"]),
    "ING_WONTON_WRAPPER": ("wonton wrapper", "grain", "gluten;eggs", ["wonton wrapper", "wonton wrappers", "won ton wrappers", "egg roll wrappers"]),
    "ING_PIZZA_CRUST": ("pizza crust", "grain", "gluten", ["pizza crust", "pizza dough", "prepared pizza crust", "refrigerated pizza dough"]),
    "ING_BISCUIT_DOUGH": ("refrigerated biscuits", "grain", "gluten", ["refrigerated biscuits", "can biscuits", "canned biscuits", "biscuit dough"]),
    "ING_CORN_BREAD_MIX": ("corn muffin mix", "grain", "gluten", ["corn muffin mix", "cornbread mix", "jiffy corn muffin mix"]),
    "ING_ANGEL_FOOD_CAKE": ("angel food cake", "grain", "gluten;eggs", ["angel food cake", "angel food cake mix", "prepared angel food cake"]),
    "ING_POUND_CAKE": ("pound cake", "grain", "gluten;eggs;milk", ["pound cake", "frozen pound cake"]),
    "ING_COOKIE_DOUGH": ("refrigerated cookie dough", "grain", "gluten;eggs", ["cookie dough", "refrigerated cookie dough", "sugar cookie dough"]),
    "ING_HASH_BROWN": ("hash brown potatoes", "vegetable", "", ["hash browns", "hash brown potatoes", "frozen hash browns", "shredded hash browns", "diced hash browns"]),
    "ING_TATER_TOTS": ("tater tots", "vegetable", "", ["tater tots", "potato tots"]),
    "ING_FRENCH_FRIED_ONIONS": ("french fried onions", "vegetable", "gluten", ["french fried onions", "can french fried onions", "french's fried onions"]),
    "ING_CHOCOLATE_SYRUP": ("chocolate syrup", "sweetener", "", ["chocolate syrup", "hershey's syrup", "chocolate sauce"]),
    "ING_CARAMEL": ("caramel", "sweetener", "milk", ["caramel", "caramels", "caramel sauce", "caramel topping", "dulce de leche"]),
    "ING_BUTTERSCOTCH_TOPPING": ("butterscotch topping", "sweetener", "milk", ["butterscotch topping", "butterscotch sauce"]),
    "ING_SUGAR_SUBSTITUTE": ("sugar substitute", "sweetener", "", ["sugar substitute", "splenda", "stevia", "sweetener", "artificial sweetener", "equal", "sweet n low"]),
    "ING_ROSE_WATER": ("rose water", "flavoring", "", ["rose water", "rosewater"]),
    "ING_ORANGE_BLOSSOM": ("orange blossom water", "flavoring", "", ["orange blossom water"]),
    "ING_MINT_EXTRACT": ("mint extract", "flavoring", "", ["mint extract", "peppermint extract"]),
    "ING_RUM_EXTRACT": ("rum extract", "flavoring", "", ["rum extract"]),
    "ING_COCONUT_EXTRACT": ("coconut extract", "flavoring", "", ["coconut extract"]),
    "ING_MAPLE_EXTRACT": ("maple extract", "flavoring", "", ["maple extract", "maple flavoring"]),

    # --- round 3: clear items from the 5,000-row review sweep ----
    "ING_SAUERKRAUT": ("sauerkraut", "vegetable", "", ["sauerkraut", "can sauerkraut", "bag sauerkraut"]),
    "ING_SUN_DRIED_TOMATO": ("sun-dried tomato", "vegetable", "", ["sun dried tomatoes", "sun-dried tomatoes", "sundried tomatoes", "julienned sun-dried tomatoes"]),
    "ING_ROASTED_RED_PEPPER": ("roasted red pepper", "vegetable", "", ["roasted red pepper", "roasted red peppers", "jar roasted red peppers", "fire roasted red peppers"]),
    "ING_CHILI_PEPPER": ("chili pepper", "vegetable", "", ["chili pepper", "chile pepper", "hot pepper", "thai chili", "serrano pepper", "serrano", "poblano pepper", "poblano", "anaheim pepper"]),
    "ING_HOMINY": ("hominy", "grain", "", ["hominy", "can hominy", "white hominy", "golden hominy"]),
    "ING_SCALLOP": ("scallop", "protein", "molluscs", ["scallop", "scallops", "sea scallops", "bay scallops"]),
    "ING_CLAM": ("clam", "protein", "molluscs", ["clam", "clams", "can clams", "minced clams", "chopped clams", "littleneck clams"]),
    "ING_CLAM_JUICE": ("clam juice", "prepared", "fish", ["clam juice", "bottled clam juice"]),
    "ING_MUSSEL": ("mussel", "protein", "molluscs", ["mussel", "mussels"]),
    "ING_OYSTER": ("oyster", "protein", "molluscs", ["oyster", "oysters", "can oysters", "shucked oysters"]),
    "ING_LOBSTER": ("lobster", "protein", "crustaceans", ["lobster", "lobster meat", "lobster tail", "lobster tails"]),
    "ING_PANCETTA": ("pancetta", "protein", "", ["pancetta"]),
    "ING_CORNED_BEEF": ("corned beef", "protein", "", ["corned beef", "corned beef brisket", "can corned beef"]),
    "ING_HOT_DOG": ("hot dog", "protein", "", ["hot dog", "hot dogs", "frankfurters", "wieners", "franks"]),
    "ING_GRUYERE": ("gruyere cheese", "dairy", "milk", ["gruyere", "gruyere cheese"]),
    "ING_QUESO_FRESCO": ("queso fresco", "dairy", "milk", ["queso fresco", "cotija cheese", "cotija"]),
    "ING_HALF_AND_HALF": ("half and half", "dairy", "milk", ["half and half", "half-and-half", "half and half cream", "half-and-half cream"]),
    "ING_SOUR_MILK": ("sour milk", "dairy", "milk", ["sour milk", "soured milk"]),
    "ING_ALMOND_MILK": ("almond milk", "plant_milk", "tree_nuts", ["almond milk", "unsweetened almond milk"]),
    "ING_SOY_MILK": ("soy milk", "plant_milk", "soy", ["soy milk", "soymilk"]),
    "ING_OAT_MILK": ("oat milk", "plant_milk", "gluten_candidate", ["oat milk", "oatmilk"]),
    "ING_EGG_SUBSTITUTE": ("egg substitute", "protein", "", ["egg substitute", "egg beaters", "liquid egg substitute", "egg replacer"]),
    "ING_ALMOND_FLOUR": ("almond flour", "grain", "tree_nuts", ["almond flour", "almond meal"]),
    "ING_COCONUT_FLOUR": ("coconut flour", "grain", "", ["coconut flour"]),
    "ING_ORZO": ("orzo", "grain", "gluten", ["orzo", "orzo pasta"]),
    "ING_GNOCCHI": ("gnocchi", "grain", "gluten", ["gnocchi", "potato gnocchi"]),
    "ING_RAMEN": ("ramen noodles", "grain", "gluten", ["ramen noodles", "ramen", "instant ramen", "top ramen"]),
    "ING_RICE_NOODLES": ("rice noodles", "grain", "", ["rice noodles", "rice vermicelli", "rice stick noodles"]),
    "ING_SANDWICH_COOKIE": ("chocolate sandwich cookies", "grain", "gluten", ["oreo cookies", "oreos", "chocolate sandwich cookies", "oreo cookie crumbs"]),
    "ING_MACE": ("mace", "seasoning", "", ["mace", "ground mace"]),
    "ING_GARAM_MASALA": ("garam masala", "seasoning", "", ["garam masala"]),
    "ING_HERBES_DE_PROVENCE": ("herbes de provence", "seasoning", "", ["herbes de provence"]),
    "ING_ZAATAR": ("za'atar", "seasoning", "sesame", ["za'atar", "zaatar", "zatar"]),
    "ING_SUMAC": ("sumac", "seasoning", "", ["sumac", "ground sumac"]),
    "ING_ROTEL": ("diced tomatoes and green chilies", "vegetable", "", [
        "ro-tel tomatoes", "rotel tomatoes", "ro-tel", "rotel", "can ro-tel", "can rotel",
        "diced tomatoes and green chilies", "diced tomatoes with green chilies",
        "tomatoes and green chilies",
    ]),
    "ING_AMARETTO": ("amaretto", "beverage", "tree_nuts", ["amaretto"]),
    "ING_KIRSCH": ("kirsch", "beverage", "", ["kirsch", "cherry brandy"]),
    "ING_SAKE": ("sake", "beverage", "", ["sake", "mirin", "rice wine"]),
    "ING_FRUIT_COCKTAIL": ("fruit cocktail", "fruit", "", ["fruit cocktail", "can fruit cocktail"]),
    "ING_INSTANT_MASHED_POTATO": ("instant mashed potato flakes", "vegetable", "", [
        "instant mashed potatoes", "mashed potato flakes", "potato flakes", "instant potato flakes",
        "instant potatoes", "instant mashed potato flakes",
    ]),
    "ING_MASHED_POTATOES": ("mashed potatoes", "vegetable", "", ["mashed potatoes", "leftover mashed potatoes"]),
    "ING_FROZEN_BREAD_DOUGH": ("frozen bread dough", "grain", "gluten", ["frozen bread dough", "bread dough", "loaf frozen bread dough"]),
}
# fmt: on

# --- human-reviewed additions -------------------------------------------
# Decisions from the unmapped_high_freq review packet (first 180-row batch).
# Kept separate from the hand-curated TABLE above so the provenance of each
# entry - "I wrote this" vs "a reviewer decided this from the sample data" -
# stays visible. `meat` / `fruit` / `berries` / `broth` / `soup` are
# deliberately generic: the source recipes genuinely do not say which meat,
# fruit, etc. Per docs/cleaning-decisions.md these must not be used for
# hard-constraint (allergen/diet) filtering or product-level FairPrice
# matching - only for presence/quantity/recipe-completeness purposes.
# fmt: off
REVIEWED_ADDITIONS: dict[str, tuple[str, str, str, list[str]]] = {
    "ING_MEAT": ("meat", "protein", "", ["meat"]),
    "ING_DARK_CHOCOLATE": ("dark chocolate", "flavoring", "milk", ["dark chocolate"]),
    "ING_GRAPESEED_OIL": ("grapeseed oil", "fat", "", ["grapeseed oil"]),
    "ING_BLACK_EYED_PEAS": ("black-eyed peas", "protein", "", ["black-eyed peas", "black eyed peas"]),
    "ING_POWDERED_MILK": ("powdered milk", "dairy", "milk", ["dry milk", "powdered milk"]),
    "ING_ONION_SALT": ("onion salt", "seasoning", "", ["onion salt"]),
    "ING_SHERRY_VINEGAR": ("sherry vinegar", "condiment", "", ["sherry vinegar"]),
    "ING_LIME_ZEST": ("lime zest", "fruit", "", ["lime zest"]),
    "ING_ARUGULA": ("arugula", "vegetable", "", ["arugula"]),
    "ING_LEMONGRASS": ("lemongrass", "herb", "", ["lemongrass"]),
    "ING_CONDENSED_CREAM_OF_POTATO_SOUP": ("condensed cream of potato soup", "prepared", "", ["cream of potato soup", "condensed cream of potato soup"]),
    "ING_BUTTER_FLAVORING": ("butter flavoring", "flavoring", "", ["butter flavoring"]),
    "ING_ALUM": ("alum", "seasoning", "", ["alum"]),
    "ING_PITA_BREAD": ("pita bread", "grain", "gluten", ["pita breads", "pita bread"]),
    "ING_COCONUT_SUGAR": ("coconut sugar", "sweetener", "", ["coconut sugar"]),
    "ING_FRUIT": ("fruit", "fruit", "", ["fruit"]),
    "ING_PRUNE": ("prune", "fruit", "", ["prunes", "prune"]),
    "ING_BERRIES": ("berries", "fruit", "", ["berries"]),
    "ING_OAT_FLOUR": ("oat flour", "grain", "gluten_candidate", ["oat flour"]),
    "ING_SUNFLOWER_OIL": ("sunflower oil", "fat", "", ["sunflower oil"]),
    "ING_PROCESSED_CHEESE_SAUCE": ("processed cheese sauce", "dairy", "milk", ["cheez whiz", "cheese whiz", "processed cheese sauce"]),
    "ING_SNOW_PEAS": ("snow peas", "vegetable", "", ["snow peas"]),
    "ING_PIZZA_SAUCE": ("pizza sauce", "condiment", "", ["pizza sauce"]),
    "ING_SOUP": ("soup", "prepared", "", ["soup"]),
    "ING_SYRUP": ("syrup", "sweetener", "", ["syrup"]),
    "ING_BROTH": ("broth", "prepared", "", ["broth"]),
    "ING_MACADAMIA_NUT": ("macadamia nut", "protein", "tree_nuts", ["macadamia nuts", "macadamia nut"]),
    "ING_TEQUILA": ("tequila", "beverage", "", ["tequila"]),
    "ING_MEATBALL": ("meatball", "protein", "", ["meatballs", "meatball"]),
    "ING_BULGUR": ("bulgur", "grain", "gluten", ["bulgur"]),
    "ING_RABBIT": ("rabbit", "protein", "", ["rabbits", "rabbit"]),
    "ING_OAT_BRAN": ("oat bran", "grain", "gluten_candidate", ["oat bran"]),
    "ING_BAGUETTE": ("baguette", "grain", "gluten", ["baguette"]),
    "ING_HABANERO_PEPPER": ("habanero pepper", "vegetable", "", ["habanero pepper"]),
    "ING_POMEGRANATE_SEEDS": ("pomegranate seeds", "fruit", "", ["pomegranate seeds"]),
    "ING_RUTABAGA": ("rutabaga", "vegetable", "", ["rutabaga"]),
    "ING_APRICOT_NECTAR": ("apricot nectar", "beverage", "", ["apricot nectar"]),
    "ING_POMEGRANATE_MOLASSES": ("pomegranate molasses", "condiment", "", ["pomegranate molasses"]),
    "ING_ALMOND_PASTE": ("almond paste", "prepared", "tree_nuts", ["almond paste"]),
}

# alias_text -> target canonical_name (existing in TABLE or in REVIEWED_ADDITIONS)
REVIEWED_ALIASES: list[tuple[str, str]] = [
    ("red pepper", "cayenne pepper"),
    ("pkg. cream cheese", "cream cheese"),
    ("fryer", "chicken"),
    ("sweet red pepper", "bell pepper"),
    ("vegetable cooking spray", "cooking spray"),
    ("1 lemon", "lemon"),
    ("fine sea salt", "salt"),
    ("almond flavoring", "almond extract"),
    ("kosher salt and black pepper", "salt and pepper"),
    ("lime wedges", "lime"),
    ("mashed sweet potatoes", "sweet potato"),
    ("biscuits", "refrigerated biscuits"),
    ("strips bacon", "bacon"),
    ("green food coloring", "food coloring"),
    ("thyme sprigs", "thyme"),
    ("baby spinach leaves", "spinach"),
    ("t butter", "butter"),
    ("chocolate", "baking chocolate"),
    ("sage leaves", "sage"),
    ("pineapple with juice", "pineapple"),
    ("wine vinegar", "vinegar"),
    ("dried oregano leaves", "oregano"),
    ("strawberry jello", "gelatin"),
    ("dry breadcrumbs", "bread crumbs"),
    ("lettuce leaves", "lettuce"),
    ("knox gelatine", "gelatin"),
    ("dried parsley flakes", "parsley"),
    ("dried thyme leaves", "thyme"),
    ("lemon jello", "gelatin"),
    ("eagle brand sweetened condensed milk", "sweetened condensed milk"),
    ("chocolate pudding", "instant pudding mix"),
    ("marshmallow cream", "marshmallow"),
    ("bread cubes", "bread"),
    ("red food coloring", "food coloring"),
    ("strawberry jell-o", "gelatin"),
    ("beef bouillon cubes", "bouillon cube"),
    ("fully ham", "ham"),
    ("basil leaf", "basil"),
    ("caramel ice cream topping", "caramel"),
    ("black peppercorns", "peppercorn"),
    ("white karo syrup", "corn syrup"),
    ("canned milk", "evaporated milk"),
    ("sweet milk", "milk"),
    ("soda crackers", "cracker crumbs"),
    ("italian tomatoes", "tomato"),
    ("pesto sauce", "pesto"),
    ("coffee granules", "instant coffee"),
    ("crisco oil", "vegetable oil"),
    ("hard- eggs", "egg"),
    ("white corn syrup", "corn syrup"),
    ("white syrup", "corn syrup"),
    ("oregano leaves", "oregano"),
    ("accent", "msg"),
    ("soup can water", "water"),
    ("hot sausage", "sausage"),
    ("celery soup", "condensed cream of celery soup"),
    ("dream whip", "whipped topping"),
    ("tarragon leaves", "tarragon"),
    ("dry milk powder", "powdered milk"),
    ("unsweetened pineapple juice", "pineapple juice"),
    ("crackers", "cracker crumbs"),
    ("lemon wedges", "lemon"),
    ("roasted peanuts", "peanut"),
    ("yellow pepper", "bell pepper"),
    ("lemon flavoring", "lemon extract"),
    ("penne pasta", "pasta"),
    ("veg-all", "mixed vegetables"),
    ("green tomatoes", "tomato"),
    ("fine cracker crumbs", "cracker crumbs"),
    ("bacon bits", "bacon"),
    ("frying chicken", "chicken"),
    ("golden raisin", "raisin"),
    ("dijon-style mustard", "dijon mustard"),
    ("french-style green beans", "green beans"),
    ("corn flake crumbs", "corn flakes"),
    ("boiled eggs", "egg"),
    ("hamburg", "ground beef"),
    ("quick oatmeal", "oats"),
    ("vegetable oil for frying", "vegetable oil"),
    ("candied cherries", "cherry"),
    ("candied pineapple", "pineapple"),
    ("devil's food cake mix", "cake mix"),
    ("oil for frying", "vegetable oil"),
    ("pie filling", "fruit pie filling"),
    ("broken pecans", "pecan"),
    ("chocolate bits", "chocolate chips"),
    ("soup can milk", "milk"),
    ("soya sauce", "soy sauce"),
    ("1/2 lemon", "lemon"),
    ("powdered ginger", "ginger"),
    ("allspice berries", "allspice"),
    ("mixed berries", "berries"),
    ("raw rice", "rice"),
    ("duncan hines butter cake mix", "cake mix"),
    ("angel flake coconut", "coconut"),
    ("italian seasoned breadcrumbs", "bread crumbs"),
    ("parmigiano-reggiano cheese", "parmesan cheese"),
    ("hot tap water", "water"),
    ("pkg. chocolate chips", "chocolate chips"),
    ("pkg. strawberry jello", "gelatin"),
    ("sea salt and black pepper", "salt and pepper"),
    ("cream of chicken", "condensed cream of chicken soup"),
    ("scalded milk", "milk"),
    ("loosely flat-leaf parsley leaves", "parsley"),
    ("hot milk", "milk"),
    ("beef chuck roast", "beef"),
    ("crusty bread", "bread"),
    ("clove", "cloves"),
    ("dark karo syrup", "corn syrup"),
    ("pork loin roast", "pork"),
    ("season salt", "seasoned salt"),
    ("condensed beef broth", "beef broth"),
    ("lemon cake mix", "cake mix"),
    ("stew meat", "beef"),
    ("parsley leaves", "parsley"),
    ("lemon jell-o", "gelatin"),
    ("t salt", "salt"),
    ("panko breadcrumbs", "bread crumbs"),
]

# --- round 5: priority-queue driven fixes (300k scale) -------------------
# From ingredient_priority_queue.csv, ranked by how many whole recipes each
# decision unlocks - not a human-reviewed spreadsheet like the batches above,
# but auto-applied because each case is unambiguous on its own (a plain
# spelling/form variant of something already in the table, or a clearly new,
# specific ingredient). Genuinely ambiguous ones ("pecans or walnuts") are
# left for the ambiguous_or review sheet, not decided here.
REVIEWED_ADDITIONS_R5: dict[str, tuple[str, str, str, list[str]]] = {
    "ING_VANILLA_BEAN": ("vanilla bean", "flavoring", "", ["vanilla bean", "vanilla beans", "vanilla pod"]),
    "ING_SALAD_DRESSING": ("salad dressing", "condiment", "", ["salad dressing", "bottled salad dressing"]),
    "ING_BLACKBERRY": ("blackberry", "fruit", "", ["blackberries", "blackberry", "fresh blackberries"]),
    "ING_DRIED_ONION_FLAKES": ("dried onion flakes", "vegetable", "", [
        "dried onion", "dried minced onion", "onion flakes", "instant onion flakes", "minced dried onion",
    ]),
    "ING_CURRANT": ("currant", "fruit", "", ["currants", "currant", "dried currants", "zante currants"]),
    "ING_XANTHAN_GUM": ("xanthan gum", "prepared", "", ["xanthan gum"]),
    "ING_MILK_CHOCOLATE": ("milk chocolate", "flavoring", "milk", ["milk chocolate", "milk chocolate bar"]),
    "ING_CRYSTALLIZED_GINGER": ("crystallized ginger", "seasoning", "", [
        "crystallized ginger", "candied ginger",
    ]),
    "ING_RYE_FLOUR": ("rye flour", "grain", "gluten", ["rye flour", "dark rye flour", "medium rye flour"]),
    "ING_WILD_RICE": ("wild rice", "grain", "", ["wild rice"]),
    "ING_DRINK_MIX_POWDER": ("powdered orange drink mix", "beverage", "", ["tang", "orange drink mix"]),
    "ING_ESPRESSO_POWDER": ("espresso powder", "flavoring", "", [
        "espresso powder", "instant espresso powder", "instant espresso",
    ]),
    "ING_ORANGE_EXTRACT": ("orange extract", "flavoring", "", ["orange extract"]),
    "ING_RICE_FLOUR": ("rice flour", "grain", "", ["rice flour", "sweet rice flour", "glutinous rice flour"]),
}

REVIEWED_ALIASES_R5: list[tuple[str, str]] = [
    ("sq. unsweetened chocolate", "baking chocolate"),
    ("raw peanuts", "peanut"),
    ("orange marmalade", "jam"),
    ("marmalade", "jam"),
    ("wheat pastry flour", "whole wheat flour"),
    ("whole wheat pastry flour", "whole wheat flour"),
    ("bisquick baking mix", "baking mix"),
    ("bisquick mix", "baking mix"),
    ("dark chocolate chips", "chocolate chips"),
    ("crisco shortening", "shortening"),
    ("splenda sugar substitute", "sugar substitute"),
    ("baked pie shell", "pie crust"),
    ("black walnuts", "walnut"),
    ("black walnut", "walnut"),
    ("dried dill weed", "dill"),
    ("white karo", "corn syrup"),
    ("karo", "corn syrup"),
    ("dairy sour cream", "sour cream"),
]
# fmt: on

HEADER = ["ingredient_id", "canonical_name", "alias", "food_group", "allergens"]


def build_rows() -> list[list[str]]:
    rows: list[list[str]] = []
    seen_alias: dict[str, str] = {}
    name_to_id: dict[str, str] = {}
    row_by_id: dict[str, list[str]] = {}

    def add_ingredient(ingredient_id, canonical_name, food_group, allergens, aliases):
        for alias in [canonical_name, *aliases]:
            key = alias.casefold().strip()
            if not key:
                continue
            if key in seen_alias and seen_alias[key] != ingredient_id:
                raise SystemExit(
                    f"alias {key!r} claimed by {seen_alias[key]} and {ingredient_id}"
                )
            if key in seen_alias:
                continue
            seen_alias[key] = ingredient_id
            rows.append([ingredient_id, canonical_name, key, food_group, allergens])
        name_to_id.setdefault(canonical_name.casefold(), ingredient_id)

    def add_aliases(aliases: list[tuple[str, str]], source_name: str) -> None:
        for alias_text, target_name in aliases:
            target_id = name_to_id.get(target_name.casefold())
            if target_id is None:
                raise SystemExit(
                    f"{source_name}: {alias_text!r} targets unknown canonical_name {target_name!r}"
                )
            key = alias_text.casefold().strip()
            if key in seen_alias and seen_alias[key] != target_id:
                raise SystemExit(
                    f"alias {key!r} claimed by {seen_alias[key]} and {source_name} -> {target_id}"
                )
            if key in seen_alias:
                continue
            seen_alias[key] = target_id
            canonical_name, food_group, allergens = next(
                (row[1], row[3], row[4]) for row in rows if row[0] == target_id
            )
            rows.append([target_id, canonical_name, key, food_group, allergens])

    for ingredient_id, (canonical_name, food_group, allergens, aliases) in TABLE.items():
        add_ingredient(ingredient_id, canonical_name, food_group, allergens, aliases)
    for ingredient_id, (canonical_name, food_group, allergens, aliases) in REVIEWED_ADDITIONS.items():
        add_ingredient(ingredient_id, canonical_name, food_group, allergens, aliases)
    add_aliases(REVIEWED_ALIASES, "REVIEWED_ALIASES")

    for ingredient_id, (canonical_name, food_group, allergens, aliases) in REVIEWED_ADDITIONS_R5.items():
        add_ingredient(ingredient_id, canonical_name, food_group, allergens, aliases)
    add_aliases(REVIEWED_ALIASES_R5, "REVIEWED_ALIASES_R5")
    return rows


def main() -> None:
    project_root = Path(__file__).resolve().parents[1]
    target = project_root / "config" / "ingredient_aliases.csv"
    rows = build_rows()
    with target.open("w", encoding="utf-8", newline="") as handle:
        writer = csv.writer(handle)
        writer.writerow(HEADER)
        writer.writerows(rows)
    canonical_count = len(TABLE) + len(REVIEWED_ADDITIONS) + len(REVIEWED_ADDITIONS_R5)
    print(f"wrote {len(rows)} alias rows for {canonical_count} canonical ingredients -> {target}")


if __name__ == "__main__":
    main()
