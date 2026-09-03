"""Carga inicial de inventario REAL (pinturas, tapicería y colchones).

Divisiones del inventario:
  - PINTURAS / TAPICERIA → insumos (material) con departamento PINTURA/TAPICERIA,
    stock en Depósito Principal, unidad por defecto "Unidad" (medidas se afinan luego).
  - COLCHONES → productos de REVENTA en USD (precio_costo_base = COMPRA + PASADA).

El precio unitario SIEMPRE es TOTAL = COMPRA + PASADA (la "pasada" se cuenta).
"""
from decimal import Decimal
from datetime import datetime

from app.db.session import session_local
from app.modules.productos.model import Material, Producto
from app.modules.inventory.model import (
    Inventario, MovimientoInventario, ProductoInventario, MovimientoProductoInventario,
)

DEPOSITO_ID = 1
UNIDAD_MEDIDA_DEFAULT = 1  # "Unidad": medidas reales se afinan después
TIPO_REVENDIDO = 2         # tipo_producto "Revendido"
MONEDA_USD = 2
STOCK_MINIMO_MATERIAL = Decimal("8")

PINTURAS = """\
$ 200,000	$ 25,000	$ 225,000	SELLADOR ECONOMICO CUÑETE 		2
$ 270,000	$ 25,000	$ 295,000	SELLADOR PRIME CUÑETE		0
$ 380,000	$ 25,000	$ 405,000	LACA BRILLANTE PIMPINA		1
$ 242,000	$ 25,000	$ 267,000	COLBON CUÑETE 		1
$ 64,000	$ 5,000	$ 69,000	GALON DE LACA  OVERLAC BRILLANTE		5
$ 84,000	$ 5,000	$ 89,000	LACA SEMI MATE NA		4
$ 71,000	$ 5,000	$ 76,000	LACA BRILLANTE BLANCA EVERY NA		4
$ 69,000	$ 5,000	$ 74,000	LACA DE NEGRO MEZCA		7
$ 60,000	$ 5,000	$ 65,000	SELLADOR BLANCO CATALIZADO MARCA PREMIUN COLOR 		8
$ 62,000	$ 5,000	$ 67,000	SELLADOR NITRO		2
$ 54,000	$ 5,000	$ 59,000	SELLADOR BLANCO MARCA PINTEMOS		7
$ 53,000	$ 5,000	$ 58,000	SELLADOR NEGRO MARCA PINTEMOS		6
$ 60,000	$ 5,000	$ 65,000	ESMALTE NEGRO SUPER 		2
$ 60,000	$ 5,000	$ 65,000	ESMALTE ALUMIO FULL COLOR		1
$ 49,000	$ 5,000	$ 54,000	ESMALTE BLANCO MARCA SUPER 		1
$ 280,000	$ 5,000	$ 285,000	POLIURETANO BLANCO  		0
$ 64,000	$ 5,000	$ 69,000	LACA ROJO OXIDO		1
$ 85,000	$ 5,000	$ 90,000	LACA CHAMPAM		1
$ 64,000	$ 5,000	$ 69,000	LACA ALUMIO GRANO FINO		7
$ 65,000	$ 5,000	$ 70,000	LACA BLANCO MEZCLA  		8
$ 17,500	$ 1,000	$ 18,500	TINTE TABACO MARCA TONNER		1
$ 17,500	$ 1,000	$ 18,500	TINTE CARMELO MARCA TONNER		2
$ 20,000	$ 1,000	$ 21,000	TINTE MIEL MARCA SUPER		2
$ 74,500	$ 5,000	$ 79,500	SUPER PL		0
$ 29,000	$ 5,000	$ 34,000	TINER		4
$ 38,000	$ 5,000	$ 43,000	SUPER SPRAY 		4
$ 58,000	$ 5,000	$ 63,000	SUPER NORMAL		0
$ 280,000	$ 5,000	$ 285,000	POLIURETANO NEGRO BRILLANTE 		0
$ 260,000	$ 5,000	$ 265,000	POLIURETANO TRASPARENTE 		1
$ 327,000	$ 5,000	$ 332,000	GALON DE BLANCO PERLA 		0
$ 34,000	$ 15,000	$ 49,000	BULTO DE TALCO POR 25KG		1
$ 1,900	$ 100	$ 2,000	LIJA# 100/120/150/180/220/240/400		
$ 4,000	$ 100	$ 4,100	LIJA #2000		
$ 66,000	$ 5,000	$ 71,000	MASILLA NEGRA MARCA SUPER 		1
$ 69,000	$ 5,000	$ 74,000	MASILLA BLANCA MARCA SUPER		1
$ 60,000	$ 5,000	$ 65,000	MASILLA GRIS MARCA SUPER		1
$ 22,000	$ 1,000	$ 23,000	REMOVEDOR SUPER 		0
$ 25,000		$ 25,000	ESCARCHA BLANCA Y MULTICOLOR		0
$ 5,000		$ 5,000	TIRRO		0
$ 4,000		$ 4,000	LITRO DE GASOLINA 		0
$ 18,000		$ 18,000	KEROSEN LITRO		0
$ 195,000	$ 5,000	$ 200,000	GALON DE ENCINA 		"""

