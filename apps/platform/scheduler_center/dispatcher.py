from __future__ import annotations

import asyncio
import json
import threading
import time
import uuid
from concurrent.futures import Future, ThreadPoolExecutor
from datetime import UTC, datetime, timedelta
from typing import Any, Optional

import httpx
from sqlalchemy import or_
from sqlalchemy.orm import Session

try:
    from scheduler_center import _ensure_stdlib_platform
    from scheduler_center.config import (
        CONTENT_FETCH_BATCH,
        CONTENT_PIPELINE_DAILY_DIGEST,
        CONTENT_PIPELINE_RADAR,
        scheduler_settings,
    )
    from scheduler_center.database import SessionLocal
    from scheduler_center.models import (
        SchedulerAgent,
        SchedulerTask,
        SchedulerTaskAttempt,
        SchedulerTaskEvent,
        SchedulerTaskLog,
    )
except ImportError:  # pragma: no cover - package import fallback
    from apps.platform.scheduler_center import _ensure_stdlib_platform
    from apps.platform.scheduler_center.config import (
        CONTENT_FETCH_BATCH,
        CONTENT_PIPELINE_DAILY_DIGEST,
        CONTENT_PIPELINE_RADAR,
        scheduler_settings,
    )
    from apps.platform.scheduler_center.database import SessionLocal
    from apps.platform.scheduler_center.models import (
        SchedulerAgent,
        SchedulerTask,
        SchedulerTaskAttempt,
        SchedulerTaskEvent,
        SchedulerTaskLog,
    )

_ensure_stdlib_platform()


def _load_content_domain_client():
    try:
        from services.content_domain_client import ContentDomainClient
    except ImportError:  # pragma: no cover - package import fallback
        from apps.platform.services.content_domain_client import ContentDomainClient
    return ContentDomainClient


def _load_platform_fetch_dependencies():
    from apps.platform import models as platform_models
    from apps.platform.crud.crud_content_item import (
        create_content_item,
        get_content_item_by_source,
        update_content_item,
    )

    from apps.fetcher_engine.api.models import FetchBatchRequest
    from apps.fetcher_engine.api.service import FetchService

    return platform_models, create_content_item, get_content_item_by_source, update_content_item, FetchBatchRequest, FetchService


def _load_platform_source_dependencies():
    from apps.platform import models as platform_models
    from apps.platform.database import SessionLocal as PlatformSessionLocal
    from apps.platform.services.fetch_alert_service import dispatch_fetch_alerts

    return PlatformSessionLocal, platform_models, dispatch_fetch_alerts


def _record_fetch_metrics(**kwargs: Any) -> None:
    try:
        from apps.platform.core.observability.metrics import record_fetch_metrics
    except Exception:
        return
    record_fetch_metrics(**kwargs)


class TaskStatus:
    PENDING = "PENDING"
    RUNNING = "RUNNING"
    SUCCEEDED = "SUCCEEDED"
    FAILED = "FAILED"
    CANCELED = "CANCELED"


def new_task_id() -> str:
    return str(uuid.uuid4())


def _utcnow() -> datetime:
    return datetime.now(UTC).replace(tzinfo=None)


