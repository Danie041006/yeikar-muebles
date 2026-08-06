from datetime import date, datetime
from decimal import Decimal
from typing import Any, Optional

from fastapi import Request
from sqlalchemy.orm import Session

from app.modules.auditoria.model import AuditEvent
from app.modules.users.model import Usuario


def _json_safe(value: Any) -> Any:
    if isinstance(value, (datetime, date)):
        return value.isoformat()
    if isinstance(value, Decimal):
        return float(value)
    if isinstance(value, dict):
        return {str(key): _json_safe(item) for key, item in value.items()}
    if isinstance(value, (list, tuple)):
        return [_json_safe(item) for item in value]
    return value


def changed_fields(before: Optional[dict[str, Any]], after: Optional[dict[str, Any]]) -> list[str]:
    before = before or {}
    after = after or {}
    return sorted({key for key in set(before) | set(after) if before.get(key) != after.get(key)})


def record_event(
    db: Session,
    *,
    actor: Optional[Usuario],
    action: str,
    entity_type: str,
    entity_id: int | str,
    before: Optional[dict[str, Any]] = None,
    after: Optional[dict[str, Any]] = None,
    request: Optional[Request] = None,
) -> AuditEvent:
    event = AuditEvent(
        actor_user_id=actor.id if actor else None,
        action=action,
        entity_type=entity_type,
        entity_id=str(entity_id),
        before_data=_json_safe(before),
        after_data=_json_safe(after),
        changed_fields=changed_fields(before, after) if before is not None or after is not None else None,
        ip_address=request.client.host if request and request.client else None,
        user_agent=request.headers.get("user-agent") if request else None,
    )
    db.add(event)
    return event
