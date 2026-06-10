"""
功能摘要：本文件负责为各个网页组装所需的数据，是视图层与数据层之间的桥梁。

初学者指南：
这个文件专门处理"页面需要哪些数据"。比如首页需要文章列表、归档页需要按月统计、
关于页需要作者信息，这些组装逻辑都在这里完成。如果你要修改页面展示的内容或排序规则，
重点关注 build_home_page_data() 和 build_post_detail_page_data() 等函数。

主要成员：
- build_home_page_data(): 组装首页所需的文章列表、分页与搜索条件
- build_archive_page_data(): 组装归档页所需的月份统计与文章筛选结果
- build_top_page_data(): 组装核心能力矩阵页面所需的模块数据与案例列表
"""
from __future__ import annotations

import math
import os
from datetime import datetime, timezone
from typing import Optional, Sequence
from urllib.parse import urlencode

from sqlalchemy.orm import Session

import models
from core.config import settings
from crud.crud_post import (
    create_post,
    get_all_posts,
    get_post_like_ids,
    get_posts,
    get_random_active_post,
    get_tech_posts,
    get_tech_tag_counts,
)
from crud.crud_user import get_user_by_username
from services.post_service import get_post_detail_payload, remove_post, toggle_post_like
from web_deps import ADMIN_USERNAME, is_admin

BASE_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
IMAGE_DIR = os.path.join(BASE_DIR, "image")
TECH_TAGS = settings.tech_tags

# 平台模块 → 能力映射（按 task_type + Agent 能力归类）
# module_posts 优先用 Post.module_id 匹配，其次用 tech_tag
CAPABILITY_MAP: dict[str, dict] = {
    "planner": {
        "task_types": ["plan.decompose", "plan.generate", "plan.evaluate"],
        "agent_types": ["PlannerAgent"],
        "tech_tags": ["FastAPI"],
        "description": "负责将复杂任务拆解为可执行子任务，并生成执行计划",
    },
    "scheduler": {
        "task_types": ["comment.moderate", "audit.draft", "ado_repost.run", "schedule.dispatch"],
        "agent_types": ["Dispatcher", "IngestWorker"],
        "tech_tags": ["SQLAlchemy"],
        "description": "统一管理所有异步任务的提交、调度、执行与重试",
    },
    "registry": {
        "task_types": ["agent.register", "agent.heartbeat", "agent.discover"],
        "agent_types": ["RegistryService"],
        "tech_tags": ["Python"],
        "description": "Agent 注册发现、健康检查与按 task_type 路由",
    },
    "memory": {
        "task_types": ["memory.set", "memory.get", "memory.lock", "memory.expire"],
        "agent_types": ["MempoolClient"],
        "tech_tags": ["SQLite"],
        "description": "跨服务共享记忆池，支持热数据缓存与分布式锁",
    },
}

PLATFORM_MODULES = [
    {
        "id": "planner",
        "name": "Planner",
        "mark": "P",
        "description": "任务拆解与规划引擎",
        "capabilities": ["目标分析", "子任务拆解", "依赖编排", "执行计划生成"],
    },
    {
        "id": "scheduler",
        "name": "Scheduler Center",
        "mark": "S",
        "description": "异步任务调度与分发中枢",
        "capabilities": ["任务投递", "状态机管理", "重试与超时", "并发控制"],
    },
    {
        "id": "registry",
        "name": "Agent Registry",
        "mark": "A",
        "description": "Agent 注册发现与健康检查",
        "capabilities": ["服务注册", "健康检查", "心跳管理", "task_type 路由"],
    },
    {
        "id": "memory",
        "name": "Shared Memory",
        "mark": "M",
        "description": "跨服务共享记忆池",
        "capabilities": ["热数据缓存", "幂等锁", "分布式状态", "冷热分离"],
    },
]


def get_month_key(value: datetime | None) -> str:
    if value is None:
        return ""
    if value.tzinfo is None:
        value = value.replace(tzinfo=timezone.utc)
    return value.astimezone(timezone.utc).strftime("%Y-%m")


