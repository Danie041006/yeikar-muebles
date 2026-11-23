"""Casos contables: el dinero solo entra una vez; el crédito conserva su moneda."""
from decimal import Decimal
from uuid import uuid4

import pytest
from fastapi import HTTPException

from app.modules.sales import service, saldos_service
from app.modules.sales.cobros import resumen_cobro
from app.modules.sales.model import Pago, SaldoFavor
from app.modules.sales.schemas import PagoCreate, PagoUpdate
from app.modules.sales.saldos_schemas import AplicarSaldoCreate
from app.modules.reports.model import MovimientoCaja


def cobrar(db, venta, monto=8000, **campos):
    return service.crear_pago(db, PagoCreate(
        venta_id=venta.id, moneda_id=venta.moneda_id, monto=monto,
        metodo_pago="USD_QA" if venta.moneda_id == 2 else "COP_QA",
        **campos,
    ))


def excedente(db, negocio):
    venta = negocio[2]()
    pago = cobrar(db, venta, confirmar_excedente=True, saldo_confirmado=7546)
    return venta, pago, pago.credito_generado


def aplicar(db, venta, credito, monto=454, **campos):
    return saldos_service.aplicar_saldo(db, AplicarSaldoCreate(
        venta_id=venta.id, saldo_favor_id=credito.id, monto=monto,
        operacion_id=campos.pop("operacion_id", uuid4()), **campos,
    ))


def test_exceso_sin_confirmar_no_escribe(db, negocio):
    venta = negocio[2]()
    with pytest.raises(HTTPException) as error:
        cobrar(db, venta)
    assert error.value.status_code == 409
    assert error.value.detail["saldo_favor"] == "454.00"
    assert db.query(Pago).count() == db.query(MovimientoCaja).count() == db.query(SaldoFavor).count() == 0


def test_8000_caja_7546_aplicado_454_credito(db, negocio):
    venta, pago, credito = excedente(db, negocio)
    assert venta.estado == "PAGADA"
    assert resumen_cobro(venta) == (7546, 0, 0)
    assert pago.monto == Decimal("8000")
    assert credito.moneda_id == 2
    assert credito.saldo == Decimal("454")
    assert db.query(MovimientoCaja).one().monto == Decimal("8000")


def test_credito_usado_no_genera_caja_y_reversion_lo_restituye(db, negocio):
    _, _, credito = excedente(db, negocio)
    venta = negocio[2](1000)
    pago = aplicar(db, venta, credito)
    assert resumen_cobro(venta) == (454, 0, 546)
    assert db.query(MovimientoCaja).count() == 1
    db.refresh(credito)
    assert credito.saldo == 0
    service.eliminar_pago(db, pago.id)
    db.refresh(credito)
    assert credito.saldo == Decimal("454")
    assert resumen_cobro(venta) == (0, 0, 1000)
    assert db.query(MovimientoCaja).count() == 1


def test_cero_de_mas_se_corrige_en_caja_factura_y_credito(db, negocio):
    venta, pago, credito = excedente(db, negocio)
    service.actualizar_pago(db, pago.id, PagoUpdate(monto=800, motivo_correccion="Cero de más"))
    db.refresh(credito)
    assert credito.saldo == 0 and credito.anulado
    assert resumen_cobro(venta) == (800, 0, 6746)
    assert venta.estado == "ABONADA"
    assert db.query(MovimientoCaja).one().monto == Decimal("800")
    assert len(pago.correcciones) == 1


def test_correccion_credito_exige_motivo(db, negocio):
    _, pago, _ = excedente(db, negocio)
    with pytest.raises(ValueError, match="motivo"):
        service.actualizar_pago(db, pago.id, PagoUpdate(monto=800))


def test_credito_usado_bloquea_correccion_y_borrado_de_origen(db, negocio):
    _, origen, credito = excedente(db, negocio)
    venta = negocio[2](1000)
    aplicar(db, venta, credito, monto=100)
    for accion in (
        lambda: service.eliminar_pago(db, origen.id),
        lambda: service.actualizar_pago(db, origen.id, PagoUpdate(monto=7546, motivo_correccion="Error")),
    ):
        with pytest.raises(HTTPException) as error:
            accion()
        assert error.value.status_code == 409
        assert str(venta.id) in error.value.detail
    assert db.query(MovimientoCaja).one().monto == Decimal("8000")


def test_anular_origen_no_usado_retira_caja_y_credito(db, negocio):
    venta, pago, credito = excedente(db, negocio)
    service.eliminar_pago(db, pago.id)
    db.refresh(credito)
    assert credito.anulado and credito.saldo == 0
    assert resumen_cobro(venta) == (0, 0, 7546)
    assert db.query(MovimientoCaja).count() == 0


def test_otra_moneda_exige_tasa_manual_y_no_crea_caja(db, negocio):
    _, _, credito = excedente(db, negocio)
    venta = negocio[2](2000000, moneda_id=1)
    with pytest.raises(ValueError, match="manual"):
        aplicar(db, venta, credito)
    pago = aplicar(db, venta, credito, tasa_cambio=3500)
    assert pago.monto_aplicado == Decimal("1589000")
    assert resumen_cobro(venta) == (1589000, 0, 411000)
    assert db.query(MovimientoCaja).count() == 1


