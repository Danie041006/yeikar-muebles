"""
cortes_service.py
=================
Servicio de consumo de materiales laminares POR CORTES, con registro de
sobrantes. Lo usan la producción por pedidos (ConsumoMaterial) y la
producción de crudos (ProduccionCrudoConsumo).

Dos orígenes posibles para un consumo:
  - origen_sobrante_id=None  → láminas nuevas del depósito: se descuentan
    láminas enteras (SALIDA) y el pedazo restante de la última lámina se
    registra como SobranteLamina.
  - origen_sobrante_id=X     → los cortes salen de ese retazo: el sobrante
    se reduce (o se marca CONSUMIDO) y NO hay movimiento de stock.

El costo del consumo SIEMPRE es proporcional al área del corte
(costo_base × área_corte / área_lámina), venga de lámina nueva o retazo.
"""
from decimal import Decimal

from app.modules.inventory import model as inv_model, schemas as inv_schemas
from app.modules.inventory import laminas
from app.modules.inventory.service import registrar_movimiento
from app.modules.productos.model import Material


def _dec(v) -> Decimal:
    return Decimal(str(v))


def _detalle_corte(cantidad, lc, ac, laminas, sobrante=None) -> str:
    det = f"Corte {int(cantidad)}x({lc.normalize()}×{ac.normalize()} cm)"
    if laminas > 0:
        det += f" — {laminas} lámina(s) nueva(s)"
    if sobrante is not None:
        det += f" — sobrante {sobrante.largo_cm.normalize()}×{sobrante.ancho_cm.normalize()}"
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
    consumo_origen_tipo: str,
    origen_sobrante_id: int | None = None,
    sobrante_largo_cm=None,
    sobrante_ancho_cm=None,
) -> dict:
    """
    Ejecuta el consumo de `cantidad_cortes` cortes de largo×ancho (cm).
    Descuenta láminas y/o reduce sobrantes y devuelve el resumen:

      laminas_consumidas  → láminas enteras a descontar (0 si vino de sobrante)
      costo_unitario      → costo POR CORTE (proporcional al área)
      costo_total         → cantidad_cortes × costo_unitario
      sobrante            → fila SobranteLamina creada/actualizada (o None)
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

    # ── Origen: sobrante existente ────────────────────────────────────────
    if origen_sobrante_id:
        sobrante = (
            db.query(inv_model.SobranteLamina)
            .filter(
                inv_model.SobranteLamina.id == origen_sobrante_id,
                inv_model.SobranteLamina.estado == "DISPONIBLE",
            )
            .with_for_update()
            .first()
        )
        if not sobrante:
            raise ValueError("El sobrante indicado no existe o ya no está disponible.")
        if sobrante.material_id != material.id:
            raise ValueError("El sobrante pertenece a otro material.")
        caben = laminas.cortes_que_caban(sobrante.largo_cm, sobrante.ancho_cm, lc, ac)
        if caben < cantidad:
            raise ValueError(
                f"En el sobrante {sobrante.largo_cm.normalize()}×{sobrante.ancho_cm.normalize()} "
                f"caben {caben} corte(s) de {lc.normalize()}×{ac.normalize()}. "
                "Usa láminas nuevas o reduce la cantidad."
            )
        area_restante = sobrante.area_cm2 - cantidad * area_corte
        if sobrante_largo_cm and sobrante_ancho_cm:
            nuevo_largo, nuevo_ancho = _dec(sobrante_largo_cm), _dec(sobrante_ancho_cm)
            if nuevo_largo * nuevo_ancho > sobrante.area_cm2:
                raise ValueError("El sobrante resultante no puede ser más grande que el original.")
            if nuevo_largo * nuevo_ancho < laminas.AREA_MINIMA_SOBRANTE_CM2:
                sobrante.estado = "CONSUMIDO"
            else:
                sobrante.largo_cm, sobrante.ancho_cm = nuevo_largo, nuevo_ancho
        else:
            propuesta = laminas.proponer_sobrante(sobrante.largo_cm, sobrante.ancho_cm, area_restante)
            if propuesta is None:
                sobrante.estado = "CONSUMIDO"
            else:
                sobrante.largo_cm, sobrante.ancho_cm = propuesta
        db.add(sobrante)
        db.flush()
        return {
            "laminas_consumidas": Decimal("0"),
            "costo_unitario": costo_unit,
            "costo_total": costo_total,
            "sobrante": sobrante,
            "detalle": _detalle_corte(cantidad, lc, ac, 0, sobrante),
        }

    # ── Origen: láminas nuevas del depósito ──────────────────────────────
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

    # Sobrante del pedazo restante de la ÚLTIMA lámina abierta.
    cortes_en_ultima = cantidad - (n_laminas - 1) * por_lamina
    area_restante = area_lamina - cortes_en_ultima * area_corte
    sobrante = None
    dims = None
    if sobrante_largo_cm and sobrante_ancho_cm:
        dims = (_dec(sobrante_largo_cm), _dec(sobrante_ancho_cm))
    else:
        dims = laminas.proponer_sobrante(material.largo_cm, material.ancho_cm, area_restante)
    if dims is not None:
        sobrante = inv_model.SobranteLamina(
            material_id=material.id,
            ubicacion_id=ubicacion_id,
            largo_cm=dims[0],
            ancho_cm=dims[1],
            estado="DISPONIBLE",
            consumo_origen_id=referencia_id,
            consumo_origen_tipo=consumo_origen_tipo,
            observaciones=f"Restante de abrir lámina para {cantidad} corte(s) "
                          f"de {lc.normalize()}×{ac.normalize()}",
        )
        db.add(sobrante)
        db.flush()

    return {
        "laminas_consumidas": n_laminas,
        "costo_unitario": costo_unit,
        "costo_total": costo_total,
        "sobrante": sobrante,
        "detalle": _detalle_corte(cantidad, lc, ac, n_laminas, sobrante),
    }


def revertir_consumo_por_cortes(
    db,
    *,
    material: Material,
    consumo_id: int,
    consumo_tipo: str,
    cantidad_cortes,
    largo_corte_cm,
    ancho_corte_cm,
    origen_sobrante_id: int | None,
    laminas_consumidas,
    ubicacion_id: int,
) -> str:
    """
    Reversa exacta de consumir_por_cortes al eliminar un consumo:
      - Origen lámina nueva → ENTRADA de las láminas descontadas + se borran
        los sobrantes que ESE consumo creó (si siguen disponibles).
      - Origen sobrante → se re-crea un retazo con el área consumida
        (aproximado: el original pudo haber cambiado; queda marcado para revisar).
    Devuelve texto del detalle para el kardex.
    """
    lc, ac = laminas.validar_corte(material, largo_corte_cm, ancho_corte_cm)
    area_corte = lc * ac

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
        borrados = (
            db.query(inv_model.SobranteLamina)
            .filter(
                inv_model.SobranteLamina.consumo_origen_id == consumo_id,
                inv_model.SobranteLamina.consumo_origen_tipo == consumo_tipo,
                inv_model.SobranteLamina.estado == "DISPONIBLE",
            )
            .delete(synchronize_session=False)
        )
        db.flush()
        return f"Reversa: +{n_laminas.normalize()} lámina(s), {borrados} sobrante(s) eliminado(s)"

    # Origen sobrante: re-crear el retazo con el área consumida.
    area_consumida = _dec(cantidad_cortes) * area_corte
    propuesta = laminas.proponer_sobrante(material.largo_cm, material.ancho_cm, area_consumida)
    if propuesta is None:
        propuesta = (ac, lc)
    sobrante = inv_model.SobranteLamina(
        material_id=material.id,
        ubicacion_id=ubicacion_id,
        largo_cm=propuesta[0],
        ancho_cm=propuesta[1],
        estado="DISPONIBLE",
        observaciones=f"Reversa de consumo #{consumo_id}: revisar medidas del retazo",
    )
    db.add(sobrante)
    db.flush()
    return f"Reversa: sobrante restaurado {propuesta[0].normalize()}×{propuesta[1].normalize()} (revisar medidas)"
