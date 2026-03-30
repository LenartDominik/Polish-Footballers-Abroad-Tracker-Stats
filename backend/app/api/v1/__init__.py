"""API v1 router configuration."""

from fastapi import APIRouter

from app.api.v1 import players, leagues, health, heatmaps, admin

api_router = APIRouter()

api_router.include_router(health.router, tags=["health"])
api_router.include_router(players.router, prefix="/players", tags=["players"])
api_router.include_router(leagues.router, prefix="/leagues", tags=["leagues"])
api_router.include_router(heatmaps.router, prefix="/players", tags=["heatmaps"])
api_router.include_router(admin.router, tags=["admin"])
