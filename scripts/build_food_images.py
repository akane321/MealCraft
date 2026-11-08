"""Rebuild frontend/app/assets/food-images.json from the local image run (see frontend/public/images/README.md).

A dish photo is shared by similar recipes, so a recipe keeps it only if the picture cannot mislead:
- it shows no meat or fish the recipe lacks. What an image shows comes from its prompt subject, from the recipes that
  share it (a kind is shown once it is in 40% of them), and for what FLUX added on its own, from SHOWS_MEAT;
- a vegan recipe also gets no picture of egg or dairy;
- a dish word in the title (soup, cake, ...) must be common among the recipes sharing the picture.
A recipe its own picture would mislead takes the most similar picture that would not (TF-IDF on title and ingredients).
Every recipe gets a picture: if none passes, the dish word gives way first, then the rest.
The curated catalog goes through the same matching. A dish imported from the web is matched in the browser by the rarest
word of its title.
`python scripts/build_food_images.py <local-image-gen folder>`
"""

import json
import re
import sys
from collections import Counter, defaultdict
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
RELEASE = ROOT / "data-engineering" / "data" / "release" / "v3"
CURATED = ROOT / "data" / "recipes" / "recipes.json"
OUTPUT = ROOT / "frontend" / "app" / "assets" / "food-images.json"

# Seen on contact sheets of every image still serving a meatless recipe: meat or fish its prompt never asked for.
SHOWS_MEAT = frozenset(
    """
d0087 d0103 d0105 d0127 d0174 d0191 d0218 d0227 d0253 d0325 d0375 d0382 d0414 d0416 d0425 d0436 d0442 d0476 d0481 d0490
d0508 d0522 d0562 d0580 d0603 d0612 d0628 d0634 d0649 d0658 d0677 d0716 d0754 d0786 d0803 d0822 d0826 d0833 d0836 d0841
d0866 d0892 d0898 d0900 d0906 d0908 d0916 d0970 d0975 d0982 d0984 d0992 d0996 d1027 d1038 d1044 d1052 d1053 d1070 d1080
d1081 d1099 d1101 d1104 d1111 d1126 d1130 d1153 d1157 d1161 d1169 d1181 d1184 d1212 d1215 d1227 d1234 d1254 d1273 d1284
d1311 d1321 d1329 d1345 d1353 d1376 d1382 d1394 d1410 d1414 d1415 d1419 d1421 d1424 d1427 d1442 d1469 d1496 d1503 d1506
d1513 d1518 d1520 d1524 d1534 d1575 d1576 d1583 d1584 d1586 d1587 d1591 d1603 d1606 d1660 d1684 d1690 d1702 d1713 d1747
d1748 d1796 d1801 d1803 d1822 d1841 d1857 d1863 d1864 d1873 d1884 d1890 d1892 d1895 d1897
""".split()
)

KINDS = {
    "pork": r"pork|bacon|ham|pancetta|prosciutto|chorizo|sausage|hot dog|pepperoni",
    "beef": r"beef|steak|pastrami",
    "poultry": r"chicken|turkey|duck|hen",
    "seafood": r"anchovy|catfish|clam|cod|crab|crabmeat|fish|hake|halibut|lobster|milkfish|mussel|octopus|oyster|"
    r"salmon|sardine|scallop|seafood|shrimp|snapper|squid|swordfish|trout|tuna|haddock",
}
SHARED_BY = 0.4
# A dish word in a title; the picture must fit it. Each pattern is the same kind of dish.
DISH_WORDS = [
    r"soup|chowder|bisque|broth|gazpacho|ramen|pho",
    r"cake|cupcake|cheesecake|torte",
    r"pizza|flatbread|calzone",
    r"salad|slaw",
    r"cookie|cookies|brownie|brownies",
    r"smoothie|shake|juice|tea|latte|lemonade|punch|cocktail|lassi",
    r"pie|tart|cobbler",
    r"bread|loaf|muffin|muffins|scone|scones|rolls",
    r"sandwich|burger|wrap|panini",
    r"pasta|spaghetti|lasagna|lasagne|penne|macaroni",
    r"curry|masala|korma",
    r"taco|tacos|burrito|quesadilla|enchilada|fajita",
    r"sauce|dip|dressing|salsa|pesto|chutney|gravy",
]
RARE_BELOW = 0.3
# Title words that say nothing about the dish, and how many recipes a word needs to stand for a picture.
FILLER_WORDS = frozenset(
    "a air an and au black bowl bowls brown de del easy for green homemade in my of on or plain plate quick recipe red "
    "s sheet simple skillet style sweet the tray white with yellow".split()
)
WORD_IN_RECIPES = 5
# A word this meatless (curry, rice, pasta...) must not bring a picture of meat to an imported dish.
MEATLESS_WORD = 0.25


