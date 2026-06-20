"""Content Generator Agent — 内容生成器。

接收上游抓取结果，生成 Markdown 格式的内容摘要。

支持 task_type:
  - content.generate   基于上游数据生成摘要/报告

暴露标准 Agent 接口：
  POST /api/internal/agent/run
  GET  /health
"""
from __future__ import annotations

import html
import logging
from datetime import datetime

from fastapi import FastAPI
from pydantic import BaseModel

logger = logging.getLogger(__name__)
app = FastAPI(title="Content Generator Agent", version="0.1.0")


class AgentRunRequest(BaseModel):
    """Agent 执行请求。"""

    task_type: str
    trace_id: str | None = None
    payload: dict = {}


def _format_video_item(video: dict, idx: int) -> str:
    """格式化单个视频条目为 Markdown 列表项。"""
    title = video.get("title", "无标题")
    bvid = video.get("bvid", "")
    play = video.get("play", 0)
    like = video.get("like", 0)
    duration = video.get("duration", "未知")
    desc = video.get("description", "") or video.get("desc", "")

    # 清理 HTML 转义字符
    title = html.unescape(title)[:80]
    desc = html.unescape(desc)[:200]

    lines = [
        f"{idx}. **{title}**",
        f"   - 链接: https://www.bilibili.com/video/{bvid}",
        f"   - 播放量: {play}  |  点赞: {like}  |  时长: {duration}",
    ]
    if desc:
        lines.append(f"   - 简介: {desc}")
    lines.append("")
    return "\n".join(lines)


def _generate_summary(videos: list[dict]) -> str:
    """基于视频列表生成 Markdown 摘要报告。"""
    if not videos:
        return "未找到相关视频。"

    total_play = sum(v.get("play", 0) or 0 for v in videos)
    total_like = sum(v.get("like", 0) or 0 for v in videos)

    lines = [
        "# 内容摘要报告",
        "",
        f"生成时间: {datetime.now().strftime('%Y-%m-%d %H:%M')}",
        "",
        "## 统计",
        f"- 视频总数: {len(videos)}",
        f"- 总播放量: {total_play:,}",
        f"- 总点赞数: {total_like:,}",
        "",
        "## 视频列表",
        "",
    ]

    for i, video in enumerate(videos, 1):
        lines.append(_format_video_item(video, i))

    return "\n".join(lines)


@app.post("/api/internal/agent/run")
async def run_agent(request: AgentRunRequest) -> dict:
    """执行内容生成任务。"""
    task_type = request.task_type
    payload = request.payload
    logger.info("[GeneratorAgent] task_type=%s trace_id=%s", task_type, request.trace_id)

    if task_type == "content.generate":
        # 获取上游 fetch 结果
        upstream = payload.get("_upstream_results", {})
        fetch_output = upstream.get("fetch", {})
        videos = fetch_output.get("videos", [])

        # 如果没有上游结果，尝试从 payload 直接获取
        if not videos:
            videos = payload.get("videos", [])

        if not videos:
            logger.warning("[GeneratorAgent] No videos found in upstream results")
            return {
                "status": "SUCCEEDED",
                "result": {
                    "summary": "未找到可生成摘要的内容。",
                    "content": "",
                    "word_count": 0,
                },
            }

        # 生成摘要
        summary = _generate_summary(videos)
        return {
            "status": "SUCCEEDED",
            "result": {
                "summary": f"Generated summary for {len(videos)} videos",
                "content": summary,
                "word_count": len(summary),
                "video_count": len(videos),
            },
        }

    return {"status": "FAILED", "error": f"unknown task_type: {task_type}"}


@app.get("/health")
def health() -> dict:
    return {"status": "ok"}
