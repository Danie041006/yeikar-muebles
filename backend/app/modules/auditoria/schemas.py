from datetime import datetime
from typing import Any, Optional

from pydantic import BaseModel, ConfigDict


class AuditEventResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    actor_user_id: Optional[int] = None
    action: str
    entity_type: str
    entity_id: str
    before_data: Optional[dict[str, Any]] = None
    after_data: Optional[dict[str, Any]] = None
    changed_fields: Optional[list[str]] = None
    ip_address: Optional[str] = None
    created_at: datetime
    actor_name: Optional[str] = None
