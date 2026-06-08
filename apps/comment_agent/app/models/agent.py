from datetime import datetime

from sqlalchemy import DateTime, ForeignKey, Integer, String, Text, UniqueConstraint
from sqlalchemy.orm import Mapped, mapped_column

from app.core.db import Base


class Agent(Base):
    __tablename__ = "agents"
    __table_args__ = (UniqueConstraint("site_id", "agent_code", name="uk_site_agent_code"),)

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    site_id: Mapped[int] = mapped_column(Integer, ForeignKey("sites.id"), nullable=False, index=True)
    agent_code: Mapped[str] = mapped_column(String(64), nullable=False)
    agent_name: Mapped[str] = mapped_column(String(64), nullable=False)
    persona: Mapped[str] = mapped_column(Text, nullable=False)
    tone: Mapped[str] = mapped_column(String(64), nullable=False, default="friendly")
    model_name: Mapped[str] = mapped_column(String(128), nullable=False)
    auto_reply_enabled: Mapped[int] = mapped_column(Integer, nullable=False, default=1)
    auto_article_comment_enabled: Mapped[int] = mapped_column(Integer, nullable=False, default=1)
    moderation_enabled: Mapped[int] = mapped_column(Integer, nullable=False, default=1)
    need_review: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    status: Mapped[int] = mapped_column(Integer, nullable=False, default=1)
    created_at: Mapped[datetime] = mapped_column(DateTime, nullable=False, default=datetime.utcnow)
    updated_at: Mapped[datetime] = mapped_column(
        DateTime,
        nullable=False,
        default=datetime.utcnow,
        onupdate=datetime.utcnow,
    )
