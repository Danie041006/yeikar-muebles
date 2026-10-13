"""Sembrar la unidad base y las equivalencias de uso del COLBÓN.

El taller compra el COLBÓN por CUÑETE pero lo consume por GALÓN, PISTOLADA o
LITRO. Este script (idempotente, dry-run por defecto):

  1. Crea la unidad de medida "Cuñete" (Cuñ) si no existe.
  2. A los materiales cuyo nombre contenga "COLBON" y "CUÑETE" les fija la
     unidad base = Cuñete (solo re-etiqueta: las cantidades no cambian).
  3. Les carga las equivalencias PRÁCTICAS del taller (ajustables después en
     Inventario → Editar Insumo):
         1 CUÑETE = 16 PISTOLADAS = 5 GALONES
         1 GALÓN  = 3,785 LITROS  → 1 CUÑETE = 18,925 LITROS
     El factor práctico manda: si en el taller rinde distinto, se corrige en
     la UI (el sistema no lo cruza ni lo "corrige").

Ejecutar:
    cd backend && venv/bin/python scripts/sembrar_unidades_uso_colbon.py            # dry-run
    cd backend && venv/bin/python scripts/sembrar_unidades_uso_colbon.py --aplicar
"""

import argparse
import os
import sys
from decimal import Decimal

sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))

import app.main  # noqa: F401
from app.db.session import session_local


PISTOLADAS_POR_CUNETE = Decimal("16")
GALONES_POR_CUNETE = Decimal("5")
LITROS_POR_GALON = Decimal("3.785")

UNIDADES_USO = [
    ("PISTOLADA", (Decimal("1") / PISTOLADAS_POR_CUNETE)),
    ("GALÓN", (Decimal("1") / GALONES_POR_CUNETE)),
    ("LITRO", (Decimal("1") / (GALONES_POR_CUNETE * LITROS_POR_GALON))),
]


def obtener_o_crear_cunete(db):
    from app.modules.catalogos.model import UnidadMedida

    unidad = db.query(UnidadMedida).filter(UnidadMedida.nombre == "Cuñete").first()
    if unidad:
        return unidad, False
    unidad = UnidadMedida(nombre="Cuñete", abreviatura="Cuñ")
    db.add(unidad)
    db.flush()
    return unidad, True


def main(aplicar: bool = False):
    from app.modules.productos.model import Material, MaterialUnidadUso

    db = session_local()
    try:
        unidad_cunete, creada_unidad = obtener_o_crear_cunete(db)
        if creada_unidad:
            print(f"[UNIDAD] creada: Cuñete (Cuñ) id={unidad_cunete.id}")
        else:
            print(f"[UNIDAD] ya existe: Cuñete (Cuñ) id={unidad_cunete.id}")

        materiales = (
            db.query(Material)
            .filter(Material.nombre.ilike("%COLBON%"), Material.nombre.ilike("%CUÑETE%"))
            .order_by(Material.id)
            .all()
        )
        if not materiales:
            print("No se encontraron materiales COLBÓN CUÑETE.")

        for mat in materiales:
            print(f"\n[MATERIAL #{mat.id}] {mat.nombre}")
            if mat.unidad_medida_id != unidad_cunete.id:
                print(f"  unidad base: #{mat.unidad_medida_id} → Cuñete (Cuñ)")
                if aplicar:
                    mat.unidad_medida_id = unidad_cunete.id

            existentes = {u.nombre: u for u in mat.unidades_uso}
            for nombre, factor in UNIDADES_USO:
                factor = factor.quantize(Decimal("0.0000000001"))
                fila = existentes.get(nombre)
                if fila:
                    print(f"  {nombre}: ya existe (factor {fila.factor_base}) — no se toca")
                    continue
                print(f"  + {nombre}: 1 {nombre} = {factor} CUÑETE")
                if aplicar:
                    db.add(MaterialUnidadUso(
                        material_id=mat.id, nombre=nombre, factor_base=factor,
                    ))

        if aplicar:
            db.commit()
            print("\nAplicado.")
        else:
            print("\nDry-run: usa --aplicar para guardar los cambios.")
    finally:
        db.close()


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--aplicar", action="store_true", help="Guardar los cambios en la BD")
    args = parser.parse_args()
    main(aplicar=args.aplicar)
