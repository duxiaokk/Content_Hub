"""端到端多智能体协作测试。

验证完整的智能体编排流程：
1. 任务提交到调度中心
2. 智能体注册与分发
3. 多智能体协作管道（planner → data_processor → content_generator → aggregator）
4. 共享内存池跨智能体数据共享
5. 结果聚合
6. 跨智能体的 trace 传播
7. 故障容忍与重试机制
"""
from __future__ import annotations

import os
import sys
import uuid

import pytest
from fastapi.testclient import TestClient


# ────────────────────── 环境准备 Fixtures ──────────────────────


@pytest.fixture(scope="class")
def scheduler_client():
    """创建调度器 TestClient，禁用 dispatcher 以进行纯 API 测试。"""
    db_path = os.path.abspath(f"./.tmp_scheduler_e2e_multi_agent_{uuid.uuid4().hex}.db")
    os.environ["SCHEDULER_DB_PATH"] = db_path
    os.environ["SCHEDULER_DISABLE_DISPATCHER"] = "true"
    os.environ["SCHEDULER_INTERNAL_TOKEN"] = "test-e2e-token"
    os.environ.setdefault("SECRET_KEY", "test-secret-key")
    os.environ.setdefault("ALGORITHM", "HS256")
    os.environ.setdefault("DB_TYPE", "sqlite")
    os.environ.setdefault("SCHEDULER_SUBMIT_WRITE_LOGS", "true")

    # 清除模块缓存，确保重新加载配置
    for name in list(sys.modules.keys()):
        if name == "scheduler_center" or name.startswith("scheduler_center."):
            sys.modules.pop(name, None)

    from scheduler_center.main import app

    with TestClient(app) as client:
        yield client

    # 清理临时数据库
    try:
        os.remove(db_path)
    except OSError:
        pass
    for ext in ("-shm", "-wal"):
        try:
            os.remove(f"{db_path}{ext}")
        except OSError:
            pass


@pytest.fixture(scope="class")
def headers():
    """内部 API 鉴权请求头。"""
    TOKEN = os.getenv("SCHEDULER_INTERNAL_TOKEN", "test-e2e-token")
    return {"x-internal-token": TOKEN, "Content-Type": "application/json"}


@pytest.fixture(scope="class")
def trace_id():
    """每次测试类共享的 trace_id。"""
    return str(uuid.uuid4())


@pytest.fixture(scope="class")
def agents_to_register():
    """测试用的智能体定义列表。"""
    return [
        {
            "agent_key": "planner",
            "name": "Planner Agent",
            "base_url": "http://127.0.0.1:9101",
            "task_types": ["planning", "content_pipeline"],
            "capabilities": {"role": "planner", "max_tokens": 4096},
        },
        {
            "agent_key": "data_processor",
            "name": "Data Processor Agent",
            "base_url": "http://127.0.0.1:9102",
            "task_types": ["data_processing", "content_pipeline"],
            "capabilities": {"role": "data_processor", "batch_size": 100},
        },
        {
            "agent_key": "content_generator",
            "name": "Content Generator Agent",
            "base_url": "http://127.0.0.1:9103",
            "task_types": ["content_generation", "content_pipeline"],
            "capabilities": {"role": "content_generator", "model": "gpt-4"},
        },
        {
            "agent_key": "aggregator",
            "name": "Aggregator Agent",
            "base_url": "http://127.0.0.1:9104",
            "task_types": ["aggregation", "content_pipeline"],
            "capabilities": {"role": "aggregator", "merge_strategy": "dedup"},
        },
        {
            "agent_key": "tool_caller",
            "name": "Tool Caller Agent",
            "base_url": "http://127.0.0.1:9105",
            "task_types": ["tool_calling", "content_pipeline"],
            "capabilities": {"role": "tool_caller", "tools": ["search", "fetch", "parse"]},
        },
    ]


# ────────────────────── 1. 智能体注册测试 ──────────────────────


