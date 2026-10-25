import json

import pytest

from app.evaluation import baseline_comparison as runner

FIRST, SECOND, *_ = runner.algorithms.implemented_system_ids()


def episode(identifier="synthetic"):
    return {"episode_id": identifier}


def result(system=FIRST, validation=None):
    return {
        "episode_id": "synthetic",
        "system_id": system,
        "scored": {"validation": validation or {"strict_passed": True, "adjusted_passed": True, "unverified": []}},
    }


def test_disabled_paid_and_human_entries_never_construct_clients():
    for name in ("pure-llm-single-turn", "rag", "generic-agent", "human", "strong-rule"):
        with pytest.raises(ValueError, match="Only offline"):
            runner.default_arms(resources=None, selected={name})


def test_shared_scoring_outcomes_are_reported_without_partial_rescoring(tmp_path):
    arm = runner.Arm(
        FIRST,
        "deterministic",
        lambda _: result(
            validation={"strict_passed": False, "adjusted_passed": True, "unverified": [["coverage", None]]}
        ),
    )
    report = runner.run_comparison(episodes=[episode()], arms=[arm], output_dir=tmp_path / "run", repeats=3)
    assert report["arms"][FIRST]["strict_passed"] == 0
    assert report["arms"][FIRST]["adjusted_passed"] == 1
    assert report["runs"][0]["outcome"]["unverified"] == [["coverage", None]]


@pytest.mark.parametrize("validation", [{"skipped": "no problem"}, {}])
def test_missing_or_skipped_validation_is_unscored_not_passed(tmp_path, validation):
    arm = runner.Arm(
        FIRST,
        "deterministic",
        lambda _: {"episode_id": "synthetic", "system_id": FIRST, "scored": {"validation": validation}},
    )
    report = runner.run_comparison(episodes=[episode()], arms=[arm], output_dir=tmp_path / "run")
    assert report["arms"][FIRST]["unscored_runs"] == 1
    assert report["arms"][FIRST]["strict_passed"] == report["arms"][FIRST]["adjusted_passed"] == 0


def test_failure_is_preserved_and_does_not_abort_other_arms(tmp_path):
    def fail(_):
        raise RuntimeError("synthetic failure")

    arms = [runner.Arm(FIRST, "deterministic", fail), runner.Arm(SECOND, "deterministic", lambda _: result(SECOND))]
    report = runner.run_comparison(episodes=[episode()], arms=arms, output_dir=tmp_path / "run")
    assert report["arms"][FIRST]["failed_runs"] == 1
    assert report["arms"][SECOND]["strict_passed"] == 1
    artifact = tmp_path / "run" / report["runs"][0]["raw_result"]
    assert json.loads(artifact.read_text())["error"]["message"] == "synthetic failure"


def test_new_runs_do_not_reuse_stale_or_failure_cache(tmp_path):
    calls = []
    arm = runner.Arm(FIRST, "deterministic", lambda _: calls.append(True) or result())
    for name in ("first", "second"):
        runner.run_comparison(episodes=[episode()], arms=[arm], output_dir=tmp_path / name)
    assert len(calls) == 2
    with pytest.raises(FileExistsError):
        runner.run_comparison(episodes=[episode()], arms=[arm], output_dir=tmp_path / "first")


def test_stochastic_offline_arm_records_requested_repeats(tmp_path):
    arm = runner.Arm(FIRST, "stochastic", lambda _: result())
    report = runner.run_comparison(episodes=[episode()], arms=[arm], output_dir=tmp_path / "run", repeats=3)
    assert len(report["runs"]) == 3


@pytest.mark.parametrize("identifier", ["../outside", "", "a/b"])
def test_artifact_paths_cannot_escape_output_dir(identifier):
    with pytest.raises(ValueError):
        runner.select_episodes([episode(identifier)], None)


def test_episode_selection_is_explicit():
    with pytest.raises(ValueError, match="unknown"):
        runner.select_episodes([episode()], {"missing"})
    with pytest.raises(ValueError, match="duplicate"):
        runner.select_episodes([episode(), episode()], None)
