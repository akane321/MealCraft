"""The pure-LLM runner with a fake model only: no test here reaches the network or a paid API."""

import json
import shutil
from functools import cache
from types import SimpleNamespace

import httpx
import openai
import pytest
from pydantic import SecretStr

from app.core.paths import repository_root
from app.evaluation import pure_llm_baseline as runner
from app.evaluation.baseline_output import BaselineAnswer
from app.evaluation.baseline_resources import _ingredient_facts, load_resources

DEV_EPISODE = repository_root() / "data/evaluation/dev/v2-multidish/episodes/md-dev-001.json"

ANSWER = {
    "status": "plan",
    "plan": {
        "meals": [
            {
                "slot_id": "mon-dinner",
                "dishes": [
                    {
                        "name": "Chicken rice",
                        "role_id": "main",
                        "servings": 4,
                        "cooking_time_minutes": 30,
                        "steps": ["Poach the chicken.", "Cook the rice in the stock."],
                        "ingredients": [
                            {"name": "chicken breast", "quantity_g": 600},
                            {"name": "rice", "quantity_g": 400},
                            {"name": "mystery paste", "quantity_g": 10},
                        ],
                    }
                ],
            }
        ],
        "total_cost_sgd": 12.5,
        "within_budget": True,
        "constraint_claims": [{"code": "allergen", "satisfied": True}],
    },
}


def reply(parsed, input_tokens=1000, output_tokens=500):
    raw = SimpleNamespace(usage_metadata={"input_tokens": input_tokens, "output_tokens": output_tokens})
    return {"parsed": parsed, "raw": raw, "parsing_error": None if parsed else "bad json"}


class FakeModel:
    def __init__(self, answers):
        self.answers = list(answers)
        self.calls = []

    def invoke(self, messages):
        self.calls.append(messages)
        answer = self.answers.pop(0) if len(self.answers) > 1 else self.answers[0]
        if isinstance(answer, Exception):
            raise answer
        return answer


def timeout():
    return openai.APITimeoutError(request=httpx.Request("POST", "https://api.invalid/v1/chat"))


def budget(max_usd=5.0):
    return runner.Budget("gpt-5.4-mini", max_usd, 10_000_000)


@cache
def resources():
    return load_resources()


def episode():
    return json.loads(DEV_EPISODE.read_text(encoding="utf-8"))


def test_prompt_carries_household_facts_only():
    messages = runner.render_messages(episode())
    text = json.dumps(messages, ensure_ascii=False)
    assert [role for role, _ in messages] == ["system", "human"]
    for leaked in ("RCP2_", "fairprice_product_ids", "recipe_candidate_slugs", "gold", "author_rationale"):
        assert leaked not in text
    assert "family of four" in text


def test_harness_fills_ids_and_retries_one_malformed_answer():
    model = FakeModel([reply(None), reply(BaselineAnswer.model_validate(ANSWER))])
    spend = budget()
    result = runner.generate(episode(), model, spend)
    assert result.response.episode_id == "md-dev-001"
    assert result.response.system_id == runner.SYSTEM_ID
    assert result.attempts == 2 and len(result.parse_errors) == 1
    assert result.usage.total_tokens == 3000
    assert result.cost_usd == pytest.approx(2 * (1000 * 0.75 + 500 * 4.5) / 1e6)
    assert spend.calls == 2


def test_transient_api_error_backs_off_then_answers():
    waits = []
    model = FakeModel([timeout(), reply(ANSWER)])
    result = runner.generate(episode(), model, budget(), sleep=waits.append)
    assert result.response is not None
    assert waits == [runner.BACKOFF_SECONDS[0]]
    assert len(result.api_errors) == 1


def test_persistent_api_error_is_a_failed_call_not_a_crash():
    waits = []
    result = runner.generate(episode(), FakeModel([timeout()]), budget(), sleep=waits.append)
    assert result.call_failed
    assert len(result.api_errors) == runner.API_ATTEMPTS
    assert len(waits) == runner.API_ATTEMPTS - 1


