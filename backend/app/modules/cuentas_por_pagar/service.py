from datetime import date
from decimal import Decimal
from typing import List, Optional

from sqlalchemy.orm import Session, joinedload

from app.modules.catalogos.model import Moneda, TipoGasto
from app.modules.cuentas_por_pagar import model, schemas
from app.modules.gastos.schemas import GastoCreate
from app.modules.gastos.service import crear_gasto
from app.modules.productos.model import Material
from app.modules.clients.model import Client
from app.modules.proveedores.model import Proveedor
from app.modules.reports.model import MetodoCaja
from app.modules.users.deps import filtrar_registros_propios
from app.modules.users.model import Usuario
from app.modules.auditoria.service import record_event

MONEDA_BASE_ID = 1  # COP
TIPO_GASTO_COMPRA_INSUMOS = "COMPRA DE INSUMOS"


def _validar_fks(db: Session, proveedor_id: int, tipo_gasto_id: int, moneda_id: int) -> Moneda:
    if not db.query(Proveedor).filter(Proveedor.id == proveedor_id).first():
        raise ValueError(f"El proveedor con id {proveedor_id} no existe.")
    if not db.query(TipoGasto).filter(TipoGasto.id == tipo_gasto_id).first():
        raise ValueError(f"El tipo de gasto con id {tipo_gasto_id} no existe.")
    moneda = db.query(Moneda).filter(Moneda.id == moneda_id).first()
    if not moneda:
        raise ValueError(f"La moneda con id {moneda_id} no existe.")
    return moneda


def _validar_detalles(db: Session, detalles: Optional[list[schemas.DetalleCuentaPorPagarCreate]]) -> Decimal:
    """Valida los renglones de una deuda (material/cliente existentes si se
    indican por id) y devuelve la suma de sus totales."""
    if not detalles:
        return Decimal("0.0")
    total = Decimal("0.0")
    for i, det in enumerate(detalles):
        if det.material_id is not None and not db.query(Material).filter(Material.id == det.material_id).first():
            raise ValueError(f"El material con id {det.material_id} del renglón {i + 1} no existe.")
        if det.cliente_id is not None and not db.query(Client).filter(Client.id == det.cliente_id).first():
            raise ValueError(f"El cliente con id {det.cliente_id} del renglón {i + 1} no existe.")
        total += (Decimal(str(det.cantidad)) * Decimal(str(det.precio_unitario))).quantize(Decimal("0.01"))
    return total


def _resolver_tasa(db: Session, moneda: Moneda, fecha: date, tasa_cambio) -> Decimal:
    if moneda.codigo == "COP":
        return Decimal("1.0")
    if tasa_cambio is None:
        from app.modules.tasas_cambio.service import obtener_tasa_moneda_a_cop
        tasa_cambio = obtener_tasa_moneda_a_cop(db, moneda.id, fecha)
    if Decimal(str(tasa_cambio)) <= 0:
        raise ValueError("La tasa de cambio debe ser mayor que cero.")
    return Decimal(str(tasa_cambio))


def _resolver_tipo_compra_insumos(db: Session) -> TipoGasto:
    tipo_gasto = db.query(TipoGasto).filter(TipoGasto.nombre == TIPO_GASTO_COMPRA_INSUMOS).first()
    if not tipo_gasto:
        tipo_gasto = TipoGasto(nombre=TIPO_GASTO_COMPRA_INSUMOS, categoria="OPERATIVO")
        db.add(tipo_gasto)
        db.flush()
    return tipo_gasto


def _snapshot(cxp: model.CuentaPorPagar) -> dict:
    return {
        "proveedor_id": cxp.proveedor_id,
        "monto": cxp.monto,
        "monto_pagado": cxp.monto_pagado,
        "monto_descontado": cxp.monto_descontado,
        "estado": cxp.estado,
        "fecha": cxp.fecha,
    }


def _cantidad_legible(cantidad) -> str:
    """2.0 → "2"; 1.5 → "1.5" (sin ceros de más en el libro)."""
    numero = float(cantidad or 0)
    return str(int(numero)) if numero == int(numero) else f"{numero:g}"


# El concepto de caja debe caber de un vistazo: el nombre del producto (no la
# descripción completa del renglón, que a veces es un párrafo).
_NOMBRE_DEUDA_MAX = 36


