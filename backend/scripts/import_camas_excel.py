#!/usr/bin/env python3
"""
import_camas_excel.py
====================
Importa las 68 hojas de 'CAMAS CON SUS MESAS DE NOCHE.xlsx'.

Lógica de Insumos:
  - Lee CANTIDAD y V/UNIT de cada insumo.
  - Almacena el insumo en la tabla Material con su costo_base = V/UNIT.
  - Si el insumo ya existe en la base de datos, actualiza su costo_base al V/UNIT más reciente.
  - Guarda la cantidad en ProductoMaterial.cantidad_base = CANTIDAD.
  - Ignora filas que tengan PRECIO TOTAL = 0 (no se usan para el producto).
  - Separa los materiales del nochero (observaciones="NOCHERO").
"""

import sys
import re
import traceback
from pathlib import Path
from decimal import Decimal

sys.path.append(str(Path(__file__).parent.parent))

import openpyxl
from app.db.session import session_local
from app.modules.productos.model import Producto, ProductoMaterial, Material
from app.modules.catalogos.model import TipoProducto, UnidadMedida

EXCEL_PATH = (
    Path(__file__).parent.parent.parent
    / "docs/info_para_usar/estructuras/CAMAS CON SUS MESAS DE NOCHE.xlsx"
)

PALABRAS_RESUMEN = [
    "MATERIA PRIMA", "CANTIDAD", "UNIDAD DE MEDIDA", "V/UNIT", "PRECIO TOTAL",
    "GANANCIA", "IVA", "PRECIO DE VENTA",
    "GASTOS DE", "SUB TOTAL", "SUBTOTAL", "HECHURA", "MANO DE OBRA",
    "POSTURA DE", "SECCION", "SECCIÓN", "NOMBRE DEL PRODUCTO",
    "COMERCIALIZADORA", "ESTRUCTURA", "RIF", "EBANISTA", "TOTAL A PAGAR",
    "MÁS GANANCIA", "MAS GANANCIA", "FABRICO", "FABRICÓ",
    # NOTA: "TOTAL PRODUCCION" y "TOTAL COSTO" se detectan en código, no aquí
]

UNIDADES_NORMALIZADAS = {
    "CMS": ("cm", "Centímetros"),
    "METROS": ("m", "Metros"),
    "METRO": ("m", "Metros"),
    "LITRO": ("L", "Litros"),
    "LITROS": ("L", "Litros"),
    "LAMINA": ("lam", "Láminas"),
    "LAMINAS": ("lam", "Láminas"),
    "CAJAS": ("cj", "Cajas"),
    "CAJA": ("cj", "Cajas"),
    "UNIDAD": ("und", "Unidades"),
    "UNIDADES": ("und", "Unidades"),
    "PAR": ("par", "Pares"),
    "TIRA": ("tira", "Tiras"),
    "TIRAS": ("tira", "Tiras"),
    "PEOPLE": ("people", "People"),
    "MANO DE OBRA": ("mo", "Mano de Obra"),
}


def limpiar_nombre_hoja(nombre: str) -> str:
    if not nombre:
        return "SIN NOMBRE"
    nombre = re.sub(r'\b\d{1,2}[-/]\d{1,2}[-/]\d{2,4}\b', '', nombre)
    nombre = re.sub(r'\d{1,2}//\d{2}/\d{4}', '', nombre)
    nombre = re.sub(r'\s*\(\d+\)\s*', '', nombre)
    nombre = ' '.join(nombre.split()).strip().strip('.,- ')
    return nombre[:150] if nombre else "SIN NOMBRE"


def es_fila_resumen(texto: str) -> bool:
    t = texto.upper().strip()
    return any(p in t for p in PALABRAS_RESUMEN)


