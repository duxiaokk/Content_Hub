from __future__ import annotations

import asyncio
import os
import sys
from pathlib import Path


def _publisher():
    sys.path.insert(0, str(Path(__file__).resolve().parents[3]))
    from publisher_engine.adapters.markdown_export.publisher import MarkdownDigestPublisher

    return MarkdownDigestPublisher()


def _output_dir() -> Path:
    path = Path("D:/Python/content_hub/.tmp/test_digest_output")
    path.mkdir(parents=True, exist_ok=True)
    return path


def test_markdown_digest_publisher_outputs_markdown_file() -> None:
    os.environ["CONTENT_HUB_DIGEST_OUTPUT_DIR"] = str(_output_dir())
    result = asyncio.run(
        _publisher().publish(
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


def test_markdown_digest_publisher_contains_required_sections() -> None:
    os.environ["CONTENT_HUB_DIGEST_OUTPUT_DIR"] = str(_output_dir())
    result = asyncio.run(
        _publisher().publish(
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
    assert "**" in markdown
    assert "AI News" in markdown


def test_markdown_digest_publisher_handles_empty_input() -> None:
    os.environ["CONTENT_HUB_DIGEST_OUTPUT_DIR"] = str(_output_dir())
    result = asyncio.run(_publisher().publish([]))

    assert result["included_count"] == 0
