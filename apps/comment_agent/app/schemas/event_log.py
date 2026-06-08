from datetime import datetime

from pydantic import BaseModel, ConfigDict


class EventLogRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    event_id: str
    site_id: int
    event_type: str
    payload_json: dict
    process_status: str
    error_message: str | None
    received_at: datetime
    processed_at: datetime | None
