"""
Agent SSE 流式接口测试。

验证要点：
- 流式端点返回 text/event-stream Content-Type
- SSE 消息格式正确（data: {...}\n\n）
- 包含 type=content 的数据块和 type=done 的结束标记
"""

from __future__ import annotations

import json
import os

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool

from database import Base, get_db
from main import app
from models import Post

# 内存数据库用于测试
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


def _parse_sse(response_text: str) -> list[dict]:
    """解析 SSE 响应文本为消息列表。"""
    messages = []
    for line in response_text.strip().split("\n\n"):
        if line.startswith("data: "):
            payload = json.loads(line[6:])
            messages.append(payload)
    return messages


def test_outline_stream():
    resp = client.post("/ai/outline/stream", json={"topic": "JWT 认证", "style": "tutorial"})
    assert resp.status_code == 200
    assert resp.headers["content-type"] == "text/event-stream; charset=utf-8"

    messages = _parse_sse(resp.text)
    assert len(messages) >= 2  # 至少包含 content + done

    # 检查是否包含 meta
    meta_msgs = [m for m in messages if m["type"] == "meta"]
    assert len(meta_msgs) == 1
    assert meta_msgs[0]["data"]["topic"] == "JWT 认证"

    # 检查是否包含 content
    content_msgs = [m for m in messages if m["type"] == "content"]
    assert len(content_msgs) >= 1
    full_text = "".join(m["data"] for m in content_msgs)
    assert "Mock 模式" in full_text

    # 检查是否以 done 结束
    assert messages[-1]["type"] == "done"


def test_polish_stream():
    resp = client.post("/ai/polish/stream", json={"text": "今天讲讲 fastapi", "tone": "casual"})
    assert resp.status_code == 200
    messages = _parse_sse(resp.text)
    assert any(m["type"] == "content" for m in messages)
    assert messages[-1]["type"] == "done"


def test_analyze_stream():
    resp = client.post("/ai/analyze/stream", json={})
    assert resp.status_code == 200
    messages = _parse_sse(resp.text)
    assert any(m["type"] == "content" for m in messages)
    assert messages[-1]["type"] == "done"


def test_recommend_stream():
    resp = client.post("/ai/recommend/stream", json={})
    assert resp.status_code == 200
    messages = _parse_sse(resp.text)
    assert any(m["type"] == "content" for m in messages)
    assert messages[-1]["type"] == "done"
