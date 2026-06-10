from __future__ import annotations

import json
import os
from datetime import datetime, timezone
from pathlib import Path

from sqlalchemy import create_engine
from sqlalchemy.orm import Session

os.environ.setdefault("SECRET_KEY", "test-secret-key")

from database import Base
from models import FetchRun, SourceConfig
from services.console_service import sync_content_items_from_result


def test_sync_content_items_from_processed_path(tmp_path: Path) -> None:
    engine = create_engine("sqlite:///:memory:", connect_args={"check_same_thread": False})
    Base.metadata.create_all(bind=engine)

    processed_path = tmp_path / "processed.json"
    processed_path.write_text(
        json.dumps(
            [
                {
                    "dedup_key": "rss:1",
                    "source": "rss",
                    "title": "Example title",
                    "content": "Example content",
                    "link": "https://example.com/item-1",
                }
            ],
            ensure_ascii=False,
        ),
        encoding="utf-8",
    )

    with Session(bind=engine) as session:
        source = SourceConfig(
            name="rss-source",
            source_type="rss",
            enabled=True,
            lookback_hours=24,
            item_limit=20,
            dedup_window_hours=24,
        )
        session.add(source)
        session.commit()
        session.refresh(source)

        fetch_run = FetchRun(
            source_config_id=source.id,
            trigger_mode="manual",
            status="success",
            started_at=datetime.now(timezone.utc),
        )
        session.add(fetch_run)
        session.commit()
        session.refresh(fetch_run)

        inserted = sync_content_items_from_result(
            session,
            fetch_run,
            source,
            {"processed_path": str(processed_path)},
        )

        assert inserted == 1
