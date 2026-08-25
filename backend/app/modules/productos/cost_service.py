"""
cost_service.py
===============
Servicio de costeo paramétrico para YEIKAR.

Dado un producto y unas dimensiones personalizadas (ancho, largo),
calcula automáticamente las cantidades de cada material según la
regla de escalado definida en la tabla `producto_material`, y luego
aplica márgenes de mano de obra, gastos, ganancia e IVA para obtener
el precio de venta sugerido.

Reglas de escalado implementadas:
  FIJO      → cantidad siempre igual a cantidad_base
  LINEAL    → escala con (nuevo_largo / largo_base)
  AREA      → escala con (nuevo_ancho × nuevo_largo) / (ancho_base × largo_base)
  ESPACIADO → basado en perímetro: (2 × (largo+ancho)) / distancia_pauta_cm × tornillos_por_pieza
  POR_RANGO → saltos discretos según tabla de rangos JSON
  FORMULA   → (reservado para futuro – usa cantidad_base como fallback)

Además se evalúa `condicion_activacion` antes de aplicar la fórmula.
Si la condición no se cumple, la cantidad del material es 0.
"""

import unicodedata
from decimal import Decimal, ROUND_HALF_UP
from sqlalchemy.orm import Session, joinedload
from app.core.redondeo import redondear_precio_cop
from app.modules.productos.model import Producto, ProductoMaterial, Material, ReglaGastoSeccion, SeccionProducto, ElementoSeccion, PoliticaSeccion, CostoProduccionSeccion


# Porcentaje de impuestos adicional sobre el costo de producción (configurable).
# Fórmula:  a = costo_produccion * (1 + impuesto%)   →   b = a * (1 + ganancia%)
IMPUESTOS_PCT_DEFAULT = Decimal("7")


# ---------------------------------------------------------------------------
# Utilidades internas
# ---------------------------------------------------------------------------

def _normalizar_seccion(seccion) -> str:
    """
    Normaliza el valor de `seccion` a la clave canónica usada en
    `regla_gasto_seccion` (sin tildes ni sufijos entre paréntesis).

    - "EBANISTERÍA" → "EBANISTERIA"
    - "PINTURA (CAMA)" → "PINTURA"
    - "EBANISTERÍA (NOCHEROS)" → "NOCHEROS"
    """
    if not seccion:
        return "EBANISTERIA"
    s = str(seccion).upper()
    if "NOCHEROS" in s:
        return "NOCHEROS"
    s = "".join(c for c in unicodedata.normalize("NFD", s) if unicodedata.category(c) != "Mn")
    s = s.split("(")[0].strip()
    s = s.replace(" ", "_")
    return s or "EBANISTERIA"

def _evaluar_condicion(condicion: dict, nuevo_ancho: Decimal, nuevo_largo: Decimal, atributos: dict = None) -> bool:
    """
    Evalúa una condición de activación de la forma:
        {"campo": "nuevo_largo", "op": ">", "valor": 2.0}
    O de tipo lógico:
        {"campo": "tiene_tapiceria", "op": "==", "valor": true}
    
    Retorna True si el material debe incluirse, False si debe omitirse.
    """
    if not condicion or not isinstance(condicion, dict):
        return True

    campo = condicion.get("campo")
    operador = condicion.get("op")
    valor_referencia = condicion.get("valor")

    if campo is None or operador is None or valor_referencia is None:
        return True

    if campo == "nuevo_largo":
        valor_actual = nuevo_largo
        valor_referencia = Decimal(str(valor_referencia))
    elif campo == "nuevo_ancho":
        valor_actual = nuevo_ancho
        valor_referencia = Decimal(str(valor_referencia))
    else:
        # Evaluar contra atributos adicionales (ej. tiene_tapiceria, tiene_nocheros)
        if atributos is None:
            return True  # Sin atributos -> incluir para no silenciar
        if campo not in atributos:
            return True  # No especificado -> incluir
        
        valor_actual = atributos[campo]
        if isinstance(valor_actual, bool):
            # Normalizar valor de referencia si es booleano
            if isinstance(valor_referencia, str):
                valor_referencia = valor_referencia.lower() in ("true", "1", "yes")
            else:
                valor_referencia = bool(valor_referencia)
        elif isinstance(valor_actual, (int, float, Decimal)):
            valor_actual = Decimal(str(valor_actual))
            valor_referencia = Decimal(str(valor_referencia))
        else:
            valor_actual = str(valor_actual)
            valor_referencia = str(valor_referencia)

    ops = {
        ">":  valor_actual >  valor_referencia,
        ">=": valor_actual >= valor_referencia,
        "<":  valor_actual <  valor_referencia,
        "<=": valor_actual <= valor_referencia,
        "==": valor_actual == valor_referencia,
        "!=": valor_actual != valor_referencia,
    }
    return ops.get(operador, True)


def _calcular_por_rango(rangos: list, nuevo_largo: Decimal) -> Decimal | None:
    """
    Busca en la lista de rangos la primera entrada donde nuevo_largo <= rango["max"]
    y devuelve la cantidad correspondiente.
    Si nuevo_largo supera todos los máximos, retorna la cantidad del último rango.
    Retorna None si la lista está vacía o mal formada.
    """
    if not rangos or not isinstance(rangos, list):
        return None

    ultima_cantidad = None
    for rango in rangos:
        try:
            max_val  = Decimal(str(rango["max"]))
            cantidad = Decimal(str(rango["cantidad"]))
            ultima_cantidad = cantidad
            if nuevo_largo <= max_val:
                return cantidad
        except (KeyError, TypeError, ValueError):
            continue

    return ultima_cantidad  # usa el último rango si supera todos los máximos


def _redondear(valor: Decimal, decimales: int = 4) -> Decimal:
    cuantificador = Decimal("0." + "0" * decimales) if decimales > 0 else Decimal("1")
    return valor.quantize(cuantificador, rounding=ROUND_HALF_UP)


