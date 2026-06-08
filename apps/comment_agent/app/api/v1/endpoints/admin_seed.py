from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.orm import Session

from app.api.deps import get_db_session
from app.models.agent import Agent
from app.models.ai_reply import AIReply
from app.models.reply_task import ReplyTask
from app.models.review_queue import ReviewQueue
from app.schemas.common import APIResponse

router = APIRouter()


@router.post("/tasks/{task_id}/mock-review", response_model=APIResponse)
def create_mock_review(task_id: int, db: Session = Depends(get_db_session)) -> APIResponse:
    task = db.query(ReplyTask).filter(ReplyTask.id == task_id).first()
    if task is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="task not found")

    existing_review = (
        db.query(ReviewQueue)
        .join(AIReply, AIReply.id == ReviewQueue.reply_id)
        .filter(AIReply.task_id == task.id, ReviewQueue.review_status == "pending")
        .first()
    )
    if existing_review is not None:
        return APIResponse(message="already exists", data={"review_id": existing_review.id})

    agent = db.query(Agent).filter(Agent.id == task.agent_id).first()
    if agent is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="agent not found")

    reply = AIReply(
        task_id=task.id,
        prompt_snapshot="MVP mock prompt snapshot",
        reply_content="MVP mock AI reply. Replace this with real model output in the worker stage.",
        reply_summary="mock reply",
        moderation_result="pending_review",
        moderation_reason="manual_review_required",
        publish_status="waiting_review",
        model_name=agent.model_name,
    )
    db.add(reply)
    db.flush()

    review = ReviewQueue(
        reply_id=reply.id,
        review_status="pending",
    )
    db.add(review)
    task.task_status = "waiting_review"
    db.commit()
    return APIResponse(message="created", data={"reply_id": reply.id, "review_id": review.id})
