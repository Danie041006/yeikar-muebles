"""Reglas comerciales de las piezas de un renglón-juego (composición).

La Fase 1 permitió declarar piezas con costo/precio propio en el catálogo
(`producto_pieza`). Esta capa traduce esa composición a un renglón de
cotización/pedido:

- Cada pieza puede apuntar a un PRODUCTO del catálogo (`producto_id`), con un
  precio unitario propio en la moneda de la cotización.
- `origen=EXHIBICION` indica que la pieza se toma de un mueble ya fabricado del
  showroom (y `conjunto_origen_id` dice de cuál conjunto despiezarla).
- El precio del renglón se calcula SOLO si TODAS las piezas traen precio:
  Σ cantidad × (precio + precio_modificacion). Si ninguna trae precio, el
  renglón conserva su precio global manual (juegos clásicos).
- El costo estimado del renglón (COP) sale del costo de catálogo de cada
  pieza; el costo REAL de las piezas de exhibición se congela al despiezar.
"""

from decimal import Decimal
from typing import Iterable

from sqlalchemy.orm import Session

ORIGEN_FABRICADO = "FABRICADO"
ORIGEN_EXHIBICION = "EXHIBICION"
ORIGENES_PIEZA = (ORIGEN_FABRICADO, ORIGEN_EXHIBICION)


def _campo(pieza, nombre: str, default=None):
    """Lee un campo de una pieza venga como dict, Pydantic o modelo ORM."""
    if isinstance(pieza, dict):
        return pieza.get(nombre, default)
    return getattr(pieza, nombre, default)


def _dec(valor) -> Decimal | None:
    if valor is None or valor == "":
        return None
    return Decimal(str(valor))


def origen_pieza(pieza) -> str:
    """FABRICADO por defecto (NULL histórico = pieza fabricada)."""
    valor = _campo(pieza, "origen")
    return (str(valor).strip().upper() if valor else ORIGEN_FABRICADO)


def es_pieza_comercial(pieza) -> bool:
    """True si la pieza usa la composición nueva (producto/precio/origen).

    Las piezas clásicas (nombre + cantidad) siguen comportándose igual: no
    tocan precios ni inventario.
    """
    return bool(
        _campo(pieza, "producto_id")
        or _campo(pieza, "precio") is not None
        or _campo(pieza, "conjunto_origen_id")
        or _campo(pieza, "requiere_retrabajo")
    )


def tiene_composicion_comercial(piezas: Iterable | None) -> bool:
    return any(es_pieza_comercial(p) for p in (piezas or []))


def datos_pieza(pieza) -> dict:
    """Normaliza una pieza a dict con TODAS las columnas nuevas."""
    origen = origen_pieza(pieza)
    return {
        "nombre": (_campo(pieza, "nombre") or "").strip(),
        "cantidad": _campo(pieza, "cantidad") or 1,
        "notas": (_campo(pieza, "notas") or "").strip() or None,
        "foto": _campo(pieza, "foto") or None,
        "producto_id": _campo(pieza, "producto_id"),
        "precio": _campo(pieza, "precio"),
        "origen": origen,
        "conjunto_origen_id": _campo(pieza, "conjunto_origen_id"),
        "modificacion": (_campo(pieza, "modificacion") or "").strip() or None,
        "requiere_retrabajo": bool(_campo(pieza, "requiere_retrabajo")),
        "precio_modificacion": _campo(pieza, "precio_modificacion"),
    }


