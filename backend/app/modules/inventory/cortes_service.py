"""
cortes_service.py
=================
Servicio de consumo de materiales laminares POR CORTES.

El material se descuenta del stock de láminas enteras (SALIDA) y el costo del
consumo es proporcional al área del corte (costo_base × área_corte / área_lámina).
Lo usan la producción por pedidos (ConsumoMaterial) y la producción de crudos
(ProduccionCrudoConsumo).

NOTA: el inventario de retazos ("sobrantes de lámina") fue RETIRADO del sistema
por decisión del dueño: ya no se crean, ni se consumen, ni se reponen. Las
tablas viejas quedan congeladas en la BD (sin uso).
"""
from decimal import Decimal

from app.modules.inventory import schemas as inv_schemas
from app.modules.inventory import laminas
from app.modules.inventory.service import registrar_movimiento
from app.modules.productos.model import Material


def _dec(v) -> Decimal:
    return Decimal(str(v))


def rechazar_origen_sobrante(origen_sobrante_id) -> None:
    """Los sobrantes de lámina ya no existen: si un cliente viejo (o una
    operación encolada offline) intenta cortar "desde sobrante", se rechaza
    con un mensaje claro en vez de descontar láminas en silencio."""
    if origen_sobrante_id:
        raise ValueError(
            "El uso de sobrantes de láminas ya no está disponible: "
            "registra el corte desde lámina nueva o registra un consumo normal."
        )


def _detalle_corte(cantidad, lc, ac, laminas_consumidas) -> str:
    det = f"Corte {int(cantidad)}x({lc.normalize()}×{ac.normalize()} cm)"
    if laminas_consumidas > 0:
        det += f" — {laminas_consumidas} lámina(s) nueva(s)"
    return det


def consumir_por_cortes(
    db,
    *,
    material: Material,
    cantidad_cortes,
    largo_corte_cm,
    ancho_corte_cm,
    ubicacion_id: int,
    referencia_tipo: str,
    referencia_id: int,
) -> dict:
    """
    Ejecuta el consumo de `cantidad_cortes` cortes de largo×ancho (cm).
    Descuenta láminas enteras del depósito y devuelve el resumen:

      laminas_consumidas  → láminas enteras descontadas
      costo_unitario      → costo POR CORTE (proporcional al área)
      costo_total         → cantidad_cortes × costo_unitario
      detalle             → texto para el kardex/gasto
    """
    lc, ac = laminas.validar_corte(material, largo_corte_cm, ancho_corte_cm)
    cantidad = _dec(cantidad_cortes)
    if cantidad <= 0:
        raise ValueError("El número de cortes debe ser mayor que cero.")

    area_corte = lc * ac
    area_lamina = _dec(material.largo_cm) * _dec(material.ancho_cm)
    costo_unit = laminas.costo_por_corte(material.costo_base, area_corte, area_lamina)
    costo_total = (costo_unit * cantidad).quantize(Decimal("0.01"))

    por_lamina = laminas.cortes_que_caban(material.largo_cm, material.ancho_cm, lc, ac)
    if por_lamina == 0:
        raise ValueError(
            f"Un corte de {lc.normalize()}×{ac.normalize()} no cabe en la lámina "
            f"de {material.largo_cm.normalize()}×{material.ancho_cm.normalize()} de '{material.nombre}'."
        )
    n_laminas = Decimal(laminas.laminas_necesarias(cantidad, por_lamina))
    movimiento = inv_schemas.MovimientoCreate(
        material_id=material.id,
        ubicacion_id=ubicacion_id,
        tipo="SALIDA",
        cantidad=n_laminas,
        referencia_tipo=referencia_tipo,
        referencia_id=referencia_id,
        observaciones=f"Cortes {lc.normalize()}×{ac.normalize()} cm ({cantidad}) — "
                      f"{por_lamina} por lámina",
    )
    registrar_movimiento(db, movimiento)

    return {
        "laminas_consumidas": n_laminas,
        "costo_unitario": costo_unit,
        "costo_total": costo_total,
        "detalle": _detalle_corte(cantidad, lc, ac, n_laminas),
    }


def revertir_consumo_por_cortes(
    db,
    *,
    material: Material,
    consumo_id: int,
    consumo_tipo: str,
    largo_corte_cm,
    ancho_corte_cm,
    laminas_consumidas,
    ubicacion_id: int,
) -> str:
    """
    Reversa de consumir_por_cortes al eliminar un consumo: ENTRADA de las
    láminas descontadas. Los consumos viejos que salieron "de sobrante" no
    tienen láminas que reponer (laminas_consumidas 0/None): no se toca stock.
    Devuelve texto del detalle para el kardex.
    """
    lc, ac = laminas.validar_corte(material, largo_corte_cm, ancho_corte_cm)

    if laminas_consumidas and _dec(laminas_consumidas) > 0:
        n_laminas = _dec(laminas_consumidas)
        registrar_movimiento(db, inv_schemas.MovimientoCreate(
            material_id=material.id,
            ubicacion_id=ubicacion_id,
            tipo="ENTRADA",
            cantidad=n_laminas,
            referencia_tipo=consumo_tipo,
            referencia_id=consumo_id,
            observaciones=f"Reversa de cortes {lc.normalize()}×{ac.normalize()} — reingreso de láminas",
        ))
        db.flush()
        return f"Reversa: +{n_laminas.normalize()} lámina(s)"

    return "Reversa: sin láminas que reponer (consumo sin descuento de stock)"