def _recortar_nombre(nombre: str) -> str:
    if len(nombre) <= _NOMBRE_DEUDA_MAX:
        return nombre
    recorte = nombre[:_NOMBRE_DEUDA_MAX].rsplit(" ", 1)[0].rstrip(" ,.;:")
    return f"{recorte}…"


def _nombre_renglon_deuda(detalle: model.DetalleCuentaPorPagar) -> str:
    """Nombre corto del renglón: el material del catálogo manda; si el renglón
    es texto libre, se recorta para no arrastrar párrafos al libro."""
    nombre = (detalle.material.nombre if detalle.material is not None else "") or ""
    if not nombre.strip():
        nombre = detalle.descripcion or ""
    return _recortar_nombre(" ".join(nombre.split()))


def descripcion_deuda(cxp: model.CuentaPorPagar) -> str:
    """Qué se fió, en una línea corta: el PRIMER producto y cuántos más hay.

    El libro de caja no debe mostrar "Por Pagar #268" ni párrafos de
    descripción: "2 × MADERA (+1 más)". Si la deuda no tiene renglones se usa
    la descripción de la cabecera, también recortada."""
    textos: list[str] = []
    for detalle in cxp.detalles or []:
        nombre = _nombre_renglon_deuda(detalle)
        if not nombre:
            continue
        cantidad = _cantidad_legible(detalle.cantidad)
        # "1 ×" no aporta nada: solo se escribe la cantidad cuando no es 1.
        textos.append(nombre if cantidad == "1" else f"{cantidad} × {nombre}")
    if textos:
        resumen = textos[0]
        if len(textos) > 1:
            resumen += f" (+{len(textos) - 1} más)"
        return resumen
    return _recortar_nombre(" ".join((cxp.descripcion or "").split()))


def concepto_abono(cxp: model.CuentaPorPagar) -> str:
    """Concepto legible de la salida de caja de un abono.

    Ej.: "Abono de fiado: 2 × MADERA — proveedor JUAN". Es la fuente única del
    texto: lo usan la creación del abono, el libro de caja y el Estado del día.
    """
    descripcion = descripcion_deuda(cxp)
    proveedor = (cxp.proveedor.nombre if cxp.proveedor else "").strip()
    if descripcion:
        return f"Abono de fiado: {descripcion}" + (f" — {proveedor}" if proveedor else "")
    if proveedor:
        return f"Abono de fiado a {proveedor}"
    return f"Abono a Por Pagar #{cxp.id}"


def exponer_concepto_abono(cxp: model.CuentaPorPagar) -> model.CuentaPorPagar:
    """Expone el concepto y la canasta en la respuesta: el modal de abono los
    muestra tal como quedarán en el libro de caja antes de confirmar."""
    cxp.concepto_abono = concepto_abono(cxp)
    cxp.clasificacion = cxp.gasto.clasificacion if cxp.gasto is not None else None
    return cxp


def _registrar_gasto_deuda(
    db: Session,
    cxp: model.CuentaPorPagar,
    usuario,
    clasificacion: Optional[str] = "GASTO_FABRICA",
) -> None:
    """El egreso entra al P&L al nacer la deuda, sin tocar caja: abonar solo
    mueve caja, así el egreso no se duplica en el P&L.

    Fiar es compra de fábrica por defecto (decisión del dueño): el costo nace
    en la canasta "Gastos de Fábrica"; los casos especiales pueden pasar otra
    clasificación."""
    gasto = crear_gasto(
        db,
        GastoCreate(
            tipo_gasto_id=cxp.tipo_gasto_id,
            moneda_id=cxp.moneda_id,
            fecha=cxp.fecha,
            descripcion=cxp.descripcion or f"Deuda con proveedor #{cxp.proveedor_id}",
            monto=cxp.monto,
            tasa_cambio=cxp.tasa_cambio,
            clasificacion=clasificacion,
            observaciones=f"Fiado — Por Pagar #{cxp.id}",
        ),
        commit=False,
        usuario=usuario,
    )
    cxp.gasto_id = gasto.id


