"""Catalog titles and ingredient lines read cleanly where they are shown; the catalog keeps its text (P16).

Every example is one the 2026-10-04 walkthrough showed on the week card, the meals list or a recipe sheet.
"""

from app.agent.replies import say
from app.models.recipe import Recipe
from app.schemas.recipe import RecipeIngredientResponse, RecipeListItemResponse
from tests.test_planning_product_path import database
from tests.test_recipes import recipe_client as recipe_client

NUTRIENTS = ("calories_kcal", "protein_g", "carbohydrate_g", "fat_g", "sodium_mg", "sugar_g")
SHOWN = {
    "Chinese Egg Flower Soup (Ww)": "Chinese Egg Flower Soup",
    "Pot Pie(Square Dumplings)": "Pot Pie (Square Dumplings)",
    "Cho Na-Mool(Korean Cabbage Salad)": "Cho Na-Mool (Korean Cabbage Salad)",
    "Tsukemono – Japanese Pickles": "Tsukemono (Japanese Pickles)",
    "Tsukemono- Japanese Cabbage Salad": "Tsukemono (Japanese Cabbage Salad)",
    "Indonesian Potato Croquettes- (Kroket Kentang)": "Indonesian Potato Croquettes (Kroket Kentang)",
    "Hara (Green)Masala Chicken": "Hara (Green) Masala Chicken",
    "Mexican Pulled Pork-Carnitas(Atk)": "Mexican Pulled Pork-Carnitas",
    "Fire Hot Chilli Paste (Sambal) - Indonesian Sauce": "Fire Hot Chilli Paste (Sambal) – Indonesian Sauce",
    "Honey Dijon Chicken(Fat:  3 Grams Per Serving)": "Honey Dijon Chicken (Fat: 3 Grams Per Serving)",
    "Lemon Chicken": "Lemon Chicken",
    "Rolled Dumplings": "Rolled Dumplings",
    "Korean-Style Ramen": "Korean-Style Ramen",
}


def test_catalog_titles_read_as_dish_names() -> None:
    from app.schemas.display import shown_title

    assert {title: shown_title(title) for title in SHOWN} == SHOWN
    assert all(shown_title(shown) == shown for shown in SHOWN.values())


def test_titles_joined_into_a_sentence_read_as_they_do_one_by_one() -> None:
    from app.schemas.display import shown_title

    titles = list(SHOWN)
    for separator in (", ", "、"):
        assert shown_title(separator.join(titles)) == separator.join(SHOWN[title] for title in titles)


def test_a_preparation_reads_as_the_recipe_wrote_it() -> None:
    from app.schemas.display import shown_preparation

    onion = "2 green onions, white and light green parts only, thinly sliced"
    assert shown_preparation("light; thinly sliced; white and green parts only", onion) == (
        "white and light green parts only, thinly sliced"
    )
    shrimp = "1 lb shrimp, peeled and deveined"
    assert shown_preparation("and; deveined; peeled", shrimp) == "peeled, deveined"
    # "light" of light brown sugar is not cut out of another fragment, so it stays.
    assert shown_preparation("firmly packed; light", "1 c. light brown sugar, firmly packed") == "light, firmly packed"
    assert shown_preparation("zested") == "zested"
    assert shown_preparation(None) is None
    assert shown_preparation("none", "4 None long white bread rolls") is None


def test_only_what_is_shown_is_cleaned() -> None:
    """Planning and matching read the attribute, which keeps the catalog's text; the API's JSON is cleaned."""
    item = RecipeListItemResponse.model_validate(
        {
            "id": 1,
            "slug": "v2-pot-pie",
            "title": "Pot Pie(Square Dumplings)",
            "description": "",
            "cuisine": "Chinese",
            "meal_type": "dinner",
            "servings": 2,
            "total_time_minutes": 30,
            "dietary_tags": [],
            "nutrition": dict.fromkeys(NUTRIENTS, 1),
        }
    )
    assert item.title == "Pot Pie(Square Dumplings)" and item.model_dump()["title"] == item.title
    assert item.model_dump(mode="json")["title"] == "Pot Pie (Square Dumplings)"
    line = RecipeIngredientResponse(
        name="green onion",
        normalized_name="green_onion",
        quantity=30,
        unit="g",
        preparation="light; thinly sliced; white and green parts only",
        allergens=[],
        original_text="2 green onions, white and light green parts only, thinly sliced",
    )
    assert line.preparation == "light; thinly sliced; white and green parts only"
    assert line.model_dump(mode="json")["preparation"] == "white and light green parts only, thinly sliced"


