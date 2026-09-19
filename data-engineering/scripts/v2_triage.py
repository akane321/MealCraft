"""Cheap cuisine and course triage used only to pick release v2 candidates.

These labels choose which recipes go forward; every selected recipe is labelled
again during enrichment, with evidence, and the quotas are checked against that
final label. A rule here therefore only has to be right often enough to fill a
candidate pool, not to be a label.

Order matters: the first cuisine whose title words match wins; failing that, the
first whose signature ingredients match. Anything else is "american", which is
what most RecipeNLG home cooking is.
"""

from __future__ import annotations

import re

# (cuisine, title pattern, ingredient signature pattern or None)
CUISINE_RULES: list[tuple[str, str, str | None]] = [
    (
        "korean",
        r"korean|kimchi|bulgogi|bibimbap|gochujang|japchae|galbi|kalbi|tteok|kimbap|banchan|mandu",
        r"gochujang|gochugaru|kimchi|korean",
    ),
    (
        "japanese",
        r"japanese|teriyaki|sushi|miso|tempura|ramen|udon|soba|yakitori|katsu|donburi|okonomiyaki|gyoza"
        r"|onigiri|sukiyaki|shabu|tonkatsu|oyakodon|nori|edamame|wasabi|tamago|matcha",
        r"\bmirin\b|\bdashi\b|\bmiso\b|wasabi|bonito|\bnori\b|sushi rice|kombu|furikake",
    ),
    (
        "vietnamese",
        r"vietnamese|\bpho\b|banh mi|bun cha|bun bo|nuoc cham|goi cuon|com tam|saigon|hanoi",
        r"rice paper|nuoc mam",
    ),
    (
        "thai",
        r"\bthai\b|pad thai|tom yum|tom kha|green curry|red curry|yellow curry|massaman|panang|larb|som tam"
        r"|pad see ew|khao",
        r"lemon ?grass.*fish sauce|fish sauce.*lemon ?grass|thai basil|kaffir|galangal.*fish sauce|thai curry paste"
        r"|red curry paste|green curry paste",
    ),
    (
        "malaysian_singaporean",
        r"malaysian|malay\b|singapore|laksa|rendang|nasi lemak|char kway|hainanese|satay"
        r"|roti canai|mee goreng|kaya\b|teh tarik|penang|peranakan|nyonya|otak\b",
        r"belacan|candlenut|laksa|pandan",
    ),
    (
        "indonesian",
        r"indonesian|nasi goreng|gado|sambal|bali\b|javanese|soto\b|tempeh|rendang|opor|bakso",
        r"kecap manis|sambal oelek|tempeh",
    ),
    (
        "filipino",
        r"filipino|philippine|(?<!\ben )adobo(?! sofrito)|lumpia|pancit|sinigang|lechon|kare.kare|bibingka"
        r"|halo.halo|tinola|longganisa|ensaymada|arroz caldo",
        r"calamansi|bagoong|patis",
    ),
    (
        "chinese",
        r"chinese|szechuan|sichuan|kung pao|lo mein|chow mein|wonton|dim sum|char siu|mapo|hoisin|egg foo"
        r"|moo shu|general tso|sweet and sour|sweet & sour|fried rice|bok choy|cantonese|hunan|peking"
        r"|mandarin|chop suey|stir.?fry|potsticker|egg roll|spring roll|orange chicken|lemon chicken"
        r"|cashew chicken|beef and broccoli|mongolian|hot and sour|bao\b|dumpling",
        r"oyster sauce|hoisin|five.spice|star anise.*soy|shaoxing|rice wine.*soy|sesame oil.*soy sauce|bok choy"
        r"|szechuan|black bean sauce|water chestnut.*soy",
    ),
    (
        "indian",
        r"indian|curry|masala|tikka|tandoori|biryani|\bdal\b|dhal|paneer|korma|vindaloo|samosa|chutney"
        r"|naan|chapati|pakora|raita|aloo|gobi|chana|saag|palak|dosa|idli|kheer|lassi|rogan josh|pulao",
        r"garam masala|turmeric.*cumin|cumin.*turmeric|ghee|paneer|curry leaves|asafoetida|fenugreek|cardamom.*cumin",
    ),
    ("turkish", r"turkish|kofte|kofta|borek|pide\b|lahmacun|baklava|doner|imam bayildi|manti\b|ayran", None),
    (
        "north_african",
        r"moroccan|tagine|tajine|couscous|harissa|algerian|tunisian|egyptian|shakshuka|koshari"
        r"|chermoula|ras el hanout|b.?stilla",
        r"ras el hanout|harissa|preserved lemon",
    ),
    (
        "middle_eastern",
        r"middle eastern|lebanese|persian|iranian|syrian|israeli|arabic|hummus|falafel|tabbouleh"
        r"|tabouli|shawarma|baba gh|fattoush|kibbeh|kebab|kabob|pita\b|za.atar|mujadara|fatayer"
        r"|dolma|labneh|halloumi|maqluba|kabsa",
        r"tahini|sumac|za.atar|bulgur|pomegranate molasses|labneh",
    ),
    (
        "greek",
        r"greek|gyro|moussaka|spanakopita|tzatziki|souvlaki|pastitsio|avgolemono|dolmades|horiatiki"
        r"|mediterranean|feta\b",
        r"feta.*oregano|kalamata",
    ),
    (
        "italian",
        r"italian|lasagna|lasagne|spaghetti|risotto|parmigiana|parmesan chicken|marinara|pesto|minestrone"
        r"|ziti|manicotti|tiramisu|biscotti|fettuccine|fettucine|alfredo|gnocchi|carbonara|bolognese"
        r"|bruschetta|focaccia|calzone|stromboli|piccata|marsala|osso buco|panna cotta|cacciatore"
        r"|tortellini|ravioli|cannelloni|frittata|polenta|primavera|antipasto|pizza|penne|linguine|rigatoni",
        None,
    ),
    (
        "french",
        r"french(?! toast| fries| fried| bread| dressing| onion dip)|quiche|crepe|souffle|au gratin"
        r"|bourguignon|ratatouille|vichyssoise|creme brulee|bearnaise|coq au vin|cassoulet|bouillabaisse"
        r"|nicoise|gratin|madeleine|clafoutis|croque|tarte|provencal|dijon chicken|beurre|bechamel",
        None,
    ),
    (
        "spanish_portuguese",
        r"spanish|paella|gazpacho|sangria|tapas|chorizo|portuguese|romesco|churro|flan\b"
        r"|empanada|tortilla espanola|patatas bravas|piri.piri|bacalhau",
        None,
    ),
    (
        "german",
        r"german|sauerkraut|strudel|schnitzel|spaetzle|spatzle|bratwurst|sauerbraten|kuchen|pretzel"
        r"|black forest|stollen|rouladen|lebkuchen|bavarian|kartoffel",
        None,
    ),
    (
        "eastern_european",
        r"polish|pierogi|kielbasa|goulash|hungarian|stroganoff|russian|borscht|ukrainian"
        r"|czech|slovak|romanian|paprikash|blini|pelmeni|golabki|cabbage roll|kolache|babka",
        None,
    ),
    (
        "british_irish",
        r"english|british|irish|scottish|welsh|scone|shepherd|trifle|yorkshire|bangers|cornish"
        r"|colcannon|soda bread|toad in the hole|bubble and squeak|sticky toffee|crumpet|kedgeree"
        r"|cottage pie|fish and chips|wellington",
        None,
    ),
    (
        "scandinavian",
        r"swedish|norwegian|danish|finnish|scandinavian|lefse|lutefisk|aebleskiver|kringle"
        r"|gravlax|smorrebrod|krumkake|rosettes",
        None,
    ),
    (
        "caribbean",
        r"jamaican|caribbean|jerk\b(?!y)|cuban|puerto ric|haitian|trinidad|plantain|mofongo|callaloo|ackee",
        r"scotch bonnet|allspice.*thyme.*lime",
    ),
    (
        "latin_american",
        r"brazilian|peruvian|argentin|chilean|colombian|venezuelan|chimichurri|ceviche|arepa"
        r"|feijoada|pupusa|salvador|guatemal|lomo saltado|dulce de leche|tres leches|alfajor",
        None,
    ),
    (
        "mexican",
        r"mexican|enchilada|burrito|quesadilla|tamale|mole\b|pozole|chile relleno|chiles rellenos|carnitas"
        r"|tostada|chilaquiles|huevos|elote|horchata|salsa verde|pico de gallo|guacamole|sopapilla|fideo",
        r"tomatillo|masa harina|chipotle|poblano|epazote",
    ),
    ("tex_mex", r"taco|nacho|fajita|chili con|tex.mex|queso|taquito|chimichanga|frito", None),
    (
        "cajun_creole",
        r"cajun|creole|jambalaya|gumbo|etouffee|andouille|po.?boy|beignet|boudin|dirty rice|muffuletta",
        None,
    ),
    (
        "southern_us",
        r"southern|grits|hush ?pupp|collard|fried chicken|chicken fried|biscuits and gravy|cornbread"
        r"|hoppin|okra|pimento cheese|chess pie|pecan pie|sweet potato pie|banana pudding",
        None,
    ),
    (
        "african",
        r"african|ethiopian|nigerian|kenyan|ghanaian|senegal|jollof|injera|bobotie|peri.peri|suya|fufu"
        r"|egusi|berbere|bunny chow|chakalaka",
        r"berbere|egusi",
    ),
]
_COMPILED = [(c, re.compile(t, re.I), re.compile(i, re.I) if i else None) for c, t, i in CUISINE_RULES]

