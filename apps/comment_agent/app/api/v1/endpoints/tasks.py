from fastapi import APIRouter, Depends
from sqlalchemy.orm import Session

from app.api.deps import get_db_session
from app.models.reply_task import ReplyTask
from app.schemas.admin import TaskDetailRead
from app.schemas.task import ReplyTaskRead
from app.services.review_service import get_task_detail_bundle

router = APIRouter()


@router.get("", response_model=list[ReplyTaskRead])
def list_tasks(
    site_id: int | None = None,
    status: str | None = None,
    db: Session = Depends(get_db_session),
) -> list[ReplyTask]:
    query = db.query(ReplyTask).order_by(ReplyTask.id.desc())
    if site_id is not None:
        query = query.filter(ReplyTask.site_id == site_id)
    if status is not None:
        query = query.filter(ReplyTask.task_status == status)
    return query.limit(100).all()


@router.get("/{task_id}", response_model=TaskDetailRead)
def get_task_detail(task_id: int, db: Session = Depends(get_db_session)) -> TaskDetailRead:
    task, replies, reviews = get_task_detail_bundle(db, task_id)
    return TaskDetailRead(task=task, replies=replies, reviews=reviews)
