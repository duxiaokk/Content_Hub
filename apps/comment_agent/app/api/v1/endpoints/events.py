from fastapi import APIRouter, Depends, Header, Request
from sqlalchemy.orm import Session

from app.api.deps import get_db_session
from app.schemas.common import APIResponse
from app.schemas.event import EventRequest
from app.services.event_service import accept_event

router = APIRouter()


@router.post("/events", response_model=APIResponse)
async def receive_event(
    request: Request,
    x_webhook_signature: str | None = Header(default=None, alias="X-Webhook-Signature"),
    db: Session = Depends(get_db_session),
) -> APIResponse:
    raw_body = await request.body()
    payload = EventRequest.model_validate_json(raw_body)
    result = accept_event(db, payload, raw_body, x_webhook_signature)
    return APIResponse(message="accepted", data=result)
