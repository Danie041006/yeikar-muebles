"""Correcciones del kardex: diferencias de existencias, sin simular compras nuevas."""
from collections import defaultdict
from decimal import Decimal
from datetime import datetime, time
from uuid import uuid4

from sqlalchemy import or_
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from app.modules.inventory import model
from app.modules.productos.model import Material, Producto


TIPOS_STOCK = {
    "MATERIAL": (model.MovimientoInventario, model.Inventario, "material_id"),
    "PRODUCTO": (model.MovimientoProductoInventario, model.ProductoInventario, "producto_id"),
}


def _stock_bloqueado(db: Session, clave: tuple):
    tipo, identificador, ubicacion_id = clave
    _, tabla, campo = TIPOS_STOCK[tipo]
    filtros = {campo: identificador, "ubicacion_id": ubicacion_id}
    fila = db.query(tabla).filter_by(**filtros).with_for_update().first()
    if fila is not None:
        return fila
    try:
        with db.begin_nested():
            fila = tabla(**filtros, cantidad=Decimal("0"))
            db.add(fila)
            db.flush()
    except IntegrityError:
        fila = db.query(tabla).filter_by(**filtros).with_for_update().one()
    return fila


def _clave_stock(linea: dict) -> tuple:
    return linea["tipo_item"], linea["item_id"], linea["ubicacion_id"]


def _validar_dependencias(db: Session, anterior: dict, nueva: dict | None, fecha) -> None:
    if nueva and _clave_stock(anterior) == _clave_stock(nueva) and Decimal(str(anterior["cantidad"])) == nueva["cantidad"] and fecha == anterior["fecha_dia"]:
        return
    tabla, _, campo = TIPOS_STOCK[anterior["tipo_item"]]
    posterior = tabla.id > anterior["movimiento_id"]
    if fecha < anterior["fecha_dia"]:
        posterior = or_(posterior, tabla.fecha >= datetime.combine(fecha, time.min))
    posteriores = db.query(tabla).filter(
        getattr(tabla, campo) == anterior["item_id"], tabla.ubicacion_id == anterior["ubicacion_id"],
        or_(tabla.referencia_tipo.is_(None), tabla.referencia_tipo != "COMPRA_INVENTARIO_MULTIPLE", tabla.referencia_id != anterior["compra_id"]),
        posterior,
    ).order_by(tabla.id).first()
    if posteriores is not None:
        raise ValueError(
            f"No se puede cambiar el artículo, cantidad, ubicación o fecha de '{anterior['nombre']}': "
            f"tiene un movimiento posterior ({posteriores.tipo}, {posteriores.fecha:%d/%m/%Y}). "
            "Revisa ese movimiento primero. Los demás datos de la entrada sí pueden corregirse."
        )


def _validar_costo_anterior(db: Session, anterior: dict, nueva: dict | None) -> None:
    if nueva and _clave_stock(anterior) == _clave_stock(nueva):
        return
    if anterior.get("costo_catalogo_anterior") is not None:
        return
    tabla, _, campo = TIPOS_STOCK[anterior["tipo_item"]]
    previa = db.query(tabla.id).filter(
        getattr(tabla, campo) == anterior["item_id"], tabla.tipo == "ENTRADA",
        tabla.id != anterior["movimiento_id"], tabla.costo_unitario > 0,
    ).first()
    if previa is None:
        raise ValueError(f"La entrada histórica de '{anterior['nombre']}' no conserva su costo anterior. Debe conciliarse antes de sustituir el artículo.")


def _movimiento_bloqueado(db: Session, linea: dict):
    tabla, _, _ = TIPOS_STOCK[linea["tipo_item"]]
    movimiento = db.query(tabla).filter_by(id=linea["movimiento_id"]).with_for_update().first()
    if movimiento is None or movimiento.referencia_tipo != "COMPRA_INVENTARIO_MULTIPLE" or movimiento.referencia_id != linea["compra_id"]:
        raise ValueError("El kardex de esta entrada cambió. Recarga antes de corregir.")
    return movimiento


