"""API v1 — 文章接口

端点:
  GET    /api/v1/posts                    — 分页文章列表
  GET    /api/v1/posts/{post_id}          — 文章详情
  POST   /api/v1/posts                    — 创建文章 (管理员)
  PUT    /api/v1/posts/{post_id}          — 更新文章 (管理员)
  DELETE /api/v1/posts/{post_id}          — 删除文章 (管理员)
  POST   /api/v1/posts/{post_id}/like     — 点赞/取消点赞
"""
from __future__ import annotations

from typing import Annotated

from fastapi import APIRouter, Depends, HTTPException, Query, Request, status
from pydantic import BaseModel, Field
from sqlalchemy.orm import Session

from core.api_schemas import ApiResponse, error, paginated, success
from core.error_codes import ErrorCode
from core.permissions import OptionalUser, RequireAdmin, get_current_user, is_admin_username
from database import get_db
from services.post_service import (
    get_post_detail_payload,
    remove_post,
    toggle_post_like,
)
from crud.crud_post import create_post as crud_create_post
from web_deps import verify_csrf

router = APIRouter(prefix="/posts", tags=["Posts API v1"])


# ------------------------------------------------------------------
# Schema
# ------------------------------------------------------------------

class CreatePostRequest(BaseModel):
    title: str = Field(..., min_length=1, max_length=200, description="文章标题")
    content: str = Field(..., min_length=1, description="Markdown 内容")
    tech_tags: str | None = Field(default=None, description="技术标签，逗号分隔")
    image_path: str | None = Field(default=None, description="封面图片路径")


class UpdatePostRequest(BaseModel):
    title: str | None = Field(default=None, min_length=1, max_length=200, description="文章标题")
    content: str | None = Field(default=None, min_length=1, description="Markdown 内容")
    tech_tags: str | None = Field(default=None, description="技术标签")
    image_path: str | None = Field(default=None, description="封面图片路径")


class PostDetail(BaseModel):
    id: int
    title: str
    content: str
    like_count: int = 0
    image_path: str | None = None
    created_at: str | None = None
    author_name: str = "Ado_Jk"
    liked: bool = False


class PostListItem(BaseModel):
    id: int
    title: str
    like_count: int = 0
    created_at: str | None = None


class LikeResponse(BaseModel):
    liked: bool = False
    like_count: int = 0


# ------------------------------------------------------------------
# 端点
# ------------------------------------------------------------------

@router.get("", response_model=ApiResponse)
async def list_posts(
    db: Session = Depends(get_db),
    page: Annotated[int, Query(ge=1)] = 1,
    page_size: Annotated[int, Query(ge=1, le=50)] = 20,
):
    """文章列表（分页）。"""
    from models import Post

    total = db.query(Post).filter(Post.deleted_at.is_(None)).count()
    posts = (
        db.query(Post)
        .filter(Post.deleted_at.is_(None))
        .order_by(Post.created_at.desc())
        .offset((page - 1) * page_size)
        .limit(page_size)
        .all()
    )
    items = [
        PostListItem(
            id=p.id, title=p.title, like_count=int(p.like_count or 0),
            created_at=p.created_at.isoformat() if p.created_at else None,
        ) for p in posts
    ]
    return paginated([i.model_dump() for i in items], total, page, page_size)


@router.get("/{post_id}", response_model=ApiResponse)
async def get_post(
    post_id: int,
    db: Session = Depends(get_db),
    request: Request = None,
):
    """文章详情。"""
    current_username = await get_current_user(request) if request else None
    try:
        payload = get_post_detail_payload(db, post_id, current_username)
    except ValueError:
        return error(ErrorCode.POST_NOT_FOUND, "文章不存在")

    post = payload["post"]
    return success(PostDetail(
        id=post.id, title=post.title, content=post.content,
        like_count=int(post.like_count or 0), image_path=post.image_path,
        created_at=post.created_at.isoformat() if post.created_at else None,
        liked=payload.get("post_liked", False),
    ).model_dump())


@router.post("", response_model=ApiResponse)
async def create_new_post(
    body: CreatePostRequest,
    request: Request,
    db: Session = Depends(get_db),
):
    """创建文章（管理员）。"""
    username = await get_current_user(request)
    if not username or not is_admin_username(username):
        return error(ErrorCode.FORBIDDEN, "需要管理员权限")

    verify_csrf(request)

    try:
        post = crud_create_post(db, title=body.title, content=body.content,
                                image_path=body.image_path, tech_tag=body.tech_tags)
    except Exception as exc:
        return error(ErrorCode.DB_ERROR, str(exc))

    return success(
        PostDetail(id=post.id, title=post.title, content=post.content,
                   created_at=post.created_at.isoformat() if post.created_at else None).model_dump(),
        "文章创建成功",
    )


@router.put("/{post_id}", response_model=ApiResponse)
async def update_existing_post(
    post_id: int,
    body: UpdatePostRequest,
    request: Request,
    db: Session = Depends(get_db),
):
    """更新文章（管理员）。"""
    from models import Post

    username = await get_current_user(request)
    if not username or not is_admin_username(username):
        return error(ErrorCode.FORBIDDEN, "需要管理员权限")

    verify_csrf(request)

    post = db.query(Post).filter(Post.id == post_id, Post.deleted_at.is_(None)).first()
    if not post:
        return error(ErrorCode.POST_NOT_FOUND, "文章不存在")

    if body.title is not None:
        post.title = body.title
    if body.content is not None:
        post.content = body.content
    if body.tech_tags is not None:
        post.tech_tag = body.tech_tags
    if body.image_path is not None:
        post.image_path = body.image_path

    db.commit()
    db.refresh(post)

    return success(
        PostDetail(id=post.id, title=post.title, content=post.content,
                   created_at=post.created_at.isoformat() if post.created_at else None).model_dump(),
        "文章更新成功",
    )


@router.delete("/{post_id}", response_model=ApiResponse, operation_id="delete_post_v1")
async def delete_post(
    post_id: int,
    request: Request,
    db: Session = Depends(get_db),
):
    """删除文章（管理员）。"""
    username = await get_current_user(request)
    if not username:
        return error(ErrorCode.UNAUTHORIZED, "未登录")
    if not is_admin_username(username):
        return error(ErrorCode.FORBIDDEN, "需要管理员权限")

    verify_csrf(request)

    try:
        ok = remove_post(db, post_id, username)
    except PermissionError:
        return error(ErrorCode.FORBIDDEN, "无权删除")
    if not ok:
        return error(ErrorCode.POST_NOT_FOUND, "文章不存在")

    return success(None, "文章已删除")


@router.post("/{post_id}/like", response_model=ApiResponse, operation_id="like_post_v1")
async def like_post(
    post_id: int,
    request: Request,
    db: Session = Depends(get_db),
):
    """点赞/取消点赞文章。"""
    verify_csrf(request)
    username = await get_current_user(request)

    try:
        result = toggle_post_like(db, post_id, username)
    except ValueError:
        return error(ErrorCode.POST_NOT_FOUND, "文章不存在")

    if "error" in result:
        return error(ErrorCode.DUPLICATE_LIKE, result["error"])

    return success(LikeResponse(liked=result.get("liked", False),
                                like_count=result.get("like_count", 0)).model_dump(),
                   "操作成功")
