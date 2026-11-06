"""The conversation-protocol baseline runner and the strong-rule arm, offline only (no model, no network)."""

import json
from dataclasses import replace
from datetime import date, datetime
from functools import cache

import pytest

from app.core import clock
from app.core.paths import repository_root
from app.evaluation import baseline_arms, strong_rule_baseline
from app.evaluation.baseline_resources import load_resources
from app.evaluation.conversation_adapter import PlanDish, PlanMeal, PlanOutput, UnifiedOutput

DEV = repository_root() / "data/evaluation/dev/v3-meal-day-week/episodes"
MONDAY_NOON = datetime(2026, 9, 28, 12, tzinfo=clock.SINGAPORE)


@cache
def resources():
    return load_resources()


def dev(name: str) -> dict:
    return json.loads((DEV / f"{name}.json").read_text(encoding="utf-8"))


def test_turns_are_the_users_own_strings_only():
    episode = {
        "scenario": {
            "user_request": "And no pork.",
            "conversation_history": [
                {"role": "user", "content": "Two of us, dinners."},
                {"role": "assistant", "content": "Sure."},
            ],
            "household_profile": {"household_size": 2},
        },
        "gold": {"class": "plan"},
    }
    assert baseline_arms.episode_turns(episode) == ["Two of us, dinners.", "And no pork."]


def test_a_plan_becomes_the_ingredient_level_answer_with_weekday_slots():
    dish = PlanDish(
        name="Chicken rice",
        role="main",
        servings=2,
        evidence={
            "ingredients": [{"name": "chicken", "quantity_g": 300}],
            "steps": ["Cook."],
            "cooking_time_minutes": 30,
        },
    )
    output = UnifiedOutput(plan=PlanOutput(meals=[PlanMeal(date=date(2026, 9, 29), meal_type="dinner", dishes=[dish])]))
    response = baseline_arms.to_baseline_response(output, episode_id="e1", system_id="arm")
    assert response.status == "plan"
    assert response.plan.meals[0].slot_id == "tue-dinner"
    assert response.plan.meals[0].dishes[0].ingredients[0].quantity_g == 300


def test_a_dish_without_ingredient_evidence_is_an_invalid_output_not_a_plan():
    output = UnifiedOutput(
        plan=PlanOutput(meals=[PlanMeal(date=date(2026, 9, 29), meal_type="dinner", dishes=[PlanDish(name="Soup")])])
    )
    with pytest.raises(ValueError):
        baseline_arms.to_baseline_response(output, episode_id="e1", system_id="arm")


def test_no_plan_is_a_clarification_or_infeasible():
    asked = baseline_arms.to_baseline_response(
        UnifiedOutput(clarification=["How many?"]), episode_id="e", system_id="a"
    )
    refused = baseline_arms.to_baseline_response(UnifiedOutput(refusal="No."), episode_id="e", system_id="a")
    assert (asked.status, refused.status) == ("clarification", "infeasible")


@pytest.mark.parametrize(
    ("text", "expected"),
    [
        (
            "Two of us. Plan breakfast and dinner every day this week: one breakfast dish, and dinner with a main "
            "and a vegetable when it fits.",
            {"breakfast": ("main",), "dinner": ("main", "vegetable")},
        ),
        (
            "四口之家。午餐一道菜就够了，晚餐要一荤一素一汤。",
            {"lunch": ("main",), "dinner": ("main", "vegetable", "soup")},
        ),
        (
            "Six of us and we eat big dinners: two different meat dishes, a vegetable dish and a soup every night.",
            {"dinner": ("main", "main-2", "vegetable", "soup")},
        ),
        ("Two of us, three meals a day.", {"breakfast": ("main",), "lunch": ("main",), "dinner": ("main",)}),
        ("Plan something for us.", {"dinner": ("main",)}),
    ],
)
def test_meals_and_dishes_are_read_by_keyword_rules(text, expected):
    assert strong_rule_baseline.read_meals(text, None) == expected


def test_the_request_is_read_with_the_rule_parser():
    request = strong_rule_baseline.read_request(
        ["Three of us, one is allergic to eggs. Breakfast, lunch and dinner every day, no pork."], MONDAY_NOON
    )
    assert request.household_size == 3
    assert "egg" in request.allergens
    assert {"pork", "bacon"} <= request.excluded
    assert (request.start, request.days) == (date(2026, 9, 28), 7)
    assert strong_rule_baseline.read_request(["四口之家，晚餐一荤一素。"], MONDAY_NOON).household_size == 4
    assert strong_rule_baseline.read_request(["Just me, dinners."], MONDAY_NOON).household_size == 1


