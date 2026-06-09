from __future__ import annotations

import os
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

import yaml


@dataclass
class FetchersSettings:
    lookback_hours: int = 24
    persist_cursors: bool = True
    max_retries: int = 3
    timeout_seconds: float = 15.0
    x_enabled: bool = False
    youtube_enabled: bool = True
    instagram_enabled: bool = False
    youtube_api_key: str | None = None
    youtube_channel_id: str = "UCln9P4Qm3-EAY4aiEPmRwEA"


@dataclass
class Settings:
    fetchers: FetchersSettings = field(default_factory=FetchersSettings)


def _apply_env_overrides(data: dict[str, Any]) -> dict[str, Any]:
    if data.get("fetchers") is None:
        data["fetchers"] = {}
    fe = data["fetchers"]
    lookback_hours = os.environ.get("ADO_FETCH_LOOKBACK_HOURS")
    fe["lookback_hours"] = int(
        lookback_hours if lookback_hours is not None else fe.get("lookback_hours", 24)
    )
    fe["persist_cursors"] = os.environ.get(
        "ADO_FETCH_PERSIST_CURSORS", str(fe.get("persist_cursors", True))
    ).lower() in ("true", "1", "yes")
    max_retries = os.environ.get("ADO_FETCH_MAX_RETRIES")
    fe["max_retries"] = int(
        max_retries if max_retries is not None else fe.get("max_retries", 3)
    )
    timeout_seconds = os.environ.get("ADO_FETCH_TIMEOUT_SECONDS")
    fe["timeout_seconds"] = float(
        timeout_seconds
        if timeout_seconds is not None
        else fe.get("timeout_seconds", 15.0)
    )
    fe["x_enabled"] = os.environ.get(
        "ADO_X_ENABLED", str(fe.get("x_enabled", False))
    ).lower() in ("true", "1", "yes")
    fe["youtube_enabled"] = os.environ.get(
        "ADO_YOUTUBE_ENABLED", str(fe.get("youtube_enabled", True))
    ).lower() in ("true", "1", "yes")
    fe["instagram_enabled"] = os.environ.get(
        "ADO_INSTAGRAM_ENABLED", str(fe.get("instagram_enabled", False))
    ).lower() in ("true", "1", "yes")
    fe["youtube_api_key"] = os.environ.get(
        "ADO_YOUTUBE_API_KEY", fe.get("youtube_api_key", "")
    ) or None
    fe["youtube_channel_id"] = str(
        os.environ.get(
            "ADO_YOUTUBE_CHANNEL_ID",
            fe.get("youtube_channel_id", "UCln9P4Qm3-EAY4aiEPmRwEA"),
        )
    )

    return data


def _yaml_to_settings(data: dict[str, Any]) -> Settings:
    fe_raw = data.get("fetchers", {})

    fe = FetchersSettings(
        lookback_hours=int(fe_raw.get("lookback_hours", 24)),
        persist_cursors=bool(fe_raw.get("persist_cursors", True)),
        max_retries=int(fe_raw.get("max_retries", 3)),
        timeout_seconds=float(fe_raw.get("timeout_seconds", 15.0)),
        x_enabled=bool(fe_raw.get("x_enabled", False)),
        youtube_enabled=bool(fe_raw.get("youtube_enabled", True)),
        instagram_enabled=bool(fe_raw.get("instagram_enabled", False)),
        youtube_api_key=fe_raw.get("youtube_api_key"),
        youtube_channel_id=str(fe_raw.get("youtube_channel_id", "UCln9P4Qm3-EAY4aiEPmRwEA")),
    )

    return Settings(fetchers=fe)


def load_settings(config_path: Path | None = None) -> Settings:
    if config_path is None:
        candidates = [
            Path.cwd() / "config.yaml",
            Path.cwd() / "config.yml",
            Path(__file__).parent.parent.parent / "config.yaml",
        ]
        for candidate in candidates:
            if candidate.exists():
                config_path = candidate
                break

    data: dict[str, Any] = {}
    if config_path and config_path.exists():
        with config_path.open("r", encoding="utf-8") as fh:
            loaded = yaml.safe_load(fh)
            if loaded and isinstance(loaded, dict):
                data = dict(loaded)

    data = _apply_env_overrides(data)
    return _yaml_to_settings(data)