COURSE_RULES: list[tuple[str, str]] = [
    (
        "drink",
        r"punch|smoothie|lemonade|cocktail|\bshake\b|milkshake|\btea\b|coffee|cocoa|eggnog|cider|sangria"
        r"|margarita|daiquiri|lassi|horchata|\bdrink\b|beverage|juice|slush|frappe|latte|wassail",
    ),
    (
        "sauce_condiment",
        r"sauce|dressing|marinade|salsa|relish|chutney|\bjam\b|jelly|preserves|pickle|glaze|gravy"
        r"|seasoning|spice mix|rub\b|butter\b(?! chicken)|syrup|frosting|icing|vinaigrette|pesto"
        r"|mayonnaise|ketchup|mustard|condiment|curry paste|stock|broth(?! soup)",
    ),
    (
        "dessert",
        r"cake|cookie|brownie|fudge|candy|pudding|cobbler|crisp\b|crumble|pie(?!.*(pot|meat|chicken|beef"
        r"|shepherd|cottage|pork|tamale|pizza))|tart\b|cheesecake|ice cream|sorbet|mousse|custard|dessert"
        r"|truffle|toffee|brittle|bars?\b|squares?\b|parfait|trifle|meringue|cupcake|doughnut|donut"
        r"|baklava|tiramisu|flan|kheer|halo.halo|mochi|sweet|dumpling.*sweet|cannoli|eclair|macaroon"
        r"|praline|caramel|shortbread|biscotti|strudel|kuchen|panna cotta",
    ),
    (
        "baked_good",
        r"bread|muffin|biscuit|scone|\brolls?\b|bun\b|buns\b|loaf|focaccia|naan|chapati|roti\b|tortillas"
        r"|bagel|pretzel|croissant|brioche|challah|crackers?|pita\b|pastry",
    ),
    (
        "breakfast",
        r"pancake|waffle|omelet|omelette|french toast|granola|breakfast|oatmeal|porridge|frittata"
        r"|scrambled|eggs benedict|hash brown|congee|arroz caldo|crepe",
    ),
    (
        "soup",
        r"soup|chowder|bisque|gazpacho|borscht|pho\b|ramen|laksa|tom yum|tom kha|sinigang|consomme|pozole"
        r"|minestrone|gumbo|miso soup|dal\b|dhal",
    ),
    ("salad", r"salad|slaw|tabbouleh|tabouli|fattoush|som tam|gado.gado|raita"),
    (
        "snack_appetizer",
        r"\bdip\b|appetizer|hors d|canape|bites|nachos|chips|popcorn|snack|spread|deviled|wings"
        r"|crostini|bruschetta|spring roll|egg roll|samosa|pakora|lumpia|gyoza|potsticker|dumpling"
        r"|wonton|satay|meatballs?|trail mix|cheese ball|nuts\b|hummus|baba gh|guacamole",
    ),
    (
        "side",
        r"rice\b|pilaf|potato|potatoes|beans\b|vegetables|veggies|green beans|carrots|corn\b|squash|broccoli"
        r"|cauliflower|asparagus|spinach|cabbage|slaw|stuffing|dressing|mashed|roasted .*vegetables|au gratin"
        r"|scalloped|casserole of|side dish|fries|onion rings|coleslaw|succotash|polenta|couscous\b|noodles\b",
    ),
]
_COURSE = [(c, re.compile(p, re.I)) for c, p in COURSE_RULES]


