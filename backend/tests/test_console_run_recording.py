"""What the operations console reads from a turn's or a plan's run: its time, its warnings and its pricing.

Found by the 2026-10-12 console review: a Plan that saved the week its reply had checked recorded 1 ms; the first
turn of a conversation left its parse (the model call) out of its time; plan warnings never reached the run; and
a live plan's run said fixture, with the snapshot total, though its list was checked at FairPrice (ADR-0058).
"""

import time
from datetime import UTC, datetime

from sqlalchemy import select

from app.models.agent import AgentRun
from app.models.platform import OperationRun
from app.orchestration.runtime import BoundedAgentOrchestrator
from app.planning.product_path import ProductPlanningEngine
from app.products.provider import FairPriceProductProvider
from app.repositories.product import ProductSnapshotRepository
from app.services.product import ProductSearchService
from tests.test_planning_capability import dish_client
from tests.test_walkthrough_1004_planning import EIGHT, kept_for, mains
from tests.test_wp1_snapshot_planning import dishes

PAUSE = 0.3


def rows(model) -> list:
    """Every row of `model` in the catalog of the client in use (`dish_client`)."""
    from app.db.session import get_db_session
    from app.main import app

    sessions = app.dependency_overrides[get_db_session]()
    session = next(sessions)
    try:
        return list(session.scalars(select(model).order_by(model.id)))
    finally:
        sessions.close()


def seconds(started: datetime, finished: datetime) -> float:
    return (finished.replace(tzinfo=None) - started.replace(tzinfo=None)).total_seconds()


def slowed(monkeypatch, owner, name: str) -> None:
    """`owner.name` takes PAUSE seconds longer, as a model call or a search does."""
    original = getattr(owner, name)

    def slow(*args, **kwargs):
        time.sleep(PAUSE)
        return original(*args, **kwargs)

    monkeypatch.setattr(owner, name, slow)


def planning_run() -> OperationRun:
    (run,) = [run for run in rows(OperationRun) if run.run_type == "planning"]
    return run


def trace(run: OperationRun) -> dict:
    return next(ref["data"] for ref in run.artifact_references if ref["kind"] == "planning_trace")


def test_a_first_turn_is_timed_from_before_its_parse(monkeypatch):
    """Turn 673 parsed at 07:46:41.2 and its run started at 07:46:43.777: 19 ms for a 2.6 s turn."""
    with dish_client(monkeypatch, mains(*EIGHT)) as client:
        slowed(monkeypatch, BoundedAgentOrchestrator, "process")
        client.post("/api/agent/sessions", json={"message": "Dinners for 4, S$40 total"})
        (run,) = rows(AgentRun)
    assert seconds(run.started_at, run.completed_at) >= PAUSE
    # The wall-time budget counts from the same start.
    assert seconds(run.started_at, run.deadline_at) == run.max_wall_seconds


def test_plan_saving_the_week_its_reply_checked_is_timed_as_that_search(monkeypatch):
    """Run 262 recorded 1 ms for a search of 13,053 expansions, done by the reply's check before Plan."""
    with kept_for(300), dish_client(monkeypatch, mains(*EIGHT)) as client:
        slowed(monkeypatch, ProductPlanningEngine, "plan")
        session = client.post("/api/agent/sessions", json={"message": "Dinners for 4, S$40 total"}).json()
        assert session["status"] == "ready", session["messages"][-1]["content"]
        confirmed = client.post(f"/api/agent/sessions/{session['id']}/confirm")
        assert confirmed.status_code == 200, confirmed.text
        run = planning_run()
    recorded = trace(run)
    assert recorded["reused_checked_week"] is True and recorded["search_seconds"] >= PAUSE
    assert seconds(run.started_at, run.finished_at) >= recorded["search_seconds"]


def test_plan_warnings_are_recorded_on_its_planning_run(monkeypatch):
    with dish_client(monkeypatch, dishes()) as client:
        plan = client.post(
            "/api/plans/generate", json={"requires_halal": False, **{"household_size": 2, "weekly_budget_sgd": 100}}
        )
        assert plan.status_code == 201, plan.text
        run = planning_run()
    assert plan.json()["warnings"] and run.warnings == plan.json()["warnings"]


