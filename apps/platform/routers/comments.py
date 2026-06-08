"""
功能摘要：本文件负责处理评论的查看、发布、修改、删除与实时推送接口。

初学者指南：
这个文件是博客系统的"评论区管家"。读者发表回复、点赞评论、实时看到新评论，
都依赖这里暴露的网络接口。如果你要修改评论的展示规则（比如限制字数），
重点关注 create_comment() 和 list_comments() 函数。

主要成员：
- list_comments(): 分页获取某篇文章下的评论列表
- create_comment(): 校验用户登录与请求频率后，将新评论写入数据库并实时推送
- comment_stream(): 建立服务器推送事件连接，让浏览器实时收到新评论
"""
from __future__ import annotations

import asyncio
import json
import logging
import uuid
from collections import defaultdict
from typing import Dict, Optional, Set

from fastapi import APIRouter, BackgroundTasks, Depends, HTTPException, Request
from fastapi.responses import StreamingResponse
from pydantic import BaseModel

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

router = APIRouter()
logger = logging.getLogger(__name__)


def _submit_comment_moderate_task(*, trace_id: str, payload: dict) -> None:
    try:
        get_scheduler_client().submit_task(
            task_type="comment.moderate",
            payload=payload,
            trace_id=trace_id,
            idempotency_key=f"comment.moderate:comment:{payload.get('comment_id')}",
        )
    except Exception:
        logger.exception("submit comment.moderate task failed")


class CommentCreateRequest(BaseModel):
    content: str
    parent_id: Optional[int] = None


class CommentUpdateRequest(BaseModel):
    content: str


class _CommentBus:
    def __init__(self) -> None:
        self._subs: Dict[int, Set[asyncio.Queue]] = defaultdict(set)

    def subscribe(self, post_id: int) -> asyncio.Queue:
        q: asyncio.Queue = asyncio.Queue(maxsize=200)
        self._subs[int(post_id)].add(q)
        return q

    def unsubscribe(self, post_id: int, q: asyncio.Queue) -> None:
        self._subs[int(post_id)].discard(q)

    def publish(self, post_id: int, event: dict) -> None:
        subs = list(self._subs.get(int(post_id), set()))
        for q in subs:
            try:
                q.put_nowait(event)
            except Exception as exc:
                logger.debug("comment bus publish failed for post_id=%s: %s", post_id, exc)


comment_bus = _CommentBus()


@router.get("/posts/{post_id}/comments")
def list_comments(
    post_id: int,
    db=Depends(get_db),
    page: int = 1,
    page_size: int = 20,
    user: Optional[str] = Depends(get_optional_user),
):
    page = max(1, int(page))
    page_size = max(1, min(50, int(page_size)))
    try:
        return list_comment_page(db, post_id=post_id, page=page, page_size=page_size, username=user)
    except ValueError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc


@router.get("/posts/{post_id}/comments/stream")
async def comment_stream(post_id: int, request: Request):
    async def gen():
        q = comment_bus.subscribe(post_id)
        try:
            yield "event: ready\ndata: {}\n\n"
            while True:
                if await request.is_disconnected():
                    break
                try:
                    ev = await asyncio.wait_for(q.get(), timeout=15.0)
                    payload = json.dumps(ev, ensure_ascii=False)
                    yield f"event: comment\ndata: {payload}\n\n"
                except asyncio.TimeoutError:
                    yield "event: ping\ndata: {}\n\n"
        finally:
            comment_bus.unsubscribe(post_id, q)

    return StreamingResponse(gen(), media_type="text/event-stream")


@router.post("/posts/{post_id}/comments")
async def create_comment(
    post_id: int,
    request: Request,
    body: CommentCreateRequest,
    background_tasks: BackgroundTasks,
    db=Depends(get_db),
    user: str = Depends(get_optional_user),
):
    if not comment_rate_limiter.allow(get_client_ip(request)):
        raise HTTPException(status_code=429, detail="too many requests, try again later")
    verify_csrf(request)

    if not user:
        raise HTTPException(status_code=401, detail="not logged in")

    try:
        comment = add_comment(
            db,
            post_id=post_id,
            username=user,
            content=body.content,
            parent_id=body.parent_id,
        )
    except LookupError as exc:
        raise HTTPException(status_code=401, detail=str(exc)) from exc
    except ValueError as exc:
        detail = str(exc)
        status_code = 404 if detail == "post not found" else 400
        raise HTTPException(status_code=status_code, detail=detail) from exc

    payload = comment_to_dict(comment, user)
    comment_bus.publish(post_id, {"type": "created", "comment": payload})
    trace_id = str(uuid.uuid4())
    background_tasks.add_task(
        _submit_comment_moderate_task,
        trace_id=trace_id,
        payload={
            "comment_id": int(comment.id),
            "post_id": int(post_id),
            "username": str(user),
            "content": str(comment.content),
            "parent_id": int(comment.parent_id) if comment.parent_id is not None else None,
        },
    )
    payload["trace_id"] = trace_id
    return payload


@router.put("/comments/{comment_id}")
async def update_comment(
    comment_id: int,
    request: Request,
    body: CommentUpdateRequest,
    db=Depends(get_db),
    user: str = Depends(get_optional_user),
):
    if not comment_rate_limiter.allow(get_client_ip(request)):
        raise HTTPException(status_code=429, detail="too many requests, try again later")
    verify_csrf(request)

    if not user:
        raise HTTPException(status_code=401, detail="not logged in")

    try:
        comment = edit_comment(db, comment_id=comment_id, username=user, content=body.content)
    except LookupError as exc:
        raise HTTPException(status_code=401, detail=str(exc)) from exc
    except PermissionError as exc:
        raise HTTPException(status_code=403, detail=str(exc)) from exc
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc

    payload = comment_to_dict(comment, user)
    comment_bus.publish(comment.article_id, {"type": "updated", "comment": payload})
    return payload


@router.delete("/comments/{comment_id}")
async def delete_comment(
    comment_id: int,
    request: Request,
    db=Depends(get_db),
    user: str = Depends(get_optional_user),
):
    if not comment_rate_limiter.allow(get_client_ip(request)):
        raise HTTPException(status_code=429, detail="too many requests, try again later")
    verify_csrf(request)

    if not user:
        raise HTTPException(status_code=401, detail="not logged in")

    try:
        comment = remove_comment(db, comment_id=comment_id, username=user)
    except LookupError as exc:
        raise HTTPException(status_code=401, detail=str(exc)) from exc
    except PermissionError as exc:
        raise HTTPException(status_code=403, detail=str(exc)) from exc
    except ValueError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc

    comment_bus.publish(comment.article_id, {"type": "deleted", "comment_id": comment_id})
    return {"message": "deleted"}


@router.post("/comments/{comment_id}/like")
async def like_comment(
    comment_id: int,
    request: Request,
    db=Depends(get_db),
):
    if not comment_rate_limiter.allow(get_client_ip(request)):
        raise HTTPException(status_code=429, detail="too many requests, try again later")
    verify_csrf(request)

    current_username = get_optional_user(request)
    try:
        result = toggle_comment_like(db, comment_id=comment_id, username=current_username)
    except ValueError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc

    comment_bus.publish(
        int(result["article_id"]),
        {"type": "liked", "comment_id": comment_id, "like_count": result["like_count"]},
    )
    return {"like_count": result["like_count"], "liked": result["liked"]}