def obtener_cuenta(db: Session, cxp_id: int, usuario: Optional[Usuario] = None):
    query = db.query(model.CuentaPorPagar).options(
        joinedload(model.CuentaPorPagar.proveedor),
        joinedload(model.CuentaPorPagar.moneda),
        joinedload(model.CuentaPorPagar.tipo_gasto),
        joinedload(model.CuentaPorPagar.creador),
        joinedload(model.CuentaPorPagar.gasto),
        joinedload(model.CuentaPorPagar.detalles).joinedload(model.DetalleCuentaPorPagar.material),
        joinedload(model.CuentaPorPagar.detalles).joinedload(model.DetalleCuentaPorPagar.cliente),
        joinedload(model.CuentaPorPagar.pagos)
        .joinedload(model.PagoCuentaPorPagar.metodo_caja)
        .joinedload(MetodoCaja.moneda),
        joinedload(model.CuentaPorPagar.pagos).joinedload(model.PagoCuentaPorPagar.creador),
    ).filter(model.CuentaPorPagar.id == cxp_id)
    if usuario is not None:
        query = filtrar_registros_propios(query, model.CuentaPorPagar.creado_por_id, usuario)
    cxp = query.first()
    return exponer_concepto_abono(cxp) if cxp is not None else None


def obtener_cuentas(
    db: Session,
    skip: int = 0,
    limit: int = 100,
    estado: Optional[str] = None,
    proveedor_id: Optional[int] = None,
    usuario: Optional[Usuario] = None,
) -> List[model.CuentaPorPagar]:
    query = db.query(model.CuentaPorPagar).options(
        joinedload(model.CuentaPorPagar.proveedor),
        joinedload(model.CuentaPorPagar.moneda),
        joinedload(model.CuentaPorPagar.tipo_gasto),
        joinedload(model.CuentaPorPagar.creador),
        joinedload(model.CuentaPorPagar.gasto),
        joinedload(model.CuentaPorPagar.detalles).joinedload(model.DetalleCuentaPorPagar.material),
        joinedload(model.CuentaPorPagar.detalles).joinedload(model.DetalleCuentaPorPagar.cliente),
        joinedload(model.CuentaPorPagar.pagos)
        .joinedload(model.PagoCuentaPorPagar.metodo_caja)
        .joinedload(MetodoCaja.moneda),
        joinedload(model.CuentaPorPagar.pagos).joinedload(model.PagoCuentaPorPagar.creador),
    )
    if usuario is not None:
        query = filtrar_registros_propios(query, model.CuentaPorPagar.creado_por_id, usuario)
    if estado:
        query = query.filter(model.CuentaPorPagar.estado == estado.upper())
    if proveedor_id:
        query = query.filter(model.CuentaPorPagar.proveedor_id == proveedor_id)
    cuentas = query.order_by(
        model.CuentaPorPagar.fecha.desc(), model.CuentaPorPagar.id.desc()
    ).offset(skip).limit(limit).all()
    for cxp in cuentas:
        exponer_concepto_abono(cxp)
    return cuentas


def obtener_resumen(db: Session, usuario: Optional[Usuario] = None) -> schemas.ResumenCuentasPorPagar:
    query = db.query(model.CuentaPorPagar).options(
        joinedload(model.CuentaPorPagar.proveedor)
    )
    if usuario is not None:
        query = filtrar_registros_propios(query, model.CuentaPorPagar.creado_por_id, usuario)
    por_proveedor: dict = {}
    total_pendiente = Decimal("0.0")
    total_pagado = Decimal("0.0")
    deudas_pendientes = 0
    for cxp in query.all():
        total_pagado += Decimal(str(cxp.monto_pagado))
        if cxp.estado == "PENDIENTE":
            deudas_pendientes += 1
            saldo = cxp.saldo
            total_pendiente += saldo
            linea = por_proveedor.setdefault(cxp.proveedor_id, {
                "proveedor_id": cxp.proveedor_id,
                "proveedor_nombre": cxp.proveedor.nombre,
                "saldo": Decimal("0.0"),
            })
            linea["saldo"] += saldo
    return schemas.ResumenCuentasPorPagar(
        total_pendiente=total_pendiente.quantize(Decimal("0.01")),
        total_pagado=total_pagado.quantize(Decimal("0.01")),
        total_deudas=deudas_pendientes,
        por_proveedor=[schemas.LineaSaldoProveedor(**linea) for linea in sorted(
            por_proveedor.values(), key=lambda l: l["saldo"], reverse=True
        )],
    )


