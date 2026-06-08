"""API v1 — 管理员接口

端点:
  GET    /api/v1/admin/health            — 系统健康检查（含 DB/Redis）
  GET    /api/v1/admin/stats             — 平台统计（文章数/用户数/评论数）
  GET    /api/v1/admin/users             — 用户列表（管理员）
"""
from __future__ import annotations

from fastapi import APIRouter, Depends, Request
from sqlalchemy.orm import Session

from core.api_schemas import ApiResponse, error, success
from core.error_codes import ErrorCode
from core.permissions import get_current_user, is_admin_username, require_admin
from database import check_db_health, get_db

router = APIRouter(prefix="/admin", tags=["Admin API v1"])


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
    comment_count = db.query(Comment).filter(Comment.deleted_at.is_(None)).count()
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
