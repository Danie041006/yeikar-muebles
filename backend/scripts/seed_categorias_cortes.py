"""
seed_categorias_cortes.py
=========================
1. Crea las categorías de inventario (MATERIAL: LÁMINAS MDF, MELAMINA, ESPUMA,
   PINTURA, OTROS INSUMOS / PRODUCTO: COLCHONES, ELECTRODOMÉSTICOS).
2. Asigna categoría a los materiales existentes por patrón de nombre.
3. Crea el material de PRUEBA 'LAMINA DE PRUEBA MDF 15"' (150×80 cm) con
   10 láminas en el Depósito Principal, para testear el sistema de cortes.

Idempotente: se puede ejecutar varias veces sin duplicar.
Uso:  cd backend && source venv/bin/activate && python scripts/seed_categorias_cortes.py
"""
import os
import re
import sys
from decimal import Decimal

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from sqlalchemy import text
from app.db.session import session_local
from app.modules.catalogos.model import CategoriaInventario, UnidadMedida
from app.modules.productos.model import Material
from app.modules.inventory.model import Inventario, MovimientoInventario
from datetime import datetime

# ── 1. Categorías ────────────────────────────────────────────────────────────
CATEGORIAS_MATERIAL = [
    "LÁMINAS MDF",
    "MELAMINA",
    "ESPUMA",
    "PINTURA",
    "OTROS INSUMOS",
]
CATEGORIAS_PRODUCTO = [
    "COLCHONES",
    "ELECTRODOMÉSTICOS",
]

# Patrón (regex de Postgres) → categoría (el primero que coincida gana)
PATRONES_MATERIAL = [
    (r"MELAMINA|MELAMÍNICA", "MELAMINA"),
    (r"ESPUMA", "ESPUMA"),
    (r"MDF", "LÁMINAS MDF"),
    (r"PINTURA|BARNIZ|LACA|SELLADOR|MASILLA|THINNER|SOLVENTE|IMPRIMANTE|ESMALTE", "PINTURA"),
]

NOMBRE_PRUEBA = 'LAMINA DE PRUEBA MDF 15"'


def _obtener_categoria(db, nombre: str, tipo: str) -> CategoriaInventario:
    cat = db.query(CategoriaInventario).filter(
        CategoriaInventario.nombre == nombre, CategoriaInventario.tipo == tipo
    ).first()
    if not cat:
        cat = CategoriaInventario(nombre=nombre, tipo=tipo, orden=0)
        db.add(cat)
        db.flush()
    return cat


def main():
    db = session_local()
    try:
        cats_material = {}
        for nombre in CATEGORIAS_MATERIAL:
            cats_material[nombre] = _obtener_categoria(db, nombre, "MATERIAL")
        for nombre in CATEGORIAS_PRODUCTO:
            _obtener_categoria(db, nombre, "PRODUCTO")
        otros = cats_material["OTROS INSUMOS"]

        # ── 2. Asignar categorías a materiales por patrón de nombre ─────────
        # SQL directo: un UPDATE masivo por categoría es más rápido y evita
        # choques con sesiones concurrentes (uvicorn --reload abierto).
        asignados = 0
        for patron, nombre_cat in PATRONES_MATERIAL:
            res = db.execute(
                text(
                    "UPDATE material SET categoria_inventario_id = :cid, updated_at = now() "
                    "WHERE categoria_inventario_id IS NULL AND nombre ~ :patron"
                ),
                {"cid": cats_material[nombre_cat].id, "patron": patron},
            )
            asignados += res.rowcount or 0
        res = db.execute(
            text(
                "UPDATE material SET categoria_inventario_id = :cid, updated_at = now() "
                "WHERE categoria_inventario_id IS NULL"
            ),
            {"cid": otros.id},
        )
        asignados += res.rowcount or 0

        # ── 3. Material de PRUEBA (lámina 150×80 cm) ────────────────────────
        prueba = db.query(Material).filter(Material.nombre == NOMBRE_PRUEBA).first()
        if not prueba:
            unidad = db.query(UnidadMedida).filter(UnidadMedida.nombre.ilike("%lamina%")).first()
            if not unidad:
                unidad = UnidadMedida(nombre="LAMINA", abreviatura="LAM")
                db.add(unidad)
                db.flush()
            prueba = Material(
                nombre=NOMBRE_PRUEBA,
                unidad_medida_id=unidad.id,
                costo_base=Decimal("180000"),
                stock_minimo=Decimal("4"),
                activo=True,
                largo_cm=Decimal("150"),
                ancho_cm=Decimal("80"),
                categoria_inventario_id=cats_material["LÁMINAS MDF"].id,
            )
            db.add(prueba)
            db.flush()
            print(f"[+] Material de prueba creado: #{prueba.id} {NOMBRE_PRUEBA} (150×80 cm)")
        else:
            prueba.largo_cm = Decimal("150")
            prueba.ancho_cm = Decimal("80")
            prueba.categoria_inventario_id = cats_material["LÁMINAS MDF"].id
            print(f"[=] Material de prueba ya existía: #{prueba.id} (dimensiones verificadas)")

        # Stock inicial de 10 láminas en Depósito Principal (idempotente)
        ubicacion_id = 1
        if not db.query(Inventario).filter(
            Inventario.material_id == prueba.id, Inventario.ubicacion_id == ubicacion_id
        ).first():
            db.add(Inventario(material_id=prueba.id, ubicacion_id=ubicacion_id, cantidad=Decimal("10")))
            db.add(MovimientoInventario(
                material_id=prueba.id,
                ubicacion_id=ubicacion_id,
                tipo="ENTRADA",
                cantidad=Decimal("10"),
                costo_unitario=prueba.costo_base,
                referencia_tipo="inventario_inicial",
                observaciones="Inventario inicial del material de PRUEBA (cortes de lámina)",
                fecha=datetime.utcnow(),
            ))
            print("[+] Stock inicial: 10 láminas de prueba en Depósito Principal")

        db.commit()

        # Resumen
        total = db.query(Material).filter(Material.activo == True).count()
        con_cat = db.query(Material).filter(
            Material.activo == True, Material.categoria_inventario_id.isnot(None)
        ).count()
        print(f"[i] Materiales activos: {total} — con categoría: {con_cat} (asignados ahora: {asignados})")
        for cat in db.query(CategoriaInventario).filter(CategoriaInventario.tipo == "MATERIAL").all():
            n = db.query(Material).filter(Material.categoria_inventario_id == cat.id).count()
            print(f"    - {cat.nombre}: {n} materiales")
    finally:
        db.close()


if __name__ == "__main__":
    main()
