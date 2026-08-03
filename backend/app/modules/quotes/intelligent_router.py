"""
intelligent_router.py
=====================
Endpoints del Motor de Cotización Inteligente (IQE) de YEIKAR.

Prefix: /api/v1/intelligent-quotation

Endpoints:
  POST /analyze-image    → Extrae atributos visuales del mueble
  POST /find-similar     → Busca Top N estructuras históricas similares
  POST /create-draft     → Genera borrador editable con precios del inventario
  POST /recalculate      → Recalcula costos con cambios del vendedor
  GET  /health           → Verifica que el módulo está activo

REGLA CENTRAL:
  La IA solo devuelve atributos visuales.
  El ERP calcula todo lo demás.
  El vendedor tiene la última palabra.
"""

import os
from decimal import Decimal
from typing import Optional

from fastapi import APIRouter, Depends, File, Form, HTTPException, UploadFile, status
from sqlalchemy.orm import Session

from app.db.session import get_db
from app.modules.users.deps import require_module
from app.modules.quotes.vision_provider import FurnitureAttributes
import datetime
from app.modules.quotes.similarity_engine import buscar_similares
from app.modules.quotes.intelligent_schemas import (
    CreateDraftRequest,
    DraftOut,
    FindSimilarRequest,
    FindSimilarResponse,
    FurnitureAttributesOut,
    MaterialLineaOut,
    RecalculateRequest,
    SimilarityResultOut,
    FinalizeRequest,
    FinalizeResponse,
    GenerateStructureRequest,
    GenerateStructureOut,
    RecalculateStructureRequest,
    FinalizeStructureRequest,
)
from app.modules.productos.cost_service import calcular_costo_producto
from app.modules.productos.model import Producto, Material, ProductoMaterial, MuebleAtributos
from app.modules.quotes.model import Cotizacion, DetalleCotizacion, CotizacionDetalleMaterial, CotizacionAnalisisIA
from app.modules.quotes.structure_builder import build_cost_structure, recalculate_structure

router = APIRouter()

# Umbral mínimo de confianza de la IA para no pedir revisión humana
CONFIANZA_MINIMA = float(os.getenv("IQE_CONFIANZA_MINIMA", "0.70"))


def _get_vision_provider():
    """
    Factory del VisionProvider. Lee la variable IQE_VISION_PROVIDER del .env
    para decidir qué proveedor usar. Así se intercambia en una sola línea.
    """
    provider_name = os.getenv("IQE_VISION_PROVIDER", "gpt").lower()
    if provider_name == "gpt":
        from app.modules.quotes.gpt_vision_provider import GPTVisionProvider
        return GPTVisionProvider()
    elif provider_name == "gemini":
        # Placeholder para el futuro proveedor de Gemini
        raise NotImplementedError("GeminiVisionProvider aún no está implementado.")
    else:
        raise ValueError(f"Proveedor de visión desconocido: {provider_name}")


# ---------------------------------------------------------------------------
# GET /health
# ---------------------------------------------------------------------------

@router.get("/health")
def health():
    """Verifica que el módulo IQE está activo."""
    return {
        "status": "ok",
        "module": "intelligent-quotation-engine",
        "vision_provider": os.getenv("IQE_VISION_PROVIDER", "gpt"),
        "confianza_minima": CONFIANZA_MINIMA,
    }


# ---------------------------------------------------------------------------
# POST /analyze-image
# ---------------------------------------------------------------------------

def _persistir_analisis(db: Session, file: UploadFile, attrs: FurnitureAttributes, contexto_adicional: Optional[str]):
    """Persistencia síncrona del análisis de imagen (corre en un thread)."""
    analisis = CotizacionAnalisisIA(
        cotizacion_id=None,
        foto_url=file.filename or "upload",
        tipo_mueble=attrs.tipo_mueble,
        familia_probable=attrs.familia_probable,
        tiene_tapiceria=attrs.tiene_tapiceria,
        tiene_nocheros=attrs.atributos_extra.get("tiene_nocheros", False),
        tiene_espejo=attrs.atributos_extra.get("tiene_espejo", False),
        tiene_luces=attrs.tiene_luces,
        tipo_patas=attrs.tipo_patas,
        estilo_general=attrs.estilo_general,
        nivel_confianza=attrs.nivel_confianza,
        observaciones=f"[Contexto: {contexto_adicional[:50]}...] {attrs.observaciones}" if (contexto_adicional and attrs.observaciones) else (attrs.observaciones or contexto_adicional),
    )
    db.add(analisis)
    db.commit()
    db.refresh(analisis)
    return analisis