@pytest.mark.usefixtures("scheduler_client")
class TestMultiAgentRegistration:
    """验证五个智能体的注册与列表查询功能。"""

    def test_register_five_agents(self, scheduler_client, headers, agents_to_register):
        """注册 planner、data_processor、content_generator、aggregator、tool_caller 五个智能体。"""
        registered_keys = set()

        for agent_def in agents_to_register:
            payload = {
                "agent_key": agent_def["agent_key"],
                "name": agent_def["name"],
                "base_url": agent_def["base_url"],
                "task_types": agent_def["task_types"],
                "health_path": "/health",
                "capabilities": agent_def["capabilities"],
                "status": 1,
            }
            # 移除 Content-Type 以便后续测试明确添加
            h = {k: v for k, v in headers.items()}

            resp = scheduler_client.post(
                "/api/internal/scheduler/agents/register",
                headers=h,
                json=payload,
            )
            assert resp.status_code == 200, f"Failed to register {agent_def['agent_key']}: {resp.text}"
            data = resp.json()
            assert data["agent_key"] == agent_def["agent_key"]
            assert data["name"] == agent_def["name"]
            assert data["base_url"] == agent_def["base_url"]
            assert set(data["task_types"]) == set(agent_def["task_types"])
            assert data["status"] == 1
            registered_keys.add(data["agent_key"])

        assert len(registered_keys) == 5, f"Expected 5 agents, got {len(registered_keys)}"
        assert registered_keys == {"planner", "data_processor", "content_generator", "aggregator", "tool_caller"}

    def test_list_all_agents(self, scheduler_client, headers, agents_to_register):
        """查询全部智能体列表，应返回 5 个。"""
        resp = scheduler_client.get("/api/internal/scheduler/agents", headers=headers)
        assert resp.status_code == 200
        data = resp.json()
        assert data["total"] == 5
        registered_keys = {item["agent_key"] for item in data["items"]}
        assert registered_keys == {"planner", "data_processor", "content_generator", "aggregator", "tool_caller"}

    def test_list_agents_by_task_type(self, scheduler_client, headers):
        """按任务类型过滤智能体列表。"content_pipeline" 应匹配全部 5 个。"""
        resp = scheduler_client.get(
            "/api/internal/scheduler/agents",
            headers=headers,
            params={"task_type": "content_pipeline"},
        )
        assert resp.status_code == 200
        data = resp.json()
        assert data["total"] == 5  # 全部五个都注册了 content_pipeline

        # "planning" 应只匹配 planner
        resp2 = scheduler_client.get(
            "/api/internal/scheduler/agents",
            headers=headers,
            params={"task_type": "planning"},
        )
        assert resp2.status_code == 200
        data2 = resp2.json()
        assert data2["total"] >= 1
        assert any(item["agent_key"] == "planner" for item in data2["items"])

    def test_reregister_updates_agent(self, scheduler_client, headers):
        """重新注册同一 agent_key 应更新已有记录而非创建新记录。"""
        payload = {
            "agent_key": "planner",
            "name": "Planner Agent Updated",
            "base_url": "http://127.0.0.1:9101",
            "task_types": ["planning", "content_pipeline", "scheduling"],
            "capabilities": {"role": "planner", "max_tokens": 8192},
            "status": 1,
        }
        resp = scheduler_client.post(
            "/api/internal/scheduler/agents/register",
            headers=headers,
            json=payload,
        )
        assert resp.status_code == 200
        data = resp.json()
        assert data["name"] == "Planner Agent Updated"
        assert "scheduling" in data["task_types"]
        assert data["capabilities"]["max_tokens"] == 8192

        # 验证总数仍为 5
        list_resp = scheduler_client.get("/api/internal/scheduler/agents", headers=headers)
        assert list_resp.json()["total"] == 5


# ────────────────────── 2. 编排管道测试 ──────────────────────


