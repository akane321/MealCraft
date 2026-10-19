"""Profile member fields, rules, basics and limits through the API (layer 08 PR-1)."""

from tests.test_recipes import recipe_client as recipe_client

RULE = {
    "source_text": "孩子工作日午饭在学校吃",
    "restatement": "anything the client sent",
    "member_name": "Mei",
    "present": False,
    "weekdays": ["monday", "tuesday", "wednesday", "thursday", "friday"],
    "meal_types": ["lunch"],
}
TIME_RULE = {
    "source_text": "weekday dinners within 30 minutes",
    "restatement": "x",
    "weekdays": ["monday", "tuesday", "wednesday", "thursday", "friday"],
    "meal_types": ["dinner"],
    "max_minutes": 30,
}


def payload(**changes) -> dict:
    body = {
        "name": "Tan household",
        "members": [
            {"name": "Ann", "servings_per_meal": None, "age_band": "adult", "sex": "female", "activity": "low"},
            {"name": "Ben", "servings_per_meal": 1.25, "age_band": "adult", "sex": "male", "goal": "muscle_gain"},
            {"name": "Mei", "servings_per_meal": None, "age_band": "child"},
            {"name": "Grandma", "servings_per_meal": None, "age_band": "senior", "default_present": False},
        ],
        "plan_shape": {"meals": {"dinner": [{"role_id": "main", "courses": ["main"]}]}},
        "presence_rules": [RULE],
        "cooking_time_rules": [TIME_RULE],
        "missing_basics": ["Soy sauce"],
        "nutrition_limits": [{"nutrient": "sodium_mg"}],
    }
    body.update(changes)
    return body


def test_a_profile_keeps_member_fields_rules_basics_and_limits(recipe_client):
    created = recipe_client.post("/api/household-profiles", json=payload())
    assert created.status_code == 201, created.text
    current = created.json()["current"]
    members = {m["name"]: m for m in current["members"]}
    # HPB adult female, low active: 1720 / 2313.
    assert (members["Ann"]["resolved_servings_per_meal"], members["Ann"]["servings_source"]) == (0.74, "hpb_default")
    assert members["Ann"]["activity"] == "low" and members["Mei"]["activity"] is None
    assert members["Ann"]["servings_per_meal"] is None
    assert (members["Ben"]["resolved_servings_per_meal"], members["Ben"]["servings_source"]) == (1.25, "stated")
    assert members["Mei"]["resolved_servings_per_meal"] == 0.73
    assert members["Grandma"]["default_present"] is False
    # Usually home: 0.74 + 1.25 + 0.73 = 2.72, rounded up; the guest is not counted.
    assert current["planning_household_size"] == 3
    assert current["presence_rules"][0]["restatement"] == "Monday to Friday, lunch: Mei eats elsewhere."
    assert current["cooking_time_rules"][0]["restatement"] == "Monday to Friday, dinner: within 30 minutes."
    assert current["missing_basics"] == ["soy_sauce"]
    assert current["nutrition_limits"] == [{"nutrient": "sodium_mg", "scope": "per_day", "max_value": None}]

    update = payload(expected_version=1, presence_rules=[], missing_basics=[])
    updated = recipe_client.put(f"/api/household-profiles/{created.json()['id']}", json=update)
    assert updated.status_code == 200, updated.text
    assert updated.json()["current"]["presence_rules"] == []
    versions = recipe_client.get(f"/api/household-profiles/{created.json()['id']}/versions").json()["items"]
    assert [len(item["presence_rules"]) for item in versions] == [0, 1]


def test_whole_portions_still_work_and_decimals_are_bounded(recipe_client):
    legacy = {"name": "Legacy", "members": [{"name": "A", "servings_per_meal": 2}, {"name": "B"}]}
    created = recipe_client.post("/api/household-profiles", json=legacy)
    assert created.status_code == 201, created.text
    assert created.json()["current"]["planning_household_size"] == 3
    assert (
        recipe_client.post(
            "/api/household-profiles", json={**legacy, "members": [{"name": "A", "servings_per_meal": 0.2}]}
        ).status_code
        == 422
    )
    profile_id = created.json()["id"]
    quarter = {**legacy, "expected_version": 1, "members": [{"name": "A", "servings_per_meal": 0.25}]}
    response = recipe_client.put(f"/api/household-profiles/{profile_id}", json=quarter)
    assert response.status_code == 200, response.text
    assert response.json()["current"]["planning_household_size"] == 1


def test_profile_rules_are_checked_on_save(recipe_client):
    bad = [
        payload(presence_rules=[{**RULE, "member_name": "Tom"}]),
        payload(missing_basics=["curry_paste"]),
        payload(nutrition_limits=[{"nutrient": "sugar_g", "max_value": 30}]),
        payload(members=[{"name": "Ann", "default_present": False}], presence_rules=[]),
        payload(members=[{"name": "Mei", "age_band": "child"}], presence_rules=[]),  # HPB has no child limit
        payload(presence_rules=[{**RULE, "dates": ["2026-11-01"]}]),
    ]
    for body in bad:
        assert recipe_client.post("/api/household-profiles", json=body).status_code == 422, body
    stated = payload(
        members=[{"name": "Mei", "age_band": "child"}],
        presence_rules=[],
        nutrition_limits=[{"nutrient": "sodium_mg", "max_value": 1500}],
    )
    assert recipe_client.post("/api/household-profiles", json=stated).status_code == 201


