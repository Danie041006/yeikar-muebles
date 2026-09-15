from typing import List, Optional

from fastapi import APIRouter, Depends, Query
from sqlalchemy.orm import Session, joinedload

from app.db.session import get_db
from app.modules.auditoria import schemas
from app.modules.auditoria.model import AuditEvent
from app.modules.users.deps import es_admin
from app.modules.users.model import Usuario

router = APIRouter()


@router.get("/", response_model=List[schemas.AuditEventResponse])
def listar_eventos(
    entity_type: Optional[str] = Query(None),
    entity_id: Optional[str] = Query(None),
    action: Optional[str] = Query(None),
    salto: int = Query(0, ge=0),
    limite: int = Query(100, ge=1, le=500),
    db: Session = Depends(get_db),
    usuario_actual: Usuario = Depends(es_admin),
):
    query = db.query(AuditEvent).options(joinedload(AuditEvent.actor))
    if entity_type:
        query = query.filter(AuditEvent.entity_type == entity_type)
    if entity_id:
        query = query.filter(AuditEvent.entity_id == entity_id)
    if action:
        query = query.filter(AuditEvent.action == action)

    events = query.order_by(AuditEvent.created_at.desc()).offset(salto).limit(limite).all()
    return [
        schemas.AuditEventResponse(
            **schemas.AuditEventResponse.model_validate(event).model_dump(exclude={"actor_name"}),
            actor_name=event.actor.display_name if event.actor else None,
        )
        for event in events
    ]
