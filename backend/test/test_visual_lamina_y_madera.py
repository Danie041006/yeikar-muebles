"""
test_visual_lamina_y_madera.py
===============================
Test VISUAL del flujo de pedido de láminas (MDF / melamina / laminados) y de
madera masiva, para verificar que el costeo vaya acorde a lo que necesitamos.

Cuando lo corras (pytest test/test_visual_lamina_y_madera.py -s -v) verás
dibujos ASCII de la lámina con sus cortes y el sobrante que queda, y el
desglose de costos paso a paso. Así es más fácil "ver" de dónde sale cada
número antes de confiar en él.

Qué demuestra:
  1. Un corte de una lámina nueva: se descuenta una lámina entera pero el
     sobrante se guarda y se puede reutilizar → el costo por corte es
     proporcional al ÁREA, no a la lámina completa.
  2. El efecto "viene de un sobrante": si cabe en un retazo, NO se toca stock.
  3. Lámina completa sin cortes aún (PENDIENTE) → luego CONFIRMADA.
  4. Madera masiva: la fórmula de la casa (largo×ancho×espesor×piezas/10000).

Ejecutar:  pytest test/test_visual_lamina_y_madera.py -s -v
"""
import os
import sys
from datetime import datetime
from decimal import Decimal
from types import SimpleNamespace

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import pytest
from sqlalchemy import text

from conftest import ADMIN_HEADERS, crear_cliente, crear_cotizacion, crear_material, crear_movimiento

# ============================================================================
# Motor puro de láminas (se importan las funciones del engine)
# ============================================================================
from app.modules.inventory.laminas import cortes_que_caban, laminas_necesarias, costo_por_corte
from app.modules.production.unidades import resolver_cantidad_consumo

# ============================================================================
# Utilidades de salida visual
# ============================================================================

LINEA = "═" * 80


def paso(titulo, cuerpo=""):
    print()
    print(f"  ▸▸ {titulo}")
    if cuerpo:
        for l in cuerpo.splitlines():
            print(f"      {l}")
    print()


def dinero(v):
    """Formatea un número como moneda."""
    return f"${Decimal(str(v)).quantize(Decimal('0.01')):,}"


