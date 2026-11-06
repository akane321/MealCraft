"""The product and its six ablations as arms of the shared baseline runner (issue #397; ADR-0092; 02-baselines.md).

Each arm reaches the product through ordinary chat (`ProductTransport`), so its answers are turned into the same
`BaselineResponse` and scored by the same unchanged `pure_llm_baseline.score` as the three baselines, on the same
episodes. "mealcraft" is the product as it ships; "mealcraft/ablation/<name>" is the product with
`EVALUATION_ABLATION=<name>`, which switches one component off (`app.core.config.ablated`; only in development
and test).

The product's saved dishes are its catalog recipes: each dish's `recipe_reference` becomes the release recipe id its
slug names, and the dish gets that recipe's ingredient lines, steps and time from the frozen release as its
`evidence`, scaled to the dish's servings (`rag_baseline.fill_evidence`, as for the RAG arm), so the scorer reads
what the catalog says the dish is.

`ablation_arms(client_factory)` is the interface: `client_factory(name)` returns an authenticated client for a fresh
household of a product running with that switch (None: no switch). The held-out caller supplies its own; this
module reads no episode.

`InProcessClient` is the factory for development runs: the product app in this process on one in-memory database
holding the release recipes the scorer's catalog holds (imported once per process), each case on a newly
registered account, every call with the test environment, the fixture parser, no OpenAI key and FairPrice as the
only store, so a development run cannot spend money. The product's clock is the harness's anchor noon
(`ConversationHarness` freezes it around the conversation).
The arms make no paid call of their own (`paid=False`). A run with the OpenAI parser runs "mealcraft" and the six
switches back to back (owner, 2026-11-06, ADR-0118): the parser's long prompt prefix stays in OpenAI's cache, which
cut a question from about US$0.005 to US$0.0016 on the development episodes.
From the repository root (the product reads its fixture files relative to it):

    uv run --project backend python -m app.evaluation.baseline_arms --arm mealcraft/ablation/repair_off \\
        --episodes data/evaluation/dev/v3-meal-day-week/episodes --anchor-date 2026-09-28 \\
        --output .local/evaluation/ablation/repair_off.jsonl
"""

from __future__ import annotations

import uuid
from collections.abc import Callable, Iterator
from contextlib import ExitStack, contextmanager
from functools import cache
from typing import Any

from app.core.code_version import code_commit
from app.core.config import ABLATIONS, get_settings
from app.core.paths import repository_root
from app.evaluation import baseline_arms
from app.evaluation.conversation_adapter import Responder, UnifiedOutput
from app.evaluation.product_transport import HttpClient, ProductTransport
from app.planning.retailers import fairprice_only

SYSTEM_ID = "mealcraft"
# What every in-process call runs with: an evaluation environment where `ablated()` is read, and no paid model.
IN_PROCESS_SETTINGS: dict[str, Any] = {
    "environment": "test",
    "agent_parser_provider": "fixture",
    "openai_api_key": None,
    "youtube_api_key": None,
}
_open = ExitStack()  # keeps the release database open for the life of the process


def system_id(ablation: str | None) -> str:
    return SYSTEM_ID if ablation is None else f"{SYSTEM_ID}/ablation/{ablation}"


def _tree(path: str) -> str | None:
    found = baseline_arms._git("rev-parse", f"HEAD:{path}")
    return (found or "").strip() or None


def fingerprint(ablation: str | None, parser_provider: str | None = None) -> dict[str, Any]:
    """The arm, the code and every data file it plans from (git tree ids), and the parser it reads requests with."""
    from app.data.release_v2 import release_dir

    settings = get_settings()
    return {
        "system_id": system_id(ablation),
        "ablation": ablation,
        "code_commit": code_commit(),
        "data_tree": _tree("data"),
        "release_tree": _tree(release_dir().relative_to(repository_root()).as_posix()),
        "runner_sha256": baseline_arms.source_sha256(__file__),
        "parser_provider": parser_provider or settings.agent_parser_provider,
        "parser_model": settings.openai_model,
    }


