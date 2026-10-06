"""Importa notas de entrega que nunca entraron al ERP (Dayana, Jeismar).

Crea cliente + cotización + pedido + detalles + órdenes + venta + etapas, todo
en UNA transacción con SQL directo. No usa convertir_cotizacion_a_pedido a
propósito: ese servicio indexa las líneas por (tipo_item, producto_id,
material_id) y los muebles a la medida tienen producto_id NULL, así que varias
líneas del mismo tipo colapsan en una sola clave. Aquí cada línea se inserta
por separado, que es lo que la nota de papel realmente significa.

Los precios son PROVISIONALES (la nota vino sin columna de valores) y quedan
marcados en observaciones para no confundirlos con un monto confirmado.

Dry-run por defecto.
"""

import argparse
from datetime import date as fecha_tipo

import app.main  # noqa: F401
from app.db.session import session_local

AVISO = "PRECIO PROVISIONAL: la nota de entrega vino sin valor. Pendiente confirmar."

NOTAS = [
    {
        "cliente": {
            "nombre": "DAYANA GARCIA",
            "cedula": None,
            # La nota vino sin RIF ni teléfono; se deja un marcador para no
            # dejar el campo vacío (el modelo lo exige NOT NULL).
            "telefono": "0424-0000000",
            "direccion": "Ureña, Las Comunas",
            "observaciones": "Importado de nota de entrega 31/08/2026 (papel sin RIF/teléfono)",
        },
        "fecha": fecha_tipo(2026, 8, 31),
        "lineas": [
            {"desc": "MUEBLE DE 2 PUESTOS TAL CUAL A LA FOTO", "precio": 700.0, "area": "Ebanistería"},
            {"desc": "POLTRONA TAL CUAL A LA FOTO", "precio": 350.0, "area": "Ebanistería"},
        ],
    },
    {
        "cliente": {
            "nombre": "JEISMAR VILLAMIZAR",
            "cedula": "C.C.V-31.119.053",
            "telefono": "0424-7710011",
            "direccion": "San Antonio Garrochal",
            "observaciones": "Importado de nota de entrega 28/08/2026",
        },
        "fecha": fecha_tipo(2026, 8, 28),
        "lineas": [
            {"desc": (
                "JUEGO DE MUEBLES DE 3 PUESTOS Y 2 POLTRONAS HACERLO TAL CUAL A LA FOTO. "
                "TAPIZAR EN TELA PERSEA CREMA Y HACER 3 COJINES DECORATIVOS EN TELA LYON HIELO "
                "Y 2 COJINES DECORATIVOS EN TELA ONIX BEIGE. PARA ENTREGAR EN 25 DIAS HABILES."),
             "precio": 1699.0, "area": "Ebanistería"},
        ],
    },
]


def main(aplicar=False):
    from app.modules.catalogos.model import Area
    from app.modules.clients.model import Client
    from app.modules.orders import model as pedido_model
    from app.modules.production.model import EtapaProduccion, OrdenProduccion
    from app.modules.quotes.model import Cotizacion, DetalleCotizacion
    from app.modules.sales.model import Venta
    from app.modules.users.model import Usuario

    db = session_local()
    try:
        areas = {a.nombre: a.id for a in db.query(Area).all()}
        usuario = db.query(Usuario).join(Usuario.roles).first()
        uid = usuario.id if usuario else None

        for nota in NOTAS:
            nombre = nota["cliente"]["nombre"]
            if db.query(Client).filter(Client.nombre == nombre).first():
                print(f"[SKIP] {nombre} ya existe")
                continue
            total = sum(l["precio"] for l in nota["lineas"])
            print(f"\n{nombre} · {nota['fecha']} · total provisional {total:,.2f}")
            for l in nota["lineas"]:
                print(f"  - {l['desc'][:55]} | {l['precio']:,.2f} | {l['area']}")

            if not aplicar:
                continue

            cli = Client(**nota["cliente"], creado_por_id=uid, actualizado_por_id=uid)
            db.add(cli)
            db.flush()

            # Una cotización y un pedido por línea: evita el colapso de claves
            # del servicio de conversión para muebles a la medida.
            for l in nota["lineas"]:
                cot = Cotizacion(
                    cliente_id=cli.id, fecha=nota["fecha"], estado="APROBADA",
                    total_estimado=l["precio"], moneda_id=1, tasa_cambio=1.0,
                    observaciones=AVISO, creado_por_id=uid, actualizado_por_id=uid,
                )
                db.add(cot)
                db.flush()
                db.add(DetalleCotizacion(
                    cotizacion_id=cot.id, producto_id=None, cantidad=1,
                    precio=l["precio"], tipo_item="FABRICADO", observaciones=l["desc"],
                ))

                pedido = pedido_model.Pedido(
                    cotizacion_id=cot.id, cliente_id=cli.id, fecha=nota["fecha"],
                    estado="PRODUCCION", observaciones=AVISO,
                    creado_por_id=uid, actualizado_por_id=uid,
                )
                db.add(pedido)
                db.flush()
                db.add(pedido_model.DetallePedido(
                    pedido_id=pedido.id, producto_id=None, material_id=None,
                    tipo_item="FABRICADO", cantidad=1, precio=l["precio"],
                    descripcion_especifica=l["desc"], observaciones=l["desc"],
                ))
                db.flush()

                det = db.query(pedido_model.DetallePedido).filter(
                    pedido_model.DetallePedido.pedido_id == pedido.id
                ).first()

                orden = OrdenProduccion(
                    detalle_pedido_id=det.id, estado="PENDIENTE",
                    tipo="PEDIDO", creado_por_id=uid, actualizado_por_id=uid,
                )
                db.add(orden)
                db.flush()

                if l["area"] in areas:
                    db.add(EtapaProduccion(
                        orden_produccion_id=orden.id, area_id=areas[l["area"]],
                        empleado_responsable_id=None, estado="EN_PROCESO",
                        observaciones="Sincronizado desde nota de entrega",
                    ))
                db.add(Venta(
                    pedido_id=pedido.id, cliente_id=cli.id, estado="PENDIENTE",
                    moneda_id=1, fecha=nota["fecha"], total=l["precio"],
                    tasa_cambio=1.0, observaciones=AVISO,
                    creado_por_id=uid, actualizado_por_id=uid,
                ))
                db.flush()
                print(f"  + cot#{cot.id} → pedido#{pedido.id} → orden#{orden.id} "
                      f"({l['area']})")

        if aplicar:
            db.commit()
            print("\n[OK] commit realizado")
        else:
            db.rollback()
            print("\n[DRY-RUN] nada escrito. Usa --aplicar.")
    finally:
        db.close()


if __name__ == "__main__":
    ap = argparse.ArgumentParser()
    ap.add_argument("--aplicar", action="store_true")
    main(aplicar=ap.parse_args().aplicar)