def resolve_avatar_path(stored_path: str) -> Optional[str]:
    normalized = stored_path.replace("\\", "/").lstrip("/")
    candidates = [normalized]
    if normalized.startswith("avatars/"):
        candidates.append(normalized[len("avatars/") :])
    else:
        candidates.append(f"avatars/{normalized}")

    for candidate in candidates:
        if os.path.exists(os.path.join(IMAGE_DIR, candidate)):
            return candidate
    return normalized if os.path.exists(os.path.join(IMAGE_DIR, normalized)) else None


def get_current_user_profile(db: Session, username: Optional[str]) -> dict[str, Optional[str]]:
    if not username:
        return {"avatar_path": None}
    user = get_user_by_username(db, username)
    if not user or not user.avatar_path:
        return {"avatar_path": None}
    return {"avatar_path": resolve_avatar_path(user.avatar_path)}


def build_home_page_data(
    db: Session,
    *,
    username: Optional[str],
    search: str = "",
    month: Optional[str] = None,
    sort: Optional[str] = None,
    page: int = 1,
    page_size: int = 6,
    tech_tags: Sequence[str] = TECH_TAGS,
) -> dict:
    skip = (page - 1) * page_size
    posts, total_count = get_posts(
        db,
        search=search,
        month=month,
        sort=sort,
        tech_scope="general",
        tech_tags=tech_tags,
        skip=skip,
        limit=page_size,
    )

    page_title = ""
    if month:
        page_title = f"归档: {month}"
    elif sort == "top":
        page_title = "热门案例"

    total_pages = math.ceil(total_count / page_size) if total_count > 0 else 1
    params = {}
    if search:
        params["search"] = search
    if month:
        params["month"] = month
    if sort:
        params["sort"] = sort
    page_query = urlencode(params)
    pagination_base = f"/?{page_query}&page=" if page_query else "/?page="

    liked_post_ids: set[int] = set()
    if username and posts:
        user = get_user_by_username(db, username)
        if user:
            liked_post_ids = get_post_like_ids(db, user.id, [int(post.id) for post in posts])

    return {
        "posts": posts,
        "search": search,
        "month": month,
        "page_title": page_title,
        "liked_post_ids": list(liked_post_ids),
        "featured_posts": posts,
        "is_admin": is_admin(username),
        "current_user_avatar_path": get_current_user_profile(db, username)["avatar_path"],
        "pagination_base": pagination_base,
        "page": page,
        "total_pages": total_pages,
        "has_prev": page > 1,
        "has_next": page < total_pages,
    }


def build_archive_page_data(
    db: Session,
    *,
    username: Optional[str],
    month: Optional[str] = None,
) -> dict:
    posts = get_all_posts(db)
    profile = get_current_user_profile(db, username)
    if month:
        filtered = [
            post for post in posts if get_month_key(getattr(post, "created_at", None)) == month
        ]
        return {
            "mode": "list",
            "posts": filtered,
            "search": "",
            "month": month,
            "page_title": f"归档: {month}",
            "featured_posts": filtered,
            "is_admin": is_admin(username),
            "current_user_avatar_path": profile["avatar_path"],
        }

    counts: dict[str, int] = {}
    for post in posts:
        key = get_month_key(getattr(post, "created_at", None))
        if key:
            counts[key] = counts.get(key, 0) + 1

    archives = [
        {"month": key, "count": count}
        for key, count in sorted(counts.items(), key=lambda item: item[0], reverse=True)
    ]
    return {
        "mode": "archive",
        "posts": [],
        "search": "",
        "archives": archives,
        "is_admin": is_admin(username),
        "current_user_avatar_path": profile["avatar_path"],
    }


