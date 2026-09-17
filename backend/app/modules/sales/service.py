from sqlalchemy.orm import Session, joinedload
from sqlalchemy import or_
from datetime import date, datetime
from decimal import Decimal
from app.core.redondeo import PASO_PRECIO_COP, redondear_a_multiplo
from app.core.hora_ve import hoy_ve
from app.modules.sales.model import Venta, DetalleVenta, Pago, DescuentoVenta
from app.modules.sales.schemas import VentaCreate, VentaUpdate, PagoCreate, DescuentoCreate
from app.modules.orders.model import Pedido, DetallePedido
from app.modules.clients.model import Client
from app.modules.catalogos.model import Moneda
from app.modules.tasas_cambio import service as tasa_cambio_service
from app.modules.tasas_cambio.model import TasaCambio
from app.modules.productos import service as productos_service
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
    query = db.query(Venta).options(joinedload(Venta.pedido))
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
    query = query.order_by(Venta.fecha.desc(), Venta.id.desc())

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
        tasa_cambio = tasa_cambio_service.obtener_tasa_moneda_a_cop(db, moneda_id, esquema.fecha or hoy_ve())

    # Crear cabecera de la venta
    db_venta = Venta(
        pedido_id=esquema.pedido_id,
        cliente_id=pedido.cliente_id,
        moneda_id=moneda_id,
        fecha=esquema.fecha or hoy_ve(),
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
    factor_costo_a_moneda = 1.0
    if moneda_id and moneda_id != 1:
        trm = float(tasa_cambio or 1.0)
        if trm > 0:
            factor_costo_a_moneda = 1.0 / trm
    detalles_venta: list = []
    for dp in pedido.detalles:
        subtotal = float(dp.cantidad) * float(dp.precio)
        total += subtotal
        item_tipo = dp.tipo_item or "FABRICADO"
        material_id = None
        costo_unit = float(dp.costo_unitario) if dp.costo_unitario is not None else None
        if item_tipo == "INSUMO":
            # Costo del material (siempre en COP)
            material_id = dp.material_id
            if costo_unit is None and material_id:
                from app.modules.productos.model import Material
                mat = db.query(Material).filter(Material.id == material_id).first()
                costo_unit = float(mat.costo_base) if mat else 0.0
        elif costo_unit is None:
            if dp.producto and dp.producto.precio_costo_base is not None:
                costo_unit = productos_service.convertir_a_moneda_base(
                    db, dp.producto.moneda_id, float(dp.producto.precio_costo_base)
                ) or 0.0
            else:
                costo_unit = 0.0
        costo_unit_moneda = costo_unit * factor_costo_a_moneda
        pct_ganancia = float(dp.porcentaje_ganancia) if dp.porcentaje_ganancia is not None else (
            min(999.99, round(((float(dp.precio) - costo_unit_moneda) / costo_unit_moneda) * 100, 2)) if costo_unit_moneda > 0 else 0.0
        )
        db_detalle = DetalleVenta(
            venta_id=db_venta.id,
            producto_id=dp.producto_id,
            material_id=material_id,
            tipo_item=item_tipo,
            cantidad=dp.cantidad,
            precio=dp.precio,
            costo_unitario=costo_unit,
            porcentaje_ganancia=pct_ganancia,
            utilidad=round(float(dp.precio) - costo_unit_moneda, 2),
            descuento=0.0,
            descripcion_especifica=dp.descripcion_especifica,
        )
        db.add(db_detalle)
        detalles_venta.append(db_detalle)

    # 6. Actualizar el total de la venta
    db_venta.total = total
    db_venta.total_en_moneda_base = round(total * float(tasa_cambio), 2)
    # 6b. Descontar stock de producto terminado / reventa al facturar.
    costo_real_por_producto = _descontar_stock_productos(db, pedido, db_venta, usuario)
    # 6b'. El costo de lo vendido de stock es el real del inventario, no el
    # estimado de la cotización (utilidad fiel, sobre todo en piezas de
    # exhibición fabricadas cuyo costo lo fijó la producción).
    _aplicar_costo_real_a_detalles(db, detalles_venta, costo_real_por_producto, factor_costo_a_moneda)
    # 6c. Descontar stock de insumos (materiales) al facturar.
    _descontar_stock_materiales(db, pedido, db_venta, usuario)
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
    # No permitir eliminar una factura con abonos o descuentos: los FK son
    # NOT NULL/RESTRICT. Exigir su anulación previa.
    if db_venta.pagos or db_venta.descuentos:
        raise ValueError(
            "No se puede eliminar una factura con pagos o descuentos registrados. "
            "Anula o elimina los pagos y descuentos asociados primero."
        )
    # Devolver al inventario lo descontado al facturar (insumos y reventa)
    # ANTES de borrar: la reversión busca los movimientos SALIDA de esta venta.
    _revertir_stock_venta(db, db_venta)
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


def _totales_cobro(db: Session, venta_id: int) -> tuple[float, float]:
    """Devuelve (total_pagado_base, total_descontado_base) en la moneda de la venta."""
    pagos = db.query(Pago).filter(Pago.venta_id == venta_id).all()
    descuentos = db.query(DescuentoVenta).filter(DescuentoVenta.venta_id == venta_id).all()
    total_pagado = sum(float(p.monto_en_moneda_base) for p in pagos)
    total_descontado = sum(float(d.monto_en_moneda_base) for d in descuentos)
    return total_pagado, total_descontado


def _saldo_pendiente(db: Session, venta: Venta) -> float:
    """Saldo real por cobrar: total − pagado − descontado (moneda de la venta)."""
    total_pagado, total_descontado = _totales_cobro(db, venta.id)
    return float(venta.total) - total_pagado - total_descontado


def _recalcular_estado_venta(db: Session, venta: Venta, margen_saldo: float = 0.01) -> None:
    """PAGADA cuando pagado + descontado cubre el total (con margen de redondeo)."""
    total_pagado, total_descontado = _totales_cobro(db, venta.id)
    if total_pagado + total_descontado >= float(venta.total) - margen_saldo:
        venta.estado = "PAGADA"
    elif total_pagado + total_descontado > 0.0:
        venta.estado = "ABONADA"
    else:
        venta.estado = "PENDIENTE"


def _convertir_a_moneda_venta(
    db: Session, moneda_id: int, monto: float, tasa_cambio: float | None, venta: Venta
) -> tuple[float, float, float]:
    """Convierte un monto (pago o descuento) a la moneda de la venta.

    Misma regla que los cobros: misma moneda → tasa 1:1; moneda distinta →
    tasa obligatoria con validaciones anti-TRM-inventada y redondeo al millar
    cuando la factura es en COP. Devuelve (tasa, monto_en_moneda_base, margen).
    """
    misma_moneda = moneda_id == venta.moneda_id
    if misma_moneda:
        return 1.0, float(monto), 0.01
    if not tasa_cambio or float(tasa_cambio) <= 0:
        raise ValueError(
            "La moneda difiere de la moneda de la factura. "
            "Debes proporcionar la tasa de cambio (TRM) para realizar la conversión."
        )
    tasa = float(tasa_cambio)
    monto_base = round(float(monto) * tasa, 2)
    margen_saldo = 0.01
    # Solo cuando la FACTURA es en COP el libro base queda al millar (la
    # moneda mínima en Colombia es 50 COP; el paso YEIKAR es 1.000). La
    # diferencia del redondeo (máx. ±500 COP) se absorbe como ajuste y por
    # eso el margen de saldo sube al paso completo. En facturas USD/VES la
    # base tiene centavos normales (moneda legal) y no se redondea.
    if venta.moneda_id == 1:
        monto_base = float(
            redondear_a_multiplo(
                Decimal(str(monto)) * Decimal(str(tasa)),
                PASO_PRECIO_COP,
                "half_up",
            )
        )
        margen_saldo = float(PASO_PRECIO_COP)

    # Tasa de cambio: validar que no sea absurda. El piso 0.0001 permite
    # tasas invertidas legítimas (COP→USD ≈ 1/3900 = 0.0002564); lo que se
    # bloquea es el monto en moneda base quedando en ~0 (dinero que
    # desaparece del libro) y desviaciones >50% contra la tasa registrada.
    if tasa < 0.0001:
        raise ValueError(
            f"La tasa de cambio ({tasa}) no es válida para un monto en moneda extranjera. "
            "Indica la TRM real del día (COP por unidad de la moneda del pago)."
        )
    if round(monto_base, 2) <= 0:
        raise ValueError(
            "El monto en moneda base queda en 0 con la tasa indicada. "
            "Revisa la TRM."
        )
    # Si el sistema tiene una tasa registrada para esa moneda, la tasa no
    # puede desviarse más de 50% (anti "cobrar en cero" con TRM inventadas
    # mientras exista una real en el catálogo).
    tasa_registrada = db.query(TasaCambio).filter(
        TasaCambio.moneda_origen_id == moneda_id,
        TasaCambio.moneda_destino_id == 1,
    ).order_by(TasaCambio.fecha.desc()).first()
    if tasa_registrada and tasa_registrada.valor > 0:
        vigente = float(tasa_registrada.valor)
        if abs(tasa - vigente) / vigente > 0.5:
            raise ValueError(
                f"La tasa ({tasa}) difiere más de 50% de la tasa registrada "
                f"del día ({vigente}). Usa la TRM real."
            )
    return tasa, monto_base, margen_saldo


def _registrar_movimiento_caja_pago(db: Session, db_pago: Pago, venta: Venta, usuario_id: int | None = None) -> None:
    """Registra el cobro en la cuenta de caja del método de pago (tipo ENTRADA).

    La tasa del movimiento expresa COP por 1 unidad de la moneda del pago:
      - pago en la moneda de la venta → venta.tasa_cambio (1 × TRM de la venta)
      - pago en otra moneda          → pago.tasa_cambio × venta.tasa_cambio
        (p. ej. COP sobre factura USD → (1/TRM) × TRM = 1.0)
    Si la cuenta no existe en el catálogo se crea automáticamente para no
    perder cobros. El movimiento se commitea con el pago (transacción atómica).
    `usuario_id` queda registrado como responsable del cobro (reporte diario).
    """
    if not db_pago.metodo_pago:
        return
    from fastapi import HTTPException
    from app.modules.reports.model import MetodoCaja, MovimientoCaja
    cuenta = db.query(MetodoCaja).filter(MetodoCaja.codigo == db_pago.metodo_pago).first()
    if not cuenta:
        # Hardening: el método de pago debe corresponder a una cuenta del
        # catálogo (metodo_caja). Antes se creaba una cuenta fantasma con el
        # código digitado, ensuciando el catálogo de cuentas.
        raise HTTPException(
            status_code=400,
            detail=f"El método de pago '{db_pago.metodo_pago}' no corresponde a ninguna cuenta. "
            "Verifica las cuentas en Cuentas y Medios de Pago.",
        )
    tasa_caja = round(float(db_pago.tasa_cambio or 1.0) * float(venta.tasa_cambio or 1.0), 6)
    if db_pago.moneda_id != venta.moneda_id and venta.moneda_id == 1:
        # Pago en moneda extranjera sobre factura COP: la caja registra el mismo
        # valor en COP que descuenta del saldo (ya redondeado al millar).
        monto_cop = float(db_pago.monto_en_moneda_base)
    else:
        monto_cop = round(float(db_pago.monto) * tasa_caja, 2)
    db.add(MovimientoCaja(
        metodo_caja_id=cuenta.id,
        usuario_id=usuario_id,
        pago_id=db_pago.id,
        fecha=db_pago.fecha,
        tipo="ENTRADA",
        monto=db_pago.monto,
        moneda_id=db_pago.moneda_id,
        tasa_cambio=tasa_caja,
        monto_en_moneda_base=monto_cop,
        referencia=f"Pago #{db_pago.id}" + (f" · {db_pago.referencia}" if db_pago.referencia else ""),
        observaciones=f"Cobro de {venta.cliente.nombre} · Venta #{venta.id} · {cuenta.nombre}",
    ))


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
    #    (misma regla para pagos y descuentos; el saldo resta ambos).
    tasa_cambio, monto_en_moneda_base, margen_saldo = _convertir_a_moneda_venta(
        db, esquema.moneda_id, float(esquema.monto), esquema.tasa_cambio, venta
    )

    # 4. Validar metodo de pago valido y su coherencia con la moneda del pago.
    #    Un pago en USD no puede entrar a la caja de pesos: el arqueo físico
    #    jamás cuadraría. Métodos → moneda esperada.
    metodos_validos = ['EFECTIVO_COP', 'EFECTIVO_USD', 'EFECTIVO_VES', 'BANCOLOMBIA', 'BANCARIBE', 'ZELLE', 'BINANCE']
    if esquema.metodo_pago not in metodos_validos:
        raise ValueError(f"Metodo de pago invalido. Debe ser uno de: {metodos_validos}")
    METODO_MONEDA = {
        "EFECTIVO_COP": 1, "BANCOLOMBIA": 1,
        "EFECTIVO_USD": 2, "ZELLE": 2, "BINANCE": 2,
        "EFECTIVO_VES": 3, "BANCARIBE": 3,
    }
    moneda_esperada = METODO_MONEDA.get(esquema.metodo_pago)
    if esquema.moneda_id != moneda_esperada:
        raise ValueError(
            f"El método de pago '{esquema.metodo_pago}' corresponde a la moneda COP/USD/VES "
            f"esperada, pero el pago se registró en la moneda {esquema.moneda_id}. "
            "Usa un método compatible (p. ej. ZELLE o EFECTIVO_USD para pagos en USD)."
        )

    # 4b. (validación de tasa absurda y ±50% contra la registrada: ya aplicada
    #     dentro de _convertir_a_moneda_venta para pagos y descuentos por igual)

    # 5. Validar que el monto (en moneda base) no supere el saldo pendiente
    #    (el saldo resta pagos Y descuentos: lo perdonado ya no se puede cobrar).
    saldo_pendiente_base = _saldo_pendiente(db, venta)

    if monto_en_moneda_base > saldo_pendiente_base + margen_saldo:
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

    # 6b. Registrar el cobro en la cuenta de caja del método de pago (mismo commit)
    _registrar_movimiento_caja_pago(db, db_pago, venta, usuario.id if usuario else None)

    # 7. Recalcular estado de la venta usando pagado + descontado
    _recalcular_estado_venta(db, venta, margen_saldo)

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
# Descuentos de cobro (rebaja sin movimiento de caja)
# ------------------------------------------------------------
def obtener_descuento(db: Session, id_descuento: int):
    return db.query(DescuentoVenta).filter(DescuentoVenta.id == id_descuento).first()


def crear_descuento(db: Session, esquema: DescuentoCreate, commit: bool = True, usuario: Usuario | None = None):
    """Registra una rebaja otorgada al cobrar: resta del saldo pendiente con la
    misma lógica multimoneda de los pagos, pero NO genera MovimientoCaja."""
    # 1. Venta con FOR UPDATE: un cobro y un descuento simultáneos no pueden
    #    validar el saldo al mismo tiempo.
    venta_query = db.query(Venta).filter(Venta.id == esquema.venta_id)
    if usuario is not None:
        venta_query = filtrar_registros_propios(venta_query, Venta.creado_por_id, usuario)
    venta = venta_query.with_for_update().first()
    if not venta:
        raise ValueError("La venta especificada no existe.")

    # 2. Validar que la venta no este cancelada ni pagada
    if venta.estado == "CANCELADA":
        raise ValueError("No se pueden registrar descuentos en una venta cancelada.")
    if venta.estado == "PAGADA":
        raise ValueError("La venta ya se encuentra totalmente pagada.")

    # 3. Conversión a la moneda de la venta (misma regla que los pagos).
    tasa_cambio, monto_en_moneda_base, margen_saldo = _convertir_a_moneda_venta(
        db, esquema.moneda_id, float(esquema.monto), esquema.tasa_cambio, venta
    )

    # 4. El descuento no puede exceder el saldo pendiente (pagos + descuentos
    #    previos ya restan).
    saldo_pendiente_base = _saldo_pendiente(db, venta)
    if monto_en_moneda_base > saldo_pendiente_base + margen_saldo:
        raise ValueError(
            f"El descuento ({monto_en_moneda_base:,.2f} en moneda base) excede el saldo "
            f"pendiente de la factura ({saldo_pendiente_base:,.2f}). Revisa el monto o la tasa de cambio."
        )

    # 5. Crear el descuento (SIN movimiento de caja: lo perdonado no es ingreso).
    db_descuento = DescuentoVenta(
        venta_id=esquema.venta_id,
        moneda_id=esquema.moneda_id,
        fecha=esquema.fecha,
        monto=esquema.monto,
        tasa_cambio=tasa_cambio,
        monto_en_moneda_base=monto_en_moneda_base,
        motivo=esquema.motivo,
        observaciones=esquema.observaciones,
        creado_por_id=usuario.id if usuario is not None else None,
    )
    db.add(db_descuento)
    db.flush()

    # 6. Recalcular estado (un descuento puede cerrar la venta: PAGADA).
    _recalcular_estado_venta(db, venta, margen_saldo)

    if usuario is not None:
        venta.actualizado_por_id = usuario.id
    record_event(
        db,
        actor=usuario,
        action="CREATE",
        entity_type="descuento_venta",
        entity_id=db_descuento.id,
        after={"venta_id": db_descuento.venta_id, "monto": db_descuento.monto, "motivo": db_descuento.motivo},
    )

    if commit:
        db.commit()
    db.refresh(db_descuento)
    return db_descuento


def anular_descuento(db: Session, id_descuento: int, usuario: Usuario | None = None):
    """Anula un descuento de cobro: el saldo vuelve a subir y el estado de la
    venta se recalcula (puede volver de PAGADA a ABONADA)."""
    db_descuento = db.query(DescuentoVenta).filter(DescuentoVenta.id == id_descuento).first()
    if not db_descuento:
        return False
    venta_query = db.query(Venta).filter(Venta.id == db_descuento.venta_id)
    if usuario is not None:
        venta_query = filtrar_registros_propios(venta_query, Venta.creado_por_id, usuario)
    venta = venta_query.with_for_update().first()
    if not venta:
        raise ValueError("La venta del descuento no existe o no tienes acceso a ella.")
    if venta.estado == "CANCELADA":
        raise ValueError("No se puede anular un descuento en una venta cancelada.")
    record_event(
        db,
        actor=usuario,
        action="DELETE",
        entity_type="descuento_venta",
        entity_id=db_descuento.id,
        before={"venta_id": db_descuento.venta_id, "monto": db_descuento.monto, "motivo": db_descuento.motivo},
    )
    db.delete(db_descuento)
    db.flush()
    _recalcular_estado_venta(db, venta)
    if usuario is not None:
        venta.actualizado_por_id = usuario.id
    db.commit()
    return True


# ------------------------------------------------------------
# Reporte de Cuentas por Cobrar
# ------------------------------------------------------------
def obtener_cuentas_por_cobrar(db: Session):
    # Obtener todas las ventas pendientes o abonadas (pedido precargado para
    # exponer su estado sin N+1: define si la cuenta está entregada o en proceso).
    ventas = (
        db.query(Venta)
        .options(joinedload(Venta.pedido))
        .filter(Venta.estado.in_(["PENDIENTE", "ABONADA"]))
        .all()
    )

    cuentas = []
    for v in ventas:
        # Usar monto_en_moneda_base para calcular pagado y descontado en la moneda de la venta
        total_pagado, total_descontado = _totales_cobro(db, v.id)
        saldo_pendiente = float(v.total) - total_pagado - total_descontado

        if saldo_pendiente > 0.0:
            # Obtener nombre de cliente y codigo de moneda
            cliente_nombre = v.cliente.nombre if v.cliente else "Desconocido"
            moneda_codigo = v.moneda.codigo if v.moneda else "COP"

            cuentas.append({
                "venta_id": v.id,
                "pedido_id": v.pedido_id,
                "cliente_nombre": cliente_nombre,
                "fecha": v.fecha,
                "total": float(v.total),
                "total_pagado": total_pagado,
                "total_descontado": total_descontado,
                "saldo_pendiente": saldo_pendiente,
                "moneda_codigo": moneda_codigo,
                "pedido_estado": v.pedido_estado,
            })

    return cuentas


# ------------------------------------------------------------
# Descuento de stock de producto terminado / reventa al facturar
# ------------------------------------------------------------
def _descontar_stock_productos(
    db: Session, pedido: Pedido, db_venta: Venta, usuario: Usuario | None = None
) -> dict:
    """
    Al facturar un pedido, descuenta del inventario de productos de REVENTA
    (producto_inventario) las cantidades vendidas. Registra un movimiento SALIDA.

    SOLO aplica a REVENTA. FABRICADO no tiene stock; INSUMO usa su propia función.

    Devuelve {producto_id: costo_promedio} con el costo REAL con el que salió
    cada producto del inventario (None si la fila no tenía costo).
    """
    from app.modules.productos.model import Producto
    from app.modules.inventory.model import ProductoInventario, MovimientoProductoInventario

    costo_real_por_producto: dict = {}
    for dp in pedido.detalles:
        if not dp.producto_id:
            continue
        if (dp.tipo_item or "FABRICADO") != "REVENTA":
            continue
        producto = db.query(Producto).filter(Producto.id == dp.producto_id).first()
        # Reventa (comprado para revender) y piezas de exhibición (fabricadas y
        # en el showroom) se venden del stock: al facturar se descuenta.
        if not producto or not (producto.es_reventa or producto.es_exhibicion):
            continue

        filas = db.query(ProductoInventario).filter(
            ProductoInventario.producto_id == dp.producto_id
        ).with_for_update().all()
        if not filas:
            if producto.es_exhibicion:
                # Pieza de exhibición de alta simple (sin entradas de
                # inventario): se vende con el costo del producto y se da de
                # baja al venderse (se acabó → se borra del listado).
                producto.activo = False
                continue
            raise ValueError(
                f"El producto '{producto.nombre}' es de reventa pero no tiene stock "
                f"registrado en inventario. Registra una entrada primero."
            )

        cantidad_a_vender = Decimal(str(dp.cantidad))
        disponible = sum(f.cantidad or Decimal("0") for f in filas)
        if disponible < cantidad_a_vender:
            raise ValueError(
                f"Stock insuficiente del producto '{producto.nombre}'. "
                f"Disponible: {disponible}, requerido: {cantidad_a_vender}."
            )

        restante = cantidad_a_vender
        for fila in filas:
            if restante <= 0:
                break
            a_descontar = min(restante, fila.cantidad or Decimal("0"))
            if a_descontar <= 0:
                continue
            fila.cantidad = (fila.cantidad or Decimal("0")) - a_descontar
            if fila.costo_promedio is not None:
                costo_real_por_producto[dp.producto_id] = fila.costo_promedio
            db.add(MovimientoProductoInventario(
                producto_id=dp.producto_id,
                ubicacion_id=fila.ubicacion_id,
                tipo="SALIDA",
                cantidad=a_descontar,
                costo_unitario=fila.costo_promedio,
                referencia_tipo="VENTA",
                referencia_id=db_venta.id,
                observaciones=f"Descuento por factura Venta #{db_venta.id}",
            ))
            restante -= a_descontar

        # Pieza de exhibición agotada: se da de baja sola (desaparece del
        # listado; el historial de ventas queda intacto).
        if producto.es_exhibicion:
            queda = sum(f.cantidad or Decimal("0") for f in filas)
            if queda <= 0:
                producto.activo = False

    return costo_real_por_producto


def _aplicar_costo_real_a_detalles(
    db: Session,
    detalles_venta: list,
    costo_real_por_producto: dict,
    factor_costo_a_moneda: float,
) -> None:
    """Los detalles vendidos de stock (REVENTA: reventa y piezas de exhibición)
    reportan el costo REAL con el que salió el inventario (costo_promedio), no
    el estimado de la cotización: la utilidad de la venta refleja lo que la
    pieza costó de verdad.

    `costo_real_por_producto` vive en la moneda del producto y `costo_unitario`
    del detalle en la moneda base (COP): se convierte antes de asignar. Si no
    hay tasa de cambio para el producto se conserva el costo estimado (mejor
    aproximación que inventar una conversión)."""
    from app.modules.productos.model import Producto
    from app.modules.productos.service import convertir_a_moneda_base

    for detalle in detalles_venta:
        costo_real = costo_real_por_producto.get(detalle.producto_id)
        if (detalle.tipo_item or "FABRICADO") != "REVENTA" or costo_real is None:
            continue
        producto = db.query(Producto).filter(Producto.id == detalle.producto_id).first()
        costo_base = convertir_a_moneda_base(
            db, producto.moneda_id if producto else None, float(costo_real)
        )
        if costo_base is None:
            continue
        detalle.costo_unitario = costo_base
        costo_en_moneda_venta = costo_base * factor_costo_a_moneda
        detalle.utilidad = round(float(detalle.precio) - costo_en_moneda_venta, 2)
        detalle.porcentaje_ganancia = (
            min(999.99, round(detalle.utilidad / costo_en_moneda_venta * 100, 2))
            if costo_en_moneda_venta > 0
            else 0.0
        )


def _descontar_stock_materiales(db: Session, pedido: Pedido, db_venta: Venta, usuario: Usuario | None = None):
    """
    Al facturar un pedido, descuenta del inventario de MATERIALES los insumos
    vendidos (tipo_item == INSUMO). Registra MovimientoInventario SALIDA.
    Cantidades fraccionarias soportadas (ej. 0.75 lámina).
    """
    from app.modules.productos.model import Material
    from app.modules.inventory.model import Inventario, MovimientoInventario

    for dp in pedido.detalles:
        if (dp.tipo_item or "FABRICADO") != "INSUMO":
            continue
        if not dp.material_id:
            continue

        material = db.query(Material).filter(Material.id == dp.material_id).first()
        if not material:
            raise ValueError(f"El material con id {dp.material_id} no existe.")

        filas = db.query(Inventario).filter(
            Inventario.material_id == dp.material_id
        ).with_for_update().all()
        if not filas:
            raise ValueError(
                f"El material '{material.nombre}' no tiene stock registrado en inventario."
            )

        cantidad_a_vender = Decimal(str(dp.cantidad))
        disponible = sum(f.cantidad or Decimal("0") for f in filas)
        if disponible < cantidad_a_vender:
            raise ValueError(
                f"Stock insuficiente del material '{material.nombre}'. "
                f"Disponible: {disponible}, requerido: {cantidad_a_vender}."
            )

        restante = cantidad_a_vender
        for fila in filas:
            if restante <= 0:
                break
            a_descontar = min(restante, fila.cantidad or Decimal("0"))
            if a_descontar <= 0:
                continue
            fila.cantidad = (fila.cantidad or Decimal("0")) - a_descontar
            db.add(MovimientoInventario(
                material_id=dp.material_id,
                ubicacion_id=fila.ubicacion_id,
                tipo="SALIDA",
                cantidad=a_descontar,
                costo_unitario=material.costo_base,
                referencia_tipo="VENTA",
                referencia_id=db_venta.id,
                observaciones=f"Descuento por venta de insumo - Venta #{db_venta.id}",
            ))
            restante -= a_descontar


def _revertir_stock_venta(db: Session, db_venta: Venta) -> None:
    """
    Al eliminar una venta, devuelve al inventario lo descontado al facturar:
    insumos (tipo_item INSUMO → inventario de materiales) y productos de
    REVENTA (producto_inventario).

    Revierte cada movimiento SALIDA con referencia VENTA en su MISMA ubicación
    y registra la ENTRADA correspondiente (kardex neto en cero). No toca
    material.costo_base (una re-entrada por anulación no fija precio de costo).
    FABRICADO no revierte nada: se consumió en producción.
    """
    from app.modules.inventory.model import (
        Inventario,
        MovimientoInventario,
        ProductoInventario,
        MovimientoProductoInventario,
    )

    salidas_material = db.query(MovimientoInventario).filter(
        MovimientoInventario.referencia_tipo == "VENTA",
        MovimientoInventario.referencia_id == db_venta.id,
        MovimientoInventario.tipo == "SALIDA",
    ).all()
    for mov in salidas_material:
        fila = db.query(Inventario).filter(
            Inventario.material_id == mov.material_id,
            Inventario.ubicacion_id == mov.ubicacion_id,
        ).with_for_update().first()
        if not fila:
            raise ValueError(
                f"No se puede revertir el stock del material #{mov.material_id}: "
                "la fila de inventario ya no existe. Ajusta el inventario manualmente."
            )
        fila.cantidad = (fila.cantidad or Decimal("0")) + (mov.cantidad or Decimal("0"))
        db.add(MovimientoInventario(
            material_id=mov.material_id,
            ubicacion_id=mov.ubicacion_id,
            tipo="ENTRADA",
            cantidad=mov.cantidad,
            costo_unitario=mov.costo_unitario,
            referencia_tipo="VENTA",
            referencia_id=db_venta.id,
            observaciones=f"Reversión por eliminación de Venta #{db_venta.id}",
        ))

    salidas_producto = db.query(MovimientoProductoInventario).filter(
        MovimientoProductoInventario.referencia_tipo == "VENTA",
        MovimientoProductoInventario.referencia_id == db_venta.id,
        MovimientoProductoInventario.tipo == "SALIDA",
    ).all()
    for mov in salidas_producto:
        fila = db.query(ProductoInventario).filter(
            ProductoInventario.producto_id == mov.producto_id,
            ProductoInventario.ubicacion_id == mov.ubicacion_id,
        ).with_for_update().first()
        if not fila:
            raise ValueError(
                f"No se puede revertir el stock del producto #{mov.producto_id}: "
                "la fila de inventario ya no existe. Ajusta el inventario manualmente."
            )
        fila.cantidad = (fila.cantidad or Decimal("0")) + (mov.cantidad or Decimal("0"))
        db.add(MovimientoProductoInventario(
            producto_id=mov.producto_id,
            ubicacion_id=mov.ubicacion_id,
            tipo="ENTRADA",
            cantidad=mov.cantidad,
            costo_unitario=fila.costo_promedio,
            referencia_tipo="VENTA",
            referencia_id=db_venta.id,
            observaciones=f"Reversión por eliminación de Venta #{db_venta.id}",
        ))
