#!/usr/bin/env python3
"""
importar_recetas_secciones.py
==============================
Importa las estructuras de costos del Excel (CAMAS CON SUS MESAS DE NOCHE.xlsx)
hacia el nuevo esquema jerárquico por secciones:
  Producto -> SeccionProducto -> ElementoSeccion (Insumos Físicos)
                              -> PoliticaSeccion (MO Base, % Liquidación, % Gastos)

Desconecta totalmente los precios unitarios e importes monetarios viejos del Excel.
"""

import sys
import re
import argparse
import traceback
from pathlib import Path
from decimal import Decimal, InvalidOperation

sys.path.append(str(Path(__file__).parent.parent))

import openpyxl
from app.db.session import session_local
from app.modules.productos.model import Producto, SeccionProducto, ElementoSeccion, PoliticaSeccion
from app.modules.catalogos.model import TipoProducto, UnidadMedida

EXCEL_PATH = (
    Path(__file__).parent.parent.parent
    / "docs/info_para_usar/estructuras/CAMAS CON SUS MESAS DE NOCHE.xlsx"
)

HEADERS_SECCION = [
    (r"TAPICER[IÍ]A", "TAPICERÍA"),
    (r"TERMINACI[OÓ]N", "TERMINACIÓN"),
    (r"PINTURA", "PINTURA"),
    (r"TENDIDO", "TENDIDO"),
    (r"COLA DE PATO", "COLA DE PATO"),
    (r"EBANISTER[IÍ]A", "EBANISTERÍA"),
    (r"MARCO", "MARCO"),
]

PREFIJOS_IGNORAR = (
    "TOTAL", "SUBTOTAL", "SUB TOTAL", "COSTO DE",
    "TOTAL COSTO DE PRODUCCION", "TOTAL COSTO DE PRODUCCIÓN", "TOTAL PRODUCCION", "TOTAL PRODUCCIÓN",
    "PRECIO DE VENTA", "Precio de Venta", "IVA", "TOTAL A PAGAR", "Total a Pagar",
    "MÁS GANANCIA", "MAS GANANCIA", "Más Ganancia", "MATERIA PRIMA",
    "COMERCIALIZADORA", "ESTRUCTURA", "RIF", "FECHA",
    "EBANISTA", "FABRICO", "FABRICÓ", "VALOR DE", "CONCEPTO"
)


def limpiar_texto(val) -> str:
    if val is None:
        return ""
    txt = str(val).strip()
    return ' '.join(txt.split())


def es_encabezado_seccion(texto_fila: str, componente_actual: str) -> tuple[str | None, str]:
    """
    Recibe el texto combinado de la fila.
    Retorna (nombre_seccion_normalizado, nuevo_componente_actual)
    Ej: ("EBANISTERÍA", "CAMA") ó ("EBANISTERÍA (NOCHEROS)", "NOCHEROS")
    """
    txt_upper = texto_fila.upper()

    nuevo_comp = componente_actual
    if "NOMBRE DEL PRODUCTO:" in txt_upper or "NOCHERO" in txt_upper:
        if "NOCHERO" in txt_upper:
            nuevo_comp = "NOCHEROS"
        elif "NOMBRE DEL PRODUCTO:" in txt_upper:
            nuevo_comp = "CAMA"

    for pat, sec_norm in HEADERS_SECCION:
        if re.search(pat, txt_upper):
            # Si el texto de la fila o el contexto actual indica Nochero
            is_nochero = (nuevo_comp == "NOCHEROS") or ("NOCHERO" in txt_upper)
            if is_nochero:
                return (f"{sec_norm} (NOCHEROS)", "NOCHEROS")
            else:
                return (sec_norm, "CAMA")

    # Si es solo una fila de 'NOMBRE DEL PRODUCTO: NOCHEROS EN CRUDO' sin la palabra EBANISTERÍA explícita
    if "NOMBRE DEL PRODUCTO:" in txt_upper and "NOCHERO" in txt_upper:
        return ("EBANISTERÍA (NOCHEROS)", "NOCHEROS")

    return (None, nuevo_comp)


def extraer_porcentaje(texto: str) -> Decimal | None:
    match = re.search(r'(\d+(?:\.\d+)?)\s*%', texto)
    if match:
        try:
            return Decimal(match.group(1))
        except (ValueError, InvalidOperation):
            return None
    return None


def extraer_monto(texto: str) -> Decimal | None:
    match = re.search(r'(\d{2,3}(?:\.\d{3})+|\d{4,7})', texto)
    if match:
        try:
            val_clean = match.group(1).replace('.', '')
            return Decimal(val_clean)
        except (ValueError, InvalidOperation):
            return None
    return None


