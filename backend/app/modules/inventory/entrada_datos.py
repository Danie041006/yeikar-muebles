"""Captura fiel de las entradas y reconstrucción verificable de las históricas."""
from copy import deepcopy
from decimal import Decimal
from uuid import NAMESPACE_URL, uuid4, uuid5

from sqlalchemy.orm import Session

from app.modules.inventory import model, schemas
from app.modules.gastos.model import Gasto
from app.modules.reports.model import MovimientoCaja
from app.modules.cuentas_por_pagar.model import CuentaPorPagar
from app.modules.users.deps import es_admin_user


def validar_autoria(compra, usuario) -> None:
    if usuario is not None and not es_admin_user(usuario) and compra.creado_por_id != usuario.id:
        raise PermissionError("Solo el autor o Dueño/Administrador puede corregir esta entrada.")


def captura_vigente(compra) -> dict:
    return {
        "operacion_id": compra.operacion_id,
        "fecha": compra.fecha.date().isoformat(),
        "proveedor_id": compra.proveedor_id,
        "proveedor_nombre": compra.proveedor_nombre,
        "recibido_por": compra.recibido_por,
        "observaciones": compra.observaciones,
        "lineas": [_captura_linea(linea) for linea in compra.lineas_json],
        "pagos": deepcopy(compra.pagos_json),
    }


def _captura_linea(linea: dict) -> dict:
    captura = deepcopy(linea)
    captura["material_id" if linea["tipo_item"] == "MATERIAL" else "producto_id"] = linea["item_id"]
    return captura


def guardar_captura(compra, solicitud: schemas.CompraInventarioMultipleCreate) -> None:
    compra.datos_json = captura_vigente(compra)
    if compra.original_json is None:
        compra.original_json = {**deepcopy(compra.datos_json), "_solicitud": solicitud.model_dump(mode="json")}


def renglon_guardado(captura, preparada: dict, movimiento) -> dict:
    return {**captura.model_dump(mode="json", exclude={"nuevo_material", "nuevo_producto"}),
        "linea_id": preparada.get("linea_id") or str(captura.linea_id or uuid4()),
        "tipo_item": preparada["tipo_item"], "item_id": preparada["item_id"],
        "movimiento_id": movimiento.id, "nombre": preparada["nombre"],
        "cantidad": str(preparada["cantidad"]), "unidad": preparada["unidad"],
        "total_en_moneda_base": str(preparada["total_cop"]),
        "moneda_precio_id": preparada["moneda_id"], "tasa_precio_a_cop": str(preparada["tasa_precio"]),
        "ubicacion_id": movimiento.ubicacion_id, "departamento": preparada["departamento"],
        "costo_catalogo_anterior": preparada["costo_catalogo_anterior"]}


def _clave_historica(compra_id: int, origen: str, identificador: int) -> str:
    return str(uuid5(NAMESPACE_URL, f"yeikar:entrada:{compra_id}:{origen}:{identificador}"))


def movimientos_entrada(db: Session, compra) -> dict[str, list]:
    filtros = {"referencia_tipo": "COMPRA_INVENTARIO_MULTIPLE", "referencia_id": compra.id}
    return {
        "MATERIAL": db.query(model.MovimientoInventario).filter_by(**filtros).order_by(model.MovimientoInventario.id).all(),
        "PRODUCTO": db.query(model.MovimientoProductoInventario).filter_by(**filtros).order_by(model.MovimientoProductoInventario.id).all(),
    }


def _lineas_historicas(db: Session, compra) -> list[dict]:
    disponibles = movimientos_entrada(db, compra)
    lineas = []
    for guardada in compra.lineas_json:
        tipo = guardada["tipo_item"]
        coincidencias = [m for m in disponibles[tipo] if (
            (m.material_id if tipo == "MATERIAL" else m.producto_id) == guardada["item_id"]
            and Decimal(str(m.cantidad)) == Decimal(str(guardada["cantidad"]))
        )]
        if not coincidencias:
            raise ValueError("Esta entrada histórica no coincide con su kardex. Debe conciliarse antes de corregirla.")
        movimiento = coincidencias[0]
        disponibles[tipo].remove(movimiento)
        lineas.append({**guardada, "movimiento_id": movimiento.id,
            "linea_id": _clave_historica(compra.id, tipo, movimiento.id),
            "ubicacion_id": movimiento.ubicacion_id, "cliente_nombre": movimiento.cliente_nombre})
    if any(disponibles.values()):
        raise ValueError("La entrada histórica contiene movimientos adicionales sin conciliar.")
    return lineas


def _pagos_historicos(db: Session, compra) -> list[dict]:
    if compra.pagado_en_moneda_base == 0:
        return []
    # NOW() es el inicio de la transacción: cabecera, gastos y caja deben coincidir
    # exactamente. Nunca enlazamos compras por nombres parecidos ni por una fecha aproximada.
    if db.query(model.CompraInventarioMultiple).filter_by(created_at=compra.created_at).count() != 1:
        raise ValueError("Los pagos históricos de esta entrada requieren conciliación manual.")
    deuda = db.get(CuentaPorPagar, compra.cuenta_por_pagar_id) if compra.cuenta_por_pagar_id else None
    gastos = db.query(Gasto).filter_by(created_at=compra.created_at, creado_por_id=compra.creado_por_id).order_by(Gasto.id).all()
    gastos = [g for g in gastos if not deuda or g.id != deuda.gasto_id]
    suma = sum((g.monto_en_moneda_base for g in gastos), Decimal("0"))
    if not gastos or suma != compra.pagado_en_moneda_base:
        raise ValueError("No se pueden identificar con certeza los pagos originales. Debe conciliarse la entrada.")
    return [_pago_historico(db, compra, gasto) for gasto in gastos]


def _pago_historico(db: Session, compra, gasto) -> dict:
    movimientos = db.query(MovimientoCaja).filter_by(referencia=f"Gasto #{gasto.id}").all()
    if len(movimientos) != 1:
        raise ValueError("Un pago histórico no tiene un movimiento de caja único.")
    movimiento = movimientos[0]
    if (movimiento.created_at != compra.created_at or movimiento.monto != gasto.monto
            or movimiento.moneda_id != gasto.moneda_id or movimiento.tipo != "SALIDA"):
        raise ValueError("El pago histórico difiere de su salida de caja. Debe conciliarse antes de corregir.")
    concepto = movimiento.concepto or ""
    observacion = concepto.split(" · Entrada de inventario:", 1)[0] if " · Entrada de inventario:" in concepto else None
    return {"pago_id": _clave_historica(compra.id, "pago", gasto.id),
        "metodo_caja_id": movimiento.metodo_caja_id, "moneda_id": movimiento.moneda_id,
        "codigo": movimiento.moneda.codigo, "monto": str(gasto.monto),
        "tasa_cambio": str(gasto.tasa_cambio), "observacion": observacion,
        "gasto_id": gasto.id, "movimiento_caja_id": movimiento.id}


def datos_entrada(db: Session, compra) -> tuple[dict, list[dict], list[dict]]:
    if compra.datos_json is not None:
        return deepcopy(compra.datos_json), deepcopy(compra.lineas_json), deepcopy(compra.pagos_json)
    lineas = _lineas_historicas(db, compra)
    pagos = _pagos_historicos(db, compra)
    captura = captura_vigente(compra)
    captura["lineas"] = [_captura_linea(linea) for linea in lineas]
    captura["pagos"] = pagos
    return captura, lineas, pagos