def _aplicar_impuestos_y_ganancia(
    costo: Decimal,
    ganancia_porcentaje: Decimal,
    iva_porcentaje: Decimal,
    impuesto_porcentaje: Decimal,
):
    """
    Regla de precios YEIKAR:
      a = costo_produccion * (1 + impuesto%)   → impuestos sobre el costo total
      b = a * (1 + ganancia%)                  → precio final del producto
      precio_con_iva = b * (1 + iva%)          → IVA opcional después
    Devuelve (monto_impuestos, base_con_impuestos, precio_sin_iva, precio_con_iva).
    """
    monto_impuestos = _redondear(costo * impuesto_porcentaje / Decimal("100"), 2)
    base_con_impuestos = _redondear(costo + monto_impuestos, 2)
    # Los precios de venta se redondean al millar COP hacia arriba: nunca se
    # vende por debajo del precio calculado y ningún descuento % deja decimales.
    precio_sin_iva = redondear_precio_cop(
        _redondear(base_con_impuestos * (Decimal("1") + ganancia_porcentaje / Decimal("100")), 2),
        "ceil",
    )
    precio_con_iva = redondear_precio_cop(
        _redondear(precio_sin_iva * (Decimal("1") + iva_porcentaje / Decimal("100")), 2),
        "ceil",
    )
    return monto_impuestos, base_con_impuestos, precio_sin_iva, precio_con_iva


def _calcular_cantidad_material(
    pm: ProductoMaterial,
    nuevo_ancho: Decimal,
    nuevo_largo: Decimal,
    ancho_base: Decimal,
    largo_base: Decimal,
    area_base: Decimal,
    area_nueva: Decimal,
    atributos: dict = None,
) -> Decimal:
    """
    Calcula la cantidad escalada de un material según su tipo_escala y dimensiones.
    Incluye verificación de condicion_activacion y es_fijo_override.
    """
    tipo = pm.tipo_escala
    cantidad_base = Decimal(str(pm.cantidad_base))

    # Verificar condición de activación
    if pm.condicion_activacion:
        if not _evaluar_condicion(pm.condicion_activacion, nuevo_ancho, nuevo_largo, atributos):
            return Decimal("0")

    # Override fijo
    if pm.es_fijo_override:
        return _redondear(cantidad_base)

    # Aplicar fórmula según tipo_escala
    if tipo == "FIJO":
        cantidad = cantidad_base

    elif tipo == "LINEAL":
        if largo_base == 0:
            cantidad = cantidad_base
        else:
            cantidad = cantidad_base * (nuevo_largo / largo_base)

    elif tipo == "AREA":
        if area_base == 0:
            cantidad = cantidad_base
        else:
            cantidad = cantidad_base * (area_nueva / area_base)

    elif tipo == "ESPACIADO":
        distancia = (
            Decimal(str(pm.distancia_pauta_cm))
            if pm.distancia_pauta_cm
            else Decimal("30")
        )
        por_pieza = pm.tornillos_por_pieza or 1

        perimetro_base = 2 * (largo_base + ancho_base)
        perimetro_nuevo = 2 * (nuevo_largo + nuevo_ancho)

        perimetro_nuevo_cm = perimetro_nuevo * 100
        perimetro_base_cm = perimetro_base * 100

        piezas_base = perimetro_base_cm / distancia + 1
        piezas_nuevas = perimetro_nuevo_cm / distancia + 1

        if piezas_base == 0:
            cantidad = cantidad_base
        else:
            cantidad = (piezas_nuevas / piezas_base) * cantidad_base * Decimal(str(por_pieza))

    elif tipo == "POR_RANGO":
        resultado = _calcular_por_rango(pm.rangos, nuevo_largo)
        cantidad = resultado if resultado is not None else cantidad_base

    elif tipo == "FORMULA":
        cantidad = cantidad_base

    else:
        cantidad = cantidad_base

    return max(Decimal("0"), _redondear(cantidad))


# ---------------------------------------------------------------------------
# Función principal
# ---------------------------------------------------------------------------

