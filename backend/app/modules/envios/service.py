from datetime import datetime

from sqlalchemy import false, or_
from sqlalchemy.orm import Session, joinedload

from app.modules.auditoria.service import record_event
from app.modules.clients.model import Client
from app.modules.empleados.model import Empleado
from app.modules.envios import schemas
from app.modules.envios.model import Envio, EnvioAsignacion, EnvioUbicacion
from app.modules.orders.model import Pedido
from app.modules.users.deps import tiene_alcance_total
from app.modules.users.model import Usuario
from app.core.state_machine import TRANSICIONES_ENVIO, validar_transicion

# Estados del envío desde los que se permite crear un nuevo intento para el
# mismo pedido (reintento tras un fallo de entrega).
ESTADOS_REINTENTO = {"FALLIDO"}


def _scope_envios(query, usuario: Usuario | None):
    if usuario is None or tiene_alcance_total(usuario):
        return query
    if usuario.empleado_id is None:
        return query.filter(false())
    return query.filter(Envio.empleado_id == usuario.empleado_id)


def _snapshot(envio: Envio) -> dict:
    return {
        "pedido_id": envio.pedido_id,
        "empleado_id": envio.empleado_id,
        "estado": envio.estado,
        "direccion_entrega": envio.direccion_entrega,
        "guia_despacho": envio.guia_despacho,
        "observaciones": envio.observaciones,
        "fecha_salida": envio.fecha_salida,
        "fecha_entrega": envio.fecha_entrega,
    }


def _registrar_asignacion(db: Session, envio: Envio, empleado_id: int | None, usuario: Usuario | None) -> None:
    if envio.empleado_id == empleado_id:
        return

    activa = db.query(EnvioAsignacion).filter(
        EnvioAsignacion.envio_id == envio.id,
        EnvioAsignacion.desasignado_en.is_(None),
    ).all()
    ahora = datetime.now()
    for asignacion in activa:
        asignacion.desasignado_en = ahora

    envio.empleado_id = empleado_id
    envio.asignado_por_usuario_id = usuario.id if usuario else None
    if empleado_id is not None:
        db.add(
            EnvioAsignacion(
                envio_id=envio.id,
                empleado_id=empleado_id,
                asignado_por_usuario_id=usuario.id if usuario else None,
                motivo="Asignación operativa",
            )
        )


def obtener_envio(db: Session, id_envio: int, usuario: Usuario | None = None):
    query = db.query(Envio).options(
        joinedload(Envio.pedido).joinedload(Pedido.cliente),
        joinedload(Envio.pedido).joinedload(Pedido.detalles),
        joinedload(Envio.empleado),
        joinedload(Envio.creador),
        joinedload(Envio.asignado_por),
    ).filter(Envio.id == id_envio)
    return _scope_envios(query, usuario).first()


def obtener_envios(
    db: Session,
    salto: int = 0,
    limite: int = 100,
    buscar: str | None = None,
    estado: str | None = None,
    usuario: Usuario | None = None,
):
    query = db.query(Envio).options(
        joinedload(Envio.pedido).joinedload(Pedido.cliente),
        joinedload(Envio.pedido).joinedload(Pedido.detalles),
        joinedload(Envio.empleado),
        joinedload(Envio.creador),
        joinedload(Envio.asignado_por),
    )
    query = _scope_envios(query, usuario)

    if estado:
        query = query.filter(Envio.estado == estado)

    if buscar:
        query = query.join(Envio.pedido).join(Pedido.cliente).filter(
            or_(
                Client.nombre.ilike(f"%{buscar}%"),
                Envio.guia_despacho.ilike(f"%{buscar}%"),
                Envio.direccion_entrega.ilike(f"%{buscar}%"),
                Envio.observaciones.ilike(f"%{buscar}%"),
            )
        )

    return query.order_by(Envio.id.desc()).offset(salto).limit(limite).all()


