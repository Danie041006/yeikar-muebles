from fastapi import APIRouter, Depends, Query
from sqlalchemy.orm import Session

from app.db.session import get_db
from app.modules.sync import schemas, service
from app.modules.users.deps import get_current_user
from app.modules.users.model import Usuario

router = APIRouter()


@router.get("/cambios", response_model=schemas.CambiosResponse)
def listar_cambios(
    desde: int = Query(0, ge=0, description="Último cursor procesado por el dispositivo"),
    limite: int = Query(500, ge=1, le=2000),
    db: Session = Depends(get_db),
    usuario_actual: Usuario = Depends(get_current_user),
):
    """Cambios (incluidos borrados) ocurridos después del cursor indicado."""
    filas, cursor, hay_mas = service.listar_cambios(db, desde, limite)
    return schemas.CambiosResponse(
        cambios=[
            schemas.CambioSync(cursor=fila.id, tabla=fila.tabla, pk=fila.pk, op=fila.op, ocurrido_en=fila.ocurrido_en)
            for fila in filas
        ],
        cursor=cursor,
        hay_mas=hay_mas,
    )


@router.get("/estado")
def estado_sync(
    db: Session = Depends(get_db),
    usuario_actual: Usuario = Depends(get_current_user),
):
    """Último cursor emitido: el cliente lo compara con el suyo para saber si está al día."""
    return {"cursor": service.ultimo_cursor(db)}


@router.post("/push", response_model=schemas.PushResponse)
def sincronizar_push(
    cuerpo: schemas.PushRequest,
    db: Session = Depends(get_db),
    usuario_actual: Usuario = Depends(get_current_user),
):
    """Aplica operaciones capturadas sin conexión. Idempotente por `operacion_id`."""
    resultados = service.aplicar_push(db, cuerpo.operaciones, usuario_actual)
    return schemas.PushResponse(resultados=resultados)
