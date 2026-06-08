from datetime import datetime

from pydantic import BaseModel, ConfigDict, Field


class SiteCreate(BaseModel):
    site_key: str = Field(min_length=1, max_length=64)
    site_name: str = Field(min_length=1, max_length=128)
    base_url: str = Field(min_length=1, max_length=255)
    webhook_secret: str = Field(min_length=1, max_length=128)
    api_token: str = Field(min_length=1, max_length=255)
    status: int = 1


class SiteRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    site_key: str
    site_name: str
    base_url: str
    status: int
    created_at: datetime
    updated_at: datetime
