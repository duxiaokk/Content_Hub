from __future__ import annotations

import os
import uuid

import httpx
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

from scheduler_center.database import Base
from scheduler_center.models import SchedulerAgent, SchedulerTask, SchedulerTaskAttempt, SchedulerTaskEvent


class _FakeResp:
    def __init__(self, status_code: int, text: str = "", json_data=None):
        self.status_code = status_code
        self.text = text
        self._json_data = json_data if json_data is not None else {"ok": False}

    def json(self):
        return self._json_data


def _make_session_local(db_path: str):
    engine = create_engine(
        f"sqlite:///{db_path.replace(os.sep, '/')}",
        connect_args={"check_same_thread": False},
        pool_pre_ping=True,
    )
    SessionLocal = sessionmaker(
        autocommit=False,
        autoflush=False,
        bind=engine,
        expire_on_commit=False,
    )
    Base.metadata.create_all(bind=engine)
    return SessionLocal


def test_dispatcher_retryable_5xx_schedules_retry(monkeypatch):
    import scheduler_center.dispatcher as dispatcher_module

    db_path = os.path.abspath(f"./.tmp_scheduler_dispatcher_test_{uuid.uuid4().hex}.db")
    SessionLocal = _make_session_local(db_path)
    monkeypatch.setattr(dispatcher_module, "SessionLocal", SessionLocal)
    dispatcher_module.scheduler_settings.scheduler_agent_endpoints_raw = "http://agent"

    class FakeClient:
        def __init__(self, *args, **kwargs):
            pass

        def __enter__(self):
            return self

        def __exit__(self, exc_type, exc, tb):
            return False

        def post(self, url, json, headers):
            return _FakeResp(500, text="server error")

    monkeypatch.setattr(dispatcher_module.httpx, "Client", FakeClient)

    db = SessionLocal()
    task = SchedulerTask(
        id=str(uuid.uuid4()),
        idempotency_key=None,
        trace_id="trace-dispatcher-1",
        task_type="demo",
        payload_json='{"a": 1}',
        status=dispatcher_module.TaskStatus.RUNNING,
        cancel_requested=0,
        max_retries=2,
        retry_delay_seconds=0.0,
        attempt_count=0,
        next_run_at=None,
        last_agent=None,
        result_json=None,
        last_error=None,
    )
    db.add(task)
    db.commit()
    db.close()

    d = dispatcher_module.SchedulerDispatcher()
    d._execute_task(task.id)

    db = SessionLocal()
    task2 = db.query(SchedulerTask).filter(SchedulerTask.id == task.id).first()
    assert task2 is not None
    assert task2.status == dispatcher_module.TaskStatus.PENDING
    assert task2.attempt_count == 1
    assert task2.next_run_at is not None

    attempt = (
        db.query(SchedulerTaskAttempt)
        .filter(SchedulerTaskAttempt.task_id == task.id)
        .order_by(SchedulerTaskAttempt.attempt_no.asc())
        .first()
    )
    assert attempt is not None
    assert attempt.http_status == 500
    assert attempt.retryable == 1

    assert (
        db.query(SchedulerTaskEvent)
        .filter(
            SchedulerTaskEvent.task_id == task.id,
            SchedulerTaskEvent.event_type == "STATUS_CHANGED",
            SchedulerTaskEvent.to_status == dispatcher_module.TaskStatus.PENDING,
        )
        .count()
        >= 1
    )
    db.close()