def test_cap_stops_before_a_call_that_could_pass_it():
    model = FakeModel([reply(ANSWER)])
    with pytest.raises(runner.BudgetExhausted):
        runner.generate(episode(), model, budget(max_usd=0.001))
    assert model.calls == []


def write_episodes(directory):
    directory.mkdir(parents=True)
    shutil.copy(DEV_EPISODE, directory / DEV_EPISODE.name)
    return directory


def test_main_defaults_to_a_dry_run_without_the_network(tmp_path, capsys):
    def no_model(_name):
        raise AssertionError("a dry run must not build a model")

    episodes = write_episodes(tmp_path / "episodes")
    output = tmp_path / "out" / "pure.jsonl"
    assert (
        runner.main(["--episodes", str(episodes), "--output", str(output), "--repeats", "3"], model_factory=no_model)
        == 0
    )
    summary = json.loads(capsys.readouterr().out)
    assert (summary["calls"], summary["dry_run"], summary["fits_cap"]) == (3, True, True)
    assert summary["estimated_input_tokens"] > 0
    assert not output.exists()


def test_main_live_writes_records_reports_and_resumes(tmp_path):
    episodes = write_episodes(tmp_path / "episodes")
    output = tmp_path / "out" / "pure.jsonl"
    model = FakeModel([reply(ANSWER)])
    args = ["--episodes", str(episodes), "--output", str(output), "--live", "--repeats", "2"]
    assert runner.main(args, model_factory=lambda _name: model, resource_loader=resources) == 0
    records = runner.read_records(output)
    assert [(row["episode_id"], row["repeat"]) for row in records] == [("md-dev-001", 0), ("md-dev-001", 1)]
    scored = records[0]["scored"]
    assert scored["recomputation"]["unmapped_lines"] == ["mystery paste"]
    assert scored["validation"]["strict_passed"] is False
    report = json.loads(output.with_suffix(".report.json").read_text(encoding="utf-8"))
    assert report["fingerprint"] == runner.freeze_fingerprint()
    assert report["release_version"] == "v2.1"
    assert report["allow_heldout"] is False
    assert report["spend"]["usd"] == pytest.approx(2 * (1000 * 0.75 + 500 * 4.5) / 1e6)
    assert report["run_date"]
    assert len(report["summary"]["per_repeat"]) == 2
    assert report["summary"]["across_repeats"]["valid_output_rate"] == {"mean": 1.0, "stdev": 0.0}

    calls = len(model.calls)
    assert runner.main(args, model_factory=lambda _name: model, resource_loader=resources) == 0
    assert len(model.calls) == calls  # every episode was answered: the rerun calls nothing
    assert len(runner.read_records(output)) == 2


def test_failed_calls_are_retried_on_resume(tmp_path):
    episodes = write_episodes(tmp_path / "episodes")
    output = tmp_path / "pure.jsonl"
    args = ["--episodes", str(episodes), "--output", str(output), "--live"]
    failing = FakeModel([timeout()])
    runner.main(args, model_factory=lambda _name: failing, resource_loader=resources, sleep=lambda _s: None)
    assert runner.read_records(output)[0]["status"] == "call_failed"
    runner.main(args, model_factory=lambda _name: FakeModel([reply(ANSWER)]), resource_loader=resources)
    assert [row["status"] for row in runner.read_records(output)] == ["call_failed", "answered"]


def test_protected_paths_need_the_flag_and_the_flag_is_recorded(tmp_path, capsys):
    episodes = write_episodes(tmp_path / "held-out")
    args = ["--episodes", str(episodes), "--output", str(tmp_path / "out.jsonl")]
    with pytest.raises(SystemExit):
        runner.main(args)
    model = FakeModel([reply(ANSWER)])
    live = [*args, "--live", "--allow-heldout"]
    assert runner.main(live, model_factory=lambda _name: model, resource_loader=resources) == 0
    report = json.loads((tmp_path / "out.report.json").read_text(encoding="utf-8"))
    assert report["allow_heldout"] is True


def test_fingerprint_cli(capsys):
    assert runner.main(["--fingerprint"]) == 0
    printed = json.loads(capsys.readouterr().out)
    assert printed == runner.freeze_fingerprint()
    assert set(printed) == {"system_id", "prompt_sha256", "output_schema_sha256", "runner_sha256"}


