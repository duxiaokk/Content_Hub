from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from app.api.deps import get_db_session
from app.models.agent import Agent
from app.models.site import Site
from app.schemas.agent import AgentCreate, AgentRead

router = APIRouter()


@router.post("", response_model=AgentRead, status_code=status.HTTP_201_CREATED)
def create_agent(payload: AgentCreate, db: Session = Depends(get_db_session)) -> Agent:
    site = db.query(Site).filter(Site.id == payload.site_id).first()
    if site is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="site not found")

    agent = Agent(
        site_id=payload.site_id,
        agent_code=payload.agent_code,
        agent_name=payload.agent_name,
        persona=payload.persona,
        tone=payload.tone,
        model_name=payload.model_name,
        auto_reply_enabled=int(payload.auto_reply_enabled),
        auto_article_comment_enabled=int(payload.auto_article_comment_enabled),
        moderation_enabled=int(payload.moderation_enabled),
        need_review=int(payload.need_review),
        status=payload.status,
    )
    db.add(agent)
    try:
        db.commit()
    except IntegrityError as exc:
        db.rollback()
        raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail="agent already exists") from exc
    db.refresh(agent)
    return agent


@router.get("", response_model=list[AgentRead])
def list_agents(site_id: int | None = None, db: Session = Depends(get_db_session)) -> list[Agent]:
    query = db.query(Agent).order_by(Agent.id.desc())
    if site_id is not None:
        query = query.filter(Agent.site_id == site_id)
    return query.all()