def procesar_hoja(sheet, db, dry_run=True):
    nombre_hoja = sheet.title.strip()
    print(f"\n📄 Procesando hoja: '{nombre_hoja}'")

    # 1. Obtener producto existente o crear
    nombre_prod = None
    for r in range(1, 10):
        for c in range(1, 6):
            val = sheet.cell(row=r, column=c).value
            if val and "NOMBRE DEL PRODUCTO:" in str(val).upper() and "NOCHERO" not in str(val).upper():
                val_prod = sheet.cell(row=r, column=c+2).value or sheet.cell(row=r, column=c+1).value
                if val_prod:
                    nombre_prod = limpiar_texto(val_prod)
                    break
        if nombre_prod:
            break

    if not nombre_prod:
        nombre_prod = f"CAMA MODELO {nombre_hoja.upper()}"

    # Limpiar el nombre del Excel: quitar fechas y medidas para el matching
    import re as _re
    nombre_limpio = _re.sub(r'\d{1,2}[/\-]\d{1,2}[/\-]?\d{0,4}', '', nombre_prod)  # quitar fechas
    nombre_limpio = _re.sub(r'\b\d+[xX*]\d+\b', '', nombre_limpio)  # quitar medidas como 2X2
    nombre_limpio = ' '.join(nombre_limpio.split()).strip()

    # Intento 1: nombre del Excel (limpio) dentro del nombre en BD
    producto = None
    if nombre_limpio:
        producto = db.query(Producto).filter(Producto.nombre.ilike(f"%{nombre_limpio}%")).first()

    # Intento 2: nombre completo del Excel dentro del nombre en BD
    if not producto and nombre_prod != nombre_limpio:
        producto = db.query(Producto).filter(Producto.nombre.ilike(f"%{nombre_prod}%")).first()

    # Intento 3: nombre en BD dentro del nombre del Excel
    # Solo si el nombre BD tiene al menos 8 caracteres (evita falsos positivos con "CAMA")
    if not producto:
        todos = db.query(Producto).filter(Producto.nombre.isnot(None)).all()
        for p in todos:
            nombre_bd = (p.nombre or "").strip().upper()
            if len(nombre_bd) >= 8 and nombre_bd in nombre_prod.upper():
                producto = p
                break

    # Intento 4: por hoja_excel exacta
    if not producto:
        producto = db.query(Producto).filter(Producto.hoja_excel == nombre_hoja).first()

    if not producto and not dry_run:
        tipo_cama = db.query(TipoProducto).filter(TipoProducto.nombre.ilike("%cama%")).first()
        producto = Producto(
            nombre=nombre_prod,
            tipo_producto_id=tipo_cama.id if tipo_cama else 1,
            hoja_excel=nombre_hoja,
            ancho_base=Decimal("1.60"),
            largo_base=Decimal("1.90")
        )
        db.add(producto)
        db.flush()

    prod_id = producto.id if producto else 9999
    prod_name = producto.nombre if producto else nombre_prod
    print(f"   ↳ Producto en BD: [{prod_id}] {prod_name}")

    # 2. Recorrer filas organizando por Sección
    seccion_actual = "EBANISTERÍA"
    componente_actual = "CAMA"
    secciones_creadas = {}
    elementos_por_seccion = {}
    politica_por_seccion = {}

    def asegurar_seccion(sec_name):
        if sec_name not in secciones_creadas:
            secciones_creadas[sec_name] = len(secciones_creadas) + 1
            elementos_por_seccion[sec_name] = []
            politica_por_seccion[sec_name] = {
                "mano_obra_base": Decimal("0"),
                "pct_liquidacion_mo": Decimal("5.00"),
                "pct_gastos_seccion": Decimal("10.00") if "EBANISTERÍA" in sec_name else Decimal("0.00")
            }

    asegurar_seccion(seccion_actual)

    for row in range(1, sheet.max_row + 1):
        c1 = limpiar_texto(sheet.cell(row=row, column=1).value)
        c2 = sheet.cell(row=row, column=2).value  # Cantidad o detalle
        c3 = limpiar_texto(sheet.cell(row=row, column=3).value)  # Unidad
        c4 = sheet.cell(row=row, column=4).value  # Valor unitario / notas
        c5 = sheet.cell(row=row, column=5).value  # Precio total en Excel

        if not c1 and not c2 and not c3:
            continue

        c1_upper = c1.upper()
        texto_fila_completo = f"{c1} {c2 or ''} {c3} {c4 or ''}".strip()

        # A. Verificar si es cambio de sección o nuevo componente (CAMA vs NOCHEROS)
        nueva_sec, componente_actual = es_encabezado_seccion(texto_fila_completo, componente_actual)
        if nueva_sec:
            seccion_actual = nueva_sec
            asegurar_seccion(seccion_actual)
            continue

        # B. Ignorar encabezados de tabla o títulos
        if "MATERIA PRIMA" in c1_upper and not c2:
            continue



        # C. Verificar si es fila de Gastos Indirectos (ej: "gastos de Ebanisteria e 10%")
        if "GASTOS DE" in c1_upper or ("GASTOS" in c1_upper and "%" in c1_upper):
            pct = extraer_porcentaje(c1_upper)
            if pct is not None:
                politica_por_seccion[seccion_actual]["pct_gastos_seccion"] = pct
                print(f"     [POLÍTICA] {seccion_actual} -> Gastos Sección: {pct}%")
            continue

        # D. Verificar si es fila de Mano de Obra (ej: "ebanisteria 300.000 x 5% de m.o" o "HECHURA")
        if "M.O" in c1_upper or "HECHURA" in c1_upper or "MANO DE OBRA" in c1_upper or "PAGO" in c1_upper:
            monto = extraer_monto(c1)
            pct_liq = extraer_porcentaje(c1)
            if monto is not None and monto > 0:
                politica_por_seccion[seccion_actual]["mano_obra_base"] = monto
            elif c5 and isinstance(c5, (int, float, Decimal)) and c5 > 0:
                politica_por_seccion[seccion_actual]["mano_obra_base"] = Decimal(str(c5))

            if pct_liq is not None:
                politica_por_seccion[seccion_actual]["pct_liquidacion_mo"] = pct_liq

            print(f"     [MANO DE OBRA] {seccion_actual} -> Base: ${politica_por_seccion[seccion_actual]['mano_obra_base']:,.2f} | Liq: {politica_por_seccion[seccion_actual]['pct_liquidacion_mo']}%")
            continue

        # E. Omitir subtotales/totales
        if any(c1_upper.startswith(pref) for pref in PREFIJOS_IGNORAR):
            continue

        # F. Si llega aquí, es un INSUMO FÍSICO
        # Extraer cantidad limpia
        cant = Decimal("1.0")
        if c2 is not None:
            try:
                if isinstance(c2, (int, float, Decimal)):
                    cant = Decimal(str(c2))
                else:
                    txt_c2 = str(c2).replace(',', '.').strip()
                    cant = Decimal(txt_c2)
            except (ValueError, InvalidOperation):
                cant = Decimal("1.0")

        elementos_por_seccion[seccion_actual].append({
            "nombre": c1[:150],
            "cantidad": cant,
            "unidad": c3[:50],
            "observaciones": f"Nota: {c4}" if c4 and not str(c4).replace('.', '').isdigit() else None
        })

    # Imprimir resumen de lo extraído
    for sec, elems in elementos_por_seccion.items():
        pol = politica_por_seccion[sec]
        print(f"   📍 SECCIÓN: {sec} ({len(elems)} insumos físicos)")
        print(f"      MO Base: ${pol['mano_obra_base']:,.2f} | Liq: {pol['pct_liquidacion_mo']}% | Gastos: {pol['pct_gastos_seccion']}%")
        for el in elems[:3]:
            print(f"        • {el['nombre']} | Cant: {el['cantidad']} {el['unidad']}")
        if len(elems) > 3:
            print(f"        ... ({len(elems)-3} más)")

    # 3. Guardar en BD si no es dry_run
    if not dry_run and producto:
        # Borrar secciones anteriores de este producto para reimportar limpiamente
        db.query(SeccionProducto).filter(SeccionProducto.producto_id == producto.id).delete()
        db.flush()

        for sec_name, orden in secciones_creadas.items():
            db_sec = SeccionProducto(
                producto_id=producto.id,
                nombre=sec_name,
                orden=orden
            )
            db.add(db_sec)
            db.flush()

            # Crear Política de la Sección
            pol_data = politica_por_seccion[sec_name]
            db_pol = PoliticaSeccion(
                seccion_id=db_sec.id,
                mano_obra_base=pol_data["mano_obra_base"],
                pct_liquidacion_mo=pol_data["pct_liquidacion_mo"],
                pct_gastos_seccion=pol_data["pct_gastos_seccion"]
            )
            db.add(db_pol)

            # Crear Elementos Insumos Físicos
            for el in elementos_por_seccion[sec_name]:
                db_el = ElementoSeccion(
                    seccion_id=db_sec.id,
                    nombre_insumo_original=el["nombre"],
                    cantidad=el["cantidad"],
                    unidad_medida=el["unidad"],
                    observaciones=el["observaciones"],
                    estado_resolucion="PENDIENTE",
                    precio_unitario=None,
                    costo_subtotal=None
                )
                db.add(db_el)

        db.commit()
        print(f"   ✅ Secciones e insumos guardados correctamente para {producto.nombre}")


def main():
    parser = argparse.ArgumentParser(description="Importar estructuras por secciones")
    parser.add_argument("--sheet", help="Importar solo una hoja específica")
    parser.add_argument("--write", action="store_true", help="Guardar cambios en la base de datos (por defecto es dry-run)")
    args = parser.parse_args()

    wb = openpyxl.load_workbook(EXCEL_PATH, data_only=True)
    db = session_local()

    try:
        if args.sheet:
            if args.sheet in wb.sheetnames:
                procesar_hoja(wb[args.sheet], db, dry_run=not args.write)
            else:
                print(f"❌ Hoja '{args.sheet}' no encontrada.")
        else:
            for sname in wb.sheetnames:
                procesar_hoja(wb[sname], db, dry_run=not args.write)
    finally:
        db.close()


if __name__ == "__main__":
    main()
