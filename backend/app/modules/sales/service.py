from sqlalchemy.orm import Session
from sqlalchemy import or_, func
from datetime import date, datetime
from app.modules.sales.model import Venta, DetalleVenta, Pago
from app.modules.sales.schemas import VentaCreate, VentaUpdate, PagoCreate
from app.modules.orders.model import Pedido, DetallePedido
from app.modules.clients.model import Client
from app.modules.catalogos.model import Moneda
from app.modules.tasas_cambio import service as tasa_cambio_service
from app.modules.auditoria.service import record_event
from app.modules.users.deps import filtrar_registros_propios
from app.modules.users.model import Usuario

# ------------------------------------------------------------
# Servicios para Ventas (Facturas)
# ------------------------------------------------------------
def _snapshot_venta(venta: Venta) -> dict:
    return {
        "pedido_id": venta.pedido_id,
        "cliente_id": venta.cliente_id,
        "fecha": venta.fecha,
        "total": venta.total,
        "estado": venta.estado,
        "observaciones": venta.observaciones,
    }


def obtener_venta(db: Session, id_venta: int, usuario: Usuario | None = None):
    query = db.query(Venta).filter(Venta.id == id_venta)
    if usuario is not None:
        query = filtrar_registros_propios(query, Venta.creado_por_id, usuario)
    return query.first()

def obtener_ventas(
    db: Session,
    salto: int = 0,
    limite: int = 100,
    buscar: str = None,
    usuario: Usuario | None = None,
):
    query = db.query(Venta)
    if usuario is not None:
        query = filtrar_registros_propios(query, Venta.creado_por_id, usuario)
    if buscar:
        query = query.join(Client).filter(
            or_(
                Venta.estado.ilike(f"%{buscar}%"),
                Venta.observaciones.ilike(f"%{buscar}%"),
                Client.nombre.ilike(f"%{buscar}%")
            )
        )
    return query.offset(salto).limit(limite).all()

def crear_venta_desde_pedido(
    db: Session,
    esquema: VentaCreate,
    permitir_estado_cotizado: bool = False,
    commit: bool = True,
    usuario: Usuario | None = None,
):
    
    pedido_query = db.query(Pedido).filter(Pedido.id == esquema.pedido_id)
    if usuario is not None:
        pedido_query = filtrar_registros_propios(pedido_query, Pedido.creado_por_id, usuario)
    pedido = pedido_query.with_for_update().first()
    if not pedido:
        raise ValueError("El pedido especificado no existe.")

    # 2. Validar estado del pedido
    estados_facturables = ["APROBADO", "PRODUCCION", "TERMINADO", "ENTREGADO"]
    if pedido.estado not in estados_facturables and not (permitir_estado_cotizado and pedido.estado == "COTIZADO"):
        raise ValueError(
            f"El pedido debe estar en estado {', '.join(estados_facturables)} para poder ser facturado. "
            f"Estado actual: {pedido.estado}"
        )

    # 3. Validar si ya existe una factura para este pedido
    venta_existente = db.query(Venta).filter(Venta.pedido_id == esquema.pedido_id).first()
    if venta_existente:
        raise ValueError("Ya existe una factura de venta para este pedido.")

    # 4. Determinar la moneda: si no viene en el request, usar la moneda de la cotización
    moneda_id = esquema.moneda_id or (pedido.cotizacion.moneda_id if pedido.cotizacion else None)
    if not moneda_id:
        raise ValueError("No se pudo determinar la moneda de la factura. Especifica una moneda.")

    # Los precios de los detalles del pedido están fijados en la moneda de la cotización.
    # Facturar en otra moneda sin reconvertir los montos inflaría/corrompería el total
    # (p.ej. total COP declarado como USD). Exigir la moneda original.
    if pedido.cotizacion and moneda_id != pedido.cotizacion.moneda_id:
        raise ValueError(
            "La moneda de la factura debe coincidir con la moneda de la cotización. "
            "Los precios del pedido están fijados en esa moneda."
        )

    # 4b. Tasa de cambio: respetar la fijada en la cotización (la TRM se congela al cotizar).
    #     Solo si el pedido no tiene cotización (o la moneda difiere) se refetchea la tasa vigente.
    tasa_cambio = None
    cot = pedido.cotizacion if pedido.cotizacion else None
    if cot and moneda_id == cot.moneda_id and cot.tasa_cambio:
        tasa_cambio = float(cot.tasa_cambio)
    if not tasa_cambio:
        tasa_cambio = tasa_cambio_service.obtener_tasa_moneda_a_cop(db, moneda_id, esquema.fecha or date.today())

    # Crear cabecera de la venta
    db_venta = Venta(
        pedido_id=esquema.pedido_id,
        cliente_id=pedido.cliente_id,
        moneda_id=moneda_id,
        fecha=esquema.fecha or date.today(),
        total=0.0,
        estado="PENDIENTE",
        tasa_cambio=tasa_cambio,
        total_en_moneda_base=0.0,
        observaciones=esquema.observaciones,
        creado_por_id=usuario.id if usuario is not None else pedido.creado_por_id,
        actualizado_por_id=usuario.id if usuario is not None else pedido.creado_por_id,
    )
    db.add(db_venta)
    db.flush()  # Para obtener db_venta.id

    # 5. Crear detalles de venta a partir de los detalles de pedido
    total = 0.0
    for dp in pedido.detalles:
        subtotal = float(dp.cantidad) * float(dp.precio)
        total += subtotal
        costo_unit = float(dp.costo_unitario) if dp.costo_unitario is not None else None
        if costo_unit is None:
            # Fallback: costo del producto
            costo_unit = float(dp.producto.precio_costo_base) if dp.producto and dp.producto.precio_costo_base is not None else 0.0
        pct_ganancia = float(dp.porcentaje_ganancia) if dp.porcentaje_ganancia is not None else (
            # Clamp: la columna es numeric(5,2) → máx 999.99. Un margen mayor no
            # debe romper la factura con un 500 (mismo fix que en pedidos).
            min(999.99, round(((float(dp.precio) - costo_unit) / costo_unit) * 100, 2)) if costo_unit > 0 else 0.0
        )
        db_detalle = DetalleVenta(
            venta_id=db_venta.id,
            producto_id=dp.producto_id,
            cantidad=dp.cantidad,
            precio=dp.precio,
            costo_unitario=costo_unit,
            porcentaje_ganancia=pct_ganancia,
            utilidad=round(float(dp.precio) - costo_unit, 2),
            descuento=0.0,
        )
        db.add(db_detalle)

    # 6. Actualizar el total de la venta
    db_venta.total = total
    db_venta.total_en_moneda_base = round(total * float(tasa_cambio), 2)
    record_event(
        db,
        actor=usuario,
        action="CREATE",
        entity_type="venta",
        entity_id=db_venta.id,
        after=_snapshot_venta(db_venta),
    )
    # commit=False: el llamador mantiene la transacción atómica (p.ej. conversión de cotización)
    if commit:
        db.commit()
    else:
        db.flush()
    db.refresh(db_venta)
    return db_venta

