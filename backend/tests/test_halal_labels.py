import csv
import json

import pytest

from app.core.paths import data_root
from app.data import halal_labels as generator
from app.data.halal import (
    CERTIFICATION_FILE,
    LABELS_FILE,
    OVERRIDES_FILE,
    halal_labels,
    needs_certification,
    recipe_halal_status,
    release_halal_certification,
)
from app.data.ingredient_hierarchy import read_links

SOURCES = {"rule:pork", "rule:alcohol", "rule:doubtful", "rule:may_contain", "rule:meat", "rule:food_group", "human"}


@pytest.fixture(scope="module")
def generated() -> list[dict]:
    return generator.labels(generator.catalog(), read_links())


def test_the_committed_file_is_what_the_generator_writes(generated: list[dict]) -> None:
    committed = json.loads((data_root() / LABELS_FILE).read_text(encoding="utf-8"))["items"]
    assert committed == generated
    assert generator.labels(generator.catalog(), read_links()) == generated  # deterministic


def test_every_catalog_ingredient_has_a_consistent_label(generated: list[dict]) -> None:
    assert {item["normalized_name"] for item in generated} == set(generator.catalog())
    for item in generated:
        assert item["status"] in {"halal", "not_halal", "uncertain"}
        assert item["source"] in SOURCES and item["reason"]
        if item["needs_certification"]:
            assert item["status"] == "halal" and item["source"] == "rule:meat"
        if item["status"] == "not_halal":
            assert item["source"] in {"rule:pork", "rule:alcohol"}


@pytest.mark.parametrize(
    ("name", "status", "certification", "source"),
    [
        ("pork_belly", "not_halal", False, "rule:pork"),
        ("bacon_grease", "not_halal", False, "rule:pork"),
        ("lard", "not_halal", False, "rule:pork"),
        ("mirin", "not_halal", False, "rule:alcohol"),
        ("red_wine", "not_halal", False, "rule:alcohol"),
        ("sausage", "uncertain", False, "rule:may_contain"),
        ("marshmallow", "uncertain", False, "rule:may_contain"),
        ("gelatin", "uncertain", False, "rule:doubtful"),
        ("vanilla", "uncertain", False, "rule:doubtful"),
        ("chicken_breast", "halal", True, "rule:meat"),
        ("beef_broth", "halal", True, "rule:meat"),
        ("turkey_bacon", "halal", True, "rule:meat"),
        ("ramen", "halal", True, "rule:meat"),  # may_contain chicken (flavour packet)
        ("stuffing_mix", "halal", True, "rule:meat"),
        ("salmon", "halal", False, "rule:food_group"),
        ("shrimp_paste", "halal", False, "rule:food_group"),
        ("milk", "halal", False, "rule:food_group"),
        ("broccoli", "halal", False, "rule:food_group"),
        ("vegetarian_ham", "halal", False, "rule:food_group"),
        ("firm_tofu", "halal", False, "rule:food_group"),
    ],
)
def test_rules_decide_the_known_cases(name: str, status: str, certification: bool, source: str) -> None:
    label = halal_labels()[name]
    assert (label["status"], label["needs_certification"], label["source"]) == (status, certification, source)
    assert needs_certification(name) is certification


def test_recipe_status_follows_the_table() -> None:
    assert recipe_halal_status(["broccoli", "milk"]) == "halal"
    assert recipe_halal_status(["broccoli", "chicken_breast"]) == "needs_certification"
    assert recipe_halal_status(["chicken_breast", "sausage"]) == "uncertain"
    assert recipe_halal_status(["chicken_breast", "sausage", "mirin"]) == "not_halal"
    assert recipe_halal_status(["broccoli", "not_in_the_catalog"]) == "uncertain"


def test_the_review_queue_lists_every_doubt_and_a_fixed_sample(generated: list[dict]) -> None:
    with (data_root() / generator.REVIEW_FILE).open(encoding="utf-8", newline="") as handle:
        rows = list(csv.DictReader(handle))
    assert rows == [{k: str(v) for k, v in row.items()} for row in generator.review_rows(generated)]
    queued = {
        queue: {r["normalized_name"] for r in rows if r["queue"] == queue}
        for queue in ("uncertain", "needs_certification", "check", "sample")
    }
    assert queued["uncertain"] == {i["normalized_name"] for i in generated if i["status"] == "uncertain"}
    assert queued["needs_certification"] == {i["normalized_name"] for i in generated if i["needs_certification"]}
    assert len(queued["sample"]) == generator.SAMPLE_SIZE
    assert {"cheese", "red_wine_vinegar"} <= queued["check"] and not queued["check"] & queued["sample"]
    assert all(not row["verdict"] for row in rows)


def _csv(name: str) -> list[dict]:
    with (data_root() / name).open(encoding="utf-8", newline="") as handle:
        return list(csv.DictReader(handle))


def test_every_verdict_short_of_ok_is_an_override_and_nothing_else_is(generated: list[dict]) -> None:
    """The person's verdicts (10-31) are on the queue the generator writes, and the overrides carry exactly them."""
    verdicts = _csv(generator.VERDICTS_FILE)
    assert [(r["queue"], r["normalized_name"]) for r in verdicts] == [
        (r["queue"], r["normalized_name"]) for r in generator.review_rows(generated)
    ]
    changed = {r["normalized_name"]: r["verdict"] for r in verdicts if r["verdict"] != "ok"}
    overrides = json.loads((data_root() / OVERRIDES_FILE).read_text(encoding="utf-8"))["items"]
    assert {i["normalized_name"]: i["status"] for i in overrides} == changed
    labels = halal_labels()
    assert all((labels[n]["status"], labels[n]["source"]) == (verdict, "human") for n, verdict in changed.items())
    assert labels["cheese"]["status"] == "uncertain" and labels["broccoli"]["status"] == "halal"


def test_the_second_round_holds_the_other_condiments_and_prepared_foods(generated: list[dict]) -> None:
    names = generator.catalog()
    rows = _csv(generator.REVIEW_V2_FILE)
    assert rows == [{k: str(v) for k, v in row.items()} for row in generator.second_round_rows(generated, names)]
    second = {r["normalized_name"] for r in rows}
    assert {"soy_sauce", "vinegar", "mayo"} <= second
    assert not second & {r["normalized_name"] for r in generator.review_rows(generated)}
    assert all(names[name][0] in generator.SECOND_ROUND_GROUPS for name in second)


def test_the_pool_report_counts_each_queue_by_outcome() -> None:
    from app.data.halal_pool import review_summary

    review = review_summary()
    assert review[generator.VERDICTS_FILE]["sample"] == {"kept": 40, "corrected": 0, "undetermined": 20, "pending": 0}
    assert review[generator.VERDICTS_FILE]["check"]["undetermined"] == 13
    assert review[generator.REVIEW_V2_FILE]["second_round"]["pending"] == len(_csv(generator.REVIEW_V2_FILE))


def test_certification_facts_are_true_or_unknown_never_false() -> None:
    document = json.loads((data_root() / CERTIFICATION_FILE).read_text(encoding="utf-8"))
    assert document["observed_at"] and document["requests"] <= 150
    facts = release_halal_certification()
    assert set(facts) == set(document["products"]) and set(facts.values()) <= {True, None}
    assert any(facts.values())