def crear_envio(db: Session, esquema: schemas.EnvioCreate, usuario: Usuario | None = None):
    if usuario is not None and not tiene_alcance_total(usuario):
        raise PermissionError("Solo un supervisor puede crear y asignar despachos.")

    pedido = db.query(Pedido).filter(Pedido.id == esquema.pedido_id).with_for_update().first()
    if not pedido:
        raise ValueError("El pedido especificado no existe.")

    existente = db.query(Envio).filter(Envio.pedido_id == esquema.pedido_id).first()
    if existente and existente.estado not in ESTADOS_REINTENTO:
        raise ValueError("Ya existe un registro de envío para este pedido.")

    # Un pedido solo puede entregarse si terminó producción (TERMINADO).
    # No se puede crear un envío directamente ENTREGADO de un pedido que
    # nunca se fabricó.
    if esquema.estado == "ENTREGADO" and pedido.estado not in ("TERMINADO", "ENTREGADO"):
        raise ValueError(
            f"No se puede marcar el envío como ENTREGADO: el pedido está en estado "
            f"'{pedido.estado}'. El pedido debe estar TERMINADO para entregarse."
        )

    datos = esquema.model_dump()
    db_envio = Envio(
        **datos,
        creado_por_id=usuario.id if usuario else pedido.creado_por_id,
        actualizado_por_id=usuario.id if usuario else pedido.creado_por_id,
        asignado_por_usuario_id=usuario.id if usuario and datos.get("empleado_id") else None,
    )
    db.add(db_envio)
    db.flush()
    if db_envio.empleado_id is not None:
        db.add(
            EnvioAsignacion(
                envio_id=db_envio.id,
                empleado_id=db_envio.empleado_id,
                asignado_por_usuario_id=usuario.id if usuario else None,
                motivo="Asignación inicial",
            )
        )

    if esquema.estado == "ENTREGADO":
        db_envio.fecha_entrega = datetime.now()
        pedido.estado = "ENTREGADO"
    elif esquema.estado == "EN_TRANSITO":
        db_envio.fecha_salida = datetime.now()

    record_event(
        db,
        actor=usuario,
        action="CREATE",
        entity_type="envio",
        entity_id=db_envio.id,
        after=_snapshot(db_envio),
    )
    db.commit()
    db.refresh(db_envio)
    return db_envio


def crear_envio_automatico(db: Session, pedido_id: int, usuario: Usuario | None = None):
    pedido = db.query(Pedido).filter(Pedido.id == pedido_id).with_for_update().first()
    existente = db.query(Envio).filter(Envio.pedido_id == pedido_id).first()
    if existente:
        return existente

    direccion = pedido.cliente.direccion if pedido and pedido.cliente else ""
    db_envio = Envio(
        pedido_id=pedido_id,
        estado="PREPARADO",
        direccion_entrega=direccion or "",
        empleado_id=None,
        fecha_salida=None,
        fecha_entrega=None,
        guia_despacho=None,
        observaciones="Creado automáticamente tras finalizar producción.",
        creado_por_id=usuario.id if usuario else (pedido.creado_por_id if pedido else None),
        actualizado_por_id=usuario.id if usuario else (pedido.creado_por_id if pedido else None),
    )
    db.add(db_envio)
    db.flush()
    record_event(
        db,
        actor=usuario,
        action="SYSTEM_CREATE",
        entity_type="envio",
        entity_id=db_envio.id,
        after=_snapshot(db_envio),
    )
    db.commit()
    db.refresh(db_envio)
    return db_envio


