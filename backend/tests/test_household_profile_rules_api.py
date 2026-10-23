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
    # One dish a dinner, so that dish has to suit everyone at the table (ADR-0071 section 1); these two
    # members differ without ruling the small test catalog out between them.
    body = payload(
        members=[
            {"name": "Ann", "servings_per_meal": 1, "excluded_ingredients": ["mushroom"]},
            {"name": "Ben", "servings_per_meal": 1, "excluded_ingredients": ["pork"]},
        ],
        presence_rules=[],
    )
    created = recipe_client.post("/api/household-profiles", json=body)
    assert created.status_code == 201, created.text
    planned = recipe_client.post(f"/api/household-profiles/{created.json()['id']}/plans", json={"day_count": 1})
    assert planned.status_code == 201, planned.text
    week = planned.json()["plan"]
    # Each dish says who at the meal cannot eat it, so the plan can show "Not for Ann" beside it. A member's
    # own exclusion no longer removes a dish for everyone, and a one-dish dinner has to suit them all, so
    # nobody is left off the only dish there is.
    assert week["days"]
    for dish in week["days"]:
        assert dish["not_for"] == []


def test_a_one_dish_dinner_nobody_can_share_is_refused_rather_than_leaving_a_member_unfed(recipe_client):
    """Fix for the review: coverage used to be checked only on the full meal structure, so a one-dish dinner
    could be planned with nothing on it a vegetarian member could eat. Now it is refused instead."""
    body = payload(
        members=[
            {"name": "Ann", "servings_per_meal": 1, "dietary_preferences": ["vegetarian"]},
            {"name": "Ben", "servings_per_meal": 1, "excluded_ingredients": ["pork"]},
        ],
        presence_rules=[],
    )
    created = recipe_client.post("/api/household-profiles", json=body)
    assert created.status_code == 201, created.text
    # A Wednesday, so the weekday 30-minute dinner rule applies whatever day the suite runs on.
    plan = {"day_count": 1, "start_date": "2027-01-06"}
    refused = recipe_client.post(f"/api/household-profiles/{created.json()['id']}/plans", json=plan)
    assert refused.status_code == 422, refused.text


def test_a_size_stated_in_the_conversation_keeps_every_members_limits(recipe_client):
    """The blocker this fixes: saying "plan for 3" replaced the saved members, and their diets, exclusions and
    allergens went with them, so the week could hold meat, pork and peanut for a member who avoids all three.

    With the members gone there is nobody left to hold a limit against, so each one becomes the whole
    household's - the allergens marked "only I avoid it" included, because an allergen with no owner can only
    be read as the household's.
    """
    body = payload(
        members=[
            {
                "name": "Ann",
                "servings_per_meal": 1,
                "allergens": ["peanut"],
                "self_only_allergens": ["peanut"],
                "excluded_ingredients": ["pork"],
                "dietary_preferences": ["vegetarian"],
            },
            {"name": "Bob", "servings_per_meal": 1},
        ],
        presence_rules=[],
    )
    assert recipe_client.post("/api/household-profiles", json=body).status_code == 201

    started = recipe_client.post("/api/agent/sessions", json={"message": "Plan my dinners."})
    assert started.status_code == 201, started.text
    before = started.json()["constraints"]
    # While the members are there, each limit stays with its member and none narrows the household.
    assert before["allergens"] == [] and before["excluded_ingredients"] == []
    assert {m["name"] for m in before["household"]["members"]} == {"Ann", "Bob"}

    session_id = started.json()["id"]
    changed = recipe_client.post(f"/api/agent/sessions/{session_id}/messages", json={"message": "plan for 3"})
    assert changed.status_code in (200, 201), changed.text
    after = changed.json()["constraints"]
    assert after["household_size"] == 3
    assert after["household"]["members"] is None  # the stated size replaced them
    # ... and not one of Ann's limits was lost on the way out.
    assert after["allergens"] == ["peanut"]
    assert after["excluded_ingredients"] == ["pork"]
    assert after["dietary_preferences"] == ["vegetarian"]


def test_a_members_allergen_outside_the_checked_vocabulary_is_refused_on_save(recipe_client):
    """ADR-0024 section 3: an allergen no recipe was ever checked for cannot be honoured. Saving it would leave
    a member whose limit silently does nothing, so the profile refuses it and names the words it does know."""
    for word in ("kiwi", "peanuts"):  # unknown, and the plural of one it knows
        body = payload(members=[{"name": "Ann", "servings_per_meal": 1, "allergens": [word]}], presence_rules=[])
        refused = recipe_client.post("/api/household-profiles", json=body)
        assert refused.status_code == 422, refused.text
        assert word in refused.text and "peanut" in refused.text
    # The vocabulary's own spelling saves.
    body = payload(members=[{"name": "Ann", "servings_per_meal": 1, "allergens": ["peanut"]}], presence_rules=[])
    assert recipe_client.post("/api/household-profiles", json=body).status_code == 201


def test_a_profile_refuses_two_members_with_the_same_name(recipe_client):
    """A presence rule names a member, a coverage failure names one and the plan says a dish is not for one;
    two members called the same are one member to all three."""
    body = payload(
        members=[{"name": "Ann", "servings_per_meal": 1}, {"name": "ann", "servings_per_meal": 1}],
        presence_rules=[],
    )
    refused = recipe_client.post("/api/household-profiles", json=body)
    assert refused.status_code == 422, refused.text
    assert "used more than once" in refused.text
