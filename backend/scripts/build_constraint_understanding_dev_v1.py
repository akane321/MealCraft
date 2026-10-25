"""Build a deterministic, developer-only multilingual constraint-understanding set."""

import json

from app.core.paths import repository_root

ROOT = repository_root()
DESTINATION = ROOT / "data/evaluation/agent/constraint-understanding-dev-v1.json"

# (language, utterance, expected extraction, expected missing fields, medical boundary)
EXTRA_CASES = [
    # Household size: numeric, word, and ordinary Chinese family phrasing.
    ("en", "Plan meals for 6 people.", {"household_size": 6}),
    ("en", "Dinner should serve seven.", {"household_size": 7}),
    ("en", "We are 8 people.", {"household_size": 8}),
    ("en", "A family of nine needs a weekly plan.", {"household_size": 9}),
    ("zh", "请为六个人安排一周菜单。", {"household_size": 6}),
    ("zh", "我们家有七口人。", {"household_size": 7}),
    ("zh", "八个人一起吃饭。", {"household_size": 8}),
    ("zh", "家里九个人，请安排晚餐。", {"household_size": 9}),
    ("zh", "我们一家四口。", {"household_size": 4}),
    ("zh", "给十个人准备晚饭。", {"household_size": 10}),
    ("mixed", "Plan for 3 people, 我们一家三口。", {"household_size": 3}),
    ("mixed", "Dinner for 5, 请安排五个人的份量。", {"household_size": 5}),
    # Weekly and per-meal budgets, including household scaling for per-person amounts.
    ("en", "Weekly budget S$80 for 2 people.", {"household_size": 2, "weekly_budget_sgd": 80}),
    ("en", "Keep each dinner under S$14 for 3 people.", {"household_size": 3, "budget_per_meal_sgd": 14}),
    ("en", "S$5 per person per meal for four people.", {"household_size": 4, "budget_per_meal_sgd": 20}),
    ("en", "We are 5; the whole week must cost no more than S$125.", {"household_size": 5, "weekly_budget_sgd": 125}),
    ("zh", "两个人，每周预算80新币。", {"household_size": 2, "weekly_budget_sgd": 80}),
    ("zh", "三个人，每餐不超过14新币。", {"household_size": 3, "budget_per_meal_sgd": 14}),
    ("zh", "每人每餐5新币，四个人吃。", {"household_size": 4, "budget_per_meal_sgd": 20}),
    ("zh", "五个人，这一周总预算125元。", {"household_size": 5, "weekly_budget_sgd": 125}),
    ("zh", "两个人每顿最多花18块。", {"household_size": 2, "budget_per_meal_sgd": 18}),
    ("mixed", "For 3 people, 每周预算 S$90.", {"household_size": 3, "weekly_budget_sgd": 90}),
    ("mixed", "四个人, keep dinner to S$16 per meal.", {"household_size": 4, "budget_per_meal_sgd": 16}),
    ("mixed", "S$4 per person per dinner, 给两个人做。", {"household_size": 2, "budget_per_meal_sgd": 8}),
    # Cooking time limits.
    ("en", "For two people, cooking takes at most 25 minutes.", {"household_size": 2, "max_cooking_time_minutes": 25}),
    ("en", "We are 3; keep cooking below 40 minutes.", {"household_size": 3, "max_cooking_time_minutes": 40}),
    ("en", "A 45-minute cooking limit for four people.", {"household_size": 4, "max_cooking_time_minutes": 45}),
    ("en", "For five, dinner prep should take half an hour.", {"household_size": 5, "max_cooking_time_minutes": 30}),
    ("zh", "两个人，做饭控制在25分钟内。", {"household_size": 2, "max_cooking_time_minutes": 25}),
    ("zh", "三个人，烹饪时间最多40分钟。", {"household_size": 3, "max_cooking_time_minutes": 40}),
    ("zh", "四个人，做饭不超过45分钟。", {"household_size": 4, "max_cooking_time_minutes": 45}),
    ("zh", "五个人，半小时内能做好的晚餐。", {"household_size": 5, "max_cooking_time_minutes": 30}),
    ("zh", "六个人，最多一小时做完。", {"household_size": 6, "max_cooking_time_minutes": 60}),
    ("mixed", "For 2 people, 做饭不超过35分钟。", {"household_size": 2, "max_cooking_time_minutes": 35}),
    ("mixed", "三个人, dinner in under 50 minutes.", {"household_size": 3, "max_cooking_time_minutes": 50}),
    ("mixed", "Cooking for four, 最多半小时。", {"household_size": 4, "max_cooking_time_minutes": 30}),
    # Allergens.
    ("en", "For two people, one person has a milk allergy.", {"household_size": 2, "allergens": ["dairy"]}),
    ("en", "Three people; someone is allergic to eggs.", {"household_size": 3, "allergens": ["egg"]}),
    ("en", "A family of four has a wheat allergy.", {"household_size": 4, "allergens": ["gluten"]}),
    (
        "en",
        "For five, avoid cross-contact with tree nuts due to an allergy.",
        {"household_size": 5, "allergens": ["tree_nut"]},
    ),
    ("zh", "两个人，其中一人对牛奶过敏。", {"household_size": 2, "allergens": ["dairy"]}),
    ("zh", "三个人，有人鸡蛋过敏。", {"household_size": 3, "allergens": ["egg"]}),
    ("zh", "四个人，小麦过敏。", {"household_size": 4, "allergens": ["gluten"]}),
    ("zh", "五个人，有人对芝麻过敏。", {"household_size": 5, "allergens": ["sesame"]}),
    ("zh", "六个人，其中一个对大豆过敏。", {"household_size": 6, "allergens": ["soy"]}),
    ("mixed", "For 2 people, 有人对 peanut 过敏。", {"household_size": 2, "allergens": ["peanut"]}),
    ("mixed", "三个人, one has a shellfish allergy.", {"household_size": 3, "allergens": ["shellfish"]}),
    ("mixed", "Four people, fish allergy for one member.", {"household_size": 4, "allergens": ["fish"]}),
    # Ingredient exclusions.
    ("en", "For two people, no pork.", {"household_size": 2, "excluded_ingredients": ["pork"]}),
    ("en", "Three people, please skip tofu.", {"household_size": 3, "excluded_ingredients": ["firm_tofu"]}),
    ("en", "Exclude chicken for four people.", {"household_size": 4, "excluded_ingredients": ["chicken"]}),
    (
        "en",
        "For five people, do not use cooking wine.",
        {"household_size": 5, "excluded_ingredients": ["wine_cooking"]},
    ),
    ("zh", "两个人，不要牛肉。", {"household_size": 2, "excluded_ingredients": ["beef"]}),
    ("zh", "三个人，不放大蒜。", {"household_size": 3, "excluded_ingredients": ["garlic"]}),
    ("zh", "四个人，避免香菜。", {"household_size": 4, "excluded_ingredients": ["cilantro"]}),
    ("zh", "五个人，不吃羊肉。", {"household_size": 5, "excluded_ingredients": ["lamb"]}),
    ("zh", "六个人，不要料酒。", {"household_size": 6, "excluded_ingredients": ["wine_cooking"]}),
    ("mixed", "For 2 people, 不要蘑菇。", {"household_size": 2, "excluded_ingredients": ["mushroom"]}),
    ("mixed", "Three people, no 鸡肉 please.", {"household_size": 3, "excluded_ingredients": ["chicken"]}),
    ("mixed", "四个人, exclude onion.", {"household_size": 4, "excluded_ingredients": ["onion"]}),
    # Dietary rules and halal.
    ("en", "Vegetarian meals for two people.", {"household_size": 2, "dietary_preferences": ["vegetarian"]}),
    ("en", "For three, make everything vegan.", {"household_size": 3, "dietary_preferences": ["vegan"]}),
    ("en", "Four people need gluten-free dinners.", {"household_size": 4, "dietary_preferences": ["gluten-free"]}),
    ("en", "Dairy-free meals for five, please.", {"household_size": 5, "dietary_preferences": ["dairy-free"]}),
    ("zh", "两个人吃素。", {"household_size": 2, "dietary_preferences": ["vegetarian"]}),
    ("zh", "三个人，要纯素菜单。", {"household_size": 3, "dietary_preferences": ["vegan"]}),
    ("zh", "四个人，要求无麸质。", {"household_size": 4, "dietary_preferences": ["gluten-free"]}),
    ("zh", "五个人，不吃乳制品。", {"household_size": 5, "dietary_preferences": ["dairy-free"]}),
    ("zh", "六个人，需要清真餐。", {"household_size": 6, "requires_halal": True}),
    ("mixed", "For 2 people, 素食 only.", {"household_size": 2, "dietary_preferences": ["vegetarian"]}),
    ("mixed", "Three people, make the meals halal / 清真.", {"household_size": 3, "requires_halal": True}),
    ("mixed", "四个人, dairy-free please.", {"household_size": 4, "dietary_preferences": ["dairy-free"]}),
    # Health preferences.
    ("en", "For two, choose lower sodium meals.", {"household_size": 2, "health_preferences": ["low-sodium"]}),
    ("en", "Three people want low-sugar food.", {"household_size": 3, "health_preferences": ["low-sugar"]}),
    (
        "en",
        "For four people, keep the meals low calorie.",
        {"household_size": 4, "health_preferences": ["lower-calorie"]},
    ),
    (
        "en",
        "Five people prefer low-sodium and low-sugar dinners.",
        {"household_size": 5, "health_preferences": ["low-sodium", "low-sugar"]},
    ),
    ("zh", "两个人，少盐。", {"household_size": 2, "health_preferences": ["low-sodium"]}),
    ("zh", "三个人，低糖饮食。", {"household_size": 3, "health_preferences": ["low-sugar"]}),
    ("zh", "四个人，选择低热量菜。", {"household_size": 4, "health_preferences": ["lower-calorie"]}),
    ("zh", "五个人，低盐低糖。", {"household_size": 5, "health_preferences": ["low-sodium", "low-sugar"]}),
    (
        "zh",
        "六个人，少油少盐。",
        {
            "household_size": 6,
            "health_preferences": ["low-sodium"],
            "planning_preferences": {"lighter": True},
        },
    ),
    ("mixed", "For 2 people, low-sodium meals.", {"household_size": 2, "health_preferences": ["low-sodium"]}),
    ("mixed", "三个人, low-sugar please.", {"household_size": 3, "health_preferences": ["low-sugar"]}),
    ("mixed", "Four people, lower calorie 菜肴.", {"household_size": 4, "health_preferences": ["lower-calorie"]}),
    # Nutrition targets.
    ("en", "For two, target 500 kcal.", {"household_size": 2, "nutrition_targets": {"calories_kcal": 500}}),
    ("en", "Three people; aim for 25 g protein.", {"household_size": 3, "nutrition_targets": {"protein_g": 25}}),
    (
        "en",
        "For four people, target 60 g carbs and 20 g fat.",
        {"household_size": 4, "nutrition_targets": {"carbohydrate_g": 60, "fat_g": 20}},
    ),
    ("en", "Keep sodium under 900 mg per meal for five.", {"household_size": 5, "max_sodium_mg_per_meal": 900}),
    ("zh", "两个人，每餐目标550千卡。", {"household_size": 2, "nutrition_targets": {"calories_kcal": 550}}),
    ("zh", "三个人，每餐蛋白质30克。", {"household_size": 3, "nutrition_targets": {"protein_g": 30}}),
    (
        "zh",
        "四个人，每餐碳水50克、脂肪15克。",
        {"household_size": 4, "nutrition_targets": {"carbohydrate_g": 50, "fat_g": 15}},
    ),
    ("zh", "五个人，每餐钠不超过700毫克。", {"household_size": 5, "max_sodium_mg_per_meal": 700}),
    ("zh", "六个人，每餐目标600卡路里。", {"household_size": 6, "nutrition_targets": {"calories_kcal": 600}}),
    ("mixed", "For 2 people, 35 g protein target.", {"household_size": 2, "nutrition_targets": {"protein_g": 35}}),
    ("mixed", "三个人, target 650 kcal.", {"household_size": 3, "nutrition_targets": {"calories_kcal": 650}}),
    ("mixed", "Four people, sodium 不超过1000毫克.", {"household_size": 4, "max_sodium_mg_per_meal": 1000}),
    # Pantry quantities and unknown amounts.
    (
        "en",
        "For two people, I have 300 g brown rice.",
        {
            "household_size": 2,
            "available_ingredients": [{"normalized_name": "brown_rice", "quantity": 300, "unit": "g"}],
        },
    ),
    (
        "en",
        "Three people. We already have 2 kg chicken breast.",
        {
            "household_size": 3,
            "available_ingredients": [{"normalized_name": "chicken_breast", "quantity": 2, "unit": "kg"}],
        },
    ),
    (
        "en",
        "For four, there is 1 l milk in the fridge.",
        {"household_size": 4, "available_ingredients": [{"normalized_name": "milk", "quantity": 1, "unit": "l"}]},
    ),
    (
        "en",
        "Five people. I have tofu at home.",
        {"household_size": 5, "available_ingredients": [{"normalized_name": "firm_tofu"}]},
        ["available_ingredients.firm_tofu.quantity"],
    ),
    (
        "zh",
        "两个人，家里有300克糙米。",
        {
            "household_size": 2,
            "available_ingredients": [{"normalized_name": "brown_rice", "quantity": 300, "unit": "g"}],
        },
    ),
    (
        "zh",
        "三个人，现有2千克鸡胸肉。",
        {
            "household_size": 3,
            "available_ingredients": [{"normalized_name": "chicken_breast", "quantity": 2, "unit": "kg"}],
        },
    ),
    (
        "zh",
        "四个人，家里有1升牛奶。",
        {"household_size": 4, "available_ingredients": [{"normalized_name": "milk", "quantity": 1, "unit": "l"}]},
    ),
    (
        "zh",
        "五个人，我有豆腐。",
        {"household_size": 5, "available_ingredients": [{"normalized_name": "firm_tofu"}]},
        ["available_ingredients.firm_tofu.quantity"],
    ),
    (
        "zh",
        "六个人，家里已有番茄。",
        {"household_size": 6, "available_ingredients": [{"normalized_name": "tomato"}]},
        ["available_ingredients.tomato.quantity"],
    ),
    (
        "mixed",
        "For 2 people, 家里有500克糙米。",
        {
            "household_size": 2,
            "available_ingredients": [{"normalized_name": "brown_rice", "quantity": 500, "unit": "g"}],
        },
    ),
    (
        "mixed",
        "Three people, 我有chicken breast 1 kg.",
        {
            "household_size": 3,
            "available_ingredients": [{"normalized_name": "chicken_breast", "quantity": 1, "unit": "kg"}],
        },
    ),
    (
        "mixed",
        "Four people, I have tofu at home.",
        {"household_size": 4, "available_ingredients": [{"normalized_name": "firm_tofu"}]},
        ["available_ingredients.firm_tofu.quantity"],
    ),
    # Soft preferences.
    (
        "en",
        "For two people, add more vegetables.",
        {"household_size": 2, "planning_preferences": {"more_vegetables": True}},
    ),
    ("en", "Three people prefer lighter meals.", {"household_size": 3, "planning_preferences": {"lighter": True}}),
    (
        "en",
        "For four, repeat breakfast if needed.",
        {"household_size": 4, "planning_preferences": {"repeat_allowed_meals": ["breakfast"]}},
    ),
    (
        "en",
        "Five people want spicy dinners on Friday.",
        {
            "household_size": 5,
            "planning_preferences": {
                "flavor_boosts": [{"flavor": "spicy", "weekdays": ["friday"], "meal_types": ["dinner"]}]
            },
        },
    ),
    ("zh", "两个人，多吃蔬菜。", {"household_size": 2, "planning_preferences": {"more_vegetables": True}}),
    ("zh", "三个人，吃得清淡些。", {"household_size": 3, "planning_preferences": {"lighter": True}}),
    (
        "zh",
        "四个人，早餐可以重复。",
        {"household_size": 4, "planning_preferences": {"repeat_allowed_meals": ["breakfast"]}},
    ),
    (
        "zh",
        "五个人，周五晚餐想吃辣的。",
        {
            "household_size": 5,
            "planning_preferences": {
                "flavor_boosts": [{"flavor": "spicy", "weekdays": ["friday"], "meal_types": ["dinner"]}]
            },
        },
    ),
    ("zh", "六个人，蔬菜多一点。", {"household_size": 6, "planning_preferences": {"more_vegetables": True}}),
    ("mixed", "For 2 people, 多来点蔬菜.", {"household_size": 2, "planning_preferences": {"more_vegetables": True}}),
    ("mixed", "三个人, lighter dinners.", {"household_size": 3, "planning_preferences": {"lighter": True}}),
    (
        "mixed",
        "Four people, 想吃spicy food.",
        {"household_size": 4, "planning_preferences": {"flavor_boosts": [{"flavor": "spicy"}]}},
    ),
    # Repetition, live pricing, medical boundaries, and follow-up answers.
    ("en", "For two people, no dish twice this week.", {"household_size": 2, "max_uses_per_recipe": 1}),
    ("en", "Three people, use FairPrice live pricing.", {"household_size": 3, "pricing_mode": "live"}),
    (
        "en",
        "For four, plan meals for someone with diabetes.",
        {"household_size": 4, "medical_request_detected": True},
        [],
        True,
    ),
    (
        "en",
        "I don't know the amount.",
        {},
        [],
        False,
        {"household_size": 2, "available_ingredients": [{"normalized_name": "brown_rice"}]},
    ),
    ("zh", "两个人，这周菜不要重复。", {"household_size": 2, "max_uses_per_recipe": 1}),
    ("zh", "三个人，使用FairPrice实时价格。", {"household_size": 3, "pricing_mode": "live"}),
    ("zh", "四个人，给痛风患者安排饮食。", {"household_size": 4, "medical_request_detected": True}, [], True),
    (
        "zh",
        "不知道。",
        {},
        [],
        False,
        {"household_size": 2, "available_ingredients": [{"normalized_name": "brown_rice"}]},
    ),
    (
        "zh",
        "还剩750克。",
        {"available_ingredients": [{"normalized_name": "brown_rice", "quantity": 750, "unit": "g"}]},
        [],
        False,
        {"household_size": 2, "available_ingredients": [{"normalized_name": "brown_rice"}]},
    ),
    ("mixed", "For 2 people, 一周不重样.", {"household_size": 2, "max_uses_per_recipe": 1}),
    ("mixed", "Three people, 请用FairPrice live prices.", {"household_size": 3, "pricing_mode": "live"}),
    ("mixed", "For four, 糖尿病患者.", {"household_size": 4, "medical_request_detected": True}, [], True),
]