def calcular_costo_producto(
    db: Session,
    producto_id: int,
    nuevo_ancho: Decimal,
    nuevo_largo: Decimal,
    ganancia_porcentaje: Decimal = Decimal("40"),
    iva_porcentaje: Decimal = Decimal("0"),        # En Colombia el IVA de muebles es 0% por defecto
    pct_mano_obra: Decimal = Decimal("15"),
    pct_gastos: Decimal = Decimal("10"),
    impuesto_porcentaje: Decimal = IMPUESTOS_PCT_DEFAULT,
    atributos: dict = None,
) -> dict:
    """
    Calcula el costo total y el precio de venta sugerido para un producto
    con dimensiones y atributos lógicos personalizados.
    """
    # --- 1. Cargar producto --------------------------------------------------
    producto = db.query(Producto).filter(Producto.id == producto_id).first()
    if not producto:
        raise ValueError(f"Producto con id {producto_id} no encontrado")

    ancho_base = Decimal(str(producto.ancho_base)) if producto.ancho_base else Decimal("1.60")
    largo_base = Decimal(str(producto.largo_base)) if producto.largo_base else Decimal("1.90")
    area_base  = ancho_base * largo_base
    area_nueva = nuevo_ancho * nuevo_largo

    # Cargamos la receta de materiales del producto
    receta: list[ProductoMaterial] = db.query(ProductoMaterial).filter(ProductoMaterial.producto_id == producto_id).all()

    # Si hay una receta de materiales cargada, calculamos los costos por SECCIÓN
    # usando ReglaGastoSeccion para aplicar el % correcto por área del mueble.
    if receta:
        # Cargar reglas de gasto por sección una sola vez
        reglas_raw = db.query(ReglaGastoSeccion).all()
        reglas_por_seccion: dict[str, Decimal] = {
            r.seccion: Decimal(str(r.porcentaje_gasto)) for r in reglas_raw
        }

        # Acumular costo base por sección (suma bruta de materiales importados)
        costo_por_seccion: dict[str, Decimal] = {}
        detalle_materiales = []
        detalle_nochero = []

        for pm in receta:
            material = pm.material
            cantidad_calculada = _calcular_cantidad_material(
                pm, nuevo_ancho, nuevo_largo, ancho_base, largo_base,
                area_base, area_nueva, atributos,
            )
            costo_linea = cantidad_calculada * Decimal(str(material.costo_base))
            seccion = _normalizar_seccion(pm.seccion)
            es_nochero = seccion == "NOCHEROS"

            item = {
                "material_id": material.id,
                "material_nombre": material.nombre,
                "nombre": material.nombre,
                "tipo_escala": pm.tipo_escala,
                "seccion": seccion,
                "condicion_activacion": pm.condicion_activacion,
                "condicion_cumplida": cantidad_calculada > 0 or not pm.condicion_activacion,
                "cantidad_base": float(pm.cantidad_base),
                "cantidad_calculada": float(cantidad_calculada),
                "unidad": material.unidad_medida.abreviatura if material.unidad_medida else "",
                "costo_unitario": float(material.costo_base),
                "costo_total": float(costo_linea),
                "costo_subtotal": float(costo_linea),
                "observaciones": pm.observaciones,
                "es_nochero": es_nochero,
            }

            if es_nochero:
                detalle_nochero.append(item)
            else:
                detalle_materiales.append(item)

            costo_por_seccion.setdefault(seccion, Decimal("0"))
            costo_por_seccion[seccion] += costo_linea

        # --- Elegir fuente de costo de producción ---
        # El precio_costo_base viene del Excel histórico de YEIKAR y es el TOTAL
        # correcto calculado por la empresa (ya incluye materiales, mano de obra y gastos).
        # Se usa siempre que las dimensiones solicitadas sean iguales a las dimensiones base.
        # Si se piden dimensiones diferentes, escalamos proporcionalmente.
        dimensiones_iguales = (
            abs(nuevo_ancho - ancho_base) < Decimal("0.01") and
            abs(nuevo_largo - largo_base) < Decimal("0.01")
        )

        if producto.precio_costo_base is not None and dimensiones_iguales:
            # Usar el costo del Excel directamente — es la fuente de verdad
            costo_produccion = Decimal(str(producto.precio_costo_base))
            # Desglose estimado por sección (para mostrar en UI, no para calcular)
            costo_total_materiales = sum(
                v for k, v in costo_por_seccion.items() if k not in ("NOCHEROS",)
            )
            costo_gastos_total = Decimal("0")
            desglose_secciones = {
                sec: {
                    "costo_base": float(c),
                    "porcentaje_gasto": float(reglas_por_seccion.get(sec, Decimal("0"))),
                    "gasto_aplicado": 0.0,
                    "total": float(c),
                    "nota": "Costo tomado del Excel histórico",
                }
                for sec, c in costo_por_seccion.items()
            }
        else:
            # Dimensiones distintas: escalar desde el Excel o calcular desde receta con % sección
            if producto.precio_costo_base is not None:
                # Escalar el costo del Excel según la variación de área
                factor_area = (nuevo_ancho * nuevo_largo) / (ancho_base * largo_base) if area_base > 0 else Decimal("1")
                costo_produccion = _redondear(Decimal(str(producto.precio_costo_base)) * factor_area, 2)
            else:
                # Fallback completo: sumar por sección con su % de gastos
                costo_produccion = Decimal("0")
                for seccion, costo_base_sec in costo_por_seccion.items():
                    pct_gasto = reglas_por_seccion.get(seccion, Decimal("0"))
                    gasto_sec = _redondear(costo_base_sec * pct_gasto / Decimal("100"), 2)
                    costo_produccion += costo_base_sec + gasto_sec

            costo_total_materiales = sum(
                v for k, v in costo_por_seccion.items() if k not in ("NOCHEROS",)
            )
            costo_gastos_total = Decimal("0")
            desglose_secciones = {
                sec: {
                    "costo_base": float(c),
                    "porcentaje_gasto": float(reglas_por_seccion.get(sec, Decimal("0"))),
                    "gasto_aplicado": 0.0,
                    "total": float(c),
                }
                for sec, c in costo_por_seccion.items()
            }

        costo_nochero = costo_por_seccion.get("NOCHEROS", Decimal("0"))

        # Precio de venta: costo + impuestos% → resultado + ganancia% → (opcional IVA)
        monto_impuestos, base_con_impuestos, precio_sin_iva, precio_con_iva = _aplicar_impuestos_y_ganancia(
            costo_produccion, ganancia_porcentaje, iva_porcentaje, impuesto_porcentaje
        )

        resultado = {
            "producto_id": producto.id,
            "producto_nombre": producto.nombre,
            "dimensiones_base": {"ancho": float(ancho_base), "largo": float(largo_base)},
            "dimensiones_nuevas": {"ancho": float(nuevo_ancho), "largo": float(nuevo_largo)},
            "materiales": detalle_materiales,
            "materiales_nochero": detalle_nochero,
            "materiales_detalle": detalle_materiales,
            "desglose_por_seccion": desglose_secciones,
            "resumen_costos": {
                "costo_materiales": float(costo_total_materiales),
                "costo_gastos_indirectos": float(costo_gastos_total),
                "costo_gastos": float(costo_gastos_total),
                "pct_gastos": "por sección (ver desglose_por_seccion)",
                "costo_produccion": float(costo_produccion),
                "costo_total": float(costo_produccion),
                "impuesto_porcentaje": float(impuesto_porcentaje),
                "impuestos": float(monto_impuestos),
                "base_con_impuestos": float(base_con_impuestos),
                "ganancia_porcentaje": float(ganancia_porcentaje),
                "precio_sin_iva": float(precio_sin_iva),
                "iva_porcentaje": float(iva_porcentaje),
                "precio_con_iva": float(precio_con_iva),
                "precio_sugerido": float(precio_con_iva),
                "precio_venta": float(precio_con_iva),
                "costo_nochero": float(costo_nochero),
            },
            "costo_materiales": float(costo_total_materiales),
            "costo_mano_obra": float(costo_por_seccion.get("MANO_DE_OBRA", Decimal("0"))),
            "costo_gastos": float(costo_gastos_total),
            "costo_gastos_indirectos": float(costo_gastos_total),
            "costo_produccion": float(costo_produccion),
            "costo_total": float(costo_produccion),
            "impuesto_porcentaje": float(impuesto_porcentaje),
            "impuestos": float(monto_impuestos),
            "base_con_impuestos": float(base_con_impuestos),
            "ganancia_porcentaje": float(ganancia_porcentaje),
            "precio_sin_iva": float(precio_sin_iva),
            "iva_porcentaje": float(iva_porcentaje),
            "precio_con_iva": float(precio_con_iva),
            "precio_sugerido": float(precio_con_iva),
            "precio_venta": float(precio_con_iva),
            "costo_nochero": float(costo_nochero),
        }
        return resultado

    # --- 2. Cargar receta de materiales ------------------------------------
    receta: list[ProductoMaterial] = (
        db.query(ProductoMaterial)
        .filter(ProductoMaterial.producto_id == producto_id)
        .all()
    )

    if not receta:
        # Intentar calcular desde ElementoSeccion (secciones con insumos)
        secciones: list[SeccionProducto] = (
            db.query(SeccionProducto)
            .filter(SeccionProducto.producto_id == producto_id)
            .options(joinedload(SeccionProducto.elementos), joinedload(SeccionProducto.politica), joinedload(SeccionProducto.costos_produccion))
            .all()
        )
        if secciones:
            costo_total_elementos = Decimal("0")
            detalle_elementos = []
            desglose_por_seccion = {}
            # Pre-cargar materiales normalizados para usarlos como FALLBACK de precio.
            # Regla: se usa el precio_unitario guardado en el elemento (el precio que
            # YEIKAR fijó en la receta/Excel). Solo si el elemento NO tiene precio se
            # cae al costo VIGENTE del material (material.costo_base). Esto evita que
            # precios del catálogo con unidades distintas (p.ej. LAM MDF por lámina vs
            # por pieza) inflen el costo de producción.
            ids_materiales = {el.material_id_normalizado for sec in secciones for el in sec.elementos if el.material_id_normalizado}
            materiales_map = {
                m.id: m for m in db.query(Material).filter(Material.id.in_(ids_materiales)).all()
            } if ids_materiales else {}
            for sec in secciones:
                # --- Sumar insumos de la sección ---
                costo_insumos = Decimal("0")
                for el in sec.elementos:
                    mat_vivo = materiales_map.get(el.material_id_normalizado) if el.material_id_normalizado else None
                    if el.precio_unitario:
                        costo_unitario_efectivo = Decimal(str(el.precio_unitario))
                    elif mat_vivo is not None and mat_vivo.costo_base is not None:
                        costo_unitario_efectivo = Decimal(str(mat_vivo.costo_base))
                    else:
                        costo_unitario_efectivo = Decimal("0")
                    subtotal = Decimal(str(el.cantidad)) * costo_unitario_efectivo
                    costo_insumos += subtotal
                    detalle_elementos.append({
                        "seccion": sec.nombre,
                        "material_id": el.material_id_normalizado,
                        "nombre": el.nombre_insumo_original,
                        "material_nombre": el.nombre_insumo_original,
                        "nombre_insumo_original": el.nombre_insumo_original,
                        "tipo_escala": "FIJO",
                        "cantidad": float(el.cantidad),
                        "cantidad_base": float(el.cantidad),
                        "cantidad_calculada": float(el.cantidad),
                        "unidad_medida": el.unidad_medida or "",
                        "unidad": el.unidad_medida or "",
                        "costo_unitario": float(costo_unitario_efectivo),
                        "costo_subtotal": float(subtotal),
                        "costo_total": float(subtotal),
                    })

                # --- Aplicar fórmula completa por sección ---
                pol = sec.politica

                # Base = insumos
                base_seccion = costo_insumos

                # + Costos de producción múltiples (PREPARADO CAMA, PINTURA CAMA, etc.)
                total_costos_produccion = Decimal("0")
                costos_produccion_detalle = []
                for cp in sec.costos_produccion or []:
                    cp_base = Decimal(str(cp.costo_base)) if cp.costo_base else Decimal("0")
                    cp_pct = Decimal(str(cp.porcentaje)) if cp.porcentaje else Decimal("0")
                    cp_aporte = cp_base + (_redondear(cp_base * cp_pct / Decimal("100"), 2) if cp_pct > 0 else Decimal("0"))
                    total_costos_produccion += cp_aporte
                    costos_produccion_detalle.append({
                        "nombre": cp.nombre,
                        "costo_base": float(cp_base),
                        "porcentaje": float(cp_pct),
                        "aporte": float(cp_aporte),
                    })

                # Subtotal = insumos + costos de producción
                subtotal_seccion = base_seccion + total_costos_produccion

                # + % gastos sección (existente)
                pct_gastos_sec = Decimal(str(pol.pct_gastos_seccion)) if (pol and pol.pct_gastos_seccion) else Decimal("0")
                gasto_seccion = _redondear(subtotal_seccion * pct_gastos_sec / Decimal("100"), 2) if pct_gastos_sec > 0 else Decimal("0")

                # + % negocio sobre subtotal (opcional)
                pct_neg = Decimal(str(pol.pct_negocio)) if (pol and pol.pct_negocio) else Decimal("0")
                costo_negocio = _redondear(subtotal_seccion * pct_neg / Decimal("100"), 2) if pct_neg > 0 else Decimal("0")

                # Total sección
                total_seccion = subtotal_seccion + gasto_seccion + costo_negocio
                costo_total_elementos += total_seccion

                desglose_por_seccion[sec.nombre] = {
                    "costo_insumos": float(base_seccion),
                    "costos_produccion": costos_produccion_detalle,
                    "total_costos_produccion": float(total_costos_produccion),
                    "subtotal": float(subtotal_seccion),
                    "pct_gastos_seccion": float(pct_gastos_sec),
                    "gasto_seccion": float(gasto_seccion),
                    "pct_negocio": float(pct_neg),
                    "costo_negocio": float(costo_negocio),
                    "total_seccion": float(total_seccion),
                }

            # El costo de producción es directamente la suma de secciones.
            # Cada sección ya incorpora sus propios gastos (pct_gastos_seccion).
            # NO se suman mano de obra ni gastos indirectos adicionales.
            costo_produccion_el = costo_total_elementos

            monto_imp_el, base_imp_el, precio_sin_iva_el, precio_con_iva_el = _aplicar_impuestos_y_ganancia(
                costo_produccion_el, ganancia_porcentaje, iva_porcentaje, impuesto_porcentaje
            )

            return {
                "producto_id": producto.id,
                "producto_nombre": producto.nombre,
                "dimensiones_base": {"ancho": float(ancho_base), "largo": float(largo_base)},
                "dimensiones_nuevas": {"ancho": float(nuevo_ancho), "largo": float(nuevo_largo)},
                "materiales": detalle_elementos,
                "materiales_detalle": detalle_elementos,
                "desglose_por_seccion": desglose_por_seccion,
                "resumen_costos": {
                    "costo_materiales": float(costo_total_elementos),
                    "costo_mano_obra": 0.0,
                    "costo_gastos": 0.0,
                    "costo_gastos_indirectos": 0.0,
                    "costo_produccion": float(costo_produccion_el),
                    "costo_total": float(costo_produccion_el),
                    "impuesto_porcentaje": float(impuesto_porcentaje),
                    "impuestos": float(monto_imp_el),
                    "base_con_impuestos": float(base_imp_el),
                    "ganancia_porcentaje": float(ganancia_porcentaje),
                    "precio_sin_iva": float(precio_sin_iva_el),
                    "iva_porcentaje": float(iva_porcentaje),
                    "precio_con_iva": float(precio_con_iva_el),
                    "precio_sugerido": float(precio_con_iva_el),
                    "precio_venta": float(precio_con_iva_el),
                },
                "costo_materiales": float(costo_total_elementos),
                "costo_mano_obra": 0.0,
                "costo_gastos": 0.0,
                "costo_gastos_indirectos": 0.0,
                "costo_produccion": float(costo_produccion_el),
                "costo_total": float(costo_produccion_el),
                "impuesto_porcentaje": float(impuesto_porcentaje),
                "impuestos": float(monto_imp_el),
                "base_con_impuestos": float(base_imp_el),
                "ganancia_porcentaje": float(ganancia_porcentaje),
                "precio_sin_iva": float(precio_sin_iva_el),
                "iva_porcentaje": float(iva_porcentaje),
                "precio_con_iva": float(precio_con_iva_el),
                "precio_sugerido": float(precio_con_iva_el),
                "precio_venta": float(precio_con_iva_el),
            }

        # Si el producto no tiene secciones ni receta pero sí precios fijos del
        # Excel, se usan como último recurso (NO antes de las secciones).
        if producto.precio_venta_base is not None:
            precio_sin_iva = Decimal(str(producto.precio_venta_base))
            precio_con_iva = redondear_precio_cop(
                Decimal(str(producto.precio_venta_con_iva)) if producto.precio_venta_con_iva else (precio_sin_iva * (Decimal("1") + iva_porcentaje / Decimal("100"))),
                "ceil",
            )
            costo_produccion = Decimal(str(producto.precio_costo_base)) if producto.precio_costo_base else (precio_sin_iva / (Decimal("1") + ganancia_porcentaje / Decimal("100")))
            costo_total_materiales = costo_produccion / (Decimal("1") + (pct_mano_obra + pct_gastos) / Decimal("100"))
            costo_mano_obra = costo_total_materiales * pct_mano_obra / Decimal("100")
            costo_gastos = costo_total_materiales * pct_gastos / Decimal("100")

            return {
                "producto_id": producto.id,
                "producto_nombre": producto.nombre,
                "dimensiones_base": {"ancho": float(ancho_base), "largo": float(largo_base)},
                "dimensiones_nuevas": {"ancho": float(nuevo_ancho), "largo": float(nuevo_largo)},
                "materiales": [],
                "materiales_detalle": [],
                "resumen_costos": {
                    "costo_materiales": float(costo_total_materiales),
                    "costo_mano_obra": float(costo_mano_obra),
                    "pct_mano_obra": float(pct_mano_obra),
                    "costo_gastos": float(costo_gastos),
                    "costo_gastos_indirectos": float(costo_gastos),
                    "pct_gastos": float(pct_gastos),
                    "costo_produccion": float(costo_produccion),
                    "costo_total": float(costo_produccion),
                    "impuesto_porcentaje": float(impuesto_porcentaje),
                    "impuestos": 0.0,
                    "base_con_impuestos": float(costo_produccion),
                    "ganancia_porcentaje": float(ganancia_porcentaje),
                    "precio_sin_iva": float(precio_sin_iva),
                    "iva_porcentaje": float(iva_porcentaje),
                    "precio_con_iva": float(precio_con_iva),
                    "precio_sugerido": float(precio_con_iva),
                    "precio_venta": float(precio_con_iva),
                },
                "costo_materiales": float(costo_total_materiales),
                "costo_mano_obra": float(costo_mano_obra),
                "costo_gastos": float(costo_gastos),
                "costo_gastos_indirectos": float(costo_gastos),
                "costo_produccion": float(costo_produccion),
                "costo_total": float(costo_produccion),
                "impuesto_porcentaje": float(impuesto_porcentaje),
                "impuestos": 0.0,
                "base_con_impuestos": float(costo_produccion),
                "ganancia_porcentaje": float(ganancia_porcentaje),
                "precio_sin_iva": float(precio_sin_iva),
                "iva_porcentaje": float(iva_porcentaje),
                "precio_con_iva": float(precio_con_iva),
                "precio_sugerido": float(precio_con_iva),
                "precio_venta": float(precio_con_iva),
            }

        return {
            "producto_id": producto.id,
            "producto_nombre": producto.nombre,
            "advertencia": "Este producto no tiene receta de materiales definida. Cargue la receta en producto_material o agregue insumos en las secciones.",
            "dimensiones_base": {"ancho": float(ancho_base), "largo": float(largo_base)},
            "dimensiones_nuevas": {"ancho": float(nuevo_ancho), "largo": float(nuevo_largo)},
            "materiales": [],
            "costo_materiales": 0.0,
            "costo_mano_obra": 0.0,
            "costo_gastos": 0.0,
            "costo_produccion": 0.0,
            "ganancia_porcentaje": float(ganancia_porcentaje),
            "precio_sin_iva": 0.0,
            "iva_porcentaje": float(iva_porcentaje),
            "precio_con_iva": 0.0,
        }

    # --- 3. Calcular cantidad de cada material ------------------------------
    costo_total_materiales = Decimal("0")
    detalle_materiales = []

    for pm in receta:
        material: Material = pm.material
        tipo          = pm.tipo_escala
        cantidad_base = Decimal(str(pm.cantidad_base))

        # 3a. Verificar condición de activación
        if pm.condicion_activacion:
            if not _evaluar_condicion(pm.condicion_activacion, nuevo_ancho, nuevo_largo, atributos):
                # Material no aplica para estas dimensiones
                detalle_materiales.append({
                    "material_id": material.id,
                    "material_nombre": material.nombre,
                    "nombre": material.nombre,  # Alias
                    "tipo_escala": tipo,
                    "condicion_activacion": pm.condicion_activacion,
                    "condicion_cumplida": False,
                    "cantidad_base": float(cantidad_base),
                    "cantidad_calculada": 0.0,
                    "unidad": material.unidad_medida.abreviatura if material.unidad_medida else "",
                    "costo_unitario": float(material.costo_base),
                    "costo_total": 0.0,
                    "costo_subtotal": 0.0,  # Alias
                    "observaciones": pm.observaciones,
                })
                continue

        # 3b. Override fijo
        if pm.es_fijo_override:
            cantidad = cantidad_base
        else:
            # 3c. Aplicar fórmula según tipo_escala
            if tipo == "FIJO":
                cantidad = cantidad_base

            elif tipo == "LINEAL":
                if largo_base == 0:
                    cantidad = cantidad_base
                else:
                    cantidad = cantidad_base * (nuevo_largo / largo_base)

            elif tipo == "AREA":
                if area_base == 0:
                    cantidad = cantidad_base
                else:
                    cantidad = cantidad_base * (area_nueva / area_base)

            elif tipo == "ESPACIADO":
                # Colocación a lo largo del perímetro
                distancia = (
                    Decimal(str(pm.distancia_pauta_cm))
                    if pm.distancia_pauta_cm
                    else Decimal("30")
                )
                por_pieza = pm.tornillos_por_pieza or 1

                perimetro_base = 2 * (largo_base + ancho_base)
                perimetro_nuevo = 2 * (nuevo_largo + nuevo_ancho)

                # Número de piezas = perímetro (en cm) / distancia + 1 (extremo)
                perimetro_nuevo_cm = perimetro_nuevo * 100
                perimetro_base_cm  = perimetro_base  * 100

                piezas_base  = perimetro_base_cm  / distancia + 1
                piezas_nuevas = perimetro_nuevo_cm / distancia + 1

                if piezas_base == 0:
                    cantidad = cantidad_base
                else:
                    # Escala en función de las piezas y la cantidad de tornillos/grapas por pieza
                    cantidad = (piezas_nuevas / piezas_base) * cantidad_base * Decimal(str(por_pieza))

            elif tipo == "POR_RANGO":
                resultado = _calcular_por_rango(pm.rangos, nuevo_largo)
                cantidad = resultado if resultado is not None else cantidad_base

            elif tipo == "FORMULA":
                # Placeholder: si hay fórmula personalizada, usar cantidad_base como fallback
                # (evaluación segura de expresiones matemáticas requiere un parser dedicado)
                cantidad = cantidad_base

            else:
                cantidad = cantidad_base  # tipo desconocido → usa base

        # Asegurar que la cantidad no sea negativa
        cantidad = max(Decimal("0"), _redondear(cantidad))

        costo_mat = _redondear(cantidad * Decimal(str(material.costo_base)), 2)
        costo_total_materiales += costo_mat

        detalle_materiales.append({
            "material_id": material.id,
            "material_nombre": material.nombre,
            "nombre": material.nombre,  # Alias
            "tipo_escala": tipo,
            "condicion_activacion": pm.condicion_activacion,
            "condicion_cumplida": True,
            "cantidad_base": float(cantidad_base),
            "cantidad_calculada": float(cantidad),
            "unidad": material.unidad_medida.abreviatura if material.unidad_medida else "",
            "costo_unitario": float(material.costo_base),
            "costo_total": float(costo_mat),
            "costo_subtotal": float(costo_mat),  # Alias
            "observaciones": pm.observaciones,
        })

    # --- 4. Calcular costos agregados ---------------------------------------
    costo_mano_obra = _redondear(costo_total_materiales * pct_mano_obra / Decimal("100"), 2)
    costo_gastos    = _redondear(costo_total_materiales * pct_gastos    / Decimal("100"), 2)
    costo_produccion = costo_total_materiales + costo_mano_obra + costo_gastos

    monto_impuestos, base_con_impuestos, precio_sin_iva, precio_con_iva = _aplicar_impuestos_y_ganancia(
        costo_produccion, ganancia_porcentaje, iva_porcentaje, impuesto_porcentaje
    )

    # --- 5. Resultado -------------------------------------------------------
    return {
        "producto_id": producto.id,
        "producto_nombre": producto.nombre,
        "dimensiones_base": {
            "ancho": float(ancho_base),
            "largo": float(largo_base),
        },
        "dimensiones_nuevas": {
            "ancho": float(nuevo_ancho),
            "largo": float(nuevo_largo),
        },
        "materiales": detalle_materiales,
        "materiales_detalle": detalle_materiales,  # Alias
        "resumen_costos": {
            "costo_materiales": float(costo_total_materiales),
            "costo_mano_obra": float(costo_mano_obra),
            "pct_mano_obra": float(pct_mano_obra),
            "costo_gastos": float(costo_gastos),
            "costo_gastos_indirectos": float(costo_gastos),  # Alias
            "pct_gastos": float(pct_gastos),
            "costo_produccion": float(costo_produccion),
            "costo_total": float(costo_produccion),  # Alias
            "impuesto_porcentaje": float(impuesto_porcentaje),
            "impuestos": float(monto_impuestos),
            "base_con_impuestos": float(base_con_impuestos),
            "ganancia_porcentaje": float(ganancia_porcentaje),
            "precio_sin_iva": float(precio_sin_iva),
            "iva_porcentaje": float(iva_porcentaje),
            "precio_con_iva": float(precio_con_iva),
            "precio_sugerido": float(precio_con_iva),  # Alias
            "precio_venta": float(precio_con_iva),  # Alias
        },
        # Campos de primer nivel para facilidad de consumo desde el frontend
        "costo_materiales": float(costo_total_materiales),
        "costo_mano_obra": float(costo_mano_obra),
        "costo_gastos": float(costo_gastos),
        "costo_gastos_indirectos": float(costo_gastos),  # Alias
        "costo_produccion": float(costo_produccion),
        "costo_total": float(costo_produccion),  # Alias
        "impuesto_porcentaje": float(impuesto_porcentaje),
        "impuestos": float(monto_impuestos),
        "base_con_impuestos": float(base_con_impuestos),
        "ganancia_porcentaje": float(ganancia_porcentaje),
        "precio_sin_iva": float(precio_sin_iva),
        "iva_porcentaje": float(iva_porcentaje),
        "precio_con_iva": float(precio_con_iva),
        "precio_sugerido": float(precio_con_iva),  # Alias
        "precio_venta": float(precio_con_iva),  # Alias
    }