def test_a_missing_household_size_is_asked_for():
    output = strong_rule_baseline.respond_to(["Plan dinners."], MONDAY_NOON, resources(), repository_root())
    assert output.plan is None and output.clarification == [strong_rule_baseline.CLARIFY_SIZE]


def test_the_strong_rule_plan_keeps_its_rules():
    request = strong_rule_baseline.read_request(
        [
            "Three of us, one is allergic to eggs. Dinner with a main and a vegetable, no pork. Please don't serve "
            "any dish twice."
        ],
        MONDAY_NOON,
    )
    output = strong_rule_baseline.plan(request, resources(), repository_root())
    facts = resources().ingredient_facts
    dishes = [dish for meal in output.plan.meals for dish in meal.dishes]
    assert len(output.plan.meals) == 7 and all(len(meal.dishes) == 2 for meal in output.plan.meals)
    names = [dish.recipe_reference for dish in dishes]
    assert len(names) == len(set(names))  # no repeats when the user says so
    by_name = {name: key for key, name in resources().names.items()}
    for dish in dishes:
        for line in dish.evidence["ingredients"]:
            key = by_name[line["name"]]
            assert key not in request.excluded
            assert "egg" not in (facts[key].allergens or ())


def test_the_runner_scores_the_strong_rule_arm_on_development_episodes(tmp_path, capsys):
    episodes = tmp_path / "episodes"
    episodes.mkdir()
    for name in ("mdw-dev-005", "mdw-dev-010"):
        (episodes / f"{name}.json").write_text(json.dumps(dev(name), ensure_ascii=False), encoding="utf-8")
    output = tmp_path / "strong-rule.jsonl"
    argv = ["--arm", "strong-rule", "--episodes", str(episodes), "--anchor-date", "2026-09-28", "--output", str(output)]
    assert baseline_arms.main(argv, resource_loader=resources) == 0
    records = [json.loads(line) for line in output.read_text(encoding="utf-8").splitlines()]
    assert [row["episode_id"] for row in records] == ["mdw-dev-005", "mdw-dev-010"]
    assert all(row["valid_output"] and row["cost_usd"] == 0.0 for row in records)
    assert all(row["scored"]["dishes"][0]["mappings"] for row in records)
    assert records[1]["scored"]["allergen_safe"] is True
    report = json.loads(output.with_suffix(".report.json").read_text(encoding="utf-8"))
    assert report["answered"] == 2 and report["anchor_date"] == "2026-09-28"
    # A rerun into the same output skips what is answered and keeps the records byte for byte.
    before = output.read_bytes()
    assert baseline_arms.main(argv, resource_loader=resources) == 0
    assert output.read_bytes() == before


def test_the_runner_refuses_a_heldout_path_and_an_unknown_arm(tmp_path):
    with pytest.raises(SystemExit):
        baseline_arms.main(["--arm", "nope", "--fingerprint"])
    with pytest.raises(SystemExit):
        baseline_arms.main(
            [
                "--arm",
                "strong-rule",
                "--episodes",
                str(tmp_path / "heldout"),
                "--anchor-date",
                "2026-09-28",
                "--output",
                str(tmp_path / "out.jsonl"),
            ]
        )


def test_the_fingerprint_names_the_arm_and_its_source():
    printed = strong_rule_baseline.fingerprint()
    assert printed["system_id"] == "strong-rule" and len(printed["runner_sha256"]) == 64


# The RAG arm, with a fake embedder and a fake model: no network.


class FakeChat:
    def __init__(self, contents):
        self.contents = list(contents)
        self.calls = []
        self.embed = lambda texts: [[1.0] * 256 for _ in texts]

    def invoke(self, messages):
        from types import SimpleNamespace

        self.calls.append(messages)
        return SimpleNamespace(
            content=self.contents.pop(0), usage_metadata={"input_tokens": 5000, "output_tokens": 800}
        )


