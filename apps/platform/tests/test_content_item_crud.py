from __future__ import annotations

import os

from sqlalchemy import create_engine
from sqlalchemy.orm import Session

os.environ.setdefault("SECRET_KEY", "test-secret-key")

from database import Base
from crud.crud_content_item import create_content_item, get_content_item_by_source, update_content_item


def test_content_item_crud_roundtrip() -> None:
    engine = create_engine("sqlite:///:memory:", connect_args={"check_same_thread": False})
    Base.metadata.create_all(bind=engine)

    with Session(bind=engine) as session:
        created = create_content_item(
            session,
            source_type="cnblogs",
            source_id="abc-1",
            source_url="https://example.com/abc-1",
            title="Example",
            raw_content="raw",
            processed_content=None,
            publish_target=None,
            publish_status="pending",
            pipeline_status="fetched",
            error_message=None,
        )
        fetched = get_content_item_by_source(session, "cnblogs", "abc-1")

        assert created.id is not None
        assert fetched is not None
        assert fetched.title == "Example"

        updated = update_content_item(
            session,
            fetched,
            processed_content="processed",
            pipeline_status="processed",
            publish_status="published",
        )
        assert updated.processed_content == "processed"
        assert updated.pipeline_status == "processed"
        assert updated.publish_status == "published"
