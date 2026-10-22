# -*- coding: utf-8 -*-
"""Importa las 4 notas de octubre 2026 que estaban solo en la caja.

Notas de papel (dictadas por la dueña):
  1. MAYERLY PAMPLONA · 05/10/2026 · colchón Dallas 259 + lavadora AIWA 354
     = USD 613 pagados (caja Nequi 2.000.000). ENTREGADO.
  2. JOHAN RODRIGUEZ · 02/10/2026 · sala + poltronas + mesas + cama + espejo
     + cojín = USD 6.295, descuento 180, abonos 1.674 → saldo 4.441.
  3. NASLY HERNANDEZ · 01/10/2026 · colchón Euro Pillow USD 360 pagados
     (caja Nequi 1.188.000 a 3.300). ENTREGADO.
  4. ANGIE NIETO · 06/10/2026 · sala + poltrona + puff + comedor = USD 4.140,
     abono USDT 2.000 → saldo 2.140.

Crea Cliente (existente) -> Cotizacion APROBADA -> Pedido -> Venta + Detalle
(+ DescuentoVenta y Envio cuando aplica). NO toca inventario, caja ni genera
orden de producción: son notas ya vendidas/entregadas (mismo patrón que las
demás notas migradas).

Uso:
  PYTHONPATH=/app python scripts/importar_notas_octubre_2026.py            # dry-run
  PYTHONPATH=/app python scripts/importar_notas_octubre_2026.py --aplicar  # commit
"""
from __future__ import annotations

import argparse
from datetime import date, datetime
from decimal import Decimal

import app.main  # noqa: F401  (registra todos los modelos)
from app.db.session import session_local
from sqlalchemy import func

NOTAS = [
    {
        "tag": "NOTA-OCT2026-MAYERLY",
        "cliente_id": 180,
        "fecha": date(2026, 10, 5),
        "entregado": True,
        "direccion": "BARRIO EL CASTILLO VEREDA 13 CALLE 7 N7-7",
        "lineas": [
            (1, "COLCHON DALLAS CLASICO 0080", "259.00", "REVENTA"),
            (1, "LAVADORA DE 14 KILOS MARCA AIWA", "354.00", "REVENTA"),
        ],
    },
    {
        "tag": "NOTA-OCT2026-JOHAN",
        "cliente_id": 174,
        "fecha": date(2026, 10, 2),
        "entregado": False,
        "direccion": None,
        "descuento": ("180.00", "Descuento acordado en la nota"),
        "lineas": [
            (1, "JUEGO DE SALA TAL CUAL EL VIDEO: SOFA DE 3 PUESTOS CON HERRAJES "
                "DESPLAZABLES Y 2 POLTRONAS, TELA DOTTY HOME 1310, BRAZOS EN CUERINA "
                "PRANNA CAPUCHINO, 3 COJINES EN LA MISMA CUERINA Y 3 EN PERSEA CREMA, "
                "PASE Y PATAS PINTADAS EN EL TONO DE LA CUERINA", "2650.00", "FABRICADO"),
            (2, "POLTRONAS TAL CUAL AL MODELO, TELA JOURNEY 01 CRUDO CON 2 COJINES EN "
                "TELA VERA HOME 9600, PATAS PINTADAS EN EL TONO DEL MUEBLE PRINCIPAL",
             "630.00", "FABRICADO"),
            (1, "JUEGO DE MESAS DE CENTRO, PINTAR CAPUCHINO", "480.00", "FABRICADO"),
            (1, "CAMA MATRIMONIAL MODELO DE ESPALDAR COMO LA FOTO, AEREA, LARGUEROS Y "
                "PIECERO TAPIZADOS LISO Y BORDES PINTADOS", "1150.00", "FABRICADO"),
            (2, "MESAS DE NOCHE DEL MODELO DE LA FOTO, PINTAR EN WENGUE CON MANIJA "
                "DORADA, AEREA", "215.00", "FABRICADO"),
            (1, "ESPEJO DECORATIVO DE 2X1", "290.00", "FABRICADO"),
            (1, "COJIN ENTRELASADO BLANCO", "35.00", "FABRICADO"),
        ],
    },
    {
        "tag": "NOTA-OCT2026-NASLY",
        "cliente_id": 175,
        "fecha": date(2026, 10, 1),
        "entregado": True,
        "direccion": "BARRIO EMANUEL VIA LA MULATA",
        "lineas": [
            (1, "COLCHON EURO PILLOW DE 1,40 ORTOPEDICO CODIGO OBSEQUIO 0080",
             "360.00", "REVENTA"),
        ],
    },
    {
        "tag": "NOTA-OCT2026-ANGIE",
        "cliente_id": 184,
        "fecha": date(2026, 10, 6),
        "entregado": False,
        "direccion": None,
        "lineas": [
            (1, "SOFA DE 2 PUESTOS RECLINABLE MANUAL, CUERINA PRANNA HIELO, 2 COJINES "
                "EN TELA CLEMONT MARFIL Y 2 EN TELA CADILAC FRESA", "1400.00", "FABRICADO"),
            (1, "POLTRONA RECLINABLE MANUAL, CUERINA PRANNA HIELO", "700.00", "FABRICADO"),
            (1, "PUFF MODELO GIRASOL, CUERINA PRANNA HIELO", "290.00", "FABRICADO"),
            (1, "COMEDOR DE 6 PUESTOS EXPANSIBLE, BASE Y BUTACO LISO SIN WALL PANEL EN "
                "MELAMINA REF KOA CON 4 SILLAS MODELO KENA, CUERINA PRANNA HIELO",
             "1750.00", "FABRICADO"),
        ],
    },
]