def rag_plan(reference: str) -> str:
    return json.dumps(
        {
            "plan": {
                "household_size": 2,
                "meals": [
                    {
                        "date": "2026-09-28",
                        "meal_type": "dinner",
                        "dishes": [
                            {"name": "From the list", "role": "main", "recipe_reference": reference, "servings": 2}
                        ],
                    }
                ],
                "total_cost_sgd": 9.0,
            }
        }
    )


def rag_context(chat, max_usd=5.0):
    Budget = baseline_arms.LedgerBudget

    return baseline_arms.ArmContext(
        resources=resources(), budget=Budget("gpt-5.4-mini", max_usd, 10_000_000), model=chat
    )


def test_rag_lists_candidates_and_fills_a_listed_dish_from_the_catalog():
    from app.evaluation import rag_baseline

    data = rag_baseline.catalog()
    reference = next(key for key, row in data.recipes.items() if row["course"] == "main")
    chat = FakeChat(["not json", rag_plan(reference)])  # one malformed answer is asked again once
    context = rag_context(chat)
    respond = rag_baseline.make_responder(context, sleep=lambda _: None)
    output = respond("Two of us, dinner tonight.", (), "SHARED")
    system = chat.calls[0][0][1]
    assert system.startswith("SHARED\n\n") and "CANDIDATES" in system
    assert len(system.split("CANDIDATES")[1].strip().splitlines()) > rag_baseline.PER_GROUP
    dish = output.plan.meals[0].dishes[0]
    assert dish.evidence["source"] == "catalog" and dish.evidence["ingredients"]
    assert context.budget.calls == 3  # the embedding and two chat calls, all charged
    response = baseline_arms.to_baseline_response(output, episode_id="e", system_id="rag")
    assert response.plan.meals[0].slot_id == "mon-dinner"


def test_rag_stops_before_a_call_its_cap_cannot_cover():
    from app.evaluation import rag_baseline
    from app.evaluation.pure_llm_baseline import BudgetExhausted

    chat = FakeChat([])
    respond = rag_baseline.make_responder(rag_context(chat, max_usd=0.001), sleep=lambda _: None)
    with pytest.raises(BudgetExhausted):
        respond("Two of us, dinner tonight.", (), "SHARED")
    assert chat.calls == []


def test_rag_dry_run_prints_a_worst_case_without_the_network(capsys, tmp_path):
    argv = [
        "--arm", "rag", "--episodes", str(DEV / "mdw-dev-001.json"), "--anchor-date", "2026-09-28",
        "--output", str(tmp_path / "rag.jsonl"),
    ]  # fmt: skip
    assert baseline_arms.main(argv) == 0
    printed = json.loads(capsys.readouterr().out)
    assert printed["dry_run"] and printed["max_calls"] == 4 and 0 < printed["worst_case_usd"] < 1
    assert not (tmp_path / "rag.jsonl").exists()


# The general-agent arm, with a fake Responses client: no network.


class FakeResponses:
    def __init__(self, responses):
        self.responses = list(responses)
        self.requests = []

    def create(self, **arguments):
        self.requests.append(arguments)
        return self.responses.pop(0)


def agent_response(output, text="", input_tokens=3000, output_tokens=500):
    from types import SimpleNamespace

    return SimpleNamespace(
        output=output,
        output_text=text,
        usage=SimpleNamespace(input_tokens=input_tokens, output_tokens=output_tokens),
    )


AGENT_PLAN = json.dumps(
    {
        "plan": {
            "household_size": 2,
            "meals": [
                {
                    "date": "2026-09-28",
                    "meal_type": "dinner",
                    "dishes": [
                        {
                            "name": "Chicken rice",
                            "role": "main",
                            "servings": 2,
                            "evidence": {
                                "ingredients": [{"name": "chicken breast", "quantity_g": 300}],
                                "steps": ["Cook."],
                                "cooking_time_minutes": 30,
                            },
                        }
                    ],
                }
            ],
        }
    }
)


@pytest.mark.parametrize(
    ("expression", "result"),
    [("3*4.5 + 2", "15.5"), ("(1+2)/4", "0.75"), ("__import__('os')", None), ("2**1000", None), ("1/0", None)],
)
def test_the_calculator_does_arithmetic_only(expression, result):
    from app.evaluation.general_agent_baseline import calculate

    answer = calculate(expression)
    assert answer == result if result is not None else answer.startswith("error")