COLCHONES = """\
186	$ 30	$ 216	DALLAS CLASISCO DE METRO		5
232	$ 16	$ 248	DALLAS CLASICO DE 1,40		0
325	$ 40	$ 365	COLCHON EURO PILLON DE 1,40		0
400		$ 400	COLCHON EURO PILLON DE 1,60		0
325	$ 40	$ 365	COLCHON LADY BEST 1,40		0
		$ 0	COLCHON LADY BEST 1,60		0
226	$ 30	$ 256	COLCHON DALLAS 1 PILLON METRO		10
283	$ 30	$ 313	COLCHON DALLAS 1 PILLON 1,40		1
338	$ 30	$ 368	COLCHON DALLAS 1 PILLON 1,60		8
389	$ 74	$ 463	COLCHON DALLAS 1 PILLON 2X2		1
573	$ 90	$ 663	COLCHON PERFEC SPLEEPER 1,40		4
698	$ 91	$ 789	COLCHON PERFEC SPLEEPER 1,60		4
729	$ 94	$ 823	COLCHON PERFEC SPLEEPER 2X2		4
578	$ 80	$ 658	COLCHON THERAFLEX		1
		$ 0	COLCHON GULT COAST DE METRO 		1"""

TAPICERIA = """\
$ 9,000	$ 2,000	$ 11,000	ESPUMA ROSADA 1CM 		18
$ 17,500	$ 4,000	$ 21,500	ESPUMA ROSADA 1"		14
$ 25,800	$ 6,000	$ 31,800	ESPUMA ROSADA 1" 1/2		20
$ 43,000	$ 8,000	$ 51,000	ESPUMA ROSADA DE 2"		1
$ 39,000	$ 6,000	$ 45,000	ESPUMA GRIS DE 1"1/2		2
$ 65,000	$ 8,000	$ 73,000	ESPUMA GRIS DE 2"		56
$ 14,000	$ 2,000	$ 16,000	ESPUMA NARANJA 1CM		9
$ 65,000	$ 8,000	$ 73,000	ESPUMA NARANJA 2"		29
$ 13,200	$ 4,000	$ 17,200	ESPUMA BLANCA 1"		37
$ 73,000	$ 8,000	$ 81,000	ESPUMA PENTA DE LUJA BLANCA 2"		0
$ 1,600			CIERRE BLANCO 		32
$ 1,600			CIERRE NEGRO METROS 		67
$ 380			CABEZAS DE CIERRE BLANCAS 		50
$ 380			CABEZAS DE CIERRE NEGRAS 		36
$ 26,000			CAÑAMO BLANCO 		2
$ 26,000			CAÑAMO NEGRO		3
$ 9,500			HILO 138 DE 40MS PLATA 		4
$ 9,500			HILO 138 DE 40MS DURAZNO		2
$ 9,500			HILO AZUL REY 		2
$ 22,500			HILO 138 MARRON 80GMS		2
$ 22,500			HILO 138 MARRON 80GMS EMPESADOS		2
$ 22,500			HILO 138 GRIS OSCURO 80GMS 		1
$ 22,500			HILO 138 BLANCO 80 GMS		3
$ 22,500			HILO 138 BEIGE DORADO 80GMS 		6
$ 22,500			HILO 69 GRIS 200GMS		1
$ 22,500			HILO 69 MARRON 200GMS		1
$ 22,500			HILO 69 GRIS OSCURO 200GMS 		1
$ 20,000			HILO DE ALGODÓN BLANCO		1
$ 700	$ 40	$ 740	CINCHA AZUL ELASTICA  MTS VIENE EN ROLLO DE 50		200
$ 9,000	$ 200	$ 9,200	CINCHA DE CAUCHO ROLLO		12
$ 44,000	$ 2,000	$ 46,000	CINCHA DE TELA POR 100 MTS 		7
$ 20,000			POKERT DE 55 X 55		4
$ 27,500			HERRAJE DE CABECERO 		4
$ 18,700	$ 1,000	$ 19,700	GUATA 300		9
$ 4,700	$ 1,000	$ 5,700	LAMINA DE CARTON 		4
$ 8,500	$ 1,250	$ 9,750	CAJA DE GRAPAS 		1
$ 38,000	$ 5,000	$ 43,000	SUPER SPRAY		4
$ 14,000	$ 1,000	$ 15,000	ALGODÓN SILICONADO		27
$ 1,900	$ 500	$ 2,400	LIENCILLO POR 100 MTS		0
$ 184,400	$ 50,000	$ 234,400	COSTAL		0
$ 1,200			MULTIUSOS GRANDS		14
			MULTIUSOS PEQUEÑOS		13
$ 75,000	$ 5,000	$ 80,000	RESORTE NOTZA ROLLOS		4
$ 400			GRAPAS NOTZA		206
$ 50,000			CAJA DE ESTOPEROLES PALMA 1000		1
$ 2,500	$ 1,000	$ 3,500	PORTAVASOS NEGROS 		3
$ 12,000	$ 1,000	$ 13,000	PORTAVASOS DE ALUMINIO		2
$ 130,000		$ 130,000	CARGADOR INALAMBRICO CON DOS PUERTOS BLANCO 		1
$ 130,000		$ 130,000	CARGADOR INALAMBRICO CON DOS PUERTOS NEGRO		0
		$ 0	PLATINAS PARA PATAS 		5
		$ 0	MINAS PLATA 		5
		$ 0	AGUJAS LARGAS 		1
$ 25,000			HERRAJE C14		2
$ 10,500			CLIK CLAK		2
$ 2,050			RODACHINES BLANCOS 		30
$ 10,500			PARES DE GRILLOS 		3
$ 360,000	$ 20,000	$ 380,000	HERRAJES ELECTRONICO RECLINOMATICO		3
$ 140,000	$ 20,000	$ 160,000	HERRAJE RECLINOMATICO MANUAL		4
		$ 0	HERRAJES DE MUEBLE ZULEIKA		4
			PATAS L CROMADAS 		88
			PATAS ZAPATILLA NEGRA		24
			PATAS METALICAS REDONDAS NEGRAS 		4
			PATAS METALICAS REDONDAS  GRIS		2
			PATAS MUNDO DORADAS 		2
			PATAS L DORADAS 		2
			PATAS NEGRAS L		1
			PATAS ESTRELLAS PLATEADAS 8CM		7
			PATAS ZAPATILLAS PLATEADAS 7 CM		8
			PATAS DORADAS LARGAS 20CM		12
			PATAS PLATEDAS 20CM 		2
			EMBOPLAST ROLLOS 		8
			PAPEL DE EMBALAR		1
			CABULLA		11"""