# ---------------------------------------------------------------------------
# Recálculo automático de precios de productos (anti-inflación)
# ---------------------------------------------------------------------------
# Cuando el costo de un insumo cambia, actualizamos `precio_costo_base` y
# `precio_venta_base` de los productos que lo usan SIN inflar precios:
#
#   - Productos con SECCIONES: se recalcula el costo completo con los precios
#     vivos de los insumos (la estructura ya incluye mano de obra, %gastos y
#     %negocio por sección). Es exacto.
#
#   - Productos con RECETA PLANA: se ESCALA el costo del Excel proporcionalmente
#     al cambio de los materiales (S1 = S0 × M1/M0), conservando la proporción
#     de mano de obra/gastos que ya tenía el Excel. NUNCA se apilan porcentajes.
#
#   - GUARDA anti-inflación: si el costo nuevo difiere más de 30% del actual,
#     el producto NO se aplica y queda marcado `requiere_revision` para que el
#     dueño lo revise en la vista previa.
UMBRAL_CAMBIO_PORCENTAJE = Decimal("30")

def _costo_materiales_actuales(db: Session, producto: Producto) -> Decimal:
    """Suma el costo de los materiales de la receta plana a medidas base con
    los precios VIGENTES de cada insumo."""
    total = Decimal("0")
    ancho_base = Decimal(str(producto.ancho_base)) if producto.ancho_base else Decimal("1.60")
    largo_base = Decimal(str(producto.largo_base)) if producto.largo_base else Decimal("1.90")
    area_base = ancho_base * largo_base
    for pm in db.query(ProductoMaterial).filter(ProductoMaterial.producto_id == producto.id).all():
        material = pm.material
        if material is None or not material.costo_base:
            continue
        cantidad = _calcular_cantidad_material(
            pm, ancho_base, largo_base, ancho_base, largo_base,
            area_base, area_base, None,
        )
        total += cantidad * Decimal(str(material.costo_base))
    return total


