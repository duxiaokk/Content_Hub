"""API v1 — 管理员接口

端点:
  GET    /api/v1/admin/health            — 系统健康检查（含 DB/Redis）
  GET    /api/v1/admin/stats             — 平台统计（文章数/用户数/评论数）
  GET    /api/v1/admin/users             — 用户列表（管理员）
"""
from __future__ import annotations

import logging
import httpx
from fastapi import APIRouter, Depends, Query, Request
from sqlalchemy.orm import Session

from core.api_schemas import ApiResponse, error, success
from core.error_codes import ErrorCode
from core.permissions import RequireUser, get_current_user, is_admin_username, require_admin
from database import check_db_health, get_db
from scheduler_client import get_scheduler_client

router = APIRouter(prefix="/admin", tags=["Admin API v1"])
logger = logging.getLogger(__name__)


def _scheduler_get(path: str, params: dict | None = None) -> dict:
    client = get_scheduler_client()
    url = client.base_url + path
    headers = {"x-internal-token": client._config.internal_token}
    timeout = httpx.Timeout(float(client._config.timeout_seconds))
    with httpx.Client(timeout=timeout) as http_client:
        response = http_client.get(url, headers=headers, params=params)
    response.raise_for_status()
    payload = response.json()
    return payload if isinstance(payload, dict) else {"value": payload}


def _scheduler_get_or_default(path: str, default: dict, params: dict | None = None) -> dict:
    try:
        return _scheduler_get(path, params)
    except httpx.HTTPError as exc:
        logger.warning("scheduler request failed path=%s error=%s", path, exc)
        return default


@router.get("/health", response_model=ApiResponse)
async def health_check():
    """系统健康检查。"""
    db_status = check_db_health()
    return success({
        "status": "ok",
        "service": "platform",
        "db": db_status["status"],
    })


@router.get("/stats", response_model=ApiResponse)
async def platform_stats(db: Session = Depends(get_db), _admin: str = Depends(require_admin)):
    """平台统计信息（需管理员权限）。"""
    from models import Comment, Post, User

    post_count = db.query(Post).filter(Post.deleted_at.is_(None)).count()
    user_count = db.query(User).count()
    comment_count = db.query(Comment).count()
    total_likes = db.query(Post).filter(Post.deleted_at.is_(None)).count()  # placeholder

    return success({
        "posts": post_count,
        "users": user_count,
        "comments": comment_count,
        "total_likes": total_likes,
    })


@router.get("/users", response_model=ApiResponse)
async def list_users(
    db: Session = Depends(get_db),
    page: int = 1,
    page_size: int = 20,
    _admin: str = Depends(require_admin),
):
    """用户列表（需管理员权限）。"""
    from models import User
    from core.permissions import is_admin_username

    page = max(1, int(page))
    page_size = max(1, min(100, int(page_size)))

    total = db.query(User).count()
    users = db.query(User).order_by(User.id.desc()).offset((page - 1) * page_size).limit(page_size).all()

    items = [
        {
            "id": u.id,
            "username": u.username,
            "email": u.email,
            "role": "admin" if is_admin_username(u.username) else "user",
            "created_at": u.created_at.isoformat() if u.created_at else None,
        }
        for u in users
    ]
    return success({
        "items": items,
        "total": total,
        "page": page,
        "page_size": page_size,
    })


@router.get("/agents", response_model=ApiResponse)
async def list_agents(
    _user: RequireUser,
    page: int = Query(default=1, ge=1),
    page_size: int = Query(default=50, ge=1, le=200),
):
    payload = _scheduler_get_or_default(
        "/api/internal/scheduler/agents",
        {"items": []},
        {"offset": (page - 1) * page_size, "limit": page_size},
    )
    items = payload.get("items") if isinstance(payload.get("items"), list) else []
    mapped = [
        {
            "agent_key": item.get("agent_key"),
            "agent_name": item.get("name"),
            "agent_type": ",".join(item.get("task_types") or []) or "generic",
            "status": "online" if int(item.get("status") or 0) == 1 else "offline",
            "host": str(item.get("base_url") or "").replace("http://", "").replace("https://", ""),
            "port": 0,
            "load_score": 0,
            "last_heartbeat": item.get("last_heartbeat_at"),
        }
        for item in items
    ]
    return success(mapped)