def _preparar_cambio_stock(db: Session, contexto, anteriores: list[dict]) -> dict:
    from app.modules.inventory.service import _ubicacion_deposito_predeterminada

    nuevas = {}
    for captura, preparada in zip(contexto.datos.lineas, contexto.lineas):
        preparada["linea_id"] = str(captura.linea_id or uuid4())
        preparada["ubicacion_id"] = preparada["ubicacion_id"] or _ubicacion_deposito_predeterminada(db)
        nuevas[preparada["linea_id"]] = preparada
    claves = {_clave_stock(linea) for linea in anteriores + list(nuevas.values())}
    for clave in sorted(claves):
        _stock_bloqueado(db, clave)
    for anterior in anteriores:
        anterior["compra_id"] = contexto.compra.id
        anterior["fecha_dia"] = contexto.compra.fecha.date()
        nueva = nuevas.get(anterior["linea_id"])
        _validar_dependencias(db, anterior, nueva, contexto.datos.fecha)
        _validar_costo_anterior(db, anterior, nueva)
    _validar_articulos_agregados(db, contexto, (anteriores, nuevas))
    return nuevas


def _validar_articulos_agregados(db: Session, contexto, renglones: tuple) -> None:
    anteriores, nuevas = renglones
    claves_previas = {_clave_stock(linea) for linea in anteriores}
    for nueva in nuevas.values():
        if _clave_stock(nueva) in claves_previas:
            continue
        tabla, _, campo = TIPOS_STOCK[nueva["tipo_item"]]
        posterior = db.query(tabla.id).filter(
            getattr(tabla, campo) == nueva["item_id"], tabla.ubicacion_id == nueva["ubicacion_id"],
            tabla.fecha >= contexto.compra.fecha,
        ).first()
        if posterior is not None:
            raise ValueError(f"'{nueva['nombre']}' tiene movimientos posteriores a la entrada que estás corrigiendo. Revisa su historial antes de agregarlo a esa fecha.")


def _aplicar_diferencias(db: Session, anteriores: list[dict], nuevas: list[dict]) -> None:
    diferencias = defaultdict(lambda: Decimal("0"))
    for linea in anteriores:
        diferencias[_clave_stock(linea)] -= Decimal(str(linea["cantidad"]))
    for linea in nuevas:
        diferencias[_clave_stock(linea)] += Decimal(str(linea["cantidad"]))
    for clave, diferencia in sorted(diferencias.items()):
        inventario = _stock_bloqueado(db, clave)
        if inventario.cantidad + diferencia < 0:
            raise ValueError("La corrección dejaría existencias negativas. Revisa las salidas del artículo antes de continuar.")
        inventario.cantidad += diferencia


def _atributos_movimiento(contexto, preparada: dict) -> dict:
    from app.modules.inventory.service import _fecha_movimiento

    fecha = contexto.compra.fecha if contexto.compra.fecha.date() == contexto.datos.fecha else _fecha_movimiento(contexto.datos.fecha)
    return {"tipo": "ENTRADA", "cantidad": preparada["cantidad"],
        "ubicacion_id": preparada["ubicacion_id"], "costo_unitario": preparada["costo_unitario"],
        "llevada": preparada["llevada_movimiento"], "fecha": fecha,
        "proveedor_id": contexto.proveedor.id if contexto.proveedor else None,
        "proveedor_nombre": contexto.proveedor_nombre, "cliente_nombre": preparada["cliente_nombre"],
        "cliente_id": None, "observaciones": preparada["observaciones"],
        "descuento_porcentaje": preparada["descuento_porcentaje"],
        "referencia_tipo": "COMPRA_INVENTARIO_MULTIPLE", "referencia_id": contexto.compra.id}


