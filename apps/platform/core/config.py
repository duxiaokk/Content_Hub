"""
功能摘要：本文件负责读取环境变量与配置文件，为整个项目提供统一的设置项。

初学者指南：
这个文件是博客系统的"配置中心"。数据库地址、密钥、管理员账号等敏感信息
都从这里统一管理，支持从 .env 文件或系统环境变量读取。
如果你要在本地和线上使用不同的数据库，只需修改 .env 文件，
不需要改动任何业务代码。

主要成员：
- Settings: 配置类，集中定义数据库、令牌、缓存等所有运行时参数
- resolved_database_url: 根据当前环境自动拼接出最终的数据库连接地址
- _parse_bool(): 辅助函数，将字符串形式的环境变量转为布尔值
"""
from __future__ import annotations

import os
from pathlib import Path
from typing import List, Optional

from pydantic import AliasChoices, Field

try:
    from pydantic_settings import BaseSettings, SettingsConfigDict

    _HAS_PYDANTIC_SETTINGS = True
except Exception:  # pragma: no cover - fallback for older/local envs
    from pydantic import BaseModel

    BaseSettings = BaseModel  # type: ignore[assignment]
    SettingsConfigDict = None  # type: ignore[assignment]
    _HAS_PYDANTIC_SETTINGS = False


BASE_DIR = Path(__file__).resolve().parent.parent
DEFAULT_SQLITE_DB_PATH = BASE_DIR / "blog.db"


def _normalize_sqlite_url(database_url: str) -> str:
    if not database_url.startswith("sqlite:///"):
        return database_url

    sqlite_path = database_url.removeprefix("sqlite:///")
    if sqlite_path in {"", ":memory:"}:
        return database_url

    candidate_path = Path(sqlite_path)
    if not candidate_path.is_absolute():
        candidate_path = (BASE_DIR / candidate_path).resolve()
    else:
        candidate_path = candidate_path.resolve()

    return f"sqlite:///{str(candidate_path).replace(os.sep, '/')}"


def _parse_bool(value: str | None, default: bool = False) -> bool:
    if value is None:
        return default
    return value.strip().lower() in {"1", "true", "yes", "on"}


def _parse_int(value: str | None, default: int) -> int:
    try:
        return int(value) if value is not None and value != "" else default
    except ValueError:
        return default


def _parse_tags(raw: str | None) -> List[str]:
    if not raw:
        return ["Python", "FastAPI", "SQLAlchemy", "SQLite"]
    tags = [item.strip() for item in raw.split(",") if item.strip()]
    return tags or ["Python", "FastAPI", "SQLAlchemy", "SQLite"]


class Settings(BaseSettings):
    if _HAS_PYDANTIC_SETTINGS:
        model_config = SettingsConfigDict(
            env_file=".env",
            env_file_encoding="utf-8",
            extra="ignore",
            populate_by_name=True,
        )

    database_url: Optional[str] = None
    sqlite_db_path: Optional[str] = None
    use_mysql: bool = False
    db_user: Optional[str] = None
    db_password: Optional[str] = None
    db_host: str = "127.0.0.1"
    db_port: str = "3306"
    db_name: Optional[str] = None
    secret_key: Optional[str] = None
    jwt_algorithm: str = Field(
        default="HS256",
        validation_alias=AliasChoices("ALGORITHM", "JWT_ALGORITHM", "jwt_algorithm"),
    )
    access_token_expire_minutes: int = 30
    refresh_token_expire_days: int = 30
    admin_username: str = "Ado_Jk"
    tech_tags_raw: str = Field(
        default="Python,FastAPI,SQLAlchemy,SQLite",
        validation_alias=AliasChoices("TECH_TAGS", "TECH_TAGS_RAW", "tech_tags_raw"),
    )
    redis_url: Optional[str] = None
    internal_agent_token: str = Field(
        default="local-dev-internal-token",
        validation_alias=AliasChoices("INTERNAL_AGENT_TOKEN", "internal_agent_token"),
    )

    # LLM 配置（新增）
    llm_api_key: Optional[str] = Field(
        default=None,
        validation_alias=AliasChoices("LLM_API_KEY", "llm_api_key"),
    )
    llm_base_url: str = Field(
        default="https://api.deepseek.com",
        validation_alias=AliasChoices("LLM_BASE_URL", "llm_base_url"),
    )
    llm_model: str = Field(
        default="deepseek-v4-flash",
        validation_alias=AliasChoices("LLM_MODEL", "llm_model"),
    )
    mock_llm: bool = Field(
        default=False,
        validation_alias=AliasChoices("MOCK_LLM", "mock_llm"),
    )

    @property
    def tech_tags(self) -> list[str]:
        return _parse_tags(self.tech_tags_raw)

    @property
    def resolved_database_url(self) -> str:
        if self.database_url:
            return _normalize_sqlite_url(self.database_url)
        if self.use_mysql:
            if not self.db_user or not self.db_password or not self.db_name:
                raise ValueError("MySQL configuration requires DB_USER, DB_PASSWORD and DB_NAME")
            return f"mysql+pymysql://{self.db_user}:{self.db_password}@{self.db_host}:{self.db_port}/{self.db_name}"
        sqlite_db_path = Path(self.sqlite_db_path).expanduser() if self.sqlite_db_path else DEFAULT_SQLITE_DB_PATH
        if not sqlite_db_path.is_absolute():
            sqlite_db_path = BASE_DIR / sqlite_db_path
        sqlite_db_path = sqlite_db_path.resolve()
        return f"sqlite:///{str(sqlite_db_path).replace(os.sep, '/')}"


def _load_fallback_settings() -> Settings:
    return Settings.model_validate(
        {
            "database_url": os.getenv("DATABASE_URL") or None,
            "sqlite_db_path": os.getenv("SQLITE_DB_PATH") or None,
            "use_mysql": _parse_bool(os.getenv("USE_MYSQL"), False),
            "db_user": os.getenv("DB_USER") or None,
            "db_password": os.getenv("DB_PASSWORD") or None,
            "db_host": os.getenv("DB_HOST", "127.0.0.1"),
            "db_port": os.getenv("DB_PORT", "3306"),
            "db_name": os.getenv("DB_NAME") or None,
            "secret_key": os.getenv("SECRET_KEY", ""),
            "ALGORITHM": os.getenv("ALGORITHM") or os.getenv("JWT_ALGORITHM", "HS256"),
            "access_token_expire_minutes": _parse_int(os.getenv("ACCESS_TOKEN_EXPIRE_MINUTES"), 30),
            "refresh_token_expire_days": _parse_int(os.getenv("REFRESH_TOKEN_EXPIRE_DAYS"), 30),
            "admin_username": os.getenv("ADMIN_USERNAME", "Ado_Jk"),
            "TECH_TAGS": os.getenv("TECH_TAGS", "Python,FastAPI,SQLAlchemy,SQLite"),
            "redis_url": os.getenv("REDIS_URL") or None,
            "INTERNAL_AGENT_TOKEN": os.getenv(
                "INTERNAL_AGENT_TOKEN", "local-dev-internal-token"
            ),
        }
    )


settings = Settings() if _HAS_PYDANTIC_SETTINGS else _load_fallback_settings()

if not settings.secret_key:
    env_name = os.getenv("CONTENT_HUB_ENV", "production").strip().lower()
    allow_insecure_dev_secret = _parse_bool(os.getenv("ALLOW_INSECURE_DEV_SECRET"), False)
    if allow_insecure_dev_secret and env_name in {"development", "dev", "local"}:
        settings.secret_key = "local-dev-secret-key"
    else:
        raise RuntimeError("SECRET_KEY is required")
