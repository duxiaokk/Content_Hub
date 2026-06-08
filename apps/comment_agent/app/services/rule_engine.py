from sqlalchemy import func
from sqlalchemy.orm import Session

from app.core.config import settings
from app.models.reply_task import ReplyTask
from app.schemas.event import EventRequest


SUPPORTED_TRIGGER_EVENTS = {"article.published", "comment.created"}


def should_create_task(db: Session, event: EventRequest, site_id: int) -> tuple[bool, str]:
    if event.event not in SUPPORTED_TRIGGER_EVENTS:
        return False, "unsupported_event"

    if event.event.startswith("article.") and event.article is None:
        return False, "missing_article"

    if event.event.startswith("comment.") and (event.article is None or event.comment is None):
        return False, "missing_comment_context"

    if event.article is None:
        return False, "missing_article"

    count = (
        db.query(func.count(ReplyTask.id))
        .filter(
            ReplyTask.site_id == site_id,
            ReplyTask.article_id == event.article.id,
            ReplyTask.task_status.in_(["pending", "queued", "running", "published"]),
        )
        .scalar()
    )
    if count >= settings.default_article_reply_limit:
        return False, "article_reply_limit"

    if event.event == "article.published":
        return True, "article_auto_comment"

    return True, "comment_created"
