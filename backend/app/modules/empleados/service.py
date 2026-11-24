from sqlalchemy import func, or_
from sqlalchemy.orm import Session, joinedload, selectinload

from app.modules.catalogos.model import Cargo
from app.modules.empleados import model, schemas


def _opciones_cargos():
    """Carga el cargo principal y los adicionales sin N+1."""
    return (
        joinedload(model.Empleado.cargo),
        selectinload(model.Empleado.cargos_asignados).joinedload(model.EmpleadoCargo.cargo),
    )


def obtener_empleado(db: Session, id_empleado: int):
    return (
        db.query(model.Empleado)
        .options(*_opciones_cargos())
        .filter(model.Empleado.id == id_empleado)
        .first()
    )


def obtener_empleados(db: Session, salto: int = 0, limite: int = 100, buscar: str = None):
    query = db.query(model.Empleado).options(*_opciones_cargos())
    if buscar:
        query = query.filter(
            or_(
                model.Empleado.nombre.ilike(f"%{buscar}%"),
                model.Empleado.telefono.ilike(f"%{buscar}%"),
            )
        )
    total = query.count()
    items = query.order_by(model.Empleado.nombre.asc()).offset(salto).limit(limite).all()
    return items, total


def _cargos_ordenados(db: Session, cargo_ids, principal_id) -> list[int]:
    """Valida los cargos y devuelve la lista con el principal primero."""
    ids: list[int] = []
    for cargo_id in cargo_ids or []:
        if cargo_id not in ids:
            ids.append(cargo_id)
    if principal_id is not None:
        if principal_id not in ids:
            ids.insert(0, principal_id)
        else:
            ids = [principal_id] + [i for i in ids if i != principal_id]
    if not ids:
        raise ValueError("Indica al menos un cargo.")
    existentes = {c.id for c in db.query(Cargo).filter(Cargo.id.in_(ids)).all()}
    faltantes = [cargo_id for cargo_id in ids if cargo_id not in existentes]
    if faltantes:
        raise ValueError(f"El cargo #{faltantes[0]} no existe.")
    return ids


def _reemplazar_cargos(db: Session, empleado: model.Empleado, cargo_ids: list[int]) -> None:
    for asignacion in list(empleado.cargos_asignados):
        db.delete(asignacion)
    db.flush()
    for orden, cargo_id in enumerate(cargo_ids):
        db.add(model.EmpleadoCargo(
            empleado_id=empleado.id,
            cargo_id=cargo_id,
            orden=orden,
        ))
    db.flush()
    db.expire(empleado, ["cargos_asignados"])


def crear_empleado(db: Session, esquema: schemas.EmpleadoCreate):
    datos = esquema.model_dump(exclude={"cargo_ids"})
    cargos = _cargos_ordenados(db, esquema.cargo_ids, datos.get("cargo_id"))
    datos["cargo_id"] = cargos[0]
    db_obj = model.Empleado(**datos)
    db.add(db_obj)
    db.flush()
    _reemplazar_cargos(db, db_obj, cargos)
    db.commit()
    db.refresh(db_obj)
    return db_obj


def actualizar_empleado(db: Session, id_empleado: int, esquema: schemas.EmpleadoUpdate):
    db_obj = obtener_empleado(db, id_empleado)
    if not db_obj:
        return None
    datos = esquema.model_dump(exclude_unset=True, exclude={"cargo_ids"})
    if esquema.cargo_ids is not None:
        principal = datos.get("cargo_id")
        if principal is None:
            principal = esquema.cargo_ids[0] if esquema.cargo_ids else db_obj.cargo_id
    else:
        principal = datos.get("cargo_id", db_obj.cargo_id)
    if esquema.cargo_ids is not None:
        cargos = esquema.cargo_ids
    else:
        cargos = [a.cargo_id for a in db_obj.cargos_asignados] or [db_obj.cargo_id]
    cargos = _cargos_ordenados(db, cargos, principal)
    datos["cargo_id"] = cargos[0]
    for campo, valor in datos.items():
        setattr(db_obj, campo, valor)
    _reemplazar_cargos(db, db_obj, cargos)
    db.commit()
    db.refresh(db_obj)
    return db_obj


def crear_cargo_empleado(db: Session, nombre: str) -> Cargo:
    """Crea un cargo desde la pantalla de Empleados (sin salir a Configuración)."""
    nombre = (nombre or "").strip()
    if not nombre:
        raise ValueError("Escribe el nombre del cargo.")
    if len(nombre) > 100:
        raise ValueError("El nombre del cargo no puede superar 100 caracteres.")
    existente = (
        db.query(Cargo)
        .filter(func.lower(Cargo.nombre) == nombre.lower())
        .first()
    )
    if existente:
        return existente
    cargo = Cargo(nombre=nombre)
    db.add(cargo)
    db.commit()
    db.refresh(cargo)
    return cargo


def eliminar_empleado(db: Session, id_empleado: int):
    db_obj = obtener_empleado(db, id_empleado)
    if not db_obj:
        return False
    db.delete(db_obj)
    db.commit()
    return True