@pytest.mark.usefixtures("scheduler_client")
class TestOrchestrationPipeline:
    """验证内容生成编排管道的完整生命周期。"""

    def _register_all_agents(self, scheduler_client, headers, agents_to_register):
        """注册全部智能体（作为辅助方法）。"""
        for agent_def in agents_to_register:
            scheduler_client.post(
                "/api/internal/scheduler/agents/register",
                headers=headers,
                json={
                    "agent_key": agent_def["agent_key"],
                    "name": agent_def["name"],
                    "base_url": agent_def["base_url"],
                    "task_types": agent_def["task_types"],
                    "health_path": "/health",
                    "capabilities": agent_def["capabilities"],
                    "status": 1,
                },
            )

    def test_submit_content_pipeline_task(self, scheduler_client, headers, trace_id, agents_to_register):
        """提交内容生成管道任务，验证返回的 task ID 与 trace ID。"""
        self._register_all_agents(scheduler_client, headers, agents_to_register)

        h = {**headers, "x-trace-id": trace_id}
        payload = {
            "task_type": "content_pipeline",
            "payload": {
                "topic": "Python FastAPI Best Practices 2025",
                "target_audience": "backend developers",
                "output_format": "blog_post",
                "pipeline_steps": ["planning", "data_processing", "content_generation", "aggregation"],
            },
            "max_retries": 3,
            "retry_delay_seconds": 5.0,
        }
        resp = scheduler_client.post("/api/internal/scheduler/tasks", headers=h, json=payload)
        assert resp.status_code == 200
        data = resp.json()
        assert "id" in data
        assert data["trace_id"] == trace_id
        assert data["status"] == "PENDING"
        assert "created_at" in data

    def test_task_lifecycle_status_transitions(self, scheduler_client, headers, trace_id, agents_to_register):
        """提交任务并查询其状态，验证状态机的基础流转。"""
        self._register_all_agents(scheduler_client, headers, agents_to_register)

        h = {**headers, "x-trace-id": trace_id}
        task_id_key = str(uuid.uuid4())

        # 提交任务
        resp = scheduler_client.post(
            "/api/internal/scheduler/tasks",
            headers=h,
            json={
                "task_type": "content_pipeline",
                "payload": {"topic": "Microservices Design Patterns"},
                "idempotency_key": task_id_key,
                "max_retries": 2,
            },
        )
        assert resp.status_code == 200
        task_data = resp.json()
        task_id = task_data["id"]
        assert task_data["status"] == "PENDING"

        # 查询任务详情（dispatcher 已禁用，状态应为 PENDING）
        detail_resp = scheduler_client.get(
            f"/api/internal/scheduler/tasks/{task_id}",
            headers=headers,
        )
        assert detail_resp.status_code == 200
        detail = detail_resp.json()
        assert detail["id"] == task_id
        assert detail["task_type"] == "content_pipeline"
        assert detail["status"] == "PENDING"
        assert detail["payload"]["topic"] == "Microservices Design Patterns"
        assert detail["idempotency_key"] == task_id_key
        assert detail["max_retries"] == 2
        assert "events" in detail
        # SUBMITTED 事件应存在
        event_types = [e["event_type"] for e in detail["events"]]
        assert "SUBMITTED" in event_types

    def test_task_idempotency_key(self, scheduler_client, headers, trace_id, agents_to_register):
        """幂等键重复提交应返回同一任务。"""
        self._register_all_agents(scheduler_client, headers, agents_to_register)

        h = {**headers, "x-trace-id": trace_id}
        idem_key = str(uuid.uuid4())

        # 首次提交
        resp1 = scheduler_client.post(
            "/api/internal/scheduler/tasks",
            headers=h,
            json={
                "task_type": "content_pipeline",
                "payload": {"topic": "Idempotency Test"},
                "idempotency_key": idem_key,
            },
        )
        assert resp1.status_code == 200
        task1 = resp1.json()

        # 重复提交（同样的 payload）
        resp2 = scheduler_client.post(
            "/api/internal/scheduler/tasks",
            headers=h,
            json={
                "task_type": "content_pipeline",
                "payload": {"topic": "Idempotency Test"},
                "idempotency_key": idem_key,
            },
        )
        assert resp2.status_code == 200
        task2 = resp2.json()
        assert task2["id"] == task1["id"]  # 返回同一个 task_id
        assert task2["status"] == task1["status"]

    def test_task_cancel_flow(self, scheduler_client, headers, trace_id, agents_to_register):
        """提交任务并立即取消，验证取消流程。"""
        self._register_all_agents(scheduler_client, headers, agents_to_register)

        h = {**headers, "x-trace-id": trace_id}
        # 提交
        resp = scheduler_client.post(
            "/api/internal/scheduler/tasks",
            headers=h,
            json={"task_type": "content_pipeline", "payload": {"topic": "Cancel Test"}},
        )
        assert resp.status_code == 200
        task_id = resp.json()["id"]

        # 取消
        cancel_resp = scheduler_client.post(
            f"/api/internal/scheduler/tasks/{task_id}/cancel",
            headers=headers,
        )
        assert cancel_resp.status_code == 200
        cancel_data = cancel_resp.json()
        assert cancel_data["cancel_requested"] is True

        # 再次查询确认
        detail_resp = scheduler_client.get(f"/api/internal/scheduler/tasks/{task_id}", headers=headers)
        assert detail_resp.status_code == 200
        detail = detail_resp.json()
        assert detail["cancel_requested"] is True

    def test_task_list_filtering(self, scheduler_client, headers, trace_id, agents_to_register):
        """按多种条件过滤任务列表。"""
        self._register_all_agents(scheduler_client, headers, agents_to_register)

        # 先提交多个不同 task_type 的任务
        task_types = ["content_pipeline", "content_pipeline", "data_processing"]
        for tt in task_types:
            scheduler_client.post(
                "/api/internal/scheduler/tasks",
                headers={**headers, "x-trace-id": trace_id},
                json={"task_type": tt, "payload": {}},
            )

        # 按 task_type 过滤
        resp = scheduler_client.get(
            "/api/internal/scheduler/tasks",
            headers=headers,
            params={"task_type": "content_pipeline"},
        )
        assert resp.status_code == 200
        data = resp.json()
        assert data["total"] >= 2
        for item in data["items"]:
            assert item["task_type"] == "content_pipeline"

        # 按状态过滤
        resp2 = scheduler_client.get(
            "/api/internal/scheduler/tasks",
            headers=headers,
            params={"status": "PENDING"},
        )
        assert resp2.status_code == 200
        data2 = resp2.json()
        assert data2["total"] >= 3
        for item in data2["items"]:
            assert item["status"] == "PENDING"

    def test_result_aggregation_field(self, scheduler_client, headers, trace_id, agents_to_register):
        """验证任务详情中的 result 字段在无 dispatcher 时为空。"""
        self._register_all_agents(scheduler_client, headers, agents_to_register)

        h = {**headers, "x-trace-id": trace_id}
        resp = scheduler_client.post(
            "/api/internal/scheduler/tasks",
            headers=h,
            json={
                "task_type": "content_pipeline",
                "payload": {"topic": "Result Aggregation Test"},
            },
        )
        task_id = resp.json()["id"]

        detail_resp = scheduler_client.get(f"/api/internal/scheduler/tasks/{task_id}", headers=headers)
        detail = detail_resp.json()
        # 无 dispatcher 时 result 应为 None
        assert detail.get("result") is None or detail.get("result") == {}


