"""Consulta y corrección atómica de una entrada, sin registrar abonos nuevos."""
from copy import deepcopy
from uuid import uuid4

from fastapi.encoders import jsonable_encoder
from sqlalchemy import or_
from sqlalchemy.orm import Session

from app.modules.auditoria.service import record_event
from app.modules.cuentas_por_pagar.model import CuentaPorPagar
from app.modules.inventory import model, service
from app.modules.inventory.entrada_datos import datos_entrada, guardar_captura, validar_autoria
from app.modules.inventory.entrada_pagos import corregir_deuda, corregir_pagos, validar_deuda_corregida
from app.modules.inventory.entrada_stock import corregir_stock
from app.modules.users.deps import filtrar_registros_propios


class ConflictoEntrada(ValueError):
    pass


def listar_entradas(db: Session, usuario, consulta: dict) -> tuple[list, int]:
    query = filtrar_registros_propios(db.query(model.CompraInventarioMultiple), model.CompraInventarioMultiple.creado_por_id, usuario)
    if consulta.get("buscar"):
        patron = f"%{consulta['buscar']}%"
        query = query.filter(or_(model.CompraInventarioMultiple.proveedor_nombre.ilike(patron),
            model.CompraInventarioMultiple.observaciones.ilike(patron)))
    total = query.count()
    compras = query.order_by(model.CompraInventarioMultiple.id.desc()).offset(consulta["offset"]).limit(consulta["limite"]).all()
    return [_resumen_entrada(db, compra) for compra in compras], total


def _deuda_entrada(db: Session, compra):
    return db.get(CuentaPorPagar, compra.cuenta_por_pagar_id) if compra.cuenta_por_pagar_id else None


def _resumen_entrada(db: Session, compra) -> dict:
    deuda = _deuda_entrada(db, compra)
    return {"compra_id": compra.id, "fecha": compra.fecha.isoformat(),
        "proveedor_nombre": compra.proveedor_nombre, "recibido_por": compra.recibido_por,
        "articulos": ", ".join(l["nombre"] for l in compra.lineas_json),
        "total_en_moneda_base": str(compra.total_en_moneda_base),
        "pagado_en_moneda_base": str(compra.pagado_en_moneda_base),
        "saldo_actual": str(deuda.saldo if deuda else 0), "version": compra.version,
        "historica": compra.datos_json is None,
        "cuenta_por_pagar_id": compra.cuenta_por_pagar_id}


def obtener_entrada(db: Session, compra_id: int, usuario):
    compra = db.get(model.CompraInventarioMultiple, compra_id)
    if compra is None:
        return None
    validar_autoria(compra, usuario)
    captura, _, _ = datos_entrada(db, compra)
    deuda = _deuda_entrada(db, compra)
    correcciones = db.query(model.CorreccionEntradaInventario).filter_by(compra_id=compra.id).order_by(model.CorreccionEntradaInventario.id).all()
    return {**_resumen_entrada(db, compra), "datos": captura,
        "original": compra.original_json or captura, "created_at": compra.created_at.isoformat(),
        "abonado_posterior": str(deuda.monto_pagado if deuda else 0),
        "descontado_posterior": str(deuda.monto_descontado if deuda else 0),
        "historial": [{"motivo": c.motivo, "fecha": c.created_at.isoformat(),
            "usuario_id": c.usuario_id, "antes": c.antes_json, "despues": c.despues_json} for c in correcciones]}


def _contexto_correccion(db: Session, compra, entrada, usuario):
    lineas, total = service._preparar_lineas_compra_multiple(db, entrada.lineas)
    pagos, pagado = service._preparar_pagos_compra_multiple(db, entrada.pagos)
    if pagado > total:
        raise ValueError("Los pagos indicados superan el total corregido. No se modificarán para hacerlos cuadrar automáticamente.")
    saldo = service._centavos(total - pagado)
    proveedor, nombre = service._resolver_proveedor_compra(db, entrada, saldo)
    tipo, clasificacion = service._tipo_gasto_compra_multiple(db, lineas)
    return service.CompraMultipleContext(datos=entrada, usuario=usuario, lineas=lineas, pagos=pagos,
        compra=compra, proveedor=proveedor, proveedor_nombre=nombre,
        tipo_gasto_id=tipo, clasificacion=clasificacion, total_cop=total, saldo_cop=saldo)