# ------------------------------------------------------------
# Validaciones contra el catálogo
# ------------------------------------------------------------
def validar_piezas_comerciales(db: Session, piezas: Iterable | None) -> None:
    """Valida las referencias al catálogo y las reglas de origen/retrabajo.

    La validación estructural (campos obligatorios, precios todos o ninguno)
    vive en el schema; esto cubre lo que necesita consultar la BD:
      - el producto-pieza existe;
      - el conjunto de origen existe;
      - si el conjunto ya tiene composición, la pieza pertenece a ella;
      - una pieza de exhibición sin conjunto se toma suelta del stock.
    """
    piezas = list(piezas or [])
    if not piezas:
        return

    from app.modules.productos.model import Producto, ProductoPieza

    ids: set[int] = set()
    ids_conjuntos: set[int] = set()
    for pieza in piezas:
        origen = origen_pieza(pieza)
        producto_id = _campo(pieza, "producto_id")
        conjunto_id = _campo(pieza, "conjunto_origen_id")
        nombre = (_campo(pieza, "nombre") or "").strip() or "pieza"

        if origen not in ORIGENES_PIEZA:
            raise ValueError(
                f"Origen inválido en la pieza '{nombre}': usa FABRICADO o EXHIBICION."
            )
        if origen == ORIGEN_EXHIBICION and not producto_id:
            raise ValueError(
                f"La pieza de exhibición '{nombre}' debe indicar el producto del "
                "catálogo del que sale (producto_id)."
            )
        if conjunto_id and origen != ORIGEN_EXHIBICION:
            raise ValueError(
                f"El conjunto de origen solo aplica a piezas de exhibición ('{nombre}')."
            )
        if _campo(pieza, "requiere_retrabajo"):
            if not (_campo(pieza, "modificacion") or "").strip():
                raise ValueError(
                    f"La pieza '{nombre}' requiere retrabajo pero no indica la modificación."
                )
            if not producto_id:
                raise ValueError(
                    f"La pieza '{nombre}' requiere retrabajo pero no tiene producto del catálogo."
                )
        elif _campo(pieza, "precio_modificacion") is not None:
            raise ValueError(
                f"La pieza '{nombre}' tiene precio de modificación sin requerir retrabajo."
            )
        if producto_id:
            ids.add(int(producto_id))
        if conjunto_id:
            ids.add(int(conjunto_id))
            ids_conjuntos.add(int(conjunto_id))

    productos = {
        p.id: p
        for p in db.query(Producto).filter(Producto.id.in_(ids)).all()
    } if ids else {}
    faltantes = sorted(ids - set(productos))
    if faltantes:
        raise ValueError(
            "No existen los productos de la composición: "
            + ", ".join(f"#{i}" for i in faltantes)
        )

    composiciones: dict[int, dict[int, Decimal]] = {}
    if ids_conjuntos:
        filas = (
            db.query(ProductoPieza)
            .filter(ProductoPieza.producto_id.in_(ids_conjuntos))
            .all()
        )
        for fila in filas:
            composiciones.setdefault(fila.producto_id, {})[fila.pieza_producto_id] = Decimal(
                str(fila.cantidad or 0)
            )

    for pieza in piezas:
        origen = origen_pieza(pieza)
        producto_id = _campo(pieza, "producto_id")
        conjunto_id = _campo(pieza, "conjunto_origen_id")
        nombre = (_campo(pieza, "nombre") or "").strip() or "pieza"
        if not conjunto_id:
            continue
        conjunto = productos.get(int(conjunto_id))
        if int(producto_id or 0) == int(conjunto_id):
            raise ValueError(
                f"La pieza '{nombre}' no puede ser el mismo conjunto del que sale."
            )
        comp = composiciones.get(int(conjunto_id)) or {}
        # Si el conjunto aún no tiene composición se permite cotizar (se
        # completará después); al convertir se exigirá para poder despiezar.
        if comp and producto_id and int(producto_id) not in comp:
            raise ValueError(
                f"La pieza '{nombre}' no pertenece al conjunto "
                f"'{conjunto.nombre if conjunto else conjunto_id}'."
            )


# ------------------------------------------------------------
# Precio y costo del renglón
# ------------------------------------------------------------
def precio_linea_desde_piezas(piezas: Iterable | None) -> Decimal | None:
    """Precio de UNA unidad del renglón (un juego), en la moneda de la venta.

    Devuelve None cuando NINGUNA pieza trae precio (el renglón conserva su
    precio global manual). Si unas traen y otras no, es un error de captura:
    mezclar precios parciales haría que el total no cuadre con lo mostrado.
    """
    piezas = list(piezas or [])
    if not piezas:
        return None
    precios = [_dec(_campo(p, "precio")) for p in piezas]
    if all(p is None for p in precios):
        return None
    if any(p is None for p in precios):
        sin_precio = [
            (_campo(p, "nombre") or "pieza") for p, pr in zip(piezas, precios) if pr is None
        ]
        raise ValueError(
            "Las piezas del renglón deben tener TODAS precio o NINGUNA. "
            f"Falta el precio de: {', '.join(sin_precio)}."
        )

    total = Decimal("0")
    for pieza, precio in zip(piezas, precios):
        cantidad = Decimal(str(_campo(pieza, "cantidad") or 1))
        modificacion = Decimal("0")
        if _campo(pieza, "requiere_retrabajo"):
            modificacion = _dec(_campo(pieza, "precio_modificacion")) or Decimal("0")
        total += cantidad * (precio + modificacion)
    return total.quantize(Decimal("0.01"))