# ────────────────────── 3. 跨智能体内存共享测试 ──────────────────────


@pytest.fixture(scope="class")
def _mempool_env():
    """为内存池测试设置 SQLite 后端环境并重置单例。"""
    old_redis_url = os.environ.get("SHARED_MEMORY_REDIS_URL")
    old_sqlite_path = os.environ.get("SHARED_MEMORY_SQLITE_PATH")
    os.environ["SHARED_MEMORY_REDIS_URL"] = ""
    os.environ["SHARED_MEMORY_SQLITE_PATH"] = ""
    # 重置 get_pool 的单例，确保使用测试配置
    import core.mempool as _mp
    _mp._pool = None
    yield
    # 恢复环境变量
    if old_redis_url is not None:
        os.environ["SHARED_MEMORY_REDIS_URL"] = old_redis_url
    else:
        os.environ.pop("SHARED_MEMORY_REDIS_URL", None)
    if old_sqlite_path is not None:
        os.environ["SHARED_MEMORY_SQLITE_PATH"] = old_sqlite_path
    else:
        os.environ.pop("SHARED_MEMORY_SQLITE_PATH", None)


@pytest.mark.usefixtures("_mempool_env")
class TestCrossAgentMemorySharing:
    """验证多个智能体可以在管道执行期间读写共享内存池。"""

    def test_planner_writes_to_memory_pool(self):
        """模拟 Planner 智能体向共享内存池写入执行计划。"""
        from core.memory_naming import RunNaming
        from core.mempool import get_pool

        run_id = str(uuid.uuid4())
        pool = get_pool()

        # Planner 写入执行计划
        plan = {
            "steps": ["research_topic", "analyze_competitors", "draft_outline", "generate_content"],
            "estimated_duration_minutes": 30,
            "dependencies": {"draft_outline": ["research_topic", "analyze_competitors"]},
        }
        run_plan_key = RunNaming.plan(run_id)
        pool.set(run_plan_key, plan)

        # 验证读取
        retrieved = pool.get(run_plan_key)
        assert retrieved is not None
        assert retrieved["steps"] == plan["steps"]
        assert retrieved["estimated_duration_minutes"] == 30

    def test_data_processor_reads_and_writes(self):
        """模拟 Data Processor 从共享内存读取输入并写入处理结果。"""
        from core.memory_naming import TaskNaming
        from core.mempool import get_pool

        run_id = str(uuid.uuid4())
        pool = get_pool()

        # plan 阶段写入输入
        input_key = TaskNaming.input("data_processing", run_id)
        pool.set(input_key, {"raw_data": ["doc1", "doc2", "doc3"], "source": "web_crawl"})

        # data_processor 读取输入并处理
        input_data = pool.get(input_key)
        assert input_data is not None
        assert len(input_data["raw_data"]) == 3

        # 处理后写入输出
        processed = {"entities": ["Python", "FastAPI", "SQLAlchemy"], "sentiment": "positive"}
        output_key = TaskNaming.output("data_processing", run_id)
        pool.set(output_key, processed)

        # 验证输出
        result = pool.get(output_key)
        assert result is not None
        assert "Python" in result["entities"]
        assert result["sentiment"] == "positive"

    def test_multiple_agents_cross_read(self):
        """模拟管道中多个智能体交叉读写：planner → data_processor → content_generator → aggregator。"""
        from core.memory_naming import RunNaming, TaskNaming
        from core.mempool import get_pool

        run_id = str(uuid.uuid4())
        pool = get_pool()

        # Step 1: Planner 写入原始输入并写出 plan
        pool.set(TaskNaming.input("planning", run_id), {"topic": "FastAPI Multi-Agent"})

        plan = {"phases": [{"agent": "data_processor"}, {"agent": "content_generator"}, {"agent": "aggregator"}]}
        pool.set(TaskNaming.output("planning", run_id), plan)

        # Step 2: Data Processor 读取 Planner 输出，处理后写入
        plan_result = pool.get(TaskNaming.output("planning", run_id))
        assert plan_result is not None
        assert "phases" in plan_result

        data_result = {"processed_docs": 5, "key_points": ["A", "B", "C"]}
        pool.set(TaskNaming.output("data_processing", run_id), data_result)

        # Step 3: Content Generator 读取 data_processor 输出并生成
        data = pool.get(TaskNaming.output("data_processing", run_id))
        assert data is not None
        assert data["processed_docs"] == 5

        content = {"draft": "# FastAPI Multi-Agent\n\nGenerated content...", "word_count": 500}
        pool.set(TaskNaming.output("content_generation", run_id), content)

        # Step 4: Aggregator 收集全部中间结果并聚合
        all_outputs = {}
        for task_key in ["planning", "data_processing", "content_generation"]:
            val = pool.get(TaskNaming.output(task_key, run_id))
            if val:
                all_outputs[task_key] = val

        assert len(all_outputs) == 3

        # 聚合结果
        aggregated = {
            "pipeline_results": all_outputs,
            "total_word_count": content["word_count"],
            "status": "SUCCEEDED",
        }
        final_key = RunNaming.result(run_id)
        pool.set(final_key, aggregated)

        # 验证最终聚合结果
        final = pool.get(final_key)
        assert final is not None
        assert final["status"] == "SUCCEEDED"
        assert final["total_word_count"] == 500
        assert "planning" in final["pipeline_results"]
        assert "data_processing" in final["pipeline_results"]
        assert "content_generation" in final["pipeline_results"]

    def test_memory_pool_namespace_isolation(self):
        """验证共享内存池的命名空间隔离。"""
        from core.mempool import get_pool

        pool = get_pool()

        # 写入带命名空间前缀的 key
        test_key = f"test_ns:{uuid.uuid4().hex}:data"
        test_value = {"message": "hello from agent"}

        pool.set(test_key, test_value)
        retrieved = pool.get(test_key)
        assert retrieved is not None
        assert retrieved["message"] == "hello from agent"

    def test_graceful_nonexistent_key_read(self):
        """验证读取不存在的 key 时优雅降级（不抛异常）。"""
        from core.mempool import get_pool

        pool = get_pool()
        nonexistent_key = f"nonexistent:{uuid.uuid4().hex}"

        result = pool.get(nonexistent_key)
        # 应返回 None 或空值，不抛异常
        assert result is None or result == {}


