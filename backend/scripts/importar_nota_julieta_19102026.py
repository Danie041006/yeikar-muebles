# -*- coding: utf-8 -*-
"""Importa la nota de entrega de JULIETA HIDALGO / C. SANDOVAL (19/10/2026).

Nota de papel:
  1 x CAMA 2X2 COPETE 1.30 PERSA PLATA ......... USD 1.387
  2 x MESAS DE NOCHE GRIS HUMO ................. USD   239 c/u  (478)
  1 x COMEDOR 6 PTOS GRIS HUMO / PERSA GRIS .... USD 1.870
  1 x COLCHON PERFECT SLEEPER 2X2 .............. USD   813
  1 x MODULAR RECLINOMATICO 5 PTOS ............. USD 1.999
  TOTAL ........................................ USD 6.547
  (abono 22/10 de USD 600 NO se registra: lo hacen ellos)

Crea los 4 muebles como productos nuevos (el colchón YA existe:
COLCHON PERFEC SPLEEPER 2X2, id 12925) y la cadena
cotización APROBADA -> pedido -> venta + detalle. Sin inventario, sin caja
y sin abonos. La venta queda PENDIENTE por el total.

Uso:
  PYTHONPATH=/app python scripts/importar_nota_julieta_19102026.py            # dry-run
  PYTHONPATH=/app python scripts/importar_nota_julieta_19102026.py --aplicar  # commit
"""
from __future__ import annotations

import argparse
from datetime import date, datetime
from decimal import Decimal

import app.main  # noqa: F401  (registra todos los modelos)
from app.db.session import session_local
from sqlalchemy import func

TAG = "NOTA-OCT2026-JULIETA"
FECHA = date(2026, 10, 19)

CLIENTE = {
    "nombre": "JULIETA HIDALGO / C. SANDOVAL",
    "cedula": "V-26125274",
    "telefono": "0424-7377019",
    "direccion": "LAS FLORES",
    "observaciones": "Nota de entrega 19/10/2026",
}

# (nombre, tipo_producto_id, precio USD, descripcion)
PRODUCTOS = [
    (
        "CAMA 2X2 CON COPETE DE 1.30 PERSA PLATA Y LARGUEROS GRIS HUMO",
        5,  # Cama
        "1387.00",
        "Cama de 2x2 tal cual modelo de la foto. Copete de 1.30 de alto tapizado "
        "en Persa Plata; largueros en gris humo; solo se tapiza el cabecero con "
        "luz calida; largueros y piecero pintados en gris humo.",
    ),
    (
        "MESAS DE NOCHE MODELO FOTO GRIS HUMO CON MANILLAS PLATIADAS",
        7,  # Nochero / Gavetero
        "239.00",
        "Mesas de noche tal cual la foto, con manillas platiadas y pintadas en "
        "color gris humo.",
    ),
    (
        "COMEDOR 6 PUESTOS GRIS HUMO PERSA GRIS BASE 3D",
        8,  # Comedor
        "1870.00",
        "Comedor de 6 puestos tal cual al modelo, pintado en color gris humo y "
        "tapizado en Persa Gris, con base 3D.",
    ),
    (
        "MODULAR RECLINOMATICO 5 PUESTOS GRIS PERSA CON 5 COJINES PERSA PLATA",
        10,  # Modular / Barra
        "1999.00",
        "Modular reclinomatico en color gris Persa de 5 puestos con sus 5 cojines "
        "en color Persa Plata.",
    ),
]

COLCHON_ID = 12925  # COLCHON PERFEC SPLEEPER 2X2 (reventa, USD 813)
COLCHON_PRECIO = "813.00"
COLCHON_COSTO = "729.00"