@router.post("/analyze-image", response_model=FurnitureAttributesOut, dependencies=[Depends(require_module('cotizaciones_ia'))])
async def analyze_image(
    file: UploadFile = File(...),
    contexto_adicional: Optional[str] = Form(None),
    db: Session = Depends(get_db),
):
    """
    Paso 1: Analiza la imagen del mueble y extrae atributos visuales.

    - El archivo debe ser una imagen (JPEG, PNG, WEBP).
    - La respuesta incluye el nivel de confianza de la IA.
    - Si confianza < 0.70, se marca `requiere_revision_humana: true`.
    - El vendedor SIEMPRE debe revisar los atributos antes del paso 2.

    El ERP NO usa estos atributos para calcular costos.
    Solo los usa para buscar estructuras similares.
    """
    if file.content_type not in ("image/jpeg", "image/png", "image/webp", "image/jpg"):
        raise HTTPException(
            status_code=status.HTTP_415_UNSUPPORTED_MEDIA_TYPE,
            detail="Formato de imagen no soportado. Use JPEG, PNG o WEBP.",
        )

    image_bytes = await file.read()

    if len(image_bytes) > 10 * 1024 * 1024:  # 10 MB
        raise HTTPException(
            status_code=status.HTTP_413_REQUEST_ENTITY_TOO_LARGE,
            detail="La imagen supera el tamaño máximo de 10 MB.",
        )

    # Llamar al proveedor de visión.
    # La creación del provider (lectura síncrona del prompt) se mueve a un
    # thread para no bloquear el event loop.
    import asyncio
    try:
        provider = await asyncio.to_thread(_get_vision_provider)
        attrs: FurnitureAttributes = await provider.analyze(
            image_bytes=image_bytes,
            mime_type=file.content_type,
            contexto_adicional=contexto_adicional,
        )
    except (ImportError, ValueError) as e:
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail=f"El servicio de visión IA no está disponible: {e}",
        )
    except RuntimeError as e:
        raise HTTPException(
            status_code=status.HTTP_502_BAD_GATEWAY,
            detail=f"Error al procesar la imagen con la IA: {e}",
        )

    requiere_revision = attrs.nivel_confianza < CONFIANZA_MINIMA

    # Guardar el análisis en la BD para trazabilidad.
    # SQLAlchemy aquí es síncrono: la persistencia se ejecuta en un thread
    # (asyncio.to_thread) para no bloquear el event loop con I/O de red a PG.
    analisis = await asyncio.to_thread(
        _persistir_analisis, db, file, attrs, contexto_adicional,
    )

    return FurnitureAttributesOut(
        tipo_mueble=attrs.tipo_mueble,
        familia_probable=attrs.familia_probable,
        estilo_general=attrs.estilo_general,
        tipo_patas=attrs.tipo_patas,
        tiene_tapiceria=attrs.tiene_tapiceria,
        tiene_luces=attrs.tiene_luces,
        nivel_confianza=attrs.nivel_confianza,
        observaciones=attrs.observaciones,
        atributos_extra=attrs.atributos_extra,
        requiere_revision_humana=requiere_revision,
        estructura_propuesta=attrs.estructura_propuesta,
        analisis_id=analisis.id,
    )


# ---------------------------------------------------------------------------
# POST /find-similar
# ---------------------------------------------------------------------------

