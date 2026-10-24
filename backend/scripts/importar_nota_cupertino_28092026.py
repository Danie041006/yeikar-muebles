# -*- coding: utf-8 -*-
"""Importa la nota de entrega de CUPERTINO BENITEZ del 28/09/2026.

Nota de papel:
  1 x COLCHON DALLAS 1 PILLON DE 1,60 = USD 351
  Entregado el 28/09/2026. Sin abonos: saldo USD 351.

Crea Cliente (existente) -> Cotizacion APROBADA -> Pedido ENTREGADO ->
Venta PENDIENTE + DetalleVenta + Envio ENTREGADO. NO toca inventario, caja
ni genera orden de produccion (es un colchon de REVENTA).

Uso:
  python scripts/importar_nota_cupertino_28092026.py            # dry-run
  python scripts/importar_nota_cupertino_28092026.py --aplicar  # commit
"""

import argparse
from datetime import date, datetime
from decimal import Decimal

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

from sqlalchemy import func

from app.db.session import session_local

TAG = "NOTA-ENTREGA-28092026-CUPERTINO"
FECHA = date(2026, 9, 28)
FECHA_HORA = datetime(2026, 9, 28, 12, 0)
TOTAL = Decimal("351.00")
COSTO = Decimal("338.00")
UTILIDAD = Decimal("13.00")
PCT_GANANCIA = Decimal("3.85")
DESCRIPCION = "COLCHON DALLAS 1 PILLON DE 1,60"
PRODUCTO_ID = 12921
CLIENTE_ID = 11
USUARIO_ID = 2  # Carolina (Dueña)


