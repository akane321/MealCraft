"""The frozen multi-dish held-out set: its digest, its drawn pools and its proven labels."""

import hashlib
import json
from collections import Counter

from app.core.paths import repository_root
from app.evaluation.multidish_labels import check
from app.evaluation.multidish_pool import draw

SET = repository_root() / "data/evaluation/heldout/v2-multidish"
QUOTAS = {
    "combined_constraints": 8,
    "safety_diet": 6,
    "budget_time": 4,
    "budget_package": 4,
    "pantry_expiry": 4,
    "infeasible_conflict": 7,
    "clarification": 7,
}


def episodes():
    return [json.loads(path.read_text(encoding="utf-8")) for path in sorted((SET / "episodes").glob("*.json"))]


def test_the_set_matches_its_frozen_digest():
    manifest = json.loads((SET / "set-manifest.json").read_text(encoding="utf-8"))
    files = sorted((SET / "episodes").glob("*.json"))
    # Canonical JSON, so the digest does not depend on line endings or formatting.
    canonical = "\n".join(
        json.dumps(episode, ensure_ascii=False, sort_keys=True, separators=(",", ":"))
        for episode in sorted(episodes(), key=lambda e: e["episode_id"])
    )
    digest = hashlib.sha256(canonical.encode("utf-8")).hexdigest()

    assert manifest["status"] == "frozen"
    assert digest == manifest["frozen_digest"], "the held-out set changed; a frozen set is not re-cut silently"
    assert len(files) == manifest["episodes"] == 40


def test_every_pool_is_the_drawn_one_and_every_label_is_proven():
    for episode in episodes():
        slugs, products = draw(episode)
        assert episode["scenario"]["recipe_candidate_slugs"] == slugs, episode["episode_id"]
        assert episode["scenario"]["fairprice_product_ids"] == products, episode["episode_id"]
        assert check(episode) is None, (episode["episode_id"], check(episode))


def test_the_quotas_and_both_languages_hold():
    rows = episodes()
    assert Counter(e["category"] for e in rows) == QUOTAS
    for category in QUOTAS:
        languages = {e["language"] for e in rows if e["category"] == category}
        assert languages == {"zh", "en"}, category


def test_no_episode_states_a_nutrition_target_the_release_cannot_score():
    for episode in episodes():
        assert not episode["gold"]["applicable_hard_constraints"]["nutrition_bands"], episode["episode_id"]
