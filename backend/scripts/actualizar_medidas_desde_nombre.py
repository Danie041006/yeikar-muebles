#!/usr/bin/env python3
"""
actualizar_medidas_desde_nombre.py
==================================
Fase 2 · Bloque 0 — Pobla las medidas REALES (ancho_base/largo_base) de los
productos con receta a partir del nombre ("2X2" → 2.0x2.0, "1.60" → 1.60x1.90)
usando el catálogo de colchones estándar.

Las medidas importadas del Excel eran ficticias (1.60 x 1.90 en todas las
camas). Este script las corrige SOLO donde el nombre permite determinarlas
con confianza; el resto no se toca.

Uso:
    venv/bin/python scripts/actualizar_medidas_desde_nombre.py            # aplica
    venv/bin/python scripts/actualizar_medidas_desde_nombre.py --dry-run  # solo muestra
"""
import sys
import os

sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))

from sqlalchemy.orm import selectinload

from app.db.session import session_local
from app.modules.productos.model import Producto
from app.modules.productos.medidas_colchon import medidas_desde_nombre

MARCA = "| medidas estimadas del nombre (verificar)"


def main() -> None:
    dry_run = "--dry-run" in sys.argv
    db = session_local()

    productos = (
        db.query(Producto)
        .options(
            selectinload(Producto.secciones),
            selectinload(Producto.materiales),
        )
        .filter(Producto.activo == True)  # noqa: E712
        .all()
    )

    actualizados = 0
    marcados = 0
    sin_medidas = 0

    for p in productos:
        tiene_receta = bool(p.secciones) or bool(p.materiales)
        if not tiene_receta:
            continue
        medidas = medidas_desde_nombre(p.nombre)
        if medidas is None:
            sin_medidas += 1
            continue
        nuevo_ancho = round(medidas["ancho"], 2)
        nuevo_largo = round(medidas["largo"], 2)
        cambio = (
            float(p.ancho_base or 0) != nuevo_ancho
            or float(p.largo_base or 0) != nuevo_largo
        )
        ya_marcado = (p.descripcion or "").endswith(MARCA)
        if cambio:
            print(
                f"[CAMBIAR] #{p.id} {p.nombre[:60]:60} "
                f"{p.ancho_base}x{p.largo_base} -> {nuevo_ancho}x{nuevo_largo} "
                f"({medidas['fuente']})"
            )
            actualizados += 1
        if not ya_marcado:
            marcados += 1
        if not dry_run:
            if cambio:
                p.ancho_base = nuevo_ancho
                p.largo_base = nuevo_largo
            if not ya_marcado:
                p.descripcion = (p.descripcion or "").strip() + " " + MARCA
            db.add(p)

    if not dry_run:
        db.commit()

    print("-" * 80)
    print(
        f"{'DRY-RUN | ' if dry_run else ''}productos con receta: {actualizados + sin_medidas} | "
        f"con medidas del nombre: {actualizados} | sin medidas (sin tocar): {sin_medidas} | "
        f"por marcar: {marcados}"
    )
    db.close()


if __name__ == "__main__":
    main()