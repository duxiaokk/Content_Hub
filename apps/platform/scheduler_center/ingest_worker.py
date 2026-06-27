from __future__ import annotations

import time
from datetime import UTC, datetime
import json

from sqlalchemy.exc import IntegrityError

from scheduler_center.config import scheduler_settings
from scheduler_center.database import Base, engine, SessionLocal
from scheduler_center.dispatcher import TaskStatus
from scheduler_center.models import SchedulerTask, SchedulerTaskEvent
from scheduler_center.redis_queue import redis_submit_queue


def _utcnow() -> datetime:
    return datetime.now(UTC).replace(tzinfo=None)


def _append_event(db, *, task_id: str, trace_id: str | None) -> None:
    db.add(
        SchedulerTaskEvent(
            task_id=task_id,
            trace_id=trace_id,
            event_type="SUBMITTED",
            from_status=None,
            to_status=TaskStatus.PENDING,
            attempt_no=0,
            message="ingested_from_standard_redis_submit_path" if redis_submit_queue.enabled else None,
        )
    )


def _ingest_one(item: dict) -> None:
    task_id = str(item.get("task_id") or "")
    if not task_id:
        return
    trace_id = str(item.get("trace_id") or "") or None
    idempotency_key = str(item.get("idempotency_key") or "") or None
    task_type = str(item.get("task_type") or "").strip()
    payload = item.get("payload") if isinstance(item.get("payload"), dict) else {}
    max_retries = int(item.get("max_retries") or scheduler_settings.scheduler_default_max_retries)
    retry_delay = float(
        item.get("retry_delay_seconds") or scheduler_settings.scheduler_default_retry_delay_seconds
    )

    cached = redis_submit_queue.get_task(task_id)
    cancel_requested = 1 if cached and bool(cached.get("cancel_requested")) else 0
    status = TaskStatus.CANCELED if cancel_requested else TaskStatus.PENDING

    now = _utcnow()
    db = SessionLocal()
    try:
        task = SchedulerTask(
            id=task_id,
            idempotency_key=idempotency_key,
            trace_id=trace_id,
            task_type=task_type,
            payload_json=json.dumps(payload, ensure_ascii=False),
            status=status,
            cancel_requested=cancel_requested,
            max_retries=max_retries,
            retry_delay_seconds=retry_delay,
            attempt_count=0,
            next_run_at=None,
            created_at=now,
            updated_at=now,
        )
        db.add(task)
        _append_event(db, task_id=task_id, trace_id=trace_id)
        if cancel_requested:
            db.add(
                SchedulerTaskEvent(
                    task_id=task_id,
                    trace_id=trace_id,
                    event_type="CANCEL_REQUESTED",
                    from_status=TaskStatus.PENDING,
                    to_status=TaskStatus.CANCELED,
                    attempt_no=0,
                    message="canceled_before_ingest",
                )
            )
        db.commit()
    except IntegrityError:
        db.rollback()
    finally:
        db.close()


def main() -> int:
    if not redis_submit_queue.enabled:
        raise SystemExit(
            "standard redis submit path requires SCHEDULER_FAST_SUBMIT_ENABLED=true and SCHEDULER_REDIS_URL"
        )
    Base.metadata.create_all(bind=engine)
    while True:
        item = redis_submit_queue.dequeue(timeout_seconds=2)
        if not item:
            time.sleep(0.05)
            continue
        try:
            _ingest_one(item)
        except Exception:
            continue


if __name__ == "__main__":
    raise SystemExit(main())