def checked_at_fairprice(monkeypatch, price: float, *, unanswered: int = 0) -> None:
    """The saved list's products answered by FairPrice at `price` each (test_wp1_final_prices), but for the first
    `unanswered` queries: priced from the reviewed snapshot, as a live list's lines are, FairPrice returns nothing."""
    selected = {}
    refresh = ProductSearchService.refresh_selected

    def refresh_synthetic(self, lines):
        for index, item in enumerate(lines):
            if item.product:
                item.product = item.product.model_copy(update={"external_id": str(10000 + index)})
                selected[item.evidence.query] = item.product
                if list(selected).index(item.evidence.query) < unanswered:
                    item.evidence = item.evidence.model_copy(update={"source": "release_snapshot"})
        return refresh(self, lines)

    def search(self, query, *, limit, timeout_seconds):
        if list(selected).index(query) < unanswered:
            return []
        return [
            selected[query].model_copy(
                update={"price_sgd": price, "source": "fairprice", "fetched_at": datetime.now(UTC)}
            )
        ]

    monkeypatch.setattr(ProductSearchService, "refresh_selected", refresh_synthetic)
    monkeypatch.setattr(FairPriceProductProvider, "search", search)
    monkeypatch.setattr(ProductSnapshotRepository, "get_fresh", lambda *args, **kwargs: [])


def test_a_live_plan_records_its_pricing_as_asked_and_its_list_as_checked(monkeypatch):
    """Plan 246 showed the household S$119.30 at FairPrice; its run 269 said fixture and S$118.97."""
    checked_at_fairprice(monkeypatch, 50)
    with dish_client(monkeypatch, dishes()) as client:
        response = client.post(
            "/api/plans/generate",
            json={"requires_halal": False, **{"household_size": 2, "weekly_budget_sgd": 100, "pricing_mode": "live"}},
        )
        assert response.status_code == 201, response.text
        run = planning_run()
    grocery = response.json()["grocery_estimate"]
    recorded = trace(run)
    assert recorded["requested_pricing_mode"] == recorded["request"]["pricing_mode"] == "live"
    assert recorded["planning_pricing_mode"] == "fixture"  # the week was chosen at snapshot prices
    assert recorded["final_list"]["pricing_mode"] == "live"
    assert recorded["final_list"]["purchase_total_sgd"] == grocery["purchase_total_sgd"]
    assert recorded["validation"]["purchase_total_sgd"] != grocery["purchase_total_sgd"]  # the snapshot total
    assert "fairprice" in recorded["final_list"]["price_sources"] and "fairprice" in run.provider_mode.split(",")


def test_a_live_plan_with_a_line_fairprice_did_not_confirm_saves_with_providers_only(monkeypatch):
    """The unconfirmed line keeps its release_snapshot label, no provider: "fairprice,fixture,release_snapshot" is
    34 characters, and Postgres refuses it for provider_mode's String(30), losing the plan (review of 8947422)."""
    checked_at_fairprice(monkeypatch, 50, unanswered=1)
    with dish_client(monkeypatch, dishes()) as client:
        response = client.post(
            "/api/plans/generate",
            json={"requires_halal": False, **{"household_size": 2, "weekly_budget_sgd": 100, "pricing_mode": "live"}},
        )
        assert response.status_code == 201, response.text
        run = planning_run()
    assert {"fairprice", "release_snapshot"} <= set(trace(run)["final_list"]["price_sources"])
    assert run.provider_mode == ",".join(sorted({*trace(run)["observed_sources"], "fairprice"}))
    assert len(run.provider_mode) <= OperationRun.provider_mode.type.length


def test_a_failed_live_plan_records_the_pricing_it_asked_for(monkeypatch):
    checked_at_fairprice(monkeypatch, 50)
    with dish_client(monkeypatch, dishes()) as client:
        response = client.post(
            "/api/plans/generate",
            json={"requires_halal": False, **{"household_size": 2, "weekly_budget_sgd": 1, "pricing_mode": "live"}},
        )
        assert response.status_code >= 400, response.text
        run = planning_run()
    recorded = trace(run)
    assert run.status == "failed"
    assert recorded["requested_pricing_mode"] == recorded["request"]["pricing_mode"] == "live"
    assert "final_list" not in recorded  # nothing was saved, so nothing was checked at FairPrice
