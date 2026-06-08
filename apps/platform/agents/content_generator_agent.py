"""Content Generator Agent — 独立 FastAPI 服务

内容生成 Agent：生成博文、大纲、摘要、社交媒体帖子、SEO 内容、多语言变体等。

任务类型: content.generate, content.blog_post, content.outline, content.summarize,
          content.generate.seo_content, content.generate.variants

特性:
  - 多语言支持（zh/en/ja/ko）
  - SEO 优化模式（meta_description, keywords, reading_time）
  - A/B 变体生成（指定 variants 生成多版本）
  - 图像提示词生成（DALL-E / Midjourney 风格）

输入:  content_type + topic + instructions + style + language + seo + variants
输出:  generated title + content + outline + tags + (seo fields) + (image_prompt) + (variants)

启动:     python -m agents.content_generator_agent --port 8130
"""
from __future__ import annotations

import json
import math
import os
from typing import Any

import httpx

from agents.base_agent import AgentConfig, BaseAgent


# ------------------------------------------------------------------
# 语言 → 系统提示词
# ------------------------------------------------------------------

LANGUAGE_SYSTEM_PROMPTS: dict[str, dict[str, str]] = {
    "zh": {
        "blog_post": "你是一位资深博客作者。根据用户要求撰写高质量中文博客文章。输出格式：先用一行写标题，然后空一行，再写正文。",
        "outline": "你是一位内容策划师。根据用户主题生成详细的中文文章大纲。使用列表格式输出，每个要点一行。",
        "summary": "你是一位编辑。将给定的内容精炼为简洁中文摘要。直接输出摘要，不要多余的话。",
        "social_media": "你是一位社交媒体运营。根据用户要求撰写引人注目的中文社交媒体帖子。输出简短的帖子，并附上推荐标签。",
        "email": "你是一位商务写作专家。根据用户要求撰写专业中文邮件。输出邮件主题和正文。",
        "seo_content": "你是一位SEO优化专家和资深博主。生成SEO友好的中文内容，输出包含标题、元描述建议、正文和关键词。",
    },
    "en": {
        "blog_post": "You are a senior blog writer. Write a high-quality blog post in English based on user requirements. Output format: title on the first line, then a blank line, then the body.",
        "outline": "You are a content strategist. Generate a detailed English article outline based on the user's topic. Use list format, one bullet per line.",
        "summary": "You are an editor. Condense the given content into a concise English summary. Output the summary directly, nothing extra.",
        "social_media": "You are a social media manager. Write an engaging English social media post based on user requirements. Output a short post with recommended hashtags.",
        "email": "You are a business writing expert. Write a professional English email based on user requirements. Output subject line and body.",
        "seo_content": "You are an SEO expert and senior blogger. Generate SEO-friendly English content. Output should include title, meta description suggestion, body, and keywords.",
    },
    "ja": {
        "blog_post": "あなたは経験豊富なブログライターです。ユーザーの要件に基づいて高品質な日本語のブログ記事を書いてください。出力形式：1行目にタイトル、空白行の後に本文。",
        "outline": "あなたはコンテンツ戦略家です。ユーザーのトピックに基づいて詳細な日本語の記事アウトラインを生成してください。リスト形式で、1行に1つのポイントを出力してください。",
        "summary": "あなたは編集者です。与えられたコンテンツを簡潔な日本語の要約にまとめてください。要約のみを直接出力してください。",
        "social_media": "あなたはソーシャルメディアマネージャーです。ユーザーの要件に基づいて魅力的な日本語のソーシャルメディア投稿を書いてください。短い投稿と推奨ハッシュタグを出力してください。",
        "email": "あなたはビジネスライティングの専門家です。ユーザーの要件に基づいて専門的な日本語のメールを書いてください。件名と本文を出力してください。",
        "seo_content": "あなたはSEO専門家でありシニアブロガーです。SEOに最適化された日本語のコンテンツを生成してください。出力にはタイトル、メタディスクリプション案、本文、キーワードを含めてください。",
    },
    "ko": {
        "blog_post": "당신은 시니어 블로그 작가입니다. 사용자 요구사항에 따라 고품질 한국어 블로그 글을 작성하세요. 출력 형식: 첫 줄에 제목, 빈 줄 후 본문.",
        "outline": "당신은 콘텐츠 전략가입니다. 사용자 주제에 따라 상세한 한국어 아티클 아웃라인을 생성하세요. 리스트 형식으로, 한 줄에 하나씩 출력하세요.",
        "summary": "당신은 편집자입니다. 주어진 콘텐츠를 간결한 한국어 요약으로 정리하세요. 요약만 직접 출력하세요.",
        "social_media": "당신은 소셜 미디어 매니저입니다. 사용자 요구사항에 따라 매력적인 한국어 소셜 미디어 게시물을 작성하세요. 짧은 게시물과 추천 해시태그를 출력하세요.",
        "email": "당신은 비즈니스 글쓰기 전문가입니다. 사용자 요구사항에 따라 전문적인 한국어 이메일을 작성하세요. 제목과 본문을 출력하세요.",
        "seo_content": "당신은 SEO 전문가이자 시니어 블로거입니다. SEO에 최적화된 한국어 콘텐츠를 생성하세요. 출력에는 제목, 메타 설명 제안, 본문, 키워드가 포함되어야 합니다.",
    },
}