def _actualizar_cabecera(contexto) -> None:
    compra = contexto.compra
    if compra.fecha.date() != contexto.datos.fecha:
        compra.fecha = service._fecha_movimiento(contexto.datos.fecha)
    compra.proveedor_id = contexto.proveedor.id if contexto.proveedor else None
    compra.proveedor_nombre = contexto.proveedor_nombre
    compra.recibido_por = contexto.datos.recibido_por
    compra.observaciones = contexto.datos.observaciones
    compra.total_en_moneda_base = contexto.total_cop
    compra.pagado_en_moneda_base = contexto.total_cop - contexto.saldo_cop
    compra.saldo_en_moneda_base = contexto.saldo_cop
    compra.version += 1
    compra.actualizado_por_id = contexto.usuario.id
    guardar_captura(compra, contexto.datos)


def _reintento_correccion(db: Session, compra_id: int, solicitud):
    existente = db.query(model.CorreccionEntradaInventario).filter_by(operacion_id=str(solicitud.operacion_id)).first()
    if existente is None:
        return None
    if existente.compra_id != compra_id or existente.solicitud_json != solicitud.model_dump(mode="json"):
        raise ConflictoEntrada("Este identificador ya se usó para otra corrección. Recarga la entrada.")
    return existente.respuesta_json


def _normalizar_claves(entrada):
    return entrada.model_copy(update={
        "lineas": [l.model_copy(update={"linea_id": l.linea_id or uuid4()}) for l in entrada.lineas],
        "pagos": [p.model_copy(update={"pago_id": p.pago_id or uuid4()}) for p in entrada.pagos],
    })


def corregir_entrada(db: Session, compra_id: int, solicitud, usuario) -> dict:
    compra = db.query(model.CompraInventarioMultiple).filter_by(id=compra_id).with_for_update().first()
    if compra is None:
        raise ValueError("La entrada de inventario no existe.")
    validar_autoria(compra, usuario)
    reintento = _reintento_correccion(db, compra_id, solicitud)
    if reintento is not None:
        return reintento
    if compra.version != solicitud.version:
        raise ConflictoEntrada("Otra persona corrigió esta entrada. Cierra y vuelve a abrirla para ver los datos vigentes; tu cambio no se aplicó.")
    if str(solicitud.entrada.operacion_id) != compra.operacion_id:
        raise ValueError("La solicitud no corresponde a esta entrada.")
    service._fecha_movimiento(solicitud.entrada.fecha)
    return _aplicar_correccion(db, compra, solicitud, usuario)


def _aplicar_correccion(db: Session, compra, solicitud, usuario) -> dict:
    antes, lineas, pagos = datos_entrada(db, compra)
    contexto = _contexto_correccion(db, compra, _normalizar_claves(solicitud.entrada), usuario)
    deuda = None
    if compra.cuenta_por_pagar_id:
        deuda = db.query(CuentaPorPagar).filter_by(id=compra.cuenta_por_pagar_id).populate_existing().with_for_update().one()
    validar_deuda_corregida(contexto, deuda)
    if compra.original_json is None:
        compra.original_json = deepcopy(antes)
    corregir_stock(db, contexto, lineas)
    corregir_pagos(db, contexto, pagos)
    corregir_deuda(db, contexto, deuda)
    _actualizar_cabecera(contexto)
    db.flush()
    respuesta = {**service._respuesta_compra_multiple(compra), "version": compra.version,
        "saldo_actual": _resumen_entrada(db, compra)["saldo_actual"]}
    _registrar_correccion(db, contexto, solicitud, (antes, respuesta))
    return respuesta


def _registrar_correccion(db: Session, contexto, solicitud, anteriores: tuple) -> None:
    antes, respuesta = anteriores
    db.add(model.CorreccionEntradaInventario(compra_id=contexto.compra.id,
        operacion_id=str(solicitud.operacion_id), solicitud_json=solicitud.model_dump(mode="json"),
        respuesta_json=jsonable_encoder(respuesta), motivo=solicitud.motivo,
        antes_json=antes, despues_json=deepcopy(contexto.compra.datos_json), usuario_id=contexto.usuario.id))
    record_event(db, actor=contexto.usuario, action="UPDATE", entity_type="entrada_inventario",
        entity_id=contexto.compra.id, before=antes,
        after={**contexto.compra.datos_json, "motivo_correccion": solicitud.motivo})
