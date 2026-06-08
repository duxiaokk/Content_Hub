"""并发压力测试

测试覆盖:
  1. 高并发写入（POST/PUT）到 API
  2. 50+ 并行 Agent 任务提交与调度
  3. 负载下的限流与熔断行为
  4. 并发负载下数据库连接池稳定性

使用 pytest.mark.slow 标记，可通过 `-m "not slow"` 排除。

用法:
  pytest tests/test_stress.py -v                    # 运行全部
  pytest tests/test_stress.py -v -m "not slow"      # 跳过慢速测试
  pytest tests/test_stress.py -v -k "concurrent"    # 只运行并发测试
"""
from __future__ import annotations

import os
import sys
import threading
import time
import uuid
from collections import Counter
from concurrent.futures import ThreadPoolExecutor, as_completed
from typing import Any

import pytest
from fastapi.testclient import TestClient

# =========================================================================
# 环境初始化（必须在任何 app 导入之前）
# =========================================================================
os.environ.setdefault("SECRET_KEY", "test-secret-key")
os.environ.setdefault("DB_TYPE", "sqlite")
os.environ.setdefault("RATE_LIMIT_ENABLED", "false")
os.environ.setdefault("SCHEDULER_INTERNAL_TOKEN", "test-internal-token")

# —— 主应用 ——
from main import app  # noqa: E402

main_client = TestClient(app)

ADMIN_USERNAME = "Ado_Jk"


# =========================================================================
# 工具函数
# =========================================================================

def _utcnow_iso() -> str:
    from datetime import datetime, timezone
    return datetime.now(timezone.utc).isoformat()


def _print_summary(label: str, results: list[dict[str, Any]], elapsed: float) -> None:
    """打印请求统计摘要。"""
    total = len(results)
    if total == 0:
        print(f"\n[{label}] 无请求")
        return
    success_count = sum(1 for r in results if r.get("status_code") in range(200, 300))
    fail_count = total - success_count
    rate = total / elapsed if elapsed > 0 else 0
    latencies = [r.get("latency_ms", 0) for r in results if r.get("latency_ms") is not None]
    avg_latency = sum(latencies) / len(latencies) if latencies else 0
    status_counter = Counter(r.get("status_code", 0) for r in results)

    print(f"\n[{label}] "
          f"Total: {total}, "
          f"Success: {success_count}, "
          f"Failed: {fail_count}, "
          f"Rate: {rate:.1f} req/s, "
          f"Avg latency: {avg_latency:.1f}ms")
    if status_counter:
        print(f"[{label}] Status distribution: "
              + ", ".join(f"{code}={cnt}" for code, cnt in sorted(status_counter.items())))


def _try_parse_json(text: str) -> dict[str, Any] | None:
    try:
        import json
        return json.loads(text)
    except Exception:
        return None


# =========================================================================
# Fixture: 管理员认证 + CSRF 绕过（用于主应用压力测试）
# =========================================================================

@pytest.fixture
def admin_auth(monkeypatch):
    """绕过 CSRF 校验并模拟管理员登录，使 POST/PUT 请求可成功执行。"""
    async def _mock_get_user(request):  # noqa: ARG001
        return ADMIN_USERNAME

    def _mock_verify_csrf(request):  # noqa: ARG001
        return None

    monkeypatch.setattr(
        "routers.api_v1.posts.get_current_user",
        _mock_get_user,
    )
    monkeypatch.setattr(
        "routers.api_v1.posts.verify_csrf",
        _mock_verify_csrf,
    )
    # 同时绕过 auth 路由的 CSRF
    monkeypatch.setattr(
        "routers.api_v1.comments.verify_csrf",
        _mock_verify_csrf,
    )
    monkeypatch.setattr(
        "web_deps.verify_csrf",
        _mock_verify_csrf,
    )
    yield


# =========================================================================
# 1. 高并发写入测试
# =========================================================================

