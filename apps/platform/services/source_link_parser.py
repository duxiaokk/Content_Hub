from __future__ import annotations

from dataclasses import dataclass
from typing import Any
from urllib.parse import parse_qs, urlparse


@dataclass(slots=True)
class ParsedSourceLink:
    source_type: str
    config: dict[str, Any]
    suggested_name: str
    missing_fields: list[str]
    warnings: list[str]


def parse_source_link(raw_text: str) -> ParsedSourceLink:
    target_url = _extract_target_url(raw_text)
    if not target_url:
        raise ValueError("No supported link found")

    parsed = urlparse(target_url)
    hostname = parsed.netloc.lower()
    path = parsed.path
    query = parse_qs(parsed.query)

    if "reddit.com" in hostname or "redd.it" in hostname:
        return _parse_reddit(target_url, path)
    if "github.com" in hostname and "/trending" in path:
        return _parse_github_trending(target_url, path, query)
    if "xiaohongshu.com" in hostname or "xhslink.com" in hostname:
        return ParsedSourceLink(
            source_type="xiaohongshu",
            config={"urls": [target_url]},
            suggested_name="xiaohongshu-note",
            missing_fields=[],
            warnings=[],
        )
    if "feed.cnblogs.com" in hostname:
        return ParsedSourceLink(
            source_type="cnblogs",
            config={"feed_url": target_url},
            suggested_name=_name_from_url("cnblogs", target_url),
            missing_fields=[],
            warnings=[],
        )
    if "cnblogs.com" in hostname:
        if "/rss" in path or target_url.endswith(".xml"):
            return ParsedSourceLink(
                source_type="cnblogs",
                config={"feed_url": target_url},
                suggested_name=_name_from_url("cnblogs", target_url),
                missing_fields=[],
                warnings=[],
            )
        return ParsedSourceLink(
            source_type="cnblogs",
            config={"feed_url": target_url},
            suggested_name=_name_from_url("cnblogs", target_url),
            missing_fields=[],
            warnings=["The link looks like a CNBlogs page instead of a feed URL. Please verify the feed address."],
        )
    if "bilibili.com" in hostname:
        return _parse_bilibili(target_url, path)
    if "rsshub.app" in hostname:
        return ParsedSourceLink(
            source_type=_detect_rsshub_source_type(path),
            config={"feed_url": target_url},
            suggested_name=_name_from_url("rss", target_url),
            missing_fields=[],
            warnings=[],
        )
    if _looks_like_rss(target_url):
        return ParsedSourceLink(
            source_type="rss",
            config={"feed_url": target_url},
            suggested_name=_name_from_url("rss", target_url),
            missing_fields=["source_name"],
            warnings=["Source name was not inferred from the link. Please fill it in."],
        )

    raise ValueError("Unsupported source link")


def _extract_target_url(raw_text: str) -> str | None:
    text = raw_text.strip()
    if not text:
        return None
    tokens = text.replace("\r", "\n").split()
    candidates = [token.strip("()[]<>\"'.,") for token in tokens]
    urls = [item for item in candidates if item.startswith(("http://", "https://"))]
    if not urls:
        return None
    return urls[-1]


def _parse_reddit(target_url: str, path: str) -> ParsedSourceLink:
    parts = [part for part in path.split("/") if part]
    subreddit = ""
    if len(parts) >= 2 and parts[0] == "r":
        subreddit = parts[1]
    if not subreddit:
        raise ValueError("Unsupported Reddit link")
    return ParsedSourceLink(
        source_type="reddit",
        config={"subreddit": subreddit, "sort": "hot"},
        suggested_name=f"reddit-{subreddit}",
        missing_fields=[],
        warnings=[],
    )


def _parse_github_trending(target_url: str, path: str, query: dict[str, list[str]]) -> ParsedSourceLink:
    parts = [part for part in path.split("/") if part]
    language = parts[1] if len(parts) >= 2 and parts[0] == "trending" else ""
    since = query.get("since", ["daily"])[0] or "daily"
    spoken_language = query.get("spoken_language_code", [""])[0]
    config: dict[str, Any] = {"since": since}
    if language:
        config["language"] = language
    if spoken_language:
        config["spoken_language"] = spoken_language
    suffix = language or "all"
    return ParsedSourceLink(
        source_type="github_trending",
        config=config,
        suggested_name=f"github-trending-{suffix}",
        missing_fields=[],
        warnings=[],
    )


def _parse_bilibili(target_url: str, path: str) -> ParsedSourceLink:
    parts = [part for part in path.split("/") if part]
    warnings: list[str] = []
    uid = ""
    if len(parts) >= 2 and parts[0] == "space" and parts[1].isdigit():
        uid = parts[1]
    elif len(parts) >= 1 and parts[0].isdigit():
        uid = parts[0]
    if uid:
        return ParsedSourceLink(
            source_type="bilibili",
            config={"feed_url": f"https://rsshub.app/bilibili/user/video/{uid}"},
            suggested_name=f"bilibili-{uid}",
            missing_fields=[],
            warnings=[],
        )
    if path.startswith("/bilibili/"):
        return ParsedSourceLink(
            source_type="bilibili",
            config={"feed_url": target_url},
            suggested_name=_name_from_url("bilibili", target_url),
            missing_fields=[],
            warnings=[],
        )
    warnings.append("This Bilibili link was not converted to a stable RSS feed automatically. Please confirm the feed URL.")
    return ParsedSourceLink(
        source_type="bilibili",
        config={"feed_url": target_url},
        suggested_name=_name_from_url("bilibili", target_url),
        missing_fields=[],
        warnings=warnings,
    )


def _detect_rsshub_source_type(path: str) -> str:
    if "/bilibili/" in path:
        return "bilibili"
    if "/cnblogs/" in path:
        return "cnblogs"
    return "rss"


def _looks_like_rss(target_url: str) -> bool:
    lowered = target_url.lower()
    return lowered.endswith(".xml") or lowered.endswith(".rss") or "/feed" in lowered or "rss" in lowered


def _name_from_url(prefix: str, target_url: str) -> str:
    parsed = urlparse(target_url)
    host = parsed.netloc.lower().replace("www.", "").replace(":", "-")
    path = parsed.path.strip("/").replace("/", "-")
    suffix = path or "default"
    return f"{prefix}-{host}-{suffix}"[:120]
