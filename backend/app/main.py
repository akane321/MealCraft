from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

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

app = FastAPI(
    title=settings.app_name,
    version=settings.app_version,
    description="Constraint-aware weekly dietary planning API",
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=cors_origins,
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

app.include_router(api_router, prefix="/api")