def crear_cuenta(db: Session, datos: schemas.CuentaPorPagarCreate, usuario: Optional[Usuario] = None) -> model.CuentaPorPagar:
    moneda = _validar_fks(db, datos.proveedor_id, datos.tipo_gasto_id, datos.moneda_id)
    tasa = _resolver_tasa(db, moneda, datos.fecha, datos.tasa_cambio)

    monto = Decimal(str(datos.monto))
    if datos.detalles:
        suma_detalles = _validar_detalles(db, datos.detalles)
        # La cabecera debe cuadrar con sus renglones (tolerancia de centavos).
        if abs(suma_detalles - monto) > Decimal("0.05"):
            raise ValueError(
                f"El monto de la deuda ({monto}) no cuadra con sus renglones (suman {suma_detalles})."
            )

    cxp = model.CuentaPorPagar(
        proveedor_id=datos.proveedor_id,
        tipo_gasto_id=datos.tipo_gasto_id,
        moneda_id=datos.moneda_id,
        fecha=datos.fecha,
        descripcion=datos.descripcion,
        monto=monto,
        tasa_cambio=tasa,
        monto_en_moneda_base=(monto * tasa).quantize(Decimal("0.01")),
        estado="PENDIENTE",
        origen_tipo="MANUAL",
        creado_por_id=usuario.id if usuario is not None else None,
    )
    db.add(cxp)
    db.flush()
    if datos.detalles:
        for i, det in enumerate(datos.detalles):
            db.add(model.DetalleCuentaPorPagar(
                cuenta_por_pagar_id=cxp.id,
                orden=i,
                descripcion=det.descripcion,
                material_id=det.material_id,
                cantidad=det.cantidad,
                precio_unitario=det.precio_unitario,
                cliente_nombre=det.cliente_nombre,
                cliente_id=det.cliente_id,
                observaciones=det.observaciones,
            ))
    _registrar_gasto_deuda(
        db, cxp, usuario, clasificacion=datos.clasificacion or "GASTO_FABRICA"
    )
    record_event(
        db,
        actor=usuario,
        action="CREATE",
        entity_type="cuenta_por_pagar",
        entity_id=cxp.id,
        after=_snapshot(cxp),
    )
    db.commit()
    db.refresh(cxp)
    return exponer_concepto_abono(cxp)


def crear_cuenta_desde_entrada(
    db: Session,
    *,
    proveedor_id: int,
    material_id: Optional[int] = None,
    material_nombre: str = "",
    producto_id: Optional[int] = None,
    producto_nombre: Optional[str] = None,
    cantidad: Decimal,
    costo_unitario: Decimal,
    llevada: Decimal,
    fecha: date,
    movimiento_id: int,
    tipo_gasto_id: Optional[int] = None,
    cliente_id: Optional[int] = None,
    cliente_nombre: Optional[str] = None,
    # Fiar inventario es compra de fábrica: el gasto nace en esa canasta.
    clasificacion: Optional[str] = "GASTO_FABRICA",
    usuario=None,
) -> model.CuentaPorPagar:
    """Deuda nacida de una entrada de inventario sin pagar ("fiar"): el monto
    es compra + pasada. NO hace commit (el llamador lo hace en su transacción)."""
    if not db.query(Proveedor).filter(Proveedor.id == proveedor_id).first():
        raise ValueError(f"El proveedor con id {proveedor_id} no existe.")
    tipo_gasto = (
        db.query(TipoGasto).filter(TipoGasto.id == tipo_gasto_id).first()
        if tipo_gasto_id else _resolver_tipo_compra_insumos(db)
    )
    if tipo_gasto is None:
        tipo_gasto = _resolver_tipo_compra_insumos(db)
    monto = (cantidad * costo_unitario + llevada).quantize(Decimal("0.01"))
    nombre = producto_nombre or material_nombre

    cxp = model.CuentaPorPagar(
        proveedor_id=proveedor_id,
        tipo_gasto_id=tipo_gasto.id,
        moneda_id=MONEDA_BASE_ID,
        fecha=fecha,
        descripcion=f"Compra fiada: {nombre} x{cantidad:g}",
        monto=monto,
        tasa_cambio=Decimal("1.0"),
        monto_en_moneda_base=monto,
        estado="PENDIENTE",
        origen_tipo="ENTRADA_INVENTARIO",
        origen_id=movimiento_id,
        creado_por_id=usuario.id if usuario is not None else None,
    )
    db.add(cxp)
    db.flush()
    # Renglón de la deuda: lo comprado, con el cliente/obra si la
    # entrada lo traía (p. ej. "madera para la obra del cliente X").
    db.add(model.DetalleCuentaPorPagar(
        cuenta_por_pagar_id=cxp.id,
        orden=0,
        descripcion=nombre,
        material_id=material_id,
        cantidad=cantidad,
        precio_unitario=costo_unitario,
        cliente_nombre=cliente_nombre,
        cliente_id=cliente_id,
    ))
    _registrar_gasto_deuda(db, cxp, usuario, clasificacion=clasificacion)
    return cxp


