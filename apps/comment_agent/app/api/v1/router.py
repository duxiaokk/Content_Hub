from fastapi import APIRouter

from app.api.v1.endpoints import admin_seed, agents, event_logs, events, reviews, sites, tasks

api_router = APIRouter()
api_router.include_router(events.router, tags=["events"])
api_router.include_router(sites.router, prefix="/sites", tags=["sites"])
api_router.include_router(agents.router, prefix="/agents", tags=["agents"])
api_router.include_router(tasks.router, prefix="/tasks", tags=["tasks"])
api_router.include_router(event_logs.router, prefix="/event-logs", tags=["event-logs"])
api_router.include_router(reviews.router, prefix="/reviews", tags=["reviews"])
api_router.include_router(admin_seed.router, prefix="/admin", tags=["admin"])
