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

from scheduler_center.config import scheduler_settings
from scheduler_center.database import SessionLocal
from scheduler_center.models import (
    SchedulerAgent,
    SchedulerTask,
    SchedulerTaskAttempt,
    SchedulerTaskEvent,
    SchedulerTaskLog,
)

from scheduler_center import _ensure_stdlib_platform
from workflow_engine.api.service import WorkflowEngineService
from workflow_engine.pipeline.linear_pipeline import LinearPipelineRunner, LinearPipelineSpec
from workflow_engine.pipeline.payloads import LinearPipelinePayload
from workflow_engine.registry.bootstrap import build_default_registry
from workflow_engine.registry.static_registry import registry

_ensure_stdlib_platform()


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
        self._executor = ThreadPoolExecutor(max_workers=scheduler_settings.scheduler_max_concurrency)
        self._running: dict[str, Future[Any]] = {}
        self._running_lock = threading.Lock()
        self._rr_lock = threading.Lock()
        self._rr_index = 0
        self._registry_built = False

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

    def _run(self) -> None:
        self._recover_running_tasks()
        while not self._stop_event.is_set():
            try:
                self._dispatch_once()
            except Exception:
                pass
            time.sleep(max(0.05, scheduler_settings.scheduler_poll_interval_seconds))

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

            if task.task_type == "content.pipeline.linear":
                self._execute_local_linear_pipeline(
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

        service = WorkflowEngineService()
        try:
            result_obj = asyncio.run(
                service.run_content_workflow(
                    workflow_name=str(payload.get("workflow_name") or "content.workflow.run"),
                    source_name=str(payload.get("source_name") or payload.get("fetcher_name") or "cnblogs"),
                    fetcher_name=str(payload.get("fetcher_name") or "cnblogs"),
                    processor_name=str(payload.get("processor_name") or "rewrite"),
                    publisher_name=str(payload.get("publisher_name") or "blog"),
                    lookback_hours=int(payload.get("lookback_hours") or 24),
                    limit=int(payload.get("limit") or 20),
                    options={
                        "fetch": dict(payload.get("fetch_options") or {}),
                        "process": dict(payload.get("process_options") or {}),
                        "publish": dict(payload.get("publish_options") or {}),
                    },
                    run_id=trace_id,
                )
            )

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