def main(aplicar: bool = False) -> None:
    from app.modules.catalogos.model import Moneda
    from app.modules.clients.model import Client
    from app.modules.productos.model import Producto
    from app.modules.quotes.model import Cotizacion, DetalleCotizacion
    from app.modules.orders.model import Pedido, DetallePedido
    from app.modules.sales.model import Venta, DetalleVenta
    from app.modules.envios.model import Envio
    from app.modules.users.model import Usuario
    from app.modules.auditoria.service import record_event

    db = session_local()
    try:
        cliente = db.query(Client).filter(Client.id == CLIENTE_ID).first()
        if not cliente or "CUPERTINO" not in (cliente.nombre or "").upper():
            raise SystemExit(f"No se encontro el cliente {CLIENTE_ID} CUPERTINO BENITEZ")
        producto = db.query(Producto).filter(Producto.id == PRODUCTO_ID).first()
        if not producto or "DALLAS" not in (producto.nombre or "").upper():
            raise SystemExit(f"No se encontro el producto {PRODUCTO_ID} COLCHON DALLAS 1,60")
        if not producto.es_reventa:
            raise SystemExit(f"El producto {PRODUCTO_ID} no esta marcado como reventa")
        moneda = db.query(Moneda).filter(Moneda.codigo == "USD").first()
        if not moneda:
            raise SystemExit("No existe la moneda USD")
        usuario = db.query(Usuario).filter(Usuario.id == USUARIO_ID).first()

        print(f"Cliente:  #{cliente.id} {cliente.nombre} ({cliente.cedula})")
        print(f"Producto: #{producto.id} {producto.nombre} ({producto.codigo})")
        print(f"Moneda:   #{moneda.id} {moneda.codigo}")
        print(f"Fecha:    {FECHA}  Total: USD {TOTAL}  Costo: USD {COSTO}")
        print(f"Usuario:  #{usuario.id if usuario else '-'} {usuario.nombre_usuario if usuario else 'sin usuario'}")

        existente = (
            db.query(Venta)
            .join(DetalleVenta, DetalleVenta.venta_id == Venta.id)
            .filter(
                Venta.cliente_id == cliente.id,
                Venta.fecha == FECHA,
                Venta.total == TOTAL,
                Venta.moneda_id == moneda.id,
                DetalleVenta.producto_id == producto.id,
            )
            .first()
        )
        if existente:
            print(f"\n[SKIP] Ya existe la venta #{existente.id} para esa fecha/total/moneda.")
            return

        existente_tag = (
            db.query(Cotizacion)
            .filter(func.coalesce(Cotizacion.observaciones, "").like(f"%{TAG}%"))
            .first()
        )
        if existente_tag:
            print(f"\n[SKIP] Ya existe la cotizacion #{existente_tag.id} con la marca {TAG}.")
            return

        if not aplicar:
            print("\n[DRY-RUN] Nada escrito. Usa --aplicar para crear la cadena.")
            db.rollback()
            return

        uid = usuario.id if usuario else None

        cot = Cotizacion(
            cliente_id=cliente.id,
            fecha=FECHA,
            estado="APROBADA",
            total_estimado=TOTAL,
            moneda_id=moneda.id,
            tasa_cambio=Decimal("1"),
            total_en_moneda_base=None,
            observaciones=f"{TAG} · Nota de entrega 28/09/2026 · entregado, pendiente de cobro",
            creado_por_id=uid,
            actualizado_por_id=uid,
        )
        db.add(cot)
        db.flush()
        db.add(
            DetalleCotizacion(
                cotizacion_id=cot.id,
                producto_id=producto.id,
                tipo_item="REVENTA",
                cantidad=Decimal("1"),
                precio=TOTAL,
                descripcion_especifica=DESCRIPCION,
                observaciones="Nota de entrega 28/09/2026",
                costo_materiales=COSTO,
                costo_mano_obra=Decimal("0"),
                costo_gastos=Decimal("0"),
                costo_total=COSTO,
            )
        )

        pedido = Pedido(
            cotizacion_id=cot.id,
            cliente_id=cliente.id,
            fecha=FECHA,
            estado="ENTREGADO",
            observaciones=f"{TAG} · Entregado el 28/09/2026 · pendiente de cobro",
            fecha_entrega_estimada=FECHA,
            creado_por_id=uid,
            actualizado_por_id=uid,
        )
        db.add(pedido)
        db.flush()

        det_pedido = DetallePedido(
            pedido_id=pedido.id,
            producto_id=producto.id,
            tipo_item="REVENTA",
            cantidad=Decimal("1"),
            precio=TOTAL,
            descripcion_especifica=DESCRIPCION,
            observaciones="Nota de entrega 28/09/2026",
            costo_unitario=COSTO,
            porcentaje_ganancia=PCT_GANANCIA,
        )
        db.add(det_pedido)
        db.flush()

        venta = Venta(
            pedido_id=pedido.id,
            cliente_id=cliente.id,
            moneda_id=moneda.id,
            fecha=FECHA,
            total=TOTAL,
            estado="PENDIENTE",
            tasa_cambio=Decimal("1"),
            total_en_moneda_base=None,
            observaciones=(
                f"{TAG} · Nota de entrega 28/09/2026 · total USD {TOTAL} · "
                f"saldo pendiente USD {TOTAL}"
            ),
            creado_por_id=uid,
            actualizado_por_id=uid,
        )
        db.add(venta)
        db.flush()

        db.add(
            DetalleVenta(
                venta_id=venta.id,
                producto_id=producto.id,
                tipo_item="REVENTA",
                cantidad=Decimal("1"),
                precio=TOTAL,
                costo_unitario=COSTO,
                porcentaje_ganancia=PCT_GANANCIA,
                utilidad=UTILIDAD,
                descuento=Decimal("0"),
                descripcion_especifica=DESCRIPCION,
            )
        )

        envio = Envio(
            pedido_id=pedido.id,
            estado="ENTREGADO",
            fecha_salida=FECHA_HORA,
            fecha_entrega=FECHA_HORA,
            direccion_entrega="BOLIVAR",
            observaciones=f"{TAG} · Entregado segun nota de entrega del 28/09/2026",
            creado_por_id=uid,
            actualizado_por_id=uid,
            asignado_por_usuario_id=uid,
        )
        db.add(envio)
        db.flush()

        record_event(
            db,
            actor=usuario,
            action="CREATE",
            entity_type="venta",
            entity_id=venta.id,
            after={
                "origen": TAG,
                "cliente": cliente.nombre,
                "producto": producto.nombre,
                "total": float(TOTAL),
                "moneda": moneda.codigo,
                "estado": "PENDIENTE",
            },
        )

        db.commit()
        print(
            f"\n[OK] cotizacion #{cot.id} -> pedido #{pedido.id} -> "
            f"venta #{venta.id} -> envio #{envio.id} (ENTREGADO, saldo USD {TOTAL})"
        )
    finally:
        db.close()


if __name__ == "__main__":
    ap = argparse.ArgumentParser()
    ap.add_argument("--aplicar", action="store_true")
    main(aplicar=ap.parse_args().aplicar)
