"""Motor de sincronización offline.

- `listar_cambios`: entrega la bitácora de cambios desde un cursor (el id de
  `sync_cambio` es monótono). Los clientes la usan para invalidar/actualizar
  su réplica local, incluidos los tombstones (`op='D'`) que no se pueden
  detectar con `updated_at`.
- `aplicar_push`: aplica un lote de operaciones capturadas sin red. Cada
  operación se reclama primero en `sync_operacion` (insert + commit) y luego
  corre su handler; así un reintento devuelve el resultado original en vez de
  duplicar el efecto. Si el proceso muere entre reclamo y cierre, el reintento
  recibe `en_proceso` y el Centro de Sincronización lo muestra para revisión.
"""
from typing import Any, Dict, List, Optional, Tuple

from fastapi import HTTPException
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from app.modules.sync import schemas
from app.modules.sync.handlers import HANDLERS, SyncConflicto
from app.modules.sync.model import SyncCambio, SyncOperacion
from app.modules.users.model import Usuario

_ESTADOS_API = {
    "EN_PROCESO": "en_proceso",
    "OK": "ok",
    "CONFLICTO": "conflicto",
    "ERROR": "error",
}


def listar_cambios(db: Session, desde: int, limite: int) -> Tuple[List[SyncCambio], int, bool]:
    filas = (
        db.query(SyncCambio)
        .filter(SyncCambio.id > desde)
        .order_by(SyncCambio.id)
        .limit(limite + 1)
        .all()
    )
    hay_mas = len(filas) > limite
    filas = filas[:limite]
    cursor = filas[-1].id if filas else desde
    return filas, cursor, hay_mas


def ultimo_cursor(db: Session) -> int:
    from sqlalchemy import func

    return int(db.query(func.max(SyncCambio.id)).scalar() or 0)


def aplicar_push(db: Session, operaciones, usuario: Optional[Usuario]) -> List[schemas.ResultadoPush]:
    return [_aplicar_operacion(db, op, usuario) for op in operaciones]


def _resultado_desde_fila(op: schemas.OperacionPush, fila: SyncOperacion) -> schemas.ResultadoPush:
    datos = fila.resultado or {}
    return schemas.ResultadoPush(
        operacion_id=op.operacion_id,
        estado=_ESTADOS_API.get(fila.estado, "error"),
        detalle=datos.get("detalle"),
        entidad=datos.get("entidad"),
        resultado=datos or None,
    )


def _cerrar(db: Session, registro: SyncOperacion, estado: str, datos: Dict[str, Any]) -> None:
    registro.estado = estado
    registro.resultado = datos or None
    db.add(registro)
    db.commit()


def _aplicar_operacion(db: Session, op: schemas.OperacionPush, usuario: Optional[Usuario]) -> schemas.ResultadoPush:
    operacion_id = str(op.operacion_id)

    existente = db.get(SyncOperacion, operacion_id)
    if existente is not None:
        return _resultado_desde_fila(op, existente)

    registro = SyncOperacion(
        operacion_id=operacion_id,
        usuario_id=usuario.id if usuario is not None else None,
        tipo=op.tipo,
        estado="EN_PROCESO",
        ocurrida_en=op.ocurrida_en,
    )
    db.add(registro)
    try:
        db.commit()
    except IntegrityError:
        # Carrera: otra petición reclamó la misma operación primero.
        db.rollback()
        existente = db.get(SyncOperacion, operacion_id)
        if existente is not None:
            return _resultado_desde_fila(op, existente)
        raise

    handler = HANDLERS.get(op.tipo)
    if handler is None:
        _cerrar(db, registro, "ERROR", {"detalle": f"Operación desconocida: {op.tipo}"})
        return _resultado_desde_fila(op, registro)

    try:
        resultado = handler(db, op.payload, usuario) or {}
    except (SyncConflicto, ValueError) as exc:
        db.rollback()
        _cerrar(db, registro, "CONFLICTO", {"detalle": str(exc)})
        return _resultado_desde_fila(op, registro)
    except HTTPException as exc:
        db.rollback()
        estado = "CONFLICTO" if exc.status_code < 500 else "ERROR"
        _cerrar(db, registro, estado, {"detalle": str(exc.detail)})
        return _resultado_desde_fila(op, registro)
    except Exception as exc:  # noqa: BLE001 — una operación no puede tumbar el lote
        db.rollback()
        _cerrar(db, registro, "ERROR", {"detalle": f"{type(exc).__name__}: {exc}"})
        return _resultado_desde_fila(op, registro)

    _cerrar(db, registro, "OK", resultado)
    return _resultado_desde_fila(op, registro)