def parse_num(valor) -> Decimal | None:
    if valor is None:
        return None
    s = str(valor).strip().replace("$", "").replace(",", "").replace("\u00a0", "").replace(" ", "")
    if not s:
        return None
    try:
        return Decimal(s)
    except Exception:
        return None


def parse_filas(bloque: str):
    """Devuelve [(nombre, compra, pasada, total, existencia)]."""
    filas = []
    for linea in bloque.splitlines():
        if not linea.strip():
            continue
        partes = linea.split("\t")
        if len(partes) < 4:
            continue
        compra = parse_num(partes[0])
        pasada = parse_num(partes[1])
        total = parse_num(partes[2])
        nombre = partes[3].strip()
        existencia = parse_num(partes[5] if len(partes) > 5 else None) or Decimal("0")
        if not nombre:
            continue
        filas.append((nombre, compra, pasada, total, existencia))
    return filas


def costo_insumo(compra, pasada, total) -> Decimal:
    """COP: si el TOTAL del Excel vino, se usa; si no, COMPRA + PASADA."""
    if total is not None and total > 0:
        return total
    return (compra or Decimal("0")) + (pasada or Decimal("0"))


def costo_reventa(compra, pasada, total) -> Decimal | None:
    """USD. None si no hay NINGÚN dato de costo (no inventar un precio)."""
    if total is not None and total > 0:
        return total
    if compra is not None or pasada is not None:
        return (compra or Decimal("0")) + (pasada or Decimal("0"))
    return None


