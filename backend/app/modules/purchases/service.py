from sqlalchemy.orm import Session
from typing import List, Optional
from decimal import Decimal
from datetime import datetime

from app.modules.purchases import model, schemas
from app.modules.inventory import service as inventory_service, schemas as inventory_schemas
from app.modules.productos.model import Material


def _ubicacion_entrada(db: Session, preferida: Optional[int] = None) -> int:
    """Resuelve la ubicación destino de una entrada por compra.

    Usa la ubicación preferida si se indica; si no, busca el depósito principal
    (tipo DEPOSITO) con nombre que contenga 'PRINCIPAL'/'DEPOSITO', y cae a la
    primera ubicación activa. Nunca hardcodea a un id mágico.
    """
    from app.modules.catalogos.model import Ubicacion

    if preferida:
        ubi = db.query(Ubicacion).filter(Ubicacion.id == preferida, Ubicacion.activo == True).first()
        if ubi:
            return ubi.id

    ubi = db.query(Ubicacion).filter(
        Ubicacion.activo == True,
        Ubicacion.tipo == "DEPOSITO",
    ).order_by(Ubicacion.nombre).first()
    if ubi:
        return ubi.id

    ubi = db.query(Ubicacion).filter(Ubicacion.activo == True).order_by(Ubicacion.id).first()
    if ubi:
        return ubi.id
    raise ValueError("No hay ninguna ubicación activa. Crea una antes de recibir compras.")


def _actualizar_costo_material(
    db: Session,
    material_id: int,
    cantidad: Decimal,
    costo_unitario: Decimal,
    ubicacion_id: int,
) -> None:
    """
    Actualiza material.costo_base AL INSTANTE con el último precio de compra.

    No se usa promedio ponderado: si el insumo sube, el nuevo precio rige desde
    ya para nuevas cotizaciones/pedidos. Los pedidos YA creados conservan su
    precio congelado (snapshot), así que solo impacta lo nuevo.
    """
    material = db.query(Material).filter(Material.id == material_id).first()
    if not material:
        return
    material.costo_base = Decimal(str(costo_unitario))


def obtener_compra(db: Session, compra_id: int) -> Optional[model.Compra]:
    return db.query(model.Compra).filter(model.Compra.id == compra_id).first()


def obtener_compras(
    db: Session,
    skip: int = 0,
    limit: int = 100,
    proveedor_id: Optional[int] = None,
    fecha_desde: Optional[datetime] = None,
    fecha_hasta: Optional[datetime] = None,
) -> List[model.Compra]:
    query = db.query(model.Compra)
    if proveedor_id:
        query = query.filter(model.Compra.proveedor_id == proveedor_id)
    if fecha_desde:
        query = query.filter(model.Compra.fecha >= fecha_desde)
    if fecha_hasta:
        query = query.filter(model.Compra.fecha <= fecha_hasta)
    return query.order_by(model.Compra.fecha.desc()).offset(skip).limit(limit).all()


def _validar_pago_contado(db: Session, compra, estado: str) -> None:
    """Una compra CONTADO debe indicar de qué cuenta sale el dinero."""
    if compra.tipo_pago == "CONTADO" and estado == "RECIBIDA" and not getattr(compra, "metodo_caja_id", None):
        raise ValueError(
            "La compra es CONTADO: debes indicar el método de caja (metodo_caja_id) "
            "del que sale el dinero al recibirla."
        )