def test_credito_no_se_puede_gastar_dos_veces(db, negocio):
    _, _, credito = excedente(db, negocio)
    aplicar(db, negocio[2](1000), credito)
    with pytest.raises(HTTPException):
        aplicar(db, negocio[2](1000), credito, monto=1)


def test_no_se_puede_aplicar_a_otro_cliente(db, negocio):
    from app.modules.clients.model import Client
    _, _, credito = excedente(db, negocio)
    otro = Client(nombre="Otro cliente", telefono="555")
    db.add(otro)
    db.flush()
    venta = negocio[2](1000)
    venta.cliente_id = otro.id
    db.flush()
    with pytest.raises(ValueError, match="otro cliente"):
        aplicar(db, venta, credito)


def test_reintento_cobro_y_aplicacion_son_idempotentes(db, negocio):
    venta = negocio[2]()
    operacion = uuid4()
    pago = cobrar(db, venta, confirmar_excedente=True, saldo_confirmado=7546, operacion_id=operacion)
    assert cobrar(db, venta, confirmar_excedente=True, saldo_confirmado=7546, operacion_id=operacion).id == pago.id
    segunda = negocio[2](1000)
    op_aplicar = uuid4()
    aplicado = aplicar(db, segunda, pago.credito_generado, operacion_id=op_aplicar)
    assert aplicar(db, segunda, pago.credito_generado, operacion_id=op_aplicar).id == aplicado.id
    assert db.query(MovimientoCaja).count() == 1


def test_confirmacion_vencida_requiere_revisar_desglose(db, negocio):
    venta = negocio[2]()
    cobrar(db, venta, monto=100)
    with pytest.raises(HTTPException) as error:
        cobrar(db, venta, confirmar_excedente=True, saldo_confirmado=7546)
    assert error.value.status_code == 409
    assert error.value.detail["saldo_confirmado"] == "7446.00"


def test_permiso_ventas_sin_cuentas_permite_todo_el_flujo(client, db, negocio):
    venta = negocio[2]()
    payload = {"venta_id": venta.id, "moneda_id": 2, "metodo_pago": "USD_QA", "monto": 8000}
    assert client.post("/api/v1/pago/", json=payload).status_code == 409
    vista = client.post("/api/v1/pago/previsualizar", json=payload)
    assert vista.status_code == 200, vista.text
    respuesta = client.post("/api/v1/pago/", json={**payload, "confirmar_excedente": True, "saldo_confirmado": 7546})
    assert respuesta.status_code == 201, respuesta.text
    creditos = client.get(f"/api/v1/saldo-favor/?cliente_id={negocio[0].id}")
    assert creditos.status_code == 200, creditos.text
    assert Decimal(creditos.json()[0]["saldo"]) == 454
    assert client.get(f"/api/v1/venta/{venta.id}").json()["saldo_pendiente"] == 0
    assert client.delete(f"/api/v1/pago/{respuesta.json()['id']}").status_code == 204


def test_pago_historico_sin_monto_aplicado_sigue_cuadrando(db, negocio):
    venta = negocio[2]()
    db.add(Pago(venta_id=venta.id, moneda_id=2, monto=1000, monto_en_moneda_base=1000,
                metodo_pago="USD_QA", fecha=venta.fecha))
    db.flush()
    assert resumen_cobro(venta) == (1000, 0, 6546)


def test_descuento_y_credito_restan_juntos_sin_negativos(db, negocio):
    from app.modules.sales.model import DescuentoVenta
    _, _, credito = excedente(db, negocio)
    venta = negocio[2](1000)
    db.add(DescuentoVenta(venta_id=venta.id, moneda_id=2, monto=100, monto_en_moneda_base=100,
                          fecha=venta.fecha))
    db.flush()
    aplicar(db, venta, credito)
    assert resumen_cobro(venta) == (454, 100, 446)


def test_aplicar_credito_que_cubre_la_venta_la_deja_pagada(db, negocio):
    _, _, credito = excedente(db, negocio)
    venta = negocio[2](454)
    aplicar(db, venta, credito)
    assert venta.estado == "PAGADA"
    assert resumen_cobro(venta) == (454, 0, 0)


def test_abono_de_conversion_mayor_exige_confirmacion(db, negocio):
    _, usuario, fabricar = negocio
    venta = fabricar(1000)
    abonos = [PagoCreate(venta_id=venta.id, moneda_id=2, monto=1200, metodo_pago="USD_QA")]
    with pytest.raises(HTTPException) as error:
        saldos_service.confirmar_abonos_conversion(db, venta, abonos, saldos_service.ConfirmacionConversion(False, None))
    assert error.value.status_code == 409
    assert error.value.detail["excedentes"] == [{"monto": "200.00", "moneda": "USD"}]
    saldos_service.confirmar_abonos_conversion(db, venta, abonos, saldos_service.ConfirmacionConversion(True, Decimal("1000")))
    for abono in abonos:
        abono.confirmar_excedente = True
        abono.saldo_confirmado = 1000
        service.crear_pago(db, abono, usuario=usuario)
    assert venta.estado == "PAGADA"
    assert db.query(SaldoFavor).one().saldo == Decimal("200")