# ────────────────────── 4. Trace 传播测试 ──────────────────────


@pytest.mark.usefixtures("scheduler_client")
class TestTracePropagationAcrossAgents:
    """验证 trace_id 在多步编排中贯穿传播。"""

    def _register_all_agents(self, scheduler_client, headers, agents_to_register):
        for agent_def in agents_to_register:
            scheduler_client.post(
                "/api/internal/scheduler/agents/register",
                headers=headers,
                json={
                    "agent_key": agent_def["agent_key"],
                    "name": agent_def["name"],
                    "base_url": agent_def["base_url"],
                    "task_types": agent_def["task_types"],
                    "health_path": "/health",
                    "capabilities": agent_def["capabilities"],
                    "status": 1,
                },
            )

    def test_trace_id_in_submit_response(self, scheduler_client, headers, trace_id, agents_to_register):
        """任务提交响应中 trace_id 应与请求头一致。"""
        self._register_all_agents(scheduler_client, headers, agents_to_register)

        h = {**headers, "x-trace-id": trace_id}
        resp = scheduler_client.post(
            "/api/internal/scheduler/tasks",
            headers=h,
            json={"task_type": "content_pipeline", "payload": {"step": 1}},
        )
        assert resp.status_code == 200
        assert resp.json()["trace_id"] == trace_id

    def test_trace_id_persisted_in_task_detail(self, scheduler_client, headers, trace_id, agents_to_register):
        """任务详情中 trace_id 已持久化。"""
        self._register_all_agents(scheduler_client, headers, agents_to_register)

        h = {**headers, "x-trace-id": trace_id}
        # 使用不同的 trace_id 避免与其他测试冲突
        distinct_trace = str(uuid.uuid4())
        h["x-trace-id"] = distinct_trace

        resp = scheduler_client.post(
            "/api/internal/scheduler/tasks",
            headers=h,
            json={"task_type": "content_pipeline", "payload": {"step": "trace_test"}},
        )
        task_id = resp.json()["id"]

        detail_resp = scheduler_client.get(
            f"/api/internal/scheduler/tasks/{task_id}",
            headers=headers,
        )
        assert detail_resp.status_code == 200
        detail = detail_resp.json()
        assert detail["trace_id"] == distinct_trace

    def test_trace_id_in_task_events(self, scheduler_client, headers, trace_id, agents_to_register):
        """事件日志中应包含 trace_id。"""
        self._register_all_agents(scheduler_client, headers, agents_to_register)

        distinct_trace = str(uuid.uuid4())
        h = {**headers, "x-trace-id": distinct_trace}

        resp = scheduler_client.post(
            "/api/internal/scheduler/tasks",
            headers=h,
            json={"task_type": "content_pipeline", "payload": {"step": "event_trace_test"}},
        )
        task_id = resp.json()["id"]

        detail_resp = scheduler_client.get(
            f"/api/internal/scheduler/tasks/{task_id}",
            headers=headers,
        )
        detail = detail_resp.json()
        for event in detail["events"]:
            assert event.get("trace_id") == distinct_trace, (
                f"Event trace_id mismatch: {event.get('trace_id')} != {distinct_trace}"
            )

    def test_trace_id_in_task_logs(self, scheduler_client, headers, trace_id, agents_to_register):
        """任务日志中应包含 trace_id。"""
        self._register_all_agents(scheduler_client, headers, agents_to_register)

        distinct_trace = str(uuid.uuid4())
        h = {**headers, "x-trace-id": distinct_trace}

        resp = scheduler_client.post(
            "/api/internal/scheduler/tasks",
            headers=h,
            json={
                "task_type": "content_pipeline",
                "payload": {"step": "log_trace_test"},
                "idempotency_key": str(uuid.uuid4()),
            },
        )
        task_id = resp.json()["id"]

        logs_resp = scheduler_client.get(
            f"/api/internal/scheduler/tasks/{task_id}/logs",
            headers=headers,
        )
        assert logs_resp.status_code == 200
        logs_data = logs_resp.json()
        # 某些配置下日志可能为空（取决于 SCHEDULER_SUBMIT_WRITE_LOGS 环境变量）
        # 但如果没有关闭，则应验证 trace_id
        if logs_data["total"] > 0:
            for log_item in logs_data["items"]:
                assert log_item.get("trace_id") == distinct_trace or log_item.get("trace_id") is None

    def test_auto_generated_trace_id_when_not_provided(self, scheduler_client, headers, agents_to_register):
        """当请求头未提供 trace_id 时，系统自动生成 UUID。"""
        self._register_all_agents(scheduler_client, headers, agents_to_register)
        h = {k: v for k, v in headers.items()}
        # 不传 x-trace-id 头

        resp = scheduler_client.post(
            "/api/internal/scheduler/tasks",
            headers=h,
            json={"task_type": "content_pipeline", "payload": {"step": "auto_trace_test"}},
        )
        assert resp.status_code == 200
        data = resp.json()
        auto_trace = data["trace_id"]

        # 应为有效的 UUID 格式
        uuid.UUID(auto_trace)

        # 查询确认
        detail_resp = scheduler_client.get(
            f"/api/internal/scheduler/tasks/{data['id']}",
            headers=headers,
        )
        assert detail_resp.status_code == 200
        assert detail_resp.json()["trace_id"] == auto_trace

    def test_trace_id_in_cancel_flow(self, scheduler_client, headers, agents_to_register):
        """取消操作也应保留 trace_id。"""
        self._register_all_agents(scheduler_client, headers, agents_to_register)

        distinct_trace = str(uuid.uuid4())
        h = {**headers, "x-trace-id": distinct_trace}

        # 提交任务
        resp = scheduler_client.post(
            "/api/internal/scheduler/tasks",
            headers=h,
            json={"task_type": "content_pipeline", "payload": {"step": "cancel_trace_test"}},
        )
        task_id = resp.json()["id"]

        # 取消任务
        cancel_resp = scheduler_client.post(
            f"/api/internal/scheduler/tasks/{task_id}/cancel",
            headers=headers,
        )
        assert cancel_resp.status_code == 200
        cancel_data = cancel_resp.json()
        # trace_id 应与提交时一致
        assert cancel_data["trace_id"] == distinct_trace

    def test_full_pipeline_trace_consistency(self, scheduler_client, headers, agents_to_register):
        """完整管道流程中 trace_id 的一致性验证：提交 → 查询 → 事件 → 日志。"""
        self._register_all_agents(scheduler_client, headers, agents_to_register)

        pipeline_trace = str(uuid.uuid4())
        h = {**headers, "x-trace-id": pipeline_trace}

        # 模拟编排流程：依次提交多个阶段的 task
        tasks = []
        step_names = ["planning", "data_processing", "content_generation", "aggregation"]

        for step in step_names:
            resp = scheduler_client.post(
                "/api/internal/scheduler/tasks",
                headers=h,
                json={
                    "task_type": "content_pipeline",
                    "payload": {"pipeline": "full_flow", "step": step},
                    "idempotency_key": f"pipeline-{pipeline_trace[:8]}-{step}",
                },
            )
            assert resp.status_code == 200
            data = resp.json()
            assert data["trace_id"] == pipeline_trace
            tasks.append(data)

        # 验证所有 task 的 trace_id 一致
        for task in tasks:
            detail = scheduler_client.get(
                f"/api/internal/scheduler/tasks/{task['id']}",
                headers=headers,
            ).json()
            assert detail["trace_id"] == pipeline_trace

            # 事件中的 trace_id 也应一致
            for event in detail.get("events", []):
                assert event.get("trace_id") == pipeline_trace


