from typing import Annotated

from fastapi import APIRouter, Depends, HTTPException, Request, status
from fastapi.concurrency import run_in_threadpool
from pydantic import BaseModel

from app.api.routes.auth import CurrentHouseholdCreatePlanCsrfDependency
from app.core.config import Settings, get_settings
from app.services.transcription import (
    FILE_EXTENSIONS,
    FixtureTranscriber,
    OpenAITranscriber,
    TranscriptionFailed,
    TranscriptionLimitReached,
)

router = APIRouter(prefix="/voice", tags=["voice"])


class VoiceTranscriptionResponse(BaseModel):
    text: str


def create_transcriber(settings: Settings) -> FixtureTranscriber | OpenAITranscriber:
    if settings.voice_transcription_provider == "openai" and settings.openai_api_key is not None:
        return OpenAITranscriber(
            api_key=settings.openai_api_key.get_secret_value(),
            model=settings.voice_transcription_model,
            timeout_seconds=settings.voice_transcription_timeout_seconds,
            max_clips=settings.voice_transcription_max_clips,
        )
    return FixtureTranscriber()


@router.post("/transcriptions", response_model=VoiceTranscriptionResponse)
async def transcribe_clip(
    request: Request,
    settings: Annotated[Settings, Depends(get_settings)],
    _current: CurrentHouseholdCreatePlanCsrfDependency,
) -> VoiceTranscriptionResponse:
    """The clip is the raw request body; it is sent on to the provider and not kept."""
    content_type = request.headers.get("content-type", "").split(";")[0].strip().lower()
    if content_type not in FILE_EXTENSIONS:
        raise HTTPException(status.HTTP_415_UNSUPPORTED_MEDIA_TYPE, "Send the clip as webm, mp4, ogg, wav or mp3.")
    limit = settings.voice_max_clip_bytes
    too_large = HTTPException(status.HTTP_413_CONTENT_TOO_LARGE, f"The clip is larger than {limit} bytes.")
    declared = request.headers.get("content-length", "")
    if declared.isdigit() and int(declared) > limit:
        raise too_large
    audio = bytearray()
    async for chunk in request.stream():
        if len(audio) + len(chunk) > limit:
            raise too_large
        audio += chunk
    if not audio:
        raise HTTPException(status.HTTP_400_BAD_REQUEST, "The clip is empty.")
    try:
        text = await run_in_threadpool(create_transcriber(settings).transcribe, bytes(audio), content_type)
    except TranscriptionLimitReached:
        raise HTTPException(
            status.HTTP_429_TOO_MANY_REQUESTS, "The transcription limit for this run of the app was reached."
        ) from None
    except TranscriptionFailed:
        raise HTTPException(status.HTTP_502_BAD_GATEWAY, "Transcription failed. Try again.") from None
    return VoiceTranscriptionResponse(text=text)
