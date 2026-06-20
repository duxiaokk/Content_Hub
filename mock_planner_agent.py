from __future__ import annotations

from fastapi import FastAPI
from pydantic import BaseModel

app = FastAPI()


class AgentRunRequest(BaseModel):
    task_type: str
    trace_id: str | None = None
    payload: dict = {}


@app.post("/api/internal/agent/run")
async def run_agent(request: AgentRunRequest):
    """Mock Planner Agent — 返回简单的任务分解计划。"""
    intent = request.payload.get("intent", "")
    lower = intent.lower()

    plan = {"tasks": []}

    # B 站特殊意图检测
    if any(k in lower for k in ["b站", "bilibili", "up主", "uid"]):
        plan["tasks"].append({
            "task_key": "fetch",
            "task_type": "bilibili.fetch.user",
            "depends_on": [],
            "input_payload": {"intent": intent},
        })
    elif "抓取" in lower or "fetch" in lower:
        plan["tasks"].append({
            "task_key": "fetch",
            "task_type": "content.fetch",
            "depends_on": [],
            "input_payload": {"intent": intent},
        })
    if "分析" in lower or "analyze" in lower:
        plan["tasks"].append({
            "task_key": "analyze",
            "task_type": "data.analyze",
            "depends_on": ["fetch"] if plan["tasks"] else [],
            "input_payload": {"intent": intent},
        })
    # 默认总是包含生成任务
    deps = []
    if any(t["task_key"] == "analyze" for t in plan["tasks"]):
        deps = ["analyze"]
    elif any(t["task_key"] == "fetch" for t in plan["tasks"]):
        deps = ["fetch"]
    plan["tasks"].append({
        "task_key": "generate",
        "task_type": "content.generate",
        "depends_on": deps,
        "input_payload": {"intent": intent},
    })

    return {"result": plan}


@app.get("/health")
def health():
    return {"status": "ok"}
