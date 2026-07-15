#!/usr/bin/env python3
"""
seed_producto_material.py
=========================
Script de ejemplo que carga la "receta paramétrica" de una Cama Nube (o el
primer producto encontrado en la BD) con materiales ficticios de referencia.

Uso:
    cd /home/daniel-castellanos/YEIKAR/backend
    ./venv/bin/python scripts/seed_producto_material.py

El script crea materiales de ejemplo si no existen, asigna las dimensiones base
al producto y luego carga las filas de producto_material con sus tipos de escala.

⚠️  Ajusta los IDs y datos según el Excel real de Carolina antes de correr en producción.
"""

import sys
from pathlib import Path

# Asegura que el backend esté en el PYTHONPATH
sys.path.append(str(Path(__file__).parent.parent))

from decimal import Decimal
from app.db.session import session_local
from app.modules.productos.model import Producto, ProductoMaterial, Material
from app.modules.catalogos.model import UnidadMedida

db = session_local()

try:
    # ------------------------------------------------------------------
    # 1. Buscar el producto "Cama Nube" (o el primero disponible)
    # ------------------------------------------------------------------
    producto = db.query(Producto).filter(
        Producto.nombre.ilike("%cama%nube%")
    ).first()

    if not producto:
        producto = db.query(Producto).filter(Producto.activo == True).first()

    if not producto:
        print("❌ No se encontró ningún producto activo. Crea uno primero en la API.")
        sys.exit(1)

    print(f"✅ Producto encontrado: [{producto.id}] {producto.nombre}")

    # Actualizar dimensiones base
    producto.ancho_base = Decimal("1.60")
    producto.largo_base = Decimal("1.90")
    producto.alto_base  = Decimal("0.60")
    db.flush()

    # ------------------------------------------------------------------
    # 2. Obtener o crear la unidad de medida "Unidad"
    # ------------------------------------------------------------------
    um_unidad = db.query(UnidadMedida).filter(
        UnidadMedida.nombre.ilike("%unidad%")
    ).first()
    if not um_unidad:
        um_unidad = UnidadMedida(nombre="Unidad", abreviatura="und")
        db.add(um_unidad)
        db.flush()

    um_metro = db.query(UnidadMedida).filter(
        UnidadMedida.nombre.ilike("%metro%")
    ).first()
    if not um_metro:
        um_metro = UnidadMedida(nombre="Metro", abreviatura="m")
        db.add(um_metro)
        db.flush()

    um_m2 = db.query(UnidadMedida).filter(
        UnidadMedida.nombre.ilike("%metro cuadrado%")
    ).first()
    if not um_m2:
        um_m2 = UnidadMedida(nombre="Metro cuadrado", abreviatura="m²")
        db.add(um_m2)
        db.flush()

    # ------------------------------------------------------------------
    # 3. Definición de materiales de ejemplo para la Cama Nube
    #    (ajusta costo_base con los precios reales del Excel)
    # ------------------------------------------------------------------
    materiales_ejemplo = [
        # (nombre,                    costo_base_COP,  um)
        ("Madera pino 1 pulgada",    85_000,   um_metro),
        ("Tablero MDF 15mm",         62_000,   um_m2),
        ("Tela tapizado premium",    45_000,   um_m2),
        ("Espuma HR-35 7cm",         38_000,   um_m2),
        ("Tornillo 2\" zinc",         80,       um_unidad),
        ("Pata madera torneada",     12_000,   um_unidad),
        ("Garrote de eje central",   25_000,   um_unidad),
    ]

    mat_db = {}
    for nombre, costo, um in materiales_ejemplo:
        m = db.query(Material).filter(Material.nombre == nombre).first()
        if not m:
            m = Material(nombre=nombre, costo_base=costo, unidad_medida_id=um.id, activo=True)
            db.add(m)
            db.flush()
            print(f"   ➕ Material creado: {nombre}")
        else:
            print(f"   ✔  Material existente: {nombre} (id={m.id})")
        mat_db[nombre] = m

    # ------------------------------------------------------------------
    # 4. Limpiar receta existente del producto (para re-seed limpio)
    # ------------------------------------------------------------------
    db.query(ProductoMaterial).filter(ProductoMaterial.producto_id == producto.id).delete()
    db.flush()

    # ------------------------------------------------------------------
    # 5. Cargar receta paramétrica
    # ------------------------------------------------------------------
    receta = [
        # --- Madera: escala LINEAL con el largo ---
        ProductoMaterial(
            producto_id=producto.id,
            material_id=mat_db["Madera pino 1 pulgada"].id,
            cantidad_base=Decimal("12.00"),   # 12 metros lineales para 1.60 × 1.90
            tipo_escala="LINEAL",
            observaciones="Listones laterales y cabecero. Escalan con el largo del mueble.",
        ),
        # --- Tablero MDF: escala por ÁREA ---
        ProductoMaterial(
            producto_id=producto.id,
            material_id=mat_db["Tablero MDF 15mm"].id,
            cantidad_base=Decimal("3.04"),    # 1.60 × 1.90 = 3.04 m²
            tipo_escala="AREA",
            observaciones="Base de la cama. Escala exactamente con el área.",
        ),
        # --- Tela: escala por ÁREA + 20% de overlap ---
        ProductoMaterial(
            producto_id=producto.id,
            material_id=mat_db["Tela tapizado premium"].id,
            cantidad_base=Decimal("3.65"),    # 3.04 × 1.20 ≈ 3.65 m²
            tipo_escala="AREA",
            observaciones="Tela del cabecero y lateral. Incluye 20% de costura y desperdicio.",
        ),
        # --- Espuma: escala por ÁREA ---
        ProductoMaterial(
            producto_id=producto.id,
            material_id=mat_db["Espuma HR-35 7cm"].id,
            cantidad_base=Decimal("3.04"),
            tipo_escala="AREA",
            observaciones="Espuma del cabecero.",
        ),
        # --- Tornillos: ESPACIADO a lo largo del perímetro ---
        ProductoMaterial(
            producto_id=producto.id,
            material_id=mat_db["Tornillo 2\" zinc"].id,
            cantidad_base=Decimal("200"),     # tornillos para la cama base
            tipo_escala="ESPACIADO",
            distancia_pauta_cm=Decimal("15"),  # un tornillo cada 15 cm
            tornillos_por_pieza=2,             # 2 tornillos por punto de anclaje
            observaciones="Tornillería general. Escala con el perímetro.",
        ),
        # --- Patas: POR_RANGO (siempre 4 para camas estándar, 6 para camas reina+) ---
        ProductoMaterial(
            producto_id=producto.id,
            material_id=mat_db["Pata madera torneada"].id,
            cantidad_base=Decimal("4"),
            tipo_escala="POR_RANGO",
            rangos=[
                {"max": 1.80, "cantidad": 4},
                {"max": 2.00, "cantidad": 4},
                {"max": 2.50, "cantidad": 6},   # camas extra-largas llevan 6 patas
            ],
            observaciones="4 patas estándar; 6 para largo > 2.00 m por estabilidad.",
        ),
        # --- Garrote de eje: FIJO (siempre 1 por cama, sin importar tamaño) ---
        ProductoMaterial(
            producto_id=producto.id,
            material_id=mat_db["Garrote de eje central"].id,
            cantidad_base=Decimal("1"),
            tipo_escala="FIJO",
            observaciones="Eje central. Siempre 1 unidad.",
        ),
        # --- Listón refuerzo central: FIJO pero SOLO si el largo > 2.00 m ---
        ProductoMaterial(
            producto_id=producto.id,
            material_id=mat_db["Madera pino 1 pulgada"].id,
            cantidad_base=Decimal("2.10"),
            tipo_escala="FIJO",
            condicion_activacion={"campo": "nuevo_largo", "op": ">", "valor": 2.00},
            observaciones="Listón refuerzo central. Solo aplica para camas > 2.00 m de largo.",
        ),
    ]

    for r in receta:
        db.add(r)

    db.commit()
    print(f"\n✅ Receta de {len(receta)} materiales cargada para [{producto.id}] {producto.nombre}")
    print(f"   Dimensiones base: {producto.ancho_base} m (ancho) × {producto.largo_base} m (largo)")
    print("\nPrueba el cálculo con:")
    print(f"  GET /api/v1/producto/{producto.id}/calcular-precio?ancho=2.00&largo=1.95&ganancia=40")

except Exception as e:
    db.rollback()
    print(f"❌ Error: {e}")
    import traceback
    traceback.print_exc()
finally:
    db.close()
