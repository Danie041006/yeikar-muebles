"""
Regresión: los nombres de productos del Informe Mensual (pendientes de pago)
nunca deben emitir 'None' ni quedar '—' cuando la información existe.

Cubre dos fallos reales vistos en producción:
  1. Muebles a medida (producto_id/material_id NULL): el nombre vive en
     detalle.descripcion_especifica (o cotización.observaciones) y el código
     antiguo imprimía 'Material #None x1.00'.
  2. Pedidos históricos sin detalle_pedido (solo cotización): el código
     antiguo mostraba '—' aunque la cotización tuviera los ítems.
"""
import pytest

from app.modules.orders.model import DetallePedido
from app.modules.quotes.model import DetalleCotizacion
from app.modules.reports.service import (
    _nombre_detalle,
    _texto_productos,
    _primer_texto_productos,
)


def _det_pedido(descripcion=None, producto_id=None, material_id=None, cantidad=1, tipo_item="FABRICADO"):
    return DetallePedido(
        id=1, producto_id=producto_id, material_id=material_id,
        tipo_item=tipo_item, cantidad=cantidad, precio=100,
        descripcion_especifica=descripcion,
    )


def _det_cotizacion(observaciones=None, cantidad=1):
    return DetalleCotizacion(
        id=1, producto_id=None, material_id=None,
        tipo_item="FABRICADO", cantidad=cantidad, precio=100,
        observaciones=observaciones,
    )


class TestNombreDetalle:
    def test_personalizado_con_descripcion(self):
        d = _det_pedido(descripcion="CAMA NUBES 2X2")
        assert _nombre_detalle(d) == "CAMA NUBES 2X2"

    def test_personalizado_sin_descripcion_no_interpola_none(self):
        d = _det_pedido()
        assert _nombre_detalle(d) is None

    def test_cotizacion_con_observaciones(self):
        dc = _det_cotizacion(observaciones="CONGELADOR MABE 200L")
        assert _nombre_detalle(dc) == "CONGELADOR MABE 200L"

    def test_prefiere_producto_sobre_descripcion(self):
        d = _det_pedido(descripcion="desc")
        d.producto = type("P", (), {"nombre": "CAMA CATÁLOGO"})()
        assert _nombre_detalle(d) == "CAMA CATÁLOGO"

    def test_prefiere_material_sobre_descripcion(self):
        d = _det_pedido(descripcion="desc")
        d.material = type("M", (), {"nombre": "MADERA APAMATE"})()
        assert _nombre_detalle(d) == "MADERA APAMATE"

    def test_id_numerico_como_ultimo_recurso(self):
        d = _det_pedido(descripcion=None, material_id=7)
        assert _nombre_detalle(d) == "Material #7"


class TestTextoProductos:
    def test_personalizado_muestra_descripcion(self):
        d = _det_pedido(descripcion="CAMA NUBES", cantidad=2)
        assert _texto_productos([d]) == "CAMA NUBES x2"

    def test_anonimo_falla_a_etiqueta_limpia(self):
        assert _texto_productos([_det_pedido()]) == "Ítem a medida x1"

    def test_vacio_devuelve_guion(self):
        assert _texto_productos([]) == "—"

    def test_nunca_emite_none(self):
        texto = _texto_productos([_det_pedido()])
        assert "None" not in texto


class TestPrimerTextoProductos:
    def test_fallback_a_cotizacion_cuando_no_hay_pedido(self):
        dc = _det_cotizacion(observaciones="AIRE SPLIT 12000 BTU")
        assert _primer_texto_productos([], [], [dc]) == "AIRE SPLIT 12000 BTU x1"

    def test_todo_vacio_devuelve_guion(self):
        assert _primer_texto_productos([], [], []) == "—"

    def test_prefiere_primera_fuente_con_nombre(self):
        anonimo = _det_pedido()          # sin descripción
        con_nombre = _det_pedido(descripcion="SOMIER 1.40")
        assert _primer_texto_productos([anonimo], [con_nombre], []) == "SOMIER 1.40 x1"

    def test_fuente_con_nombre_gana_a_cotizacion(self):
        con_nombre = _det_pedido(descripcion="SOMIER 1.40")
        dc = _det_cotizacion(observaciones="SOMIER DE CATÁLOGO")
        assert _primer_texto_productos([con_nombre], [], [dc]) == "SOMIER 1.40 x1"