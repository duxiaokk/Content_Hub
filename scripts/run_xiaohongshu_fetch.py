#!/usr/bin/env python3
"""小红书抓取直接执行脚本（绕过调度器）。

用法:
    cd D:\\Python\\content_hub
    .venv\\Scripts\\python.exe scripts/run_xiaohongshu_fetch.py [source_config_id]

如果没有提供 source_config_id，默认抓取第一个启用的 xiaohongshu 信源。
"""
from __future__ import annotations

import asyncio
import json
import os
import sys
import time
from datetime import datetime, timezone

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

from apps.fetcher_engine.api.models import FetchBatchRequest
from apps.fetcher_engine.api.service import FetchService
from apps.platform import models


def _utcnow() -> datetime:
    return datetime.now(timezone.utc)


def _get_db_session():
    """从项目默认 SQLite 路径创建会话。"""
    db_path = os.path.join(os.path.dirname(__file__), "..", "apps", "platform", "blog.db")
    db_path = os.path.abspath(db_path)
    engine = create_engine(f"sqlite:///{db_path}", echo=False)
    Session = sessionmaker(bind=engine)
    return Session()


def _create_fetch_run(db, source: models.SourceConfig) -> models.FetchRun:
    """创建 FetchRun 记录。"""
    fetch_run = models.FetchRun(
        source_config_id=source.id,
        trigger_mode="manual",
        status="running",
        task_id=None,
        trace_id=None,
        requested_by="direct_script",
        request_payload=json.dumps({"source_type": source.source_type, "source_name": source.name}),
        started_at=_utcnow(),
    )
    db.add(fetch_run)
    db.commit()
    db.refresh(fetch_run)
    return fetch_run


def _update_fetch_run(db, fetch_run: models.FetchRun, *, fetched: int, inserted: int, deduped: int, errors: list[str]) -> None:
    fetch_run.status = "success" if not errors else "partial_success"
    fetch_run.fetched_count = fetched
    fetch_run.inserted_count = inserted
    fetch_run.deduped_count = deduped
    fetch_run.error_message = "; ".join(errors) if errors else None
    fetch_run.finished_at = _utcnow()
    db.commit()


def _load_source_config(db, source_config_id: int | None) -> models.SourceConfig | None:
    if source_config_id:
        return db.query(models.SourceConfig).filter(models.SourceConfig.id == source_config_id).first()
    # 默认取第一个启用的 xiaohongshu 信源
    return (
        db.query(models.SourceConfig)
        .filter(models.SourceConfig.source_type == "xiaohongshu")
        .filter(models.SourceConfig.enabled.is_(True))
        .order_by(models.SourceConfig.id.asc())
        .first()
    )


class _DirectRepo:
    """直接读取数据库的简易 repo，供 FetchService 使用。"""
    ContentItem = models.ContentItem
    SourceSubscription = models.SourceConfig

    def __init__(self, db):
        self.db = db

    def create_content_item(self, db, **kwargs):
        item = models.ContentItem(**kwargs)
        db.add(item)
        db.commit()
        db.refresh(item)
        return item

    def get_content_item_by_source(self, db, source_type, source_id):
        return (
            db.query(models.ContentItem)
            .filter(models.ContentItem.source_type == source_type)
            .filter(models.ContentItem.source_id == source_id)
            .first()
        )

    def update_cursor(self, db, subscription, cursor_value):
        subscription.last_cursor = cursor_value
        subscription.last_run_at = _utcnow()
        db.add(subscription)
        db.commit()


async def run_fetch(source_config_id: int | None = None) -> None:
    db = _get_db_session()
    try:
        source = _load_source_config(db, source_config_id)
        if not source:
            print("未找到启用的 xiaohongshu 信源，请先在前端创建信源并配置 urls。")
            return

        print(f"信源: {source.name} (ID={source.id}, type={source.source_type})")
        config = json.loads(source.config_json or "{}")
        urls = config.get("urls", [])
        print(f"配置 URLs 数量: {len(urls)}")
        if not urls:
            print("⚠️ 配置中未设置 urls，无法抓取。请在前端编辑信源，配置 JSON 中填入 urls 列表。")
            return

        fetch_run = _create_fetch_run(db, source)
        print(f"创建 FetchRun: ID={fetch_run.id}")

        service = FetchService(db, _DirectRepo(db))

        request = FetchBatchRequest(
            run_id=f"direct-{fetch_run.id}",
            sources=["xiaohongshu"],
            subscription_ids=[source.id],
            lookback_hours=source.lookback_hours or 24,
            limit_per_source=source.item_limit or 20,
            options={},
        )

        started_at = time.perf_counter()
        result = await service.run_sources(request)
        elapsed_ms = round((time.perf_counter() - started_at) * 1000, 2)

        errors = [e.error for e in result.errors] if result.errors else []
        _update_fetch_run(
            db,
            fetch_run,
            fetched=result.stats.total_fetched,
            inserted=result.stats.total_inserted,
            deduped=result.stats.total_deduped,
            errors=errors,
        )

        print(f"\n=== 抓取结果 ===")
        print(f"耗时: {elapsed_ms} ms")
        print(f"抓取: {result.stats.total_fetched}")
        print(f"入库: {result.stats.total_inserted}")
        print(f"去重: {result.stats.total_deduped}")
        print(f"成功源: {result.stats.sources_succeeded}")
        print(f"失败源: {result.stats.sources_failed}")
        if errors:
            print(f"错误: {errors}")
        print(f"\n=== 入库内容 ===")
        for item in result.items:
            print(f"  - [{item['source_type']}] {item['title'][:50]}")

    finally:
        db.close()


if __name__ == "__main__":
    sid = int(sys.argv[1]) if len(sys.argv) > 1 else None
    asyncio.run(run_fetch(sid))