def _movimiento_caja_compra(db: Session, compra: model.Compra, registrar: bool) -> None:
    """Registra (o revierte) la salida de caja de una compra RECIBIDA.

    Cada peso que sale del negocio debe quedar en su cuenta: al recibir una
    compra CONTADO se genera la SALIDA; si la compra deja de estar RECIBIDA
    (cancela/reversa), el movimiento se elimina para no dejar egresos fantasma.
    """
    if compra.tipo_pago != "CONTADO" or not compra.metodo_caja_id:
        return
    from app.modules.reports.model import MovimientoCaja
    referencia = f"Compra #{compra.id}"
    mov = db.query(MovimientoCaja).filter(MovimientoCaja.referencia == referencia).first()
    if registrar and mov is None:
        from app.core.caja import registrar_movimiento_caja
        registrar_movimiento_caja(
            db,
            metodo_caja_id=compra.metodo_caja_id,
            tipo="SALIDA",
            monto=float(compra.total_en_moneda_base or 0),
            moneda_id=1,
            tasa_cambio=1.0,
            fecha=compra.fecha,
            referencia=referencia,
            observaciones=f"Compra #{compra.id} a {compra.proveedor.nombre if compra.proveedor else 'proveedor'}",
        )
    elif not registrar and mov is not None:
        db.delete(mov)
        db.flush()


def crear_compra(db: Session, compra: schemas.CompraCreate) -> model.Compra:
    # Crear registro de compra y sus detalles
    from app.modules.tasas_cambio.service import obtener_tasa_moneda_a_cop
    _validar_pago_contado(db, compra, compra.estado or "BORRADOR")
    tasa_cambio = obtener_tasa_moneda_a_cop(db, compra.moneda_id, compra.fecha)
    total_en_base = sum(
        float(d.cantidad) * float(d.costo_unitario) for d in compra.detalle
    ) * float(tasa_cambio)

    db_compra = model.Compra(
        proveedor_id=compra.proveedor_id,
        moneda_id=compra.moneda_id,
        fecha=compra.fecha,
        estado=compra.estado or "BORRADOR",
        tipo_pago=compra.tipo_pago or "CREDITO",
        metodo_caja_id=compra.metodo_caja_id,
        tasa_cambio=tasa_cambio,
        total_en_moneda_base=round(total_en_base, 2),
        observaciones=compra.observaciones,
    )
    db.add(db_compra)
    db.flush()  # asigna id antes de crear los movimientos

    # Para cada detalle, crear DetalleCompra
    for detalle in compra.detalle:
        db_detalle = model.DetalleCompra(
            compra_id=db_compra.id,
            material_id=detalle.material_id,
            cantidad=detalle.cantidad,
            costo_unitario=detalle.costo_unitario,
        )
        db.add(db_detalle)

    # Registrar movimiento de inventario (entrada) ÚNICAMENTE si está RECIBIDA
    if db_compra.estado == "RECIBIDA":
        ubicacion_id = _ubicacion_entrada(db)
        for detalle in compra.detalle:
            movimiento = inventory_schemas.MovimientoCreate(
                material_id=detalle.material_id,
                ubicacion_id=ubicacion_id,
                tipo="ENTRADA",
                cantidad=detalle.cantidad,
                referencia_tipo="COMPRA",
                referencia_id=db_compra.id,
                observaciones="Entrada por compra",
            )
            inventory_service.registrar_movimiento(db, movimiento)
            # Actualizar costo promedio ponderado del material
            _actualizar_costo_material(
                db, detalle.material_id, detalle.cantidad, detalle.costo_unitario, ubicacion_id
            )
        _movimiento_caja_compra(db, db_compra, registrar=True)

    db.commit()
    db.refresh(db_compra)
    return db_compra


