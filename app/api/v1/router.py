from fastapi import APIRouter

from app.api.v1.routes import analyses, health, library

api_router = APIRouter()
api_router.include_router(health.router, tags=["health"])
api_router.include_router(analyses.router, tags=["analysis"])
api_router.include_router(library.router)