def _costo_plana_fallback(db: Session, producto: Producto) -> Decimal:
    """Costo de receta plana con la fórmula del Excel: Σ materiales × (1 + %gastos
    por sección). No apila mano de obra ni gastos indirectos adicionales."""
    ancho_base = Decimal(str(producto.ancho_base)) if producto.ancho_base else Decimal("1.60")
    largo_base = Decimal(str(producto.largo_base)) if producto.largo_base else Decimal("1.90")
    area_base = ancho_base * largo_base
    reglas = {r.seccion: Decimal(str(r.porcentaje_gasto)) for r in db.query(ReglaGastoSeccion).all()}
    costo_por_seccion: dict[str, Decimal] = {}
    for pm in db.query(ProductoMaterial).filter(ProductoMaterial.producto_id == producto.id).all():
        material = pm.material
        if material is None or not material.costo_base:
            continue
        cantidad = _calcular_cantidad_material(
            pm, ancho_base, largo_base, ancho_base, largo_base,
            area_base, area_base, None,
        )
        sec = _normalizar_seccion(pm.seccion)
        costo_por_seccion[sec] = costo_por_seccion.get(sec, Decimal("0")) + cantidad * Decimal(str(material.costo_base))
    total = Decimal("0")
    for sec, base in costo_por_seccion.items():
        pct = reglas.get(sec, Decimal("0"))
        total += base + _redondear(base * pct / Decimal("100"), 2)
    return total