def actualizar_compra(db: Session, compra_id: int, compra_update: schemas.CompraBase) -> Optional[model.Compra]:
    db_compra = obtener_compra(db, compra_id)
    if not db_compra:
        return None
        
    viejo_estado = db_compra.estado
    for attr, value in compra_update.model_dump(exclude_unset=True).items():
        setattr(db_compra, attr, value)
    _validar_pago_contado(db, db_compra, db_compra.estado)

    # Registrar movimiento de inventario (entrada) si transiciona a RECIBIDA.
    # Stock NETO: si hay una reversa previa (SALIDA) por CANCELADA→RECIBIDA,
    # la entrada debe re-registrarse; si el stock ya está, se omite.
    from app.modules.inventory.model import MovimientoInventario
    if viejo_estado != "RECIBIDA" and db_compra.estado == "RECIBIDA":
        try:
            _reentrada_stock_compra(db, db_compra)
        except ValueError as e:
            raise ValueError(f"Error al recibir la compra: {e}")
        _movimiento_caja_compra(db, db_compra, registrar=True)

    # Revertir stock si la compra SALIÓ de RECIBIDA (CANCELADA, BORRADOR, EMITIDA).
    # La entrada de inventario solo tiene validez mientras la compra siga RECIBIDA.
    if viejo_estado == "RECIBIDA" and db_compra.estado != "RECIBIDA":
        _reversa_stock_compra(db, db_compra)
        _movimiento_caja_compra(db, db_compra, registrar=False)

    db.commit()
    db.refresh(db_compra)
    return db_compra


def _stock_neto_compra(db: Session, compra_id: int, material_id: int) -> float:
    """Entradas de inventario de la compra menos sus reversas (SALIDA)."""
    from app.modules.inventory.model import MovimientoInventario
    movs = db.query(MovimientoInventario).filter(
        MovimientoInventario.referencia_tipo == "COMPRA",
        MovimientoInventario.referencia_id == compra_id,
        MovimientoInventario.material_id == material_id,
    ).all()
    neto = 0.0
    for m in movs:
        neto += float(m.cantidad) if m.tipo == "ENTRADA" else -float(m.cantidad)
    return neto


def _reentrada_stock_compra(db: Session, db_compra: model.Compra) -> None:
    """Registra la entrada de stock al pasar a RECIBIDA (idempotente)."""
    for detalle in db_compra.detalles:
        if _stock_neto_compra(db, db_compra.id, detalle.material_id) > 0:
            continue  # el stock ya está contado
        ubicacion_id = _ubicacion_entrada(db)
        movimiento = inventory_schemas.MovimientoCreate(
            material_id=detalle.material_id,
            ubicacion_id=ubicacion_id,
            tipo="ENTRADA",
            cantidad=detalle.cantidad,
            referencia_tipo="COMPRA",
            referencia_id=db_compra.id,
            observaciones="Entrada por compra (actualizada a recibida)",
        )
        inventory_service.registrar_movimiento(db, movimiento)
        _actualizar_costo_material(
            db, detalle.material_id, detalle.cantidad, detalle.costo_unitario, ubicacion_id
        )


def _reversa_stock_compra(db: Session, db_compra: model.Compra) -> None:
    """Revierte el stock al salir de RECIBIDA, con mensaje claro si no alcanza."""
    from app.modules.inventory.model import MovimientoInventario
    movimientos = db.query(MovimientoInventario).filter(
        MovimientoInventario.referencia_tipo == "COMPRA",
        MovimientoInventario.referencia_id == db_compra.id,
    ).all()
    for mov in movimientos:
        if mov.tipo == "ENTRADA":
            for detalle in db_compra.detalles:
                if detalle.material_id == mov.material_id:
                    try:
                        salida = inventory_schemas.MovimientoCreate(
                            material_id=mov.material_id,
                            ubicacion_id=mov.ubicacion_id,
                            tipo="SALIDA",
                            cantidad=mov.cantidad,
                            referencia_tipo="COMPRA",
                            referencia_id=db_compra.id,
                            observaciones=f"Reversa de entrada por compra ({db_compra.estado})",
                        )
                        inventory_service.registrar_movimiento(db, salida)
                    except ValueError as e:
                        raise ValueError(
                            f"No se puede cancelar la compra #{db_compra.id}: "
                            f"el material {detalle.material_id} ya no tiene stock suficiente para revertir. {e}"
                        )


def eliminar_compra(db: Session, compra_id: int) -> bool:
    db_compra = obtener_compra(db, compra_id)
    if not db_compra:
        return False
    db.delete(db_compra)
    db.commit()
    return True
