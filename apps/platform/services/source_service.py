from __future__ import annotations

import logging

from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from apps.platform.models import SourceSubscription
from schemas.source import SourceSubscriptionCreate, SourceSubscriptionUpdate

logger = logging.getLogger(__name__)


class SourceConflictError(ValueError):
    pass


class SourceNotFoundError(ValueError):
    pass


class SourceService:
    def __init__(self, db: Session) -> None:
        self.db = db

    def list_sources(self, enabled_only: bool = False) -> list[SourceSubscription]:
        query = self.db.query(SourceSubscription)
        if enabled_only:
            query = query.filter(SourceSubscription.enabled.is_(True))
        return query.order_by(SourceSubscription.id.desc()).all()

    def get_source(self, source_id: int) -> SourceSubscription:
        source = self.db.query(SourceSubscription).filter(SourceSubscription.id == source_id).first()
        if source is None:
            raise SourceNotFoundError(f"source not found: {source_id}")
        return source

    def create_source(self, data: SourceSubscriptionCreate) -> SourceSubscription:
        source = SourceSubscription(
            source_type=data.source_type,
            source_name=data.source_name,
            account_identifier=data.account_identifier,
            feed_url=data.feed_url,
            schedule_expression=data.schedule_expression,
            category=data.category,
            default_tags=data.default_tags,
            enabled=True,
        )
        self.db.add(source)
        return self._commit_with_conflict_handling(source)

    def update_source(self, source_id: int, data: SourceSubscriptionUpdate) -> SourceSubscription:
        source = self.get_source(source_id)
        updates = data.model_dump(exclude_unset=True)
        for field_name, field_value in updates.items():
            setattr(source, field_name, field_value)
        self.db.add(source)
        return self._commit_with_conflict_handling(source)

    def enable_source(self, source_id: int) -> SourceSubscription:
        source = self.get_source(source_id)
        source.enabled = True
        self.db.add(source)
        self.db.commit()
        self.db.refresh(source)
        return source

    def disable_source(self, source_id: int) -> SourceSubscription:
        source = self.get_source(source_id)
        source.enabled = False
        self.db.add(source)
        self.db.commit()
        self.db.refresh(source)
        return source

    def _commit_with_conflict_handling(self, source: SourceSubscription) -> SourceSubscription:
        try:
            self.db.commit()
        except IntegrityError as exc:
            self.db.rollback()
            logger.warning("source subscription conflict: %s", exc)
            raise SourceConflictError("source subscription already exists") from exc
        self.db.refresh(source)
        return source
