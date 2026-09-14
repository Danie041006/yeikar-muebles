# -*- coding: utf-8 -*-
"""Migra las notas de entrega transcritas de fotos (cotizaciones_extraidas/)
al ERP: Cliente → Cotización (APROBADA) → Pedido (ENTREGADO) → Venta + Pagos.

Fuentes de verdad:
- El TOTAL y los ABONOS del papel mandan (los errores de multiplicación de
  filas no bloquean: el detalle de items es informativo).
- Cada nota queda registrada en SU moneda (USD o VES). La tabla de tasas está
  vacía: tasa_cambio=1.0 y total_en_moneda_base NULL hasta configurar tasas.

Reglas especiales (decididas con el dueño):
- N09 Zulima: DESCUENTO −$40 del 29/7 → venta total 4.020.
- N16 Daniel #2: solo los 3 abonos IMPRESOS (1.000). Los 2 manuscritos de 500
  no se registran (aritmética imposible: saldo papel 500, calculado −522).
- N21 Arnulfo: verbatim Bs (total 3.364.500.000, abono 2.200.000). Flag: el
  papel manuscrito dice saldo 1.364.500.000, aritmética da 1.362.500.000.
- N23 UNIHOME (resumen 59.175): NO genera venta (es consolidación de las
  notas N24/N25/N26); se documenta en observaciones del cliente.
- UNIHOME: 3 ventas (Feb 32.350 · Mar 25.160 con descuento caletas integrado ·
  Jun 25.845) + pagos únicos sin repetir entre hojas.

Uso:
    python scripts/migrar_notas_fotos.py                # dry-run
    python scripts/migrar_notas_fotos.py --ejecutar     # commit real
    python scripts/migrar_notas_fotos.py --db-url postgresql://...
    python scripts/migrar_notas_fotos.py --solo N01,N16
"""
import argparse
import json
import os
import re
import sys
import unicodedata
from datetime import date
from decimal import Decimal
from pathlib import Path

sys.path.insert(0, os.path.abspath(os.path.dirname(__file__) + "/.."))

RAIZ = Path(os.path.abspath(os.path.dirname(__file__) + "/../..")) / "cotizaciones_extraidas"

TAG = "MIGRA-N{:02d}"

# Moneda por nota (las 4 notas de montos grandes están en BOLÍVARES)
MONEDA_OVERRIDE = {"N21": "VES", "N22": "VES", "N28": "VES", "N29": "VES"}

