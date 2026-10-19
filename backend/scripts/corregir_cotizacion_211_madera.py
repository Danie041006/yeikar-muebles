"""
Corrige la cotización histórica #211 (madera cotizada en cm, guardada como m³).

La señora escribió 1128 cm × 160 COP/cm = 180.480. El renglón quedó con
cantidad=1128 (m³) y costo_total=1.804.800.000. Este script deja el renglón
coherente:
  - cantidad: 1128 (se conserva, es lo que ve el cliente)
  - precio: 160 (se conserva)
  - unidad_captura: 'CM'
  - cantidad_base: 0,1128 m³
  - costo_materiales / costo_total: 180.480 COP

Uso (por defecto solo muestra, no escribe):
    venv/bin/python scripts/corregir_cotizacion_211_madera.py
    venv/bin/python scripts/corregir_cotizacion_211_madera.py --aplicar
"""
import argparse
import sys
from decimal import Decimal
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from app.main import app  # noqa: F401  (carga todos los mappers)
from app.db.session import session_local
from app.modules.quotes.model import Cotizacion, DetalleCotizacion
from app.modules.productos.model import Material

COTIZACION_ID = 211
CANTIDAD_CM = Decimal("1128")
CANTIDAD_BASE = Decimal("0.1128")
COSTO_REAL = Decimal("180480.00")


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--aplicar", action="store_true", help="escribe los cambios")
    args = parser.parse_args()

    db = session_local()
    try:
        cot = db.query(Cotizacion).filter(Cotizacion.id == COTIZACION_ID).first()
        if not cot:
            print(f"No existe la cotización #{COTIZACION_ID}.")
            return 1

        detalles = (
            db.query(DetalleCotizacion)
            .filter(
                DetalleCotizacion.cotizacion_id == COTIZACION_ID,
                DetalleCotizacion.tipo_item == "INSUMO",
            )
            .all()
        )
        if not detalles:
            print(f"La cotización #{COTIZACION_ID} no tiene renglones INSUMO.")
            return 1

        for det in detalles:
            material = (
                db.query(Material).filter(Material.id == det.material_id).first()
            )
            if not material or "madera" not in (material.nombre or "").lower():
                print(
                    f"  detalle #{det.id}: material #{det.material_id} "
                    f"({material.nombre if material else '?'}) no es madera; se omite."
                )
                continue
            if Decimal(str(det.cantidad)) != CANTIDAD_CM:
                print(
                    f"  detalle #{det.id}: cantidad {det.cantidad} != {CANTIDAD_CM}; "
                    "se omite por seguridad."
                )
                continue

            print(f"Antes detalle #{det.id}:")
            print(
                f"  cantidad={det.cantidad} precio={det.precio} "
                f"costo_total={det.costo_total} "
                f"unidad_captura={det.unidad_captura} cantidad_base={det.cantidad_base}"
            )
            det.unidad_captura = "CM"
            det.cantidad_base = CANTIDAD_BASE
            det.costo_materiales = COSTO_REAL
            det.costo_total = COSTO_REAL
            print(
                f"Después detalle #{det.id}: cantidad={det.cantidad} precio={det.precio} "
                f"costo_total={det.costo_total} unidad_captura={det.unidad_captura} "
                f"cantidad_base={det.cantidad_base}"
            )

        if args.aplicar:
            db.commit()
            print("Cambios aplicados.")
        else:
            db.rollback()
            print("Simulación: no se escribió nada. Usa --aplicar para guardar.")
        return 0
    finally:
        db.close()


if __name__ == "__main__":
    raise SystemExit(main())