def main() -> None:
    existing = json.loads(DESTINATION.read_text(encoding="utf-8"))
    existing = [case for case in existing if int(case["id"].rsplit("-", maxsplit=1)[-1]) <= 30]
    cases = list(existing)
    for index, row in enumerate(EXTRA_CASES, start=len(cases) + 1):
        language, message, extraction, *optional = row
        missing: list[str] = []
        medical = False
        current: dict = {}
        if optional and isinstance(optional[0], list):
            missing = optional.pop(0)
        if optional and isinstance(optional[0], bool):
            medical = optional.pop(0)
        if optional:
            current = optional[0]
        case = {
            "id": f"cud-{index:03d}",
            "category": row_category(index),
            "language": language,
            "message": message,
            "expected_extraction": extraction,
            "expected_missing_fields": missing,
        }
        if current:
            case["current_constraints"] = current
        if medical:
            case["expect_medical_boundary"] = True
        cases.append(case)
    DESTINATION.write_text(json.dumps(cases, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    print(f"Wrote {len(cases)} cases to {DESTINATION}")


def row_category(case_number: int) -> str:
    blocks = (
        "household",
        "budget",
        "time",
        "allergen",
        "exclusion",
        "dietary",
        "health",
        "nutrition",
        "pantry",
        "soft-preference",
        "interaction",
    )
    return blocks[(case_number - 31) // 12]


if __name__ == "__main__":
    main()