@router.get("/agents/{agent_key}", response_model=ApiResponse)
async def get_agent(agent_key: str, _user: RequireUser):
    payload = _scheduler_get_or_default("/api/internal/scheduler/agents", {"items": []}, {"limit": 200, "offset": 0})
    items = payload.get("items") if isinstance(payload.get("items"), list) else []
    for item in items:
        if str(item.get("agent_key")) == agent_key:
            return success(
                {
                    "agent_key": item.get("agent_key"),
                    "agent_name": item.get("name"),
                    "agent_type": ",".join(item.get("task_types") or []) or "generic",
                    "status": "online" if int(item.get("status") or 0) == 1 else "offline",
                    "host": str(item.get("base_url") or "").replace("http://", "").replace("https://", ""),
                    "port": 0,
                    "load_score": 0,
                    "last_heartbeat": item.get("last_heartbeat_at"),
                }
            )
    return error(ErrorCode.NOT_FOUND, "Agent 不存在")


@router.get("/tasks", response_model=ApiResponse)
async def list_tasks(
    _user: RequireUser,
    page: int = Query(default=1, ge=1),
    page_size: int = Query(default=20, ge=1, le=100),
    status: str | None = Query(default=None),
    task_type: str | None = Query(default=None),
):
    params: dict[str, object] = {"offset": (page - 1) * page_size, "limit": page_size}
    if status:
        params["status"] = status
    if task_type:
        params["task_type"] = task_type
    payload = _scheduler_get_or_default("/api/internal/scheduler/tasks", {"items": [], "total": 0}, params)
    items = payload.get("items") if isinstance(payload.get("items"), list) else []
    mapped = [
        {
            "task_id": item.get("id"),
            "trace_id": item.get("trace_id"),
            "task_type": item.get("task_type"),
            "status": item.get("status"),
            "input_payload": {},
            "output_payload": {},
            "error_message": item.get("last_error"),
            "retry_count": item.get("attempt_count") or 0,
            "max_retries": 0,
            "created_at": item.get("created_at"),
            "updated_at": item.get("updated_at"),
        }
        for item in items
    ]
    return success({
        "items": mapped,
        "total": int(payload.get("total") or len(mapped)),
        "page": page,
        "page_size": page_size,
    })


@router.get("/tasks/{task_id}", response_model=ApiResponse)
async def get_task_detail(task_id: str, _user: RequireUser):
    item = _scheduler_get_or_default(f"/api/internal/scheduler/tasks/{task_id}", {})
    return success({
        "task_id": item.get("id"),
        "trace_id": item.get("trace_id"),
        "task_type": item.get("task_type"),
        "status": item.get("status"),
        "input_payload": item.get("payload") or {},
        "output_payload": item.get("result") or {},
        "error_message": item.get("last_error"),
        "retry_count": item.get("attempt_count") or 0,
        "max_retries": item.get("max_retries") or 0,
        "created_at": item.get("created_at"),
        "updated_at": item.get("updated_at"),
    })


@router.get("/orchestrations", response_model=ApiResponse)
async def list_orchestrations(
    _user: RequireUser,
    page: int = Query(default=1, ge=1),
    page_size: int = Query(default=20, ge=1, le=100),
    status: str | None = Query(default=None),
):
    params: dict[str, object] = {"offset": (page - 1) * page_size, "limit": page_size}
    if status:
        params["status"] = status
    payload = _scheduler_get_or_default("/api/internal/orchestration/runs", {"items": [], "total": 0}, params)
    items = payload.get("items") if isinstance(payload.get("items"), list) else []
    mapped = [
        {
            "id": item.get("run_id"),
            "status": item.get("status"),
            "dag_definition": {},
            "tasks": [],
            "created_at": item.get("created_at"),
            "updated_at": item.get("created_at"),
        }
        for item in items
    ]
    return success({
        "items": mapped,
        "total": int(payload.get("total") or len(mapped)),
        "page": page,
        "page_size": page_size,
    })


@router.get("/orchestrations/{run_id}", response_model=ApiResponse)
async def get_orchestration_detail(run_id: str, _user: RequireUser):
    item = _scheduler_get_or_default(f"/api/internal/orchestration/runs/{run_id}", {})
    return success({
        "id": item.get("run_id"),
        "status": item.get("status"),
        "dag_definition": {},
        "tasks": [],
        "created_at": item.get("created_at"),
        "updated_at": item.get("updated_at"),
    })