@router.post("/find-similar", response_model=FindSimilarResponse, dependencies=[Depends(require_module('cotizaciones_ia'))])
def find_similar(payload: FindSimilarRequest, db: Session = Depends(get_db)):
    """
    Paso 2: Busca las estructuras históricas más similares.

    Recibe los atributos VALIDADOS POR EL VENDEDOR (no directamente de la IA).
    Devuelve Top N estructuras con score de similitud y explicación de coincidencias.

    El algoritmo usa similitud de coseno sobre vectores de atributos.
    NO usa IA. Solo Python puro.
    """
    attrs = FurnitureAttributes(
        tipo_mueble=payload.tipo_mueble,
        familia_probable=payload.familia_probable,
        estilo_general=payload.estilo_general,
        tipo_patas=payload.tipo_patas,
        tiene_tapiceria=payload.tiene_tapiceria,
        tiene_luces=payload.tiene_luces,
        nivel_confianza=1.0,  # validados por humano = confianza máxima
        observaciones=None,
        atributos_extra=payload.atributos_extra,
    )

    resultados = buscar_similares(db=db, attrs=attrs, top_n=payload.top_n)

    sin_receta = [r for r in resultados if not r.tiene_receta]
    mensaje = None
    if not resultados:
        mensaje = f"No hay estructuras históricas de tipo '{payload.tipo_mueble}'. Deberá construir la receta manualmente."
    elif all(r.es_estructura_nueva for r in resultados):
        mensaje = "El diseño no tiene un similar claro en el histórico. Se muestran los más cercanos para usar como base."

    return FindSimilarResponse(
        resultados=[
            SimilarityResultOut(
                producto_id=r.producto_id,
                nombre=r.nombre,
                tipo_mueble=r.tipo_mueble,
                score=r.score,
                score_pct=r.score_pct,
                coincidencias=r.coincidencias,
                diferencias=r.diferencias,
                ancho_base=r.ancho_base,
                largo_base=r.largo_base,
                tiene_receta=r.tiene_receta,
                es_estructura_nueva=r.es_estructura_nueva,
            )
            for r in resultados
        ],
        tipo_mueble_buscado=payload.tipo_mueble,
        hay_resultados=len(resultados) > 0,
        mensaje=mensaje,
    )


# ---------------------------------------------------------------------------
# POST /create-draft
# ---------------------------------------------------------------------------

@router.post("/create-draft", response_model=DraftOut, dependencies=[Depends(require_module('cotizaciones_ia'))])
def create_draft(payload: CreateDraftRequest, db: Session = Depends(get_db)):
    """
    Paso 3: Genera el borrador de cotización editable.

    Toma la plantilla histórica seleccionada por el vendedor,
    escala las cantidades a las nuevas dimensiones y calcula costos
    con los precios ACTUALES del inventario.

    Los precios históricos son IGNORADOS. Solo se reutilizan
    materiales + cantidades + tipo de escala.
    """
    try:
        resultado = calcular_costo_producto(
            db=db,
            producto_id=payload.producto_base_id,
            nuevo_ancho=payload.nuevo_ancho,
            nuevo_largo=payload.nuevo_largo,
            ganancia_porcentaje=payload.ganancia_porcentaje,
            iva_porcentaje=payload.iva_porcentaje,
            pct_mano_obra=payload.pct_mano_obra,
            pct_gastos=payload.pct_gastos,
            atributos=payload.atributos,
        )
    except ValueError as e:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=str(e))

    if "advertencia" in resultado:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail=resultado["advertencia"],
        )

    materiales_out = [
        MaterialLineaOut(
            material_id=m.get("material_id"),
            nombre=m["nombre"],
            tipo_escala=m["tipo_escala"],
            cantidad_base=m["cantidad_base"],
            cantidad_calculada=m["cantidad_calculada"],
            unidad=m["unidad"],
            costo_unitario=m["costo_unitario"],
            costo_total=m["costo_total"],
            activo=m.get("condicion_cumplida", True),
            observaciones=m.get("observaciones"),
        )
        for m in resultado["materiales"]
    ]

    return DraftOut(
        producto_base_id=payload.producto_base_id,
        producto_base_nombre=resultado["producto_nombre"],
        nuevo_ancho=float(payload.nuevo_ancho),
        nuevo_largo=float(payload.nuevo_largo),
        materiales=materiales_out,
        costo_materiales=resultado["costo_materiales"],
        costo_mano_obra=resultado["costo_mano_obra"],
        costo_gastos=resultado["costo_gastos"],
        costo_produccion=resultado["costo_produccion"],
        ganancia_porcentaje=float(payload.ganancia_porcentaje),
        precio_sin_iva=resultado["precio_sin_iva"],
        iva_porcentaje=float(payload.iva_porcentaje),
        precio_con_iva=resultado["precio_con_iva"],
    )


# ---------------------------------------------------------------------------
# POST /recalculate
# ---------------------------------------------------------------------------