def test_no_se_puede_aplicar_mas_que_el_pendiente(db, negocio):
    _, _, credito = excedente(db, negocio)
    with pytest.raises(ValueError, match="pendiente"):
        aplicar(db, negocio[2](300), credito)


def test_aplicacion_no_puede_ser_anterior_al_cobro(db, negocio):
    from datetime import timedelta
    _, origen, credito = excedente(db, negocio)
    with pytest.raises(ValueError, match="antes"):
        aplicar(db, negocio[2](1000), credito, fecha=origen.fecha - timedelta(days=1))


def test_cobros_agregados_usan_lo_aplicado_no_lo_recibido(db, negocio):
    venta = negocio[2]()
    cobrar(db, venta, confirmar_excedente=True, saldo_confirmado=7546)
    pagos, _ = service._cobros_base_por_venta(db, [venta.id])
    assert Decimal(str(pagos[venta.id])) == Decimal("7546")


def _cotizacion_a_medida(db, negocio, precio=7546):
    from datetime import date
    from app.modules.quotes.model import Cotizacion, DetalleCotizacion

    cliente, usuario, _ = negocio
    cot = Cotizacion(cliente_id=cliente.id, fecha=date.today(), estado="APROBADA",
                     moneda_id=2, total_estimado=precio, tasa_cambio=4000, creado_por_id=usuario.id)
    db.add(cot)
    db.flush()
    db.add(DetalleCotizacion(cotizacion_id=cot.id, tipo_item="FABRICADO", cantidad=1, precio=precio,
                             producto_id=None, material_id=None, descripcion_especifica="Comedor a medida"))
    db.flush()
    return cot


def _abono_excedente():
    from datetime import date
    return [{"metodo_pago": "USD_QA", "moneda_id": 2, "monto": 8000, "fecha": date.today()}]


def _detalle(precio=7546):
    return [{"tipo_item": "FABRICADO", "cantidad": 1, "precio": precio,
             "descripcion_especifica": "Comedor a medida"}]


def test_conversion_con_abono_mayor_pide_confirmacion_sin_escribir_caja(db, negocio):
    from app.modules.orders.service import convertir_cotizacion_a_pedido

    cot = _cotizacion_a_medida(db, negocio)
    with pytest.raises(HTTPException) as error:
        convertir_cotizacion_a_pedido(db, cot.id, None, _detalle(), adelantos=_abono_excedente(),
                                      usuario=negocio[1])
    assert error.value.status_code == 409
    assert error.value.detail["excedentes"] == [{"monto": "454.00", "moneda": "USD"}]
    assert db.query(MovimientoCaja).count() == 0


def test_conversion_confirmada_deja_454_a_favor_y_caja_real(db, negocio):
    from app.modules.orders.service import convertir_cotizacion_a_pedido

    cot = _cotizacion_a_medida(db, negocio)
    pedido = convertir_cotizacion_a_pedido(db, cot.id, None, _detalle(), adelantos=_abono_excedente(),
                                           confirmar_excedente=True, total_confirmado=7546, usuario=negocio[1])
    from app.modules.sales.model import Venta
    venta = db.query(Venta).filter(Venta.pedido_id == pedido.id).one()
    assert venta.estado == "PAGADA"
    assert resumen_cobro(venta) == (7546, 0, 0)
    assert db.query(MovimientoCaja).one().monto == Decimal("8000")
    assert db.query(SaldoFavor).one().saldo == Decimal("454")


def test_aplicar_por_http_no_mueve_caja(client, db, negocio):
    venta = negocio[2]()
    cobro = client.post("/api/v1/pago/", json={
        "venta_id": venta.id, "moneda_id": 2, "metodo_pago": "USD_QA", "monto": 8000,
        "confirmar_excedente": True, "saldo_confirmado": 7546,
    })
    assert cobro.status_code == 201, cobro.text
    assert Decimal(cobro.json()["saldo_favor_generado"]) == Decimal("454.00")
    credito = client.get(f"/api/v1/saldo-favor/?cliente_id={negocio[0].id}").json()[0]

    segunda = negocio[2](1000)
    aplicacion = client.post("/api/v1/saldo-favor/aplicar", json={
        "venta_id": segunda.id, "saldo_favor_id": credito["id"], "monto": 454,
        "operacion_id": str(uuid4()),
    })
    assert aplicacion.status_code == 201, aplicacion.text
    assert aplicacion.json()["tipo"] == "SALDO_FAVOR"
    assert aplicacion.json()["metodo_pago"] == "SALDO_FAVOR"
    assert db.query(MovimientoCaja).count() == 1
    assert client.get(f"/api/v1/venta/{segunda.id}").json()["saldo_pendiente"] == 546
