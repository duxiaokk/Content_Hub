from __future__ import annotations

import json
from datetime import datetime, timezone

from sqlalchemy.orm import Session

from apps.platform.models import ContentItem, Post, PublishRecord


def _utcnow() -> datetime:
    return datetime.now(timezone.utc)


class PublishNotFoundError(ValueError):
    pass


class PublishService:
    def __init__(self, db: Session) -> None:
        self.db = db

    def publish_blog_draft(self, content_item_id: int, run_id: str | None = None) -> dict:
        item = self.db.query(ContentItem).filter(ContentItem.id == content_item_id).first()
        if item is None:
            raise PublishNotFoundError(f"content item not found: {content_item_id}")

        existing = (
            self.db.query(PublishRecord)
            .filter(
                PublishRecord.content_item_id == content_item_id,
                PublishRecord.target_type == "blog",
                PublishRecord.status == "success",
            )
            .first()
        )
        if existing is not None:
            return {
                "content_item_id": content_item_id,
                "target_type": "blog",
                "status": "skipped",
                "external_url": existing.external_url,
                "external_id": existing.external_id,
                "message": "already published",
            }

        title = item.rewritten_title or item.title
        content = item.rewritten_content or item.processed_content or item.raw_content or ""
        tags = self._parse_tags(item.tags_json)
        resolved_run_id = run_id or f"blog-draft-{content_item_id}"

        try:
            media_data = self._extract_media(item)
            post = Post(
                title=title,
                content=content,
                published=False,
                tech_tag=tags[0] if tags else None,
                media_json=json.dumps(media_data, ensure_ascii=False) if media_data else None,
            )
            self.db.add(post)
            self.db.flush()

            item.publish_status = "published"
            item.pipeline_status = "published"
            item.draft_post_id = int(post.id)
            self.db.add(item)

            self.db.add(
                PublishRecord(
                    content_item_id=content_item_id,
                    target_type="blog",
                    target_name="draft_post",
                    status="success",
                    external_id=str(post.id),
                    response_payload=json.dumps(
                        {
                            "post_id": post.id,
                            "source_url": item.source_url,
                            "tags": tags,
                        },
                        ensure_ascii=False,
                    ),
                    run_id=resolved_run_id,
                    published_at=_utcnow(),
                )
            )
            self.db.commit()
            self.db.refresh(post)
            self.db.refresh(item)
            return {
                "content_item_id": content_item_id,
                "target_type": "blog",
                "status": "success",
                "external_url": None,
                "external_id": str(post.id),
                "message": "draft published",
            }
        except Exception as exc:
            self.db.rollback()
            self.db.add(
                PublishRecord(
                    content_item_id=content_item_id,
                    target_type="blog",
                    target_name="draft_post",
                    status="failed",
                    response_payload=json.dumps({"error": str(exc)}, ensure_ascii=False),
                    run_id=resolved_run_id,
                )
            )
            self.db.commit()
            raise

    @staticmethod
    def _parse_tags(raw_tags: str | None) -> list[str]:
        try:
            parsed = json.loads(raw_tags or "[]")
        except json.JSONDecodeError:
            return []
        return [str(tag) for tag in parsed if str(tag)]

    @staticmethod
    def _extract_media(item: ContentItem) -> dict[str, Any] | None:
        """从 ContentItem.metadata_json 中提取媒体引用信息。"""
        if not item.metadata_json:
            return None
        try:
            meta = json.loads(item.metadata_json)
        except json.JSONDecodeError:
            return None

        media: dict[str, Any] = {}
        # 提取封面图
        cover = meta.get("cover_url") or meta.get("cover")
        if cover:
            media["cover_url"] = cover

        # 提取视频链接
        video = meta.get("video_url") or meta.get("video")
        if video:
            media["video_url"] = video

        # 提取图片列表
        images = meta.get("images") or meta.get("imageList") or meta.get("image_list")
        if isinstance(images, list) and images:
            media["images"] = [str(u) for u in images if isinstance(u, str)]

        # bilibili 专用：metadata.media 列表
        raw_media = meta.get("media")
        if isinstance(raw_media, list) and raw_media and "images" not in media:
            media["images"] = [str(u) for u in raw_media if isinstance(u, str)]

        # 原始平台链接（用于嵌入 iframe）
        if item.source_url:
            media["source_url"] = item.source_url

        return media if media else None
