from datetime import datetime

from fastapi import HTTPException, status
from sqlalchemy.orm import Session

from app.models.ai_reply import AIReply
from app.models.reply_task import ReplyTask
from app.models.review_queue import ReviewQueue
from app.schemas.review import ReviewActionRequest


def get_task_detail_bundle(db: Session, task_id: int) -> tuple[ReplyTask, list[AIReply], list[ReviewQueue]]:
    task = db.query(ReplyTask).filter(ReplyTask.id == task_id).first()
    if task is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="task not found")

    replies = db.query(AIReply).filter(AIReply.task_id == task_id).order_by(AIReply.id.desc()).all()
    reply_ids = [reply.id for reply in replies]
    reviews = []
    if reply_ids:
        reviews = (
            db.query(ReviewQueue)
            .filter(ReviewQueue.reply_id.in_(reply_ids))
            .order_by(ReviewQueue.id.desc())
            .all()
        )
    return task, replies, reviews


def approve_review(db: Session, review_id: int, payload: ReviewActionRequest) -> ReviewQueue:
    review = db.query(ReviewQueue).filter(ReviewQueue.id == review_id).first()
    if review is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="review not found")

    reply = db.query(AIReply).filter(AIReply.id == review.reply_id).first()
    if reply is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="reply not found")

    task = db.query(ReplyTask).filter(ReplyTask.id == reply.task_id).first()
    if task is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="task not found")

    now = datetime.utcnow()
    review.review_status = "approved"
    review.reviewer = payload.reviewer
    review.review_comment = payload.review_comment
    review.reviewed_at = now
    reply.publish_status = "approved"
    reply.moderation_result = "approved"
    task.task_status = "approved"
    task.finished_at = now
    db.commit()
    db.refresh(review)
    return review


def reject_review(db: Session, review_id: int, payload: ReviewActionRequest) -> ReviewQueue:
    review = db.query(ReviewQueue).filter(ReviewQueue.id == review_id).first()
    if review is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="review not found")

    reply = db.query(AIReply).filter(AIReply.id == review.reply_id).first()
    if reply is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="reply not found")

    task = db.query(ReplyTask).filter(ReplyTask.id == reply.task_id).first()
    if task is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="task not found")

    now = datetime.utcnow()
    review.review_status = "rejected"
    review.reviewer = payload.reviewer
    review.review_comment = payload.review_comment
    review.reviewed_at = now
    reply.publish_status = "rejected"
    reply.moderation_result = "rejected"
    task.task_status = "rejected"
    task.finished_at = now
    task.error_message = payload.review_comment or "review rejected"
    db.commit()
    db.refresh(review)
    return review