def meat_kinds(name: str) -> set[str]:
    """The kinds in one meat or fish ingredient name; "meat" alone (goat, lamb, venison...) is its own kind."""
    return {kind for kind, words in KINDS.items() if re.search(rf"\b({words})s?\b", name)} or {"other meat"}


def load_ingredients() -> list[dict]:
    with (RELEASE / "ingredients.jsonl").open(encoding="utf-8") as lines:
        return [json.loads(line) for line in lines]


def load_recipes() -> list[dict]:
    meats = {
        row["canonical_name"]
        for row in load_ingredients()
        if row["food_group"] == "protein" and row["dietary_origin"] == "flesh"
    }
    recipes = []
    with (RELEASE / "recipes.jsonl").open(encoding="utf-8") as lines:
        for line in lines:
            row = json.loads(line)
            names = {item["canonical_name"] for item in row["ingredients"]}
            recipes.append(
                {
                    "id": row["recipe_id"],
                    "key": row["recipe_id"][-12:].lower(),
                    "title": row["title"].lower(),
                    "text": " ".join([row["title"], *sorted(names)]),
                    "vegan": "vegan" in row["dietary_tags"],
                    "meat": set().union(*map(meat_kinds, names & meats)),
                }
            )
    return recipes


def load_curated() -> list[dict]:
    """The curated catalog, keyed by whole slug: the last 12 characters of two curated slugs can be the same."""
    recipes = []
    for row in json.loads(CURATED.read_text(encoding="utf-8")):
        names = {item["ingredient"].replace("_", " ") for item in row["ingredients"]}
        meat = {k for k, words in KINDS.items() for name in names if re.search(rf"\b({words})s?\b", name)}
        recipes.append(
            {
                "key": row["slug"],
                "title": row["title"].lower(),
                "text": " ".join([row["title"], *sorted(names)]),
                "vegan": "vegan" in row["dietary_tags"],
                "meat": meat,
            }
        )
    return recipes


def shown_kinds(members: list[dict], subject: set[str]) -> set[str]:
    """What an image shows: its prompt subject, each kind most of its recipes have, "meat" if most have any."""
    counts = Counter(kind for recipe in members for kind in recipe["meat"])
    shown = subject | {kind for kind, count in counts.items() if count >= SHARED_BY * len(members)}
    if sum(1 for recipe in members if recipe["meat"]) >= SHARED_BY * len(members):
        shown.add("meat")
    return shown


def misfit(recipe: dict, shown: set[str], shows_animal: bool, members: list[dict]) -> str | None:
    """Why this recipe must not use this image, or None."""
    if ("meat" in shown and not recipe["meat"]) or shown - {"meat"} - recipe["meat"]:
        return "meat"
    if shows_animal and recipe["vegan"]:
        return "egg or dairy"
    for words in DISH_WORDS:
        word = re.compile(rf"\b({words})\b")
        if word.search(recipe["title"]):
            sharing = sum(1 for member in members if word.search(member["title"]))
            if sharing < RARE_BELOW * len(members):
                return "dish word"
    return None