@router.post("/recalculate", response_model=DraftOut, dependencies=[Depends(require_module('cotizaciones_ia'))])
def recalculate(payload: RecalculateRequest, db: Session = Depends(get_db)):
    """
    Paso 4 (opcional): Recalcula los costos del borrador con cambios manuales.

    El vendedor puede:
      - Cambiar cantidades de materiales.
      - Activar/desactivar materiales opcionales.

    El sistema recalcula subtotales, margen e IVA en tiempo real.
    Los precios SIEMPRE vienen del inventario actual, nunca del payload.
    """
    from decimal import Decimal as D

    # Cargar precios actuales del inventario para los materiales del payload
    total_materiales = D("0")
    materiales_out = []

    for linea in payload.materiales:
        mat = db.query(Material).filter(Material.id == linea.material_id).first() if linea.material_id else None

        if not linea.activo:
            # Material desactivado: incluirlo en la lista pero con costo 0
            materiales_out.append(MaterialLineaOut(
                material_id=linea.material_id,
                nombre=(mat.nombre if mat else linea.nombre) or "Insumo libre",
                tipo_escala="FIJO",
                cantidad_base=linea.cantidad_calculada,
                cantidad_calculada=linea.cantidad_calculada,
                unidad=mat.unidad_medida.abreviatura if (mat and mat.unidad_medida) else "",
                costo_unitario=float(mat.costo_base) if mat else 0.0,
                costo_total=0.0,
                activo=False,
            ))
            continue

        cantidad = D(str(linea.cantidad_calculada))
        if mat:
            costo_unit = D(str(mat.costo_base))
        elif linea.costo_unitario is not None:
            costo_unit = D(str(linea.costo_unitario))
        else:
            costo_unit = D("0")
        costo_total = cantidad * costo_unit
        total_materiales += costo_total

        materiales_out.append(MaterialLineaOut(
            material_id=linea.material_id,
            nombre=(mat.nombre if mat else linea.nombre) or "Insumo libre",
            tipo_escala="FIJO",  # el tipo_escala no cambia en recálculo manual
            cantidad_base=linea.cantidad_calculada,
            cantidad_calculada=linea.cantidad_calculada,
            unidad=mat.unidad_medida.abreviatura if (mat and mat.unidad_medida) else "",
            costo_unitario=float(costo_unit),
            costo_total=float(costo_total),
            activo=True,
        ))

    pct_mo = payload.pct_mano_obra / D("100")
    pct_g = payload.pct_gastos / D("100")
    costo_mo = total_materiales * pct_mo
    costo_g = total_materiales * pct_g
    costo_prod = total_materiales + costo_mo + costo_g
    precio_sin_iva = costo_prod * (D("1") + payload.ganancia_porcentaje / D("100"))
    precio_con_iva = precio_sin_iva * (D("1") + payload.iva_porcentaje / D("100"))

    # Cargar nombre del producto base
    from app.modules.productos.model import Producto
    prod = db.query(Producto).filter(Producto.id == payload.producto_base_id).first()
    nombre_base = prod.nombre if prod else f"Producto #{payload.producto_base_id}"

    return DraftOut(
        producto_base_id=payload.producto_base_id,
        producto_base_nombre=nombre_base,
        nuevo_ancho=float(payload.nuevo_ancho),
        nuevo_largo=float(payload.nuevo_largo),
        materiales=materiales_out,
        costo_materiales=float(total_materiales),
        costo_mano_obra=float(costo_mo),
        costo_gastos=float(costo_g),
        costo_produccion=float(costo_prod),
        ganancia_porcentaje=float(payload.ganancia_porcentaje),
        precio_sin_iva=float(precio_sin_iva),
        iva_porcentaje=float(payload.iva_porcentaje),
        precio_con_iva=float(precio_con_iva),
    )


# ---------------------------------------------------------------------------
# POST /finalize
# ---------------------------------------------------------------------------

