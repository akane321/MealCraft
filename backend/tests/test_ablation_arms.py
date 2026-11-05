"""The product and its ablations run as arms of the shared baseline runner, offline (fixture parser, no network)."""

import hashlib
import json
from datetime import date
from functools import cache, partial

import pytest

from app.core import clock
from app.core.config import ABLATIONS, get_settings
from app.core.paths import repository_root
from app.evaluation import ablation_arms, baseline_arms, general_agent_baseline, rag_baseline, strong_rule_baseline
from app.evaluation.baseline_resources import load_resources
from app.evaluation.conversation_adapter import RuntimeConfig
from app.evaluation.meal_day_week_runner import product_database
from app.planning.retailers import is_fairprice_only

DEV = repository_root() / "data/evaluation/dev/v3-meal-day-week/episodes"
ANCHOR = date(2026, 9, 28)
CONFIG = RuntimeConfig(anchor_date=ANCHOR)
EPISODE = "mdw-dev-001"


@cache
def resources():
    return load_resources()


def dev(name: str) -> dict:
    return json.loads((DEV / f"{name}.json").read_text(encoding="utf-8"))


@pytest.fixture
def sessions():
    """The episode's drawn pool, imported by the product's importer, in place of the whole release catalog."""
    with product_database(dev(EPISODE)) as factory:
        yield factory


def run(arm_id: str, sessions) -> dict:
    arm = ablation_arms.ablation_arms(partial(ablation_arms.InProcessClient, sessions=sessions))[arm_id]
    context = baseline_arms.ArmContext(resources=resources())
    return baseline_arms.run_case(arm, dev(EPISODE), 0, config=CONFIG, context=context)


def test_a_development_episode_is_planned_by_the_product_and_scored_like_the_baselines(sessions):
    record = run("mealcraft", sessions)
    assert record["errors"] == [] and record["valid_output"] is True
    assert record["response"]["status"] == "plan"
    assert record["scored"] and "error" not in record["scored"]
    assert record["scored"]["dishes"][0]["mappings"]
    assert record["cost_usd"] == 0.0 and record["fingerprint"]["ablation"] is None


def test_a_case_runs_with_its_switch_and_the_anchor_day_and_restores_the_settings(sessions):
    settings = get_settings()
    before = (settings.evaluation_ablation, settings.environment, settings.agent_parser_provider)
    seen: list[tuple] = []

    def spy():  # the product opens its database inside each request: what the product sees there
        current = get_settings()
        switches = (current.evaluation_ablation, current.environment, current.openai_api_key)
        seen.append((*switches, clock.today(), is_fairprice_only()))
        return sessions()

    record = run("mealcraft/ablation/repair_off", spy)
    assert record["valid_output"] is True and record["system_id"] == "mealcraft/ablation/repair_off"
    assert seen and set(seen) == {("repair_off", "test", None, ANCHOR, True)}
    assert not is_fairprice_only()
    assert (settings.evaluation_ablation, settings.environment, settings.agent_parser_provider) == before


def test_the_runner_offers_the_baselines_the_product_and_its_six_ablations():
    available = baseline_arms.arms()
    baselines = {strong_rule_baseline.SYSTEM_ID, rag_baseline.SYSTEM_ID, general_agent_baseline.SYSTEM_ID}
    product = {"mealcraft", *(f"mealcraft/ablation/{name}" for name in ABLATIONS)}
    assert set(available) == baselines | product and len(available) == 10
    assert not any(available[name].paid for name in product)


def test_the_fingerprint_names_the_switch_the_code_the_data_and_the_parser(monkeypatch):
    # No git in CI's container: the revision comes from CODE_COMMIT and each tree id from a stand-in `git`.
    monkeypatch.setenv("CODE_COMMIT", "c" * 40)
    monkeypatch.setattr(baseline_arms, "_git", lambda *arguments: hashlib.sha1(arguments[-1].encode()).hexdigest())
    printed = baseline_arms.arms()["mealcraft/ablation/retrieval_off"].fingerprint()
    assert printed["system_id"] == "mealcraft/ablation/retrieval_off" and printed["ablation"] == "retrieval_off"
    assert printed["parser_provider"] == "fixture" and printed["parser_model"] == get_settings().openai_model
    assert len(printed["runner_sha256"]) == 64
    assert printed["code_commit"] == "c" * 40
    assert printed["data_tree"] == hashlib.sha1(b"HEAD:data").hexdigest()
    assert len(printed["release_tree"]) == 40 and printed["release_tree"] != printed["data_tree"]