def test_dispatcher_non_retryable_4xx_fails(monkeypatch):
    import scheduler_center.dispatcher as dispatcher_module

    db_path = os.path.abspath(f"./.tmp_scheduler_dispatcher_test_{uuid.uuid4().hex}.db")
    SessionLocal = _make_session_local(db_path)
    monkeypatch.setattr(dispatcher_module, "SessionLocal", SessionLocal)
    dispatcher_module.scheduler_settings.scheduler_agent_endpoints_raw = "http://agent"

    class FakeClient:
        def __init__(self, *args, **kwargs):
            pass

        def __enter__(self):
            return self

        def __exit__(self, exc_type, exc, tb):
            return False

        def post(self, url, json, headers):
            return _FakeResp(400, text="bad request")

    monkeypatch.setattr(dispatcher_module.httpx, "Client", FakeClient)

    db = SessionLocal()
    task = SchedulerTask(
        id=str(uuid.uuid4()),
        idempotency_key=None,
        trace_id="trace-dispatcher-2",
        task_type="demo",
        payload_json="{}",
        status=dispatcher_module.TaskStatus.RUNNING,
        cancel_requested=0,
        max_retries=2,
        retry_delay_seconds=0.0,
        attempt_count=0,
        next_run_at=None,
        last_agent=None,
        result_json=None,
        last_error=None,
    )
    db.add(task)
    db.commit()
    db.close()

    d = dispatcher_module.SchedulerDispatcher()
    d._execute_task(task.id)

    db = SessionLocal()
    task2 = db.query(SchedulerTask).filter(SchedulerTask.id == task.id).first()
    assert task2 is not None
    assert task2.status == dispatcher_module.TaskStatus.FAILED
    assert task2.next_run_at is None

    attempt = (
        db.query(SchedulerTaskAttempt)
        .filter(SchedulerTaskAttempt.task_id == task.id)
        .order_by(SchedulerTaskAttempt.attempt_no.asc())
        .first()
    )
    assert attempt is not None
    assert attempt.http_status == 400
    assert attempt.retryable == 0
    db.close()


def test_dispatcher_cancel_during_running_prevents_retry(monkeypatch):
    import scheduler_center.dispatcher as dispatcher_module

    db_path = os.path.abspath(f"./.tmp_scheduler_dispatcher_test_{uuid.uuid4().hex}.db")
    SessionLocal = _make_session_local(db_path)
    monkeypatch.setattr(dispatcher_module, "SessionLocal", SessionLocal)
    dispatcher_module.scheduler_settings.scheduler_agent_endpoints_raw = "http://agent"

    class FakeClient:
        def __init__(self, *args, **kwargs):
            pass

        def __enter__(self):
            return self

        def __exit__(self, exc_type, exc, tb):
            return False

        def post(self, url, json, headers):
            db = SessionLocal()
            task = db.query(SchedulerTask).filter(SchedulerTask.id == json["task_id"]).first()
            assert task is not None
            task.cancel_requested = 1
            db.commit()
            db.close()
            return _FakeResp(500, text="server error")

    monkeypatch.setattr(dispatcher_module.httpx, "Client", FakeClient)

    db = SessionLocal()
    task = SchedulerTask(
        id=str(uuid.uuid4()),
        idempotency_key=None,
        trace_id="trace-dispatcher-3",
        task_type="demo",
        payload_json="{}",
        status=dispatcher_module.TaskStatus.RUNNING,
        cancel_requested=0,
        max_retries=2,
        retry_delay_seconds=0.0,
        attempt_count=0,
        next_run_at=None,
        last_agent=None,
        result_json=None,
        last_error=None,
    )
    db.add(task)
    db.commit()
    db.close()

    d = dispatcher_module.SchedulerDispatcher()
    d._execute_task(task.id)

    db = SessionLocal()
    task2 = db.query(SchedulerTask).filter(SchedulerTask.id == task.id).first()
    assert task2 is not None
    assert task2.status == dispatcher_module.TaskStatus.CANCELED
    assert task2.next_run_at is None
    db.close()