def costo_unitario_desde_piezas(
    db: Session,
    piezas: Iterable | None,
    *,
    usar_snapshot: bool = False,
) -> Decimal | None:
    """Costo de UNA unidad del renglón, en COP.

    Por defecto usa el costo de referencia del catálogo de cada pieza
    (`precio_costo_base`, en la moneda del producto). Con `usar_snapshot=True`
    prioriza `pieza.costo_unitario`, el costo REAL congelado al despiezar una
    pieza de exhibición. Es la misma cifra que usa la rentabilidad.
    """
    piezas = list(piezas or [])
    if not piezas:
        return None

    from app.modules.productos.model import Producto
    from app.modules.productos.service import convertir_a_moneda_base

    ids = {int(_campo(p, "producto_id")) for p in piezas if _campo(p, "producto_id")}
    productos = {
        p.id: p for p in db.query(Producto).filter(Producto.id.in_(ids)).all()
    } if ids else {}

    total = Decimal("0")
    hay_costo = False
    for pieza in piezas:
        costo_cop = None
        if usar_snapshot:
            costo_cop = _dec(_campo(pieza, "costo_unitario"))
        if costo_cop is None:
            producto_id = _campo(pieza, "producto_id")
            producto = productos.get(int(producto_id)) if producto_id else None
            if producto is not None and producto.precio_costo_base is not None:
                costo_cop = convertir_a_moneda_base(
                    db, producto.moneda_id, float(producto.precio_costo_base)
                )
        if costo_cop is None:
            continue
        hay_costo = True
        total += Decimal(str(_campo(pieza, "cantidad") or 1)) * Decimal(str(costo_cop))
    if not hay_costo:
        return None
    return total.quantize(Decimal("0.01"))


def aplicar_composicion_detalles(db: Session, detalles: Iterable) -> bool:
    """Recalcula precio y costo de los renglones compuestos, si aplica.

    Acepta Pydantic o dicts (create/update de cotización y pedido). Devuelve
    True si al menos un renglón usa la composición comercial, para que el
    llamador recalcule el total del documento desde sus renglones.
    """
    compuesto = False
    for detalle in detalles or []:
        piezas = _campo(detalle, "piezas") or []
        if not piezas or not tiene_composicion_comercial(piezas):
            continue
        validar_piezas_comerciales(db, piezas)
        compuesto = True

        precio = precio_linea_desde_piezas(piezas)
        if precio is not None:
            if isinstance(detalle, dict):
                detalle["precio"] = float(precio)
            else:
                detalle.precio = float(precio)

        costo_unitario = costo_unitario_desde_piezas(db, piezas)
        if costo_unitario is not None:
            cantidad = Decimal(str(_campo(detalle, "cantidad") or 1))
            costo_linea = (costo_unitario * cantidad).quantize(Decimal("0.01"))
            if isinstance(detalle, dict):
                detalle["costo_total"] = float(costo_linea)
            else:
                detalle.costo_total = float(costo_linea)
    return compuesto


def total_desde_detalles(detalles: Iterable) -> float | None:
    """Σ precio × cantidad de los renglones, o None si no hay renglones."""
    total = Decimal("0")
    hay = False
    for detalle in detalles or []:
        precio = _dec(_campo(detalle, "precio"))
        if precio is None:
            continue
        hay = True
        total += precio * Decimal(str(_campo(detalle, "cantidad") or 1))
    return float(total.quantize(Decimal("0.01"))) if hay else None