def build_top_page_data(db: Session, *, username: Optional[str]) -> dict:
    profile = get_current_user_profile(db, username)
    tech_posts = get_tech_posts(db, TECH_TAGS)
    tech_posts_by_tag: dict[str, list[models.Post]] = {tag: [] for tag in TECH_TAGS}
    for post in tech_posts:
        if post.tech_tag in tech_posts_by_tag:
            tech_posts_by_tag[post.tech_tag].append(post)

    # 按 CAPABILITY_MAP 真实统计每个模块的关联案例
    # 优先按 Post.module_id 匹配，无 module_id 时回退到 tech_tag
    module_posts: dict[str, list[models.Post]] = {}
    module_case_counts: dict[str, int] = {}
    for mod in PLATFORM_MODULES:
        cap = CAPABILITY_MAP.get(mod["id"], {})
        posts_for_mod: list[models.Post] = []
        seen_ids: set[int] = set()

        # 1) 按 module_id 匹配（新的平台语义字段）
        for post in tech_posts:
            if post.module_id == mod["id"] and post.id not in seen_ids:
                posts_for_mod.append(post)
                seen_ids.add(post.id)

        # 2) 回退：按 tech_tag 匹配
        for tag in cap.get("tech_tags", []):
            for post in tech_posts_by_tag.get(tag, []):
                if post.id not in seen_ids:
                    posts_for_mod.append(post)
                    seen_ids.add(post.id)

        module_posts[mod["id"]] = posts_for_mod
        module_case_counts[mod["id"]] = len(posts_for_mod)

    # 模块卡片
    platform_stack = []
    for mod in PLATFORM_MODULES:
        cap = CAPABILITY_MAP.get(mod["id"], {})
        tags = cap.get("tech_tags", [])
        action_tag = tags[0] if tags else TECH_TAGS[0]
        platform_stack.append({
            "name": mod["name"],
            "mark": mod["mark"],
            "description": mod["description"],
            "capabilities": mod["capabilities"],
            "task_types": cap.get("task_types", []),
            "agent_types": cap.get("agent_types", []),
            "case_count": module_case_counts.get(mod["id"], 0),
            "action_url": f"/create-post?{urlencode({'tech_tag': action_tag})}"
            if is_admin(username)
            else "/console",
        })

    return {
        "mode": "tech",
        "posts": [],
        "search": "",
        "page_title": "核心能力",
        "platform_stack": platform_stack,
        "platform_modules": PLATFORM_MODULES,
        "capability_map": CAPABILITY_MAP,
        "module_posts": module_posts,
        "is_admin": is_admin(username),
        "current_user_avatar_path": profile["avatar_path"],
    }


def build_about_page_data(db: Session, *, username: Optional[str]) -> dict:
    profile = get_current_user_profile(db, username)
    return {
        "mode": "about",
        "posts": [],
        "search": "",
        "is_admin": is_admin(username),
        "current_user_avatar_path": profile["avatar_path"],
    }


def build_architecture_page_data(db: Session, *, username: Optional[str]) -> dict:
    profile = get_current_user_profile(db, username)
    return {
        "mode": "architecture",
        "posts": [],
        "search": "",
        "is_admin": is_admin(username),
        "current_user_avatar_path": profile["avatar_path"],
        "platform_modules": PLATFORM_MODULES,
    }


def build_demo_page_data(db: Session, *, username: Optional[str]) -> dict:
    profile = get_current_user_profile(db, username)
    return {
        "mode": "demo",
        "posts": [],
        "search": "",
        "is_admin": is_admin(username),
        "current_user_avatar_path": profile["avatar_path"],
    }


def build_post_detail_page_data(
    db: Session,
    *,
    post_id: int,
    username: Optional[str],
) -> dict:
    payload = get_post_detail_payload(db, post_id, username)
    profile = get_current_user_profile(db, username)
    return {
        "post": payload["post"],
        "user": username,
        "author_name": ADMIN_USERNAME,
        "post_liked": payload["post_liked"],
        "is_admin": is_admin(username),
        "current_user_avatar_path": profile["avatar_path"],
    }


def build_create_post_page_data(
    db: Session,
    *,
    username: str,
    preselected_tech_tag: str,
) -> dict:
    profile = get_current_user_profile(db, username)
    return {
        "user": username,
        "current_user_avatar_path": profile["avatar_path"],
        "tech_tags": TECH_TAGS,
        "preselected_tech_tag": preselected_tech_tag if preselected_tech_tag in TECH_TAGS else "",
    }


def create_blog_post(
    db: Session,
    *,
    title: str,
    content: str,
    image_path: str | None = None,
    tech_tag: str | None = None,
) -> models.Post:
    return create_post(db, title=title, content=content, image_path=image_path, tech_tag=tech_tag)


def get_random_post(db: Session) -> Optional[models.Post]:
    return get_random_active_post(db)


def remove_blog_post(db: Session, post_id: int, username: str) -> bool:
    return remove_post(db, post_id, username)


def toggle_blog_post_like(db: Session, post_id: int, username: Optional[str]) -> dict:
    return toggle_post_like(db, post_id, username)
