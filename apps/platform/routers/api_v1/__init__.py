"""API v1 路由聚合器

统一挂载所有 v1 子路由到 /api/v1
"""
from __future__ import annotations

from fastapi import APIRouter

from apps.platform.routers.api_v1.admin import router as admin_router
from apps.platform.routers.api_v1.ai import router as ai_router
from apps.platform.routers.api_v1.auth import router as auth_router
from apps.platform.routers.api_v1.comments import router as comments_router
from apps.platform.routers.api_v1.console import router as console_router
from apps.platform.routers.api_v1.posts import router as posts_router

api_v1 = APIRouter(prefix="/api/v1")

api_v1.include_router(auth_router)
api_v1.include_router(posts_router)
api_v1.include_router(comments_router)
api_v1.include_router(ai_router)
api_v1.include_router(admin_router)
api_v1.include_router(console_router)
