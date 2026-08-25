"""
intelligent_router.py
=====================
Endpoints del COTIZADOR MANUAL (sin APIs de pago).

Prefix: /api/v1/intelligent-quotation

Flujo:
  1. GET  /contexto-exportar      → paquete de contexto (inventario + receta similar + prompt maestro)
  2. POST /import-structure       → estructura JSON que devolvió una IA de navegador → matcheo con inventario
  3. POST /recalculate-structure  → recalcular subtotales tras ediciones del vendedor
  4. POST /finalize-structure     → guardar como cotización o como producto

REGLA CENTRAL:
  La IA de navegador SOLO propone materiales y cantidades (JSON).
  El ERP calcula costos con precios VIGENTES del inventario, matchea
  materiales (fuzzy + sinónimos) y guarda. El vendedor tiene la última palabra.
"""

import datetime
import logging
from decimal import Decimal as D
from typing import Optional

from fastapi import APIRouter, Depends, HTTPException, Query, status
from sqlalchemy.orm import Session

from app.db.session import get_db
from app.core.redondeo import redondear_precio_cop
from app.modules.users.deps import require_module
from app.modules.quotes.atributos import FurnitureAttributes
from app.modules.quotes.intelligent_schemas import (
    ContextoExportarOut,
    FinalizeResponse,
    FinalizeStructureRequest,
    GenerateStructureOut,
    ImportStructureRequest,
    ImportTextoRequest,
    RecalculateStructureRequest,
)
from app.modules.productos.model import Producto, Material, ProductoMaterial, MuebleAtributos
from app.modules.quotes.model import Cotizacion, DetalleCotizacion, CotizacionDetalleMaterial, CotizacionAnalisisIA
from app.modules.quotes.structure_builder import build_cost_structure, recalculate_structure
from app.modules.quotes.contexto_exporter import generar_contexto
from app.modules.quotes.texto_excel_parser import parsear_texto_excel

logger = logging.getLogger(__name__)

router = APIRouter()


def _analisis_con_lock(db: Session, analisis_id: Optional[int]):
    """
    Idempotencia ante doble clic: si el análisis ya generó una cotización o
    un producto, devuelve ese registro para NO duplicarlo.
    En el Modo Manual analisis_id siempre llega vacío (conservado por compatibilidad).
    """
    if not analisis_id:
        return None, None, None
    analisis = db.query(CotizacionAnalisisIA).filter(
        CotizacionAnalisisIA.id == analisis_id
    ).with_for_update().first()
    if not analisis:
        return None, None, None
    cotizacion = None
    if analisis.cotizacion_id:
        cotizacion = db.query(Cotizacion).filter(Cotizacion.id == analisis.cotizacion_id).first()
    producto = None
    if analisis.producto_id:
        producto = db.query(Producto).filter(Producto.id == analisis.producto_id).first()
    return analisis, cotizacion, producto


# ---------------------------------------------------------------------------
# 1) Paquete de contexto para la IA de navegador
# ---------------------------------------------------------------------------

@router.get("/contexto-exportar", response_model=ContextoExportarOut, dependencies=[Depends(require_module('cotizaciones_ia'))])
def contexto_exportar(
    producto_base_id: Optional[int] = Query(None, description="Producto similar a usar como receta de referencia"),
    ancho: float = Query(1.60, description="Ancho del mueble en metros"),
    largo: float = Query(1.90, description="Largo del mueble en metros"),
    alto: Optional[float] = Query(None, description="Alto del mueble en metros"),
    con_foto: bool = Query(True, description="True si la IA analizará una foto, False si es solo descripción de texto"),
    descripcion: Optional[str] = Query(None, description="Descripción del mueble cuando es sin foto"),
    tipo_mueble: str = Query("otro", description="Tipo de mueble (cama, closet, sala...): ajusta anatomía y catálogo"),
    db: Session = Depends(get_db),
):
    """
    Genera el paquete de contexto (inventario + receta del producto
    similar + reglas de negocio + librería de prompts + esquema JSON)
    para pegarlo en una IA de navegador junto con la foto del mueble
    (o la descripción).
    """
    return generar_contexto(
        db,
        producto_base_id=producto_base_id,
        ancho=ancho,
        largo=largo,
        alto=alto,
        con_foto=con_foto,
        descripcion=descripcion,
        tipo_mueble=tipo_mueble,
    )


# ---------------------------------------------------------------------------
# 2) Importar la estructura JSON pegada
# ---------------------------------------------------------------------------

