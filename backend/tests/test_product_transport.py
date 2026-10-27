"""The product reaches the held-out harness through ordinary chat only (ADR-0092 item 2, ADR-0098)."""

from __future__ import annotations

import pytest

from app.evaluation.conversation_adapter import (
    CONFIRMATION_MESSAGE,
    ConversationHarness,
    RuntimeConfig,
)
from app.evaluation.product_transport import ProductTransport, ProductTransportError
from tests.test_recipes import recipe_client as recipe_client  # noqa: F401

REQUEST = "Build a weekly plan for 2 people with a S$20 per meal budget."
CONFIG = RuntimeConfig(anchor_date="2026-10-23")


class RecordingClient:
    """Wraps a client and records every call, so a test can see which endpoints the transport used."""

    def __init__(self, client):
        self.client = client
        self.calls: list[tuple[str, str, dict | None]] = []

    def post(self, url, json=None):
        self.calls.append(("POST", url, json))
        return self.client.post(url, json=json)

    def get(self, url):
        self.calls.append(("GET", url, None))
        return self.client.get(url)


def test_a_waiting_plan_is_confirmed_by_the_fixed_message_through_chat_only(recipe_client):  # noqa: F811
    client = RecordingClient(recipe_client)
    harness = ConversationHarness(CONFIG)
    result = harness.run("mealcraft", [REQUEST], ProductTransport(client).responder())

    assert result.confirmation_count == 1
    assert [e.automatic_confirmation for e in result.exchanges] == [False, True]
    assert result.exchanges[0].output.awaiting_confirmation is True
    assert result.final.plan is not None
    assert [item["id"] for item in recipe_client.get("/api/plans").json()["items"]] != []

    posted = [(url, body) for method, url, body in client.calls if method == "POST"]
    # The harness never reaches the product's confirm actions: only the first message and chat messages.
    assert not any(url.endswith("/confirm") or url.endswith("/replan/confirm") for url, _ in posted)
    assert posted[0][0].endswith("/agent/sessions")
    assert posted[1][0].endswith("/messages")
    # What the product receives is the message and nothing else: no schema, labels or instructions.
    assert [body for _, body in posted] == [{"message": REQUEST}, {"message": CONFIRMATION_MESSAGE}]


def test_every_case_starts_a_new_session(recipe_client):  # noqa: F811
    client = RecordingClient(recipe_client)
    transport = ProductTransport(client)
    harness = ConversationHarness(CONFIG)
    harness.run("mealcraft", [REQUEST], transport.responder())
    harness.run("mealcraft", [REQUEST], transport.responder())
    creations = [url for method, url, _ in client.calls if method == "POST" and url.endswith("/agent/sessions")]
    assert len(creations) == 2
    sessions = recipe_client.get("/api/agent/sessions").json()["items"]
    assert len({item["id"] for item in sessions}) == 2


def test_one_responder_serves_one_case():
    class Silent:
        def post(self, url, json=None):
            raise AssertionError("not reached")

        def get(self, url):
            raise AssertionError("not reached")

    responder = ProductTransport(Silent()).responder()
    with pytest.raises(ProductTransportError, match="history"):
        # A follow-up turn arrives before any first turn created a session.
        responder("hello", (object(),), "instructions")


def test_a_failed_request_is_an_error_not_an_infeasible_answer():
    class Broken:
        def post(self, url, json=None):
            class Response:
                status_code = 503

                def json(self):
                    return {"detail": "down"}

            return Response()

        def get(self, url):
            raise AssertionError("not reached")

    responder = ProductTransport(Broken()).responder()
    with pytest.raises(ProductTransportError, match="503"):
        responder(REQUEST, (), "instructions")


def test_a_second_first_turn_on_the_same_responder_is_rejected(recipe_client):  # noqa: F811
    responder = ProductTransport(recipe_client).responder()
    responder(REQUEST, (), "instructions")
    with pytest.raises(ProductTransportError, match="one case"):
        responder(REQUEST, (), "instructions")
