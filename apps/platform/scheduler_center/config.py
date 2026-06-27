from __future__ import annotations

import os
from pathlib import Path
from typing import Optional

from pydantic import AliasChoices, Field

try:
    from pydantic_settings import BaseSettings, SettingsConfigDict

    _HAS_PYDANTIC_SETTINGS = True
except Exception:
    from pydantic import BaseModel

    BaseSettings = BaseModel  # type: ignore[assignment]
    SettingsConfigDict = None  # type: ignore[assignment]
    _HAS_PYDANTIC_SETTINGS = False


BASE_DIR = Path(__file__).resolve().parent.parent
CONTENT_FETCH_BATCH = "content.fetch.batch"
CONTENT_PIPELINE_RADAR = "content.pipeline.radar"
CONTENT_PIPELINE_DAILY_DIGEST = "content.pipeline.daily_digest"


def _parse_int(value: str | None, default: int) -> int:
    try:
        return int(value) if value is not None and value != "" else default
    except ValueError:
        return default


def _parse_float(value: str | None, default: float) -> float:
    try:
        return float(value) if value is not None and value != "" else default
    except ValueError:
        return default


def _parse_bool(value: str | None, default: bool = False) -> bool:
    if value is None:
        return default
    return value.strip().lower() in {"1", "true", "yes", "on"}


def _parse_list(raw: str | None) -> list[str]:
    if not raw:
        return []
    return [item.strip() for item in raw.split(",") if item.strip()]