def actualizar_envio(
    db: Session,
    id_envio: int,
    esquema: schemas.EnvioUpdate,
    usuario: Usuario | None = None,
):
    query = db.query(Envio).filter(Envio.id == id_envio).with_for_update()
    db_envio = _scope_envios(query, usuario).first()
    if not db_envio:
        return None

    datos = esquema.model_dump(exclude_unset=True)
    if usuario is not None and not tiene_alcance_total(usuario):
        if "empleado_id" in datos and datos["empleado_id"] != db_envio.empleado_id:
            raise PermissionError("No puedes reasignar un despacho.")
        campos_restringidos = {"direccion_entrega", "guia_despacho", "empleado_id"}
        if campos_restringidos.intersection(datos):
            raise PermissionError("Tu rol solo puede actualizar el estado y las novedades de tu despacho.")

    antes = _snapshot(db_envio)
    estado_anterior = db_envio.estado
    nuevo_estado = datos.get("estado")

    # Máquina de estados del envío: PREPARADO→EN_TRANSITO→ENTREGADO/FALLIDO.
    # Prohíbe retrocesos (ENTREGADO→PREPARADO) y transiciones inventadas.
    # Se valida SIEMPRE (aunque el estado no cambie): re-marcar un estado
    # terminal (ENTREGADO/FALLIDO) es rechazado por validar_transicion.
    if nuevo_estado:
        validar_transicion(TRANSICIONES_ENVIO, estado_anterior, nuevo_estado, "envío")
        # Entregar exige que el pedido haya terminado producción. Sin esto, un
        # conductor podía marcar ENTREGADO un pedido que nunca se fabricó.
        if nuevo_estado == "ENTREGADO":
            pedido = db.query(Pedido).filter(Pedido.id == db_envio.pedido_id).first()
            if not pedido:
                raise ValueError("El pedido asociado al envío no existe.")
            if pedido.estado not in ("TERMINADO", "ENTREGADO"):
                raise ValueError(
                    f"No se puede entregar el pedido #{pedido.id}: está en estado "
                    f"'{pedido.estado}'. El pedido debe estar TERMINADO para entregarse."
                )

    empleado_nuevo = datos.get("empleado_id", db_envio.empleado_id)
    if empleado_nuevo != db_envio.empleado_id:
        _registrar_asignacion(db, db_envio, empleado_nuevo, usuario)

    for campo, valor in datos.items():
        setattr(db_envio, campo, valor)

    if nuevo_estado and nuevo_estado != estado_anterior:
        if nuevo_estado == "EN_TRANSITO" and not db_envio.fecha_salida:
            db_envio.fecha_salida = datetime.now()
        elif nuevo_estado == "ENTREGADO":
            db_envio.fecha_entrega = datetime.now()
            pedido = db.query(Pedido).filter(Pedido.id == db_envio.pedido_id).first()
            if pedido:
                pedido.estado = "ENTREGADO"

    if usuario is not None:
        db_envio.actualizado_por_id = usuario.id
    record_event(
        db,
        actor=usuario,
        action="STATE_CHANGE" if nuevo_estado and nuevo_estado != estado_anterior else "UPDATE",
        entity_type="envio",
        entity_id=db_envio.id,
        before=antes,
        after=_snapshot(db_envio),
    )
    db.commit()
    db.refresh(db_envio)
    return db_envio


def eliminar_envio(db: Session, id_envio: int, usuario: Usuario | None = None):
    if usuario is not None and not tiene_alcance_total(usuario):
        raise PermissionError("Solo un supervisor puede eliminar despachos.")
    db_envio = db.query(Envio).filter(Envio.id == id_envio).first()
    if not db_envio:
        return False
    # Borrar un envío EN_TRANSITO o ENTREGADO destruye la evidencia del despacho
    # y puede dejar el pedido "entregado" sin envío que lo respalde.
    if db_envio.estado in ("EN_TRANSITO", "ENTREGADO"):
        raise ValueError(
            f"No se puede eliminar un envío en estado '{db_envio.estado}'. "
            "Solo se eliminan envíos PREPARADO o FALLIDO."
        )
    record_event(
        db,
        actor=usuario,
        action="DELETE",
        entity_type="envio",
        entity_id=db_envio.id,
        before=_snapshot(db_envio),
    )
    db.delete(db_envio)
    db.commit()
    return True


def registrar_ubicacion(
    db: Session,
    id_envio: int,
    datos: schemas.EnvioUbicacionCreate,
    usuario: Usuario,
):
    envio = db.query(Envio).filter(Envio.id == id_envio).first()
    if not envio:
        raise LookupError("Envío no encontrado.")
    # Primero el permiso: un no-repartidor no debe poder inferir la existencia/
    # estado de un envío ajeno a través de un 409 (fuga de información).
    if not tiene_alcance_total(usuario) and usuario.empleado_id != envio.empleado_id:
        raise PermissionError("Solo el repartidor asignado puede reportar su ubicación.")
    if envio.estado == "ENTREGADO":
        raise ValueError("El seguimiento finalizó porque el pedido ya fue entregado.")

    ubicacion = EnvioUbicacion(
        envio_id=envio.id,
        empleado_id=usuario.empleado_id,
        reportado_por_id=usuario.id,
        **datos.model_dump(),
    )
    db.add(ubicacion)
    db.flush()
    record_event(
        db,
        actor=usuario,
        action="LOCATION_UPDATE",
        entity_type="envio",
        entity_id=envio.id,
        after={"latitud": datos.latitud, "longitud": datos.longitud, "fuente": datos.fuente},
    )
    db.commit()
    db.refresh(ubicacion)
    return ubicacion


def obtener_ubicaciones(db: Session, id_envio: int, usuario: Usuario):
    envio = obtener_envio(db, id_envio, usuario)
    if not envio:
        return None, []
    ubicaciones = db.query(EnvioUbicacion).filter(
        EnvioUbicacion.envio_id == id_envio
    ).order_by(EnvioUbicacion.recibida_en.desc()).limit(500).all()
    return envio, ubicaciones