def ablation_arms(
    client_factory: Callable[[str | None], HttpClient], *, parser_provider: str | None = None
) -> dict[str, baseline_arms.Arm]:
    """ "mealcraft" and its six ablations; each case asks `client_factory` for a client of its own.

    `parser_provider` is the parser the product behind the factory uses, when it is not this process's setting."""

    def arm(ablation: str | None) -> baseline_arms.Arm:
        return baseline_arms.Arm(
            system_id=system_id(ablation),
            paid=False,
            fingerprint=lambda: fingerprint(ablation, parser_provider),
            responder=lambda context: responder(client_factory(ablation), context),
        )

    return {item.system_id: item for item in map(arm, (None, *ABLATIONS))}


def responder(client: HttpClient, context: baseline_arms.ArmContext) -> Responder:
    """The product's answers, each saved dish with its catalog recipe's lines as evidence, as the RAG arm's are."""
    from app.evaluation.rag_baseline import catalog, fill_evidence

    respond, data, names = ProductTransport(client).responder(), catalog(), context.resources.names
    # The product's slug for a release recipe ends with its id's hex (`app.data.release_v2.recipe_slug`).
    by_hex = {key.removeprefix("RCP2_").lower(): key for key in data.recipes}

    def answer(message: str, own_history, instructions: str) -> UnifiedOutput:
        output = respond(message, own_history, instructions)
        if output.plan is None:
            return output
        payload = output.model_dump(mode="json")
        for meal in payload["plan"]["meals"]:
            for dish in meal["dishes"]:
                reference = dish.get("recipe_reference") or ""
                dish["recipe_reference"] = by_hex.get(reference.rsplit("-", 1)[-1], reference or None)
        return fill_evidence(UnifiedOutput.model_validate(payload), data, names)

    return answer


def in_process_arms() -> dict[str, baseline_arms.Arm]:
    return ablation_arms(InProcessClient, parser_provider=IN_PROCESS_SETTINGS["agent_parser_provider"])


@cache
def release_database():
    """The scorer's release catalog in one in-memory product database, imported by the product's own importer."""
    from app.evaluation.meal_day_week_runner import product_database
    from app.evaluation.rag_baseline import catalog

    # Only the recipes the scorer's frozen catalog prices: a dish outside it has no evidence lines and scores invalid.
    return _open.enter_context(product_database({"scenario": {"recipe_candidate_slugs": list(catalog().recipes)}}))


class InProcessClient:
    """One case's newly registered account on the product app in this process, with one ablation switched on.

    Every call runs with `IN_PROCESS_SETTINGS`, the switch and the case's database, set on the cached settings and
    the app's database dependency for that call only and restored after it."""

    def __init__(self, ablation: str | None, sessions: Callable[[], Any] | None = None):
        from fastapi.testclient import TestClient

        from app.main import app

        self.app, self.ablation = app, ablation
        self.sessions = sessions or release_database()
        self.client = TestClient(app)  # not entered: no start-up model warming or pool thread

    @contextmanager
    def _product(self) -> Iterator[None]:
        from app.db.session import get_db_session

        settings = get_settings()
        forced = {**IN_PROCESS_SETTINGS, "evaluation_ablation": self.ablation}
        before = {name: getattr(settings, name) for name in forced}
        overrides = self.app.dependency_overrides
        previous = overrides.get(get_db_session)

        def database():
            with self.sessions() as session:
                yield session

        for name, value in forced.items():
            setattr(settings, name, value)
        overrides[get_db_session] = database
        try:
            yield
        finally:
            for name, value in before.items():
                setattr(settings, name, value)
            if previous is None:
                overrides.pop(get_db_session, None)
            else:
                overrides[get_db_session] = previous

    def _call(self, method: str, url: str, **arguments):
        # FairPrice only, like every other evaluation of the product (`meal_day_week_runner.run_episode`).
        with self._product(), fairprice_only():
            if "X-CSRF-Token" not in self.client.headers:  # registered on the case's first call, on the case's clock
                registered = self.client.post(
                    "/api/auth/register",
                    json={
                        "email": f"ablation-{uuid.uuid4().hex}@example.test",
                        "password": "correct horse battery staple",
                        "display_name": "Evaluation household",
                    },
                )
                if registered.status_code != 201:
                    raise RuntimeError(f"registering the case's household failed with status {registered.status_code}")
                self.client.headers["X-CSRF-Token"] = registered.json()["csrf_token"]
            return getattr(self.client, method)(url, **arguments)

    def post(self, url: str, json=None):
        return self._call("post", url, json=json)

    def get(self, url: str):
        return self._call("get", url)