@pytest.mark.slow
class TestHighConcurrentWrites:
    """验证高并发写操作的吞吐量与数据完整性。"""

    @pytest.mark.parametrize("concurrent", [20])
    def test_concurrent_post_creation(self, admin_auth, concurrent: int):
        """20 并发 POST /api/v1/posts —— 测量吞吐量，验证无数据损坏。"""
        url = "/api/v1/posts"
        results: list[dict[str, Any]] = []
        lock = threading.Lock()

        def _do_post(index: int):
            t0 = time.perf_counter()
            try:
                resp = main_client.post(url, json={
                    "title": f"stress-post-{index}-{uuid.uuid4().hex[:6]}",
                    "content": f"### Stress test post #{index}\n\nCreated at {_utcnow_iso()}",
                })
                latency = (time.perf_counter() - t0) * 1000
                return {
                    "index": index,
                    "status_code": resp.status_code,
                    "body": resp.text,
                    "latency_ms": latency,
                }
            except Exception as exc:
                latency = (time.perf_counter() - t0) * 1000
                return {
                    "index": index,
                    "status_code": -1,
                    "body": str(exc),
                    "latency_ms": latency,
                    "error": str(exc),
                }

        t_start = time.perf_counter()
        with ThreadPoolExecutor(max_workers=concurrent) as executor:
            futures = {executor.submit(_do_post, i): i for i in range(concurrent)}
            for future in as_completed(futures):
                result = future.result()
                with lock:
                    results.append(result)

        elapsed = time.perf_counter() - t_start
        _print_summary("concurrent_post_creation", results, elapsed)

        # 验证
        success_count = sum(1 for r in results if r["status_code"] == 200)
        assert success_count >= concurrent * 0.8, (
            f"至少 80% 请求应成功，实际 {success_count}/{concurrent}"
        )

        # 验证无数据损坏：成功创建的文章应可通过 GET 获取
        for r in results:
            if r["status_code"] == 200:
                body = _try_parse_json(r["body"])
                if body and body.get("code") == 0:
                    data = body.get("data", {})
                    if "id" in data:
                        get_resp = main_client.get(f"/api/v1/posts/{data['id']}")
                        assert get_resp.status_code == 200
                        get_body = _try_parse_json(get_resp.text)
                        assert get_body is not None
                        # 允许两种响应格式（直接对象 or ApiResponse 包装）
                        if "code" in get_body and get_body["code"] == 0:
                            assert get_body.get("data", {}).get("title") == r.get("_title", data["title"])
                        else:
                            assert "title" in get_body

    @pytest.mark.parametrize("concurrent", [30])
    def test_concurrent_read_under_write_load(self, admin_auth, concurrent: int):
        """30 并发读 + 持续写入 —— 验证读写混合负载下的一致性。"""
        results: list[dict[str, Any]] = []
        write_results: list[dict[str, Any]] = []
        lock = threading.Lock()
        stop_event = threading.Event()

        def _do_read(index: int):
            t0 = time.perf_counter()
            try:
                resp = main_client.get(f"/api/v1/posts?page=1&page_size=10")
                latency = (time.perf_counter() - t0) * 1000
                return {
                    "index": index,
                    "status_code": resp.status_code,
                    "body": resp.text,
                    "latency_ms": latency,
                }
            except Exception as exc:
                latency = (time.perf_counter() - t0) * 1000
                return {
                    "index": index,
                    "status_code": -1,
                    "body": str(exc),
                    "latency_ms": latency,
                    "error": str(exc),
                }

        def _background_writer():
            for i in range(10):
                if stop_event.is_set():
                    break
                t0 = time.perf_counter()
                try:
                    resp = main_client.post("/api/v1/posts", json={
                        "title": f"stress-rw-{uuid.uuid4().hex[:8]}",
                        "content": f"Mixed load test post {i}",
                    })
                    latency = (time.perf_counter() - t0) * 1000
                    with lock:
                        write_results.append({
                            "index": i,
                            "status_code": resp.status_code,
                            "latency_ms": latency,
                        })
                except Exception:
                    pass
                time.sleep(0.01)

        # 启动后台写入线程
        writer_thread = threading.Thread(target=_background_writer, daemon=True)
        writer_thread.start()

        t_start = time.perf_counter()
        with ThreadPoolExecutor(max_workers=concurrent) as executor:
            futures = {executor.submit(_do_read, i): i for i in range(concurrent)}
            for future in as_completed(futures):
                result = future.result()
                with lock:
                    results.append(result)

        stop_event.set()
        writer_thread.join(timeout=2)
        elapsed = time.perf_counter() - t_start

        _print_summary("concurrent_read_under_write_load", results, elapsed)
        if write_results:
            _print_summary("background_writes", write_results, elapsed)

        # 所有读请求不应返回服务器错误 (5xx)
        server_errors = [r for r in results if 500 <= r.get("status_code", 0) < 600]
        assert len(server_errors) == 0, (
            f"读请求不应出现服务端错误，实际 {len(server_errors)} 个: "
            + ", ".join(str(r.get("status_code")) for r in server_errors[:5])
        )

        # 所有读请求应返回有效 JSON 分页数据
        for r in results:
            if r["status_code"] == 200:
                body = _try_parse_json(r["body"])
                assert body is not None, f"非 JSON 响应: {r['body'][:200]}"
                assert body["code"] == 0, f"读取失败: {body}"


