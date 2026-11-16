"""Sincroniza los pagos originales y la deuda; los abonos siguen en Gastos."""
from decimal import Decimal
from uuid import uuid4

from sqlalchemy.orm import Session

from app.modules.cuentas_por_pagar.model import CuentaPorPagar, DetalleCuentaPorPagar
from app.modules.gastos.model import Gasto
from app.modules.reports.model import MovimientoCaja


def proteger_gasto_entrada(db: Session, gasto_id: int) -> None:
    from app.modules.inventory.model import CompraInventarioMultiple

    gasto = db.get(Gasto, gasto_id)
    historica = gasto is not None and db.query(CompraInventarioMultiple.id).filter_by(
        created_at=gasto.created_at, creado_por_id=gasto.creado_por_id,
    ).first()
    if gasto is not None and (gasto.entrada_inventario_id is not None or historica):
        raise ValueError("Este egreso pertenece a una entrada de inventario. Usa Inventario → Entradas registradas → Corregir entrada para mantener stock, caja y deuda sincronizados.")


def bloquear_deuda_entrada(db: Session, deuda_id: int) -> None:
    from app.modules.inventory.model import CompraInventarioMultiple

    deuda = db.get(CuentaPorPagar, deuda_id)
    if deuda is not None and deuda.origen_tipo == "COMPRA_INVENTARIO_MULTIPLE":
        db.query(CompraInventarioMultiple).filter_by(id=deuda.origen_id).with_for_update().first()
    db.query(CuentaPorPagar).filter_by(id=deuda_id).populate_existing().with_for_update().first()


def marcar_abonos_modificados(db: Session, deuda) -> None:
    from app.modules.inventory.model import CompraInventarioMultiple

    if deuda.origen_tipo == "COMPRA_INVENTARIO_MULTIPLE":
        compra = db.get(CompraInventarioMultiple, deuda.origen_id)
        if compra is not None:
            compra.version += 1


def _difiere(valor_a, valor_b, tolerancia: Decimal) -> bool:
    return abs(Decimal(str(valor_a or 0)) - Decimal(str(valor_b or 0))) > tolerancia


def _pago_vinculado(db: Session, compra_id: int, anterior: dict) -> tuple:
    gasto = db.query(Gasto).filter_by(id=anterior["gasto_id"]).with_for_update().first()
    movimiento = db.query(MovimientoCaja).filter_by(id=anterior["movimiento_caja_id"]).with_for_update().first()
    if gasto is None or movimiento is None or movimiento.referencia != f"Gasto #{gasto.id}":
        raise ValueError("Un pago original fue eliminado por separado. Debe conciliarse antes de corregir la entrada.")
    if gasto.entrada_inventario_id not in (None, compra_id):
        raise ValueError("Un pago está vinculado a otra entrada.")
    if (_difiere(gasto.monto, anterior["monto"], Decimal("0.001"))
            or _difiere(gasto.tasa_cambio, anterior["tasa_cambio"], Decimal("0.000001"))
            or _difiere(movimiento.monto, gasto.monto, Decimal("0.001"))
            or movimiento.metodo_caja_id != anterior["metodo_caja_id"]
            or movimiento.tipo != "SALIDA" or gasto.moneda_id != anterior["moneda_id"]
            or movimiento.moneda_id != gasto.moneda_id
            or _difiere(movimiento.tasa_cambio, gasto.tasa_cambio, Decimal("0.000001"))
            or _difiere(movimiento.monto_en_moneda_base, gasto.monto_en_moneda_base, Decimal("0.01"))):
        raise ValueError("Los pagos cambiaron por fuera de la entrada. Recarga y concilia la diferencia antes de corregir.")
    return gasto, movimiento


def _actualizar_pago(db: Session, contexto, pago: dict, anterior: dict) -> dict:
    from app.modules.inventory.service import _concepto_pago_compra, _detalle_entrada_inventario, _persona_compra

    gasto, movimiento = _pago_vinculado(db, contexto.compra.id, anterior)
    concepto = _concepto_pago_compra(_detalle_entrada_inventario(contexto.lineas), pago["observacion"])
    atributos = {"monto": pago["monto"], "moneda_id": pago["moneda_id"],
        "tasa_cambio": pago["tasa"], "monto_en_moneda_base": pago["monto_cop"], "fecha": contexto.datos.fecha}
    for nombre, valor in atributos.items():
        setattr(gasto, nombre, valor)
        setattr(movimiento, nombre, valor)
    gasto.descripcion, movimiento.concepto = concepto, concepto
    gasto.entrada_inventario_id = contexto.compra.id
    gasto.tipo_gasto_id, gasto.clasificacion = contexto.tipo_gasto_id, contexto.clasificacion
    gasto.observaciones = contexto.datos.observaciones
    gasto.actualizado_por_id = contexto.usuario.id
    movimiento.metodo_caja_id = pago["cuenta"].id
    movimiento.persona_entidad = _persona_compra(db, contexto.usuario, contexto.proveedor.id if contexto.proveedor else None, contexto.proveedor_nombre)
    return {**anterior, "monto": str(pago["monto"]), "tasa_cambio": str(pago["tasa"]),
        "metodo_caja_id": pago["cuenta"].id, "moneda_id": pago["moneda_id"],
        "codigo": pago["cuenta"].moneda.codigo, "observacion": pago["observacion"]}


