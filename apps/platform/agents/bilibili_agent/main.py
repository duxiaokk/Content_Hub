"""Bilibili Agent — 专门为 B 站抓取设计的 Multi-Agent 节点。

暴露标准 Agent 接口：
  POST /api/internal/agent/run
  GET  /health

支持 task_type:
  - bilibili.fetch.user   抓取 UP 主视频列表
  - bilibili.fetch.info   获取 UP 主空间信息
"""
from __future__ import annotations

import logging

from fastapi import FastAPI
from pydantic import BaseModel

from apps.platform.agents.bilibili_agent.fetcher import (
    _resolve_cookie,
    fetch_user_space_info,
    fetch_user_videos,
)

logger = logging.getLogger(__name__)
app = FastAPI(title="Bilibili Agent", version="0.1.0")


class AgentRunRequest(BaseModel):
    """Agent 执行请求。"""

    task_type: str
    trace_id: str | None = None
    payload: dict = {}


@app.post("/api/internal/agent/run")
async def run_agent(request: AgentRunRequest) -> dict:
    """执行 B 站抓取任务。"""
    task_type = request.task_type
    payload = request.payload
    logger.info("[BilibiliAgent] task_type=%s trace_id=%s", task_type, request.trace_id)

    if task_type == "bilibili.fetch.user":
        mid = payload.get("mid") or payload.get("user_id")
        if not mid:
            # 尝试从 intent 中解析 UID
            intent = payload.get("intent", "")
            import re
            m = re.search(r'uid[:：\s]*(\d+)', intent, re.IGNORECASE)
            if m:
                mid = int(m.group(1))
        if not mid:
            return {"status": "FAILED", "error": "missing 'mid' or 'user_id' in payload"}
        try:
            cookie = _resolve_cookie(payload)
            keyword = payload.get("keyword")
            videos = await fetch_user_videos(int(mid), ps=payload.get("ps", 30), cookie=cookie, keyword=keyword)
            return {
                "status": "SUCCEEDED",
                "result": {
                    "mid": mid,
                    "videos": videos,
                    "count": len(videos),
                },
            }
        except Exception as exc:
            logger.exception("[BilibiliAgent] fetch_user_videos failed")
            return {"status": "FAILED", "error": str(exc)}

    if task_type == "bilibili.fetch.info":
        mid = payload.get("mid") or payload.get("user_id")
        if not mid:
            return {"status": "FAILED", "error": "missing 'mid' or 'user_id' in payload"}
        try:
            cookie = _resolve_cookie(payload)
            info = await fetch_user_space_info(int(mid), cookie=cookie)
            return {
                "status": "SUCCEEDED",
                "result": {"mid": mid, "info": info},
            }
        except Exception as exc:
            logger.exception("[BilibiliAgent] fetch_user_space_info failed")
            return {"status": "FAILED", "error": str(exc)}

    return {"status": "FAILED", "error": f"unknown task_type: {task_type}"}


@app.get("/health")
def health() -> dict:
    return {"status": "ok"}
