"""
estructura_generador.py — Estructura de costes generada desde la producción.

Cuando una OrdenProduccion se FINALIZA y el producto NO tiene estructura de
costes, este módulo la genera con lo que REALMENTE se usó en el taller:

  - Consumos de material (cantidad, sección, componente, precio congelado).
  - Mano de obra por área → CostoProduccionSeccion en el formato del Excel:
    "FABRICACION {base} *{recargo}%": el costo_base es la mano de obra REAL por
    unidad y el porcentaje es el recargo de producción (por defecto 8%, o el
    `porcentaje_recargo` registrado en la mano de obra si existe). El motor
    suma base × (1 + recargo/100), igual que "FABRICACION 300.000 *8%".
  - El % de gastos de cada sección (pct_gastos_seccion, ej. 10% Ebanistería,
    5% Nocheros) lo aplica el motor sobre TODO el subtotal de la sección
    (insumos + costos de producción), igual que "gastos de X e N%" del Excel.

Reglas (decisiones del dueño):
  * Solo genera si el producto no tiene elementos en su estructura (nunca
    pisa trabajo manual; secciones vacías se llenan).
  * Consumos marcados como excedente (daño/desperdicio) y consumos/mano de
    obra de etapas de RETRABAJO se EXCLUYEN de la estructura (el costo real
    de la orden sí los incluye: es dinero que salió).
  * `componente` del consumo (CAMA, NOCHERO...) → secciones "SECCIÓN
    (COMPONENTE)", diferenciando piezas del mismo mueble.
  * Cantidades divididas por la cantidad de unidades del detalle del pedido
    (una orden cubre todas las unidades de su detalle).
"""
import logging
from decimal import Decimal, ROUND_HALF_UP

from sqlalchemy.orm import Session

from app.modules.production.model import (
    ConsumoMaterial,
    EtapaProduccion,
    ManoObra,
    OrdenProduccion,
)
from app.modules.orders.model import DetallePedido
from app.modules.productos.model import (
    CostoProduccionSeccion,
    ElementoSeccion,
    PoliticaSeccion,
    Producto,
    SeccionProducto,
)

logger = logging.getLogger(__name__)

# Pretty-print de secciones normalizadas (EBANISTERIA → EBANISTERÍA).
_PRETTY_SECCION = {
    "EBANISTERIA": "EBANISTERÍA",
    "PREPARACION": "PREPARACIÓN",
    "PINTURA": "PINTURA",
    "TAPICERIA": "TAPICERÍA",
    "TERMINACION": "TERMINACIÓN",
    "TENDIDO": "TENDIDO",
    "COLA_DE_PATO": "COLA DE PATO",
    "NOCHEROS": "NOCHEROS",
    "MANO_DE_OBRA": "MANO DE OBRA",
    "ILUMINACION": "ILUMINACIÓN",
}

_MOTIVOS_VALIDOS = ("DAÑO", "RETRABAJO", "DESPERDICIO", "PRUEBA", "OTRO")

# Recargo de producción por defecto: el *8% que lleva la fabricación en el
# Excel ("FABRICACION 300.000 *8% → 324000"). Si la mano de obra registrada
# tiene su propio porcentaje_recargo, ese manda; si no, se usa este 8%.
RECARGO_PRODUCCION_PCT = Decimal("8.00")


def _r2(v: Decimal) -> Decimal:
    return v.quantize(Decimal("0.01"), rounding=ROUND_HALF_UP)


def _r4(v: Decimal) -> Decimal:
    return v.quantize(Decimal("0.0001"), rounding=ROUND_HALF_UP)


def _normalizar_seccion(seccion) -> str:
    """Mismo criterio que cost_service._normalizar_seccion (sin importarlo
    para no acoplar): NOCHEROS gana, se quita el sufijo entre paréntesis."""
    from app.modules.productos.cost_service import _normalizar_seccion as _norm
    return _norm(seccion)


def _pretty_seccion(normalizada: str) -> str:
    return _PRETTY_SECCION.get(normalizada, normalizada.capitalize().replace("_", " "))


def _sufijo_componente(componente: str | None) -> str | None:
    """'NOCHERO' → 'NOCHEROS' (el costeo detecta la palabra NOCHEROS para la
    regla de gastos del 5%). Otros componentes se usan tal cual."""
    if not componente:
        return None
    if "NOCHER" in componente.upper():
        return "NOCHEROS"
    return componente.upper()


