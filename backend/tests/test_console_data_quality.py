"""Console data-quality fixes: the dropped-reason filter, the release funnel and literal recipe search."""

from __future__ import annotations

import json
import shutil
from pathlib import Path

from sqlalchemy import create_engine
from sqlalchemy.orm import Session
from sqlalchemy.pool import StaticPool

from app.core.paths import repository_root
from app.db.base import Base
from app.models.recipe import Recipe
from app.services.ops_data import DataService
from app.services.ops_data_quality import _REASON_DETAIL, ENRICHER_REASON, DataQualityService, reason_bucket

FIXTURE_DIRECTORY = repository_root() / "data-engineering" / "data" / "fixtures" / "ops"


def _release_directory(target: Path, counts: dict | None) -> Path:
    target.mkdir()
    shutil.copyfile(FIXTURE_DIRECTORY / "quality_summary.sample.json", target / "quality_summary.json")
    shutil.copyfile(FIXTURE_DIRECTORY / "dropped.sample.jsonl", target / "dropped.jsonl")
    summary = json.loads((target / "quality_summary.json").read_text(encoding="utf-8"))
    manifest = {
        "release_version": summary["release_version"],
        "schema_version": "v2",
        "created_at": summary["created_at"],
    }
    if counts is not None:
        manifest["counts"] = counts
    (target / "release_manifest.json").write_text(json.dumps(manifest), encoding="utf-8")
    return target


def test_every_offered_reason_returns_the_rows_its_count_stands_for() -> None:
    service = DataQualityService.current()
    offered = service.summary().dropped_by_reason
    assert offered == {
        "reviewed incomplete": 221,
        "implausible energy # kcal per serving": 70,
        "excluded by enricher": 1,
    }

    totals = {reason: service.dropped(offset=0, limit=1, reason=reason).total for reason in offered}
    enricher = service.dropped(offset=0, limit=5, reason="excluded by enricher").items

    assert totals == offered
    assert [item.title for item in enricher] == ["Furniture Polish"]
    # A raw recorded reason still narrows to exactly its own rows.
    assert service.dropped(offset=0, limit=1, reason="reviewed incomplete: gluten").total == 69


def test_a_reason_maps_to_the_bucket_the_build_counted_it_under() -> None:
    buckets = {"ingredient form # not enriched", "implausible energy # kcal per serving", "excluded by enricher"}

    assert reason_bucket("ingredient form ING_FLOUR#cooked not enriched", buckets) == "ingredient form # not enriched"
    assert (
        reason_bucket("implausible energy 4713.2 kcal per serving", buckets) == "implausible energy # kcal per serving"
    )
    assert reason_bucket("not a food recipe: furniture polish", buckets) == "excluded by enricher"
    # Without an enricher bucket nothing is filed under it.
    assert reason_bucket("not a food recipe: furniture polish", {"reviewed incomplete"}) == "not a food recipe"


def test_the_reason_mapping_matches_the_builder() -> None:
    # reason_bucket copies the builder's normalisation; a change there must be copied here too.
    builder = (repository_root() / "data-engineering" / "scripts" / "build_release_v2.py").read_text(encoding="utf-8")

    assert f'r"{_REASON_DETAIL.pattern}"' in builder
    assert f'"{ENRICHER_REASON}"' in builder


def test_the_registered_release_accounts_for_the_quota_cut() -> None:
    coverage = DataQualityService.current().summary().coverage

    assert coverage is not None
    assert (coverage.enrichment_set, coverage.built_before_quota, coverage.released_recipes) == (11971, 11679, 8968)
    assert coverage.not_picked_by_quota == 2711
    assert coverage.unbucketed_cuisine == 217


def test_a_manifest_without_counts_leaves_the_quota_cut_unknown(tmp_path: Path) -> None:
    missing = DataQualityService(_release_directory(tmp_path / "missing", None), "v2").summary()
    inconsistent = DataQualityService(_release_directory(tmp_path / "bad", {"built_before_quota": 3}), "v2").summary()

    assert missing.status == "available"
    assert missing.coverage is not None
    assert (missing.coverage.built_before_quota, missing.coverage.not_picked_by_quota) == (None, None)
    # Fewer built than released (12) cannot be a quota cut; it is reported, not turned into a number.
    assert inconsistent.status == "degraded"
    assert inconsistent.coverage is not None
    assert inconsistent.coverage.not_picked_by_quota is None
    assert {issue.code for issue in inconsistent.issues} == {"invalid_contract"}


def test_counts_that_cannot_describe_this_release_are_not_used(tmp_path: Path) -> None:
    # More built than entered enrichment (11,971) would show a negative build drop.
    too_many = DataQualityService(_release_directory(tmp_path / "many", {"built_before_quota": 20000}), "v2").summary()
    other = _release_directory(tmp_path / "other", {"built_before_quota": 100, "unbucketed_cuisine": 4})
    manifest = json.loads((other / "release_manifest.json").read_text(encoding="utf-8"))
    (other / "release_manifest.json").write_text(json.dumps({**manifest, "release_version": "v1"}), encoding="utf-8")
    mixed = DataQualityService(other, "v2").summary()

    assert too_many.coverage is not None
    assert too_many.coverage.built_before_quota is None
    assert {issue.code for issue in too_many.issues} == {"invalid_contract"}
    # A manifest from another release cannot say how many of this release's recipes the quota cut.
    assert mixed.coverage is not None
    assert (mixed.coverage.built_before_quota, mixed.coverage.unbucketed_cuisine) == (None, None)
    assert {issue.code for issue in mixed.issues} == {"release_mismatch"}


def test_recipe_search_reads_percent_and_underscore_as_text() -> None:
    engine = create_engine("sqlite+pysqlite://", connect_args={"check_same_thread": False}, poolclass=StaticPool)
    Base.metadata.create_all(engine)
    with Session(engine) as database:
        for slug, title in (("rye-loaf", "100% Rye Loaf"), ("island-salad", "1000 Island Salad"), ("stew", "Stew")):
            database.add(
                Recipe(
                    slug=slug,
                    title=title,
                    description=title,
                    cuisine="Test",
                    meal_type="main",
                    servings=2,
                    prep_time_minutes=10,
                    cook_time_minutes=20,
                )
            )
        database.commit()
        service = DataService(database, actor_user_id=1)

        def found(query: str) -> list[str]:
            listed = service.recipes(
                query=query, course=None, meal_type=None, origin=None, withdrawn=None, offset=0, limit=10
            )
            return [item.slug for item in listed.items]

        assert found("_") == []
        assert found("100%") == ["rye-loaf"]
        assert found("STEW") == ["stew"]
    engine.dispose()