def _producto_usa_secciones(db: Session, producto_id: int) -> bool:
    return db.query(SeccionProducto.id).filter(SeccionProducto.producto_id == producto_id).first() is not None


def productos_que_usan_material(db: Session, id_material: int) -> list[int]:
    """Ids de productos (receta plana o secciones) que referencian un material."""
    ids = set()
    for (pid,) in db.query(ProductoMaterial.producto_id).filter(ProductoMaterial.material_id == id_material).all():
        ids.add(pid)
    for (pid,) in (
        db.query(SeccionProducto.producto_id)
        .join(ElementoSeccion, ElementoSeccion.seccion_id == SeccionProducto.id)
        .filter(ElementoSeccion.material_id_normalizado == id_material)
        .all()
    ):
        ids.add(pid)
    return sorted(ids)


def _guardar_snapshot(db: Session, producto: Producto, costo_nuevo: Decimal, precio_nuevo: Decimal) -> None:
    producto.precio_costo_base = _redondear(costo_nuevo, 2)
    # Precios de venta siempre al millar COP (hacia arriba para no erosionar margen).
    producto.precio_venta_base = redondear_precio_cop(precio_nuevo, "ceil")
    producto.precio_venta_con_iva = redondear_precio_cop(precio_nuevo, "ceil")  # IVA de muebles 0% por defecto