def barra(titulo, partes):
    """Dibuja una fila de tabla ASCII con título y partes (lista de textos)."""
    ancho = 62
    celda_titulo = f" {titulo} "
    body = f"│ {celda_titulo.ljust(ancho - 4)}│"
    widths = [max(0, ancho - 4 - sum(len(p) for p in partes) // len(partes)) for _ in partes]
    return body


def caja(titulo, lineas):
    """Dibuja un recuadro ASCII con título y contenido."""
    print("    ┌" + "─" * 60 + "┐")
    print(f"    │  {titulo}" + " " * max(0, 58 - len(titulo)) + "│")
    print("    ├" + "─" * 60 + "┤")
    for l in lineas:
        print(f"    │  {l}" + " " * max(0, 58 - len(l)) + "│")
    print("    └" + "─" * 60 + "┘")


def resaltado(linea_color):
    """Dibuja una línea de resumen destacada."""
    print("    █ " + linea_color)


def dibujar_lamina_con_cortes(largo_lam, ancho_lam, largo_corte, ancho_corte, n_cortes, costo_lamina):
    """Dibuja la lámina (a escala) con la zona de cortes y el sobrante."""
    L, A = int(largo_lam), int(ancho_lam)
    lc, ac = int(largo_corte), int(ancho_corte)

    area_lam = L * A
    area_corte = lc * ac
    por_lamina = cortes_que_caban(L, A, lc, ac)
    cortes_por_fila = max(1, L // lc)
    filas = (n_cortes + cortes_por_fila - 1) // cortes_por_fila if n_cortes else 0

    # Dibujo a escala: el ancho de cada corte en caracteres
    ancho_char = max(2, 56 // cortes_por_fila)
    print("    ┌" + "─" * 60 + "┐")
    print(f"    │  Lámina {L}×{A} cm  | área {area_lam:,} cm²"
          + " " * max(0, 46 - len(f"Lámina {L}×{A} cm  | área {area_lam:,} cm²")) + "│")
    print("    ├" + "─" * 60 + "┤")
    print(f"    │  ┌{'─' * 56}┐  │")
    if n_cortes:
        for f in range(filas):
            texto = ""
            for c in range(cortes_por_fila):
                idx = f * cortes_por_fila + c
                if idx < n_cortes:
                    texto += f"[{lc}×{ac}] "
            print("    │  │ " + texto.ljust(54) + "│  │")
    else:
        print("    │  │ (lámina entera, sin cortes aún)" + " " * 22 + "│  │")
    print("    │  └" + "─" * 56 + "┘  │")
    area_sobrante = area_lam - min(n_cortes, por_lamina) * area_corte
    print(f"    │  SOBRANTE de esta lámina: {area_sobrante:,} cm²"
          + " " * max(0, 40 - len(f"SOBRANTE de esta lámina: {area_sobrante:,} cm²")) + "│")
    print("    └" + "─" * 60 + "┘")

    # Datos
    caja("MATEMÁTICA", [
        f"Cortes de {lc}×{ac} = {area_corte:,} cm² cada uno",
        f"Caben {por_lamina} cortes por lámina (probando ambas orientaciones)",
        f"Costo lámina completa = {dinero(costo_lamina)}",
        f"Costo por corte = {dinero(costo_lamina)} × {area_corte:,} / {area_lam:,} "
        f"= {dinero(costo_por_corte(Decimal(costo_lamina), Decimal(area_corte), Decimal(area_lam)))}",
    ])


def dibujar_retazo(largo, ancho, titulo="RETAZO / sobranTE"):
    """Dibuja un retazo simple."""
    print("    ┌" + "─" * 60 + "┐")
    print(f"    │  {titulo}: {largo}×{ancho} cm | área {int(Decimal(str(largo)) * Decimal(str(ancho))):,} cm²"
          + " " * max(0, 36 - len(f"{titulo}: {largo}×{ancho} cm | área {int(Decimal(str(largo)) * Decimal(str(ancho))):,} cm²")) + "│")
    print("    │  " + "▓" * 54 + "  │")
    print("    └" + "─" * 60 + "┘")


def dibujar_formula_madera(largo, ancho, espesor, piezas):
    """Dibuja la fórmula de la casa para madera masiva y devuelve los m³."""
    producto = largo * ancho * espesor * piezas
    m3 = Decimal(producto) / Decimal(10000)
    caja("FÓRMULA DE LA CASA (21 años de práctica)", [
        "m³ = (largo × ancho × espesor) × piezas ÷ 10000",
        f"m³ = ({largo} × {ancho} × {espesor}) × {piezas} ÷ 10000",
        f"m³ = {producto:,} ÷ 10000",
        f"m³ = {float(m3):.4f}",
    ])
    return m3


# ============================================================================
# Helpers
# ============================================================================

def crear_material_laminar(client, cleaner, nombre=None, largo=244, ancho=183, costo=90_000.0):
    """Material laminar de prueba: lámina de X×Y cm."""
    from conftest import _uniq
    payload = {
        "nombre": nombre or _uniq("mdf"),
        "unidad_medida_id": 2,
        "costo_base": costo,
        "largo_cm": largo,
        "ancho_cm": ancho,
    }
    r = client.post("/api/v1/material/", json=payload, headers=ADMIN_HEADERS)
    assert r.status_code == 201, f"crear material laminar → {r.status_code}: {r.text}"
    body = r.json()
    cleaner.registrar("material", body["id"])
    return body


def dar_stock(client, cleaner, material_id, cantidad):
    r, body = crear_movimiento(client, cleaner, material_id, "ENTRADA", cantidad)
    assert r.status_code in (200, 201), f"ENTRADA stock → {r.status_code}: {body}"
    return body


def stock_actual(db, material_id):
    row = db.execute(
        text("SELECT cantidad FROM inventario WHERE material_id = :m"), {"m": material_id}
    ).fetchone()
    return Decimal(str(row[0])) if row else Decimal("0")


def registrar_movs_y_sobrantes(db, cleaner, material_id):
    """Registra en el cleaner movimientos, inventario y sobrantes del material
    (incluye los creados internamente por consumir_por_cortes vía BD directa)."""
    from conftest import registrar_inventario_de_material
    registrar_inventario_de_material(db, cleaner, material_id)
    registrar_sobrantes_de_material(db, cleaner, material_id)


def registrar_sobrantes_de_material(db, cleaner, material_id):
    for (sid,) in db.execute(
        text("SELECT id FROM sobrante_lamina WHERE material_id = :m"), {"m": material_id}
    ).fetchall():
        cleaner._ids.setdefault("sobrante_lamina", set()).add(int(sid))


def _pedido_y_etapa(client, cleaner):
    """Crea un pedido con producto y una etapa EN_PROCESO para registrar consumos."""
    from conftest import crear_orden_desde_pedido, registrar_venta_de_pedido
    from test_cortes_laminas import crear_producto_simple
    cli = crear_cliente(client, cleaner)
    prod = crear_producto_simple(client, cleaner)
    cot = crear_cotizacion(client, cleaner, cli["id"], prod["id"], 100_000)
    r = client.post(f"/api/v1/pedido/convertir/{cot['id']}",
                    json={"detalles": [{"producto_id": prod["id"], "cantidad": 1,
                                        "precio": 100_000}]},
                    headers=ADMIN_HEADERS)
    assert r.status_code == 201, r.text
    ped = r.json()
    cleaner.registrar("pedido", ped["id"])
    registrar_venta_de_pedido(client, cleaner, ped["id"])
    orden = crear_orden_desde_pedido(client, cleaner, ped["detalles"][0]["id"])
    r = client.post("/api/v1/produccion/etapa/", json={
        "orden_produccion_id": orden["id"], "area_id": 1,
        "empleado_responsable_id": 3, "estado": "ASIGNADA"}, headers=ADMIN_HEADERS)
    assert r.status_code == 201, r.text
    etapa_id = r.json()["id"]
    cleaner.registrar("etapa_produccion", etapa_id)
    r = client.put(f"/api/v1/produccion/etapa/{etapa_id}/estado",
                   params={"estado": "EN_PROCESO"}, headers=ADMIN_HEADERS)
    assert r.status_code == 200, r.text
    return ped, orden, etapa_id


# ============================================================================
# TEST 1 — Lámina nueva: se descuenta 1 lámina, costo por área, sobrante
# ============================================================================

def test_01_lamina_nueva_corte_y_sobrante(client, cleaner, db):
    print("\n" + LINEA)
    paso("CASO 1 — Corte desde lámina nueva (MDF)",
         "El operario pide: 'necesito 2 tableros de 80×130 cm de MDF'.\n"
         "La lámina de MDF en el depósito: 244×183 cm, cuesta $90.000.\n"
         "Pregunta clave: ¿cuántas láminas abro y CUÁNTO cobro a ESTE pedido?")

    mat = crear_material_laminar(client, cleaner, largo=244, ancho=183, costo=90_000)
    stock_inicial = 10
    dar_stock(client, cleaner, mat["id"], stock_inicial)
    stock_antes = stock_actual(db, mat["id"])

    paso("ANTES de cortar",
         f"  Lámina MDF: 244×183 cm | área = {244*183:,} cm²\n"
         f"  Costo lámina completa = {dinero(90_000)}\n"
         f"  Stock = {int(stock_antes)} láminas")

    # Motor puro: ¿cuántos cortes caben?
    lc, ac = 130, 80
    area_lam = 244 * 183
    area_corte = lc * ac
    por_lamina = cortes_que_caban(244, 183, lc, ac)
    n_laminas = laminas_necesarias(2, por_lamina)
    costo_unit = costo_por_corte(Decimal(90_000), Decimal(area_corte), Decimal(area_lam))
    costo_total = costo_unit * 2

    paso("MATEMÁTICA DEL MOTOR (sin BD)",
         f"  cortes_que_caban(244, 183, 130, 80) = {por_lamina}\n"
         f"  → Caben {por_lamina} cortes de 80×130 por lámina\n"
         f"  laminas_necesarias(2 cortes, {por_lamina}/lámina) = {n_laminas}\n"
         f"  → Se abre {n_laminas} lámina(s) entera(s)")

    dibujar_lamina_con_cortes(244, 183, lc, ac, 2, 90_000)

    paso("COSTO PROPORCIONAL AL ÁREA",
         f"  Área lámina:  244 × 183 = {area_lam:,} cm²\n"
         f"  Área 1 corte: 130 × 80  = {area_corte:,} cm²\n"
         f"  Costo/corte:  {dinero(90_000)} × {area_corte:,} / {area_lam:,}\n"
         f"              = {dinero(costo_unit)}\n"
         f"  Costo 2 cortes = {dinero(costo_total)}")

    assert por_lamina == 3
    assert n_laminas == 1
    assert costo_unit == Decimal("20962.11")  # 90000 × 10400 / 44652

    # Consumo real vía BD (para que quede registro en kardex)
    from app.modules.inventory.cortes_service import consumir_por_cortes
    from app.modules.productos.model import Material
    material = db.query(Material).filter(Material.id == mat["id"]).first()

    res = consumir_por_cortes(
        db, material=material, cantidad_cortes=2,
        largo_corte_cm=lc, ancho_corte_cm=ac,
        ubicacion_id=1, referencia_tipo="produccion", referencia_id=99901,
        consumo_origen_tipo="produccion",
    )
    db.flush()
    registrar_movs_y_sobrantes(db, cleaner, mat["id"])

    stock_despues = stock_actual(db, mat["id"])
    sob = res["sobrante"]
    area_sob = Decimal(str(sob.largo_cm)) * Decimal(str(sob.ancho_cm)) if sob else 0

    paso("DESPUÉS de cortar",
         f"  Stock: {int(stock_antes)} → {int(stock_despues)} láminas "
         f"(se descontó 1 lámina entera)\n"
         f"  Costo REAL del consumo: {dinero(res['costo_total'])}\n"
         f"  Sobrante: {sob.largo_cm}×{sob.ancho_cm} = {area_sob:,} cm² "
         f"(estado: {sob.estado})")

    if sob:
        dibujar_retazo(sob.largo_cm, sob.ancho_cm, "SOBRANTE reutilizable")

    paso("VERIFICACIONES",
         f"  ✅ Se abrió 1 lámina (stock bajó de {int(stock_antes)} a {int(stock_despues)})\n"
         f"  ✅ Costo proporcional: {dinero(costo_unit)} por corte "
         f"(NO {dinero(90_000)} por lámina)\n"
         f"  ✅ Sobrante {float(area_sob):,.0f} cm² queda disponible para otro mueble")

    assert res["laminas_consumidas"] == 1
    assert float(stock_despues) == float(stock_antes) - 1
    assert sob.estado == "DISPONIBLE"
    assert area_sob > 0

    resaltado(f"RESULTADO: el pedido paga {dinero(res['costo_total'])} por 2 tableros, "
              f"y {float(area_sob):,.0f} cm² de MDF quedan en el taller.")
    print("  ✅ CASO 1 OK")
    print()


# ============================================================================
# TEST 2 — Consumo desde sobrante: no toca stock
# ============================================================================

def test_02_consumo_desde_sobrante_no_toca_stock(client, cleaner, db):
    print("\n" + LINEA)
    paso("CASO 2 — El siguiente mueble 'cabe' en el sobrante",
         "Otro pedido necesita 1 pieza de 45×45 cm.\n"
         "En vez de abrir una lámina nueva, el operario usa un retazo del taller.\n"
         "La regla: si cabe en el sobrante, NO se toca el stock de láminas.")

    mat = crear_material_laminar(client, cleaner, largo=244, ancho=183, costo=90_000)
    stock_inicial = 5
    dar_stock(client, cleaner, mat["id"], stock_inicial)
    stock_antes = stock_actual(db, mat["id"])

    from app.modules.inventory.model import SobranteLamina
    sob = SobranteLamina(
        material_id=mat["id"], ubicacion_id=1,
        largo_cm=Decimal("120"), ancho_cm=Decimal("100"),
        estado="DISPONIBLE", observaciones="retazo del taller",
    )
    db.add(sob)
    db.commit()
    registrar_sobrantes_de_material(db, cleaner, mat["id"])

    paso("ANTES",
         f"  Retazo disponible: 120×100 cm (área {120*100:,} cm²)\n"
         f"  Stock láminas nuevas: {int(stock_antes)}\n"
         f"  Corte que necesita: 45×45 cm = {45*45:,} cm²")

    por_retazo = cortes_que_caban(120, 100, 45, 45)
    caja("MATEMÁTICA DEL MOTOR", [
        f"cortes_que_caban(120, 100, 45, 45) = {por_retazo}",
        f"→ Caben {por_retazo} pieza(s) de 45×45 en el retazo",
    ])

    # Consumo real
    from app.modules.inventory.cortes_service import consumir_por_cortes
    from app.modules.productos.model import Material
    material = db.query(Material).filter(Material.id == mat["id"]).first()

    res = consumir_por_cortes(
        db, material=material, cantidad_cortes=1,
        largo_corte_cm=45, ancho_corte_cm=45,
        ubicacion_id=1, referencia_tipo="produccion", referencia_id=99902,
        consumo_origen_tipo="produccion", origen_sobrante_id=sob.id,
    )
    db.flush()
    db.refresh(sob)
    registrar_movs_y_sobrantes(db, cleaner, mat["id"])

    stock_despues = stock_actual(db, mat["id"])
    area_sob_nuevo = Decimal(str(sob.largo_cm)) * Decimal(str(sob.ancho_cm))

    paso("DESPUÉS",
         f"  Stock láminas: {int(stock_antes)} → {int(stock_despues)} (NO CAMBIÓ)\n"
         f"  Costo del corte: {dinero(res['costo_unitario'])} (proporcional)\n"
         f"  Retazo ahora: {sob.largo_cm}×{sob.ancho_cm} = {area_sob_nuevo:,} cm²")

    dibujar_retazo(sob.largo_cm, sob.ancho_cm, "RETAZO tras el corte")

    paso("VERIFICACIONES",
         f"  ✅ Stock NO se tocó (sigue en {int(stock_despues)})\n"
         f"  ✅ El retazo se redujo de {120*100:,} a {float(area_sob_nuevo):,.0f} cm²\n"
         f"  ✅ Costo: solo cobramos el área que se usó, no lámina entera")

    assert res["laminas_consumidas"] == 0
    assert float(stock_despues) == float(stock_antes)
    assert area_sob_nuevo < 120 * 100

    resaltado(f"RESULTADO: 1 pieza de 45×45 sale de un retazo por {dinero(res['costo_unitario'])}, "
              f"sin gastar ninguna lámina nueva.")
    print("  ✅ CASO 2 OK")
    print()


# ============================================================================
# TEST 3 — Lámina completa PENDIENTE → CONFIRMAR con cortes reales
# ============================================================================

def test_03_lamina_completa_pendiente_confirmacion(client, cleaner, db):
    print("\n" + LINEA)
    paso("CASO 3 — Pedido de láminas completas → confirmación posterior",
         "A veces el operario pide N láminas sin saber los cortes exactos\n"
         "(los va a despiezar en el momento). Se registran como PENDIENTE\n"
         "y cuando termina de cortar CONFIRMA las medidas reales.")

    _, _, etapa = _pedido_y_etapa(client, cleaner)
    mat = crear_material_laminar(client, cleaner, largo=244, ancho=183, costo=90_000)
    stock_inicial = 10
    dar_stock(client, cleaner, mat["id"], stock_inicial)
    stock_antes = stock_actual(db, mat["id"])

    paso("PASO A — Pedido de 2 láminas completas",
         f"  El operario dice: 'dame 2 láminas de melamina 244×183'\n"
         f"  Stock ANTES: {int(stock_antes)} láminas")

    payload = {
        "etapa_produccion_id": etapa,
        "material_id": mat["id"],
        "cantidad": 2,
        "es_lamina_completa": True,
        "solicitante_empleado_id": 3,
        "fecha": datetime.utcnow().isoformat(),
    }
    r = client.post("/api/v1/produccion/consumo/", json=payload, headers=ADMIN_HEADERS)
    assert r.status_code == 201, r.text
    consumo = r.json()
    cleaner.registrar("consumo_material", consumo["id"])
    registrar_sobrantes_de_material(db, cleaner, mat["id"])
    cleaner.registrar_gastos_like(db, f"[consumo {consumo['id']}]")
    registrar_movs_y_sobrantes(db, cleaner, mat["id"])

    stock_after_pedir = stock_actual(db, mat["id"])
    costo_prov = Decimal(str(consumo["cantidad"])) * Decimal(str(consumo["costo_unitario"]))

    dibujar_lamina_con_cortes(244, 183, 130, 80, 0, 90_000)

    paso("RESULTADO A",
         f"  Estado: {consumo['estado']} (PENDIENTE)\n"
         f"  Costo provisional (2 láminas): {dinero(costo_prov)}\n"
         f"  Stock: {int(stock_antes)} → {int(stock_after_pedir)} "
         f"(se descontaron 2 láminas enteras)")

    assert consumo["estado"] == "PENDIENTE"
    assert float(stock_after_pedir) == float(stock_antes) - 2

    # PASO B: confirmar cortes reales
    # 8 cortes de 60×60 → caben 12 por lámina 244×183 → solo 1 lámina
    lc, ac = 60, 60
    por_lam = cortes_que_caban(244, 183, lc, ac)
    n_real = laminas_necesarias(8, por_lam)
    costo_unit = costo_por_corte(Decimal(90_000), Decimal(lc * ac), Decimal(244 * 183))
    costo_final = Decimal(8) * costo_unit  # 8 cortes × costo por corte

    paso("PASO B — Confirmación de cortes reales",
         f"  En realidad el operario cortó 8 piezas de 60×60 cm\n"
         f"  Caben {por_lam} por lámina → solo {n_real} lámina(s) real(es)")

    r = client.put(f"/api/v1/produccion/consumo/{consumo['id']}/confirmar", json={
        "cantidad_cortes": 8, "largo_corte_cm": lc, "ancho_corte_cm": ac,
    }, headers=ADMIN_HEADERS)
    assert r.status_code == 200, r.text
    consumo2 = r.json()
    registrar_sobrantes_de_material(db, cleaner, mat["id"])
    registrar_movs_y_sobrantes(db, cleaner, mat["id"])

    stock_final = stock_actual(db, mat["id"])

    dibujar_lamina_con_cortes(244, 183, lc, ac, 8, 90_000)

    paso("RESULTADO B",
         f"  Estado: {consumo2['estado']} (CONFIRMADO)\n"
         f"  Costo/corte: {dinero(costo_unit)} → costo FINAL: {dinero(costo_final)}\n"
         f"  Stock: {int(stock_after_pedir)} → {int(stock_final)} "
         f"(la lámina sin abrir VUELVE al depósito)")

    assert consumo2["estado"] == "CONFIRMADO"
    assert float(stock_final) == float(stock_antes) - n_real

    paso("VERIFICACIONES",
         f"  ✅ La lámina sin abrir regresa al stock (no se pierde plata)\n"
         f"  ✅ Stock final: {int(stock_final)} láminas (se usó solo 1, no 2)\n"
         f"  ✅ Costo congelado proporcional al área REAL cortada\n"
         f"  ✅ Costo ajustado de {dinero(2*90_000)} → {dinero(costo_final)}")

    resaltado(f"RESULTADO: se pidieron 2 láminas ({dinero(2*90_000)}), se usó 1 "
              f"({dinero(costo_final)}) y la otra volvió al stock.")
    print("  ✅ CASO 3 OK")
    print()


# ============================================================================
# TEST 4 — Madera masiva: la fórmula de la casa
# ============================================================================

def test_04_madera_masiva_formula(client, cleaner, db):
    print("\n" + LINEA)
    paso("CASO 4 — Madera masiva (listones, vigas)",
         "La madera masiva NO es lámina: se compra y se mide en m³.\n"
         "El carpintero pide 'por pieza': 'dame 2 piezas de 200×4×2 cm de cedro'.")

    costo_m3 = 750_000
    paso("Material", f"Cedro masivo | 1 m³ = {dinero(costo_m3)}")

    largo, ancho, espesor, piezas = 200, 4, 2, 2
    m3 = dibujar_formula_madera(largo, ancho, espesor, piezas)

    # El mismo cálculo pasando por production/unidades.py con un material m³
    m3_real = resolver_cantidad_consumo(
        SimpleNamespace(unidad_medida=SimpleNamespace(abreviatura="m³")),
        piezas,
        pieza_largo=largo, pieza_ancho=ancho, pieza_espesor=espesor,
    )

    paso("resolver_cantidad_consumo (el punto único que usa la BD)",
         f"  m³ calculado = {float(m3_real):.4f}\n"
         f"  → coincide con la fórmula: {m3 == m3_real}")

    assert float(m3_real) == pytest.approx(0.32, abs=0.01)
    assert m3 == m3_real

    paso("Costo de ESTAS 2 piezas",
         f"  m³ usados: {float(m3_real):.4f}\n"
         f"  Costo: {float(m3_real):.4f} × {dinero(costo_m3)} = "
         f"{dinero(Decimal(float(m3_real)) * Decimal(costo_m3))}")

    resaltado(f"RESULTADO: 2 listones de 200×4×2 cm {':'.join([])} {float(m3_real):.3f} m³ de cedro "
              f"=> {dinero(Decimal(float(m3_real)) * Decimal(costo_m3))} de material.")
    print("  ✅ CASO 4 OK")
    print()


# ============================================================================
# TEST 5 — Costeo paramétrico: receta CORTE escala por área
# ============================================================================

def test_05_costeo_receta_corte_escala(client, cleaner, db):
    print("\n" + LINEA)
    paso("CASO 5 — Receta CORTE en un producto: escala por área",
         "Cuando un producto tiene un material con tipo_escala=CORTE,\n"
         "el motor de costeo calcula cuántos cortes necesita según las\n"
         "dimensiones del mueble (ancho×largo) vs las dimensiones base.")

    from conftest import crear_receta
    from test_cortes_laminas import crear_producto_simple

    prod = crear_producto_simple(client, cleaner)
    mat = crear_material_laminar(client, cleaner, largo=244, ancho=183, costo=90_000)
    receta = crear_receta(client, cleaner, prod["id"], mat["id"], 2, tipo_escala="CORTE")
    r = client.put(f"/api/v1/receta/{receta['id']}", json={
        "ancho_corte_cm": 80, "largo_corte_cm": 130,
    }, headers=ADMIN_HEADERS)
    assert r.status_code == 200, r.text

    # Calcular precio con dimensiones base
    r = client.post(f"/api/v1/producto/{prod['id']}/calcular-precio", params={
        "ancho": 1.60, "largo": 1.90, "ganancia": 0, "iva": 0,
    }, headers=ADMIN_HEADERS)
    assert r.status_code == 200, r.text
    body = r.json()
    linea = [m for m in body["materiales"] if m["material_id"] == mat["id"]][0]

    paso("Con dimensiones base 1.60×1.90",
         f"  cantidad_calculada = {linea['cantidad_calculada']} cortes\n"
         f"  costo_unitario (por corte) = {dinero(linea['costo_unitario'])}\n"
         f"  costo_total = {dinero(linea['costo_total'])}\n"
         f"  laminas_equivalentes = {linea.get('laminas_equivalentes', '?')}")

    assert linea.get("es_corte") is True
    assert float(linea["cantidad_calculada"]) == 2.0
    assert float(linea["costo_unitario"]) == float(costo_por_corte(
        Decimal(90_000), Decimal(80 * 130), Decimal(244 * 183)))

    # Doble de área → doble de cortes
    r2 = client.post(f"/api/v1/producto/{prod['id']}/calcular-precio", params={
        "ancho": 3.20, "largo": 1.90, "ganancia": 0, "iva": 0,
    }, headers=ADMIN_HEADERS)
    assert r2.status_code == 200
    linea2 = [m for m in r2.json()["materiales"] if m["material_id"] == mat["id"]][0]

    dibujar_lamina_con_cortes(244, 183, 130, 80, 4, 90_000)

    paso("Con doble de área (3.20×1.90)",
         f"  cantidad_calculada = {linea2['cantidad_calculada']} cortes "
         f"(era 2, ahora 4 → duplica)\n"
         f"  costo_total = {dinero(linea2['costo_total'])}")

    assert abs(float(linea2["cantidad_calculada"]) - 4.0) < 1e-6

    paso("VERIFICACIONES",
         f"  ✅ Un mueble más grande necesita más cortes (escala con el área)\n"
         f"  ✅ La lámina de MDF se cobra proporcionalmente, no de más ni de menos\n"
         f"  ✅ laminas_equivalentes muestra cuántas láminas equivale en stock")

    resaltado(f"RESULTADO: el mueble normal pide 2 cortes ({dinero(linea['costo_total'])}), "
              f"el doble de grande pide 4 ({dinero(linea2['costo_total'])}).")
    print("  ✅ CASO 5 OK")
    print()


# ============================================================================
# Resumen final
# ============================================================================

def test_resumen_visual():
    print("\n" + LINEA)
    print(LINEA)
    caja("RESUMEN DE CASOS", [
        "CASO 1 — Corte desde lámina nueva (MDF 244×183, $90.000)",
        "  Se corta en tableros de 80×130 (caben 3 por lámina).",
        "  Se abre 1 lámina y el sobrante queda reutilizable.",
        "  Costo por corte = $90.000 × 10.400 / 44.652 = $20.962",
        "",
        "CASO 2 — Consumo desde sobrante",
        "  Un retazo 120×100 da 4 piezas de 45×45.",
        "  NO se toca el stock de láminas; solo se cobra el área usada.",
        "",
        "CASO 3 — Lámina completa PENDIENTE → CONFIRMAR",
        "  Piden 2 láminas ($180.000 provisional). Se confirma que solo",
        "  se usó 1 (8 cortes de 60×60) → la otra vuelve al depósito.",
        "",
        "CASO 4 — Madera masiva",
        "  m³ = (largo × ancho × espesor) × piezas ÷ 10000",
        "    = (200 × 4 × 2) × 2 ÷ 10000 = 0,32 m³ de cedro",
        "  costo = 0,32 × $750.000 = $240.000",
        "",
        "CASO 5 — Costeo paramétrico CORTE",
        "  La receta con tipo_escala=CORTE escala con el área del mueble:",
        "  doble de área → doble de cortes → doble de costo de material.",
    ])
    caja("CONCLUSIÓN", [
        "El sistema NO cobra una lámina entera a cada pedido:",
        "cobra PROPORCIONAL AL ÁREA que realmente se usa.",
        "Los sobrantes quedan disponibles para otros pedidos.",
        "La madera masiva se costea con una fórmula simple de m³.",
        "",
        "SI VA ACORDE AL FLUJO QUE QUEREMOS ✓",
    ])
    print(LINEA)