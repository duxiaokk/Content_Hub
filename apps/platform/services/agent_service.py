# services/agent_service.py
"""BlogAgent 核心实现。

关键设计：
- 只读安全：所有工具均为数据读取，禁止修改/删除
- 动态上下文：系统提示词自动注入最近文章信息
- 温度控制：生成类任务用较高 temperature，润色类用较低
- 统一接口：对外暴露 4 个核心方法，对应 4 种功能
"""

from __future__ import annotations

from typing import AsyncIterable

from sqlalchemy.orm import Session

from core.config import settings
from models import Post
from services.agent_prompts import (
    BLOG_AGENT_SYSTEM_PROMPT,
    get_analyze_prompt,
    get_draft_prompt,
    get_outline_prompt,
    get_polish_prompt,
    get_recommend_prompt,
)
from services.agent_tools import prepare_blog_data, prepare_existing_posts
from services.llm_client import LLMProvider, get_default_provider


class BlogAgent:
    """多 Agent 任务编排平台智能体。"""

    # 功能 → temperature 映射
    TEMPERATURE_MAP = {
        "generate_outline": 0.7,
        "recommend_topics": 0.7,
        "polish_text": 0.3,
        "analyze_blog": 0.4,
    }

    def __init__(self, db: Session, llm: LLMProvider | None = None):
        self.db = db
        self.llm = llm or get_default_provider()

    # ------------------------------------------------------------------
    # 内部方法
    # ------------------------------------------------------------------
    async def _build_system_prompt(self) -> str:
        """构建系统提示词，注入动态上下文（最近文章）。"""
        prompt = BLOG_AGENT_SYSTEM_PROMPT

        recent_posts = (
            self.db.query(Post)
            .filter(Post.deleted_at.is_(None))
            .order_by(Post.created_at.desc())
            .limit(5)
            .all()
        )

        if recent_posts:
            posts_info = "\n".join(
                [
                    f"- 《{p.title}》（{p.like_count or 0}赞）"
                    for p in recent_posts
                ]
            )
            prompt += f"\n\n## 最近发布的文章\n{posts_info}"

        return prompt

    async def _call_llm(self, user_prompt: str, task_type: str) -> str:
        """调用 LLM，自动选择 temperature（非流式）。"""
        system_prompt = await self._build_system_prompt()
        temperature = self.TEMPERATURE_MAP.get(task_type, 0.7)
        return await self.llm.chat(system_prompt, user_prompt, temperature=temperature)

    async def _call_llm_stream(
        self, user_prompt: str, task_type: str
    ) -> AsyncIterable[str]:
        """调用 LLM，自动选择 temperature（流式）。"""
        system_prompt = await self._build_system_prompt()
        temperature = self.TEMPERATURE_MAP.get(task_type, 0.7)
        async for chunk in self.llm.chat_stream(system_prompt, user_prompt, temperature=temperature):
            yield chunk

    # ------------------------------------------------------------------
    # 对外接口（非流式）
    # ------------------------------------------------------------------
    async def generate_outline(self, topic: str, style: str = "tutorial") -> str:
        """生成文章大纲。"""
        prompt = get_outline_prompt(topic=topic, style=style)
        return await self._call_llm(prompt, task_type="generate_outline")

    async def polish_text(self, text: str, tone: str = "professional") -> str:
        """润色和优化文章段落。"""
        prompt = get_polish_prompt(text=text, tone=tone)
        return await self._call_llm(prompt, task_type="polish_text")

    async def analyze_blog(self) -> str:
        """分析平台数据并给出运营建议。"""
        data_json = prepare_blog_data(self.db)
        prompt = get_analyze_prompt(data_json=data_json)
        return await self._call_llm(prompt, task_type="analyze_blog")

    async def recommend_topics(self, tech_stack: str | None = None) -> str:
        """基于已有内容推荐新选题。"""
        existing_posts = prepare_existing_posts(self.db)
        stack = tech_stack or ", ".join(settings.tech_tags)
        prompt = get_recommend_prompt(
            existing_posts=existing_posts,
            tech_stack=stack,
        )
        return await self._call_llm(prompt, task_type="recommend_topics")

    # ------------------------------------------------------------------
    # 对外接口（流式 SSE）
    # ------------------------------------------------------------------
    async def generate_outline_stream(
        self, topic: str, style: str = "tutorial"
    ) -> AsyncIterable[str]:
        """流式生成文章大纲。"""
        prompt = get_outline_prompt(topic=topic, style=style)
        async for chunk in self._call_llm_stream(prompt, task_type="generate_outline"):
            yield chunk

    async def polish_text_stream(
        self, text: str, tone: str = "professional"
    ) -> AsyncIterable[str]:
        """流式润色文章段落。"""
        prompt = get_polish_prompt(text=text, tone=tone)
        async for chunk in self._call_llm_stream(prompt, task_type="polish_text"):
            yield chunk

    async def analyze_blog_stream(self) -> AsyncIterable[str]:
        """流式分析平台数据。"""
        data_json = prepare_blog_data(self.db)
        prompt = get_analyze_prompt(data_json=data_json)
        async for chunk in self._call_llm_stream(prompt, task_type="analyze_blog"):
            yield chunk

    async def recommend_topics_stream(
        self, tech_stack: str | None = None
    ) -> AsyncIterable[str]:
        """流式推荐新选题。"""
        existing_posts = prepare_existing_posts(self.db)
        stack = tech_stack or ", ".join(settings.tech_tags)
        prompt = get_recommend_prompt(
            existing_posts=existing_posts,
            tech_stack=stack,
        )
        async for chunk in self._call_llm_stream(prompt, task_type="recommend_topics"):
            yield chunk

    async def generate_draft(self, topic: str, style: str = "tutorial") -> str:
        """生成完整文章草稿（非流式）。"""
        prompt = get_draft_prompt(topic=topic, style=style)
        return await self._call_llm(prompt, task_type="generate_draft")

    async def generate_draft_stream(
        self, topic: str, style: str = "tutorial"
    ) -> AsyncIterable[str]:
        """流式生成完整文章草稿。"""
        prompt = get_draft_prompt(topic=topic, style=style)
        async for chunk in self._call_llm_stream(prompt, task_type="generate_draft"):
            yield chunk