def _eliminar_pago(db: Session, compra_id: int, anterior: dict) -> None:
    from app.modules.adjuntos.model import Adjunto

    gasto, movimiento = _pago_vinculado(db, compra_id, anterior)
    if db.query(Adjunto.id).filter_by(entidad_tipo="GASTO", entidad_id=gasto.id).first():
        raise ValueError("Este pago tiene comprobantes adjuntos. Revisa sus comprobantes antes de quitarlo de la entrada.")
    db.delete(movimiento)
    db.delete(gasto)


def corregir_pagos(db: Session, contexto, anteriores: list[dict]) -> None:
    from app.modules.inventory.service import _registrar_pagos_compra_multiple

    originales = {pago["pago_id"]: pago for pago in anteriores}
    guardados, nuevos, capturas = [], [], []
    for captura, pago in zip(contexto.datos.pagos, contexto.pagos):
        clave = str(captura.pago_id or uuid4())
        anterior = originales.pop(clave, None)
        if anterior is not None:
            guardados.append(_actualizar_pago(db, contexto, pago, anterior))
        else:
            nuevos.append(pago)
            capturas.append(captura.model_copy(update={"pago_id": clave}))
    for anterior in originales.values():
        _eliminar_pago(db, contexto.compra.id, anterior)
    originales_pagos, originales_datos = contexto.pagos, contexto.datos
    contexto.pagos = nuevos
    contexto.datos = contexto.datos.model_copy(update={"pagos": capturas})
    _registrar_pagos_compra_multiple(db, contexto)
    por_clave = {p["pago_id"]: p for p in guardados + contexto.compra.pagos_json}
    contexto.compra.pagos_json = [por_clave[str(p.pago_id)] for p in originales_datos.pagos]
    contexto.pagos, contexto.datos = originales_pagos, originales_datos


def validar_deuda_corregida(contexto, deuda) -> None:
    aplicado = Decimal("0") if deuda is None else deuda.monto_pagado
    if contexto.saldo_cop < aplicado:
        raise ValueError(
            f"La corrección deja {contexto.saldo_cop:,.2f} COP de deuda original, "
            f"pero ya se aplicaron {aplicado:,.2f} COP en abonos/descuentos desde Gastos. "
            "Revisa esos abonos; no se modificarán ni se creará un saldo negativo."
        )
    if deuda is not None and deuda.pagos and (contexto.proveedor is None or deuda.proveedor_id != contexto.proveedor.id):
        raise ValueError("La deuda ya tiene abonos. No se pueden trasladar esos pagos a otro proveedor desde la corrección de la entrada.")
    if deuda is not None and any(pago.fecha < contexto.datos.fecha for pago in deuda.pagos):
        raise ValueError("La fecha corregida de la entrada no puede ser posterior a un abono ya registrado en Gastos.")


def _gasto_deuda_corregido(db: Session, contexto, deuda) -> None:
    from app.modules.gastos.schemas import GastoCreate
    from app.modules.gastos.service import crear_gasto

    gasto = db.get(Gasto, deuda.gasto_id) if deuda.gasto_id else None
    if contexto.saldo_cop == 0:
        if gasto is not None:
            from app.modules.adjuntos.model import Adjunto
            if db.query(Adjunto.id).filter_by(entidad_tipo="GASTO", entidad_id=gasto.id).first():
                raise ValueError("El gasto de la deuda tiene comprobantes. Revisa esos comprobantes antes de quitar el fiado.")
            deuda.gasto_id = None
            db.flush()
            db.delete(gasto)
        return
    if gasto is None:
        gasto = crear_gasto(db, GastoCreate(tipo_gasto_id=contexto.tipo_gasto_id, moneda_id=1,
            fecha=contexto.datos.fecha, monto=contexto.saldo_cop, descripcion=deuda.descripcion),
            usuario=contexto.usuario, commit=False)
        deuda.gasto_id = gasto.id
        gasto.creado_por_id = contexto.compra.creado_por_id
    gasto.monto = gasto.monto_en_moneda_base = contexto.saldo_cop
    gasto.fecha, gasto.descripcion = contexto.datos.fecha, deuda.descripcion
    gasto.tipo_gasto_id = contexto.tipo_gasto_id
    gasto.clasificacion = contexto.clasificacion or "GASTO_FABRICA"
    gasto.entrada_inventario_id = contexto.compra.id
    gasto.actualizado_por_id = contexto.usuario.id


def corregir_deuda(db: Session, contexto, deuda) -> None:
    from app.modules.inventory.service import _registrar_deuda_compra_multiple, _registrar_detalles_deuda_compra, _detalle_entrada_inventario

    if deuda is None:
        _registrar_deuda_compra_multiple(db, contexto)
        if contexto.compra.cuenta_por_pagar_id:
            creada = db.get(CuentaPorPagar, contexto.compra.cuenta_por_pagar_id)
            creada.creado_por_id = contexto.compra.creado_por_id
            db.get(Gasto, creada.gasto_id).creado_por_id = contexto.compra.creado_por_id
        return
    deuda.monto = deuda.monto_en_moneda_base = contexto.saldo_cop
    if contexto.proveedor is not None:
        deuda.proveedor_id = contexto.proveedor.id
    deuda.fecha, deuda.tipo_gasto_id = contexto.datos.fecha, contexto.tipo_gasto_id
    deuda.descripcion = _detalle_entrada_inventario(contexto.lineas)
    deuda.estado = "PAGADA" if deuda.saldo == 0 else "PENDIENTE"
    db.query(DetalleCuentaPorPagar).filter_by(cuenta_por_pagar_id=deuda.id).delete(synchronize_session=False)
    _registrar_detalles_deuda_compra(db, contexto, deuda)
    _gasto_deuda_corregido(db, contexto, deuda)