def actualizar_venta(db: Session, id_venta: int, esquema: VentaUpdate, usuario: Usuario | None = None):
    db_venta = obtener_venta(db, id_venta, usuario)
    if not db_venta:
        return None
    antes = _snapshot_venta(db_venta)
    data = esquema.model_dump(exclude_unset=True)
    for clave, valor in data.items():
        setattr(db_venta, clave, valor)
    if usuario is not None:
        db_venta.actualizado_por_id = usuario.id
    record_event(
        db,
        actor=usuario,
        action="STATE_CHANGE" if "estado" in data else "UPDATE",
        entity_type="venta",
        entity_id=db_venta.id,
        before=antes,
        after=_snapshot_venta(db_venta),
    )
    db.commit()
    db.refresh(db_venta)
    return db_venta

def eliminar_venta(db: Session, id_venta: int, usuario: Usuario | None = None):
    db_venta = obtener_venta(db, id_venta, usuario)
    if not db_venta:
        return False
    # No permitir eliminar una factura con abonos: el FK pago.venta_id es
    # NOT NULL y SQLAlchemy intentaría anularlo (500). Exigir su anulación previa.
    if db_venta.pagos:
        raise ValueError(
            "No se puede eliminar una factura con pagos registrados. "
            "Anula o elimina los pagos asociados primero."
        )
    # La eliminacion en cascada eliminara detalle_venta (ondelete=CASCADE); pago
    # tiene ON DELETE RESTRICT, de modo que sin pagos asociados la BD falla de forma segura.
    record_event(
        db,
        actor=usuario,
        action="DELETE",
        entity_type="venta",
        entity_id=db_venta.id,
        before=_snapshot_venta(db_venta),
    )
    db.delete(db_venta)
    db.commit()
    return True


# ------------------------------------------------------------
# Servicios para Pagos (Abonos)
# ------------------------------------------------------------
def obtener_pago(db: Session, id_pago: int):
    return db.query(Pago).filter(Pago.id == id_pago).first()