# Clientes existentes en la BD (tras la limpieza) ← nombre según la nota.
# None en nombre = conservar el nombre actual; los datos faltantes se rellenan.
CLIENTES_MAPA = {
    "DANIEL GOMEZ MONTOYA": ("Daniel Gomez Montoya", "V-15.958.210"),
    "LILIBETH VILLALOBOS": ("Lilibeth Villalobos", "V-13.939.895"),
    "MARIA ANGELICA BECERRA MEJIA": ("Maria Angelica Becerra Mejia", "V-32.611.004"),
    "FELIX ENRIQUE KAJALAY VEGAS": ("Felix Enrique Kajalay Vegas", "V-21.378.188"),
    "EDWAR ENMANUEL SANCHEZ VASQUEZ": ("Edwar Enmanuel Sanchez Vasquez", "V-20.475.088"),
    "TATIANA BAUTISTA": ("Tatiana Bautista", "V-21.033.701"),
    "YURAIMA RANGEL": ("Yuraima Rangel", "V-17.767.702"),
    "CUPERTINO BENITEZ": (None, "C.C 1.100.968.792"),  # nuevo
    "ZULIMA RANGEL": ("Zulima Rangel", "V-18.719.429"),
    "CESAR PATIÑO": ("Cesar Patiño", "V-19.385.416"),
    "JOFRE VELANDIA": ("Jofre Velandia", None),
    "CAPITAN AMURANDAI": ("Capitan Amurandai", None),
    "ARBIN CARRILLO": ("Arbin Carrillo", "C.C 1.092.342.376"),
    "AROLDO CARRILLO": (None, None),  # nuevo
    "MAYOR MORALES": ("Mayor Morales", None),
    "MARIA SANCHEZ": ("Maria Sanchez", "V-37.642.571"),
    "HECTOR": ("Hector Cumpleaños de Lilibeth", None),  # conservar nombre existente
    "JEFREY RODRIGUEZ": ("Jefrey Rodriguez", None),
    "WUILBER AUDILIO GONZALEZ PEÑA / ARNULFO": ("Wuilber Audilio Gonzalez Peña / Arnulfo", "V-14.435.106"),
    "ARNULFO ALVAREZ": ("Arnulfo Alvarez", None),
    "SARGENTO VARELA": ("Sargento Varela", None),
    "UNIHOME": ("UniHome", "J-50048892-0"),
    "JEFERSON MIGRACION": ("Yeferson Higuaran", None),  # conservar nombre existente
    "OSMAN SENIAT": ("Osman Seniat", None),
    "SENIAT YAIR": ("Seniat Yair", None),
    "ELDIS CONTRERAS": ("Eldis Contreras (Pocho)", None),
    "ZODI (Picedro)": ("Zodi", None),
    "EDDY DELGADO": ("General Santiago Eddy Delgado", None),
    "PAOLA BONILLA": ("Paola Bonilla", "V-18.354.455"),
    "YORLEDY FARFAN": ("Yorledy Farfan", None),
    "WILLIAM": ("Willian Cristóbal", None),
}

# Nombre final (mapa de arriba) → nombre REAL existente en la BD cuando el
# fuzzy por substring no alcanza (typos distintos: Yofre/Jofre, Emmanuel/Enmanuel…)
ALIAS_EXISTENTES = {
    "Edwar Enmanuel Sanchez Vasquez": "Edwar Emmanuel",
    "Zulima Rangel": "Zuleima",
    "Jofre Velandia": "Yofre Velandia",
    "Capitan Amurandai": "Capitan Almoranday",
    "Arbin Carrillo": "Arbin Castillo",
    "Jefrey Rodriguez": "Yefrey Rodriguez",
    "Arnulfo Alvarez": "Arnulfo",
    "Osman Seniat": "Osman Señal",
    "Seniat Yair": "SENIAT Yain",
    "Wuilber Audilio Gonzalez Peña / Arnulfo": "Wilber Auxilio Gonzalez / Arnulfo",
    "Daniel Gomez Montoya": "Daniel Gomez Montaña",
    "Felix Enrique Kajalay Vegas": "Felix Enrique",
    "Tatiana Bautista": "Tatiana",
}


def normalizar_rif(texto):
    """C.I.V 15.958.210 → V-15.958.210 · C.C 1.092.342.376 → C.C 1.092.342.376 · J-... → igual."""
    if not texto:
        return None
    t = re.sub(r"(?i)c\.?\s?i\.?\s?v\.?", "V-", texto.strip())
    t = re.sub(r"(?i)c\.?\s?c\.?\s?v?", "C.C", t)
    t = re.sub(r"(?i)j\.?(-|\s)?", "J-", t)
    t = re.sub(r"\s+", " ", t).strip(" -")
    return t or None


def clasificar_tipo(descripcion):
    d = (descripcion or "").upper()
    if re.search(r"COLCHON|AIRE SPLIT|AIRE DE VENTANA|NEVERA", d) and "TAPIZ" not in d:
        return "REVENTA"
    return "FABRICADO"


METODOS_VALIDOS = {
    "EFECTIVO_COP", "EFECTIVO_USD", "EFECTIVO_VES", "BANCOLOMBIA", "BANCARIBE",
    "ZELLE", "BINANCE", "NEQUI", "SOFITASA", "BANESCO",
}


