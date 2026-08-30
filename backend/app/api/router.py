from fastapi import APIRouter

from app.api.routes.recipes import router as recipes_router
from app.api.routes.recommendations import router as recommendations_router
from app.api.routes.system import router as system_router

api_router = APIRouter()
api_router.include_router(system_router)
api_router.include_router(recipes_router)
api_router.include_router(recommendations_router)