def test_dispatcher_timeout_is_retryable(monkeypatch):
    import scheduler_center.dispatcher as dispatcher_module

    db_path = os.path.abspath(f"./.tmp_scheduler_dispatcher_test_{uuid.uuid4().hex}.db")
    SessionLocal = _make_session_local(db_path)
    monkeypatch.setattr(dispatcher_module, "SessionLocal", SessionLocal)
    dispatcher_module.scheduler_settings.scheduler_agent_endpoints_raw = "http://agent"

    class FakeClient:
        def __init__(self, *args, **kwargs):
            pass

        def __enter__(self):
            return self

        def __exit__(self, exc_type, exc, tb):
            return False

        def post(self, url, json, headers):
            raise httpx.ReadTimeout("timeout")

    monkeypatch.setattr(dispatcher_module.httpx, "Client", FakeClient)

    db = SessionLocal()
    task = SchedulerTask(
        id=str(uuid.uuid4()),
        idempotency_key=None,
        trace_id="trace-dispatcher-4",
        task_type="demo",
        payload_json="{}",
        status=dispatcher_module.TaskStatus.RUNNING,
        cancel_requested=0,
        max_retries=2,
        retry_delay_seconds=0.0,
        attempt_count=0,
        next_run_at=None,
        last_agent=None,
        result_json=None,
        last_error=None,
    )
    db.add(task)
    db.commit()
    db.close()

    d = dispatcher_module.SchedulerDispatcher()
    d._execute_task(task.id)

    db = SessionLocal()
    task2 = db.query(SchedulerTask).filter(SchedulerTask.id == task.id).first()
    assert task2 is not None
    assert task2.status == dispatcher_module.TaskStatus.PENDING
    attempt = (
        db.query(SchedulerTaskAttempt)
        .filter(SchedulerTaskAttempt.task_id == task.id)
        .order_by(SchedulerTaskAttempt.attempt_no.asc())
        .first()
    )
    assert attempt is not None
    assert attempt.retryable == 1
    db.close()


def test_dispatcher_choose_registered_agent_by_task_type(monkeypatch):
    import scheduler_center.dispatcher as dispatcher_module

    db_path = os.path.abspath(f"./.tmp_scheduler_dispatcher_test_{uuid.uuid4().hex}.db")
    SessionLocal = _make_session_local(db_path)
    monkeypatch.setattr(dispatcher_module, "SessionLocal", SessionLocal)
    dispatcher_module.scheduler_settings.scheduler_agent_endpoints_raw = ""
    dispatcher_module.scheduler_settings.scheduler_agent_registry_prefer_db = True
    dispatcher_module.scheduler_settings.scheduler_agent_health_cache_seconds = 0.0

    class FakeClient:
        def __init__(self, *args, **kwargs):
            pass

        def __enter__(self):
            return self

        def __exit__(self, exc_type, exc, tb):
            return False

        def get(self, url):
            return _FakeResp(200, text="ok")

        def post(self, url, json, headers):
            return _FakeResp(200, text="ok", json_data={"ok": True})

    monkeypatch.setattr(dispatcher_module.httpx, "Client", FakeClient)

    db = SessionLocal()
    db.add(
        SchedulerAgent(
            agent_key="agent-1",
            name="Agent One",
            base_url="http://agent",
            task_types_json='["demo"]',
            capabilities_json="{}",
            health_path="/health",
            status=1,
        )
    )
    task = SchedulerTask(
        id=str(uuid.uuid4()),
        idempotency_key=None,
        trace_id="trace-dispatcher-5",
        task_type="demo",
        payload_json="{}",
        status=dispatcher_module.TaskStatus.RUNNING,
        cancel_requested=0,
        max_retries=0,
        retry_delay_seconds=0.0,
        attempt_count=0,
        next_run_at=None,
        last_agent=None,
        result_json=None,
        last_error=None,
    )
    db.add(task)
    db.commit()
    db.close()

    d = dispatcher_module.SchedulerDispatcher()
    d._execute_task(task.id)

    db = SessionLocal()
    task2 = db.query(SchedulerTask).filter(SchedulerTask.id == task.id).first()
    assert task2 is not None
    assert task2.status == dispatcher_module.TaskStatus.SUCCEEDED
    assert task2.last_agent == "http://agent"
    db.close()

