from __future__ import annotations

from datetime import timedelta

import pytest

from apps.fetcher_engine.runtime import rss as rss_runtime
from apps.fetcher_engine.runtime.rss import ParseError, RssFetchRequest, parse_rss_items, within_lookback


def test_parse_rss_items_returns_sorted_posts() -> None:
    xml_text = """
    <rss>
      <channel>
        <item>
          <title>Older</title>
          <link>https://example.com/older</link>
          <guid>older</guid>
          <pubDate>Fri, 12 Jun 2026 09:00:00 GMT</pubDate>
        </item>
        <item>
          <title>Newer</title>
          <link>https://example.com/newer</link>
          <guid>newer</guid>
          <pubDate>Fri, 12 Jun 2026 10:00:00 GMT</pubDate>
        </item>
      </channel>
    </rss>
    """.strip()

    items = parse_rss_items(xml_text, source="rss", adapter="rss")

    assert [item.external_id for item in items] == ["newer", "older"]


def test_parse_rss_items_raises_parse_error_for_invalid_xml() -> None:
    with pytest.raises(ParseError):
        parse_rss_items("<rss><channel><item></rss>", source="rss", adapter="rss")


def test_within_lookback_respects_request_window(monkeypatch: pytest.MonkeyPatch) -> None:
    anchor = rss_runtime.utc_now()
    monkeypatch.setattr(rss_runtime, "utc_now", lambda: anchor)
    recent = anchor - timedelta(hours=2)
    stale = anchor - timedelta(hours=72)

    assert within_lookback(recent, RssFetchRequest(lookback_hours=24)) is True
    assert within_lookback(stale, RssFetchRequest(lookback_hours=24)) is False