def mapear_metodo(metodo_papel, moneda_cod):
    """Enum del ERP ← texto libre del papel. Guarda el texto original en obs."""
    m = (metodo_papel or "").upper()
    if "ZELLE" in m:
        return "ZELLE"
    if "BANCOLOMBIA" in m:
        return "BANCOLOMBIA"
    if "BANCARIBE" in m:
        return "BANCARIBE"
    if "USDT" in m:
        return "BINANCE"  # USDT suele moverse por Binance
    if "NEQUI" in m:
        return "NEQUI"
    efectivo = "EFECTIVO_VES" if moneda_cod == "VES" else "EFECTIVO_USD"
    if "EFECTIVO" in m or "OTRO" in m or "ABONO" in m or "DESCUENTO" in m or not m.strip():
        return efectivo
    return efectivo


def cargar_notas():
    notas = []
    for f in sorted((RAIZ / "notas").glob("N*.json")):
        data = json.loads(f.read_text(encoding="utf-8"))
        m = re.match(r"N(\d+)", f.name)
        notas.append({"id": f"N{int(m.group(1)):02d}", "archivo": f.name, "data": data})
    return notas


def total_efectivo_y_flags(nid, data):
    """Devuelve (total_venta, pagos_filtrados, flags[]) con las reglas especiales."""
    flags = []
    total = Decimal(str(data["total_declarado"]))
    pagos = list(data.get("abonos") or [])

    if nid == "N09":  # Zulima: descuento −40
        total = total - Decimal("40")
        flags.append("Incluye DESCUENTO −$40 del 29/7 (venta total 4.020)")
    if nid == "N16":  # Daniel #2: solo abonos impresos
        impresos = [p for p in pagos if p.get("origen") == "IMPRESO"]
        flags.append(
            "⚠️ 2 abonos manuscritos de $500 (18/8) NO registrados: la aritmética es imposible "
            "(1.478 − 2.000 = −522; papel dice saldo 500). Revisar la foto."
        )
        pagos = impresos
    if nid == "N21":  # Arnulfo: verbatim + flag
        flags.append(
            "⚠️ Cantidad ambigua (papel: 2.243 metros a 1.500.000). Saldo calculado "
            "1.362.500.000 vs papel manuscrito 1.364.500.000. Revisar la foto."
        )
    if nid == "N29":  # SENIAT Yair
        flags.append(
            "⚠️ No cuadra en ningún paso: saldo calculado 869.400 vs papel impreso 2.488.400 "
            "y manuscrito 133.400. Revisar la foto."
        )
    return total, pagos, flags


