"""The frozen meal-day-week held-out set: its digest, its drawn pools, its quotas and its recorded proofs.

Label proofs take minutes an episode (six-dish meals do not finish), so CI checks the recorded proofs
in verification.json and witnesses.json instead of re-running them.
"""

import hashlib
import json
from collections import Counter

from app.core.paths import repository_root
from app.evaluation.multidish_pool import draw

SET = repository_root() / "data/evaluation/heldout/v3-meal-day-week"
QUOTAS = {
    "shape_change": 12,
    "meals_per_day": 9,
    "composition": 9,
    "budget": 9,
    "safety_diet": 9,
    "nutrition_per_day": 7,
    "variety": 5,
}


def episodes():
    return [json.loads(path.read_text(encoding="utf-8")) for path in sorted((SET / "episodes").glob("*.json"))]


def load(name):
    return json.loads((SET / name).read_text(encoding="utf-8"))


def test_the_set_matches_its_frozen_digest():
    manifest = load("set-manifest.json")
    canonical = "\n".join(
        json.dumps(episode, ensure_ascii=False, sort_keys=True, separators=(",", ":")) for episode in episodes()
    )
    assert manifest["status"] == "frozen"
    assert hashlib.sha256(canonical.encode("utf-8")).hexdigest() == manifest["frozen_digest"], (
        "the held-out set changed; a frozen set is not re-cut silently"
    )
    assert len(episodes()) == manifest["episodes"] == 60


def test_every_pool_is_the_drawn_one():
    for episode in episodes():
        slugs, products = draw(episode)
        assert episode["scenario"]["recipe_candidate_slugs"] == slugs, episode["episode_id"]
        assert episode["scenario"]["fairprice_product_ids"] == products, episode["episode_id"]


def test_quotas_languages_and_classes_hold():
    rows = episodes()
    assert Counter(e["category"] for e in rows) == QUOTAS
    for category in QUOTAS:
        languages = Counter(e["language"] for e in rows if e["category"] == category)
        assert languages["en"] >= 2 and languages["zh"] >= 2, category
    infeasible = Counter(e["category"] for e in rows if e["gold"]["class"] == "infeasible")
    assert 13 <= sum(infeasible.values()) <= 16
    assert set(infeasible) <= {"meals_per_day", "composition", "safety_diet"}


def test_every_budget_is_a_real_households_amount_above_its_witness():
    witnesses = load("witnesses.json")["episodes"]
    for episode in episodes():
        budget = episode["gold"]["applicable_hard_constraints"]["budget_sgd"]
        if budget is None:
            continue
        profile, slots = episode["scenario"]["household_profile"], episode["scenario"]["planning_horizon"]["slots"]
        assert budget / (profile["household_size"] * len(slots)) >= 2.5, episode["episode_id"]
        ratio = budget / witnesses[episode["episode_id"]]["witness_cost_sgd"]
        assert 1.15 <= ratio <= (1.25 if episode["category"] == "budget" else 1.40), episode["episode_id"]


def test_every_feasible_label_has_a_recorded_witness_and_every_label_a_recorded_proof():
    witnesses = load("witnesses.json")["episodes"]
    proofs = {row["episode_id"]: row["output"] for row in load("verification.json")["repository_labels"]["per_episode"]}
    for episode in episodes():
        eid, label = episode["episode_id"], episode["gold"]["class"]
        assert (eid in witnesses) == (label == "feasible"), eid
        if eid != "mdw-ho-024":  # proven by the recorded meal-time lower bound instead
            assert proofs[eid].startswith(f"{eid}: {label}; {label}_proven"), (eid, proofs[eid])
        if label == "feasible":
            week = witnesses[eid]
            assert round(sum(line["cost_sgd"] for line in week["shopping"]), 2) == week["witness_cost_sgd"], eid
            assert set(week["menu"]) == set(episode["scenario"]["planning_horizon"]["slots"]) or episode["gold"].get(
                "replan_invariants"
            ), eid