# 回退兼容：原来的 CONTENT_SYSTEM_PROMPTS 作为 zh 默认值
CONTENT_SYSTEM_PROMPTS = LANGUAGE_SYSTEM_PROMPTS["zh"]

# 风格变体描述（用于 A/B 生成）
VARIANT_STYLES: list[str] = [
    "专业严谨风格（professional）",
    "轻松对话风格（conversational）",
    "故事叙述风格（storytelling）",
    "教程指南风格（tutorial）",
    "观点评论风格（opinion）",
    "数据驱动风格（data-driven）",
    "极简摘要风格（minimalist）",
    "深度分析风格（deep-dive）",
]


class ContentGeneratorAgent(BaseAgent):
    """Content Generator Agent — 内容生成。"""

    def supported_task_types(self) -> list[str]:
        return [
            "content.generate", "content.blog_post", "content.outline",
            "content.summarize", "content.social_media", "content.email",
            "content.generate.seo_content", "content.generate.variants",
        ]

    async def execute(self, task_type: str, payload: dict[str, Any], trace_id: str | None) -> dict[str, Any]:
        content_type = str(payload.get("content_type", task_type.replace("content.", "").replace("generate.", "")))
        topic = str(payload.get("topic", payload.get("intent", "")))
        instructions = str(payload.get("instructions", ""))
        style = str(payload.get("style", "professional"))
        target_audience = str(payload.get("target_audience", ""))
        context = payload.get("context", {}) if isinstance(payload.get("context"), dict) else {}
        reference_materials = payload.get("reference_materials", []) if isinstance(payload.get("reference_materials"), list) else []

        # 多语言支持
        language = str(payload.get("language", "zh")).lower()
        if language not in LANGUAGE_SYSTEM_PROMPTS:
            language = "zh"

        # SEO 模式
        seo_enabled = bool(payload.get("seo", False))

        # A/B 变体
        variants = payload.get("variants")
        variant_count = max(1, min(int(variants), 8)) if variants is not None else None

        if self.config.mock_llm or not self.config.llm_api_key:
            return self._generate_mock(content_type, topic, instructions, language, seo_enabled, variant_count)

        return await self._generate_with_llm(
            content_type, topic, instructions, style, target_audience,
            context, reference_materials, language, seo_enabled, variant_count,
        )

    async def _generate_with_llm(
        self,
        content_type: str,
        topic: str,
        instructions: str,
        style: str,
        audience: str,
        context: dict,
        references: list,
        language: str = "zh",
        seo_enabled: bool = False,
        variant_count: int | None = None,
    ) -> dict:
        # 如果请求变体，使用独立流程
        if variant_count is not None and variant_count > 1:
            return await self._generate_variants(
                content_type, topic, instructions, style, audience,
                context, references, language, seo_enabled, variant_count,
            )

        # 单次生成
        system_prompt = self._get_system_prompt(content_type, language)

        user_prompt_parts = [f"主题：{topic}"]
        if instructions:
            user_prompt_parts.append(f"要求：{instructions}")
        if style:
            user_prompt_parts.append(f"风格：{style}")
        if audience:
            user_prompt_parts.append(f"目标读者：{audience}")
        if references:
            refs_text = "\n".join(json.dumps(r, ensure_ascii=False)[:500] for r in references[:3])
            user_prompt_parts.append(f"参考资料：\n{refs_text}")

        body = {
            "model": self.config.llm_model,
            "messages": [
                {"role": "system", "content": system_prompt},
                {"role": "user", "content": "\n".join(user_prompt_parts)},
            ],
            "temperature": 0.7,
            "max_tokens": 4000,
        }
        async with httpx.AsyncClient(timeout=60.0) as client:
            resp = await client.post(
                f"{self.config.llm_base_url}/chat/completions",
                json=body,
                headers={"Authorization": f"Bearer {self.config.llm_api_key}"},
            )
        resp.raise_for_status()
        raw_content = resp.json()["choices"][0]["message"]["content"]

        # 解析标题和正文
        lines = raw_content.strip().split("\n")
        title = lines[0].lstrip("# ").strip() if lines else topic
        body_text = "\n".join(lines[1:]).strip() if len(lines) > 1 else raw_content

        # 标签
        tags = self._extract_tags(topic, raw_content)

        result: dict[str, Any] = {
            "content_type": content_type,
            "language": language,
            "title": title,
            "content": body_text,
            "outline": self._extract_outline(lines, content_type),
            "tags": tags,
            "token_count": len(raw_content) // 3,
        }

        # SEO 增强
        if seo_enabled:
            result.update(self._build_seo_fields(title, body_text, tags, language))

        # 图像提示词
        result["image_prompt"] = self._generate_image_prompt(title, body_text, language)

        return result

    # ------------------------------------------------------------------
    # A/B 变体生成
    # ------------------------------------------------------------------

    async def _generate_variants(
        self,
        content_type: str,
        topic: str,
        instructions: str,
        style: str,
        audience: str,
        context: dict,
        references: list,
        language: str,
        seo_enabled: bool,
        variant_count: int,
    ) -> dict:
        system_prompt = self._get_system_prompt(content_type, language)

        results: list[dict] = []
        # 取不同风格用于变体
        chosen_styles = VARIANT_STYLES[:variant_count]

        for idx, variant_style in enumerate(chosen_styles):
            user_prompt_parts = [
                f"主题：{topic}",
                f"风格：{variant_style}",
                f"这是变体 #{idx + 1}，请生成不同风格的内容。",
            ]
            if instructions:
                user_prompt_parts.append(f"要求：{instructions}")
            if audience:
                user_prompt_parts.append(f"目标读者：{audience}")

            body = {
                "model": self.config.llm_model,
                "messages": [
                    {"role": "system", "content": system_prompt},
                    {"role": "user", "content": "\n".join(user_prompt_parts)},
                ],
                "temperature": 0.8,
                "max_tokens": 4000,
            }
            async with httpx.AsyncClient(timeout=60.0) as client:
                resp = await client.post(
                    f"{self.config.llm_base_url}/chat/completions",
                    json=body,
                    headers={"Authorization": f"Bearer {self.config.llm_api_key}"},
                )
            resp.raise_for_status()
            raw = resp.json()["choices"][0]["message"]["content"]
            lines_raw = raw.strip().split("\n")
            var_title = lines_raw[0].lstrip("# ").strip() if lines_raw else topic
            var_body = "\n".join(lines_raw[1:]).strip() if len(lines_raw) > 1 else raw
            var_tags = self._extract_tags(topic, raw)

            variant_entry: dict[str, Any] = {
                "variant_index": idx + 1,
                "variant_style": variant_style,
                "title": var_title,
                "content": var_body,
                "outline": self._extract_outline(lines_raw, content_type),
                "tags": var_tags,
                "token_count": len(raw) // 3,
            }
            if seo_enabled:
                variant_entry.update(self._build_seo_fields(var_title, var_body, var_tags, language))
            variant_entry["image_prompt"] = self._generate_image_prompt(var_title, var_body, language)
            results.append(variant_entry)

        return {
            "content_type": content_type,
            "language": language,
            "variant_count": len(results),
            "variants": results,
        }

    # ------------------------------------------------------------------
    # SEO 字段生成
    # ------------------------------------------------------------------

    def _build_seo_fields(self, title: str, content: str, tags: list[str], language: str) -> dict:
        # 生成 meta_description（截取前 160 字符）
        clean_content = content.replace("\n", " ").strip()
        meta_description = clean_content[:160]
        if len(clean_content) > 160:
            meta_description = meta_description.rsplit(" ", 1)[0] + "..."

        # 估算阅读时间（中文 ~400 字/分钟, 英文 ~200 词/分钟）
        if language == "zh":
            reading_time_minutes = max(1, math.ceil(len(content) / 400))
        else:
            word_count = len(clean_content.split())
            reading_time_minutes = max(1, math.ceil(word_count / 200))

        return {
            "meta_description": meta_description,
            "keywords": tags[:10],
            "reading_time_minutes": reading_time_minutes,
        }

    # ------------------------------------------------------------------
    # 图像提示词生成
    # ------------------------------------------------------------------

    def _generate_image_prompt(self, title: str, content: str, language: str) -> str:
        """根据内容生成 DALL-E / Midjourney 风格的图像提示词。"""
        # 提取内容关键词（取首段，最多 200 字）
        snippet = content[:200].replace("\n", " ")
        prompt = (
            f"A high-quality blog header illustration representing: {title}. "
            f"Context: {snippet}. "
            "Style: modern digital illustration, clean composition, vibrant colors, "
            "professional and engaging, suitable for a tech/lifestyle blog."
        )
        return prompt

    # ------------------------------------------------------------------
    # 获取语言特定的系统提示词
    # ------------------------------------------------------------------

    def _get_system_prompt(self, content_type: str, language: str) -> str:
        lang_prompts = LANGUAGE_SYSTEM_PROMPTS.get(language, LANGUAGE_SYSTEM_PROMPTS["zh"])
        return lang_prompts.get(content_type, lang_prompts.get("blog_post", lang_prompts["blog_post"]))

    # ------------------------------------------------------------------
    # 轮廓提取
    # ------------------------------------------------------------------

    def _extract_outline(self, lines: list[str], content_type: str) -> list[str]:
        if content_type == "outline":
            return lines[:15]
        # 提取以列表符号开头的行作为轮廓
        outline = []
        for line in lines[1:]:
            stripped = line.strip()
            if stripped and (stripped.startswith(("- ", "* ", "+ ", "#"))):
                outline.append(stripped.lstrip("-*+# "))
        return outline[:10]

    def _generate_mock(
        self, content_type: str, topic: str, instructions: str,
        language: str = "zh", seo_enabled: bool = False,
        variant_count: int | None = None,
    ) -> dict:
        # 变体模式
        if variant_count is not None and variant_count > 1:
            chosen = VARIANT_STYLES[:variant_count]
            mock_variants = []
            for idx, vs in enumerate(chosen):
                entry: dict[str, Any] = {
                    "variant_index": idx + 1,
                    "variant_style": vs,
                    "title": f"[{vs}] {topic or 'Mock Variant Content'}",
                    "content": f"这是关于 '{topic}' 的第 {idx+1} 个变体（{vs}）。\n\nInstructions: {instructions}",
                    "outline": [f"{vs} - Part 1", f"{vs} - Part 2", f"{vs} - Part 3"],
                    "tags": [topic, "AI-generated", content_type],
                    "token_count": 50,
                }
                if seo_enabled:
                    entry.update({
                        "meta_description": f"{vs}: {topic} - meta description",
                        "keywords": [topic, "mock", vs],
                        "reading_time_minutes": 1,
                    })
                entry["image_prompt"] = f"DALL-E prompt for {topic} in {vs} style"
                mock_variants.append(entry)
            return {
                "content_type": content_type,
                "language": language,
                "variant_count": len(mock_variants),
                "variants": mock_variants,
            }

        result: dict[str, Any] = {
            "content_type": content_type,
            "language": language,
            "title": topic or "Mock Generated Content",
            "content": f"这是关于 '{topic}' 的模拟生成内容。\n\nInstructions: {instructions}\n\n这是模拟 AI 生成的文章正文，实际部署时将调用 LLM API。",
            "outline": [f"Part 1: {topic}简介", f"Part 2: 核心内容", "Part 3: 总结"],
            "tags": [topic, "AI-generated", content_type],
            "token_count": 50,
        }
        if seo_enabled:
            result.update({
                "meta_description": f"{topic} - 模拟SEO元描述",
                "keywords": [topic, "mock", "SEO"],
                "reading_time_minutes": 1,
            })
        result["image_prompt"] = f"DALL-E / Midjourney prompt for: {topic or 'blog illustration'}"
        return result

    def _extract_tags(self, topic: str, content: str) -> list[str]:
        tags = [topic]
        # 简单提取常见关键词
        keywords = ["Python", "FastAPI", "AI", "Agent", "博客", "技术", "教程", "开发"]
        for kw in keywords:
            if kw.lower() in content.lower():
                tags.append(kw)
        return tags[:5]


# =========================================================================
# 入口
# =========================================================================


def create_app():
    config = AgentConfig(
        agent_key=os.getenv("AGENT_KEY", "content-generator-agent"),
        agent_name=os.getenv("AGENT_NAME", "Content Generator Agent"),
        base_url=os.getenv("AGENT_BASE_URL", "http://127.0.0.1:8130"),
        task_types=[
            "content.generate", "content.blog_post", "content.outline",
            "content.summarize", "content.social_media", "content.email",
            "content.generate.seo_content", "content.generate.variants",
        ],
        capabilities={
            "kind": "content_generator",
            "content_types": ["blog_post", "outline", "summary", "social_media", "email", "seo_content"],
            "languages_supported": list(LANGUAGE_SYSTEM_PROMPTS.keys()),
            "features": ["multi_language", "seo_optimization", "ab_variants", "image_prompt_generation"],
        },
    )
    return ContentGeneratorAgent(config).create_app()


app = create_app()


if __name__ == "__main__":
    import uvicorn
    port = int(os.getenv("AGENT_PORT", "8130"))
    uvicorn.run("agents.content_generator_agent:app", host="0.0.0.0", port=port, reload=True)
