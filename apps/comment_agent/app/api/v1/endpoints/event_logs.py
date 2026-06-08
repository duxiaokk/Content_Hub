from fastapi import APIRouter, Depends
from sqlalchemy.orm import Session

from app.api.deps import get_db_session
from app.models.event_log import EventLog
from app.schemas.event_log import EventLogRead

router = APIRouter()


@router.get("", response_model=list[EventLogRead])
def list_event_logs(
    site_id: int | None = None,
    event_type: str | None = None,
    process_status: str | None = None,
    db: Session = Depends(get_db_session),
) -> list[EventLog]:
    query = db.query(EventLog).order_by(EventLog.id.desc())
    if site_id is not None:
        query = query.filter(EventLog.site_id == site_id)
    if event_type is not None:
        query = query.filter(EventLog.event_type == event_type)
    if process_status is not None:
        query = query.filter(EventLog.process_status == process_status)
    return query.limit(100).all()
