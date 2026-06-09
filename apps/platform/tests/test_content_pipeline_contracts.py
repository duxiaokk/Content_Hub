from __future__ import annotations

from sqlalchemy import create_engine, inspect
from sqlalchemy.orm import Session

from models import ContentItem
from database import Base


def test_content_items_table_exists() -> None:
    engine = create_engine("sqlite:///:memory:", connect_args={"check_same_thread": False})
    Base.metadata.create_all(bind=engine)
    inspector = inspect(engine)

    assert "content_items" in inspector.get_table_names()


def test_content_item_crud_defaults() -> None:
    engine = create_engine("sqlite:///:memory:", connect_args={"check_same_thread": False})
    Base.metadata.create_all(bind=engine)

    with Session(bind=engine) as session:
        item = ContentItem(
            source_type="cnblogs",
            source_id="post-001",
            source_url="https://www.cnblogs.com/example/p/001.html",
            title="Example Post",
            raw_content="raw body",
        )
        session.add(item)
        session.commit()
        session.refresh(item)

        assert item.id is not None
        assert item.publish_status == "pending"
        assert item.pipeline_status == "fetched"
        assert item.created_at is not None
        assert item.updated_at is not None