def crear_pago(db: Session, esquema: PagoCreate, commit: bool = True, usuario: Usuario | None = None):
    # 1. Obtener la venta con FOR UPDATE para serializar pagos concurrentes:
    #    dos abonos simultáneos no pueden validar el saldo al mismo tiempo.
    venta_query = db.query(Venta).filter(Venta.id == esquema.venta_id)
    if usuario is not None:
        venta_query = filtrar_registros_propios(venta_query, Venta.creado_por_id, usuario)
    venta = venta_query.with_for_update().first()
    if not venta:
        raise ValueError("La venta especificada no existe.")

    # 2. Validar que la venta no este cancelada ni pagada
    if venta.estado == "CANCELADA":
        raise ValueError("No se pueden registrar pagos en una venta cancelada.")
    if venta.estado == "PAGADA":
        raise ValueError("La venta ya se encuentra totalmente pagada.")

    # 3. Determinar tasa de cambio y calcular monto en moneda base
    misma_moneda = esquema.moneda_id == venta.moneda_id
    if misma_moneda:
        # Mismo tipo de moneda: tasa 1:1, no se requiere TRM
        tasa_cambio = 1.0
        monto_en_moneda_base = float(esquema.monto)
    else:
        # Moneda diferente: la tasa_cambio es obligatoria
        if not esquema.tasa_cambio or float(esquema.tasa_cambio) <= 0:
            raise ValueError(
                "La moneda del pago difiere de la moneda de la factura. "
                "Debes proporcionar la tasa de cambio (TRM) para realizar la conversión."
            )
        tasa_cambio = float(esquema.tasa_cambio)
        monto_en_moneda_base = round(float(esquema.monto) * tasa_cambio, 2)

    # 4. Validar metodo de pago valido
    metodos_validos = ['EFECTIVO_COP', 'EFECTIVO_USD', 'EFECTIVO_VES', 'BANCOLOMBIA', 'BANCARIBE', 'ZELLE']
    if esquema.metodo_pago not in metodos_validos:
        raise ValueError(f"Metodo de pago invalido. Debe ser uno de: {metodos_validos}")

    # 5. Validar que el monto (en moneda base) no supere el saldo pendiente
    pagos_previos = db.query(Pago).filter(Pago.venta_id == venta.id).all()
    total_ya_pagado_base = sum(float(p.monto_en_moneda_base) for p in pagos_previos)
    saldo_pendiente_base = float(venta.total) - total_ya_pagado_base

    if monto_en_moneda_base > saldo_pendiente_base + 0.01:  # margen de redondeo de 1 centavo
        raise ValueError(
            f"El monto del pago ({monto_en_moneda_base:,.2f} en moneda base) excede el saldo "
            f"pendiente de la factura ({saldo_pendiente_base:,.2f}). Revisa el monto o la tasa de cambio."
        )

    # 6. Crear el pago
    db_pago = Pago(
        venta_id=esquema.venta_id,
        moneda_id=esquema.moneda_id,
        fecha=esquema.fecha,
        monto=esquema.monto,
        tasa_cambio=tasa_cambio,
        monto_en_moneda_base=monto_en_moneda_base,
        metodo_pago=esquema.metodo_pago,
        referencia=esquema.referencia,
        observaciones=esquema.observaciones
    )
    db.add(db_pago)
    db.flush()

    # 7. Recalcular estado de la venta usando monto_en_moneda_base
    todos_pagos = db.query(Pago).filter(Pago.venta_id == venta.id).all()
    total_pagado_base = sum(float(p.monto_en_moneda_base) for p in todos_pagos)
    total_venta = float(venta.total)

    if total_pagado_base >= total_venta - 0.01:  # margen de redondeo
        venta.estado = "PAGADA"
    elif total_pagado_base > 0.0:
        venta.estado = "ABONADA"
    else:
        venta.estado = "PENDIENTE"

    if usuario is not None:
        venta.actualizado_por_id = usuario.id
    record_event(
        db,
        actor=usuario,
        action="CREATE",
        entity_type="pago",
        entity_id=db_pago.id,
        after={"venta_id": db_pago.venta_id, "monto": db_pago.monto, "metodo_pago": db_pago.metodo_pago},
    )

    # commit=False: el llamador mantiene la transacción atómica (p.ej. conversión de cotización)
    if commit:
        db.commit()
    db.refresh(db_pago)
    return db_pago


# ------------------------------------------------------------
# Reporte de Cuentas por Cobrar
# ------------------------------------------------------------
def obtener_cuentas_por_cobrar(db: Session):
    # Obtener todas las ventas pendientes o abonadas
    ventas = db.query(Venta).filter(
        Venta.estado.in_(["PENDIENTE", "ABONADA"])
    ).all()

    cuentas = []
    for v in ventas:
        pagos = db.query(Pago).filter(Pago.venta_id == v.id).all()
        # Usar monto_en_moneda_base para calcular el total pagado en la moneda base de la venta
        total_pagado = sum(float(p.monto_en_moneda_base) for p in pagos)
        saldo_pendiente = float(v.total) - total_pagado

        if saldo_pendiente > 0.0:
            # Obtener nombre de cliente y codigo de moneda
            cliente_nombre = v.cliente.nombre if v.cliente else "Desconocido"
            moneda_codigo = v.moneda.codigo if v.moneda else "COP"

            cuentas.append({
                "venta_id": v.id,
                "cliente_nombre": cliente_nombre,
                "fecha": v.fecha,
                "total": float(v.total),
                "total_pagado": total_pagado,
                "saldo_pendiente": saldo_pendiente,
                "moneda_codigo": moneda_codigo
            })

    return cuentas