class SchedulerSettings(BaseSettings):
    if _HAS_PYDANTIC_SETTINGS:
        model_config = SettingsConfigDict(
            env_file=".env",
            env_file_encoding="utf-8",
            extra="ignore",
            populate_by_name=True,
        )

    scheduler_database_url: Optional[str] = Field(
        default=None,
        validation_alias=AliasChoices("SCHEDULER_DATABASE_URL", "scheduler_database_url"),
    )
    scheduler_db_path: str = Field(
        default=str(BASE_DIR / "scheduler.db"),
        validation_alias=AliasChoices("SCHEDULER_DB_PATH", "scheduler_db_path"),
    )
    scheduler_internal_token: str = Field(
        default="local-dev-scheduler-token",
        validation_alias=AliasChoices("SCHEDULER_INTERNAL_TOKEN", "scheduler_internal_token"),
    )
    scheduler_agent_endpoints_raw: str = Field(
        default="",
        validation_alias=AliasChoices("SCHEDULER_AGENT_ENDPOINTS", "scheduler_agent_endpoints_raw"),
    )
    scheduler_agent_request_path: str = Field(
        default="/api/internal/agent/run",
        validation_alias=AliasChoices("SCHEDULER_AGENT_REQUEST_PATH", "scheduler_agent_request_path"),
    )
    scheduler_agent_token: Optional[str] = Field(
        default=None,
        validation_alias=AliasChoices("SCHEDULER_AGENT_TOKEN", "scheduler_agent_token"),
    )
    scheduler_agent_registry_prefer_db: bool = Field(
        default=True,
        validation_alias=AliasChoices(
            "SCHEDULER_AGENT_REGISTRY_PREFER_DB",
            "scheduler_agent_registry_prefer_db",
        ),
    )
    scheduler_agent_heartbeat_ttl_seconds: float = Field(
        default=120.0,
        validation_alias=AliasChoices(
            "SCHEDULER_AGENT_HEARTBEAT_TTL_SECONDS",
            "scheduler_agent_heartbeat_ttl_seconds",
        ),
    )
    scheduler_agent_health_cache_seconds: float = Field(
        default=10.0,
        validation_alias=AliasChoices(
            "SCHEDULER_AGENT_HEALTH_CACHE_SECONDS",
            "scheduler_agent_health_cache_seconds",
        ),
    )
    scheduler_agent_health_timeout_seconds: float = Field(
        default=2.0,
        validation_alias=AliasChoices(
            "SCHEDULER_AGENT_HEALTH_TIMEOUT_SECONDS",
            "scheduler_agent_health_timeout_seconds",
        ),
    )
    scheduler_max_concurrency: int = Field(
        default=4,
        validation_alias=AliasChoices("SCHEDULER_MAX_CONCURRENCY", "scheduler_max_concurrency"),
    )
    scheduler_poll_interval_seconds: float = Field(
        default=0.5,
        validation_alias=AliasChoices(
            "SCHEDULER_POLL_INTERVAL_SECONDS", "scheduler_poll_interval_seconds"
        ),
    )
    scheduler_default_max_retries: int = Field(
        default=2,
        validation_alias=AliasChoices("SCHEDULER_DEFAULT_MAX_RETRIES", "scheduler_default_max_retries"),
    )
    scheduler_default_retry_delay_seconds: float = Field(
        default=3.0,
        validation_alias=AliasChoices(
            "SCHEDULER_DEFAULT_RETRY_DELAY_SECONDS", "scheduler_default_retry_delay_seconds"
        ),
    )
    scheduler_http_timeout_seconds: float = Field(
        default=60.0,
        validation_alias=AliasChoices("SCHEDULER_HTTP_TIMEOUT_SECONDS", "scheduler_http_timeout_seconds"),
    )
    scheduler_disable_dispatcher: bool = Field(
        default=False,
        validation_alias=AliasChoices(
            "SCHEDULER_DISABLE_DISPATCHER", "scheduler_disable_dispatcher"
        ),
    )
    scheduler_cron_enabled: bool = Field(
        default=True,
        validation_alias=AliasChoices(
            "CONTENT_HUB_SCHEDULER_ENABLED",
            "scheduler_cron_enabled",
        ),
    )
    scheduler_submit_write_logs: bool = Field(
        default=False,
        validation_alias=AliasChoices(
            "SCHEDULER_SUBMIT_WRITE_LOGS",
            "scheduler_submit_write_logs",
        ),
    )
    scheduler_cors_allow_origins_raw: str = Field(
        default="",
        validation_alias=AliasChoices("SCHEDULER_CORS_ALLOW_ORIGINS", "scheduler_cors_allow_origins_raw"),
    )
    scheduler_redis_url: Optional[str] = Field(
        default=None,
        validation_alias=AliasChoices("SCHEDULER_REDIS_URL", "scheduler_redis_url"),
    )
    scheduler_redis_prefix: str = Field(
        default="scheduler",
        validation_alias=AliasChoices("SCHEDULER_REDIS_PREFIX", "scheduler_redis_prefix"),
    )
    scheduler_fast_submit_enabled: bool = Field(
        default=False,
        validation_alias=AliasChoices(
            "SCHEDULER_FAST_SUBMIT_ENABLED",
            "scheduler_fast_submit_enabled",
        ),
    )
    scheduler_fast_submit_task_ttl_seconds: int = Field(
        default=3600,
        validation_alias=AliasChoices(
            "SCHEDULER_FAST_SUBMIT_TASK_TTL_SECONDS",
            "scheduler_fast_submit_task_ttl_seconds",
        ),
    )
    scheduler_sqlite_busy_timeout_seconds: float = Field(
        default=30.0,
        validation_alias=AliasChoices(
            "SCHEDULER_SQLITE_BUSY_TIMEOUT_SECONDS",
            "scheduler_sqlite_busy_timeout_seconds",
        ),
    )
    scheduler_db_pool_size: int = Field(
        default=30,
        validation_alias=AliasChoices("SCHEDULER_DB_POOL_SIZE", "scheduler_db_pool_size"),
    )
    scheduler_db_max_overflow: int = Field(
        default=60,
        validation_alias=AliasChoices("SCHEDULER_DB_MAX_OVERFLOW", "scheduler_db_max_overflow"),
    )
    scheduler_db_pool_timeout_seconds: float = Field(
        default=30.0,
        validation_alias=AliasChoices(
            "SCHEDULER_DB_POOL_TIMEOUT_SECONDS",
            "scheduler_db_pool_timeout_seconds",
        ),
    )

    @property
    def scheduler_agent_endpoints(self) -> list[str]:
        return _parse_list(self.scheduler_agent_endpoints_raw)

    @property
    def scheduler_cors_allow_origins(self) -> list[str]:
        return [o for o in _parse_list(self.scheduler_cors_allow_origins_raw) if o != "*"]

    @property
    def resolved_scheduler_database_url(self) -> str:
        if self.scheduler_database_url:
            return self.scheduler_database_url
        path = str(Path(self.scheduler_db_path)).replace(os.sep, "/")
        return f"sqlite:///{path}"

    @property
    def scheduled_jobs(self) -> list[dict[str, object]]:
        return [
            {
                "task_type": CONTENT_PIPELINE_RADAR,
                "cron_expression": "0 9 * * *",
                "payload": {
                    "workflow_name": "radar_pipeline",
                    "limit": 20,
                    "source_type": None,
                    "trigger_type": "scheduled",
                    "filter_config": {
                        "keywords": ["agent", "rag", "openai", "llm"],
                        "exclude_keywords": ["招聘", "广告"],
                    },
                    "process_options": {"rewrite_profile": "zh_tech_blog"},
                },
            },
            {
                "task_type": CONTENT_PIPELINE_DAILY_DIGEST,
                "cron_expression": "15 9 * * *",
                "payload": {
                    "lookback_hours": 24,
                    "trigger_type": "scheduled",
                },
            },
        ]


