from fastapi import APIRouter

from app.api.routes.agent import router as agent_router
from app.api.routes.meal_plans import router as meal_plans_router
from app.api.routes.products import router as products_router
from app.api.routes.recipes import router as recipes_router
from app.api.routes.recommendations import router as recommendations_router
from app.api.routes.system import router as system_router

api_router = APIRouter()
api_router.include_router(system_router)
api_router.include_router(agent_router)
api_router.include_router(meal_plans_router)
api_router.include_router(products_router)
api_router.include_router(recipes_router)
api_router.include_router(recommendations_router)