def parsear_hoja(ws) -> dict:
    resultado = {
        "materiales_cama": [],
        "materiales_nochero": [],
        "precio_costo_cama": None,
        "precio_venta_cama": None,
        "precio_con_iva_cama": None,
    }

    apariciones_nombre = 0
    en_nochero = False

    for row in ws.iter_rows(values_only=True):
        celdas = list(row)
        if not any(v is not None for v in celdas):
            continue

        fila_txt = " ".join(str(v) for v in celdas if v is not None).upper()
        nums = [v for v in celdas if isinstance(v, (int, float)) and v > 0]

        # Detectar secciones
        if "NOMBRE DEL PRODUCTO" in fila_txt:
            apariciones_nombre += 1
            if apariciones_nombre >= 2:
                en_nochero = True
            continue

        # Totales de costos:
        # "TOTAL PRODUCCION" = costo real de fabricación (lo que cuesta producir la cama)
        # "TOTAL COSTO" = contiene la ganancia (40% u otro %), NO el costo de producción
        # "PRECIO DE VENTA DEL PRODUCTO" = precio final sin IVA
        # "TOTAL A PAGAR" = precio con IVA
        if "TOTAL PRODUCCION" in fila_txt or "TOTAL PRODUCCIÓN" in fila_txt:
            if nums and resultado["precio_costo_cama"] is None:
                resultado["precio_costo_cama"] = Decimal(str(nums[0]))
            continue

        if "TOTAL COSTO" in fila_txt:
            # Contiene el porcentaje de ganancia y su monto, no el costo de producción.
            # Solo lo usamos si todavía no tenemos precio_costo
            continue

        if "PRECIO DE VENTA DEL PRODUCTO" in fila_txt:
            if nums:
                resultado["precio_venta_cama"] = Decimal(str(nums[0]))
            continue

        if "TOTAL A PAGAR" in fila_txt:
            if nums:
                resultado["precio_con_iva_cama"] = Decimal(str(nums[0]))
            continue

        # Materiales
        col_a = str(celdas[0]).strip() if celdas[0] is not None else ""
        if len(col_a) < 3 or es_fila_resumen(col_a):
            continue

        # Verificar si hay PRECIO TOTAL > 0 en la fila
        precio_total = None
        if len(celdas) > 5 and isinstance(celdas[5], (int, float)) and celdas[5] > 0:
            precio_total = Decimal(str(celdas[5]))
        elif len(celdas) > 4 and isinstance(celdas[4], (int, float)) and celdas[4] > 0:
            # Si solo tiene 5 columnas, la última es el total
            if len(celdas) == 5:
                precio_total = Decimal(str(celdas[4]))

        if precio_total:
            # Obtener cantidad
            qty = celdas[1] if len(celdas) > 1 else None
            cantidad = Decimal(str(qty)) if isinstance(qty, (int, float)) and qty > 0 else Decimal("1")

            # Obtener unidad
            unidad_excel = str(celdas[2]).strip() if len(celdas) > 2 and celdas[2] is not None else "Global"
            
            # Obtener valor unitario
            v_unit = None
            if len(celdas) > 4 and isinstance(celdas[4], (int, float)) and celdas[4] > 0:
                v_unit = Decimal(str(celdas[4]))
            elif len(celdas) > 3 and isinstance(celdas[3], (int, float)) and celdas[3] > 0:
                v_unit = Decimal(str(celdas[3]))
            
            if not v_unit:
                v_unit = precio_total / cantidad

            item = {
                "nombre": col_a[:150],
                "cantidad": cantidad,
                "unidad": unidad_excel,
                "v_unit": v_unit
            }

            if en_nochero:
                resultado["materiales_nochero"].append(item)
            else:
                resultado["materiales_cama"].append(item)

    return resultado


def get_or_create_unidad(db, nombre_excel: str) -> UnidadMedida:
    norm = nombre_excel.upper().strip()
    abrev, nombre_completo = UNIDADES_NORMALIZADAS.get(norm, (norm.lower()[:10], norm[:50]))
    
    u = db.query(UnidadMedida).filter(
        (UnidadMedida.nombre.ilike(nombre_completo)) | 
        (UnidadMedida.abreviatura == abrev)
    ).first()
    if not u:
        u = UnidadMedida(nombre=nombre_completo, abreviatura=abrev)
        db.add(u)
        db.flush()
    return u


