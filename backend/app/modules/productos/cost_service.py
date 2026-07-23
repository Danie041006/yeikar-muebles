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

from decimal import Decimal, ROUND_HALF_UP
from sqlalchemy.orm import Session
from app.modules.productos.model import Producto, ProductoMaterial, Material, ReglaGastoSeccion


# ---------------------------------------------------------------------------
# Utilidades internas
# ---------------------------------------------------------------------------

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
            costo_linea = pm.cantidad_base * Decimal(str(material.costo_base))
            seccion = (pm.seccion or "EBANISTERIA").upper()
            es_nochero = seccion == "NOCHEROS"

            item = {
                "material_id": material.id,
                "material_nombre": material.nombre,
                "nombre": material.nombre,
                "tipo_escala": pm.tipo_escala,
                "seccion": seccion,
                "condicion_activacion": pm.condicion_activacion,
                "condicion_cumplida": True,
                "cantidad_base": float(pm.cantidad_base),
                "cantidad_calculada": float(pm.cantidad_base),
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

        # Precio de venta con margen de ganancia e IVA sobre el costo de producción real
        precio_sin_iva = _redondear(costo_produccion * (Decimal("1") + ganancia_porcentaje / Decimal("100")), 2)
        precio_con_iva = _redondear(precio_sin_iva * (Decimal("1") + iva_porcentaje / Decimal("100")), 2)

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
            "ganancia_porcentaje": float(ganancia_porcentaje),
            "precio_sin_iva": float(precio_sin_iva),
            "iva_porcentaje": float(iva_porcentaje),
            "precio_con_iva": float(precio_con_iva),
            "precio_sugerido": float(precio_con_iva),
            "precio_venta": float(precio_con_iva),
            "costo_nochero": float(costo_nochero),
        }
        return resultado

    # Si por alguna razón el producto no tiene receta cargada, usamos los valores fijos del Excel como fallback
    elif producto.precio_venta_base is not None:
        precio_sin_iva = Decimal(str(producto.precio_venta_base))
        precio_con_iva = Decimal(str(producto.precio_venta_con_iva)) if producto.precio_venta_con_iva else (precio_sin_iva * (Decimal("1") + iva_porcentaje / Decimal("100")))
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
            "ganancia_porcentaje": float(ganancia_porcentaje),
            "precio_sin_iva": float(precio_sin_iva),
            "iva_porcentaje": float(iva_porcentaje),
            "precio_con_iva": float(precio_con_iva),
            "precio_sugerido": float(precio_con_iva),
            "precio_venta": float(precio_con_iva),
        }

    # --- 2. Cargar receta de materiales ------------------------------------
    receta: list[ProductoMaterial] = (
        db.query(ProductoMaterial)
        .filter(ProductoMaterial.producto_id == producto_id)
        .all()
    )

    if not receta:
        return {
            "producto_id": producto.id,
            "producto_nombre": producto.nombre,
            "advertencia": "Este producto no tiene receta de materiales definida. Cargue la receta en producto_material.",
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

    precio_sin_iva = _redondear(costo_produccion * (Decimal("1") + ganancia_porcentaje / Decimal("100")), 2)
    precio_con_iva = _redondear(precio_sin_iva   * (Decimal("1") + iva_porcentaje      / Decimal("100")), 2)

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
        "ganancia_porcentaje": float(ganancia_porcentaje),
        "precio_sin_iva": float(precio_sin_iva),
        "iva_porcentaje": float(iva_porcentaje),
        "precio_con_iva": float(precio_con_iva),
        "precio_sugerido": float(precio_con_iva),  # Alias
        "precio_venta": float(precio_con_iva),  # Alias
    }
