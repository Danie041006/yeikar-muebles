from sqlalchemy.orm import Session, joinedload
from typing import List, Optional

from app.modules.auditoria.service import record_event
from app.modules.costos_produccion import model, schemas
from app.modules.catalogos.model import Area
from app.modules.users.model import Usuario


def _validar_area(db: Session, area_id: int) -> None:
    if not db.query(Area).filter(Area.id == area_id).first():
        raise ValueError(f"El área con id {area_id} no existe.")


def listar_precios(
    db: Session,
    area_id: Optional[int] = None,
    buscar: Optional[str] = None,
    activo: Optional[bool] = None,
    skip: int = 0,
    limit: int = 500,
) -> List[model.PrecioProduccion]:
    query = db.query(model.PrecioProduccion).options(joinedload(model.PrecioProduccion.area))
    if area_id:
        query = query.filter(model.PrecioProduccion.area_id == area_id)
    if buscar:
        query = query.filter(model.PrecioProduccion.descripcion.ilike(f"%{buscar}%"))
    if activo is not None:
        query = query.filter(model.PrecioProduccion.activo == activo)
    return (
        query.order_by(
            model.PrecioProduccion.area_id,
            model.PrecioProduccion.orden,
            model.PrecioProduccion.id,
        )
        .offset(skip)
        .limit(limit)
        .all()
    )


def _snapshot(obj: model.PrecioProduccion) -> dict:
    return {
        "area_id": obj.area_id,
        "descripcion": obj.descripcion,
        "precio": float(obj.precio) if obj.precio is not None else None,
        "activo": bool(obj.activo),
    }


def crear_precio(
    db: Session,
    esquema: schemas.PrecioProduccionCreate,
    usuario: Usuario | None = None,
) -> model.PrecioProduccion:
    _validar_area(db, esquema.area_id)
    obj = model.PrecioProduccion(**esquema.model_dump())
    db.add(obj)
    db.flush()
    record_event(
        db, actor=usuario, action="CREATE", entity_type="precio_produccion",
        entity_id=obj.id, after=_snapshot(obj),
    )
    db.commit()
    db.refresh(obj)
    return obj


def actualizar_precio(
    db: Session,
    precio_id: int,
    esquema: schemas.PrecioProduccionUpdate,
    usuario: Usuario | None = None,
) -> Optional[model.PrecioProduccion]:
    obj = db.query(model.PrecioProduccion).filter(model.PrecioProduccion.id == precio_id).first()
    if not obj:
        return None
    antes = _snapshot(obj)
    data = esquema.model_dump(exclude_unset=True)
    if "area_id" in data:
        _validar_area(db, data["area_id"])
    for campo, valor in data.items():
        setattr(obj, campo, valor)
    record_event(
        db, actor=usuario, action="UPDATE", entity_type="precio_produccion",
        entity_id=obj.id, before=antes, after=_snapshot(obj),
    )
    db.commit()
    db.refresh(obj)
    return obj


def eliminar_precio(db: Session, precio_id: int, usuario: Usuario | None = None) -> bool:
    obj = db.query(model.PrecioProduccion).filter(model.PrecioProduccion.id == precio_id).first()
    if not obj:
        return False
    # Una tarifa usada por mano de obra se desactiva, no se borra: la FK es
    # ON DELETE SET NULL y el borrado desvinculaba el trabajo histórico.
    from app.modules.production.model import ManoObra

    if db.query(ManoObra.id).filter(ManoObra.precio_produccion_id == precio_id).first():
        raise ValueError(
            "La tarifa está en uso por mano de obra registrada: desactívala en lugar de eliminarla."
        )
    record_event(
        db, actor=usuario, action="DELETE", entity_type="precio_produccion",
        entity_id=precio_id, before=_snapshot(obj),
    )
    db.delete(obj)
    db.commit()
    return True