def _analisis_con_lock(db: Session, analisis_id):
    """
    Bloquea la fila del análisis de imagen (FOR UPDATE) y devuelve
    (analisis, cotizacion_existente, producto_existente). Si el análisis ya
    generó una cotización o un producto, devuelve ese registro para NO
    duplicarlo (idempotencia ante doble clic o retry del mismo request).
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


@router.post("/finalize", response_model=FinalizeResponse, dependencies=[Depends(require_module('cotizaciones_ia'))])
def finalize(payload: FinalizeRequest, db: Session = Depends(get_db)):
    """
    Paso 5: Guarda definitivamente la cotización y su receta detallada en la BD.

    Crea los registros de Cotizacion, DetalleCotizacion y guarda la receta
    personalizada de materiales en cotizacion_detalle_material.
    """
    from decimal import Decimal as D

    # 0. Idempotencia: si este análisis ya generó una cotización, devolverla
    analisis, cotizacion_existente, _ = _analisis_con_lock(db, payload.analisis_id)
    if cotizacion_existente:
        return FinalizeResponse(
            cotizacion_id=cotizacion_existente.id,
            total_estimado=float(cotizacion_existente.total_estimado or 0),
            pdf_url=f"/api/v1/cotizacion/{cotizacion_existente.id}/imprimir",
            mensaje="La cotización ya fue guardada a partir de este análisis. Se devuelve la existente."
        )

    # 1. Recalcular costos finales basados en los materiales actuales del inventario
    total_materiales = D("0")
    materiales_validos = []

    for linea in payload.materiales:
        mat = db.query(Material).filter(Material.id == linea.material_id).first() if linea.material_id else None

        if not linea.activo:
            # Material desactivado: se conserva en la receta (activo=False) si existe
            if mat:
                materiales_validos.append((mat, linea))
            continue

        if mat:
            costo_linea = D(str(linea.cantidad_calculada)) * D(str(mat.costo_base))
            total_materiales += costo_linea
            materiales_validos.append((mat, linea))
        elif linea.costo_unitario is not None:
            # Insumo libre sin material de inventario: aporta su costo pero no se
            # persiste en cotizacion_detalle_material (requiere material_id)
            total_materiales += D(str(linea.cantidad_calculada)) * D(str(linea.costo_unitario))

    pct_mo = payload.pct_mano_obra / D("100")
    pct_g = payload.pct_gastos / D("100")
    costo_mo = total_materiales * pct_mo
    costo_g = total_materiales * pct_g
    costo_prod = total_materiales + costo_mo + costo_g
    precio_sin_iva = costo_prod * (D("1") + payload.ganancia_porcentaje / D("100"))
    precio_con_iva = precio_sin_iva * (D("1") + payload.iva_porcentaje / D("100"))

    # 2. Guardar cabecera de la cotización
    cotizacion = Cotizacion(
        cliente_id=payload.cliente_id,
        fecha=datetime.date.today(),
        estado="BORRADOR",
        total_estimado=precio_con_iva,
        observaciones=payload.observaciones or "Generada inteligentemente a partir de imagen base.",
    )
    db.add(cotizacion)
    db.flush()  # Obtener cotizacion.id

    # 3. Guardar el detalle de la cotización
    detalle = DetalleCotizacion(
        cotizacion_id=cotizacion.id,
        producto_id=payload.producto_base_id,
        cantidad=D("1"),
        precio=precio_con_iva,
        ancho=payload.nuevo_ancho,
        largo=payload.nuevo_largo,
        observaciones="Cotización personalizada inteligente",
        costo_materiales=total_materiales,
        costo_mano_obra=costo_mo,
        costo_gastos=costo_g,
        costo_total=costo_prod,
    )
    db.add(detalle)
    db.flush()  # Obtener detalle.id

    # 4. Guardar la receta personalizada por cada material
    for mat, linea in materiales_validos:
        detalle_material = CotizacionDetalleMaterial(
            detalle_cotizacion_id=detalle.id,
            material_id=linea.material_id,
            cantidad_base=linea.cantidad_calculada,  # usar calculada como base en receta final
            cantidad_calculada=linea.cantidad_calculada,
            tipo_escala="FIJO",
            activo=linea.activo,
            observaciones="Cargado desde el wizard inteligente",
        )
        db.add(detalle_material)

    # 5. Si hay un análisis de imagen previo, asociarlo a esta cotización
    #    (la fila ya está bloqueada con FOR UPDATE desde la idempotencia)
    if analisis:
        analisis.cotizacion_id = cotizacion.id

    db.commit()

    return FinalizeResponse(
        cotizacion_id=cotizacion.id,
        total_estimado=float(precio_con_iva),
        pdf_url=f"/api/v1/cotizacion/{cotizacion.id}/imprimir",  # Placeholder
        mensaje="Cotización finalizada y guardada exitosamente."
    )


# ---------------------------------------------------------------------------
# Estructura de Costos Editable con IA (v2)
# ---------------------------------------------------------------------------

@router.post("/generate-structure", response_model=GenerateStructureOut, dependencies=[Depends(require_module('cotizaciones_ia'))])
def generate_structure(payload: GenerateStructureRequest, db: Session = Depends(get_db)):
    """
    Paso 3 (Inteligente): Genera la estructura de costos a partir de
    la propuesta de la IA y la receta más similar del inventario.
    """
    # 1. Crear el objeto FurnitureAttributes para buscar_similares
    attrs = FurnitureAttributes(
        tipo_mueble=payload.tipo_mueble,
        familia_probable=payload.atributos.get("familia_probable"),
        estilo_general=payload.atributos.get("estilo_general"),
        tipo_patas=payload.atributos.get("tipo_patas"),
        tiene_tapiceria=bool(payload.atributos.get("tiene_tapiceria", False)),
        tiene_luces=bool(payload.atributos.get("tiene_luces", False)),
        nivel_confianza=1.0,
        observaciones=payload.atributos.get("observaciones"),
        atributos_extra=payload.atributos.get("atributos_extra", {}),
        estructura_propuesta=payload.estructura_propuesta,
    )

    try:
        resultado = build_cost_structure(
            db=db,
            attrs=attrs,
            estructura_ia=payload.estructura_propuesta,
            nuevo_ancho=payload.nuevo_ancho,
            nuevo_largo=payload.nuevo_largo,
            ganancia_porcentaje=payload.ganancia_porcentaje,
            iva_porcentaje=payload.iva_porcentaje,
            pct_mano_obra=payload.pct_mano_obra,
            pct_gastos=payload.pct_gastos,
            top_n_similar=3
        )
        return resultado
    except Exception as e:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Error al construir la estructura de costos: {e}"
        )


@router.post("/recalculate-structure", response_model=GenerateStructureOut, dependencies=[Depends(require_module('cotizaciones_ia'))])
def recalculate_structure_endpoint(payload: RecalculateStructureRequest, db: Session = Depends(get_db)):
    """
    Recalcula subtotales, totales y desgloses de la estructura de costos editada.
    """
    secciones_dict = [sec.model_dump() for sec in payload.secciones]
    try:
        resultado = recalculate_structure(
            db=db,
            secciones_editadas=secciones_dict,
            ganancia_porcentaje=payload.ganancia_porcentaje,
            iva_porcentaje=payload.iva_porcentaje,
            pct_mano_obra=payload.pct_mano_obra,
            pct_gastos=payload.pct_gastos,
        )
        return resultado
    except Exception as e:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Error al recalcular la estructura de costos: {e}"
        )


@router.post("/finalize-structure", response_model=FinalizeResponse, dependencies=[Depends(require_module('cotizaciones_ia'))])
def finalize_structure(payload: FinalizeStructureRequest, db: Session = Depends(get_db)):
    """
    Paso 5: Guarda la cotización terminada (Opción B) o la registra como
    un Producto Nuevo en la base de datos (Opción A).
    """
    from decimal import Decimal as D
    import datetime

    # 1. Validar que tengamos las secciones de costo
    if not payload.secciones:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="La estructura de costos está vacía."
        )

    # 2. Cargar/Verificar materiales y calcular total real
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

    # Calcular desgloses del costo
    pct_mo = D(str(payload.pct_mano_obra)) / D("100")
    pct_g = D(str(payload.pct_gastos)) / D("100")
    costo_mo = total_materiales * pct_mo
    costo_g = total_materiales * pct_g
    costo_prod = total_materiales + costo_mo + costo_g
    precio_sin_iva = costo_prod * (D("1") + D(str(payload.ganancia_porcentaje)) / D("100"))
    precio_con_iva = precio_sin_iva * (D("1") + D(str(payload.iva_porcentaje)) / D("100"))

    if payload.guardar_como == "producto":
        if not payload.nombre_producto:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="El nombre del producto es requerido para guardar como Producto."
            )
        if not payload.tipo_producto_id:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="El tipo de producto es requerido para guardar como Producto."
            )

        # Idempotencia: si este análisis ya creó un producto, devolverlo
        analisis, _, producto_existente = _analisis_con_lock(db, payload.analisis_id)
        if producto_existente:
            return FinalizeResponse(
                cotizacion_id=0,
                total_estimado=float(producto_existente.precio_venta_con_iva or producto_existente.precio_venta_base or 0),
                pdf_url=f"/productos",
                mensaje="El producto ya fue guardado a partir de este análisis. Se devuelve el existente."
            )

        # Crear nuevo producto
        nuevo_prod = Producto(
            nombre=payload.nombre_producto,
            tipo_producto_id=payload.tipo_producto_id,
            ancho_base=D(str(payload.nuevo_ancho)),
            largo_base=D(str(payload.nuevo_largo)),
            precio_costo_base=costo_prod,
            precio_venta_base=precio_sin_iva,
            precio_venta_con_iva=precio_con_iva,
            descripcion=payload.observaciones or f"Creado desde Cotizador Inteligente v2 el {datetime.date.today()}",
            activo=True
        )
        db.add(nuevo_prod)
        db.flush()

        # Guardar la receta
        for sec in payload.secciones:
            for item in sec.items:
                if not item.activo or not item.material_id:
                    continue
                pm = ProductoMaterial(
                    producto_id=nuevo_prod.id,
                    material_id=item.material_id,
                    cantidad_base=D(str(item.cantidad)),
                    tipo_escala="FIJO",
                    observaciones=f"Sección: {sec.seccion}. Razón: {item.razon}"
                )
                db.add(pm)

        # Crear registro en mueble_atributos
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

        mueble_attr = MuebleAtributos(
            producto_id=nuevo_prod.id,
            tipo_mueble=tipo_m,
            tiene_tapiceria=v_tap > 0,
            tiene_luces=v_luz > 0,
            atributos_extra={"es_opcional": False},
            vector_similitud=vector_base
        )
        db.add(mueble_attr)
        db.commit()

        if analisis:
            analisis.producto_id = nuevo_prod.id
            db.commit()

        return FinalizeResponse(
            cotizacion_id=0,
            total_estimado=float(precio_con_iva),
            pdf_url=f"/productos", # Cambiado para ir a la vista de productos
            mensaje=f"Producto '{nuevo_prod.nombre}' y su receta guardados exitosamente."
        )

    else:
        # Guardar como Cotización
        if not payload.cliente_id:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="El cliente es requerido para guardar como Cotización."
            )

        # Idempotencia: si este análisis ya generó una cotización, devolverla
        analisis, cotizacion_existente, _ = _analisis_con_lock(db, payload.analisis_id)
        if cotizacion_existente:
            return FinalizeResponse(
                cotizacion_id=cotizacion_existente.id,
                total_estimado=float(cotizacion_existente.total_estimado or 0),
                pdf_url=f"/api/v1/cotizacion/{cotizacion_existente.id}/imprimir",
                mensaje="La cotización ya fue guardada a partir de este análisis. Se devuelve la existente."
            )

        cotizacion = Cotizacion(
            cliente_id=payload.cliente_id,
            fecha=datetime.date.today(),
            estado="BORRADOR",
            total_estimado=precio_con_iva,
            observaciones=payload.observaciones or "Generada con estructura de costos editable v2.",
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
            observaciones="Estructura personalizada inteligente v2",
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
                
                detalle_material = CotizacionDetalleMaterial(
                    detalle_cotizacion_id=detalle.id,
                    material_id=item.material_id,
                    cantidad_base=D(str(item.cantidad)),
                    cantidad_calculada=D(str(item.cantidad)),
                    tipo_escala="FIJO",
                    activo=item.activo,
                    observaciones=f"Sección: {sec.seccion}. Razón: {item.razon}",
                )
                db.add(detalle_material)

        if analisis:
            analisis.cotizacion_id = cotizacion.id

        db.commit()

        return FinalizeResponse(
            cotizacion_id=cotizacion.id,
            total_estimado=float(precio_con_iva),
            pdf_url=f"/api/v1/cotizacion/{cotizacion.id}/imprimir",
            mensaje="Cotización finalizada y guardada exitosamente con estructura de costos."
        )