def test_request_shape_with_a_mocked_client(monkeypatch):
    seen = {}

    class FakeChat:
        def __init__(self, **kwargs):
            seen["init"] = kwargs

        def with_structured_output(self, schema, **kwargs):
            seen["schema"], seen["structured"] = schema, kwargs
            return "structured-model"

    import langchain_openai

    from app.agent import model_client
    from app.core import config

    monkeypatch.setattr(langchain_openai, "ChatOpenAI", FakeChat)
    monkeypatch.setattr(
        config, "get_settings", lambda: SimpleNamespace(openai_api_key=SecretStr("test"), openai_timeout_seconds=30)
    )
    monkeypatch.setattr(model_client, "http_client", lambda: None)
    assert runner.create_model("gpt-5.4-mini") == "structured-model"
    assert seen["init"]["temperature"] == 0
    assert seen["init"]["model"] == "gpt-5.4-mini"
    assert seen["init"]["max_retries"] == 0
    assert seen["init"]["max_tokens"] == runner.MAX_OUTPUT_TOKENS
    assert seen["schema"] is BaselineAnswer
    assert seen["structured"] == {"method": "json_schema", "strict": True, "include_raw": True}


def test_load_resources_reads_the_frozen_data():
    loaded = resources()
    assert loaded.release_version == "v2.1"
    assert loaded.checked_allergens == {
        "dairy", "egg", "fish", "gluten", "peanut", "sesame", "shellfish", "soy", "tree_nut",
    }  # fmt: skip
    # Snapshot products whose ingredient the release names nothing for: priced, never reachable by a line.
    assert loaded.unnamed_product_ingredients == ("laksa_leaf", "pork_bones", "pork_trotter", "suet", "tripe")
    assert "salt" in loaded.basic_seasonings
    assert loaded.not_bought({"missing_basics": ["salt"]}) >= {"water", "ice"}
    assert "salt" not in loaded.not_bought({"missing_basics": ["salt"]})
    assert loaded.ingredient_facts["soy_sauce"].allergens == ("gluten", "soy")


def test_ingredient_facts_keep_unknown_and_add_curated_allergens(tmp_path):
    release = tmp_path / "data-engineering/data/release/v2.1"
    release.mkdir(parents=True)
    nutrition = {"energy_kcal": 1, "protein_g": 1, "carbohydrate_g": 1, "fat_g": 1, "sodium_mg": 1, "sugar_g": 1}
    rows = [
        {"ingredient_id": "ING_BUTTER", "allergen_status": "confirmed", "allergens": ["milk"],
         "forms": {"ING_BUTTER": {"nutrition_per_100g": nutrition}}},
        {"ingredient_id": "ING_PESTO", "allergen_status": "unreviewed", "allergens": [], "forms": {}},
        {"ingredient_id": "ING_BREAD", "allergen_status": "confirmed", "allergens": [], "forms": {}},
    ]  # fmt: skip
    (release / "ingredients.jsonl").write_text("\n".join(json.dumps(row) for row in rows), encoding="utf-8")
    curated = tmp_path / "data/ingredients/ingredients.json"
    curated.parent.mkdir(parents=True)
    curated.write_text(json.dumps([{"normalized_name": "bread", "allergens": ["gluten"]}]), encoding="utf-8")
    facts = _ingredient_facts(tmp_path)
    assert facts["butter"].allergens == ("dairy",)
    assert facts["butter"].nutrition_per_100g.calories_kcal == 1
    assert facts["pesto"].allergens is None  # unknown stays unknown, never "none"
    assert facts["bread"].allergens == ("gluten",)
    assert facts["bread"].nutrition_per_100g is None