def _calcular_abono_caja(db: Session, cxp: model.CuentaPorPagar, abono: schemas.AbonoCreate):
    """Convierte el abono (en moneda de la deuda) al movimiento de caja (en
    moneda de la cuenta). Una sola tasa manual: '1 [moneda cuenta] = X COP'.
    El equivalente COP usa la tasa de la deuda, que es la que el P&L ya contó."""
    from app.modules.reports.model import MetodoCaja
    cuenta = db.query(MetodoCaja).filter(MetodoCaja.id == abono.metodo_caja_id).first()
    if not cuenta:
        raise ValueError("La cuenta de caja indicada no existe.")
    moneda_cuenta = db.query(Moneda).filter(Moneda.id == (cuenta.moneda_id or MONEDA_BASE_ID)).first()
    if moneda_cuenta is None:
        moneda_cuenta = db.query(Moneda).filter(Moneda.id == MONEDA_BASE_ID).first()
    tasa_cuenta = Decimal(str(abono.tasa_cambio or 1.0))
    if moneda_cuenta.codigo != "COP" and not (tasa_cuenta > 0):
        raise ValueError(f"Indica la tasa de cambio: 1 {moneda_cuenta.codigo} = ? COP")
    if moneda_cuenta.codigo == "COP":
        tasa_cuenta = Decimal("1.0")
    tasa_deuda = Decimal(str(cxp.tasa_cambio or 1.0))
    monto_cuenta = (Decimal(str(abono.monto)) * tasa_deuda / tasa_cuenta).quantize(Decimal("0.01"))
    monto_base = (Decimal(str(abono.monto)) * tasa_deuda).quantize(Decimal("0.01"))
    return cuenta, moneda_cuenta, monto_cuenta, monto_base, tasa_cuenta


def abonar(db: Session, cxp_id: int, abono: schemas.AbonoCreate, usuario: Optional[Usuario] = None) -> model.PagoCuentaPorPagar:
    from app.modules.inventory.entrada_pagos import bloquear_deuda_entrada
    bloquear_deuda_entrada(db, cxp_id)
    cxp = obtener_cuenta(db, cxp_id, usuario)
    if not cxp:
        raise ValueError("La cuenta por pagar no existe.")
    saldo = cxp.saldo
    monto = Decimal(str(abono.monto)).quantize(Decimal("0.01"))
    porcentaje = abono.descuento_porcentaje
    if porcentaje is not None and Decimal(str(porcentaje)) > 0:
        # Regla del negocio: el % se calcula sobre la deuda ORIGINAL, no
        # sobre el monto del abono. Ej.: deuda 9.800.000 con saldo 5.000.000
        # al 5% → 490.000 de descuento; el cajero paga 4.510.000 y la deuda
        # baja los 5.000.000.
        descuento = (
            Decimal(str(cxp.monto)) * Decimal(str(porcentaje)) / Decimal("100")
        ).quantize(Decimal("0.01"))
    else:
        descuento = Decimal(str(abono.descuento or 0)).quantize(Decimal("0.01"))
        porcentaje = None
    if descuento < 0:
        raise ValueError("El descuento no puede ser negativo.")
    # El descuento NO sale de caja: cierra deuda igual que el efectivo, pero
    # el gasto original (el costo) se queda intacto.
    aplicado = (monto + descuento).quantize(Decimal("0.01"))
    if aplicado > saldo + Decimal("0.005"):
        raise ValueError(f"El abono excede el saldo de la deuda (saldo: {saldo}).")
    if descuento <= 0:
        porcentaje = None
    antes = _snapshot(cxp)

    cuenta, moneda_cuenta, monto_cuenta, monto_base, tasa_cuenta = _calcular_abono_caja(db, cxp, abono)
    pago = model.PagoCuentaPorPagar(
        cuenta_por_pagar_id=cxp.id,
        fecha=abono.fecha,
        metodo_caja_id=cuenta.id,
        monto=monto,
        descuento=descuento,
        descuento_porcentaje=porcentaje,
        tasa_cambio=tasa_cuenta,
        monto_en_moneda_base=monto_base,
        creado_por_id=usuario.id if usuario is not None else None,
    )
    db.add(pago)
    db.flush()

    from app.core.caja import registrar_movimiento_caja
    registrar_movimiento_caja(
        db,
        metodo_caja_id=cuenta.id,
        tipo="SALIDA",
        monto=float(monto_cuenta),
        moneda_id=moneda_cuenta.id,
        tasa_cambio=float(tasa_cuenta),
        fecha=abono.fecha,
        referencia=f"CxP #{cxp.id} abono #{pago.id}",
        concepto=concepto_abono(cxp),
        persona_entidad=cxp.proveedor.nombre if cxp.proveedor else None,
        usuario_id=usuario.id if usuario is not None else None,
    )

    cxp.monto_pagado = (Decimal(str(cxp.monto_pagado)) + monto).quantize(Decimal("0.01"))
    cxp.monto_descontado = (Decimal(str(cxp.monto_descontado)) + descuento).quantize(Decimal("0.01"))
    if cxp.saldo <= Decimal("0.005"):
        cxp.estado = "PAGADA"
    from app.modules.inventory.entrada_pagos import marcar_abonos_modificados
    marcar_abonos_modificados(db, cxp)
    record_event(
        db,
        actor=usuario,
        action="UPDATE",
        entity_type="cuenta_por_pagar",
        entity_id=cxp.id,
        before=antes,
    )
    db.commit()
    db.refresh(pago)
    return pago


