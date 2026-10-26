"""The 2026-10-26 walkthrough: what the shop does not have.

"I can't buy tofu this week" asked for a day, echoed the chip as "Day 3", listed every dish of that day, and then
proposed Malaysian Fried Noodles, with 297.7 g of firm tofu: "tofu" was read as the curated `firm_tofu`, and the
release writes its "tofu, firm, cubed" as plain `tofu`. The plan panel's "Can't buy…" button proposed the same dish,
already twice in the week, a third time. The day chip's echo is in test_agent_limits_and_language.py.
"""

import re
from collections import Counter
from datetime import date

import pytest

from app.agent.replies import weekday
from app.core.clock import today as local_today
from app.data.ingredient_hierarchy import same_food
from tests.test_agent_limits_and_language import tap
from tests.test_planning_capability import _dish, dish_client
from tests.test_walkthrough_1004_planning import add

TOFU_DISHES = {"mongolian-tofu-and-green-beans", "tofu-vegetable-soba", "mapo-tofu", "malaysian-fried-noodles"}


def mains(*pairs, grams: int = 100) -> list:
    """Dinner mains of one ingredient each; dishes that name the same ingredient share its row."""
    rows = {}
    dishes = [_dish(slug, "main", name, grams, calories=450) for slug, name in pairs]
    for dish in dishes:
        line = dish.recipe_ingredients[0]
        line.ingredient = rows.setdefault(line.ingredient.normalized_name, line.ingredient)
    return dishes


def week(client, budget: float | None = None) -> dict:
    """Seven one-dish dinners for four from today, at snapshot prices."""
    response = client.post(
        "/api/plans/generate",
        json={
            "requires_halal": False,
            "start_date": local_today().isoformat(),
            "household_size": 4,
            "max_cooking_time_minutes": 90,
            "pricing_mode": "fixture",
            "plan_shape": {"meals": {"dinner": [{"role_id": "main", "courses": ["main"]}]}},
            **({"weekly_budget_sgd": budget} if budget is not None else {}),
        },
    )
    assert response.status_code == 201, response.text
    return response.json()


def chat(client, plan: dict, message: str) -> dict:
    response = client.post("/api/agent/sessions", json={"message": message, "plan_id": plan["id"]})
    assert response.status_code == 201, response.text
    return response.json()


def test_tofu_is_every_kind_of_tofu_and_nothing_made_from_it():
    assert {"tofu", "firm_tofu"} <= same_food("tofu")
    assert same_food("firm_tofu") == {"firm_tofu"}  # firm tofu missing leaves silken tofu on the shelf
    assert "ketchup" not in same_food("tomato") and "cherry_tomato" in same_food("tomato")


ONE_TOFU = [
    ("mongolian-tofu-and-green-beans", "firm_tofu"),
    ("lemon-chicken", "chicken_breast"),
    ("salmon-bake", "salmon_fillet"),
    ("tuna-melt", "canned_tuna"),
    ("chickpea-stew", "chickpea"),
    ("bean-chili", "black_bean"),
    ("mushroom-rice", "mushroom"),
]


@pytest.mark.parametrize(
    "message",
    [
        "I can't buy tofu this week",
        "这周买不到豆腐",
        "I can't buy an ingredient for {day}'s {title}: tofu",  # the plan panel's "Can't buy…" button
        "{zh_day}的{title}买不到豆腐",
    ],
)
def test_a_dish_the_shop_lacks_tofu_for_is_never_swapped_for_another_tofu_dish(monkeypatch, message):
    with dish_client(monkeypatch, mains(*ONE_TOFU)) as client:
        plan = week(client)
        tofu = next(dish for dish in plan["days"] if dish["recipe"]["slug"] == "mongolian-tofu-and-green-beans")
        # The walkthrough's replacement, the one dish the week does not serve: its tofu is the release's `tofu`.
        add(*mains(("malaysian-fried-noodles", "tofu")))
        day = date.fromisoformat(tofu["planned_date"])
        said = message.format(day=f"{day:%A}", zh_day=weekday(day, "zh").split()[0], title=tofu["recipe"]["title"])
        reply = chat(client, plan, said)

    preview = reply["pending_replan"]
    assert preview is not None, reply["messages"][-1]["content"]  # the one dish with tofu, without asking
    assert preview["event_type"] == "ITEM_UNAVAILABLE" and preview["before_entry"]["entry_id"] == tofu["entry_id"]
    assert preview["after_entry"]["recipe_slug"] not in TOFU_DISHES
    assert reply["messages"][-1]["content"].endswith(("Nothing changes until you confirm.", "确认之前什么都不会改。"))


TWO_TOFU = [
    ("tofu-vegetable-soba", "firm_tofu"),
    ("mapo-tofu", "tofu"),
    ("lemon-chicken", "chicken_breast"),
    ("salmon-bake", "salmon_fillet"),
    ("tuna-melt", "canned_tuna"),
    ("chickpea-stew", "chickpea"),
    ("bean-chili", "black_bean"),
]