if __name__ == "__main__":
    db = session_local()
    ahora = datetime.utcnow()

    # ── 1. INSUMOS: pinturas y tapicería ──
    n_materiales = 0
    for departamento, bloque in (("PINTURA", PINTURAS), ("TAPICERIA", TAPICERIA)):
        for nombre, compra, pasada, total, existencia in parse_filas(bloque):
            costo = costo_insumo(compra, pasada, total)
            material = Material(
                nombre=nombre,
                unidad_medida_id=UNIDAD_MEDIDA_DEFAULT,
                costo_base=costo,
                stock_minimo=STOCK_MINIMO_MATERIAL,
                activo=True,
                departamento=departamento,
            )
            db.add(material)
            db.flush()
            db.add(Inventario(material_id=material.id, ubicacion_id=DEPOSITO_ID, cantidad=existencia))
            db.add(MovimientoInventario(
                material_id=material.id,
                ubicacion_id=DEPOSITO_ID,
                tipo="ENTRADA",
                cantidad=existencia,
                costo_unitario=costo,
                fecha=ahora,
                referencia_tipo="CARGA_INICIAL",
                observaciones="Carga inicial de inventario (Excel)",
            ))
            n_materiales += 1

    # ── 2. COLCHONES: productos de reventa (USD) ──
    n_colchones = 0
    for nombre, compra, pasada, total, existencia in parse_filas(COLCHONES):
        costo = costo_reventa(compra, pasada, total)
        producto = Producto(
            nombre=nombre,
            tipo_producto_id=TIPO_REVENDIDO,
            descripcion="Colchón de reventa (carga inicial)",
            activo=True,
            stock_minimo=Decimal("0"),
            es_reventa=True,
            moneda_id=MONEDA_USD,
            precio_costo_base=costo,
        )
        db.add(producto)
        db.flush()
        db.add(ProductoInventario(
            producto_id=producto.id, ubicacion_id=DEPOSITO_ID,
            cantidad=existencia, costo_promedio=costo,
        ))
        db.add(MovimientoProductoInventario(
            producto_id=producto.id,
            ubicacion_id=DEPOSITO_ID,
            tipo="ENTRADA",
            cantidad=existencia,
            costo_unitario=costo,
            fecha=ahora,
            referencia_tipo="CARGA_INICIAL",
            observaciones="Carga inicial de inventario (Excel)",
        ))
        n_colchones += 1

    db.commit()
    print(f"Insumos importados: {n_materiales}")
    print(f"Colchones importados: {n_colchones}")
    db.close()