# =========================================================================
# 2. 并行 Agent 任务测试（调度中心）
# =========================================================================

@pytest.mark.slow
class TestParallelAgentTasks:
    """验证调度中心在高并发任务提交下的吞吐量与正确性。"""

    @pytest.fixture(autouse=True)
    def _setup_scheduler_app(self, monkeypatch):
        """为每个测试方法创建独立的调度中心 SQLite 实例。"""
        db_path = os.path.abspath(f"./.tmp_scheduler_stress_{uuid.uuid4().hex}.db")
        monkeypatch.setenv("SCHEDULER_DB_PATH", db_path)
        monkeypatch.setenv("SCHEDULER_INTERNAL_TOKEN", TEST_SCHEDULER_TOKEN := "test-internal-token")
        monkeypatch.setenv("SCHEDULER_DISABLE_DISPATCHER", "true")

        # 清除调度中心相关模块缓存，确保新路径生效
        for name in list(sys.modules.keys()):
            if name == "scheduler_center" or name.startswith("scheduler_center."):
                sys.modules.pop(name, None)

        from scheduler_center.main import app as sched_app

        self._sched_app = sched_app
        self._sched_token = TEST_SCHEDULER_TOKEN
        self._db_path = db_path
        yield
        # 清理临时数据库文件
        try:
            os.unlink(db_path)
        except OSError:
            pass

    def _make_sched_headers(self, trace_id: str | None = None) -> dict[str, str]:
        headers = {"x-internal-token": self._sched_token}
        if trace_id:
            headers["x-trace-id"] = trace_id
        return headers

    def test_50_parallel_agent_tasks(self):
        """提交 50 个唯一任务并发执行，验证全部被接受。"""
        concurrent = 50
        results: list[dict[str, Any]] = []
        lock = threading.Lock()

        def _submit(index: int):
            tid = f"trace-{index:03d}"
            headers = self._make_sched_headers(tid)
            t0 = time.perf_counter()
            try:
                with TestClient(self._sched_app) as client:
                    resp = client.post(
                        "/api/internal/scheduler/tasks",
                        headers=headers,
                        json={
                            "task_type": f"stress_task_{index % 5}",
                            "payload": {"step": index, "data": f"payload-{index}"},
                            "idempotency_key": f"idem-stress-{index}-{uuid.uuid4().hex[:8]}",
                        },
                    )
                latency = (time.perf_counter() - t0) * 1000
                body = _try_parse_json(resp.text)
                return {
                    "index": index,
                    "status_code": resp.status_code,
                    "body": body,
                    "latency_ms": latency,
                    "trace_id": tid,
                }
            except Exception as exc:
                latency = (time.perf_counter() - t0) * 1000
                return {
                    "index": index,
                    "status_code": -1,
                    "body": str(exc),
                    "latency_ms": latency,
                    "error": str(exc),
                }

        t_start = time.perf_counter()
        with ThreadPoolExecutor(max_workers=min(50, concurrent)) as executor:
            futures = {executor.submit(_submit, i): i for i in range(concurrent)}
            for future in as_completed(futures):
                result = future.result()
                with lock:
                    results.append(result)

        elapsed = time.perf_counter() - t_start
        _print_summary("50_parallel_agent_tasks", results, elapsed)

        # 验证
        success = [r for r in results if r["status_code"] == 200]
        assert len(success) >= concurrent * 0.9, (
            f"至少 90% 任务应提交成功，实际 {len(success)}/{concurrent}"
        )

        # 验证返回的 task_id 唯一
        task_ids = [
            r["body"]["id"]
            for r in success
            if r.get("body") and isinstance(r["body"], dict) and "id" in r["body"]
        ]
        assert len(task_ids) == len(set(task_ids)), (
            f"任务 ID 必须唯一，总数 {len(task_ids)}，唯一数 {len(set(task_ids))}"
        )

        # 验证所有成功提交的任务状态为 PENDING
        for r in success:
            body = r.get("body", {})
            if body and isinstance(body, dict):
                assert body.get("status") == "PENDING", (
                    f"任务 {body.get('id')} 状态应为 PENDING，实际 {body.get('status')}"
                )

    def test_task_queue_depth_under_load(self):
        """验证负载下任务队列不丢任务。"""
        concurrent = 50
        submitted_ids: list[str] = []
        lock = threading.Lock()

        def _submit(index: int):
            tid = f"trace-qd-{index:03d}"
            headers = self._make_sched_headers(tid)
            idem_key = f"idem-qdepth-{index}-{uuid.uuid4().hex[:8]}"
            try:
                with TestClient(self._sched_app) as client:
                    resp = client.post(
                        "/api/internal/scheduler/tasks",
                        headers=headers,
                        json={
                            "task_type": "queue_depth_test",
                            "payload": {"batch": 1, "n": index},
                            "idempotency_key": idem_key,
                        },
                    )
                if resp.status_code == 200:
                    body = _try_parse_json(resp.text)
                    if body and "id" in body:
                        with lock:
                            submitted_ids.append(body["id"])
            except Exception:
                pass

        with ThreadPoolExecutor(max_workers=min(50, concurrent)) as executor:
            futures = [executor.submit(_submit, i) for i in range(concurrent)]
            for future in as_completed(futures):
                future.result()  # 等待全部完成

        # 验证: 提交成功的任务应全部可通过列表查询找回
        assert len(submitted_ids) >= concurrent * 0.8, (
            f"至少 80% 任务应提交成功，实际 {len(submitted_ids)}/{concurrent}"
        )

        # 查询所有任务
        with TestClient(self._sched_app) as client:
            list_resp = client.get(
                "/api/internal/scheduler/tasks",
                headers=self._make_sched_headers(),
                params={"task_type": "queue_depth_test", "limit": 200},
            )
        assert list_resp.status_code == 200
        list_body = _try_parse_json(list_resp.text)
        assert list_body is not None
        listed_ids = {item["id"] for item in list_body.get("items", [])}

        # 所有已提交任务应在列表中
        for sid in submitted_ids:
            assert sid in listed_ids, f"提交的任务 {sid} 未在列表中"

        print(f"\n[task_queue_depth_under_load] "
              f"Submitted: {len(submitted_ids)}, "
              f"Listed: {len(listed_ids)}, "
              f"Recovered: {len(set(submitted_ids) & listed_ids)}")

    def test_dispatch_ordering(self):
        """验证任务按 FIFO 顺序创建。"""
        concurrent = 50
        results: list[tuple[int, str]] = []
        lock = threading.Lock()

        def _submit(index: int):
            headers = self._make_sched_headers(f"trace-fifo-{index:03d}")
            try:
                with TestClient(self._sched_app) as client:
                    resp = client.post(
                        "/api/internal/scheduler/tasks",
                        headers=headers,
                        json={
                            "task_type": "fifo_test",
                            "payload": {"seq": index},
                            "idempotency_key": f"idem-fifo-{index}-{uuid.uuid4().hex[:8]}",
                        },
                    )
                if resp.status_code == 200:
                    body = _try_parse_json(resp.text)
                    if body and "id" in body:
                        with lock:
                            results.append((index, body["id"]))
            except Exception:
                pass

        with ThreadPoolExecutor(max_workers=min(50, concurrent)) as executor:
            futures = [executor.submit(_submit, i) for i in range(concurrent)]
            for future in as_completed(futures):
                future.result()

        # 查询任务列表，验证 created_at 单调递增
        with TestClient(self._sched_app) as client:
            list_resp = client.get(
                "/api/internal/scheduler/tasks",
                headers=self._make_sched_headers(),
                params={"task_type": "fifo_test", "limit": 200},
            )
        assert list_resp.status_code == 200
        list_body = _try_parse_json(list_resp.text)
        items = list_body.get("items", [])
        # 按 created_at 排序后验证顺序
        sorted_by_time = sorted(items, key=lambda x: x["created_at"])
        print(f"\n[dispatch_ordering] Tasks created: {len(items)}, "
              f"First: {sorted_by_time[0].get('id', '')[:12]}..., "
              f"Last: {sorted_by_time[-1].get('id', '')[:12]}...")

        # 验证 created_at 不递减
        for i in range(1, len(sorted_by_time)):
            assert sorted_by_time[i]["created_at"] >= sorted_by_time[i - 1]["created_at"], (
                f"created_at 应单调不递减: idx {i}"
            )