def test_reference_lists_hpb_defaults_and_the_basics(recipe_client):
    response = recipe_client.get("/api/household-profiles/reference")
    assert response.status_code == 200, response.text
    reference = response.json()
    assert reference["default_servings"]["teen"]["male"]["moderate"]["none"] == 1.35
    assert reference["default_servings"]["adult"]["any"]["moderate"]["fat_loss"] == 0.9
    assert reference["default_servings"]["teen"]["male"]["high"]["none"] == 1.55
    assert reference["sodium_limit_mg"]["adult"] == 2000 and reference["sodium_limit_mg"]["child"] is None
    assert {"salt", "soy_sauce"} <= {item["normalized_name"] for item in reference["basics"]}
    assert len(reference["sources"]) == 2


def test_parse_rule_reads_a_sentence_and_stores_nothing(recipe_client):
    body = {
        "kind": "presence",
        "text": "孩子工作日午饭在学校吃",
        "members": [{"name": "Ann", "age_band": "adult"}, {"name": "Mei", "age_band": "child"}],
        "speaker": "Ann",
    }
    response = recipe_client.post("/api/household-profiles/parse-rule", json=body)
    assert response.status_code == 200, response.text
    result = response.json()
    assert result["provider"] == "rules" and result["fell_back"] is False and result["issues"] == []
    assert [rule["restatement"] for rule in result["rules"]] == ["Monday to Friday, lunch: Mei eats elsewhere."]
    assert recipe_client.get("/api/household-profiles/current").status_code == 404
    timed = recipe_client.post(
        "/api/household-profiles/parse-rule", json={**body, "kind": "cooking_time", "text": "周末晚饭一个小时"}
    ).json()
    assert [rule["max_minutes"] for rule in timed["rules"]] == [60]


# --- The shared-dish model through the API (layer 08 PR-4, ADR-0071 sections 1 and 2) ----------------------


def test_a_profile_keeps_each_members_own_limits_and_the_household_wide_allergens(recipe_client):
    body = payload(
        members=[
            {"name": "Ann", "servings_per_meal": 1, "dietary_preferences": ["vegetarian"]},
            {"name": "Ben", "servings_per_meal": 1, "allergens": ["shellfish"], "excluded_ingredients": ["Pork"]},
            {"name": "Mei", "servings_per_meal": 1, "allergens": ["peanut"], "self_only_allergens": ["Peanut"]},
        ],
        presence_rules=[],
    )
    created = recipe_client.post("/api/household-profiles", json=body)
    assert created.status_code == 201, created.text
    current = created.json()["current"]
    members = {m["name"]: m for m in current["members"]}
    assert members["Mei"]["self_only_allergens"] == ["peanut"]
    assert members["Ann"]["self_only_allergens"] == []
    # The whole household avoids shellfish, which nobody marked; peanut stays Mei's own.
    assert current["allergens"] == ["shellfish"]
    # The exclusion and diet union columns stay written for compatibility, and planning no longer reads them.
    assert current["excluded_ingredients"] == ["pork"] and current["dietary_preferences"] == ["vegetarian"]


def test_only_an_allergen_the_member_has_may_be_marked_as_theirs_alone(recipe_client):
    body = payload(
        members=[{"name": "Ann", "servings_per_meal": 1, "self_only_allergens": ["peanut"]}], presence_rules=[]
    )
    response = recipe_client.post("/api/household-profiles", json=body)
    assert response.status_code == 422, response.text
    assert "peanut" in response.text


def test_a_plan_from_a_profile_carries_each_members_limits_and_not_the_union(recipe_client):
    body = payload(
        members=[
            {"name": "Ann", "servings_per_meal": 1, "dietary_preferences": ["vegetarian"]},
            {"name": "Ben", "servings_per_meal": 1, "excluded_ingredients": ["pork"]},
        ],
        presence_rules=[],
    )
    created = recipe_client.post("/api/household-profiles", json=body)
    assert created.status_code == 201, created.text
    planned = recipe_client.post(f"/api/household-profiles/{created.json()['id']}/plans", json={"day_count": 1})
    assert planned.status_code == 201, planned.text
    week = planned.json()["plan"]
    # Each dish says who at the meal cannot eat it, so the plan can show "Not for Ann" beside it. Ann's own
    # diet no longer removes a dish for everyone: it only takes her off that dish.
    for dish in week["days"]:
        vegetarian = {"vegetarian", "vegan"} & set(dish["recipe"]["dietary_tags"])
        assert ("Ann" in dish["not_for"]) is not bool(vegetarian)
        assert "Ben" not in dish["not_for"]