def get_or_create_material(db, nombre: str, v_unit: Decimal, um_id: int) -> Material:
    m = db.query(Material).filter(Material.nombre == nombre).first()
    if not m:
        m = Material(nombre=nombre, costo_base=v_unit, unidad_medida_id=um_id, activo=True)
        db.add(m)
        db.flush()
    else:
        m.costo_base = v_unit
        db.flush()
    return m


def main():
    print(f"📂 Leyendo: {EXCEL_PATH}")
    if not EXCEL_PATH.exists():
        print(f"❌ No se encontró: {EXCEL_PATH}")
        sys.exit(1)

    wb = openpyxl.load_workbook(str(EXCEL_PATH), data_only=True)
    db = session_local()
    try:
        tipo_cama = db.query(TipoProducto).filter(TipoProducto.nombre.ilike("%cama%")).first()
        if not tipo_cama:
            tipo_cama = db.query(TipoProducto).first()
        if not tipo_cama:
            tipo_cama = TipoProducto(nombre="Cama", descripcion="Camas y muebles de dormitorio")
            db.add(tipo_cama)
            db.flush()

        # Limpiar importaciones previas
        prev = db.query(Producto).filter(Producto.hoja_excel.isnot(None)).all()
        for p in prev:
            db.query(ProductoMaterial).filter(ProductoMaterial.producto_id == p.id).delete()
            db.delete(p)
        db.flush()
        print(f"🧹 Eliminados {len(prev)} productos anteriores del Excel\n")

        creados = 0
        for sheet_name in wb.sheetnames:
            datos = parsear_hoja(wb[sheet_name])
            nombre = limpiar_nombre_hoja(sheet_name)

            pv = datos["precio_venta_cama"]
            piva = datos["precio_con_iva_cama"]
            costo = datos["precio_costo_cama"]

            if not pv and not costo:
                continue

            # Rellenar precios nulos
            if pv and not piva:
                piva = (pv * Decimal("1.16")).quantize(Decimal("0.01"))
            if piva and not pv:
                pv = (piva / Decimal("1.16")).quantize(Decimal("0.01"))
            if not costo and pv:
                costo = (pv / Decimal("1.30")).quantize(Decimal("0.01"))

            producto = Producto(
                nombre=nombre,
                tipo_producto_id=tipo_cama.id,
                activo=True,
                hoja_excel=sheet_name,
                ancho_base=Decimal("1.60"),
                largo_base=Decimal("2.00"),
                precio_costo_base=costo,
                precio_venta_base=pv,
                precio_venta_con_iva=piva,
            )
            db.add(producto)
            db.flush()

            # Guardar materiales de la cama
            for it in datos["materiales_cama"]:
                um = get_or_create_unidad(db, it["unidad"])
                mat = get_or_create_material(db, it["nombre"], it["v_unit"], um.id)
                db.add(ProductoMaterial(
                    producto_id=producto.id,
                    material_id=mat.id,
                    cantidad_base=it["cantidad"],
                    tipo_escala="FIJO",
                    observaciones=f"hoja:{sheet_name}",
                ))

            # Guardar materiales del nochero
            for it in datos["materiales_nochero"]:
                um = get_or_create_unidad(db, it["unidad"])
                nombre_noch = f"NOCHERO | {it['nombre']}"[:150]
                mat = get_or_create_material(db, nombre_noch, it["v_unit"], um.id)
                db.add(ProductoMaterial(
                    producto_id=producto.id,
                    material_id=mat.id,
                    cantidad_base=it["cantidad"],
                    tipo_escala="FIJO",
                    observaciones="NOCHERO",
                ))

            db.flush()
            print(f"  ✅ {nombre[:40]:<40} | Costo: {costo:,.0f} | Venta: {pv:,.0f} | Cama: {len(datos['materiales_cama'])} noch: {len(datos['materiales_nochero'])}")
            creados += 1

        db.commit()
        print(f"\n✅ ¡Importación finalizada con éxito! Total: {creados} productos.")

    except Exception as e:
        db.rollback()
        print(f"\n❌ Error: {e}")
        traceback.print_exc()
        sys.exit(1)
    finally:
        db.close()


if __name__ == "__main__":
    main()