def cuisine_of(title: str, ingredient_text: str) -> tuple[str, str]:
    """Return (cuisine, basis) where basis is "title", "ingredients" or "default"."""
    for cuisine, title_rx, _ in _COMPILED:
        if title_rx.search(title):
            return cuisine, "title"
    for cuisine, _, ingredient_rx in _COMPILED:
        if ingredient_rx and ingredient_rx.search(ingredient_text):
            return cuisine, "ingredients"
    return "american", "default"


def course_of(title: str) -> str:
    for course, rx in _COURSE:
        if rx.search(title):
            return course
    return "main"


if __name__ == "__main__":
    for title, ingredients, cuisine, course in [
        ("Kimchi Fried Rice", "kimchi, rice, egg", "korean", "side"),
        ("Chicken Teriyaki", "soy sauce, mirin, sugar", "japanese", "main"),
        ("Baked French Toast", "bread, eggs, milk", "american", "breakfast"),
        ("Grandma's Pound Cake", "flour, butter, sugar", "american", "dessert"),
        ("Beef Stir Fry", "beef, oyster sauce, soy sauce", "chinese", "main"),
        ("Hummus", "chickpeas, tahini, lemon", "middle_eastern", "snack_appetizer"),
        ("Stuffed Peppers", "beef, rice, garam masala, turmeric, cumin", "indian", "main"),
        ("Pad Thai", "rice noodles, fish sauce", "thai", "main"),
    ]:
        got = (cuisine_of(title, ingredients)[0], course_of(title))
        assert got == (cuisine, course), (title, got)
    print("triage self-check passed")