@pytest.mark.parametrize(
    ("message", "asked", "lang"),
    [
        ("I can't buy tofu this week", r"2 dishes still to come use tofu: .+\. Which one should I change\?", "en"),
        ("这周买不到豆腐", r"接下来有 2 道菜用到豆腐：.+。要换哪一道？", "zh"),
    ],
)
def test_an_ingredient_said_without_a_dish_asks_only_about_the_dishes_that_use_it(monkeypatch, message, asked, lang):
    with dish_client(monkeypatch, mains(*TWO_TOFU)) as client:
        plan = week(client)
        reply = chat(client, plan, message)
        users = [dish for dish in plan["days"] if dish["recipe"]["slug"] in TOFU_DISHES]
        question = reply["messages"][-1]["content"]
        assert re.fullmatch(asked, question) and reply["pending_replan"] is None
        assert all(dish["recipe"]["title"] in question for dish in users)
        assert not any(dish["recipe"]["title"] in question for dish in plan["days"] if dish not in users)
        for dish in users:  # each with its day and meal
            assert weekday(date.fromisoformat(dish["planned_date"]), lang) in question
        options = reply["pending_interaction"]["options"]
        assert [option["label"] for option in options] == [
            f"{dish['recipe']['title']} ({weekday(date.fromisoformat(dish['planned_date']), 'en')}, dinner)"
            for dish in users
        ]

        picked = tap(client, reply, options[1]["label"])
    assert picked["pending_replan"]["before_entry"]["entry_id"] == users[1]["entry_id"]
    assert picked["pending_replan"]["after_entry"]["recipe_slug"] not in TOFU_DISHES


@pytest.mark.parametrize(
    ("message", "said"),
    [
        ("I can't buy tofu this week", "No dish still to come uses tofu, so nothing needs to change."),
        ("这周买不到豆腐", "接下来的菜都没有用到豆腐，不需要调整。"),
    ],
)
def test_an_ingredient_no_dish_still_to_come_uses_changes_nothing(monkeypatch, message, said):
    with dish_client(monkeypatch, mains(*ONE_TOFU[1:], ("pasta-toss", "wholewheat_pasta"))) as client:
        reply = chat(client, week(client), message)
    assert reply["messages"][-1]["content"] == said
    assert reply["pending_replan"] is None and reply["replan_draft"]["event_type"] is None


def test_a_dish_the_week_serves_twice_is_not_swapped_in_a_third_time_while_another_can_be(monkeypatch):
    """The walkthrough's third Malaysian Fried Noodles shared a package the week buys anyway, so it alone kept the
    week within its budget. Here the quickest dish (so the week's one repeat) takes a tenth of a bag of oats."""
    oats = _dish("oat-bake", "main", "rolled_oats", 100, calories=450, prep=1, cook=1)
    rest = [
        _dish(slug, "main", name, grams, calories=450)
        for slug, name, grams in (
            ("chickpea-stew", "chickpea", 400),
            ("tuna-melt", "canned_tuna", 185),
            ("tomato-stew", "canned_tomato", 400),
            ("broccoli-bake", "broccoli", 300),
            ("mushroom-rice", "mushroom", 300),
        )
    ]
    with dish_client(monkeypatch, [oats, *rest]) as client:
        plan = week(client, budget=18.2)
        assert Counter(dish["recipe"]["slug"] for dish in plan["days"])["oat-bake"] == 2
        add(*mains(("salmon-bake", "salmon_fillet"), grams=300))
        chickpea = next(dish for dish in plan["days"] if dish["recipe"]["slug"] == "chickpea-stew")
        preview = client.post(
            f"/api/plans/{plan['id']}/replan/preview",
            json={"entry_id": chickpea["entry_id"], "event_type": "REPLACE_MEAL"},
        )
    assert preview.status_code == 201, preview.text
    assert preview.json()["after_entry"]["recipe_slug"] != "oat-bake"
    assert preview.json()["over_budget_sgd"] is not None  # what it costs over the budget is said, as for any swap


def test_no_dish_without_the_missing_ingredient_is_said_so_and_none_with_it_is_offered(monkeypatch):
    names = ("mapo-tofu", "tofu-soba", "tofu-curry", "tofu-stirfry", "tofu-bowl", "tofu-laksa", "tofu-salad")
    with dish_client(monkeypatch, mains(*[(name, "firm_tofu") for name in names])) as client:
        plan = week(client)
        add(*mains(("malaysian-fried-noodles", "tofu")))
        first = plan["days"][0]
        title = first["recipe"]["title"]
        refused = client.post(
            f"/api/plans/{plan['id']}/replan/preview",
            json={"entry_id": first["entry_id"], "event_type": "ITEM_UNAVAILABLE", "unavailable_ingredient": "tofu"},
        )
        assert refused.status_code == 422, refused.text
        reason = f"No dish without tofu can replace {title} under the current hard constraints."
        assert refused.json()["detail"] == reason

        day = weekday(date.fromisoformat(first["planned_date"]), "zh").split()[0]
        reply = chat(client, plan, f"{day}的{title}买不到豆腐")
    assert reply["pending_replan"] is None
    assert reply["messages"][-1]["content"] == f"我没法准备这个调整：没有不含豆腐、又符合现在限制的菜能替换{title}。"
