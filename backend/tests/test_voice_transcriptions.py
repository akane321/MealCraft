"""ADR-0116 item 2: a recorded clip is transcribed for the chat box; no test reaches the network."""

from types import SimpleNamespace

import httpx
import pytest
from openai import APIConnectionError, APIStatusError, APITimeoutError
from pydantic import SecretStr

from app.core.config import get_settings
from app.services import transcription
from tests.test_recipes import recipe_client as recipe_client

URL = "/api/voice/transcriptions"
WEBM = {"Content-Type": "audio/webm;codecs=opus"}
REQUEST = httpx.Request("POST", "https://api.openai.test/v1/audio/transcriptions")


class FakeOpenAI:
    """Stands in for openai.OpenAI; `results` holds what each create() call returns or raises."""

    results: list = []
    calls: list = []

    def __init__(self, **options) -> None:
        self.audio = SimpleNamespace(transcriptions=SimpleNamespace(create=self.create))

    def create(self, **arguments):
        FakeOpenAI.calls.append(arguments)
        result = FakeOpenAI.results.pop(0)
        if isinstance(result, Exception):
            raise result
        return result


@pytest.fixture
def paid(monkeypatch):
    settings = get_settings()
    monkeypatch.setattr(settings, "voice_transcription_provider", "openai")
    monkeypatch.setattr(settings, "openai_api_key", SecretStr("sk-test-not-real"))
    monkeypatch.setattr(transcription, "OpenAI", FakeOpenAI)
    monkeypatch.setattr(transcription, "_paid_clips", 0)
    monkeypatch.setattr(FakeOpenAI, "results", [])
    monkeypatch.setattr(FakeOpenAI, "calls", [])
    return FakeOpenAI


def test_signed_out_is_refused(recipe_client) -> None:
    recipe_client.cookies.clear()
    assert recipe_client.post(URL, content=b"x", headers=WEBM).status_code == 401


def test_a_write_still_needs_the_csrf_token(recipe_client) -> None:
    token = recipe_client.headers.pop("X-CSRF-Token")
    try:
        response = recipe_client.post(URL, content=b"x", headers=WEBM)
    finally:
        recipe_client.headers["X-CSRF-Token"] = token
    assert response.status_code == 403


def test_fixture_provider_returns_the_fixed_sentence(recipe_client) -> None:
    response = recipe_client.post(URL, content=b"audio", headers=WEBM)
    assert response.status_code == 200
    assert response.json() == {"text": transcription.FIXTURE_TEXT}


def test_a_key_alone_does_not_select_the_paid_provider(recipe_client, monkeypatch) -> None:
    monkeypatch.setattr(get_settings(), "openai_api_key", SecretStr("sk-test-not-real"))
    assert recipe_client.post(URL, content=b"audio", headers=WEBM).json() == {"text": transcription.FIXTURE_TEXT}


def test_other_content_types_are_415(recipe_client) -> None:
    assert recipe_client.post(URL, content=b"x", headers={"Content-Type": "text/plain"}).status_code == 415
    assert recipe_client.post(URL, content=b"x", headers={"Content-Type": "video/mp4"}).status_code == 415


def test_an_empty_clip_is_400(recipe_client) -> None:
    assert recipe_client.post(URL, content=b"", headers=WEBM).status_code == 400


def test_a_clip_over_the_limit_is_413(recipe_client, monkeypatch) -> None:
    monkeypatch.setattr(get_settings(), "voice_max_clip_bytes", 10)
    assert recipe_client.post(URL, content=b"x" * 10, headers=WEBM).status_code == 200
    assert recipe_client.post(URL, content=b"x" * 11, headers=WEBM).status_code == 413


def test_a_streamed_clip_over_the_limit_is_413_without_a_length(recipe_client, monkeypatch) -> None:
    monkeypatch.setattr(get_settings(), "voice_max_clip_bytes", 10)
    response = recipe_client.post(URL, content=iter([b"x" * 6, b"x" * 6]), headers=WEBM)
    assert response.status_code == 413


def test_openai_gets_the_clip_and_the_stripped_text_comes_back(recipe_client, paid) -> None:
    paid.results = [SimpleNamespace(text="  char siew rice for two \n")]
    response = recipe_client.post(URL, content=b"audio", headers={"Content-Type": "audio/mp4"})
    assert response.json() == {"text": "char siew rice for two"}
    (call,) = paid.calls
    assert call["model"] == "gpt-transcribe"
    assert call["languages"] == ["en", "zh"]
    assert "char siew" in call["keywords"] and "kangkong" in call["keywords"]
    assert "Simplified Chinese" in call["prompt"]
    assert call["file"] == ("clip.m4a", b"audio", "audio/mp4")


def test_a_clip_nobody_spoke_into_is_empty_text(recipe_client, paid) -> None:
    paid.results = [SimpleNamespace(text="  \n")]
    response = recipe_client.post(URL, content=b"audio", headers=WEBM)
    assert (response.status_code, response.json()) == (200, {"text": ""})


def test_the_cap_on_paid_clips_is_429(recipe_client, paid, monkeypatch) -> None:
    monkeypatch.setattr(get_settings(), "voice_transcription_max_clips", 2)
    paid.results = [SimpleNamespace(text="one"), SimpleNamespace(text="two")]
    assert [recipe_client.post(URL, content=b"a", headers=WEBM).status_code for _ in range(2)] == [200, 200]
    response = recipe_client.post(URL, content=b"a", headers=WEBM)
    assert response.status_code == 429
    assert "limit" in response.json()["detail"]
    assert len(paid.calls) == 2


def test_one_timeout_is_retried(recipe_client, paid) -> None:
    paid.results = [APITimeoutError(request=REQUEST), SimpleNamespace(text="second try")]
    assert recipe_client.post(URL, content=b"a", headers=WEBM).json() == {"text": "second try"}
    assert len(paid.calls) == 2


def test_a_second_connection_error_is_502(recipe_client, paid) -> None:
    paid.results = [APIConnectionError(request=REQUEST), APIConnectionError(request=REQUEST)]
    assert recipe_client.post(URL, content=b"a", headers=WEBM).status_code == 502


def test_an_api_error_is_502_without_details(recipe_client, paid) -> None:
    error = APIStatusError("sk-test-not-real leaked", response=httpx.Response(500, request=REQUEST), body=None)
    paid.results = [error]
    response = recipe_client.post(URL, content=b"a", headers=WEBM)
    assert response.status_code == 502
    assert "sk-test" not in response.text
    assert len(paid.calls) == 1
