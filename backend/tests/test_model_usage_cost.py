from decimal import Decimal
from types import SimpleNamespace

import httpx
import pytest

from app.agent import model_client
from app.services.agent import AgentSessionService


def test_reported_chat_and_embedding_usage_produces_a_dated_cost_estimate(monkeypatch):
    run = SimpleNamespace(
        used_llm_calls=0,
        max_llm_calls=8,
        used_api_cost_usd=Decimal("0"),
        model_config={
            "chat_token_rates_usd_per_million": ["0.75", "0.075", "4.50"],
            "embedding_token_rates_usd_per_million": {"text-embedding-3-small": "0.02"},
        },
    )
    monkeypatch.setattr(
        model_client,
        "take",
        lambda: model_client.Tally(
            requests=2,
            input_tokens=1000,
            cached_input_tokens=100,
            output_tokens=500,
            embedding_tokens=400,
        ),
    )

    AgentSessionService._record_model_calls(run)

    assert run.used_llm_calls == 2
    assert run.used_api_cost_usd == Decimal("0.0029405")
    assert run.model_config["token_usage"] == {
        "input_tokens": 1000,
        "cached_input_tokens": 100,
        "output_tokens": 500,
        "embedding_tokens": 400,
    }
    assert run.model_config["api_cost_estimate_status"] == "estimated"


def test_openai_response_hook_counts_chat_and_embedding_usage(monkeypatch):
    tally = model_client.Tally()
    token = model_client._turn.set(tally)
    try:
        chat = httpx.Response(
            200,
            json={
                "usage": {
                    "prompt_tokens": 120,
                    "completion_tokens": 15,
                    "prompt_tokens_details": {"cached_tokens": 20},
                }
            },
            request=httpx.Request("POST", "https://api.openai.com/v1/chat/completions"),
        )
        embedding = httpx.Response(
            200,
            json={"usage": {"prompt_tokens": 9}},
            request=httpx.Request("POST", "https://api.openai.com/v1/embeddings"),
        )
        model_client._count_response_usage(chat)
        model_client._count_response_usage(embedding)
    finally:
        model_client._turn.reset(token)

    assert tally.input_tokens == 120
    assert tally.cached_input_tokens == 20
    assert tally.output_tokens == 15
    assert tally.embedding_tokens == 9


def test_response_hook_reads_a_streamed_transport_body_before_accounting():
    # Unlike Response(json=...), this body is unread when HTTPX invokes response hooks.
    transport = httpx.MockTransport(
        lambda request: httpx.Response(
            200,
            stream=httpx.ByteStream(b'{"usage":{"prompt_tokens":17,"completion_tokens":3}}'),
            headers={"content-type": "application/json"},
        )
    )
    with (
        model_client.counting(),
        httpx.Client(
            transport=transport,
            event_hooks={"response": [model_client._count_response_usage]},
        ) as client,
    ):
        assert client.post("http://127.0.0.1/v1/chat/completions").json()["usage"]["prompt_tokens"] == 17
        tally = model_client.take()
    assert (tally.input_tokens, tally.output_tokens) == (17, 3)


def test_request_budget_blocks_before_transport_and_take_cannot_reset_it():
    sent = []
    transport = httpx.MockTransport(lambda request: (sent.append(request), httpx.Response(200, json={}))[1])
    with (
        model_client.counting(max_requests=2),
        httpx.Client(
            transport=transport,
            event_hooks={"request": [model_client._count]},
        ) as client,
    ):
        client.post("http://127.0.0.1/first")
        assert model_client.take().requests == 1
        client.post("http://127.0.0.1/second")
        with pytest.raises(model_client.ModelCallLimitReached):
            client.post("http://127.0.0.1/third")
        assert model_client.take().requests == 1
    assert len(sent) == 2
