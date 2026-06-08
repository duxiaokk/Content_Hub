"""
功能摘要：本文件封装评论相关的数据库增删改查操作。

初学者指南：
这个文件专门处理"评论数据"的读写。评论的发布、修改、删除、点赞记录
都通过这里的函数直接操作数据库。如果你要调整评论的查询逻辑（比如按热度排序），
重点关注 list_comments_with_usernames() 函数。

主要成员：
- list_comments_with_usernames(): 分页查询某篇文章下的所有有效评论并附带用户名
- create_comment(): 在数据库中插入一条新评论
- soft_delete_comment(): 将评论状态标记为已删除，保留原始数据
- toggle_comment_like(): 切换当前用户对某条评论的点赞状态
"""
from __future__ import annotations

from typing import Optional, Sequence, Set, Tuple

from sqlalchemy.orm import Session

import models


def get_active_post(db: Session, post_id: int) -> Optional[models.Post]:
    return (
        db.query(models.Post)
        .filter(models.Post.id == post_id, models.Post.deleted_at.is_(None))
        .first()
    )


def get_active_comment(db: Session, comment_id: int) -> Optional[models.Comment]:
    return (
        db.query(models.Comment)
        .filter(models.Comment.id == comment_id, models.Comment.status == "active")
        .first()
    )


def get_comment_by_id(db: Session, comment_id: int) -> Optional[models.Comment]:
    return db.query(models.Comment).filter(models.Comment.id == comment_id).first()


def get_parent_comment(db: Session, post_id: int, parent_id: int) -> Optional[models.Comment]:
    return (
        db.query(models.Comment)
        .filter(models.Comment.id == parent_id, models.Comment.article_id == post_id)
        .first()
    )


def list_comments_with_usernames(
    db: Session,
    post_id: int,
    *,
    offset: int,
    limit: int,
) -> Tuple[list[tuple[models.Comment, str]], int]:
    query = (
        db.query(models.Comment, models.User.username)
        .join(models.User, models.User.id == models.Comment.user_id)
        .filter(models.Comment.article_id == post_id, models.Comment.status == "active")
        .order_by(models.Comment.created_at.desc(), models.Comment.id.desc())
    )
    total = query.count()
    rows = query.offset(offset).limit(limit).all()
    return rows, total


def get_liked_comment_ids(
    db: Session,
    user_id: int,
    comment_ids: Sequence[int],
) -> Set[int]:
    if not comment_ids:
        return set()
    liked_rows = (
        db.query(models.CommentLike.comment_id)
        .filter(
            models.CommentLike.user_id == user_id,
            models.CommentLike.comment_id.in_(list(comment_ids)),
        )
        .all()
    )
    return {int(row[0]) for row in liked_rows}


def create_comment(
    db: Session,
    *,
    article_id: int,
    user_id: int,
    content: str,
    parent_id: int | None = None,
) -> models.Comment:
    comment = models.Comment(
        article_id=article_id,
        user_id=user_id,
        parent_id=parent_id,
        content=content,
    )
    db.add(comment)
    db.commit()
    db.refresh(comment)
    return comment


def update_comment_content(db: Session, comment: models.Comment, content: str) -> models.Comment:
    comment.content = content
    db.commit()
    db.refresh(comment)
    return comment


def soft_delete_comment(db: Session, comment: models.Comment) -> models.Comment:
    comment.status = "deleted"
    db.commit()
    db.refresh(comment)
    return comment


def get_comment_like(db: Session, user_id: int, comment_id: int) -> Optional[models.CommentLike]:
    return (
        db.query(models.CommentLike)
        .filter(
            models.CommentLike.user_id == user_id,
            models.CommentLike.comment_id == comment_id,
        )
        .first()
    )


def increment_comment_like_count(
    db: Session, comment: models.Comment, delta: int
) -> models.Comment:
    comment.like_count = max(0, int(comment.like_count or 0) + int(delta))
    db.commit()
    db.refresh(comment)
    return comment


def create_comment_like(
    db: Session,
    *,
    comment_id: int,
    user_id: int,
) -> models.CommentLike:
    like = models.CommentLike(comment_id=comment_id, user_id=user_id)
    db.add(like)
    db.commit()
    return like


def delete_comment_like(db: Session, like: models.CommentLike) -> None:
    db.delete(like)
    db.commit()
