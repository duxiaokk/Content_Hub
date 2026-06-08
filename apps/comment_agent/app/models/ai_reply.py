from datetime import datetime

from sqlalchemy import DateTime, Integer, String, Text
from sqlalchemy.orm import Mapped, mapped_column

from app.core.db import Base


class AIReply(Base):
    __tablename__ = "ai_replies"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    task_id: Mapped[int] = mapped_column(Integer, nullable=False, index=True)
    prompt_snapshot: Mapped[str] = mapped_column(Text, nullable=False)
    reply_content: Mapped[str] = mapped_column(Text, nullable=False)
    reply_summary: Mapped[str | None] = mapped_column(String(255), nullable=True)
    moderation_result: Mapped[str] = mapped_column(String(32), nullable=False, default="pending")
    moderation_reason: Mapped[str | None] = mapped_column(Text, nullable=True)
    publish_status: Mapped[str] = mapped_column(String(32), nullable=False, default="pending")
    published_comment_id: Mapped[str | None] = mapped_column(String(128), nullable=True)
    token_input: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    token_output: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    model_name: Mapped[str] = mapped_column(String(128), nullable=False)
    created_at: Mapped[datetime] = mapped_column(DateTime, nullable=False, default=datetime.utcnow)
    updated_at: Mapped[datetime] = mapped_column(
        DateTime,
        nullable=False,
        default=datetime.utcnow,
        onupdate=datetime.utcnow,
    )