def construir_unihome(notas):
    """Reemplaza N23..N26 por 3 ventas consolidadas con pagos únicos."""
    salto = {"N23"}
    ventas = {
        "N26": {  # consolidación Feb (saldo factura nueva 28.098 + cuenta anterior 4.252)
            "total": Decimal("32350"),
            "pagos": [
                {"fecha": "2026-03-30", "metodo": "EFECTIVO (RONALD QUINTERO)", "monto": 24000, "origen": "IMPRESO"},
                {"fecha": "2026-03-30", "metodo": "DESCUENTO DE CALETAS", "monto": 180, "origen": "IMPRESO"},
            ],
            "flags": ["Nota de consolidación de cuentas anteriores (saldo Feb 8.170 ✓ papel)"],
        },
        "N25": {  # venta Mar 30: 25.340 − 180 caletas = 25.160
            "total": Decimal("25160"),
            "pagos": [
                {"fecha": "2026-06-10", "metodo": "USDT", "monto": 10000, "origen": "MANUSCRITO"},
            ],
            "flags": ["Incluye DESCUENTO DE CALETAS −180 (total papel 25.340)"],
        },
        "N24": {  # venta Jun 30: 25.845
            "total": Decimal("25845"),
            "pagos": [
                {"fecha": "2026-06-24", "metodo": "EFECTIVO", "monto": 5100, "origen": "IMPRESO"},
                {"fecha": "2026-06-24", "metodo": "DESCUENTO DE CALETAS", "monto": 180, "origen": "IMPRESO"},
                {"fecha": "2026-08-05", "metodo": "USDT", "monto": 10000, "origen": "MANUSCRITO"},
            ],
            "flags": [
                "⚠️ Saldo calculado 10.565; el papel consolidado (02/08) da saldo global 33.995 "
                "vs 33.895 reconstruido (Δ100). Revisar con la cliente.",
            ],
        },
    }
    return salto, ventas


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--ejecutar", action="store_true", help="Aplica los cambios (default: dry-run)")
    parser.add_argument("--db-url", help="URL de la BD (default: DATABASE_URL del entorno)")
    parser.add_argument("--solo", help="Lista de ids separados por coma (ej. N01,N16)")
    args = parser.parse_args()

    if args.db_url:
        os.environ["DATABASE_URL"] = args.db_url

    # Registro completo de mappers (mismo listado que alembic/env.py)
    import app.modules.catalogos.model  # noqa: F401
    import app.modules.clients.model  # noqa: F401
    import app.modules.productos.model  # noqa: F401
    import app.modules.quotes.model  # noqa: F401
    import app.modules.orders.model  # noqa: F401
    import app.modules.production.model  # noqa: F401
    import app.modules.inventory.model  # noqa: F401
    import app.modules.users.model  # noqa: F401
    import app.modules.purchases.model  # noqa: F401
    import app.modules.sales.model  # noqa: F401
    import app.modules.facturacion.model  # noqa: F401
    import app.modules.gastos.model  # noqa: F401
    import app.modules.proveedores.model  # noqa: F401
    import app.modules.empleados.model  # noqa: F401
    import app.modules.envios.model  # noqa: F401
    import app.modules.tasas_cambio.model  # noqa: F401
    import app.modules.reports.model  # noqa: F401
    import app.modules.auditoria.model  # noqa: F401
    import app.modules.costos_produccion.model  # noqa: F401
    import app.modules.nomina.model  # noqa: F401
    import app.modules.adjuntos.model  # noqa: F401
    import app.modules.cuentas_por_pagar.model  # noqa: F401

    from app.db.session import session_local
    from app.modules.clients.model import Client
    from app.modules.quotes.model import Cotizacion, DetalleCotizacion
    from app.modules.orders.model import Pedido, DetallePedido
    from app.modules.sales.model import Venta, DetalleVenta, Pago

    salto_unihome, unihome_ventas = construir_unihome(cargar_notas())
    notas = cargar_notas()
    if args.solo:
        solo = {s.strip().upper() for s in args.solo.split(",")}
        notas = [n for n in notas if n["id"] in solo]

    db = session_local()
    informe = []
    try:
        monedas = {m.codigo: m.id for m in db.execute(text_monedas(db)).fetchall()}
        for nota in notas:
            nid = nota["id"]
            data = nota["data"]
            if nid in salto_unihome:
                informe.append((nid, data["cliente"]["nombre"], "OMITIDA", "Nota-resumen: cubierta por las ventas consolidadas de UniHome", []))
                continue

            cli_json = data["cliente"]
            nombre_nota = (cli_json.get("nombre") or "").upper().strip()
            nombre_mapa = next((k for k in CLIENTES_MAPA if k.upper() == nombre_nota), None)
            nombre_final, rif = CLIENTES_MAPA.get(nombre_mapa, (None, None))
            rif = normalizar_rif(rif or cli_json.get("rif_cedula"))

            cliente = None
            if nombre_final:
                cliente = db.query(Client).filter(Client.nombre == nombre_final).first()
            if not cliente and nombre_final and nombre_final in ALIAS_EXISTENTES:
                cliente = db.query(Client).filter(Client.nombre == ALIAS_EXISTENTES[nombre_final]).first()
            if not cliente:
                # búsqueda tolerante por nombre normalizado. Reglas:
                # objetivo ⊆ candidato (siempre) · candidato ⊆ objetivo solo
                # si el candidato es ≥50% del objetivo (evita que "Arnulfo"
                # capture "Wuilber ... / Arnulfo").
                objetivo = normalizar_texto(cli_json.get("nombre"))
                for c in db.query(Client).all():
                    cand = normalizar_texto(c.nombre)
                    ok = (objetivo and cand) and (
                        objetivo in cand
                        or (cand in objetivo and len(cand) >= len(objetivo) * 0.5)
                    )
                    if ok:
                        cliente = c
                        break
            if not cliente:
                cliente = Client(
                    nombre=nombre_final or cli_json.get("nombre"),
                    cedula=rif,
                    telefono=cli_json.get("telefono") or "N/D",
                    direccion=cli_json.get("direccion") or None,
                    fecha_registro=data.get("fecha"),
                )
                db.add(cliente)
                db.flush()
                accion_cli = "cliente creado"
            else:
                if nombre_final:
                    cliente.nombre = nombre_final
                if rif:
                    cliente.cedula = rif
                if cli_json.get("telefono"):
                    cliente.telefono = cli_json["telefono"]
                if cli_json.get("direccion"):
                    cliente.direccion = cli_json["direccion"]
                accion_cli = "cliente actualizado"

            moneda_cod = MONEDA_OVERRIDE.get(nid, data.get("moneda", "USD"))
            moneda_id = monedas.get(moneda_cod, 2)
            fecha_nota = data.get("fecha") or str(date.today())

            total_venta, pagos, flags = total_efectivo_y_flags(nid, data)
            if nid in unihome_ventas:
                total_venta = unihome_ventas[nid]["total"]
                pagos = unihome_ventas[nid]["pagos"]
                flags = flags + unihome_ventas[nid]["flags"]
                if nid == "N25":
                    flags.append("Venta total 25.160 (25.340 del papel − 180 descuento caletas)")

            # ── Idempotencia: ¿ya existe la venta de esta nota? ──
            tag = TAG.format(int(nid[1:]))
            if db.query(Venta).filter(Venta.observaciones.contains(tag)).first():
                informe.append((nid, cliente.nombre, "OMITIDA", "Ya migrada (idempotente)", flags))
                continue

            saldo_papel = data.get("saldo_final_manuscrito", data.get("saldo_impreso"))

            # ── 1. Cotización ──
            cot = Cotizacion(
                cliente_id=cliente.id,
                fecha=fecha_nota,
                estado="APROBADA",
                total_estimado=total_venta,
                moneda_id=moneda_id,
                tasa_cambio=Decimal("1"),
                observaciones=(
                    f"{tag} · Nota de entrega migrada de foto ({nota['archivo']}). "
                    f"Saldo papel: {saldo_papel}. "
                    + (" Inconsistencias: " + " | ".join(data.get("inconsistencias", [])[:3]) if data.get("inconsistencias") else "")
                ),
            )
            db.add(cot)
            db.flush()
            for item in data.get("items") or []:
                desc = item.get("descripcion") or "ITEM SIN DESCRIPCIÓN"
                obs = desc + (f" | {item['observaciones']}" if item.get("observaciones") else "")
                db.add(DetalleCotizacion(
                    cotizacion_id=cot.id,
                    producto_id=None,
                    tipo_item=clasificar_tipo(desc),
                    cantidad=Decimal(str(item.get("cantidad") or 0)) or Decimal("1"),
                    precio=Decimal(str(item.get("precio_unitario") or 0)),
                    observaciones=obs,
                ))

            # ── 2. Pedido (histórico, entregado) ──
            pedido = Pedido(
                cotizacion_id=cot.id,
                cliente_id=cliente.id,
                fecha=fecha_nota,
                estado="ENTREGADO",
                observaciones=f"{tag} · Nota de entrega migrada de foto",
            )
            db.add(pedido)
            db.flush()
            for item in data.get("items") or []:
                desc = item.get("descripcion") or "ITEM SIN DESCRIPCIÓN"
                db.add(DetallePedido(
                    pedido_id=pedido.id,
                    producto_id=None,
                    tipo_item=clasificar_tipo(desc),
                    cantidad=Decimal(str(item.get("cantidad") or 0)) or Decimal("1"),
                    precio=Decimal(str(item.get("precio_unitario") or 0)),
                    descripcion_especifica=desc + (f" | {item['observaciones']}" if item.get("observaciones") else ""),
                ))

            # ── 3. Venta + detalle + pagos ──
            abonos_suma = sum(Decimal(str(p.get("monto") or 0)) for p in pagos)
            if abonos_suma >= total_venta and abonos_suma > 0:
                estado_venta = "PAGADA"
            elif abonos_suma > 0:
                estado_venta = "ABONADA"
            else:
                estado_venta = "PENDIENTE"
            venta = Venta(
                pedido_id=pedido.id,
                cliente_id=cliente.id,
                moneda_id=moneda_id,
                fecha=fecha_nota,
                total=total_venta,
                estado=estado_venta,
                tasa_cambio=Decimal("1"),
                total_en_moneda_base=None,  # sin tasas configuradas aún
                observaciones=(
                    f"{tag} · Migrada de foto. Total papel: {data['total_declarado']} {moneda_cod}. "
                    + (" ".join(flags))
                ),
            )
            db.add(venta)
            db.flush()
            for item in data.get("items") or []:
                desc = item.get("descripcion") or "ITEM SIN DESCRIPCIÓN"
                db.add(DetalleVenta(
                    venta_id=venta.id,
                    producto_id=None,
                    tipo_item=clasificar_tipo(desc),
                    cantidad=Decimal(str(item.get("cantidad") or 0)) or Decimal("1"),
                    precio=Decimal(str(item.get("precio_unitario") or 0)),
                ))
            for p in pagos:
                metodo = mapear_metodo(p.get("metodo"), moneda_cod)
                db.add(Pago(
                    venta_id=venta.id,
                    moneda_id=moneda_id,
                    fecha=p.get("fecha") or f"{fecha_nota} 00:00:00",
                    monto=Decimal(str(p.get("monto") or 0)),
                    tasa_cambio=Decimal("1"),
                    monto_en_moneda_base=Decimal(str(p.get("monto") or 0)),
                    metodo_pago=metodo,
                    observaciones=(
                        f"{tag} · origen {p.get('origen', 'N/D')}"
                        + (f" · papel: {p['metodo']}" if (p.get("metodo") or "").upper().strip() != metodo else "")
                    ),
                ))

            saldo_calc = total_venta - abonos_suma
            informe.append((nid, cliente.nombre, estado_venta,
                            f"{moneda_cod} total {total_venta} · abonos {abonos_suma} · saldo {saldo_calc} ({accion_cli})", flags))
        if args.ejecutar:
            db.commit()
            modo = "EJECUTADO ✓"
        else:
            db.rollback()
            modo = "DRY-RUN (rollback) — usa --ejecutar para aplicar"
    finally:
        db.close()

    print(f"\n═══ INFORME DE MIGRACIÓN · {modo} ═══")
    for nid, cli, estado, detalle, flags in informe:
        print(f"{nid} | {cli[:32]:32} | {estado:9} | {detalle}")
        for f in flags:
            print(f"     └─ {f}")
    pagadas = sum(1 for i in informe if i[2] == "PAGADA")
    print(f"\nNotas: {len(informe)} · pagadas: {pagadas}")


def text_monedas(db):
    from sqlalchemy import text
    return text("SELECT codigo, id FROM moneda")


def normalizar_texto(s):
    s = unicodedata.normalize("NFKD", s or "")
    s = s.encode("ascii", "ignore").decode().upper()
    return re.sub(r"[^A-Z0-9]+", " ", s).strip()


if __name__ == "__main__":
    main()
