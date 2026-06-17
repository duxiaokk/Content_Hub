"""
功能摘要：本文件实现评论相关的核心业务逻辑，包括查询、发布、修改、删除与点赞。

初学者指南：
这个文件是"评论功能的幕后大脑"。它负责把路由层传来的参数转换成数据库操作，
并处理权限校验（比如只能删自己的评论）。如果你要调整评论的展示顺序或增加新互动功能，
重点关注 list_comment_page() 和 add_comment() 函数。

主要成员：
- list_comment_page(): 分页获取某篇文章的评论，附带点赞状态与用户名
- add_comment(): 校验内容长度与父评论存在性后，创建新评论
- toggle_comment_like(): 切换当前用户对某条评论的点赞状态并同步计数
"""
from __future__ import annotations

from typing import Optional

from sqlalchemy.orm import Session

from apps.platform import models
from apps.platform.crud.crud_comment import (
    create_comment,
    create_comment_like,
    delete_comment_like,
    get_active_comment,
    get_active_post,
    get_comment_like,
    get_liked_comment_ids,
    get_parent_comment,
    increment_comment_like_count,
    list_comments_with_usernames,
    soft_delete_comment,
    update_comment_content,
)
from apps.platform.crud.crud_user import get_user_by_username
from apps.platform.web_deps import is_admin


def comment_to_dict(comment: models.Comment, username: str, *, liked_by_me: bool = False) -> dict:
    return {
        "id": comment.id,
        "article_id": comment.article_id,
        "user_id": comment.user_id,
        "username": username,
        "parent_id": comment.parent_id,
        "content": comment.content,
        "like_count": int(comment.like_count or 0),
        "liked_by_me": bool(liked_by_me),
        "status": comment.status,
        "created_at": comment.created_at.isoformat() if comment.created_at else None,
        "updated_at": comment.updated_at.isoformat() if comment.updated_at else None,
    }


def list_comment_page(
    db: Session,
    *,
    post_id: int,
    page: int,
    page_size: int,
    username: Optional[str] = None,
) -> dict:
    post = get_active_post(db, post_id)
    if not post:
        raise ValueError("post not found")

    rows, total = list_comments_with_usernames(
        db,
        post_id,
        offset=(page - 1) * page_size,
        limit=page_size,
    )

    liked_ids: set[int] = set()
    if username and rows:
        current = get_user_by_username(db, username)
        if current:
            liked_ids = get_liked_comment_ids(
                db,
                current.id,
                [int(comment.id) for comment, _ in rows],
            )

    items = [
        comment_to_dict(comment, row_username, liked_by_me=(int(comment.id) in liked_ids))
        for comment, row_username in rows
    ]
    return {"items": items, "page": page, "page_size": page_size, "total": total}


def add_comment(
    db: Session,
    *,
    post_id: int,
    username: str,
    content: str,
    parent_id: int | None = None,
) -> models.Comment:
    post = get_active_post(db, post_id)
    if not post:
        raise ValueError("post not found")

    current = get_user_by_username(db, username)
    if not current:
        raise LookupError("not logged in")

    content = content.strip()
    if not content:
        raise ValueError("comment content cannot be empty")
    if len(content) > 2000:
        raise ValueError("comment content too long")

    if parent_id is not None:
        parent = get_parent_comment(db, post_id, parent_id)
        if not parent:
            raise ValueError("parent comment not found")

    return create_comment(
        db,
        article_id=post_id,
        user_id=current.id,
        content=content,
        parent_id=parent_id,
    )


def edit_comment(
    db: Session,
    *,
    comment_id: int,
    username: str,
    content: str,
) -> models.Comment:
    comment = get_active_comment(db, comment_id)
    if not comment:
        raise ValueError("comment not found")

    current = get_user_by_username(db, username)
    if not current:
        raise LookupError("not logged in")
    if comment.user_id != current.id:
        raise PermissionError("can only edit your own comment")

    content = content.strip()
    if not content:
        raise ValueError("comment content cannot be empty")
    if len(content) > 2000:
        raise ValueError("comment content too long")

    return update_comment_content(db, comment, content)


def remove_comment(
    db: Session,
    *,
    comment_id: int,
    username: str,
) -> models.Comment:
    comment = get_active_comment(db, comment_id)
    if not comment:
        raise ValueError("comment not found")

    current = get_user_by_username(db, username)
    if not current:
        raise LookupError("not logged in")
    if comment.user_id != current.id and not is_admin(username):
        raise PermissionError("can only delete your own comment")

    return soft_delete_comment(db, comment)


def toggle_comment_like(
    db: Session,
    *,
    comment_id: int,
    username: Optional[str],
) -> dict:
    comment = get_active_comment(db, comment_id)
    if not comment:
        raise ValueError("comment not found")

    current = get_user_by_username(db, username) if username else None
    if not current:
        updated = increment_comment_like_count(db, comment, 1)
        return {
            "article_id": comment.article_id,
            "like_count": int(updated.like_count or 0),
            "liked": False,
        }

    existing = get_comment_like(db, current.id, comment_id)
    if existing:
        delete_comment_like(db, existing)
        updated = increment_comment_like_count(db, comment, -1)
        return {
            "article_id": comment.article_id,
            "like_count": int(updated.like_count or 0),
            "liked": False,
        }

    create_comment_like(db, comment_id=comment_id, user_id=current.id)
    updated = increment_comment_like_count(db, comment, 1)
    return {
        "article_id": comment.article_id,
        "like_count": int(updated.like_count or 0),
        "liked": True,
    }
