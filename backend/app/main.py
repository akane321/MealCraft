import gc
import threading
from contextlib import asynccontextmanager

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from app.agent import model_client
from app.api.router import api_router
from app.core.config import get_settings
from app.data.overrides import ensure_loaded
from app.db.session import SessionLocal
from app.repositories.recipe import POOL_CHECK_SECONDS, _reload_pool, keep_planning_pool_warm

settings = get_settings()
# A chat turn's planning allocates millions of short-lived objects beside the recipe pool's million or so long-lived
# ones. At Python's default first-generation threshold (700) the collector ran about 3,000 times in one budget
# refusal and took 2.5-3.3 s of its 8-10 s (WP1 1b, 2026-10-08); every 50,000 allocations it runs a few dozen times
# for the same garbage. When garbage is collected changes nothing the planner computes.
GC_FIRST_GENERATION = 50_000
gc.set_threshold(GC_FIRST_GENERATION)
cors_origins = list(
    dict.fromkeys(
        [
            *settings.cors_origins,
            f"http://localhost:{settings.frontend_port}",
            f"http://127.0.0.1:{settings.frontend_port}",
        ]
    )
)


def warm_planning_pool(stop: threading.Event) -> None:
    """Keeps the planner's recipe pool loaded and young until shutdown: loading it in a request took 3.5-4.5 s on
    the walkthrough's PostgreSQL, enough to take an OpenAI-mode answer past 10 s (ADR-0046 section 3)."""
    with SessionLocal() as session:
        while not ensure_loaded(session):
            if stop.wait(POOL_CHECK_SECONDS):
                return
        bind = session.get_bind()
    keep_planning_pool_warm(bind, stop)


def load_planning_pool() -> None:
    """The pool's first load, before the API answers: a message sent as soon as it answered after a restart waited
    about 1.2 s for `warm_planning_pool` to load it, taking the demo's cold budget refusal past its 6 s (WP1 1b,
    2026-10-08). A database not readable yet is left to `warm_planning_pool`, which retries with its backoff."""
    with SessionLocal() as session:
        if ensure_loaded(session):
            _reload_pool(session.get_bind())


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
    stop = threading.Event()
    if settings.planning_pool_cache_seconds:
        load_planning_pool()  # in the startup itself: the API answers once the pool is in hand
        threading.Thread(target=warm_planning_pool, args=(stop,), name="warm-planning-pool", daemon=True).start()
    yield
    stop.set()


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