def test_the_general_agent_uses_its_tools_and_pays_for_searches():
    from types import SimpleNamespace

    from app.evaluation import general_agent_baseline as agent

    Budget = baseline_arms.LedgerBudget

    responses = FakeResponses(
        [
            agent_response(
                [
                    SimpleNamespace(model_dump=lambda **_: {"type": "web_search_call", "action": {"query": "rice"}}),
                    {
                        "type": "function_call",
                        "name": "calculator",
                        "call_id": "c1",
                        "arguments": '{"expression": "2*3"}',
                    },
                ]
            ),
            agent_response([{"type": "message"}], text=AGENT_PLAN),
        ]
    )
    budget = Budget("gpt-5.4-mini", 5.0, 10_000_000)
    trace: list = []
    context = baseline_arms.ArmContext(
        resources=resources(), budget=budget, model=SimpleNamespace(responses=responses), trace=trace
    )
    output = agent.make_responder(context)("Two of us, dinner tonight.", (), "SHARED")
    first, second = responses.requests
    assert {tool["type"] for tool in first["tools"]} == {"web_search", "function"}
    web = next(tool for tool in first["tools"] if tool["type"] == "web_search")
    assert web["filters"]["blocked_domains"] == ["github.com", "githubusercontent.com"]
    assert first["include"] == ["web_search_call.action.sources"]
    assert "text" not in first and "text" not in second  # OpenAI refuses JSON mode with web search
    assert [step["tool"] for step in trace] == ["response", "web_search", "calculator", "response"]
    assert trace[0]["searches"] == 1 and "raw" in trace[0]
    assert first["input"][0]["content"].startswith("SHARED\n\n")
    assert second["input"][-1] == {"type": "function_call_output", "call_id": "c1", "output": "6"}
    assert output.plan.meals[0].dishes[0].evidence["ingredients"][0]["quantity_g"] == 300
    tokens_only = 2 * (3000 * 0.75 + 500 * 4.5) / 1_000_000
    assert budget.spent_usd == pytest.approx(tokens_only + agent.SEARCH_USD)


def test_the_general_agent_parses_a_plan_wrapped_in_prose():
    from app.evaluation import general_agent_baseline as agent

    assert agent.json_text(f"Here is the plan:\n{AGENT_PLAN}\nSources: [1]") == AGENT_PLAN
    assert agent.json_text("no plan") == "no plan"


def test_the_general_agent_has_no_tools_on_its_last_step_and_stops_at_its_cap():
    from types import SimpleNamespace

    from app.evaluation import general_agent_baseline as agent
    from app.evaluation.pure_llm_baseline import BudgetExhausted

    Budget = baseline_arms.LedgerBudget
    call = {"type": "function_call", "name": "calculator", "call_id": "c", "arguments": '{"expression": "1"}'}
    responses = FakeResponses(
        [agent_response([call]) for _ in range(agent.MAX_STEPS - 1)] + [agent_response([], text=AGENT_PLAN)]
    )
    context = baseline_arms.ArmContext(
        resources=resources(),
        budget=Budget("gpt-5.4-mini", 5.0, 10_000_000),
        model=SimpleNamespace(responses=responses),
    )
    agent.make_responder(context)("Plan dinner.", (), "SHARED")
    assert "tools" not in responses.requests[-1] and len(responses.requests) == agent.MAX_STEPS

    broke = baseline_arms.ArmContext(
        resources=resources(), budget=Budget("gpt-5.4-mini", 0.01, 10_000_000), model=SimpleNamespace(responses=None)
    )
    with pytest.raises(BudgetExhausted):
        agent.make_responder(broke)("Plan dinner.", (), "SHARED")


def test_the_mapping_review_reads_arm_records_byte_for_byte(tmp_path):
    from app.evaluation import baseline_mapping_review as review

    episodes = tmp_path / "episodes"
    episodes.mkdir()
    (episodes / "mdw-dev-013.json").write_text(json.dumps(dev("mdw-dev-013")), encoding="utf-8")
    output = tmp_path / "strong-rule.jsonl"
    argv = ["--arm", "strong-rule", "--episodes", str(episodes), "--anchor-date", "2026-09-28", "--output", str(output)]
    assert baseline_arms.main(argv, resource_loader=resources) == 0
    payload = review.load_population([output, output])
    assert payload["schema_version"] == review.ARM_RECORDS_SCHEMA and len(payload["records"]) == 2
    first = review.generate_review_rows(review.load_population([output]), names=resources().names)
    again = review.generate_review_rows(review.load_population([output]), names=resources().names)
    assert first == again and first
    assert {row["system_id"] for row in first} == {"strong-rule"}
    assert all(row["personally_reviewed"] is None and row["decision"] is None for row in first)
    with pytest.raises(ValueError):
        review.load_population([output, tmp_path / "comparison.json"])


