"""TRM contable de cotizaciones: nunca bloquea el guardado y solo se le pide
al usuario cuando hay conversión real (renglones en otra moneda). Una
cotización en la misma moneda de sus productos (USD+USD) guarda sin preguntar.

Cadena del backend: tasa indicada → TRM registrada → última usada → 1.0."""
from datetime import date

from app.modules.tasas_cambio.model import TasaCambio
from conftest import crear_cotizacion, crear_cliente, crear_producto


def test_cotizacion_usd_sin_trm_guarda_ok(client, db, cleaner):
    """Cotización en USD con tasa default 1.0: el guardado NO se bloquea por
    falta de TRM (antes: error 'Indica la TRM...')."""
    cliente = crear_cliente(client, cleaner)
    prod = crear_producto(client, cleaner)
    cot = crear_cotizacion(
        client, cleaner, cliente["id"], prod["id"], 100.0, moneda_id=2, tasa_cambio=1.0,
    )
    assert cot["moneda_id"] == 2
    assert float(cot["tasa_cambio"]) > 0  # tasa resuelta, no rechazada


def test_trm_registrada_manda_para_valor_contable(client, db, cleaner):
    """Con una TRM registrada hoy (USD→COP), una cotización USD guardada sin
    tasa hereda la registrada como valor contable."""
    # Limpiar tasas USD de hoy en la BD de pruebas y registrar la del test
    db.query(TasaCambio).filter(
        TasaCambio.moneda_origen_id == 2, TasaCambio.fecha == date.today(),
    ).delete()
    db.commit()
    tasa = TasaCambio(
        moneda_origen_id=2, moneda_destino_id=1, valor=4200.0, fecha=date.today(),
    )
    db.add(tasa)
    db.commit()
    db.refresh(tasa)
    cleaner.registrar("tasa_cambio", tasa.id)

    cliente = crear_cliente(client, cleaner)
    prod = crear_producto(client, cleaner)
    cot = crear_cotizacion(
        client, cleaner, cliente["id"], prod["id"], 100.0, moneda_id=2, tasa_cambio=1.0,
    )
    assert abs(float(cot["tasa_cambio"]) - 4200.0) < 0.001