def _producto_de_orden(db: Session, orden: OrdenProduccion) -> Producto | None:
    if orden.es_stock:
        return orden.producto
    detalle = db.query(DetallePedido).filter(DetallePedido.id == orden.detalle_pedido_id).first()
    if not detalle or not detalle.producto_id:
        return None
    return db.query(Producto).filter(Producto.id == detalle.producto_id).first()


def _tiene_estructura(db: Session, producto_id: int) -> bool:
    return (
        db.query(ElementoSeccion.id)
        .join(SeccionProducto, SeccionProducto.id == ElementoSeccion.seccion_id)
        .filter(SeccionProducto.producto_id == producto_id)
        .first()
        is not None
    )


def _nombre_seccion(normalizada: str, componente: str | None) -> str:
    nombre = _pretty_seccion(normalizada)
    sufijo = _sufijo_componente(componente)
    if sufijo:
        nombre = f"{nombre} ({sufijo})"
    return nombre.upper()


def generar_estructura_desde_orden(db: Session, orden_id: int) -> bool:
    """Genera la estructura de costes del producto desde la producción real.

    Devuelve True si generó (o completó) estructura; False si no aplicó.
    NUNCA levanta excepciones: quien la llama (finalizar orden) la envuelve.
    """
    orden = db.query(OrdenProduccion).filter(OrdenProduccion.id == orden_id).first()
    if not orden or orden.estado != "FINALIZADA":
        return False
    producto = _producto_de_orden(db, orden)
    if not producto:
        return False
    if _tiene_estructura(db, producto.id):
        return False

    # Unidades del detalle (una orden cubre todas las del detalle).
    unidades = Decimal("1")
    dims = (orden.ancho, orden.largo)
    if orden.detalle_pedido_id:
        detalle = db.query(DetallePedido).filter(DetallePedido.id == orden.detalle_pedido_id).first()
        if detalle:
            unidades = Decimal(str(detalle.cantidad or 1))
            dims = (detalle.ancho, detalle.largo)

    # Etapas en orden de flujo (área → sección normalizada).
    etapas = (
        db.query(EtapaProduccion)
        .filter(EtapaProduccion.orden_produccion_id == orden_id)
        .order_by(EtapaProduccion.id)
        .all()
    )
    seccion_de_etapa = {
        e.id: _normalizar_seccion(e.area.nombre if e.area else None) for e in etapas
    }
    orden_secciones: list[str] = []
    for sec in seccion_de_etapa.values():
        if sec not in orden_secciones:
            orden_secciones.append(sec)

    # 1) Consumos normales por (sección, componente) — excluye excedente y retrabajo.
    #    clave: (seccion_norm, componente)
    consumos_por_seccion: dict[tuple, list[ConsumoMaterial]] = {}
    for c in db.query(ConsumoMaterial).filter(
        ConsumoMaterial.etapa_produccion_id.in_([e.id for e in etapas])
    ).all():
        etapa = next((e for e in etapas if e.id == c.etapa_produccion_id), None)
        if not etapa:
            continue
        if c.es_excedente or etapa.es_retrabajo:
            continue
        clave = (seccion_de_etapa.get(etapa.id, "EBANISTERIA"), c.componente or None)
        consumos_por_seccion.setdefault(clave, []).append(c)

    # 2) Mano de obra por sección normalizada — excluye retrabajo.
    #    (la MO cae en la sección BASE de su área, sin componente)
    manos_por_seccion: dict[str, list[ManoObra]] = {}
    for mo in db.query(ManoObra).filter(
        ManoObra.etapa_produccion_id.in_([e.id for e in etapas])
    ).all():
        etapa = next((e for e in etapas if e.id == mo.etapa_produccion_id), None)
        if not etapa or etapa.es_retrabajo:
            continue
        sec = seccion_de_etapa.get(etapa.id, "EBANISTERIA")
        manos_por_seccion.setdefault(sec, []).append(mo)

    if not consumos_por_seccion and not manos_por_seccion:
        return False

    # 3) Crear/llenar secciones en el orden de flujo de producción.
    claves_consumos = list(consumos_por_seccion.keys())
    claves_mo = [(sec, None) for sec in manos_por_seccion]
    claves_ordenadas = sorted(
        set(claves_consumos) | set(claves_mo),
        key=lambda c: (orden_secciones.index(c[0]) if c[0] in orden_secciones else 999, c[1] or ""),
    )

    seccion_obj: dict[tuple, SeccionProducto] = {}
    origen_note = (
        f"Generada desde producción (orden #{orden_id}, "
        f"{unidades} ud, dims {dims[0] or '?'}x{dims[1] or '?'} m)"
    )

    for pos, clave in enumerate(claves_ordenadas, start=1):
        sec_norm, comp = clave
        nombre = _nombre_seccion(sec_norm, comp)
        seccion = (
            db.query(SeccionProducto)
            .filter(
                SeccionProducto.producto_id == producto.id,
                SeccionProducto.nombre == nombre,
            )
            .first()
        )
        if not seccion:
            seccion = SeccionProducto(
                producto_id=producto.id,
                nombre=nombre,
                orden=pos,
            )
            db.add(seccion)
            db.flush()
            # % gastos de la sección: la regla global (NOCHEROS=5%) manda;
            # se busca con la sección NORMALIZADA del nombre final
            # ("EBANISTERÍA (NOCHEROS)" → "NOCHEROS" → 5%).
            pct_gastos = Decimal("10.00")
            from app.modules.productos.model import ReglaGastoSeccion
            regla = db.query(ReglaGastoSeccion).filter(
                ReglaGastoSeccion.seccion == _normalizar_seccion(nombre)
            ).first()
            if regla and regla.porcentaje_gasto is not None:
                pct_gastos = Decimal(str(regla.porcentaje_gasto))
            db.add(PoliticaSeccion(
                seccion_id=seccion.id,
                mano_obra_base=Decimal("0"),
                pct_liquidacion_mo=Decimal("5.00"),
                pct_gastos_seccion=pct_gastos,
            ))
        seccion_obj[clave] = seccion

    # 4) Elementos (materiales) por sección.
    for clave, consumos in consumos_por_seccion.items():
        seccion = seccion_obj[clave]
        por_material: dict[int, list[ConsumoMaterial]] = {}
        for c in consumos:
            por_material.setdefault(c.material_id, []).append(c)
        for material_id, items in por_material.items():
            material = items[0].material
            cantidad_total = sum((Decimal(str(c.cantidad)) for c in items), Decimal("0"))
            costo_total = sum(
                (Decimal(str(c.cantidad)) * (Decimal(str(c.costo_unitario)) if c.costo_unitario else Decimal("0"))
                 for c in items),
                Decimal("0"),
            )
            cantidad_por_unidad = _r4(cantidad_total / unidades)
            precio_promedio = _r2(costo_total / cantidad_total) if cantidad_total else Decimal("0")
            if precio_promedio <= 0 and material and material.costo_base:
                precio_promedio = _r2(Decimal(str(material.costo_base)))
            unidad = ""
            if material and material.unidad_medida:
                unidad = material.unidad_medida.abreviatura or material.unidad_medida.nombre
            db.add(ElementoSeccion(
                seccion_id=seccion.id,
                nombre_insumo_original=material.nombre if material else f"Material #{material_id}",
                material_id_normalizado=material_id,
                estado_resolucion="MAPEADO",
                cantidad=cantidad_por_unidad,
                unidad_medida=unidad or None,
                # precio_unitario = precio del MATERIAL (por su unidad); el
                # motor jerárquico hace cantidad × precio_unitario.
                precio_unitario=precio_promedio if precio_promedio > 0 else None,
                costo_subtotal=(cantidad_por_unidad * precio_promedio) if precio_promedio > 0 else None,
                observaciones=origen_note,
            ))

    # 5) Costos de producción (mano de obra real) por sección.
    #    Formato del Excel: "FABRICACION {base} *{recargo}%" → el motor suma
    #    base × (1 + recargo/100). El recargo usa el registrado en la mano de
    #    obra si existe; si no, el recargo de producción por defecto (8%).
    for sec_norm, manos in manos_por_seccion.items():
        clave = (sec_norm, None)
        seccion = seccion_obj.get(clave)
        if not seccion:
            continue
        total_mo = sum((Decimal(str(mo.monto)) for mo in manos), Decimal("0"))
        total_por_unidad = _r2(total_mo / unidades) if unidades else Decimal("0")
        if total_por_unidad <= 0:
            continue
        recargo = next(
            (Decimal(str(mo.porcentaje_recargo)) for mo in manos
             if mo.porcentaje_recargo and Decimal(str(mo.porcentaje_recargo)) > 0),
            RECARGO_PRODUCCION_PCT,
        )
        nombre_tarifa = None
        for mo in manos:
            if mo.precio_produccion and mo.precio_produccion.descripcion:
                nombre_tarifa = mo.precio_produccion.descripcion
                break
        db.add(CostoProduccionSeccion(
            seccion_id=seccion.id,
            nombre=(nombre_tarifa or _pretty_seccion(sec_norm)).upper(),
            porcentaje=recargo,
            costo_base=total_por_unidad,
        ))

    logger.info("Estructura de costes generada para producto #%s desde orden #%s",
                producto.id, orden_id)
    return True