def main(aplicar: bool = False) -> None:
    from app.modules.catalogos.model import Moneda
    from app.modules.clients.model import Client
    from app.modules.orders.model import DetallePedido, Pedido
    from app.modules.quotes.model import Cotizacion, DetalleCotizacion
    from app.modules.sales.model import DescuentoVenta, DetalleVenta, Venta
    from app.modules.envios.model import Envio
    from app.modules.users.model import Usuario
    from app.modules.auditoria.service import record_event

    db = session_local()
    try:
        moneda = db.query(Moneda).filter(Moneda.codigo == "USD").first()
        if moneda is None:
            raise SystemExit("No existe la moneda USD")
        usuario = db.get(Usuario, 4)  # daniel (admin)
        uid = usuario.id if usuario else None

        for nota in NOTAS:
            tag = nota["tag"]
            cliente = db.get(Client, nota["cliente_id"])
            if cliente is None:
                raise SystemExit(f"[{tag}] no existe el cliente {nota['cliente_id']}")
            existente = (
                db.query(Cotizacion)
                .filter(func.coalesce(Cotizacion.observaciones, "").like(f"%{tag}%"))
                .first()
            )
            total = sum(Decimal(str(p)) * Decimal(str(c)) for c, _, p, _ in nota["lineas"])
            print(f"\n[{tag}] cliente #{cliente.id} {cliente.nombre} · {nota['fecha']} · "
                  f"{len(nota['lineas'])} líneas · total USD {total}")
            if existente:
                print(f"  [SKIP] ya existe la cotizacion #{existente.id} con esa marca")
                continue
            for cant, desc, precio, tipo in nota["lineas"]:
                print(f"   {cant} x {desc[:60]}... @ {precio} ({tipo})")
            if nota.get("descuento"):
                print(f"   descuento: USD {nota['descuento'][0]}")

            if not aplicar:
                continue

            cot = Cotizacion(
                cliente_id=cliente.id,
                fecha=nota["fecha"],
                estado="APROBADA",
                total_estimado=total,
                moneda_id=moneda.id,
                tasa_cambio=Decimal("1"),
                total_en_moneda_base=None,
                observaciones=f"{tag} · Nota de octubre 2026 migrada de la nota de papel",
                creado_por_id=uid,
                actualizado_por_id=uid,
            )
            db.add(cot)
            db.flush()
            for cant, desc, precio, tipo in nota["lineas"]:
                db.add(DetalleCotizacion(
                    cotizacion_id=cot.id, producto_id=None, tipo_item=tipo,
                    cantidad=Decimal(str(cant)), precio=Decimal(str(precio)),
                    descripcion_especifica=desc,
                ))

            pedido = Pedido(
                cotizacion_id=cot.id,
                cliente_id=cliente.id,
                fecha=nota["fecha"],
                estado="ENTREGADO" if nota["entregado"] else "PRODUCCION",
                observaciones=f"{tag} · Nota de octubre 2026",
                fecha_entrega_estimada=nota["fecha"] if nota["entregado"] else None,
                creado_por_id=uid,
                actualizado_por_id=uid,
            )
            db.add(pedido)
            db.flush()
            for cant, desc, precio, tipo in nota["lineas"]:
                db.add(DetallePedido(
                    pedido_id=pedido.id, producto_id=None, tipo_item=tipo,
                    cantidad=Decimal(str(cant)), precio=Decimal(str(precio)),
                    descripcion_especifica=desc,
                ))

            venta = Venta(
                pedido_id=pedido.id,
                cliente_id=cliente.id,
                moneda_id=moneda.id,
                fecha=nota["fecha"],
                total=total,
                estado="PENDIENTE",
                tasa_cambio=Decimal("1"),
                total_en_moneda_base=None,
                observaciones=f"{tag} · Nota de octubre 2026 · total USD {total}",
                creado_por_id=uid,
                actualizado_por_id=uid,
            )
            db.add(venta)
            db.flush()
            for cant, desc, precio, tipo in nota["lineas"]:
                db.add(DetalleVenta(
                    venta_id=venta.id, producto_id=None, tipo_item=tipo,
                    cantidad=Decimal(str(cant)), precio=Decimal(str(precio)),
                    descuento=Decimal("0"), descripcion_especifica=desc,
                ))

            if nota.get("descuento"):
                monto, motivo = nota["descuento"]
                db.add(DescuentoVenta(
                    venta_id=venta.id, moneda_id=moneda.id,
                    fecha=datetime.combine(nota["fecha"], datetime.min.time()).replace(hour=12),
                    monto=Decimal(monto), tasa_cambio=Decimal("1"),
                    monto_en_moneda_base=Decimal(monto),
                    motivo=motivo, creado_por_id=uid,
                ))

            envio = None
            if nota["entregado"]:
                cuando = datetime.combine(nota["fecha"], datetime.min.time()).replace(hour=12)
                envio = Envio(
                    pedido_id=pedido.id,
                    estado="ENTREGADO",
                    fecha_salida=cuando,
                    fecha_entrega=cuando,
                    direccion_entrega=nota["direccion"],
                    observaciones=f"{tag} · Entregado segun nota de papel",
                    creado_por_id=uid,
                    actualizado_por_id=uid,
                    asignado_por_usuario_id=uid,
                )
                db.add(envio)
                db.flush()

            record_event(
                db, actor=usuario, action="CREATE", entity_type="venta", entity_id=venta.id,
                after={"origen": tag, "cliente": cliente.nombre, "total": float(total),
                       "moneda": "USD", "estado": "PENDIENTE",
                       "descuento": nota.get("descuento", (None,))[0],
                       "envio": envio.id if envio else None},
            )
            print(f"  creado: cotizacion #{cot.id} -> pedido #{pedido.id} -> venta #{venta.id}"
                  + (f" -> envio #{envio.id}" if envio else ""))

        if aplicar:
            db.commit()
            print("\nAPLICADO")
        else:
            db.rollback()
            print("\nDRY-RUN (sin cambios)")
    except Exception:
        db.rollback()
        raise
    finally:
        db.close()


if __name__ == "__main__":
    ap = argparse.ArgumentParser()
    ap.add_argument("--aplicar", action="store_true")
    main(aplicar=ap.parse_args().aplicar)
