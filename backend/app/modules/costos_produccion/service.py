from sqlalchemy.orm import Session, joinedload
from typing import List, Optional

from app.modules.costos_produccion import model, schemas
from app.modules.catalogos.model import Area


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


def crear_precio(db: Session, esquema: schemas.PrecioProduccionCreate) -> model.PrecioProduccion:
    _validar_area(db, esquema.area_id)
    obj = model.PrecioProduccion(**esquema.model_dump())
    db.add(obj)
    db.commit()
    db.refresh(obj)
    return obj


def actualizar_precio(
    db: Session, precio_id: int, esquema: schemas.PrecioProduccionUpdate
) -> Optional[model.PrecioProduccion]:
    obj = db.query(model.PrecioProduccion).filter(model.PrecioProduccion.id == precio_id).first()
    if not obj:
        return None
    data = esquema.model_dump(exclude_unset=True)
    if "area_id" in data:
        _validar_area(db, data["area_id"])
    for campo, valor in data.items():
        setattr(obj, campo, valor)
    db.commit()
    db.refresh(obj)
    return obj


def eliminar_precio(db: Session, precio_id: int) -> bool:
    obj = db.query(model.PrecioProduccion).filter(model.PrecioProduccion.id == precio_id).first()
    if not obj:
        return False
    db.delete(obj)
    db.commit()
    return True