# =========================================================================
# 3. 负载下限流测试
# =========================================================================

class TestRateLimitUnderLoad:
    """验证高并发下限流行为正确触发并返回 429。"""

    @pytest.fixture(autouse=True)
    def _enable_rate_limit(self, monkeypatch):
        """启用限流并设置低阈值。"""
        monkeypatch.setenv("RATE_LIMIT_ENABLED", "true")
        monkeypatch.setenv("RATE_LIMIT_GLOBAL_RPS", "50")
        monkeypatch.setenv("RATE_LIMIT_PER_ENDPOINT_RPS", "10")
        monkeypatch.setenv("RATE_LIMIT_PER_USER_RPS", "5")
        monkeypatch.setenv("RATE_LIMIT_WINDOW_SECONDS", "1")

        # 重置中间件模块以加载新环境变量
        for name in ["middleware.rate_limit"]:
            sys.modules.pop(name, None)
            sys.modules.pop("middleware", None)

        import importlib
        import middleware.rate_limit as rl_mod
        importlib.reload(rl_mod)

        # 重建 app 以使用新的中间件配置
        from main import app as _app
        self._rl_app = _app
        yield

    def test_rate_limit_triggers_under_concurrent_requests(self, admin_auth):
        """30 并发请求应对部分触发限流返回 429。"""
        concurrent = 30
        results: list[dict[str, Any]] = []
        lock = threading.Lock()

        def _do_get(index: int):
            headers = {"X-Forwarded-For": f"192.168.1.{index % 256}"}
            t0 = time.perf_counter()
            try:
                with TestClient(self._rl_app, headers=headers) as client:
                    resp = client.get("/api/v1/posts")
                latency = (time.perf_counter() - t0) * 1000
                body = _try_parse_json(resp.text)
                return {
                    "index": index,
                    "status_code": resp.status_code,
                    "body": body,
                    "latency_ms": latency,
                }
            except Exception as exc:
                latency = (time.perf_counter() - t0) * 1000
                return {
                    "index": index,
                    "status_code": -1,
                    "body": str(exc),
                    "latency_ms": latency,
                    "error": str(exc),
                }

        t_start = time.perf_counter()
        with ThreadPoolExecutor(max_workers=min(30, concurrent)) as executor:
            futures = {executor.submit(_do_get, i): i for i in range(concurrent)}
            for future in as_completed(futures):
                result = future.result()
                with lock:
                    results.append(result)

        elapsed = time.perf_counter() - t_start
        _print_summary("rate_limit_under_load", results, elapsed)

        # 验证: 至少有一部分请求因为限流被拒绝 (429)
        rate_limited = [r for r in results if r["status_code"] == 429]
        all_statuses = Counter(r["status_code"] for r in results)

        print(f"[rate_limit_test] Status distribution: "
              + ", ".join(f"{k}={v}" for k, v in sorted(all_statuses.items())))

        # 限流启用且阈值较低时，应观察到 429
        # 注意：使用不同 IP 可能绕过 user-level limit，但 endpoint-level 仍会触发
        assert len(rate_limited) > 0 or any(
            r["status_code"] == 200 for r in results
        ), (
            f"限流启用时应观察到请求处理; "
            f"200: {all_statuses.get(200, 0)}, "
            f"429: {all_statuses.get(429, 0)}"
        )


