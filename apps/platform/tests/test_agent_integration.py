"""
Agent 集成测试：验证任务编排智能体的新增端点可正常访问。

注意：这些测试使用 Mock LLM，不消耗真实 API 额度。
"""

from __future__ import annotations

import os

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool

from database import Base, get_db
from main import app
from models import Post

# 内存数据库用于测试（StaticPool 确保所有连接共享同一内存实例）
TEST_DATABASE_URL = "sqlite:///:memory:"
engine = create_engine(
    TEST_DATABASE_URL,
    connect_args={"check_same_thread": False},
    poolclass=StaticPool,
)
TestingSessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)


def override_get_db():
    db = TestingSessionLocal()
    try:
        yield db
    finally:
        db.close()


client = TestClient(app)


@pytest.fixture(autouse=True)
def setup_db(monkeypatch):
    """每个测试前初始化内存数据库并插入示例数据。"""
    app.dependency_overrides[get_db] = override_get_db
    Base.metadata.create_all(bind=engine)
    monkeypatch.setenv("MOCK_LLM", "true")

    db = TestingSessionLocal()
    p1 = Post(title="FastAPI 入门", tech_tag="FastAPI", like_count=42)
    p2 = Post(title="SQLAlchemy 进阶", tech_tag="SQLAlchemy", like_count=28)
    db.add_all([p1, p2])
    db.commit()
    db.close()

    yield

    Base.metadata.drop_all(bind=engine)


def test_generate_outline():
    resp = client.post("/ai/outline", json={"topic": "JWT 认证", "style": "tutorial"})
    assert resp.status_code == 200
    data = resp.json()
    assert data["success"] is True
    assert "Mock 模式" in data["data"]
    assert data["meta"]["topic"] == "JWT 认证"


def test_polish_text():
    resp = client.post("/ai/polish", json={"text": "今天讲讲 fastapi 怎么连数据库", "tone": "professional"})
    assert resp.status_code == 200
    data = resp.json()
    assert data["success"] is True
    assert "Mock 模式" in data["data"]


def test_analyze_blog():
    resp = client.post("/ai/analyze", json={})
    assert resp.status_code == 200
    data = resp.json()
    assert data["success"] is True
    assert "Mock 模式" in data["data"]


def test_recommend_topics():
    resp = client.post("/ai/recommend", json={})
    assert resp.status_code == 200
    data = resp.json()
    assert data["success"] is True
    assert "Mock 模式" in data["data"]


def test_existing_draft_endpoint():
    """验证原有草稿接口仍然可用。"""
    resp = client.post("/ai/articles/draft", json={"topic": "测试", "style": "技术文章"})
    assert resp.status_code == 200
    data = resp.json()
    assert "测试" in data["title"]


# ── 页面访问级测试 ──

def test_architecture_page_accessible():
    """架构设计页正常渲染。"""
    resp = client.get("/architecture")
    assert resp.status_code == 200
    assert "架构设计" in resp.text
    assert "Ado_Jk Multi-Agent Orchestration Platform" in resp.text


def test_demo_page_accessible():
    """任务演示页正常渲染。"""
    resp = client.get("/demo")
    assert resp.status_code == 200
    assert "任务演示" in resp.text
    assert "执行流程" in resp.text


def test_top_page_accessible():
    """核心能力页正常渲染。"""
    resp = client.get("/top")
    assert resp.status_code == 200
    assert "核心能力" in resp.text
    assert "Planner" in resp.text
    assert "Scheduler Center" in resp.text
    assert "Agent Registry" in resp.text
    assert "Shared Memory" in resp.text


def test_top_page_has_capability_info():
    """核心能力页包含 task_type 和 Agent 信息。"""
    resp = client.get("/top")
    assert resp.status_code == 200
    assert "task_type" in resp.text.lower() or "plan.decompose" in resp.text or "comment.moderate" in resp.text


def test_demo_api_submit_mock():
    """演示 API 提交返回 mock 模式任务。"""
    resp = client.post("/api/demo/submit", json={"task_type": "demo.echo"})
    assert resp.status_code == 200
    data = resp.json()
    assert "task_id" in data
    assert data["mode"] in ("mock", "live")
    assert data["status"] == "pending"


def test_demo_api_status_polling():
    """演示 API 状态轮询推进到 success。"""
    submit = client.post("/api/demo/submit", json={"task_type": "demo.echo"})
    task_id = submit.json()["task_id"]
    status = client.get(f"/api/demo/status/{task_id}")
    assert status.status_code == 200
    data = status.json()
    assert data["status"] in ("pending", "running", "succeeded")


def test_demo_submit_task_type_preserved():
    """提交自定义 task_type 后，状态返回中应保留该 task_type。"""
    resp = client.post("/api/demo/submit", json={"task_type": "comment.moderate"})
    assert resp.status_code == 200
    task_id = resp.json()["task_id"]

    # 查询状态，验证 task_type 透传
    status = client.get(f"/api/demo/status/{task_id}")
    assert status.status_code == 200
    data = status.json()
    assert data["task_type"] == "comment.moderate"


def test_demo_submit_payload_preserved():
    """提交自定义 payload 后，状态返回中应保留对应 payload。"""
    custom_payload = {"text": "这是一条测试评论", "user_id": "u123"}
    resp = client.post("/api/demo/submit", json={
        "task_type": "comment.moderate",
        "payload": custom_payload,
    })
    assert resp.status_code == 200
    task_id = resp.json()["task_id"]

    status = client.get(f"/api/demo/status/{task_id}")
    assert status.status_code == 200
    data = status.json()
    assert data["payload"] == custom_payload


def test_platform_fields_persistence():
    """Post 模型支持新的平台语义字段。"""
    db = TestingSessionLocal()
    p = Post(title="测试平台字段", tech_tag="FastAPI", module_id="planner", scenario_type="demo", task_type="plan.decompose")
    db.add(p)
    db.commit()
    db.refresh(p)
    assert p.module_id == "planner"
    assert p.scenario_type == "demo"
    assert p.task_type == "plan.decompose"
    db.close()