def _load_fallback_settings() -> SchedulerSettings:
    return SchedulerSettings.model_validate(
        {
            "SCHEDULER_DATABASE_URL": os.getenv("SCHEDULER_DATABASE_URL") or None,
            "SCHEDULER_DB_PATH": os.getenv("SCHEDULER_DB_PATH") or str(BASE_DIR / "scheduler.db"),
            "SCHEDULER_INTERNAL_TOKEN": os.getenv(
                "SCHEDULER_INTERNAL_TOKEN", "local-dev-scheduler-token"
            ),
            "SCHEDULER_AGENT_ENDPOINTS": os.getenv("SCHEDULER_AGENT_ENDPOINTS", ""),
            "SCHEDULER_AGENT_REQUEST_PATH": os.getenv(
                "SCHEDULER_AGENT_REQUEST_PATH", "/api/internal/agent/run"
            ),
            "SCHEDULER_AGENT_TOKEN": os.getenv("SCHEDULER_AGENT_TOKEN") or None,
            "SCHEDULER_AGENT_REGISTRY_PREFER_DB": _parse_bool(
                os.getenv("SCHEDULER_AGENT_REGISTRY_PREFER_DB"), True
            ),
            "SCHEDULER_AGENT_HEARTBEAT_TTL_SECONDS": _parse_float(
                os.getenv("SCHEDULER_AGENT_HEARTBEAT_TTL_SECONDS"), 120.0
            ),
            "SCHEDULER_AGENT_HEALTH_CACHE_SECONDS": _parse_float(
                os.getenv("SCHEDULER_AGENT_HEALTH_CACHE_SECONDS"), 10.0
            ),
            "SCHEDULER_AGENT_HEALTH_TIMEOUT_SECONDS": _parse_float(
                os.getenv("SCHEDULER_AGENT_HEALTH_TIMEOUT_SECONDS"), 2.0
            ),
            "SCHEDULER_MAX_CONCURRENCY": _parse_int(os.getenv("SCHEDULER_MAX_CONCURRENCY"), 4),
            "SCHEDULER_POLL_INTERVAL_SECONDS": _parse_float(
                os.getenv("SCHEDULER_POLL_INTERVAL_SECONDS"), 0.5
            ),
            "SCHEDULER_DEFAULT_MAX_RETRIES": _parse_int(
                os.getenv("SCHEDULER_DEFAULT_MAX_RETRIES"), 2
            ),
            "SCHEDULER_DEFAULT_RETRY_DELAY_SECONDS": _parse_float(
                os.getenv("SCHEDULER_DEFAULT_RETRY_DELAY_SECONDS"), 3.0
            ),
            "SCHEDULER_HTTP_TIMEOUT_SECONDS": _parse_float(
                os.getenv("SCHEDULER_HTTP_TIMEOUT_SECONDS"), 60.0
            ),
            "SCHEDULER_DISABLE_DISPATCHER": _parse_bool(
                os.getenv("SCHEDULER_DISABLE_DISPATCHER"), False
            ),
            "CONTENT_HUB_SCHEDULER_ENABLED": _parse_bool(
                os.getenv("CONTENT_HUB_SCHEDULER_ENABLED"), True
            ),
            "SCHEDULER_SUBMIT_WRITE_LOGS": _parse_bool(
                os.getenv("SCHEDULER_SUBMIT_WRITE_LOGS"), False
            ),
            "SCHEDULER_CORS_ALLOW_ORIGINS": os.getenv("SCHEDULER_CORS_ALLOW_ORIGINS", ""),
            "SCHEDULER_REDIS_URL": os.getenv("SCHEDULER_REDIS_URL") or None,
            "SCHEDULER_REDIS_PREFIX": os.getenv("SCHEDULER_REDIS_PREFIX", "scheduler"),
            "SCHEDULER_FAST_SUBMIT_ENABLED": _parse_bool(
                os.getenv("SCHEDULER_FAST_SUBMIT_ENABLED"), False
            ),
            "SCHEDULER_FAST_SUBMIT_TASK_TTL_SECONDS": _parse_int(
                os.getenv("SCHEDULER_FAST_SUBMIT_TASK_TTL_SECONDS"), 3600
            ),
            "SCHEDULER_SQLITE_BUSY_TIMEOUT_SECONDS": _parse_float(
                os.getenv("SCHEDULER_SQLITE_BUSY_TIMEOUT_SECONDS"), 30.0
            ),
            "SCHEDULER_DB_POOL_SIZE": _parse_int(os.getenv("SCHEDULER_DB_POOL_SIZE"), 30),
            "SCHEDULER_DB_MAX_OVERFLOW": _parse_int(os.getenv("SCHEDULER_DB_MAX_OVERFLOW"), 60),
            "SCHEDULER_DB_POOL_TIMEOUT_SECONDS": _parse_float(
                os.getenv("SCHEDULER_DB_POOL_TIMEOUT_SECONDS"), 30.0
            ),
        }
    )


scheduler_settings = SchedulerSettings() if _HAS_PYDANTIC_SETTINGS else _load_fallback_settings()