@router.post("/import-structure", response_model=GenerateStructureOut, dependencies=[Depends(require_module('cotizaciones_ia'))])
def import_structure(payload: ImportStructureRequest, db: Session = Depends(get_db)):
    """
    Importa la estructura JSON que devolvió una IA de navegador, la fusiona
    con la receta del producto base (si se indicó) y la matchea contra el
    inventario. No realiza ninguna llamada externa.
    """
    attrs = FurnitureAttributes(
        tipo_mueble=payload.tipo_mueble,
        nivel_confianza=1.0,
        estructura_propuesta=payload.estructura_propuesta,
    )
    if not payload.estructura_propuesta:
        # Vacío → vacío: sin estructura pegada no se arrastra receta histórica.
        return {
            "producto_base_id": None,
            "producto_base_nombre": None,
            "score_similitud": 0.0,
            "secciones": [],
            "materiales_sin_precio": 0,
            "resumen": {
                "costo_materiales": 0.0, "costo_mano_obra": 0.0, "costo_gastos": 0.0,
                "costo_produccion": 0.0, "impuesto_porcentaje": payload.impuesto_porcentaje,
                "impuestos": 0.0, "base_con_impuestos": 0.0,
                "ganancia_porcentaje": payload.ganancia_porcentaje,
                "precio_sin_iva": 0.0, "iva_porcentaje": payload.iva_porcentaje,
                "precio_con_iva": 0.0,
            },
        }
    try:
        return build_cost_structure(
            db=db,
            attrs=attrs,
            estructura_ia=payload.estructura_propuesta,
            nuevo_ancho=payload.nuevo_ancho,
            nuevo_largo=payload.nuevo_largo,
            nuevo_alto=payload.nuevo_alto,
            nuevo_fondo=payload.nuevo_fondo,
            respuestas={},
            dimensiones_referencia=payload.dimensiones_referencia,
            ganancia_porcentaje=payload.ganancia_porcentaje,
            iva_porcentaje=payload.iva_porcentaje,
            impuesto_porcentaje=payload.impuesto_porcentaje,
            pct_mano_obra=payload.pct_mano_obra,
            pct_gastos=payload.pct_gastos,
            top_n_similar=3,
            producto_base_id=payload.producto_base_id,
        )
    except ValueError as e:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(e))
    except Exception as e:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Error al importar la estructura: {e}"
        )


# ---------------------------------------------------------------------------
# 2b) Importar la respuesta de la IA en FORMATO EXCEL (tabla por secciones)
# ---------------------------------------------------------------------------

@router.post("/import-texto", response_model=GenerateStructureOut, dependencies=[Depends(require_module('cotizaciones_ia'))])
def import_texto(payload: ImportTextoRequest, db: Session = Depends(get_db)):
    """
    Importa la respuesta de la IA en formato Excel (MATERIAL | CANTIDAD |
    UNIDAD | V/UNIT | PRECIO TOTAL, por secciones). El sistema la convierte
    al JSON interno y la fusiona con la receta base + inventario.
    """
    estructura = parsear_texto_excel(payload.texto)
    if not estructura:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="No se pudo interpretar la respuesta. Copia la tabla completa que devolvió la IA "
                   "(con las secciones y las columnas MATERIAL | CANTIDAD | UNIDAD)."
        )
    attrs = FurnitureAttributes(
        tipo_mueble=payload.tipo_mueble,
        nivel_confianza=1.0,
        estructura_propuesta=estructura,
    )
    try:
        return build_cost_structure(
            db=db,
            attrs=attrs,
            estructura_ia=estructura,
            nuevo_ancho=payload.nuevo_ancho,
            nuevo_largo=payload.nuevo_largo,
            nuevo_alto=payload.nuevo_alto,
            nuevo_fondo=payload.nuevo_fondo,
            respuestas={},
            dimensiones_referencia=payload.dimensiones_referencia,
            ganancia_porcentaje=payload.ganancia_porcentaje,
            iva_porcentaje=payload.iva_porcentaje,
            impuesto_porcentaje=payload.impuesto_porcentaje,
            pct_mano_obra=payload.pct_mano_obra,
            pct_gastos=payload.pct_gastos,
            top_n_similar=3,
            producto_base_id=payload.producto_base_id,
        )
    except ValueError as e:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(e))
    except Exception as e:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Error al importar la estructura: {e}"
        )


# ---------------------------------------------------------------------------
# 3) Recalcular la estructura editada
# ---------------------------------------------------------------------------