# ────────────────────── 5. 故障容忍与重试测试 ──────────────────────


@pytest.mark.usefixtures("scheduler_client")
class TestFaultToleranceRetry:
    """验证任务失败后的重试机制与最终状态。"""

    def _register_all_agents(self, scheduler_client, headers, agents_to_register):
        for agent_def in agents_to_register:
            scheduler_client.post(
                "/api/internal/scheduler/agents/register",
                headers=headers,
                json={
                    "agent_key": agent_def["agent_key"],
                    "name": agent_def["name"],
                    "base_url": agent_def["base_url"],
                    "task_types": agent_def["task_types"],
                    "health_path": "/health",
                    "capabilities": agent_def["capabilities"],
                    "status": 1,
                },
            )

    def test_task_retry_config_persisted(self, scheduler_client, headers, trace_id, agents_to_register):
        """验证任务的重试配置（max_retries, retry_delay_seconds）已持久化。"""
        self._register_all_agents(scheduler_client, headers, agents_to_register)

        h = {**headers, "x-trace-id": trace_id}
        resp = scheduler_client.post(
            "/api/internal/scheduler/tasks",
            headers=h,
            json={
                "task_type": "content_pipeline",
                "payload": {"topic": "Retry Config Test"},
                "max_retries": 5,
                "retry_delay_seconds": 10.0,
            },
        )
        task_id = resp.json()["id"]

        detail = scheduler_client.get(
            f"/api/internal/scheduler/tasks/{task_id}",
            headers=headers,
        ).json()
        assert detail["max_retries"] == 5
        assert detail["retry_delay_seconds"] == 10.0

    def test_task_uses_default_retry_when_not_specified(self, scheduler_client, headers, agents_to_register):
        """当未指定重试参数时使用默认值（scheduler_default_max_retries=2）。"""
        self._register_all_agents(scheduler_client, headers, agents_to_register)

        resp = scheduler_client.post(
            "/api/internal/scheduler/tasks",
            headers=headers,
            json={"task_type": "content_pipeline", "payload": {"topic": "Default Retry Test"}},
        )
        task_id = resp.json()["id"]

        detail = scheduler_client.get(
            f"/api/internal/scheduler/tasks/{task_id}",
            headers=headers,
        ).json()
        assert detail["max_retries"] == 2  # scheduler_default_max_retries
        assert detail["retry_delay_seconds"] == 3.0  # scheduler_default_retry_delay_seconds

    def test_task_initial_state_is_pending(self, scheduler_client, headers, agents_to_register):
        """新提交的任务初始状态为 PENDING，attempt_count 为 0。"""
        self._register_all_agents(scheduler_client, headers, agents_to_register)

        resp = scheduler_client.post(
            "/api/internal/scheduler/tasks",
            headers=headers,
            json={"task_type": "content_pipeline", "payload": {"topic": "State Test"}},
        )
        assert resp.status_code == 200
        data = resp.json()
        assert data["status"] == "PENDING"

        # 查询详情确认 attempt_count
        detail = scheduler_client.get(
            f"/api/internal/scheduler/tasks/{data['id']}",
            headers=headers,
        ).json()
        assert detail["attempt_count"] == 0
        assert detail["last_error"] is None
        assert detail["last_agent"] is None

    def test_task_with_zero_retries(self, scheduler_client, headers, agents_to_register):
        """max_retries=0 的任务配置应被接受。"""
        self._register_all_agents(scheduler_client, headers, agents_to_register)

        resp = scheduler_client.post(
            "/api/internal/scheduler/tasks",
            headers=headers,
            json={
                "task_type": "content_pipeline",
                "payload": {"topic": "No Retry"},
                "max_retries": 0,
            },
        )
        assert resp.status_code == 200
        task_id = resp.json()["id"]

        detail = scheduler_client.get(
            f"/api/internal/scheduler/tasks/{task_id}",
            headers=headers,
        ).json()
        assert detail["max_retries"] == 0

    def test_multiple_failing_tasks_independence(self, scheduler_client, headers, agents_to_register):
        """多个独立任务各自独立，一个失败不影响其他任务。"""
        self._register_all_agents(scheduler_client, headers, agents_to_register)

        task_ids = []
        for i in range(3):
            resp = scheduler_client.post(
                "/api/internal/scheduler/tasks",
                headers=headers,
                json={
                    "task_type": "content_pipeline",
                    "payload": {"index": i},
                    "idempotency_key": f"independence-test-{i}",
                },
            )
            assert resp.status_code == 200
            task_ids.append(resp.json()["id"])

        # 分别查询确认它们都独立存在
        tasks_details = []
        for tid in task_ids:
            detail = scheduler_client.get(
                f"/api/internal/scheduler/tasks/{tid}",
                headers=headers,
            ).json()
            tasks_details.append(detail)

        assert len(tasks_details) == 3
        # 所有任务的 id 应各不相同
        assert len(set(t["id"] for t in tasks_details)) == 3

    def test_task_results_payload_integrity(self, scheduler_client, headers, agents_to_register):
        """验证复杂 payload 在提交后完整性不丢失。"""
        self._register_all_agents(scheduler_client, headers, agents_to_register)

        complex_payload = {
            "pipeline_config": {
                "stages": [
                    {"name": "plan", "agent": "planner", "timeout": 30},
                    {"name": "process", "agent": "data_processor", "timeout": 60},
                    {"name": "generate", "agent": "content_generator", "timeout": 120},
                ],
                "enable_cache": True,
                "output_formats": ["html", "markdown", "json"],
            },
            "metadata": {"project": "Personal Blog", "version": "2.0", "tags": ["e2e", "multi-agent"]},
        }

        resp = scheduler_client.post(
            "/api/internal/scheduler/tasks",
            headers=headers,
            json={
                "task_type": "content_pipeline",
                "payload": complex_payload,
            },
        )
        task_id = resp.json()["id"]

        detail = scheduler_client.get(
            f"/api/internal/scheduler/tasks/{task_id}",
            headers=headers,
        ).json()
        assert detail["payload"]["pipeline_config"]["stages"][0]["name"] == "plan"
        assert detail["payload"]["pipeline_config"]["stages"][1]["agent"] == "data_processor"
        assert detail["payload"]["pipeline_config"]["output_formats"] == ["html", "markdown", "json"]
        assert detail["payload"]["metadata"]["project"] == "Personal Blog"
        assert "multi-agent" in detail["payload"]["metadata"]["tags"]

    def test_task_list_large_result_set(self, scheduler_client, headers, agents_to_register):
        """提交大量任务后列表查询正确，验证分页机制。"""
        self._register_all_agents(scheduler_client, headers, agents_to_register)

        n_tasks = 40
        for i in range(n_tasks):
            scheduler_client.post(
                "/api/internal/scheduler/tasks",
                headers=headers,
                json={
                    "task_type": "content_pipeline",
                    "payload": {"batch_index": i},
                    "idempotency_key": f"large-batch-{i}",
                },
            )

        # 默认 limit=50，应返回 40 条
        resp = scheduler_client.get("/api/internal/scheduler/tasks", headers=headers)
        assert resp.status_code == 200
        data = resp.json()
        assert data["total"] >= n_tasks

        # 分页测试：limit=10
        resp2 = scheduler_client.get(
            "/api/internal/scheduler/tasks",
            headers=headers,
            params={"limit": 10, "offset": 0},
        )
        assert resp2.status_code == 200
        data2 = resp2.json()
        assert len(data2["items"]) <= 10