def _corregir_renglon(db: Session, contexto, preparada: dict, anterior: dict | None):
    tabla, _, campo = TIPOS_STOCK[preparada["tipo_item"]]
    conserva = anterior and anterior["tipo_item"] == preparada["tipo_item"]
    movimiento = _movimiento_bloqueado(db, anterior) if conserva else tabla()
    if anterior and not conserva:
        db.delete(_movimiento_bloqueado(db, anterior))
    atributos = {**_atributos_movimiento(contexto, preparada), campo: preparada["item_id"]}
    if preparada["tipo_item"] == "MATERIAL":
        atributos.update(departamento=preparada["departamento"], recibido_por=contexto.datos.recibido_por)
    for nombre, valor in atributos.items():
        setattr(movimiento, nombre, valor)
    db.add(movimiento)
    db.flush()
    return movimiento


def _recalcular_costo_catalogo(db: Session, clave: tuple, anteriores: list[dict]) -> None:
    tipo, identificador, ubicacion_id = clave
    tabla, inventario_tabla, campo = TIPOS_STOCK[tipo]
    query = db.query(tabla).filter(getattr(tabla, campo) == identificador, tabla.tipo == "ENTRADA", tabla.costo_unitario > 0)
    ultima = query.order_by(tabla.fecha.desc(), tabla.id.desc()).first()
    previos = [l for l in anteriores if l["tipo_item"] == tipo and l["item_id"] == identificador]
    costo = ultima.costo_unitario if ultima else next((Decimal(l["costo_catalogo_anterior"]) for l in previos if l.get("costo_catalogo_anterior") is not None), None)
    if costo is None:
        return
    if tipo == "MATERIAL":
        db.get(Material, identificador).costo_base = costo
    else:
        db.get(Producto, identificador).precio_costo_base = costo
        ultima_ubicacion = query.filter(tabla.ubicacion_id == ubicacion_id).order_by(tabla.fecha.desc(), tabla.id.desc()).first()
        inventario = db.query(inventario_tabla).filter_by(producto_id=identificador, ubicacion_id=ubicacion_id).one()
        inventario.costo_promedio = ultima_ubicacion.costo_unitario if ultima_ubicacion else costo


def corregir_stock(db: Session, contexto, anteriores: list[dict]) -> None:
    from app.modules.inventory.entrada_datos import renglon_guardado

    nuevas = _preparar_cambio_stock(db, contexto, anteriores)
    _aplicar_diferencias(db, anteriores, list(nuevas.values()))
    originales = {linea["linea_id"]: linea for linea in anteriores}
    guardadas = []
    for captura, preparada in zip(contexto.datos.lineas, contexto.lineas):
        anterior = originales.pop(preparada["linea_id"], None)
        if anterior and _clave_stock(anterior) == _clave_stock(preparada):
            preparada["costo_catalogo_anterior"] = anterior.get("costo_catalogo_anterior")
        movimiento = _corregir_renglon(db, contexto, preparada, anterior)
        guardadas.append(renglon_guardado(captura, preparada, movimiento))
    for anterior in originales.values():
        db.delete(_movimiento_bloqueado(db, anterior))
    db.flush()
    contexto.compra.lineas_json = guardadas
    claves = {_clave_stock(l) for l in anteriores + list(nuevas.values())}
    if _cambia_valoracion(contexto, anteriores):
        for clave in sorted(claves):
            _recalcular_costo_catalogo(db, clave, anteriores)


def _cambia_valoracion(contexto, anteriores: list[dict]) -> bool:
    if contexto.datos.fecha != contexto.compra.fecha.date() or len(anteriores) != len(contexto.lineas):
        return True
    previas = {linea["linea_id"]: linea for linea in anteriores}
    for captura, nueva in zip(contexto.datos.lineas, contexto.lineas):
        anterior = previas.get(nueva["linea_id"])
        if anterior is None or _clave_stock(anterior) != _clave_stock(nueva):
            return True
        for campo in ("precio_unitario", "descuento_porcentaje", "tasa_precio_a_cop"):
            if Decimal(str(anterior.get(campo) or 0)) != Decimal(str(getattr(captura, campo) or 0)):
                return True
    return False
