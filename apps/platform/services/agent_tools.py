# services/agent_tools.py
"""Agent 工具：数据准备和辅助函数。

所有函数均设计为纯读取操作，不修改数据库。
适配现有模型字段（deleted_at 软删除、tech_tag 单标签、article_id 外键）。
"""

from __future__ import annotations

import json
from typing import Any

from sqlalchemy.orm import Session

from apps.platform.models import Comment, Post


def _count_comments_for_post(db: Session, post_id: int) -> int:
    """手动统计某篇文章的评论数（现有模型未定义 relationship）。"""
    return db.query(Comment).filter(Comment.article_id == post_id).count()


def prepare_blog_data(db: Session, max_comments: int = 50) -> str:
    """准备平台分析所需的 JSON 数据。

    Args:
        db: 数据库 Session。
        max_comments: 最多取多少条近期评论。

    Returns:
        JSON 字符串。
    """
    posts = db.query(Post).filter(Post.deleted_at.is_(None)).all()
    comments = (
        db.query(Comment)
        .filter(Comment.status == "active")
        .order_by(Comment.created_at.desc())
        .limit(max_comments)
        .all()
    )

    # 统计标签频率（tech_tag 是单标签字段）
    tag_freq: dict[str, int] = {}
    for p in posts:
        if p.tech_tag:
            tag = p.tech_tag.strip()
            if tag:
                tag_freq[tag] = tag_freq.get(tag, 0) + 1

    data: dict[str, Any] = {
        "posts": [
            {
                "id": p.id,
                "title": p.title,
                "created_at": p.created_at.isoformat() if p.created_at else None,
                "like_count": p.like_count or 0,
                "comment_count": _count_comments_for_post(db, p.id),
                "tag": p.tech_tag,
            }
            for p in posts
        ],
        "comments": [
            {
                "id": c.id,
                "content": c.content[:200] if c.content else "",
                "article_id": c.article_id,
                "created_at": c.created_at.isoformat() if c.created_at else None,
            }
            for c in comments
        ],
        "tags": [{"name": k, "count": v} for k, v in sorted(tag_freq.items(), key=lambda x: -x[1])],
        "summary": {
            "total_posts": len(posts),
            "total_comments": db.query(Comment).filter(Comment.status == "active").count(),
            "total_likes": sum((p.like_count or 0) for p in posts),
        },
    }

    return json.dumps(data, ensure_ascii=False, indent=2)


def prepare_existing_posts(db: Session, limit: int = 30) -> str:
    """准备已有文章列表，用于选题推荐。

    Args:
        db: 数据库 Session。
        limit: 最多取多少篇文章。

    Returns:
        JSON 字符串。
    """
    posts = (
        db.query(Post)
        .filter(Post.deleted_at.is_(None))
        .order_by(Post.created_at.desc())
        .limit(limit)
        .all()
    )

    data = [
        {
            "title": p.title,
            "tag": p.tech_tag,
            "like_count": p.like_count or 0,
            "comment_count": _count_comments_for_post(db, p.id),
        }
        for p in posts
    ]

    return json.dumps(data, ensure_ascii=False, indent=2)
