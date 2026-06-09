from pydantic import AliasChoices, Field
from pydantic_settings import BaseSettings, SettingsConfigDict


def _parse_list(raw: str | None) -> list[str]:
    if not raw:
        return []
    return [item.strip() for item in raw.split(",") if item.strip() and item.strip() != "*"]


class Settings(BaseSettings):
    app_name: str = "Comment Agent"
    database_url: str = "sqlite:///./comment_agent.db"
    default_reply_delay_seconds: int = 120
    default_article_reply_limit: int = 3
    cors_allow_origins_raw: str = Field(
        default="",
        validation_alias=AliasChoices(
            "COMMENT_AGENT_CORS_ALLOW_ORIGINS",
            "CORS_ALLOW_ORIGINS",
            "cors_allow_origins_raw",
        ),
    )
    mempool_namespace: str = "comment-agent"
    mempool_redis_url: str = "redis://localhost:6379/0"
    mempool_sqlite_path: str = "./shared_memory.db"
    mempool_default_ttl_seconds: int | None = 3600
    mempool_serializer: str = "json"
    mempool_redis_key_prefix: str = "shared_memory:"

    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        extra="ignore",
    )

    @property
    def cors_allow_origins(self) -> list[str]:
        return _parse_list(self.cors_allow_origins_raw)


settings = Settings()