def eliminar_abono(db: Session, abono_id: int, usuario: Optional[Usuario] = None) -> bool:
    pago = db.query(model.PagoCuentaPorPagar).filter(model.PagoCuentaPorPagar.id == abono_id).first()
    if not pago:
        return False
    from app.modules.inventory.entrada_pagos import bloquear_deuda_entrada
    bloquear_deuda_entrada(db, pago.cuenta_por_pagar_id)
    pago = db.query(model.PagoCuentaPorPagar).filter_by(id=abono_id).populate_existing().with_for_update().first()
    if pago is None:
        return False
    cxp = obtener_cuenta(db, pago.cuenta_por_pagar_id, usuario)
    if not cxp:
        raise ValueError("La cuenta por pagar asociada no existe.")

    from app.modules.reports.model import MovimientoCaja
    db.query(MovimientoCaja).filter(
        MovimientoCaja.referencia == f"CxP #{cxp.id} abono #{pago.id}"
    ).delete(synchronize_session=False)
    cxp.monto_pagado = (Decimal(str(cxp.monto_pagado)) - Decimal(str(pago.monto))).quantize(Decimal("0.01"))
    cxp.monto_descontado = (
        Decimal(str(cxp.monto_descontado)) - Decimal(str(pago.descuento or 0))
    ).quantize(Decimal("0.01"))
    cxp.estado = "PAGADA" if cxp.saldo <= Decimal("0.005") else "PENDIENTE"
    from app.modules.inventory.entrada_pagos import marcar_abonos_modificados
    marcar_abonos_modificados(db, cxp)
    db.delete(pago)
    db.commit()
    return True


def eliminar_cuenta(db: Session, cxp_id: int, usuario: Optional[Usuario] = None) -> bool:
    cxp = obtener_cuenta(db, cxp_id, usuario)
    if not cxp:
        return False
    if cxp.origen_tipo == "COMPRA_INVENTARIO_MULTIPLE":
        raise ValueError("Esta deuda pertenece a una entrada de inventario. Corrige la entrada desde Inventario; sus abonos se administran aquí en Gastos.")
    if Decimal(str(cxp.monto_pagado)) > 0 or Decimal(str(cxp.monto_descontado)) > 0:
        raise ValueError("No se puede eliminar una deuda con abonos. Elimina primero sus abonos.")

    if cxp.gasto_id:
        from app.modules.gastos.model import Gasto
        from app.modules.reports.model import MovimientoCaja
        db.query(MovimientoCaja).filter(
            MovimientoCaja.referencia == f"Gasto #{cxp.gasto_id}"
        ).delete(synchronize_session=False)
        db.query(Gasto).filter(Gasto.id == cxp.gasto_id).delete(synchronize_session=False)
    record_event(
        db,
        actor=usuario,
        action="DELETE",
        entity_type="cuenta_por_pagar",
        entity_id=cxp.id,
        before=_snapshot(cxp),
    )
    db.delete(cxp)
    db.commit()
    return True