def main(aplicar: bool = False) -> None:
    from app.modules.catalogos.model import Moneda
    from app.modules.clients.model import Client
    from app.modules.orders.model import DetallePedido, Pedido
    from app.modules.productos.model import Producto
    from app.modules.quotes.model import Cotizacion, DetalleCotizacion
    from app.modules.sales.model import DetalleVenta, Venta
    from app.modules.users.model import Usuario
    from app.modules.auditoria.service import record_event

    db = session_local()
    try:
        moneda = db.query(Moneda).filter(Moneda.codigo == "USD").first()
        if moneda is None:
            raise SystemExit("No existe la moneda USD")
        usuario = db.get(Usuario, 4)
        uid = usuario.id if usuario else None

        existente = (
            db.query(Cotizacion)
            .filter(func.coalesce(Cotizacion.observaciones, "").like(f"%{TAG}%"))
            .first()
        )
        if existente:
            print(f"[SKIP] ya existe la cotizacion #{existente.id} con la marca {TAG}")
            db.rollback()
            return

        # Cliente
        cliente = (
            db.query(Client)
            .filter(func.upper(Client.nombre) == CLIENTE["nombre"].upper())
            .first()
        )
        if cliente is None:
            print(f"Cliente NUEVO: {CLIENTE['nombre']} · {CLIENTE['cedula']} · {CLIENTE['telefono']}")
            if aplicar:
                cliente = Client(
                    nombre=CLIENTE["nombre"],
                    cedula=CLIENTE["cedula"],
                    telefono=CLIENTE["telefono"],
                    direccion=CLIENTE["direccion"],
                    observaciones=CLIENTE["observaciones"],
                    fecha_registro=FECHA,
                    creado_por_id=uid,
                )
                db.add(cliente)
                db.flush()
        else:
            print(f"Cliente existente: #{cliente.id} {cliente.nombre}")
        if not aplicar and cliente is None:
            cliente = Client(id=0, nombre=CLIENTE["nombre"], telefono=CLIENTE["telefono"])

        # Productos nuevos
        productos = []
        for nombre, tipo_id, precio, descripcion in PRODUCTOS:
            prod = (
                db.query(Producto)
                .filter(func.upper(Producto.nombre) == nombre.upper())
                .first()
            )
            if prod is None:
                print(f"Producto NUEVO: {nombre[:55]}... · USD {precio} · tipo {tipo_id}")
                if aplicar:
                    prod = Producto(
                        nombre=nombre,
                        tipo_producto_id=tipo_id,
                        descripcion=descripcion,
                        activo=True,
                        es_reventa=False,
                        moneda_id=moneda.id,
                        precio_venta_base=Decimal(precio),
                    )
                    db.add(prod)
                    db.flush()
            else:
                print(f"Producto existente: #{prod.id} {prod.nombre[:50]}")
            productos.append((prod, precio, "FABRICADO", Decimal("0"), descripcion))

        # Colchón existente
        colchon = db.get(Producto, COLCHON_ID)
        if colchon is None:
            raise SystemExit(f"No existe el colchón {COLCHON_ID}")
        productos.append((
            colchon, COLCHON_PRECIO, "REVENTA", Decimal(COLCHON_COSTO),
            colchon.nombre,
        ))

        # Cantidades por línea (en el mismo orden que PRODUCTOS + colchón)
        cantidades = [1, 2, 1, 1, 1]
        total = sum(
            Decimal(precio) * Decimal(str(cant))
            for (_, precio, _, _, _), cant in zip(productos, cantidades)
        )
        print(f"\nTotal nota: USD {total} · {len(productos)} líneas")
        if total != Decimal("6547.00"):
            raise SystemExit(f"El total {total} no coincide con la nota (6.547)")

        if not aplicar:
            print("\n[DRY-RUN] Nada escrito. Usa --aplicar para crear la cadena.")
            db.rollback()
            return

        cot = Cotizacion(
            cliente_id=cliente.id,
            fecha=FECHA,
            estado="APROBADA",
            total_estimado=total,
            moneda_id=moneda.id,
            tasa_cambio=Decimal("1"),
            total_en_moneda_base=None,
            observaciones=f"{TAG} · Nota de entrega 19/10/2026",
            creado_por_id=uid,
            actualizado_por_id=uid,
        )
        db.add(cot)
        db.flush()

        pedido = Pedido(
            cotizacion_id=cot.id,
            cliente_id=cliente.id,
            fecha=FECHA,
            estado="PRODUCCION",
            observaciones=f"{TAG} · Nota de entrega 19/10/2026 · abono de USD 600 el 22/10 lo registra el cliente",
            creado_por_id=uid,
            actualizado_por_id=uid,
        )
        db.add(pedido)
        db.flush()

        venta = Venta(
            pedido_id=pedido.id,
            cliente_id=cliente.id,
            moneda_id=moneda.id,
            fecha=FECHA,
            total=total,
            estado="PENDIENTE",
            tasa_cambio=Decimal("1"),
            total_en_moneda_base=None,
            observaciones=f"{TAG} · total USD {total} · sin abonos registrados",
            creado_por_id=uid,
            actualizado_por_id=uid,
        )
        db.add(venta)
        db.flush()

        for (prod, precio, tipo, costo, descripcion), cant in zip(productos, cantidades):
            db.add(DetalleCotizacion(
                cotizacion_id=cot.id, producto_id=prod.id, tipo_item=tipo,
                cantidad=Decimal(str(cant)), precio=Decimal(precio),
                descripcion_especifica=descripcion,
            ))
            db.add(DetallePedido(
                pedido_id=pedido.id, producto_id=prod.id, tipo_item=tipo,
                cantidad=Decimal(str(cant)), precio=Decimal(precio),
                descripcion_especifica=descripcion,
                costo_unitario=(costo if costo > 0 else None),
                porcentaje_ganancia=(
                    round((Decimal(precio) - costo) / costo * 100, 2) if costo > 0 else None
                ),
            ))
            db.add(DetalleVenta(
                venta_id=venta.id, producto_id=prod.id, tipo_item=tipo,
                cantidad=Decimal(str(cant)), precio=Decimal(precio),
                costo_unitario=(costo if costo > 0 else None),
                utilidad=((Decimal(precio) - costo) if costo > 0 else None),
                porcentaje_ganancia=(
                    round((Decimal(precio) - costo) / costo * 100, 2) if costo > 0 else None
                ),
                descuento=Decimal("0"),
                descripcion_especifica=descripcion,
            ))

        record_event(
            db, actor=usuario, action="CREATE", entity_type="venta", entity_id=venta.id,
            after={"origen": TAG, "cliente": cliente.nombre, "total": float(total),
                   "moneda": "USD", "estado": "PENDIENTE",
                   "productos_nuevos": len([p for p in PRODUCTOS]),
                   "colchon_id": COLCHON_ID},
        )

        # Promo obsequio (plástico de regalo): solo si el colchón vendido tiene
        # una promoción activa. Se agrega 1 obsequio por colchón a precio 0,
        # igual que la conversión cotización -> pedido.
        from app.modules.productos.model import PromocionObsequio

        promo = (
            db.query(PromocionObsequio)
            .filter(
                PromocionObsequio.colchon_id == COLCHON_ID,
                PromocionObsequio.activo.is_(True),
            )
            .first()
        )
        if promo is not None:
            obsequio = db.get(Producto, promo.obsequio_id)
            nombre_obsequio = obsequio.nombre if obsequio else f"producto {promo.obsequio_id}"
            cantidad_obsequio = Decimal(str(cantidades[-1]))
            db.add(DetallePedido(
                pedido_id=pedido.id, producto_id=promo.obsequio_id, tipo_item="REVENTA",
                cantidad=cantidad_obsequio, precio=Decimal("0"),
                descripcion_especifica=f"OBSEQUIO PROMO · {nombre_obsequio}",
                es_obsequio=True,
            ))
            db.add(DetalleVenta(
                venta_id=venta.id, producto_id=promo.obsequio_id, tipo_item="REVENTA",
                cantidad=cantidad_obsequio, precio=Decimal("0"),
                descuento=Decimal("0"), es_obsequio=True,
                descripcion_especifica=f"OBSEQUIO PROMO · {nombre_obsequio}",
            ))
            print(f"Obsequio promo agregado: {nombre_obsequio} x {cantidad_obsequio}")
        else:
            print("Obsequio promo: el colchón NO tiene plástico de regalo configurado")

        db.commit()
        print(f"\n[OK] cotizacion #{cot.id} -> pedido #{pedido.id} -> venta #{venta.id} "
              f"(USD {total}, PENDIENTE, sin abonos)")
    except Exception:
        db.rollback()
        raise
    finally:
        db.close()


if __name__ == "__main__":
    ap = argparse.ArgumentParser()
    ap.add_argument("--aplicar", action="store_true")
    main(aplicar=ap.parse_args().aplicar)