def recalcular_precios_productos(
    db: Session,
    producto_ids: list[int] | None = None,
    aplicar: bool = False,
    ganancia_porcentaje: Decimal = Decimal("40"),
    iva_porcentaje: Decimal = Decimal("0"),
    impuesto_porcentaje: Decimal = IMPUESTOS_PCT_DEFAULT,
) -> list[dict]:
    """Vista previa (aplicar=False) o recálculo real (aplicar=True) de los precios
    base de productos con receta. Devuelve por producto el antes → después y si se
    aplicó o quedó en revisión."""
    resultados = []
    if producto_ids is None:
        planos = [pid for (pid,) in db.query(ProductoMaterial.producto_id).distinct().all()]
        jerarquicos = [pid for (pid,) in db.query(SeccionProducto.producto_id).distinct().all()]
        producto_ids = sorted(set(planos) | set(jerarquicos))

    for pid in producto_ids:
        producto = db.query(Producto).filter(Producto.id == pid).first()
        if not producto:
            continue
        costo_anterior = Decimal(str(producto.precio_costo_base)) if producto.precio_costo_base is not None else None
        precio_anterior = Decimal(str(producto.precio_venta_base)) if producto.precio_venta_base is not None else None

        if _producto_usa_secciones(db, pid):
            tipo = "secciones"
            ancho = Decimal(str(producto.ancho_base)) if producto.ancho_base else Decimal("1.60")
            largo = Decimal(str(producto.largo_base)) if producto.largo_base else Decimal("1.90")
            calc = calcular_costo_producto(
                db, pid, ancho, largo,
                ganancia_porcentaje=ganancia_porcentaje,
                iva_porcentaje=iva_porcentaje,
                impuesto_porcentaje=impuesto_porcentaje,
            )
            costo_nuevo = Decimal(str(calc["costo_produccion"]))
            precio_nuevo = Decimal(str(calc["precio_venta"]))
            # Guarda anti-inflación también aquí: si el snapshot estaba muy
            # desactualizado (>30%), no se aplica solo; se revisa en la vista previa.
            requiere_revision = (
                costo_anterior is not None and costo_anterior > 0
                and abs(costo_nuevo / costo_anterior - Decimal("1")) * Decimal("100") > UMBRAL_CAMBIO_PORCENTAJE
            )
        else:
            tipo = "plana"
            costo_nuevo = _costo_plana_fallback(db, producto)
            monto_imp, base_imp, precio_sin_iva, precio_con_iva = _aplicar_impuestos_y_ganancia(
                costo_nuevo, ganancia_porcentaje, iva_porcentaje, impuesto_porcentaje
            )
            precio_nuevo = precio_con_iva
            # Guarda anti-inflación sobre el costo actual (si existe)
            requiere_revision = (
                costo_anterior is not None and costo_anterior > 0
                and abs(costo_nuevo / costo_anterior - Decimal("1")) * Decimal("100") > UMBRAL_CAMBIO_PORCENTAJE
            )

        pct_cambio = None
        if costo_anterior and costo_anterior > 0:
            pct_cambio = float((costo_nuevo / costo_anterior - Decimal("1")) * Decimal("100"))

        aplicado = False
        if aplicar and not requiere_revision:
            _guardar_snapshot(db, producto, costo_nuevo, precio_nuevo)
            aplicado = True

        resultados.append({
            "producto_id": producto.id,
            "producto_nombre": producto.nombre,
            "tipo": tipo,
            "costo_anterior": float(costo_anterior) if costo_anterior is not None else None,
            "costo_nuevo": float(costo_nuevo),
            "precio_anterior": float(precio_anterior) if precio_anterior is not None else None,
            "precio_nuevo": float(precio_nuevo),
            "pct_cambio": pct_cambio,
            "requiere_revision": bool(requiere_revision),
            "aplicado": aplicado,
        })

    if aplicar:
        db.commit()
    return resultados


