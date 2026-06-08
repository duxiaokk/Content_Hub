from datetime import datetime, timedelta
from uuid import uuid4

from fastapi import HTTPException, status
from sqlalchemy.orm import Session

from app.core.config import settings
from app.models.agent import Agent
from app.models.event_log import EventLog
from app.models.reply_task import ReplyTask
from app.models.site import Site
from app.schemas.event import EventRequest
from app.services.rule_engine import should_create_task
from app.services.signature import verify_hmac_signature


def accept_event(db: Session, payload: EventRequest, raw_body: bytes, header_signature: str | None) -> dict:
    site = db.query(Site).filter(Site.site_key == payload.site.id, Site.status == 1).first()
    if site is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="site not found")

    signature = header_signature or payload.signature
    if not verify_hmac_signature(raw_body, site.webhook_secret, signature):
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="invalid signature")

    event_id = build_event_id(payload)
    existing = db.query(EventLog).filter(EventLog.event_id == event_id).first()
    if existing is not None:
        return {"event_id": event_id, "task_id": None, "status": "duplicate"}

    event_log = EventLog(
        event_id=event_id,
        site_id=site.id,
        event_type=payload.event,
        payload_json=payload.model_dump(mode="json"),
        process_status="pending",
        received_at=datetime.utcnow(),
    )
    db.add(event_log)

    can_create, reason = should_create_task(db, payload, site.id)
    if not can_create:
        event_log.process_status = "skipped"
        event_log.error_message = reason
        db.commit()
        return {"event_id": event_id, "task_id": None, "status": reason}

    agent = pick_default_agent(db, site.id, payload.event)
    if agent is None:
        event_log.process_status = "skipped"
        event_log.error_message = "agent_not_found"
        db.commit()
        return {"event_id": event_id, "task_id": None, "status": "agent_not_found"}

    task = build_reply_task(payload, site.id, agent.id, event_id, reason)
    db.add(task)
    event_log.process_status = "queued"
    db.commit()
    db.refresh(task)
    return {"event_id": event_id, "task_id": task.id, "status": "queued"}


def build_event_id(payload: EventRequest) -> str:
    if payload.article and payload.comment:
        source = f"{payload.article.id}:{payload.comment.id}"
    elif payload.article:
        source = payload.article.id
    else:
        source = str(uuid4())
    return f"{payload.site.id}:{payload.event}:{source}:{payload.timestamp.isoformat()}"


def pick_default_agent(db: Session, site_id: int, event_type: str) -> Agent | None:
    query = db.query(Agent).filter(Agent.site_id == site_id, Agent.status == 1)
    if event_type == "article.published":
        query = query.filter(Agent.auto_article_comment_enabled == 1)
    else:
        query = query.filter(Agent.auto_reply_enabled == 1)
    return query.order_by(Agent.id.asc()).first()


def build_reply_task(
    payload: EventRequest,
    site_id: int,
    agent_id: int,
    event_id: str,
    trigger_reason: str,
) -> ReplyTask:
    article = payload.article
    comment = payload.comment
    if article is None:
        raise ValueError("article is required to create reply task")

    source_type = "comment" if comment else "article"
    source_id = comment.id if comment else article.id
    return ReplyTask(
        site_id=site_id,
        agent_id=agent_id,
        event_id=event_id,
        source_type=source_type,
        source_id=source_id,
        article_id=article.id,
        comment_id=comment.id if comment else None,
        parent_comment_id=comment.parent_id if comment else None,
        trigger_reason=trigger_reason,
        task_status="queued",
        scheduled_at=datetime.utcnow() + timedelta(seconds=settings.default_reply_delay_seconds),
    )
