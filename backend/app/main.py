import threading
from contextlib import asynccontextmanager

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from app.agent import model_client
from app.api.router import api_router
from app.core.config import get_settings

settings = get_settings()
cors_origins = list(
    dict.fromkeys(
        [
            *settings.cors_origins,
            f"http://localhost:{settings.frontend_port}",
            f"http://127.0.0.1:{settings.frontend_port}",
        ]
    )
)


@asynccontextmanager
async def lifespan(_app: FastAPI):
    # With a key the console can switch the parser to OpenAI at any time (ADR-0047), so a key is what decides.
    # In the background: the API answers at once, and a request that arrives first only waits for the rest.
    if settings.openai_api_key is not None:
        threading.Thread(
            target=model_client.warm,
            args=(settings.openai_api_key.get_secret_value(), settings.openai_model),
            name="warm-openai",
            daemon=True,
        ).start()
    yield


app = FastAPI(
    title=settings.app_name,
    version=settings.app_version,
    description="Constraint-aware weekly dietary planning API",
    lifespan=lifespan,
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=cors_origins,
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

app.include_router(api_router, prefix="/api")