def build(source: Path) -> tuple[dict[str, list[dict]], Counter]:
    """{image: the recipes it stands for} and, by reason, how many recipes moved to another picture."""
    origin = {row["canonical_name"]: row["dietary_origin"] for row in load_ingredients()}
    groups = json.loads((source / "groups.json").read_text(encoding="utf-8"))
    pictured = [group for group in groups if group["main"] != "mixed"]  # the order make_batch.py numbers the images in
    subjects = {f"d{n:04d}": {group["main"], group.get("with")} for n, group in enumerate(pictured)}
    assigned = json.loads((source / "recipe_images.json").read_text(encoding="utf-8"))

    by_image = defaultdict(list)
    for recipe in load_recipes():
        by_image[assigned[recipe["id"]]].append(recipe)

    shown, shows_animal = {}, {}
    for image, members in by_image.items():
        flesh = [name for name in subjects[image] if origin.get(name) == "flesh"]
        shown[image] = shown_kinds(members, set().union(*map(meat_kinds, flesh)))
        if image in SHOWS_MEAT:
            shown[image].add("meat")
        shows_animal[image] = any(origin.get(name) == "secretion" for name in subjects[image])

    kept, moved, reasons = defaultdict(list), [], Counter()
    for image, members in sorted(by_image.items()):
        for recipe in members:
            why = misfit(recipe, shown[image], shows_animal[image], members)
            if why:
                reasons[why] += 1
                moved.append(recipe)
            else:
                kept[image].append(recipe)

    from sklearn.feature_extraction.text import TfidfVectorizer  # the local image folder's Python has it

    # Only pictures that keep recipes of their own exist in the repository.
    images = sorted(kept)
    vectorizer = TfidfVectorizer(sublinear_tf=True)
    matrix = vectorizer.fit_transform(" ".join(recipe["text"] for recipe in kept[image]) for image in images)
    moved += load_curated()
    similarity = (vectorizer.transform(recipe["text"] for recipe in moved) * matrix.T).toarray()
    for recipe, scores in zip(moved, similarity, strict=True):
        nearest = [images[index] for index in scores.argsort()[::-1]]
        why = {image: misfit(recipe, shown[image], shows_animal[image], by_image[image]) for image in nearest}
        fits = next((image for image in nearest if why[image] is None), None)
        if fits is None:
            reasons["no picture fits"] += 1
            fits = next((image for image in nearest if why[image] == "dish word"), nearest[0])
            if why[fits] != "dish word":
                reasons["shows what the recipe lacks"] += 1
        kept[fits].append(recipe)

    return {image: kept[image] for image in images}, reasons


def title_words(dishes: dict[str, list[dict]]) -> dict[str, str]:
    """{title word: the picture most recipes with that word use}, rarest word first (a rare word says most).

    An imported dish has no checked ingredients, so a word many meatless recipes use counts only their pictures.
    """
    every, meatless = defaultdict(Counter), defaultdict(Counter)
    for image, members in dishes.items():
        for recipe in members:
            for word in set(re.findall(r"[a-z]+", recipe["title"])) - FILLER_WORDS:
                every[word][image] += 1
                if not recipe["meat"]:
                    meatless[word][image] += 1
    usable = [(sum(c.values()), word) for word, c in every.items() if sum(c.values()) >= WORD_IN_RECIPES]
    words = {}
    for total, word in sorted(usable):
        pictures = meatless[word] if sum(meatless[word].values()) >= MEATLESS_WORD * total else every[word]
        words[word] = pictures.most_common(1)[0][0]
    return words


def main() -> None:
    pictured, dropped = build(Path(sys.argv[1]))
    dishes = {image: " ".join(recipe["key"] for recipe in members) for image, members in pictured.items()}
    words = title_words(pictured)
    names = sorted(re.sub(r"[^a-z0-9]", "-", row["canonical_name"].lower()) for row in load_ingredients())
    food_images = {"dishes": dishes, "ingredients": names, "words": words, "fallback": words["vegetable"]}
    OUTPUT.write_text(json.dumps(food_images, separators=(",", ":")), encoding="utf-8")
    recipes = sum(len(ids.split()) for ids in dishes.values())
    print(f"{len(dishes)} images, {recipes} recipes; moved to a nearer picture, by reason: {dict(dropped)}")


if __name__ == "__main__":
    main()