def recalcular_tras_cambio_material(
    db: Session,
    id_material: int,
    costo_viejo: Decimal | None,
    costo_nuevo: Decimal | None,
) -> list[dict]:
    """Hook llamado al actualizar un material: recalcula (con cuidado) los
    productos que lo usan. Para recetas planas ESCALA el costo del Excel por el
    cambio de materiales; para secciones recalcula el costo completo."""
    if costo_viejo is None or costo_nuevo is None or costo_viejo == costo_nuevo:
        return []
    resultados = []
    for pid in productos_que_usan_material(db, id_material):
        producto = db.query(Producto).filter(Producto.id == pid).first()
        if not producto:
            continue
        costo_anterior = Decimal(str(producto.precio_costo_base)) if producto.precio_costo_base is not None else None
        precio_anterior = Decimal(str(producto.precio_venta_base)) if producto.precio_venta_base is not None else None

        if _producto_usa_secciones(db, pid):
            # Recalcular completo (exacto): ya refleja el precio vivo del insumo.
            ancho = Decimal(str(producto.ancho_base)) if producto.ancho_base else Decimal("1.60")
            largo = Decimal(str(producto.largo_base)) if producto.largo_base else Decimal("1.90")
            calc = calcular_costo_producto(db, pid, ancho, largo)
            costo_nuevo_p = Decimal(str(calc["costo_produccion"]))
            precio_nuevo_p = Decimal(str(calc["precio_venta"]))
            requiere_revision = (
                costo_anterior is not None and costo_anterior > 0
                and abs(costo_nuevo_p / costo_anterior - Decimal("1")) * Decimal("100") > UMBRAL_CAMBIO_PORCENTAJE
            )
        else:
            # Escalar el costo del Excel proporcionalmente al cambio de materiales.
            m1 = _costo_materiales_actuales(db, producto)
            m0 = m1
            for pm in db.query(ProductoMaterial).filter(ProductoMaterial.producto_id == pid, ProductoMaterial.material_id == id_material).all():
                material = pm.material
                if material is None or not material.costo_base:
                    continue
                cantidad = _calcular_cantidad_material(
                    pm,
                    Decimal(str(producto.ancho_base)) if producto.ancho_base else Decimal("1.60"),
                    Decimal(str(producto.largo_base)) if producto.largo_base else Decimal("1.90"),
                    Decimal(str(producto.ancho_base)) if producto.ancho_base else Decimal("1.60"),
                    Decimal(str(producto.largo_base)) if producto.largo_base else Decimal("1.90"),
                    (Decimal(str(producto.ancho_base)) if producto.ancho_base else Decimal("1.60")) * (Decimal(str(producto.largo_base)) if producto.largo_base else Decimal("1.90")),
                    (Decimal(str(producto.ancho_base)) if producto.ancho_base else Decimal("1.60")) * (Decimal(str(producto.largo_base)) if producto.largo_base else Decimal("1.90")),
                    None,
                )
                m0 = m0 - cantidad * (costo_nuevo - costo_viejo)

            if costo_anterior is not None and m0 > 0:
                costo_nuevo_p = _redondear(costo_anterior * m1 / m0, 2)
            else:
                costo_nuevo_p = _costo_plana_fallback(db, producto)
            _, _, precio_sin_iva, precio_con_iva = _aplicar_impuestos_y_ganancia(
                costo_nuevo_p, Decimal("40"), Decimal("0"), IMPUESTOS_PCT_DEFAULT
            )
            precio_nuevo_p = precio_con_iva
            requiere_revision = (
                costo_anterior is not None and costo_anterior > 0
                and abs(costo_nuevo_p / costo_anterior - Decimal("1")) * Decimal("100") > UMBRAL_CAMBIO_PORCENTAJE
            )

        pct_cambio = None
        if costo_anterior and costo_anterior > 0:
            pct_cambio = float((costo_nuevo_p / costo_anterior - Decimal("1")) * Decimal("100"))

        aplicado = False
        if not requiere_revision:
            _guardar_snapshot(db, producto, costo_nuevo_p, precio_nuevo_p)
            aplicado = True

        resultados.append({
            "producto_id": producto.id,
            "producto_nombre": producto.nombre,
            "tipo": "secciones" if _producto_usa_secciones(db, pid) else "plana",
            "costo_anterior": float(costo_anterior) if costo_anterior is not None else None,
            "costo_nuevo": float(costo_nuevo_p),
            "precio_anterior": float(precio_anterior) if precio_anterior is not None else None,
            "precio_nuevo": float(precio_nuevo_p),
            "pct_cambio": pct_cambio,
            "requiere_revision": bool(requiere_revision),
            "aplicado": aplicado,
        })

    db.commit()
    return resultados
