"""API v1 — 评论接口

端点:
  GET    /api/v1/comments/{post_id}         — 评论列表（分页）
  POST   /api/v1/comments/{post_id}         — 发表评论
  PUT    /api/v1/comments/{comment_id}       — 编辑评论
  DELETE /api/v1/comments/{comment_id}       — 删除评论
  POST   /api/v1/comments/{comment_id}/like  — 点赞评论
"""
from __future__ import annotations

from typing import Optional

from fastapi import APIRouter, BackgroundTasks, Depends, HTTPException, Request
from pydantic import BaseModel, Field

from core.api_schemas import ApiResponse, error, paginated, success
from core.error_codes import ErrorCode
from database import get_db
from scheduler_client import get_scheduler_client
from services.comment_service import (
    add_comment,
    comment_to_dict,
    edit_comment,
    list_comment_page,
    remove_comment,
    toggle_comment_like,
)
from web_deps import comment_rate_limiter, get_client_ip, get_optional_user, verify_csrf

router = APIRouter(prefix="/comments", tags=["Comments API v1"])


# ------------------------------------------------------------------
# Schema
# ------------------------------------------------------------------

class CommentCreate(BaseModel):
    content: str = Field(..., min_length=1, max_length=2000, description="评论内容")
    parent_id: int | None = Field(default=None, description="父评论 ID")


class CommentUpdate(BaseModel):
    content: str = Field(..., min_length=1, max_length=2000, description="修改后的内容")


# ------------------------------------------------------------------
# 端点
# ------------------------------------------------------------------

@router.get("/{post_id}", response_model=ApiResponse)
async def list_comments(
    post_id: int,
    db=Depends(get_db),
    page: int = 1,
    page_size: int = 20,
    request: Request = None,
):
    """评论列表（分页）。"""
    page = max(1, int(page))
    page_size = max(1, min(50, int(page_size)))
    username = get_optional_user(request) if request else None

    try:
        result = list_comment_page(db, post_id=post_id, page=page, page_size=page_size, username=username)
    except ValueError:
        return error(ErrorCode.POST_NOT_FOUND, "文章不存在")

    return success(result)


@router.post("/{post_id}", response_model=ApiResponse)
async def create_comment(
    post_id: int,
    request: Request,
    body: CommentCreate,
    background_tasks: BackgroundTasks,
    db=Depends(get_db),
):
    """发表评论（需登录）。"""
    if not comment_rate_limiter.allow(get_client_ip(request)):
        return error(ErrorCode.RATE_LIMITED, "评论过于频繁，请稍后再试")

    verify_csrf(request)
    username = get_optional_user(request)
    if not username:
        return error(ErrorCode.UNAUTHORIZED, "请先登录")

    try:
        comment = add_comment(db, post_id=post_id, username=username,
                              content=body.content, parent_id=body.parent_id)
    except LookupError:
        return error(ErrorCode.USER_NOT_FOUND, "用户不存在")
    except ValueError as exc:
        detail = str(exc)
        code = ErrorCode.POST_NOT_FOUND if detail == "post not found" else ErrorCode.VALIDATION_ERROR
        return error(code, detail)

    payload = comment_to_dict(comment, username)

    # 异步提交评论审核
    import uuid
    trace_id = str(uuid.uuid4())
    try:
        background_tasks.add_task(
            get_scheduler_client().submit_task,
            task_type="comment.moderate",
            payload={"comment_id": int(comment.id), "post_id": int(post_id),
                     "username": str(username), "content": str(comment.content)},
            trace_id=trace_id,
            idempotency_key=f"comment.moderate:comment:{comment.id}",
        )
    except Exception:
        pass

    return success(payload, "评论发表成功")


@router.put("/{comment_id}", response_model=ApiResponse)
async def update_comment(
    comment_id: int,
    request: Request,
    body: CommentUpdate,
    db=Depends(get_db),
):
    """编辑评论（仅作者本人）。"""
    if not comment_rate_limiter.allow(get_client_ip(request)):
        return error(ErrorCode.RATE_LIMITED, "评论过于频繁")

    verify_csrf(request)
    username = get_optional_user(request)
    if not username:
        return error(ErrorCode.UNAUTHORIZED, "请先登录")

    try:
        comment = edit_comment(db, comment_id=comment_id, username=username, content=body.content)
    except LookupError:
        return error(ErrorCode.USER_NOT_FOUND, "用户不存在")
    except PermissionError:
        return error(ErrorCode.FORBIDDEN, "只能编辑自己的评论")
    except ValueError as exc:
        return error(ErrorCode.COMMENT_NOT_FOUND, str(exc))

    return success(comment_to_dict(comment, username), "评论已更新")


@router.delete("/{comment_id}", response_model=ApiResponse)
async def delete_comment(
    comment_id: int,
    request: Request,
    db=Depends(get_db),
):
    """删除评论（作者或管理员）。"""
    if not comment_rate_limiter.allow(get_client_ip(request)):
        return error(ErrorCode.RATE_LIMITED, "评论过于频繁")

    verify_csrf(request)
    username = get_optional_user(request)
    if not username:
        return error(ErrorCode.UNAUTHORIZED, "请先登录")

    try:
        remove_comment(db, comment_id=comment_id, username=username)
    except LookupError:
        return error(ErrorCode.USER_NOT_FOUND, "用户不存在")
    except PermissionError:
        return error(ErrorCode.FORBIDDEN, "只能删除自己的评论")
    except ValueError:
        return error(ErrorCode.COMMENT_NOT_FOUND, "评论不存在")

    return success(None, "评论已删除")


@router.post("/{comment_id}/like", response_model=ApiResponse)
async def like_comment(
    comment_id: int,
    request: Request,
    db=Depends(get_db),
):
    """点赞评论。"""
    if not comment_rate_limiter.allow(get_client_ip(request)):
        return error(ErrorCode.RATE_LIMITED, "评论过于频繁")

    verify_csrf(request)
    username = get_optional_user(request)

    try:
        result = toggle_comment_like(db, comment_id=comment_id, username=username)
    except ValueError:
        return error(ErrorCode.COMMENT_NOT_FOUND, "评论不存在")

    return success({"like_count": result["like_count"], "liked": result["liked"]}, "操作成功")
