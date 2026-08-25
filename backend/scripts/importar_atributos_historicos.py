#!/usr/bin/env python3
"""
importar_atributos_historicos.py
================================
Genera atributos de similitud para camas a partir de sus recetas (producto_material).

Pobla DOS tablas:
  - cama_historica_atributos  (legacy, compatibilidad)
  - mueble_atributos          (genérica, motor IQE v2)

Ejecutar después de importar productos desde Excel:
  backend/venv/bin/python backend/scripts/importar_atributos_historicos.py
"""

import os
import sys

sys.path.append(os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))

from app.db.session import session_local
from app.modules.productos.model import (
    Producto,
    ProductoMaterial,
    CamaHistoricaAtributos,
    MuebleAtributos,
)
from app.modules.quotes.vision_provider import FurnitureAttributes


def clasificar_patas(materiales: list[str]) -> str:
    for m in materiales:
        m_upper = m.upper()
        if "PATA" in m_upper:
            if any(k in m_upper for k in ("PLATEADA", " L ", "METAL", "ALUMINIO")):
                return "metal"
            return "madera"
    return "sin_patas"


def inferir_atributos_cama(cama: Producto, receta: list[ProductoMaterial]) -> FurnitureAttributes:
    mats = [pm.material.nombre for pm in receta if pm.material]
    mats_upper = [m.upper() for m in mats]
    nombre_upper = (cama.nombre or "").upper()

    tiene_tapiceria = any(
        k in m for m in mats_upper
        for k in ("TELA", "ESPUMA", "ALGODON", "FIBRA", "CAPITONE", "POLIPIEL")
    )
    tiene_nocheros = (
        "NOCHERO" in nombre_upper
        or "CON MESA DE NOCHE" in nombre_upper
        or any("NOCHERO" in m for m in mats_upper)
    )
    tiene_espejo = any("ESPEJO" in m or "BISELADO" in m for m in mats_upper)
    tiene_luces = any(
        k in m for m in mats_upper
        for k in ("CABLE", "APAGADOR", "LUCES", "TOMA", "SWITCH", "LED")
    )
    tipo_patas = clasificar_patas(mats)

    estilo = "moderno"
    if any(k in nombre_upper for k in ("ROMANA", "DINASTIA", "VENECIA", "CLASIC", "IMPERIO")):
        estilo = "clasico"
    elif any(k in nombre_upper for k in ("RUSTIC", "CAMPESTR")):
        estilo = "rustico"

    return FurnitureAttributes(
        tipo_mueble="cama",
        familia_probable="tapizada" if tiene_tapiceria else "melamina",
        estilo_general=estilo,
        tipo_patas=tipo_patas,
        tiene_tapiceria=tiene_tapiceria,
        tiene_luces=tiene_luces,
        nivel_confianza=1.0,
        observaciones=None,
        atributos_extra={"tiene_nocheros": tiene_nocheros, "tiene_espejo": tiene_espejo},
    )


def main() -> int:
    db = session_local()
    try:
        camas = db.query(Producto).filter(Producto.nombre.ilike("%Cama%")).all()
        print(f"Se encontraron {len(camas)} camas en la base de datos.")

        db.query(CamaHistoricaAtributos).delete()
        db.query(MuebleAtributos).filter(MuebleAtributos.tipo_mueble == "cama").delete()
        db.commit()

        count = 0
        for cama in camas:
            receta = (
                db.query(ProductoMaterial)
                .filter(ProductoMaterial.producto_id == cama.id)
                .all()
            )
            attrs = inferir_atributos_cama(cama, receta)
            vector = attrs.to_vector()

            db.add(CamaHistoricaAtributos(
                producto_id=cama.id,
                tiene_tapiceria=attrs.tiene_tapiceria,
                tiene_nocheros=attrs.tiene_nocheros(),
                tiene_espejo=attrs.tiene_espejo(),
                tiene_luces=attrs.tiene_luces,
                tipo_patas=attrs.tipo_patas,
                estilo_general=attrs.estilo_general,
                vector_similitud=vector,
            ))

            db.add(MuebleAtributos(
                producto_id=cama.id,
                tipo_mueble="cama",
                familia_probable=attrs.familia_probable,
                estilo_general=attrs.estilo_general,
                tipo_patas=attrs.tipo_patas,
                tiene_tapiceria=attrs.tiene_tapiceria,
                tiene_luces=attrs.tiene_luces,
                atributos_extra=attrs.atributos_extra,
                vector_similitud=vector,
            ))
            count += 1

        db.commit()
        print(
            f" Clasificación completada: {count} registros en "
            f"cama_historica_atributos y mueble_atributos (vectores 8D)."
        )
        return 0
    except Exception as e:
        db.rollback()
        print(f" Error durante la importación: {e}")
        return 1
    finally:
        db.close()


if __name__ == "__main__":
    raise SystemExit(main())
