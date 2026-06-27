from __future__ import annotations

import os
import uuid

import httpx
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool

from scheduler_center.database import Base
from scheduler_center.models import SchedulerAgent, SchedulerTask, SchedulerTaskAttempt, SchedulerTaskEvent



class _FakeResp:
    def __init__(self, status_code: int, text: str = "", json_data=None):
        self.status_code = status_code
        self.text = text
        self._json_data = json_data if json_data is not None else {"ok": False}

    def json(self):
        return self._json_data


def _make_session_local(_db_path: str):
    engine = create_engine(
        "sqlite://",
        connect_args={"check_same_thread": False},
        pool_pre_ping=True,
        poolclass=StaticPool,
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


def test_dispatcher_executes_local_fetch_batch(monkeypatch):
    import scheduler_center.dispatcher as dispatcher_module
    from apps.platform.models import ContentItem, FetchRun, SourceConfig
    from apps.platform.database import Base as PlatformBase
    from apps.fetcher_engine.api.models import FetchBatchError, FetchBatchResult, FetchBatchStats

    db_path = os.path.abspath(f"./.tmp_scheduler_dispatcher_test_{uuid.uuid4().hex}.db")
    session_local = _make_session_local(db_path)
    monkeypatch.setattr(dispatcher_module, "SessionLocal", session_local)
    PlatformBase.metadata.create_all(bind=session_local.kw["bind"])

    def fake_load_source_deps():
        from apps.platform import models as pm
        return session_local, pm, lambda *a, **kw: []

    monkeypatch.setattr(dispatcher_module, "_load_platform_source_dependencies", fake_load_source_deps)

    captured_request: dict[str, object] = {}

    class FakeFetchService:
        def __init__(self, db, source_repo):  # noqa: ANN001
            self.db = db
            self.source_repo = source_repo

        async def run_sources(self, request):  # noqa: ANN001
            captured_request["run_id"] = request.run_id
            captured_request["sources"] = list(request.sources)
            captured_request["subscription_ids"] = list(request.subscription_ids)
            captured_request["lookback_hours"] = request.lookback_hours
            captured_request["limit_per_source"] = request.limit_per_source
            captured_request["options"] = dict(request.options)

            self.source_repo.create_content_item(
                self.db,
                source_type="reddit",
                source_id="t3_test_1",
                source_account="python",
                source_url="https://example.com/r/test/1",
                title="Test Reddit Post",
                raw_content="Fetched content",
                summary="Fetched content",
                tags_json="[]",
                language="zh",
                pipeline_status="fetched",
                review_status="pending",
            )
            return FetchBatchResult(
                run_id=request.run_id,
                items=[
                    {
                        "source_type": "reddit",
                        "source_id": "t3_test_1",
                        "title": "Test Reddit Post",
                        "source_url": "https://example.com/r/test/1",
                    }
                ],
                matched_items=[
                    {
                        "source_type": "reddit",
                        "source_id": "t3_test_1",
                        "title": "Test Reddit Post",
                        "source_url": "https://example.com/r/test/1",
                    }
                ],
                errors=[],
                stats=FetchBatchStats(
                    total_fetched=1,
                    total_inserted=1,
                    total_deduped=0,
                    sources_succeeded=1,
                    sources_failed=0,
                ),
            )

        def fake_load_dependencies():
            from apps.platform import models as platform_models
            from apps.fetcher_engine.api.models import FetchBatchRequest

            def create_content_item(db, **kwargs):  # noqa: ANN001
                item = platform_models.ContentItem(**kwargs)
                db.add(item)
                db.commit()
                db.refresh(item)
                return item

            def get_content_item_by_source(db, source_type, source_id):  # noqa: ANN001
                return (
                    db.query(platform_models.ContentItem)
                    .filter(platform_models.ContentItem.source_type == source_type)
                    .filter(platform_models.ContentItem.source_id == source_id)
                    .first()
                )

            def update_content_item(db, item, **kwargs):  # noqa: ANN001
                for key, value in kwargs.items():
                    setattr(item, key, value)
                db.commit()
                db.refresh(item)
                return item

            return (
                platform_models,
                create_content_item,
                get_content_item_by_source,
                update_content_item,
                FetchBatchRequest,
                FakeFetchService,
            )

        monkeypatch.setattr(dispatcher_module, "_load_platform_fetch_dependencies", fake_load_dependencies)

    db = session_local()
    source = SourceConfig(
        name="Reddit Python",
        source_type="reddit",
        enabled=True,
        channels='["r/python"]',
        keywords='[]',
        lookback_hours=24,
        item_limit=20,
        dedup_window_hours=24,
        config_json='{"subreddit":"python","sort":"new"}',
    )
    db.add(source)
    db.commit()
    db.refresh(source)

    task = SchedulerTask(
        id=str(uuid.uuid4()),
        idempotency_key=None,
        trace_id="trace-fetch-batch-1",
        task_type="content.fetch.batch",
        payload_json='{"source_config_id": %d, "source_type": "reddit", "source_name": "Reddit Python", "channels": ["r/python"], "lookback_hours": 24, "limit": 5, "config": {"subreddit": "python", "sort": "new"}}' % source.id,
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

    fetch_run = FetchRun(
        source_config_id=source.id,
        trigger_mode="manual",
        status="pending",
        task_id=task.id,
        trace_id=task.trace_id,
        requested_by="tester",
        request_payload=task.payload_json,
    )
    db.add(fetch_run)
    db.commit()
    db.close()

    dispatcher = dispatcher_module.SchedulerDispatcher()
    dispatcher._execute_task(task.id)

    db = session_local()
    task_row = db.query(SchedulerTask).filter(SchedulerTask.id == task.id).first()
    assert task_row is not None
    assert task_row.status == dispatcher_module.TaskStatus.SUCCEEDED
    assert captured_request == {
        "run_id": task.id,
        "sources": ["reddit"],
        "subscription_ids": [source.id],
        "lookback_hours": 24,
        "limit_per_source": 5,
        "options": {"subreddit": "python", "sort": "new"},
    }

    fetch_run_row = db.query(FetchRun).filter(FetchRun.task_id == task.id).first()
    assert fetch_run_row is not None
    assert fetch_run_row.status == "success"
    assert fetch_run_row.fetched_count == 1
    assert fetch_run_row.inserted_count == 1

    content_item = db.query(ContentItem).filter(ContentItem.source_type == "reddit").filter(ContentItem.source_id == "t3_test_1").first()
    assert content_item is not None
    assert content_item.fetch_run_id == fetch_run_row.id
    assert content_item.pipeline_status == "fetched"
    db.close()


def test_dispatcher_attaches_fetch_run_id_to_deduped_existing_content(monkeypatch):
    import scheduler_center.dispatcher as dispatcher_module
    from apps.platform.models import ContentItem, FetchRun, SourceConfig
    from apps.platform.database import Base as PlatformBase
    from apps.fetcher_engine.api.models import FetchBatchResult, FetchBatchStats

    db_path = os.path.abspath(f"./.tmp_scheduler_dispatcher_test_{uuid.uuid4().hex}.db")
    session_local = _make_session_local(db_path)
    monkeypatch.setattr(dispatcher_module, "SessionLocal", session_local)
    PlatformBase.metadata.create_all(bind=session_local.kw["bind"])

    def fake_load_source_deps():
        from apps.platform import models as pm
        return session_local, pm, lambda *a, **kw: []

    monkeypatch.setattr(dispatcher_module, "_load_platform_source_dependencies", fake_load_source_deps)

    class FakeFetchService:
        def __init__(self, db, source_repo):  # noqa: ANN001
            self.db = db
            self.source_repo = source_repo

        async def run_sources(self, request):  # noqa: ANN001
            return FetchBatchResult(
                run_id=request.run_id,
                items=[],
                matched_items=[
                    {
                        "source_type": "reddit",
                        "source_id": "t3_existing_1",
                        "title": "Existing Reddit Post",
                        "source_url": "https://example.com/r/test/existing",
                    }
                ],
                errors=[],
                stats=FetchBatchStats(
                    total_fetched=1,
                    total_inserted=0,
                    total_deduped=1,
                    sources_succeeded=1,
                    sources_failed=0,
                ),
            )

    def fake_load_dependencies():
        from apps.platform import models as platform_models
        from apps.fetcher_engine.api.models import FetchBatchRequest

        def create_content_item(db, **kwargs):  # noqa: ANN001
            item = platform_models.ContentItem(**kwargs)
            db.add(item)
            db.commit()
            db.refresh(item)
            return item

        def get_content_item_by_source(db, source_type, source_id):  # noqa: ANN001
            return (
                db.query(platform_models.ContentItem)
                .filter(platform_models.ContentItem.source_type == source_type)
                .filter(platform_models.ContentItem.source_id == source_id)
                .first()
            )

        def update_content_item(db, item, **kwargs):  # noqa: ANN001
            for key, value in kwargs.items():
                setattr(item, key, value)
            db.commit()
            db.refresh(item)
            return item

        return (
            platform_models,
            create_content_item,
            get_content_item_by_source,
            update_content_item,
            FetchBatchRequest,
            FakeFetchService,
        )

    monkeypatch.setattr(dispatcher_module, "_load_platform_fetch_dependencies", fake_load_dependencies)

    db = session_local()
    source = SourceConfig(
        name="Reddit Python",
        source_type="reddit",
        enabled=True,
        channels='["r/python"]',
        keywords='[]',
        lookback_hours=24,
        item_limit=20,
        dedup_window_hours=24,
        config_json='{"subreddit":"python","sort":"new"}',
    )
    db.add(source)
    db.commit()
    db.refresh(source)

    existing_item = ContentItem(
        source_config_id=source.id,
        fetch_run_id=None,
        source_type="reddit",
        source_id="t3_existing_1",
        source_url="https://example.com/r/test/existing",
        title="Existing Reddit Post",
        language="zh",
        raw_content="old",
        tags_json="[]",
        score=0,
        publish_status="pending",
        pipeline_status="fetched",
        review_status="pending",
        digest_included=False,
    )
    db.add(existing_item)
    db.commit()

    task = SchedulerTask(
        id=str(uuid.uuid4()),
        idempotency_key=None,
        trace_id="trace-fetch-batch-dedup-1",
        task_type="content.fetch.batch",
        payload_json='{"source_config_id": %d, "source_type": "reddit", "lookback_hours": 24, "limit": 5, "config": {"subreddit": "python"}}' % source.id,
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

    fetch_run = FetchRun(
        source_config_id=source.id,
        trigger_mode="manual",
        status="pending",
        task_id=task.id,
        trace_id=task.trace_id,
        requested_by="tester",
        request_payload=task.payload_json,
    )
    db.add(fetch_run)
    db.commit()
    db.close()

    dispatcher = dispatcher_module.SchedulerDispatcher()
    dispatcher._execute_task(task.id)

    db = session_local()
    fetch_run_row = db.query(FetchRun).filter(FetchRun.task_id == task.id).first()
    assert fetch_run_row is not None
    updated_item = db.query(ContentItem).filter(ContentItem.source_id == "t3_existing_1").first()
    assert updated_item is not None
    assert updated_item.fetch_run_id == fetch_run_row.id
    db.close()


def test_dispatcher_marks_local_fetch_batch_failed_when_fetch_service_returns_errors(monkeypatch):
    import scheduler_center.dispatcher as dispatcher_module
    from apps.platform.models import FetchRun, SourceConfig
    from apps.platform.database import Base as PlatformBase
    from apps.fetcher_engine.api.models import FetchBatchError, FetchBatchResult, FetchBatchStats

    db_path = os.path.abspath(f"./.tmp_scheduler_dispatcher_test_{uuid.uuid4().hex}.db")
    session_local = _make_session_local(db_path)
    monkeypatch.setattr(dispatcher_module, "SessionLocal", session_local)
    PlatformBase.metadata.create_all(bind=session_local.kw["bind"])

    def fake_load_source_deps():
        from apps.platform import models as pm
        return session_local, pm, lambda *a, **kw: []

    monkeypatch.setattr(dispatcher_module, "_load_platform_source_dependencies", fake_load_source_deps)

    class FakeFetchService:
        def __init__(self, db, source_repo):  # noqa: ANN001
            self.db = db
            self.source_repo = source_repo

        async def run_sources(self, request):  # noqa: ANN001
            return FetchBatchResult(
                run_id=request.run_id,
                items=[],
                errors=[
                    FetchBatchError(
                        source="reddit",
                        error="upstream fetch failed",
                        traceback=None,
                    )
                ],
                stats=FetchBatchStats(
                    total_fetched=0,
                    total_inserted=0,
                    total_deduped=0,
                    sources_succeeded=0,
                    sources_failed=1,
                ),
            )

    def fake_load_dependencies():
        from apps.platform import models as platform_models
        from apps.fetcher_engine.api.models import FetchBatchRequest

        def create_content_item(db, **kwargs):  # noqa: ANN001
            item = platform_models.ContentItem(**kwargs)
            db.add(item)
            db.commit()
            db.refresh(item)
            return item

        def get_content_item_by_source(db, source_type, source_id):  # noqa: ANN001
            return (
                db.query(platform_models.ContentItem)
                .filter(platform_models.ContentItem.source_type == source_type)
                .filter(platform_models.ContentItem.source_id == source_id)
                .first()
            )

        def update_content_item(db, item, **kwargs):  # noqa: ANN001
            for key, value in kwargs.items():
                setattr(item, key, value)
            db.commit()
            db.refresh(item)
            return item

        return (
            platform_models,
            create_content_item,
            get_content_item_by_source,
            update_content_item,
            FetchBatchRequest,
            FakeFetchService,
        )

    monkeypatch.setattr(dispatcher_module, "_load_platform_fetch_dependencies", fake_load_dependencies)

    db = session_local()
    source = SourceConfig(
        name="Reddit Python",
        source_type="reddit",
        enabled=True,
        channels='["r/python"]',
        keywords='[]',
        lookback_hours=24,
        item_limit=20,
        dedup_window_hours=24,
        config_json='{"subreddit":"python","sort":"new"}',
    )
    db.add(source)
    db.commit()
    db.refresh(source)

    task = SchedulerTask(
        id=str(uuid.uuid4()),
        idempotency_key=None,
        trace_id="trace-fetch-batch-failed-1",
        task_type="content.fetch.batch",
        payload_json='{"source_config_id": %d, "source_type": "reddit", "lookback_hours": 24, "limit": 5, "config": {"subreddit": "python", "sort": "new"}}' % source.id,
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

    fetch_run = FetchRun(
        source_config_id=source.id,
        trigger_mode="manual",
        status="pending",
        task_id=task.id,
        trace_id=task.trace_id,
        requested_by="tester",
        request_payload=task.payload_json,
    )
    db.add(fetch_run)
    db.commit()
    db.close()

    dispatcher = dispatcher_module.SchedulerDispatcher()
    dispatcher._execute_task(task.id)

    db = session_local()
    task_row = db.query(SchedulerTask).filter(SchedulerTask.id == task.id).first()
    assert task_row is not None
    assert task_row.status == dispatcher_module.TaskStatus.FAILED
    assert task_row.last_error == "upstream fetch failed"

    fetch_run_row = db.query(FetchRun).filter(FetchRun.task_id == task.id).first()
    assert fetch_run_row is not None
    assert fetch_run_row.status == "failure"
    assert fetch_run_row.error_message == "upstream fetch failed"
    db.close()