def test_hierarchy_parents_keep_only_one_same_or_variety_parent(tmp_path):
    from app.data.ingredient_hierarchy import FILES
    from app.evaluation.baseline_resources import hierarchy_parents

    real = resources().parents
    assert real["baby_spinach"] == "spinach"
    assert "canned_tomato" not in real  # `same` as canned_tomatoes and a `variety` of tomato: two parents
    directory = tmp_path / "data/ingredients/hierarchy"
    directory.mkdir(parents=True)
    entries = {
        "kid": {"parents": [{"id": "tomato", "relation": "variety"}]},
        "grouped": {"parents": [{"id": "tomato", "relation": "member"}]},
    }
    (directory / next(iter(FILES.values()))).write_text(json.dumps({"entries": entries}), encoding="utf-8")
    assert hierarchy_parents({"tomato": "Tomato"}, tmp_path) == {"kid": "tomato"}


def clarification_episode():
    return json.loads((DEV_EPISODE.parent / "md-dev-009.json").read_text(encoding="utf-8"))


def test_a_plan_for_an_episode_without_a_gold_problem_is_scored_not_crashed():
    response = runner.BaselineResponse.model_validate({**ANSWER, "episode_id": "md-dev-009", "system_id": "x"})
    scored = runner.score(clarification_episode(), response, resources())
    assert "skipped" in scored["validation"]
    assert scored["verification"]["gram_coverage"] < 1


def test_a_scoring_failure_still_writes_the_paid_record(tmp_path, monkeypatch):
    def broken(*_args):
        raise RuntimeError("scorer bug")

    monkeypatch.setattr(runner, "score", broken)
    episodes = write_episodes(tmp_path / "episodes")
    output = tmp_path / "pure.jsonl"
    args = ["--episodes", str(episodes), "--output", str(output), "--live"]
    assert runner.main(args, model_factory=lambda _name: FakeModel([reply(ANSWER)]), resource_loader=resources) == 0
    (record,) = runner.read_records(output)
    assert record["status"] == "answered" and record["cost_usd"] > 0
    assert record["scored"] == {"error": "RuntimeError: scorer bug"}


def test_a_call_without_usage_is_charged_its_worst_case():
    no_usage = {"parsed": BaselineAnswer.model_validate(ANSWER), "raw": SimpleNamespace(), "parsing_error": None}
    spend = budget()
    result = runner.generate(episode(), FakeModel([no_usage]), spend)
    worst_tokens, worst_usd = spend.worst_case(runner.estimate_tokens(runner.render_messages(episode())))
    assert result.usage.total_tokens == worst_tokens
    assert spend.spent_usd == pytest.approx(worst_usd)


def test_resume_survives_a_half_written_line_and_refuses_another_fingerprint(tmp_path):
    episodes = write_episodes(tmp_path / "episodes")
    output = tmp_path / "pure.jsonl"
    args = ["--episodes", str(episodes), "--output", str(output), "--live", "--repeats", "2"]
    model = FakeModel([reply(ANSWER)])
    runner.main(args, model_factory=lambda _name: model, resource_loader=resources)
    first, second = output.read_text(encoding="utf-8").splitlines()
    output.write_text(first + "\n" + second[: len(second) // 2], encoding="utf-8")  # killed mid-write
    assert runner.main(args, model_factory=lambda _name: model, resource_loader=resources) == 0
    assert [row["repeat"] for row in runner.read_records(output)] == [0, 1]
    assert len(model.calls) == 3  # only the lost repeat was asked again

    row = json.loads(first)
    row["fingerprint"] = {**row["fingerprint"], "prompt_sha256": "an older prompt"}
    output.write_text(json.dumps(row) + "\n", encoding="utf-8")
    with pytest.raises(SystemExit):
        runner.main(args, model_factory=lambda _name: model, resource_loader=resources)


def test_dry_run_worst_case_counts_the_malformed_retry(tmp_path, capsys):
    episodes = write_episodes(tmp_path / "episodes")
    runner.main(["--episodes", str(episodes), "--output", str(tmp_path / "o.jsonl")])
    summary = json.loads(capsys.readouterr().out)
    tokens = summary["estimated_input_tokens"]
    one_call = runner.price_usd("gpt-5.4-mini", runner.Usage(tokens, runner.MAX_OUTPUT_TOKENS))
    assert summary["worst_case_usd"] == round(runner.MAX_ATTEMPTS * one_call, 4)