# The arm's spend ledger (owner review on #427): every paid call is reserved, then charged or settled.


def fake_paid_arm(calls_per_case: int, usd_per_call: float):
    def responder(context):
        def respond(message, own_history, instructions):
            for _ in range(calls_per_case):
                context.budget.paid(lambda: None, 0, 0, extra_usd=usd_per_call)
                context.budget.charge(baseline_arms.Usage(0, 0), extra_usd=usd_per_call, call="fake")
            return UnifiedOutput(answer="done")

        return respond

    return baseline_arms.Arm(
        system_id="fake-paid",
        paid=True,
        fingerprint=lambda: {"system_id": "fake-paid"},
        responder=responder,
        model_factory=lambda name: object(),
    )


def test_a_case_cut_by_the_cap_is_still_charged_and_later_runs_spend_nothing(tmp_path):
    episodes = tmp_path / "episodes"
    episodes.mkdir()
    for name in ("mdw-dev-001", "mdw-dev-002"):
        (episodes / f"{name}.json").write_text(json.dumps(dev(name), ensure_ascii=False), encoding="utf-8")
    ledger = tmp_path / "fake.spend.jsonl"
    arm = fake_paid_arm(calls_per_case=4, usd_per_call=0.30)
    argv = [
        "--arm", "fake-paid", "--episodes", str(episodes), "--anchor-date", "2026-09-28",
        "--output", str(tmp_path / "out.jsonl"), "--ledger", str(ledger), "--live", "--max-usd", "1.0",
    ]  # fmt: skip
    totals = []
    for _ in range(3):
        assert baseline_arms.main(argv, registry=lambda: {"fake-paid": arm}, resource_loader=resources) == 0
        totals.append(baseline_arms.ledger_totals(ledger)[0])
    assert totals == pytest.approx([0.90, 0.90, 0.90])
    report = json.loads((tmp_path / "out.report.json").read_text(encoding="utf-8"))
    assert report["spend"]["usd"] == pytest.approx(0.90) and report["spend"]["stop_reason"].startswith("spend cap")


def test_a_reserve_with_no_charge_counts_at_its_worst_case(tmp_path):
    ledger = tmp_path / "arm.spend.jsonl"
    ledger.write_text(json.dumps({"event": "reserve", "usd": 0.50, "total_tokens": 100}) + "\n", encoding="utf-8")
    spent, tokens = baseline_arms.ledger_totals(ledger)
    assert (spent, tokens) == (0.50, 100)
    budget = baseline_arms.LedgerBudget("gpt-5.4-mini", 1.0, 10_000_000, spent_usd=spent, ledger=ledger)
    with pytest.raises(baseline_arms.BudgetExhausted):
        budget.reserve(0, 0, extra_usd=0.60)


def test_a_refused_call_writes_no_reserve_and_an_unbilled_error_is_settled_at_zero(tmp_path):
    ledger = tmp_path / "arm.spend.jsonl"
    budget = baseline_arms.LedgerBudget("gpt-5.4-mini", 1.0, 10_000_000, ledger=ledger)
    with pytest.raises(baseline_arms.BudgetExhausted):
        budget.reserve(0, 0, extra_usd=2.0)
    assert not ledger.exists()
    budget.stop_reason = None

    class BadRequest(Exception):
        status_code = 400

    def refused():
        raise BadRequest("json_object with tools")

    with pytest.raises(BadRequest):
        budget.paid(refused, 0, 0, extra_usd=0.20)
    rows = [json.loads(line) for line in ledger.read_text(encoding="utf-8").splitlines()]
    assert [row["event"] for row in rows] == ["reserve", "charge"] and rows[1]["usd"] == 0.0
    assert baseline_arms.ledger_totals(ledger)[0] == 0.0

    def timed_out():
        raise TimeoutError("may have been billed")

    with pytest.raises(TimeoutError):
        budget.paid(timed_out, 0, 0, extra_usd=0.20)
    assert baseline_arms.ledger_totals(ledger)[0] == pytest.approx(0.20)
    assert budget.spent_usd == pytest.approx(0.20)