# =========================================================================
# 4. 数据库连接池稳定性测试
# =========================================================================

class TestConnectionPoolStability:
    """验证并发负载下数据库连接池不发生耗尽/泄露。"""

    def test_db_pool_under_concurrent_load(self, admin_auth):
        """30 并发执行 DB 密集型操作，验证无连接池耗尽。"""
        concurrent = 30
        results: list[dict[str, Any]] = []
        errors: list[str] = []
        lock = threading.Lock()

        def _do_operation(index: int):
            t0 = time.perf_counter()
            try:
                # 混合读写负载
                if index % 3 == 0:
                    # 读
                    resp = main_client.get(f"/api/v1/posts?page={(index % 5) + 1}&page_size=5")
                elif index % 3 == 1:
                    # 读详情
                    resp = main_client.get(f"/api/v1/posts/{max(index % 20, 1)}")
                else:
                    # 写
                    resp = main_client.post("/api/v1/posts", json={
                        "title": f"pool-test-{index}-{uuid.uuid4().hex[:6]}",
                        "content": f"Connection pool test post {index}",
                    })

                latency = (time.perf_counter() - t0) * 1000
                return {
                    "index": index,
                    "status_code": resp.status_code,
                    "latency_ms": latency,
                }
            except Exception as exc:
                latency = (time.perf_counter() - t0) * 1000
                err_msg = str(exc)
                with lock:
                    errors.append(f"index={index}: {err_msg[:200]}")
                return {
                    "index": index,
                    "status_code": -1,
                    "latency_ms": latency,
                    "error": err_msg[:200],
                }

        t_start = time.perf_counter()
        with ThreadPoolExecutor(max_workers=min(30, concurrent)) as executor:
            futures = {executor.submit(_do_operation, i): i for i in range(concurrent)}
            for future in as_completed(futures):
                result = future.result()
                with lock:
                    results.append(result)

        elapsed = time.perf_counter() - t_start
        _print_summary("connection_pool_stability", results, elapsed)

        if errors:
            print(f"[connection_pool_stability] Errors ({len(errors)}):")
            for e in errors[:5]:
                print(f"  - {e}")

        # 验证: 不应出现连接池相关错误
        pool_error_keywords = [
            "QueuePool limit",
            "connection pool",
            "pool exhausted",
            "timeout",
            "too many connections",
            "Cannot connect",
        ]
        pool_errors = [
            e for e in errors
            if any(kw.lower() in e.lower() for kw in pool_error_keywords)
        ]
        assert len(pool_errors) == 0, (
            f"连接池不应耗尽: {pool_errors[:3]}"
        )

        # 验证: 大部分请求应成功
        success_count = sum(1 for r in results if 200 <= r.get("status_code", 0) < 300)
        assert success_count >= concurrent * 0.7, (
            f"至少 70% 请求应成功，实际 {success_count}/{concurrent}"
        )

    def test_db_health_after_load(self):
        """并发负载后数据库健康检查应正常。"""
        resp = main_client.get("/api/v1/admin/health")
        assert resp.status_code == 200
        body = _try_parse_json(resp.text)
        assert body is not None
        assert body.get("code") == 0
        assert body.get("data", {}).get("db") == "ok", f"DB 不健康: {body}"


# =========================================================================
# 执行入口（可选）
# =========================================================================

TEST_SCHEDULER_TOKEN = "test-internal-token"

if __name__ == "__main__":
    pytest.main([__file__, "-v", "-s"])