class SchedulerDispatcher:
    def __init__(self) -> None:
        self._stop_event = threading.Event()
        self._thread: Optional[threading.Thread] = None
        self._cron_stop_event = threading.Event()
        self._cron_thread: Optional[threading.Thread] = None
        self._executor = ThreadPoolExecutor(max_workers=scheduler_settings.scheduler_max_concurrency)
        self._running: dict[str, Future[Any]] = {}
        self._running_lock = threading.Lock()
        self._rr_lock = threading.Lock()
        self._scheduled_submit_lock = threading.Lock()
        self._rr_index = 0
        self._registry_built = False
        self._last_scheduled_minute: str | None = None

    def start(self) -> None:
        if self._thread and self._thread.is_alive():
            return
        self._stop_event.clear()
        self._thread = threading.Thread(target=self._run, name="scheduler-dispatcher", daemon=True)
        self._thread.start()

    def stop(self, wait_seconds: float = 3.0) -> None:
        self._stop_event.set()
        if self._thread:
            self._thread.join(timeout=wait_seconds)
        self._executor.shutdown(wait=False, cancel_futures=True)

    def start_cron(self) -> None:
        if self._cron_thread and self._cron_thread.is_alive():
            return
        self._cron_stop_event.clear()
        self._cron_thread = threading.Thread(target=self._run_cron, name="scheduler-cron", daemon=True)
        self._cron_thread.start()

    def stop_cron(self, wait_seconds: float = 3.0) -> None:
        self._cron_stop_event.set()
        if self._cron_thread:
            self._cron_thread.join(timeout=wait_seconds)

    def _run(self) -> None:
        self._recover_running_tasks()
        while not self._stop_event.is_set():
            try:
                self._dispatch_once()
            except Exception:
                pass
            time.sleep(max(0.05, scheduler_settings.scheduler_poll_interval_seconds))

    def _run_cron(self) -> None:
        while not self._cron_stop_event.is_set():
            try:
                self._run_scheduled_jobs_once()
            except Exception:
                pass
            time.sleep(30.0)

    def _recover_running_tasks(self) -> None:
        db = SessionLocal()
        try:
            now = _utcnow()
            tasks = (
                db.query(SchedulerTask)
                .filter(SchedulerTask.status == TaskStatus.RUNNING)
                .all()
            )
            for task in tasks:
                trace_id = task.trace_id or None
                before = task.status
                if task.cancel_requested:
                    task.status = TaskStatus.CANCELED
                else:
                    task.status = TaskStatus.PENDING
                task.updated_at = now
                self._append_log(
                    db,
                    task_id=task.id,
                    trace_id=trace_id,
                    level="WARN",
                    message="recovered from RUNNING on startup",
                )
                self._append_event(
                    db,
                    task_id=task.id,
                    trace_id=trace_id,
                    event_type="RECOVERED_ON_STARTUP",
                    from_status=before,
                    to_status=task.status,
                    attempt_no=None,
                    message=None,
                )
            db.commit()
        finally:
            db.close()

    def _dispatch_once(self) -> None:
        self._cleanup_done_futures()

        with self._running_lock:
            available = scheduler_settings.scheduler_max_concurrency - len(self._running)

        if available <= 0:
            return

        db = SessionLocal()
        try:
            now = _utcnow()
            query = db.query(SchedulerTask).filter(
                SchedulerTask.status == TaskStatus.PENDING,
                SchedulerTask.cancel_requested == 0,
                or_(SchedulerTask.next_run_at.is_(None), SchedulerTask.next_run_at <= now),
            )
            tasks = query.order_by(SchedulerTask.created_at.asc()).limit(available).all()

            for task in tasks:
                trace_id = task.trace_id or None
                before = task.status
                task.status = TaskStatus.RUNNING
                task.updated_at = now
                self._append_log(
                    db,
                    task_id=task.id,
                    trace_id=trace_id,
                    level="INFO",
                    message="dispatching",
                )
                self._append_event(
                    db,
                    task_id=task.id,
                    trace_id=trace_id,
                    event_type="STATUS_CHANGED",
                    from_status=before,
                    to_status=TaskStatus.RUNNING,
                    attempt_no=None,
                    message=None,
                )
            db.commit()

            for task in tasks:
                future = self._executor.submit(self._execute_task, task.id)
                with self._running_lock:
                    self._running[task.id] = future
        finally:
            db.close()

    def _cleanup_done_futures(self) -> None:
        done_ids: list[str] = []
        with self._running_lock:
            for task_id, future in self._running.items():
                if future.done():
                    done_ids.append(task_id)
            for task_id in done_ids:
                self._running.pop(task_id, None)

    def _run_scheduled_jobs_once(self, now: datetime | None = None) -> list[str]:
        if not scheduler_settings.scheduler_cron_enabled:
            return []
        current = now or _utcnow()
        minute_key = current.strftime("%Y-%m-%d %H:%M")
        if self._last_scheduled_minute == minute_key:
            return []

        dispatched: list[str] = []
        for job in scheduler_settings.scheduled_jobs:
            cron_expression = str(job.get("cron_expression") or "").strip()
            if self._cron_matches(cron_expression, current):
                task_id = self.dispatch_scheduled_task(
                    task_type=str(job["task_type"]),
                    payload=dict(job.get("payload") or {}),
                    scheduled_for=current,
                    idempotency_key=f"{job['task_type']}:{minute_key}",
                )
                dispatched.append(task_id)

        for job in self._load_dynamic_source_jobs(current):
            task_id = self.dispatch_scheduled_task(
                task_type=CONTENT_FETCH_BATCH,
                payload=job["payload"],
                scheduled_for=current,
                idempotency_key=str(job["idempotency_key"]),
            )
            dispatched.append(task_id)

        if dispatched:
            self._last_scheduled_minute = minute_key
        return dispatched

    def dispatch_scheduled_task(
        self,
        *,
        task_type: str,
        payload: dict[str, Any],
        scheduled_for: datetime | None = None,
        idempotency_key: str | None = None,
    ) -> str:
        with self._scheduled_submit_lock:
            return self._dispatch_scheduled_task_locked(
                task_type=task_type,
                payload=payload,
                scheduled_for=scheduled_for,
                idempotency_key=idempotency_key,
            )

    def _dispatch_scheduled_task_locked(
        self,
        *,
        task_type: str,
        payload: dict[str, Any],
        scheduled_for: datetime | None = None,
        idempotency_key: str | None = None,
    ) -> str:
        db = SessionLocal()
        try:
            now = scheduled_for or _utcnow()
            resolved_idempotency_key = idempotency_key or f"{task_type}:{now.strftime('%Y-%m-%dT%H:%M')}"
            existing_id = (
                db.query(SchedulerTask.id)
                .filter(SchedulerTask.idempotency_key == resolved_idempotency_key)
                .scalar()
            )
            if existing_id is not None:
                return str(existing_id)
            task_id = new_task_id()
            trace_id = str(uuid.uuid4())
            task = SchedulerTask(
                id=task_id,
                idempotency_key=resolved_idempotency_key,
                trace_id=trace_id,
                task_type=task_type,
                payload_json=json.dumps(payload, ensure_ascii=False),
                status=TaskStatus.PENDING,
                cancel_requested=0,
                max_retries=0,
                retry_delay_seconds=0.0,
                attempt_count=0,
                next_run_at=None,
                last_agent=None,
                result_json=None,
                last_error=None,
                created_at=now,
                updated_at=now,
            )
            db.add(task)
            self._append_log(
                db,
                task_id=task.id,
                trace_id=trace_id,
                level="INFO",
                message=f"scheduled task submitted: {task_type}",
            )
            self._append_event(
                db,
                task_id=task.id,
                trace_id=trace_id,
                event_type="SUBMITTED",
                from_status=None,
                to_status=TaskStatus.PENDING,
                attempt_no=0,
                message="submitted by cron scheduler",
            )
            try:
                db.commit()
            except Exception:
                db.rollback()
                for _ in range(3):
                    existing_id = (
                        db.query(SchedulerTask.id)
                        .filter(SchedulerTask.idempotency_key == task.idempotency_key)
                        .scalar()
                    )
                    if existing_id is not None:
                        return str(existing_id)
                    time.sleep(0.01)
                raise
            return task_id
        finally:
            db.close()

    @staticmethod
    def _cron_matches(cron_expression: str, now: datetime) -> bool:
        parts = cron_expression.split()
        if len(parts) != 5:
            return False
        minute, hour, day, month, weekday = parts
        return (
            SchedulerDispatcher._cron_field_matches(minute, now.minute)
            and SchedulerDispatcher._cron_field_matches(hour, now.hour)
            and SchedulerDispatcher._cron_field_matches(day, now.day)
            and SchedulerDispatcher._cron_field_matches(month, now.month)
            and SchedulerDispatcher._cron_field_matches(weekday, now.weekday())
        )

    @staticmethod
    def _cron_field_matches(expression: str, value: int) -> bool:
        expression = expression.strip()
        if expression == "*":
            return True
        if expression.startswith("*/"):
            try:
                step = int(expression[2:])
            except ValueError:
                return False
            return step > 0 and value % step == 0
        if "," in expression:
            return any(SchedulerDispatcher._cron_field_matches(part, value) for part in expression.split(","))
        try:
            return int(expression) == value
        except ValueError:
            return False

    def _load_dynamic_source_jobs(self, now: datetime) -> list[dict[str, Any]]:
        try:
            platform_session_local, platform_models, _dispatch_fetch_alerts = _load_platform_source_dependencies()
            del _dispatch_fetch_alerts
        except Exception:
            return []

        db = platform_session_local()
        try:
            try:
                rows = (
                    db.query(platform_models.SourceConfig)
                    .filter(platform_models.SourceConfig.enabled.is_(True))
                    .order_by(platform_models.SourceConfig.id.asc())
                    .all()
                )
            except Exception:
                return []
            jobs: list[dict[str, Any]] = []
            for row in rows:
                config = self._load_json_dict(getattr(row, "config_json", None))
                schedule_expression = str(config.get("schedule_expression") or "").strip()
                if not schedule_expression or not self._cron_matches(schedule_expression, now):
                    continue
                jobs.append(
                    {
                        "idempotency_key": f"{CONTENT_FETCH_BATCH}:source:{row.id}:{now.strftime('%Y-%m-%dT%H:%M')}",
                        "payload": {
                            "source_config_id": row.id,
                            "source_type": row.source_type,
                            "source_name": row.name,
                            "channels": self._load_json_list(getattr(row, "channels", None)),
                            "keywords": self._load_json_list(getattr(row, "keywords", None)),
                            "lookback_hours": int(row.lookback_hours or 24),
                            "limit": int(row.item_limit or 20),
                            "dedup_window_hours": int(row.dedup_window_hours or 24),
                            "trigger_type": "scheduled",
                            "config": config,
                        },
                    }
                )
            return jobs
        finally:
            db.close()

    @staticmethod
    def _load_json_dict(raw: str | None) -> dict[str, Any]:
        if not raw:
            return {}
        try:
            parsed = json.loads(raw)
        except Exception:
            return {}
        return parsed if isinstance(parsed, dict) else {}

    @staticmethod
    def _load_json_list(raw: str | None) -> list[Any]:
        if not raw:
            return []
        try:
            parsed = json.loads(raw)
        except Exception:
            return []
        return parsed if isinstance(parsed, list) else []

    def _choose_agent_from_endpoints(self) -> Optional[str]:
        endpoints = scheduler_settings.scheduler_agent_endpoints
        if not endpoints:
            return None
        with self._rr_lock:
            idx = self._rr_index % len(endpoints)
            self._rr_index += 1
        return endpoints[idx]

    def _choose_agent(self, db: Session, task_type: str) -> Optional[str]:
        if scheduler_settings.scheduler_agent_registry_prefer_db:
            agent = self._choose_registered_agent(db, task_type)
            if agent:
                return agent.base_url
        return self._choose_agent_from_endpoints()

    def _choose_registered_agent(self, db: Session, task_type: str) -> Optional[SchedulerAgent]:
        now = _utcnow()
        ttl = float(scheduler_settings.scheduler_agent_heartbeat_ttl_seconds)
        desired = str(task_type or "").strip()
        agents = (
            db.query(SchedulerAgent)
            .filter(SchedulerAgent.status == 1)
            .order_by(SchedulerAgent.id.asc())
            .all()
        )
        candidates: list[SchedulerAgent] = []
        for agent in agents:
            if ttl > 0 and agent.last_heartbeat_at and (now - agent.last_heartbeat_at).total_seconds() > ttl:
                agent.last_health_check_at = None
            task_types = self._safe_json_list(agent.task_types_json)
            if desired not in task_types and "*" not in task_types:
                continue
            if not self._ensure_agent_healthy(db, agent, now):
                continue
            candidates.append(agent)

        if not candidates:
            return None
        with self._rr_lock:
            idx = self._rr_index % len(candidates)
            self._rr_index += 1
        return candidates[idx]

    def _ensure_agent_healthy(self, db: Session, agent: SchedulerAgent, now: datetime) -> bool:
        cache_seconds = float(scheduler_settings.scheduler_agent_health_cache_seconds)
        if agent.last_health_check_at is not None and cache_seconds > 0:
            age = (now - agent.last_health_check_at).total_seconds()
            if age >= 0 and age <= cache_seconds:
                return bool(agent.last_health_ok)

        url = agent.base_url.rstrip("/") + (agent.health_path or "/health")
        timeout = httpx.Timeout(float(scheduler_settings.scheduler_agent_health_timeout_seconds))
        ok = False
        err: str | None = None
        try:
            with httpx.Client(timeout=timeout, trust_env=False) as client:
                resp = client.get(url)
            ok = 200 <= int(resp.status_code) < 300
            if not ok:
                err = f"http {resp.status_code}"
        except Exception as exc:
            ok = False
            err = str(exc)

        agent.last_health_check_at = now
        agent.last_health_ok = 1 if ok else 0
        agent.last_health_error = err
        if ok:
            agent.last_heartbeat_at = now
        agent.updated_at = now
        db.commit()
        return ok

    def _safe_json_list(self, raw: str | None) -> set[str]:
        try:
            obj = json.loads(raw or "[]")
            if isinstance(obj, list):
                return {str(v) for v in obj if str(v).strip()}
            return {str(obj)}
        except Exception:
            return set()

    def _execute_task(self, task_id: str) -> None:
        db = SessionLocal()
        try:
            task = db.query(SchedulerTask).filter(SchedulerTask.id == task_id).first()
            if not task:
                return
            if task.status != TaskStatus.RUNNING:
                return

            if not task.trace_id:
                task.trace_id = str(uuid.uuid4())
                db.commit()
            trace_id = task.trace_id

            if task.cancel_requested:
                now = _utcnow()
                task.status = TaskStatus.CANCELED
                task.updated_at = now
                self._append_log(
                    db,
                    task_id=task.id,
                    trace_id=trace_id,
                    level="INFO",
                    message="canceled before execution",
                )
                self._append_event(
                    db,
                    task_id=task.id,
                    trace_id=trace_id,
                    event_type="STATUS_CHANGED",
                    from_status=TaskStatus.RUNNING,
                    to_status=TaskStatus.CANCELED,
                    attempt_no=None,
                    message="canceled before execution",
                )
                db.commit()
                return

            payload = self._safe_json_loads(task.payload_json) or {}
            attempt_no = int(task.attempt_count) + 1

            if task.task_type == "content.workflow.run":
                self._execute_content_workflow(
                    db=db,
                    task=task,
                    attempt_no=attempt_no,
                    payload=payload,
                )
                return

            if task.task_type == CONTENT_PIPELINE_RADAR:
                self._execute_scheduled_radar(
                    db=db,
                    task=task,
                    attempt_no=attempt_no,
                    payload=payload,
                )
                return

            if task.task_type == CONTENT_PIPELINE_DAILY_DIGEST:
                self._execute_scheduled_daily_digest(
                    db=db,
                    task=task,
                    attempt_no=attempt_no,
                    payload=payload,
                )
                return

            if task.task_type == "content.publish.approved":
                self._execute_publish_approved_content(
                    db=db,
                    task=task,
                    attempt_no=attempt_no,
                    payload=payload,
                )
                return

            if task.task_type == "content.pipeline.linear":
                self._execute_local_linear_pipeline(
                    db=db,
                    task=task,
                    attempt_no=attempt_no,
                    payload=payload,
                )
                return

            if task.task_type == "content.fetch.batch":
                self._execute_local_fetch_batch(
                    db=db,
                    task=task,
                    attempt_no=attempt_no,
                    payload=payload,
                )
                return

            agent = self._choose_agent(db, task.task_type)

            attempt = SchedulerTaskAttempt(
                task_id=task.id,
                attempt_no=attempt_no,
                agent=agent,
                trace_id=trace_id,
                status=TaskStatus.RUNNING,
                started_at=_utcnow(),
            )
            db.add(attempt)
            task.last_agent = agent
            task.updated_at = _utcnow()
            self._append_event(
                db,
                task_id=task.id,
                trace_id=trace_id,
                event_type="ATTEMPT_STARTED",
                from_status=TaskStatus.RUNNING,
                to_status=TaskStatus.RUNNING,
                attempt_no=attempt_no,
                message=None,
            )
            db.commit()
            db.refresh(attempt)

            if not agent:
                attempt.retryable = 1
                self._mark_retry_or_fail(
                    db,
                    task,
                    attempt,
                    attempt_no,
                    "no available agent",
                    retryable=True,
                )
                return

            url = agent.rstrip("/") + scheduler_settings.scheduler_agent_request_path
            headers: dict[str, str] = {}
            token = scheduler_settings.scheduler_agent_token or scheduler_settings.scheduler_internal_token
            if token:
                headers["x-internal-token"] = token
            headers["x-trace-id"] = trace_id

            request_body = {
                "task_id": task.id,
                "task_type": task.task_type,
                "payload": payload,
                "attempt_no": attempt_no,
                "trace_id": trace_id,
            }
            attempt.request_url = url
            attempt.request_json = json.dumps(request_body, ensure_ascii=False)[:20000]

            timeout = httpx.Timeout(scheduler_settings.scheduler_http_timeout_seconds)
            try:
                with httpx.Client(timeout=timeout, trust_env=False) as client:
                    resp = client.post(url, json=request_body, headers=headers)
            except Exception as exc:
                retryable = self._is_retryable_exception(exc)
                attempt.retryable = 1 if retryable else 0
                self._mark_retry_or_fail(
                    db,
                    task,
                    attempt,
                    attempt_no,
                    str(exc),
                    retryable=retryable,
                )
                return

            response_text = (resp.text or "")[:20000]
            attempt.http_status = resp.status_code
            attempt.response_text = response_text

            if 200 <= resp.status_code < 300:
                result_obj = None
                try:
                    result_obj = resp.json()
                except Exception:
                    result_obj = {"raw": response_text}

                now = _utcnow()
                attempt.status = TaskStatus.SUCCEEDED
                attempt.finished_at = now
                task.status = TaskStatus.SUCCEEDED
                task.attempt_count = attempt_no
                task.result_json = json.dumps(result_obj, ensure_ascii=False)
                task.last_error = None
                task.next_run_at = None
                task.updated_at = now
                self._append_log(
                    db,
                    task_id=task.id,
                    trace_id=trace_id,
                    level="INFO",
                    message=f"succeeded on attempt {attempt_no}",
                )
                self._append_event(
                    db,
                    task_id=task.id,
                    trace_id=trace_id,
                    event_type="ATTEMPT_FINISHED",
                    from_status=TaskStatus.RUNNING,
                    to_status=TaskStatus.SUCCEEDED,
                    attempt_no=attempt_no,
                    message=None,
                )
                self._append_event(
                    db,
                    task_id=task.id,
                    trace_id=trace_id,
                    event_type="STATUS_CHANGED",
                    from_status=TaskStatus.RUNNING,
                    to_status=TaskStatus.SUCCEEDED,
                    attempt_no=attempt_no,
                    message=None,
                )
                db.commit()
                return

            error = f"http {resp.status_code}"
            retryable = self._is_retryable_response(resp.status_code)
            attempt.retryable = 1 if retryable else 0
            self._mark_retry_or_fail(db, task, attempt, attempt_no, error, retryable=retryable)
        except Exception as exc:
            db.rollback()
            task = db.query(SchedulerTask).filter(SchedulerTask.id == task_id).first()
            if not task:
                return
            if not task.trace_id:
                task.trace_id = str(uuid.uuid4())
                db.commit()
            trace_id = task.trace_id
            retryable = self._is_retryable_exception(exc)
            attempt = (
                db.query(SchedulerTaskAttempt)
                .filter(SchedulerTaskAttempt.task_id == task.id)
                .order_by(SchedulerTaskAttempt.attempt_no.desc(), SchedulerTaskAttempt.id.desc())
                .first()
            )
            if not attempt:
                attempt = SchedulerTaskAttempt(
                    task_id=task.id,
                    attempt_no=int(task.attempt_count) + 1,
                    agent=task.last_agent,
                    trace_id=trace_id,
                    status=TaskStatus.RUNNING,
                    started_at=_utcnow(),
                )
                db.add(attempt)
                db.commit()
                db.refresh(attempt)

            attempt.trace_id = trace_id
            attempt.retryable = 1 if retryable else 0
            self._mark_retry_or_fail(db, task, attempt, int(attempt.attempt_no), str(exc), retryable=retryable)
        finally:
            db.close()

    def _execute_local_linear_pipeline(
        self,
        *,
        db: Session,
        task: SchedulerTask,
        attempt_no: int,
        payload: dict[str, Any],
    ) -> None:
        trace_id = task.trace_id or str(uuid.uuid4())
        attempt = SchedulerTaskAttempt(
            task_id=task.id,
            attempt_no=attempt_no,
            agent="local-linear-pipeline",
            trace_id=trace_id,
            status=TaskStatus.RUNNING,
            started_at=_utcnow(),
            request_url="local://workflow_engine/pipeline/linear",
            request_json=json.dumps(payload, ensure_ascii=False)[:20000],
        )
        db.add(attempt)
        task.last_agent = "local-linear-pipeline"
        task.updated_at = _utcnow()
        self._append_event(
            db,
            task_id=task.id,
            trace_id=trace_id,
            event_type="ATTEMPT_STARTED",
            from_status=TaskStatus.RUNNING,
            to_status=TaskStatus.RUNNING,
            attempt_no=attempt_no,
            message="executing local linear pipeline",
        )
        db.commit()
        db.refresh(attempt)

        try:
            from apps.workflow_engine.pipeline.linear_pipeline import LinearPipelineRunner, LinearPipelineSpec
            from apps.workflow_engine.pipeline.payloads import LinearPipelinePayload
            from apps.workflow_engine.registry.bootstrap import build_default_registry
            from apps.workflow_engine.registry.static_registry import registry

            if not self._registry_built:
                build_default_registry()
                self._registry_built = True

            parsed = LinearPipelinePayload.from_dict(payload)
            parsed.process_context.run_id = parsed.process_context.run_id or task.id
            runner = LinearPipelineRunner(registry)
            spec = LinearPipelineSpec(
                fetcher_name=parsed.fetcher_name,
                processor_name=parsed.processor_name,
                publisher_name=parsed.publisher_name,
                fetch_request=parsed.fetch_request,
                process_context=parsed.process_context,
                publish_target=parsed.publish_target,
            )
            result_obj = asyncio.run(runner.run(spec))

            now = _utcnow()
            attempt.status = TaskStatus.SUCCEEDED
            attempt.finished_at = now
            attempt.response_text = json.dumps(result_obj, ensure_ascii=False)[:20000]
            task.status = TaskStatus.SUCCEEDED
            task.attempt_count = attempt_no
            task.result_json = json.dumps({"items": result_obj}, ensure_ascii=False)
            task.last_error = None
            task.next_run_at = None
            task.updated_at = now
            self._append_log(
                db,
                task_id=task.id,
                trace_id=trace_id,
                level="INFO",
                message=f"local linear pipeline succeeded on attempt {attempt_no}",
            )
            self._append_event(
                db,
                task_id=task.id,
                trace_id=trace_id,
                event_type="ATTEMPT_FINISHED",
                from_status=TaskStatus.RUNNING,
                to_status=TaskStatus.SUCCEEDED,
                attempt_no=attempt_no,
                message=None,
            )
            self._append_event(
                db,
                task_id=task.id,
                trace_id=trace_id,
                event_type="STATUS_CHANGED",
                from_status=TaskStatus.RUNNING,
                to_status=TaskStatus.SUCCEEDED,
                attempt_no=attempt_no,
                message=None,
            )
            db.commit()
        except Exception as exc:
            attempt.retryable = 0
            self._mark_retry_or_fail(
                db,
                task,
                attempt,
                attempt_no,
                str(exc),
                retryable=False,
            )

    def _execute_content_workflow(
        self,
        *,
        db: Session,
        task: SchedulerTask,
        attempt_no: int,
        payload: dict[str, Any],
    ) -> None:
        trace_id = task.trace_id or str(uuid.uuid4())
        attempt = SchedulerTaskAttempt(
            task_id=task.id,
            attempt_no=attempt_no,
            agent="workflow_engine",
            trace_id=trace_id,
            status=TaskStatus.RUNNING,
            started_at=_utcnow(),
            request_url="local://workflow_engine/workflow/run",
            request_json=json.dumps(payload, ensure_ascii=False)[:20000],
        )
        db.add(attempt)
        task.last_agent = "workflow_engine"
        task.updated_at = _utcnow()
        self._append_event(
            db,
            task_id=task.id,
            trace_id=trace_id,
            event_type="ATTEMPT_STARTED",
            from_status=TaskStatus.RUNNING,
            to_status=TaskStatus.RUNNING,
            attempt_no=attempt_no,
            message="executing workflow_engine DAG workflow",
        )
        db.commit()
        db.refresh(attempt)

        try:
            client_cls = _load_content_domain_client()
            client = client_cls()
            result = asyncio.run(
                client.run_content_workflow(
                    {
                        **payload,
                        "run_id": trace_id,
                    }
                )
            )
            result_obj = result.to_dict()

            now = _utcnow()
            attempt.status = TaskStatus.SUCCEEDED
            attempt.finished_at = now
            attempt.response_text = json.dumps(result_obj, ensure_ascii=False)[:20000]
            task.status = TaskStatus.SUCCEEDED
            task.attempt_count = attempt_no
            task.result_json = json.dumps(result_obj, ensure_ascii=False)
            task.last_error = None
            task.next_run_at = None
            task.updated_at = now
            self._append_log(
                db,
                task_id=task.id,
                trace_id=trace_id,
                level="INFO",
                message=f"workflow_engine DAG workflow succeeded on attempt {attempt_no}",
            )
            self._append_event(
                db,
                task_id=task.id,
                trace_id=trace_id,
                event_type="ATTEMPT_FINISHED",
                from_status=TaskStatus.RUNNING,
                to_status=TaskStatus.SUCCEEDED,
                attempt_no=attempt_no,
                message=None,
            )
            self._append_event(
                db,
                task_id=task.id,
                trace_id=trace_id,
                event_type="STATUS_CHANGED",
                from_status=TaskStatus.RUNNING,
                to_status=TaskStatus.SUCCEEDED,
                attempt_no=attempt_no,
                message=None,
            )
            db.commit()
        except Exception as exc:
            attempt.retryable = 0
            self._mark_retry_or_fail(
                db,
                task,
                attempt,
                attempt_no,
                str(exc),
                retryable=False,
            )

    def _execute_local_fetch_batch(
        self,
        *,
        db: Session,
        task: SchedulerTask,
        attempt_no: int,
        payload: dict[str, Any],
    ) -> None:
        trace_id = task.trace_id or str(uuid.uuid4())
        attempt = SchedulerTaskAttempt(
            task_id=task.id,
            attempt_no=attempt_no,
            agent="local-fetch-batch",
            trace_id=trace_id,
            status=TaskStatus.RUNNING,
            started_at=_utcnow(),
            request_url="local://fetcher_engine/fetch_batch",
            request_json=json.dumps(payload, ensure_ascii=False)[:20000],
        )
        db.add(attempt)
        task.last_agent = "local-fetch-batch"
        task.updated_at = _utcnow()
        self._append_event(
            db,
            task_id=task.id,
            trace_id=trace_id,
            event_type="ATTEMPT_STARTED",
            from_status=TaskStatus.RUNNING,
            to_status=TaskStatus.RUNNING,
            attempt_no=attempt_no,
            message="executing local fetch batch",
        )
        db.commit()
        db.refresh(attempt)

        try:
            result_obj = asyncio.run(self._run_local_fetch_batch(db=db, task=task, payload=payload))
            now = _utcnow()
            attempt.status = TaskStatus.SUCCEEDED
            attempt.finished_at = now
            attempt.response_text = json.dumps(result_obj, ensure_ascii=False)[:20000]
            task.status = TaskStatus.SUCCEEDED
            task.attempt_count = attempt_no
            task.result_json = json.dumps(result_obj, ensure_ascii=False)
            task.last_error = None
            task.next_run_at = None
            task.updated_at = now
            self._append_log(
                db,
                task_id=task.id,
                trace_id=trace_id,
                level="INFO",
                message=f"local fetch batch succeeded on attempt {attempt_no}",
            )
            self._append_event(
                db,
                task_id=task.id,
                trace_id=trace_id,
                event_type="ATTEMPT_FINISHED",
                from_status=TaskStatus.RUNNING,
                to_status=TaskStatus.SUCCEEDED,
                attempt_no=attempt_no,
                message=None,
            )
            self._append_event(
                db,
                task_id=task.id,
                trace_id=trace_id,
                event_type="STATUS_CHANGED",
                from_status=TaskStatus.RUNNING,
                to_status=TaskStatus.SUCCEEDED,
                attempt_no=attempt_no,
                message=None,
            )
            db.commit()
        except Exception as exc:
            attempt.retryable = 0
            self._mark_retry_or_fail(
                db,
                task,
                attempt,
                attempt_no,
                str(exc),
                retryable=False,
            )

    async def _run_local_fetch_batch(
        self,
        *,
        db: Session,
        task: SchedulerTask,
        payload: dict[str, Any],
    ) -> dict[str, Any]:
        (
            platform_models,
            create_content_item,
            get_content_item_by_source,
            update_content_item,
            FetchBatchRequest,
            FetchService,
        ) = _load_platform_fetch_dependencies()
        platform_session_local, platform_models, dispatch_fetch_alerts = _load_platform_source_dependencies()

        source_config_id = int(payload.get("source_config_id") or 0)
        if source_config_id <= 0:
            raise ValueError("source_config_id is required")

        # 使用平台数据库 session 查询 SourceConfig（调度器 DB 没有这些表）
        platform_db: Session = platform_session_local()
        try:
            source = platform_db.query(platform_models.SourceConfig).filter(
                platform_models.SourceConfig.id == source_config_id
            ).first()
        finally:
            platform_db.close()

        if source is None:
            raise ValueError(f"source config not found: {source_config_id}")
        if not bool(source.enabled):
            raise ValueError(f"source config disabled: {source_config_id}")

        source_type = str(payload.get("source_type") or source.source_type or "").strip()
        if not source_type:
            raise ValueError("source_type is required")

        request_options = payload.get("config")
        if not isinstance(request_options, dict):
            request_options = {}

        source_repo = self._build_platform_fetch_source_repo(
            platform_models=platform_models,
            create_content_item=create_content_item,
            get_content_item_by_source=get_content_item_by_source,
            update_content_item=update_content_item,
            source=source,
            payload=payload,
        )
        service = FetchService(db, source_repo)
        result = await service.run_sources(
            FetchBatchRequest(
                run_id=task.id,
                sources=[source_type],
                subscription_ids=[source.id],
                lookback_hours=int(payload.get("lookback_hours") or source.lookback_hours or 24),
                limit_per_source=int(payload.get("limit") or source.item_limit or 20),
                options=request_options,
            )
        )
        serialized_items = list(result.items)
        matched_items = list(result.matched_items)

        fetch_run = (
            db.query(platform_models.FetchRun)
            .filter(platform_models.FetchRun.task_id == task.id)
            .order_by(platform_models.FetchRun.id.desc())
            .first()
        )
        if fetch_run is not None:
            fetch_run.status = "success" if not result.errors else "failure"
            fetch_run.trace_id = task.trace_id
            fetch_run.fetched_count = int(result.stats.total_fetched)
            fetch_run.inserted_count = int(result.stats.total_inserted)
            fetch_run.deduped_count = int(result.stats.total_deduped)
            fetch_run.finished_at = _utcnow()
            fetch_run.error_message = result.errors[0].error if result.errors else None
            db.add(fetch_run)
            for item in matched_items:
                content_item = get_content_item_by_source(db, item["source_type"], item["source_id"])
                if content_item is not None:
                    content_item.fetch_run_id = fetch_run.id
                    db.add(content_item)

        alert_payloads = dispatch_fetch_alerts(
            db,
            source=source,
            fetch_run=fetch_run,
            task_result=result.model_dump(),
            append_log=lambda level, message: self._append_log(
                db,
                task_id=task.id,
                trace_id=task.trace_id,
                level=level,
                message=message,
            ),
        )
        _record_fetch_metrics(
            source_type=source_type,
            status="failure" if result.errors else "success",
            fetched_count=int(result.stats.total_fetched),
            inserted_count=int(result.stats.total_inserted),
            invalid_count=int(result.stats.total_invalid),
        )
        db.commit()
        if result.stats.sources_failed > 0 or result.errors:
            first_error = result.errors[0].error if result.errors else "fetch batch failed"
            raise RuntimeError(first_error)
        return {
            "run_id": task.id,
            "items": serialized_items,
            "matched_items": matched_items,
            "fetched_count": int(result.stats.total_fetched),
            "inserted_count": int(result.stats.total_inserted),
            "deduped_count": int(result.stats.total_deduped),
            "stats": result.stats.model_dump(),
            "errors": [error.model_dump() for error in result.errors],
            "validation_issues": [issue.model_dump() for issue in result.validation_issues],
            "source_stats": [stat.model_dump() for stat in result.source_stats],
            "checkpoints": result.checkpoints,
            "alerts": alert_payloads or [alert.model_dump() for alert in result.alerts],
        }

    def _build_platform_fetch_source_repo(
        self,
        *,
        platform_models: Any,
        create_content_item: Any,
        get_content_item_by_source: Any,
        update_content_item: Any,
        source: Any,
        payload: dict[str, Any],
    ) -> Any:
        del get_content_item_by_source
        del update_content_item

        class _PlatformFetchSourceRepo:
            ContentItem = platform_models.ContentItem
            SourceSubscription = platform_models.SourceConfig

            @staticmethod
            def create_content_item(db: Session, **kwargs: Any):
                normalized = dict(kwargs)
                normalized.setdefault("source_config_id", source.id)
                normalized.setdefault("processed_content", None)
                normalized.setdefault("publish_target", None)
                normalized.setdefault("publish_status", "pending")
                normalized.setdefault("pipeline_status", "fetched")
                normalized.setdefault("review_status", "pending")
                normalized.setdefault("digest_included", False)
                normalized.setdefault("error_message", None)
                return create_content_item(db, **normalized)

            @staticmethod
            def load_subscriptions(db: Session, *, sources: list[str], subscription_ids: list[int]) -> list[Any]:
                query = db.query(platform_models.SourceConfig).filter(platform_models.SourceConfig.enabled.is_(True))
                if subscription_ids:
                    query = query.filter(platform_models.SourceConfig.id.in_(subscription_ids))
                if sources:
                    query = query.filter(platform_models.SourceConfig.source_type.in_(sources))
                return list(query.order_by(platform_models.SourceConfig.id.asc()).all())

            @staticmethod
            def update_cursor(db: Session, subscription: Any, cursor_value: str) -> None:
                real = db.query(platform_models.SourceConfig).filter(
                    platform_models.SourceConfig.id == subscription.id
                ).first()
                if real is not None:
                    real.last_cursor = cursor_value
                    real.last_run_at = _utcnow()
                    db.add(real)
                    db.commit()

        def _feed_url(subscription: Any) -> str | None:
            # 优先从 config_json 读取 feed_url / url
            raw_config = str(getattr(subscription, "config_json", "") or "").strip()
            config_data: dict[str, Any] = {}
            if raw_config:
                try:
                    parsed = json.loads(raw_config)
                    if isinstance(parsed, dict):
                        config_data = parsed
                except Exception:
                    config_data = {}
            feed_url = str(config_data.get("feed_url") or config_data.get("url") or "").strip()
            if feed_url:
                return feed_url
            # fallback：从 channels 字段提取首个 URL（适用于 API 创建的 SourceConfig）
            channels_raw = str(getattr(subscription, "channels", "") or "").strip()
            if channels_raw:
                try:
                    parsed_channels = json.loads(channels_raw)
                    if isinstance(parsed_channels, list) and parsed_channels:
                        first = str(parsed_channels[0]).strip()
                        if first:
                            return first
                except Exception:
                    pass
            return None

        original_loader = _PlatformFetchSourceRepo.load_subscriptions

        @staticmethod
        def _load_subscriptions_with_mapping(db: Session, *, sources: list[str], subscription_ids: list[int]) -> list[Any]:
            rows = original_loader(db, sources=sources, subscription_ids=subscription_ids)
            mapped: list[Any] = []
            for row in rows:
                account_identifier = None
                channels = getattr(row, "channels", None)
                if isinstance(channels, str) and channels.strip():
                    try:
                        parsed_channels = json.loads(channels)
                        if isinstance(parsed_channels, list) and parsed_channels:
                            first_channel = parsed_channels[0]
                            if isinstance(first_channel, str) and first_channel.strip():
                                account_identifier = first_channel.strip()
                    except Exception:
                        account_identifier = None
                config_payload = payload.get("config")
                config_data = config_payload if isinstance(config_payload, dict) else {}
                if row.source_type == "reddit":
                    account_identifier = str(
                        config_data.get("subreddit")
                        or account_identifier
                        or row.name
                    ).strip()
                mapped.append(
                    type(
                        "PlatformSourceSubscription",
                        (),
                        {
                            "id": row.id,
                            "source_type": row.source_type,
                            "source_name": row.name,
                            "account_identifier": account_identifier,
                            "feed_url": _feed_url(row),
                            "enabled": row.enabled,
                            "default_tags": None,
                            "last_cursor": row.last_cursor,
                        },
                    )()
                )
            return mapped

        _PlatformFetchSourceRepo.load_subscriptions = _load_subscriptions_with_mapping
        return _PlatformFetchSourceRepo

    def _execute_scheduled_radar(
        self,
        *,
        db: Session,
        task: SchedulerTask,
        attempt_no: int,
        payload: dict[str, Any],
    ) -> None:
        trace_id = task.trace_id or str(uuid.uuid4())
        attempt = SchedulerTaskAttempt(
            task_id=task.id,
            attempt_no=attempt_no,
            agent="scheduler-radar",
            trace_id=trace_id,
            status=TaskStatus.RUNNING,
            started_at=_utcnow(),
            request_url="local://workflow_engine/radar_pipeline",
            request_json=json.dumps(payload, ensure_ascii=False)[:20000],
        )
        db.add(attempt)
        task.last_agent = "scheduler-radar"
        task.updated_at = _utcnow()
        self._append_event(
            db,
            task_id=task.id,
            trace_id=trace_id,
            event_type="ATTEMPT_STARTED",
            from_status=TaskStatus.RUNNING,
            to_status=TaskStatus.RUNNING,
            attempt_no=attempt_no,
            message="executing scheduled radar pipeline",
        )
        db.commit()
        db.refresh(attempt)

        try:
            client_cls = _load_content_domain_client()
            client = client_cls()
            result = asyncio.run(
                client.run_content_radar(
                    {
                        **payload,
                        "run_id": trace_id,
                        "trigger_type": str(payload.get("trigger_type") or "scheduled"),
                    }
                )
            )
            result_obj = result.to_dict()
            now = _utcnow()
            attempt.status = TaskStatus.SUCCEEDED
            attempt.finished_at = now
            attempt.response_text = json.dumps(result_obj, ensure_ascii=False)[:20000]
            task.status = TaskStatus.SUCCEEDED
            task.attempt_count = attempt_no
            task.result_json = json.dumps(result_obj, ensure_ascii=False)
            task.last_error = None
            task.next_run_at = None
            task.updated_at = now
            self._append_log(
                db,
                task_id=task.id,
                trace_id=trace_id,
                level="INFO",
                message=f"scheduled radar pipeline succeeded on attempt {attempt_no}",
            )
            self._append_event(
                db,
                task_id=task.id,
                trace_id=trace_id,
                event_type="ATTEMPT_FINISHED",
                from_status=TaskStatus.RUNNING,
                to_status=TaskStatus.SUCCEEDED,
                attempt_no=attempt_no,
                message=None,
            )
            self._append_event(
                db,
                task_id=task.id,
                trace_id=trace_id,
                event_type="STATUS_CHANGED",
                from_status=TaskStatus.RUNNING,
                to_status=TaskStatus.SUCCEEDED,
                attempt_no=attempt_no,
                message=None,
            )
            db.commit()
        except Exception as exc:
            attempt.retryable = 0
            self._mark_retry_or_fail(db, task, attempt, attempt_no, str(exc), retryable=False)

    def _execute_scheduled_daily_digest(
        self,
        *,
        db: Session,
        task: SchedulerTask,
        attempt_no: int,
        payload: dict[str, Any],
    ) -> None:
        trace_id = task.trace_id or str(uuid.uuid4())
        attempt = SchedulerTaskAttempt(
            task_id=task.id,
            attempt_no=attempt_no,
            agent="scheduler-daily-digest",
            trace_id=trace_id,
            status=TaskStatus.RUNNING,
            started_at=_utcnow(),
            request_url="local://platform/digest_service",
            request_json=json.dumps(payload, ensure_ascii=False)[:20000],
        )
        db.add(attempt)
        task.last_agent = "scheduler-daily-digest"
        task.updated_at = _utcnow()
        self._append_event(
            db,
            task_id=task.id,
            trace_id=trace_id,
            event_type="ATTEMPT_STARTED",
            from_status=TaskStatus.RUNNING,
            to_status=TaskStatus.RUNNING,
            attempt_no=attempt_no,
            message="executing scheduled daily digest",
        )
        db.commit()
        db.refresh(attempt)

        try:
            client_cls = _load_content_domain_client()
            client = client_cls()
            result = asyncio.run(
                client.run_daily_digest(
                    {
                        **payload,
                        "run_id": trace_id,
                    }
                )
            )
            result_obj = result.to_dict()
            now = _utcnow()
            attempt.status = TaskStatus.SUCCEEDED
            attempt.finished_at = now
            attempt.response_text = json.dumps(result_obj, ensure_ascii=False)[:20000]
            task.status = TaskStatus.SUCCEEDED
            task.attempt_count = attempt_no
            task.result_json = json.dumps(result_obj, ensure_ascii=False)
            task.last_error = None
            task.next_run_at = None
            task.updated_at = now
            self._append_log(
                db,
                task_id=task.id,
                trace_id=trace_id,
                level="INFO",
                message=f"scheduled daily digest succeeded on attempt {attempt_no}",
            )
            self._append_event(
                db,
                task_id=task.id,
                trace_id=trace_id,
                event_type="ATTEMPT_FINISHED",
                from_status=TaskStatus.RUNNING,
                to_status=TaskStatus.SUCCEEDED,
                attempt_no=attempt_no,
                message=None,
            )
            self._append_event(
                db,
                task_id=task.id,
                trace_id=trace_id,
                event_type="STATUS_CHANGED",
                from_status=TaskStatus.RUNNING,
                to_status=TaskStatus.SUCCEEDED,
                attempt_no=attempt_no,
                message=None,
            )
            db.commit()
        except Exception as exc:
            attempt.retryable = 0
            self._mark_retry_or_fail(db, task, attempt, attempt_no, str(exc), retryable=False)

    def _execute_publish_approved_content(
        self,
        *,
        db: Session,
        task: SchedulerTask,
        attempt_no: int,
        payload: dict[str, Any],
    ) -> None:
        trace_id = task.trace_id or str(uuid.uuid4())
        attempt = SchedulerTaskAttempt(
            task_id=task.id,
            attempt_no=attempt_no,
            agent="content-domain-publish",
            trace_id=trace_id,
            status=TaskStatus.RUNNING,
            started_at=_utcnow(),
            request_url="local://content_domain/publish_approved_content",
            request_json=json.dumps(payload, ensure_ascii=False)[:20000],
        )
        db.add(attempt)
        task.last_agent = "content-domain-publish"
        task.updated_at = _utcnow()
        self._append_event(
            db,
            task_id=task.id,
            trace_id=trace_id,
            event_type="ATTEMPT_STARTED",
            from_status=TaskStatus.RUNNING,
            to_status=TaskStatus.RUNNING,
            attempt_no=attempt_no,
            message="executing approved content publish",
        )
        db.commit()
        db.refresh(attempt)

        try:
            client_cls = _load_content_domain_client()
            client = client_cls()
            result = asyncio.run(
                client.publish_approved_content(
                    {
                        **payload,
                        "run_id": trace_id,
                    }
                )
            )
            result_obj = result.to_dict()
            now = _utcnow()
            attempt.status = TaskStatus.SUCCEEDED
            attempt.finished_at = now
            attempt.response_text = json.dumps(result_obj, ensure_ascii=False)[:20000]
            task.status = TaskStatus.SUCCEEDED
            task.attempt_count = attempt_no
            task.result_json = json.dumps(result_obj, ensure_ascii=False)
            task.last_error = None
            task.next_run_at = None
            task.updated_at = now
            self._append_log(
                db,
                task_id=task.id,
                trace_id=trace_id,
                level="INFO",
                message=f"approved content publish succeeded on attempt {attempt_no}",
            )
            self._append_event(
                db,
                task_id=task.id,
                trace_id=trace_id,
                event_type="ATTEMPT_FINISHED",
                from_status=TaskStatus.RUNNING,
                to_status=TaskStatus.SUCCEEDED,
                attempt_no=attempt_no,
                message=None,
            )
            self._append_event(
                db,
                task_id=task.id,
                trace_id=trace_id,
                event_type="STATUS_CHANGED",
                from_status=TaskStatus.RUNNING,
                to_status=TaskStatus.SUCCEEDED,
                attempt_no=attempt_no,
                message=None,
            )
            db.commit()
        except Exception as exc:
            attempt.retryable = 0
            self._mark_retry_or_fail(db, task, attempt, attempt_no, str(exc), retryable=False)

    def _mark_failed(
        self,
        db: Session,
        task: SchedulerTask,
        attempt: SchedulerTaskAttempt,
        error: str,
    ) -> None:
        now = _utcnow()
        attempt.status = TaskStatus.FAILED
        attempt.error = error
        attempt.finished_at = now
        attempt.retryable = 0
        task.status = TaskStatus.FAILED
        task.attempt_count = attempt.attempt_no
        task.last_error = error
        task.next_run_at = None
        task.updated_at = now
        trace_id = task.trace_id or attempt.trace_id
        self._append_log(db, task_id=task.id, trace_id=trace_id, level="ERROR", message=error)
        self._append_event(
            db,
            task_id=task.id,
            trace_id=trace_id,
            event_type="ATTEMPT_FINISHED",
            from_status=TaskStatus.RUNNING,
            to_status=TaskStatus.FAILED,
            attempt_no=attempt.attempt_no,
            message=error,
        )
        self._append_event(
            db,
            task_id=task.id,
            trace_id=trace_id,
            event_type="STATUS_CHANGED",
            from_status=TaskStatus.RUNNING,
            to_status=TaskStatus.FAILED,
            attempt_no=attempt.attempt_no,
            message=error,
        )
        db.commit()

    def _mark_retry_or_fail(
        self,
        db: Session,
        task: SchedulerTask,
        attempt: SchedulerTaskAttempt,
        attempt_no: int,
        error: str,
        *,
        retryable: bool,
    ) -> None:
        max_attempts = int(task.max_retries) + 1
        now = _utcnow()
        trace_id = task.trace_id or attempt.trace_id

        try:
            db.refresh(task)
        except Exception:
            pass

        self._append_event(
            db,
            task_id=task.id,
            trace_id=trace_id,
            event_type="ATTEMPT_FINISHED",
            from_status=TaskStatus.RUNNING,
            to_status=TaskStatus.FAILED,
            attempt_no=attempt_no,
            message=error,
        )

        attempt.status = TaskStatus.FAILED
        attempt.error = error
        attempt.finished_at = now
        task.attempt_count = attempt_no
        task.last_error = error
        task.updated_at = now

        if task.cancel_requested:
            task.status = TaskStatus.CANCELED
            task.next_run_at = None
            self._append_log(
                db,
                task_id=task.id,
                trace_id=trace_id,
                level="INFO",
                message="canceled after failure",
            )
            self._append_event(
                db,
                task_id=task.id,
                trace_id=trace_id,
                event_type="STATUS_CHANGED",
                from_status=TaskStatus.RUNNING,
                to_status=TaskStatus.CANCELED,
                attempt_no=attempt_no,
                message="canceled after failure",
            )
            db.commit()
            return

        if retryable and attempt_no < max_attempts:
            delay = float(task.retry_delay_seconds)
            task.status = TaskStatus.PENDING
            task.next_run_at = now + timedelta(seconds=max(0.0, delay))
            self._append_log(
                db,
                task_id=task.id,
                trace_id=trace_id,
                level="WARN",
                message=f"failed attempt {attempt_no}, retry scheduled",
            )
            self._append_event(
                db,
                task_id=task.id,
                trace_id=trace_id,
                event_type="STATUS_CHANGED",
                from_status=TaskStatus.RUNNING,
                to_status=TaskStatus.PENDING,
                attempt_no=attempt_no,
                message="retry scheduled",
            )
            db.commit()
            return

        task.status = TaskStatus.FAILED
        task.next_run_at = None
        self._append_log(
            db,
            task_id=task.id,
            trace_id=trace_id,
            level="ERROR",
            message=f"failed after {attempt_no} attempts",
        )
        self._append_event(
            db,
            task_id=task.id,
            trace_id=trace_id,
            event_type="STATUS_CHANGED",
            from_status=TaskStatus.RUNNING,
            to_status=TaskStatus.FAILED,
            attempt_no=attempt_no,
            message="not retryable" if not retryable else "retries exhausted",
        )
        db.commit()

    def _append_event(
        self,
        db: Session,
        *,
        task_id: str,
        trace_id: str | None,
        event_type: str,
        from_status: str | None,
        to_status: str | None,
        attempt_no: int | None,
        message: str | None,
    ) -> None:
        db.add(
            SchedulerTaskEvent(
                task_id=task_id,
                trace_id=trace_id,
                event_type=event_type,
                from_status=from_status,
                to_status=to_status,
                attempt_no=attempt_no,
                message=message,
            )
        )

    def _append_log(
        self,
        db: Session,
        *,
        task_id: str,
        trace_id: str | None,
        level: str,
        message: str,
    ) -> None:
        db.add(SchedulerTaskLog(task_id=task_id, trace_id=trace_id, level=level, message=message))

    def _is_retryable_response(self, status_code: int) -> bool:
        return 500 <= int(status_code) <= 599

    def _is_retryable_exception(self, exc: Exception) -> bool:
        if isinstance(exc, (httpx.TimeoutException, httpx.NetworkError, httpx.TransportError)):
            return True
        name = exc.__class__.__name__.lower()
        return "timeout" in name or "connect" in name

    def _safe_json_loads(self, raw: str) -> Optional[dict[str, Any]]:
        try:
            obj = json.loads(raw or "{}")
            return obj if isinstance(obj, dict) else {"value": obj}
        except Exception:
            return None