def test_the_general_agents_charge_carries_its_search_fees(tmp_path):
    from types import SimpleNamespace

    from app.evaluation import general_agent_baseline as agent

    search = {"type": "web_search_call", "action": {"query": "rice price"}}
    responses = FakeResponses([agent_response([search, search, {"type": "message"}], text=AGENT_PLAN)])
    ledger = tmp_path / "agent.spend.jsonl"
    budget = baseline_arms.LedgerBudget("gpt-5.4-mini", 5.0, 10_000_000, ledger=ledger, episode_id="e1")
    context = baseline_arms.ArmContext(resources=resources(), budget=budget, model=SimpleNamespace(responses=responses))
    agent.make_responder(context)("Two of us, dinner tonight.", (), "SHARED")
    charge = [json.loads(line) for line in ledger.read_text(encoding="utf-8").splitlines()][-1]
    tokens_only = (3000 * 0.75 + 500 * 4.5) / 1_000_000
    assert charge["searches"] == 2 and charge["episode_id"] == "e1"
    assert charge["usd"] == pytest.approx(tokens_only + 2 * agent.SEARCH_USD)


def test_a_dry_run_counts_what_the_arms_ledger_already_spent(tmp_path, capsys):
    episodes = tmp_path / "episodes"
    episodes.mkdir()
    (episodes / "mdw-dev-001.json").write_text(json.dumps(dev("mdw-dev-001"), ensure_ascii=False), encoding="utf-8")
    ledger = tmp_path / "fake.spend.jsonl"
    ledger.write_text(json.dumps({"event": "charge", "usd": 0.80, "total_tokens": 0}) + "\n", encoding="utf-8")
    arm = replace(fake_paid_arm(1, 0.30), estimate=lambda turns, instructions, model: (1, 10, 0.30))
    argv = [
        "--arm", "fake-paid", "--episodes", str(episodes), "--anchor-date", "2026-09-28",
        "--output", str(tmp_path / "out.jsonl"), "--ledger", str(ledger), "--max-usd", "1.0",
    ]  # fmt: skip
    assert baseline_arms.main(argv, registry=lambda: {"fake-paid": arm}, resource_loader=resources) == 0
    report = json.loads(capsys.readouterr().out)
    assert report["ledger_usd"] == pytest.approx(0.80) and report["fits_cap"] is False


def test_the_arms_own_cap_is_the_default_and_the_ceiling(tmp_path, capsys):
    from app.evaluation import general_agent_baseline, rag_baseline

    assert general_agent_baseline.ARM.max_usd == 15.0 and rag_baseline.ARM.max_usd == 5.0
    episodes = tmp_path / "episodes"
    episodes.mkdir()
    (episodes / "mdw-dev-001.json").write_text(json.dumps(dev("mdw-dev-001"), ensure_ascii=False), encoding="utf-8")
    arm = replace(fake_paid_arm(1, 0.30), estimate=lambda turns, instructions, model: (1, 10, 0.30), max_usd=2.0)
    argv = [
        "--arm", "fake-paid", "--episodes", str(episodes), "--anchor-date", "2026-09-28",
        "--output", str(tmp_path / "out.jsonl"), "--ledger", str(tmp_path / "fake.spend.jsonl"),
    ]  # fmt: skip
    assert baseline_arms.main(argv, registry=lambda: {"fake-paid": arm}, resource_loader=resources) == 0
    assert json.loads(capsys.readouterr().out)["max_usd"] == 2.0
    with pytest.raises(SystemExit):
        baseline_arms.main([*argv, "--max-usd", "2.5"], registry=lambda: {"fake-paid": arm}, resource_loader=resources)


def test_a_held_out_ledger_line_carries_no_episode_id(tmp_path):
    ledger = tmp_path / "arm.spend.jsonl"
    budget = baseline_arms.LedgerBudget(
        "gpt-5.4-mini", 1.0, 10_000_000, ledger=ledger, episode_id="e1", record_episodes=False
    )
    budget.paid(lambda: None, 0, 0)
    budget.charge(baseline_arms.Usage(10, 10), call="fake")
    assert all("episode_id" not in json.loads(line) for line in ledger.read_text(encoding="utf-8").splitlines())
