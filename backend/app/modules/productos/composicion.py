"""Composición de un conjunto: qué piezas (productos) forman un mueble.

Un comedor = mesa ×1 + sillas ×6. Cada pieza es un `Producto` del catálogo con
su propio costo y precio, así que la MISMA pieza sirve para armar el conjunto,
para cotizarse sola y para quedar como sobrante vendible en el showroom.

Esto NO toca la receta de materiales ni el motor de costos: es el desglose
comercial y de costo del mueble. Por eso la conciliación entre "lo que vale el
conjunto" y "la suma de sus piezas" solo se REPORTA, nunca se autocorrige.
"""
from decimal import Decimal
from typing import Optional

from sqlalchemy.orm import Session, joinedload

from app.modules.productos import model, schemas


def _dec(valor) -> Decimal:
    return Decimal(str(valor)) if valor is not None else Decimal("0")


def resumen_composicion(producto: model.Producto, piezas: list) -> schemas.ProductoComposicionResumen:
    """Suma de las piezas vs costo/precio del conjunto, con sus diferencias.

    Si las piezas no comparten la moneda del conjunto se avisa: sumar COP con
    USD daría un número bonito y falso, y eso es peor que no dar número.
    """
    costo = Decimal("0")
    precio = Decimal("0")
    sin_costo = 0
    sin_precio = 0
    monedas_distintas = False
    for fila in piezas:
        pieza = fila.pieza
        if pieza is None:
            continue
        cantidad = _dec(fila.cantidad)
        if pieza.precio_costo_base is None:
            sin_costo += 1
        else:
            costo += cantidad * _dec(pieza.precio_costo_base)
        if pieza.precio_venta_base is None:
            sin_precio += 1
        else:
            precio += cantidad * _dec(pieza.precio_venta_base)
        if (pieza.moneda_id or 1) != (producto.moneda_id or 1):
            monedas_distintas = True

    costo_conjunto = _dec(producto.precio_costo_base) if producto.precio_costo_base is not None else None
    precio_conjunto = _dec(producto.precio_venta_base) if producto.precio_venta_base is not None else None
    return schemas.ProductoComposicionResumen(
        costo_piezas=float(costo),
        precio_piezas=float(precio),
        costo_conjunto=float(costo_conjunto) if costo_conjunto is not None else None,
        precio_conjunto=float(precio_conjunto) if precio_conjunto is not None else None,
        diferencia_costo=float(costo_conjunto - costo) if costo_conjunto is not None else None,
        diferencia_precio=float(precio_conjunto - precio) if precio_conjunto is not None else None,
        piezas_sin_costo=sin_costo,
        piezas_sin_precio=sin_precio,
        advertencia_moneda=(
            "Hay piezas en una moneda distinta a la del conjunto: la suma mezcla monedas."
            if monedas_distintas else None
        ),
    )


def _cargar_piezas(db: Session, producto_id: int) -> list:
    return (
        db.query(model.ProductoPieza)
        .options(joinedload(model.ProductoPieza.pieza))
        .filter(model.ProductoPieza.producto_id == producto_id)
        .order_by(model.ProductoPieza.orden, model.ProductoPieza.id)
        .all()
    )


def obtener_composicion(db: Session, producto: model.Producto) -> schemas.ProductoComposicionResponse:
    piezas = _cargar_piezas(db, producto.id)
    return schemas.ProductoComposicionResponse(
        producto_id=producto.id,
        es_conjunto=bool(producto.es_conjunto),
        piezas=[schemas.ProductoPiezaResponse.model_validate(p) for p in piezas],
        resumen=resumen_composicion(producto, piezas),
    )


def reemplazar_composicion(
    db: Session,
    producto: model.Producto,
    piezas_in: list,
    usuario=None,
) -> schemas.ProductoComposicionResponse:
    """Reemplaza TODA la composición del conjunto (contrato de lista completa).

    - Marca el producto como conjunto si queda con piezas (y lo desmarca si
      queda vacío): `es_conjunto` no se edita a mano en el formulario.
    - Marca cada producto usado como `es_pieza` (nunca lo desmarca: una pieza
      que sobró de un despiece sigue siendo una pieza aunque ya no esté en
      ningún conjunto).
    - No permite anidar conjuntos: el despiece y el costo por pieza se
      calculan sobre piezas simples, y un conjunto dentro de otro rompería esa
      cuenta. Si hace falta, se desglosa el mueble en sus piezas directas.
    """
    nuevas = list(piezas_in or [])
    ids = [p.pieza_producto_id for p in nuevas]
    if producto.id in ids:
        raise ValueError("Un producto no puede ser pieza de sí mismo.")

    productos_pieza = {}
    if ids:
        for pieza in db.query(model.Producto).filter(model.Producto.id.in_(ids)).all():
            productos_pieza[pieza.id] = pieza
        faltantes = [i for i in ids if i not in productos_pieza]
        if faltantes:
            raise ValueError(f"Hay piezas que no existen en el catálogo (id {', '.join(map(str, faltantes))}).")
        for pieza in productos_pieza.values():
            if pieza.id != producto.id and pieza.es_conjunto:
                raise ValueError(
                    f"'{pieza.nombre}' ya es un conjunto. Un conjunto no puede ser pieza de "
                    "otro conjunto: desglosa el mueble en sus piezas directas."
                )

    # Reemplazo completo: se borran las filas viejas y se escriben las nuevas.
    # Mismo contrato que los detalles de una cotización (PUT con la lista).
    db.query(model.ProductoPieza).filter(
        model.ProductoPieza.producto_id == producto.id
    ).delete(synchronize_session=False)

    for posicion, item in enumerate(nuevas):
        orden = item.orden if item.orden is not None else posicion
        db.add(model.ProductoPieza(
            producto_id=producto.id,
            pieza_producto_id=item.pieza_producto_id,
            cantidad=Decimal(str(item.cantidad)),
            orden=orden if orden else posicion,
        ))
        pieza = productos_pieza.get(item.pieza_producto_id)
        if pieza is not None and not pieza.es_pieza:
            pieza.es_pieza = True

    producto.es_conjunto = bool(nuevas)
    db.flush()

    if usuario is not None:
        from app.modules.auditoria.service import record_event

        record_event(
            db,
            actor=usuario,
            action="UPDATE",
            entity_type="producto",
            entity_id=producto.id,
            after={
                "composicion": [
                    {"pieza_producto_id": p.pieza_producto_id, "cantidad": float(p.cantidad)}
                    for p in nuevas
                ],
                "es_conjunto": bool(nuevas),
            },
        )

    db.commit()
    db.refresh(producto)
    return obtener_composicion(db, producto)