def test_the_recipe_api_shows_clean_text_and_searches_the_catalog_text(recipe_client) -> None:
    with database() as session:
        recipe = session.query(Recipe).filter_by(slug="tofu-soba").one()
        recipe.title = "Tofu Soba(Ww)"
        recipe.recipe_ingredients[0].preparation = "and; cubed; pressed"
        recipe.recipe_ingredients[0].original_text = "300 g firm tofu, pressed and cubed"
        session.commit()
    detail = recipe_client.get("/api/recipes/tofu-soba").json()
    assert detail["title"] == "Tofu Soba"
    assert detail["ingredients"][0]["preparation"] == "pressed, cubed"
    found = recipe_client.get("/api/recipes", params={"q": "soba"}).json()["items"]
    assert [(item["slug"], item["title"]) for item in found] == [("tofu-soba", "Tofu Soba")]
    with database() as session:
        assert session.query(Recipe).filter_by(slug="tofu-soba").one().title == "Tofu Soba(Ww)"


def test_the_assistant_names_a_dish_as_the_plan_shows_it() -> None:
    assert say("preview_skip", "en", title="Pot Pie(Square Dumplings)") == "Skip Pot Pie (Square Dumplings)?"
    assert say("preview_swap", "en", before="Chinese Egg Flower Soup (Ww)", after="Tsukemono – Japanese Pickles") == (
        "How about Tsukemono (Japanese Pickles) instead of Chinese Egg Flower Soup?"
    )
    assert say("ask_dish", "zh", count=2, titles="Tsukemono – Japanese Pickles、Pot Pie(Square Dumplings)") == (
        "那天有 2 道菜（Tsukemono (Japanese Pickles)、Pot Pie (Square Dumplings)），你想调整哪一道？"
    )
    # A count is a count.
    assert "had 5)" in say("varied_planned", "en", count=7, before=5, fresh="")


def test_a_dish_is_offered_and_understood_by_the_name_the_plan_shows(monkeypatch) -> None:
    """The "which dish" choices name dishes as the week card does, and choosing one picks that dish."""
    from tests.test_agent_limits_and_language import planned, tap
    from tests.test_agent_limits_and_language import say as tell
    from tests.test_planning_capability import _dish, dish_client

    dishes = [
        _dish("salmon-bake", "main", "salmon_fillet", 400, calories=500),
        _dish("chicken-roast", "main", "chicken_breast", 400, calories=450),
        _dish("broccoli-stirfry", "side", "broccoli", 300, calories=100),
        _dish("spinach-saute", "side", "baby_spinach", 200, calories=80),
    ]
    for dish in dishes:
        dish.title = f"{dish.title}(Ww)"
    with dish_client(monkeypatch, dishes) as client:
        asked = tell(client, planned(client, "Dinners for 4 this week"), "swap every dish")
        which = tap(client, asked, asked["pending_interaction"]["options"][1]["label"])
        labels = [option["label"] for option in which["pending_interaction"]["options"]]
        assert len(labels) == 2 and all(
            label in {"Salmon Bake", "Chicken Roast", "Broccoli Stirfry", "Spinach Saute"} for label in labels
        )
        previewed = tap(client, which, labels[0])
        assert previewed["pending_replan"]["status"] == "previewed"
        assert previewed["pending_replan"]["before_entry"]["recipe_title"] == labels[0]
