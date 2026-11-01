"""Reach the product through the held-out conversation harness with ordinary chat only (ADR-0092, ADR-0098).

The harness sends every system the same user strings, and one fixed confirmation message when a system waits for
one. This transport turns each string into a chat message on a product session and reads the product's actual
answer, and its saved plan if any, into the common output. It never calls a confirm or discard action: the product
recognises the clear confirmation in chat (ADR-0098).

It has no episode loader, gold, scorer or sealed file, creates no household or profile, and chooses no provider:
the caller supplies an authenticated client for a household prepared for the run. The shared instructions are for
model arms; the product has its own contract and receives only the message. Use one responder per case.
"""

from __future__ import annotations

from typing import Protocol

from app.evaluation.conversation_adapter import Exchange, Responder, UnifiedOutput, normalize_product
from app.schemas.agent import AgentSessionResponse
from app.schemas.meal_plan import WeeklyMealPlanResponse


class ProductTransportError(RuntimeError):
    """A product call failed. It is an error of the run, never an infeasible or refused answer."""


class HttpResponse(Protocol):
    status_code: int

    def json(self): ...


class HttpClient(Protocol):
    def post(self, url: str, json=None) -> HttpResponse: ...

    def get(self, url: str) -> HttpResponse: ...


class ProductTransport:
    def __init__(self, client: HttpClient, *, api_prefix: str = "/api"):
        self.client = client
        self.sessions = f"{api_prefix}/agent/sessions"
        self.plans = f"{api_prefix}/plans"

    def _body(self, response: HttpResponse, what: str):
        if not 200 <= response.status_code < 300:
            raise ProductTransportError(f"{what} failed with status {response.status_code}")
        return response.json()

    def responder(self) -> Responder:
        """A fresh responder for one case: its first turn opens a new session, later turns reuse it."""
        session_id: int | None = None

        def respond(message: str, own_history: tuple[Exchange, ...], instructions: str) -> UnifiedOutput:
            nonlocal session_id
            if not own_history:
                if session_id is not None:
                    raise ProductTransportError("one responder serves one case; make a new one for the next case")
                body = self._body(self.client.post(self.sessions, json={"message": message}), "opening the session")
                session = AgentSessionResponse.model_validate(body)
                session_id = session.id
            else:
                if session_id is None:
                    raise ProductTransportError("a later turn arrived with history but no session was opened")
                body = self._body(
                    self.client.post(f"{self.sessions}/{session_id}/messages", json={"message": message}),
                    "sending the message",
                )
                session = AgentSessionResponse.model_validate(body)
            plan = None
            if session.plan_id is not None:
                plan_body = self._body(self.client.get(f"{self.plans}/{session.plan_id}"), "reading the saved plan")
                plan = WeeklyMealPlanResponse.model_validate(plan_body)
            return normalize_product(session, plan)

        return respond
