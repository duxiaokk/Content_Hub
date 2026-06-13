from __future__ import annotations

import asyncio
import os
import sys
from pathlib import Path


def _output_dir() -> Path:
    path = Path("D:/Python/content_hub/.tmp/test_digest_output")
    path.mkdir(parents=True, exist_ok=True)
    return path


def test_markdown_digest_publisher_outputs_markdown_file() -> None:
    output_dir = _output_dir()
    os.environ["CONTENT_HUB_DIGEST_OUTPUT_DIR"] = str(output_dir)
    sys.path.insert(0, str(Path(__file__).resolve().parents[3]))

    from publisher_engine.adapters.markdown_export.publisher import MarkdownDigestPublisher

    publisher = MarkdownDigestPublisher()
    result = asyncio.run(
        publisher.publish(
            [
                {
                    "title": "FastAPI Weekly",
                    "url": "https://example.com/post-1",
                    "source_type": "rss",
                    "source_account": "weekly-feed",
                    "category": "backend",
                    "tags": ["python", "fastapi"],
                    "summary": "Weekly FastAPI roundup.",
                }
            ]
        )
    )

    assert result["included_count"] == 1
    assert Path(result["file_path"]).exists()
    assert Path(result["file_path"]).read_text(encoding="utf-8").startswith("# 技术内容日报 - ")
    assert "[FastAPI Weekly](https://example.com/post-1)" in result["content_markdown"]


def test_markdown_digest_publisher_includes_required_fields() -> None:
    output_dir = _output_dir()
    os.environ["CONTENT_HUB_DIGEST_OUTPUT_DIR"] = str(output_dir)
    sys.path.insert(0, str(Path(__file__).resolve().parents[3]))

    from publisher_engine.adapters.markdown_export.publisher import MarkdownDigestPublisher

    publisher = MarkdownDigestPublisher()
    result = asyncio.run(
        publisher.publish(
            [
                {
                    "title": "AI News",
                    "url": "https://example.com/ai-news",
                    "source_type": "reddit",
                    "source_account": "r/artificial",
                    "category": "AI",
                    "tags": ["llm", "agents"],
                    "summary": "Agent systems roundup.",
                }
            ]
        )
    )

    markdown = result["content_markdown"]
    assert "**来源**：reddit / r/artificial" in markdown
    assert "**分类**：AI" in markdown
    assert "**标签**：llm, agents" in markdown
    assert "**摘要**：Agent systems roundup." in markdown