@router.post("/recalculate-structure", response_model=GenerateStructureOut, dependencies=[Depends(require_module('cotizaciones_ia'))])
def recalculate_structure_endpoint(payload: RecalculateStructureRequest, db: Session = Depends(get_db)):
    """
    Recalcula subtotales, totales y desgloses de la estructura de costos editada.
    Los precios SIEMPRE vienen del inventario actual (Material.costo_base).
    """
    secciones_dict = [sec.model_dump() for sec in payload.secciones]
    try:
        return recalculate_structure(
            db=db,
            secciones_editadas=secciones_dict,
            ganancia_porcentaje=payload.ganancia_porcentaje,
            iva_porcentaje=payload.iva_porcentaje,
            impuesto_porcentaje=payload.impuesto_porcentaje,
            pct_mano_obra=payload.pct_mano_obra,
            pct_gastos=payload.pct_gastos,
        )
    except Exception as e:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Error al recalcular la estructura de costos: {e}"
        )


# ---------------------------------------------------------------------------
# 4) Finalizar: guardar como cotización o como producto
# ---------------------------------------------------------------------------

@router.post("/finalize-structure", response_model=FinalizeResponse, dependencies=[Depends(require_module('cotizaciones_ia'))])
def finalize_structure(payload: FinalizeStructureRequest, db: Session = Depends(get_db)):
    """
    Guarda la cotización terminada (guardar_como="cotizacion") o la registra
    como un Producto nuevo con su receta (guardar_como="producto").
    """
    if not payload.secciones:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="La estructura de costos está vacía."
        )

    # 1. Calcular total real con precios VIGENTES del inventario
    total_materiales = D("0")
    for sec in payload.secciones:
        for item in sec.items:
            if not item.activo:
                continue
            costo_unit = D(str(item.costo_unitario))
            if item.material_id:
                mat = db.query(Material).filter(Material.id == item.material_id).first()
                if mat:
                    costo_unit = D(str(mat.costo_base))
            total_materiales += D(str(item.cantidad)) * costo_unit

    pct_mo = D(str(payload.pct_mano_obra)) / D("100")
    pct_g = D(str(payload.pct_gastos)) / D("100")
    costo_mo = total_materiales * pct_mo
    costo_g = total_materiales * pct_g
    costo_prod = total_materiales + costo_mo + costo_g
    # a = costo_producción × (1 + impuesto%); b = a × (1 + ganancia%)
    monto_imp = costo_prod * D(str(payload.impuesto_porcentaje)) / D("100")
    base_imp = costo_prod + monto_imp
    precio_sin_iva = base_imp * (D("1") + D(str(payload.ganancia_porcentaje)) / D("100"))
    precio_con_iva = precio_sin_iva * (D("1") + D(str(payload.iva_porcentaje)) / D("100"))

    if payload.guardar_como == "producto":
        if not payload.nombre_producto:
            raise HTTPException(status_code=400, detail="El nombre del producto es requerido para guardar como Producto.")
        if not payload.tipo_producto_id:
            raise HTTPException(status_code=400, detail="El tipo de producto es requerido para guardar como Producto.")

        analisis, _, producto_existente = _analisis_con_lock(db, payload.analisis_id)
        if producto_existente:
            return FinalizeResponse(
                cotizacion_id=0,
                total_estimado=float(producto_existente.precio_venta_con_iva or producto_existente.precio_venta_base or 0),
                pdf_url="/productos",
                mensaje="El producto ya fue guardado a partir de este análisis. Se devuelve el existente.",
            )

        nuevo_prod = Producto(
            nombre=payload.nombre_producto,
            tipo_producto_id=payload.tipo_producto_id,
            ancho_base=D(str(payload.nuevo_ancho)),
            largo_base=D(str(payload.nuevo_largo)),
            alto_base=D(str(payload.nuevo_alto)) if payload.nuevo_alto else None,
            precio_costo_base=costo_prod,
            precio_venta_base=redondear_precio_cop(precio_sin_iva, "ceil"),
            precio_venta_con_iva=redondear_precio_cop(precio_con_iva, "ceil"),
            descripcion=payload.observaciones or f"Creado desde Cotizador Inteligente el {datetime.date.today()}",
            activo=True,
        )
        db.add(nuevo_prod)
        db.flush()

        for sec in payload.secciones:
            for item in sec.items:
                if not item.activo or not item.material_id:
                    continue
                db.add(ProductoMaterial(
                    producto_id=nuevo_prod.id,
                    material_id=item.material_id,
                    cantidad_base=D(str(item.cantidad)),
                    tipo_escala="FIJO",
                    observaciones=f"Sección: {sec.seccion}. Razón: {item.razon}",
                ))

        # Vector de similitud para futuros "muebles similares"
        v_tap = 1.0 if any("TELA" in it.nombre.upper() for s in payload.secciones for it in s.items if it.activo) else 0.0
        v_luz = 1.0 if any("LED" in it.nombre.upper() for s in payload.secciones for it in s.items if it.activo) else 0.0

        tipo_m = "otro"
        from app.modules.catalogos.model import TipoProducto as TPMod
        tp = db.query(TPMod).filter(TPMod.id == payload.tipo_producto_id).first()
        if tp:
            tipo_m_lower = tp.nombre.lower()
            if "cama" in tipo_m_lower:
                tipo_m = "cama"
            elif "closet" in tipo_m_lower or "armario" in tipo_m_lower:
                tipo_m = "closet"
            elif "comedor" in tipo_m_lower:
                tipo_m = "comedor"
            elif "sala" in tipo_m_lower:
                tipo_m = "sala"
            elif "nochero" in tipo_m_lower:
                tipo_m = "nochero"
            elif "tv" in tipo_m_lower or "rack" in tipo_m_lower:
                tipo_m = "rack_tv"

        vector_base = [v_tap, v_luz, 0.0, 0.0, 0.5, 0.0, 0.4, 0.0]
        if payload.producto_base_id:
            ma_base = db.query(MuebleAtributos).filter(MuebleAtributos.producto_id == payload.producto_base_id).first()
            if ma_base and ma_base.vector_similitud:
                vector_base = ma_base.vector_similitud

        db.add(MuebleAtributos(
            producto_id=nuevo_prod.id,
            tipo_mueble=tipo_m,
            tiene_tapiceria=v_tap > 0,
            tiene_luces=v_luz > 0,
            atributos_extra={"es_opcional": False},
            vector_similitud=vector_base,
        ))
        db.commit()

        if analisis:
            analisis.producto_id = nuevo_prod.id
            db.commit()

        return FinalizeResponse(
            cotizacion_id=0,
            total_estimado=float(precio_con_iva),
            pdf_url="/productos",
            mensaje=f"Producto '{nuevo_prod.nombre}' y su receta guardados exitosamente.",
        )

    # ── Guardar como Cotización ──
    if not payload.cliente_id:
        raise HTTPException(status_code=400, detail="El cliente es requerido para guardar como Cotización.")

    analisis, cotizacion_existente, _ = _analisis_con_lock(db, payload.analisis_id)
    if cotizacion_existente:
        return FinalizeResponse(
            cotizacion_id=cotizacion_existente.id,
            total_estimado=float(cotizacion_existente.total_estimado or 0),
            pdf_url=f"/api/v1/cotizacion/{cotizacion_existente.id}/imprimir",
            mensaje="La cotización ya fue guardada a partir de este análisis. Se devuelve la existente.",
        )

    cotizacion = Cotizacion(
        cliente_id=payload.cliente_id,
        fecha=datetime.date.today(),
        estado="BORRADOR",
        total_estimado=precio_con_iva,
        observaciones=payload.observaciones or "Generada con estructura de costos editable.",
    )
    db.add(cotizacion)
    db.flush()

    detalle = DetalleCotizacion(
        cotizacion_id=cotizacion.id,
        producto_id=payload.producto_base_id or 1,
        cantidad=D("1"),
        precio=precio_con_iva,
        ancho=D(str(payload.nuevo_ancho)),
        largo=D(str(payload.nuevo_largo)),
        alto=D(str(payload.nuevo_alto)) if payload.nuevo_alto else None,
        observaciones="Estructura personalizada",
        costo_materiales=total_materiales,
        costo_mano_obra=costo_mo,
        costo_gastos=costo_g,
        costo_total=costo_prod,
    )
    db.add(detalle)
    db.flush()

    for sec in payload.secciones:
        for item in sec.items:
            if not item.material_id:
                continue
            db.add(CotizacionDetalleMaterial(
                detalle_cotizacion_id=detalle.id,
                material_id=item.material_id,
                cantidad_base=D(str(item.cantidad)),
                cantidad_calculada=D(str(item.cantidad)),
                tipo_escala="FIJO",
                activo=item.activo,
                observaciones=f"Sección: {sec.seccion}. Razón: {item.razon}",
            ))

    if analisis:
        analisis.cotizacion_id = cotizacion.id

    db.commit()

    return FinalizeResponse(
        cotizacion_id=cotizacion.id,
        total_estimado=float(precio_con_iva),
        pdf_url=f"/api/v1/cotizacion/{cotizacion.id}/imprimir",
        mensaje="Cotización finalizada y guardada exitosamente con estructura de costos.",
    )
