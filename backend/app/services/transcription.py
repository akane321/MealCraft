"""Speech to text for the chat's voice button (ADR-0116): one short clip in, one transcript out, nothing stored."""

import threading

from openai import APIConnectionError, APIError, OpenAI

from app.agent import model_client

FIXTURE_TEXT = "Plan dinners for two this week, no beef, under 80 dollars."
FILE_EXTENSIONS = {
    "audio/webm": "webm",
    "audio/mp4": "m4a",
    "audio/ogg": "ogg",
    "audio/wav": "wav",
    "audio/mpeg": "mp3",
}
LANGUAGES = ["en", "zh"]
KEYWORDS = ["kangkong", "char siew", "chye sim", "laksa", "sambal", "tau kwa"]
PROMPT = "Simplified Chinese where Chinese is spoken; Singapore food, dishes and prices."

_lock = threading.Lock()
_paid_clips = 0  # paid calls since the process started; the cap is per run of the app, so it resets on restart


class TranscriptionLimitReached(RuntimeError):
    pass


class TranscriptionFailed(RuntimeError):
    pass


class FixtureTranscriber:
    def transcribe(self, audio: bytes, content_type: str) -> str:
        return FIXTURE_TEXT


class OpenAITranscriber:
    def __init__(self, *, api_key: str, model: str, timeout_seconds: float, max_clips: int) -> None:
        self.model = model
        self.max_clips = max_clips
        # No SDK retries: the one retry below keeps a clip's cost and wait bounded.
        self.client = OpenAI(
            api_key=api_key, timeout=timeout_seconds, max_retries=0, http_client=model_client.http_client()
        )

    def transcribe(self, audio: bytes, content_type: str) -> str:
        global _paid_clips
        with _lock:
            if _paid_clips >= self.max_clips:
                raise TranscriptionLimitReached
            _paid_clips += 1
        file = (f"clip.{FILE_EXTENSIONS[content_type]}", audio, content_type)
        for attempt in (1, 2):
            try:
                response = self.client.audio.transcriptions.create(
                    model=self.model, file=file, languages=LANGUAGES, keywords=KEYWORDS, prompt=PROMPT
                )
                break
            except APIConnectionError as error:  # a timeout is one: try once more
                if attempt == 2:
                    raise TranscriptionFailed from error
            except APIError as error:
                raise TranscriptionFailed from error
        text = response if isinstance(response, str) else getattr(response, "text", "")
        return text.strip()
