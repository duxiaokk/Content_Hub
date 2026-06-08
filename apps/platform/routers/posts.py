"""
功能摘要：本文件提供文章相关的数据接口，供前端异步获取文章详情与点赞状态。

初学者指南：
这个文件与 pages.py 不同，它不返回完整网页，而是返回结构化数据。
前端通过调用这里的接口来更新局部内容（比如点赞后实时刷新数字）。
如果你要调整文章的数据返回格式，重点关注 get_post_detail() 函数。

主要成员：
- get_post_detail(): 返回单篇文章的标题、内容、点赞数等结构化数据
- like_post(): 处理文章点赞请求，校验跨站请求伪造令牌后执行
- delete_post(): 处理文章删除请求，仅允许管理员操作
"""
from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException, Request, status
from sqlalchemy.orm import Session

from database import get_db
from services.post_service import get_post_detail_payload, remove_post, toggle_post_like
from web_deps import get_optional_user, verify_csrf

router = APIRouter(prefix="/api/v1/posts", tags=["Posts API"])


@router.get("/{post_id}")
def get_post_detail(
    post_id: int,
    db: Session = Depends(get_db),
    current_username: str | None = Depends(get_optional_user),
):
    try:
        payload = get_post_detail_payload(db, post_id, current_username)
    except ValueError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc

    post = payload["post"]
    return {
        "id": post.id,
        "title": post.title,
        "content": post.content,
        "like_count": int(post.like_count or 0),
        "image_path": post.image_path,
        "created_at": post.created_at.isoformat() if post.created_at else None,
        "author_name": "Ado_Jk",
        "liked": payload["post_liked"],
    }


@router.post("/{post_id}/like")
def like_post(
    post_id: int,
    request: Request,
    db: Session = Depends(get_db),
    current_username: str | None = Depends(get_optional_user),
):
    verify_csrf(request)
    result = toggle_post_like(db, post_id, current_username)
    if "error" in result:
        raise HTTPException(status_code=404, detail=result["error"])
    return result


@router.delete("/{post_id}")
def delete_post(
    post_id: int,
    request: Request,
    db: Session = Depends(get_db),
    current_username: str | None = Depends(get_optional_user),
):
    verify_csrf(request)
    if not current_username:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="not logged in")
    try:
        ok = remove_post(db, post_id, current_username)
    except PermissionError as exc:
        raise HTTPException(status_code=403, detail=str(exc)) from exc
    if not ok:
        raise HTTPException(status_code=404, detail="post not found")
    return {"message": "deleted"}
