// Normaliza las distintas respuestas del costeo (receta plana, receta por
// secciones y la del cotizador IA) a un objeto único tipo "ESTRUCTURA DE
// COSTOS" para renderizarla como documento estilo Excel.
//
// Secciones con nombre COMO EL SISTEMA (EBANISTERÍA (CAMA), PINTURA (CAMA),
// TERMINACIÓN, TENDIDO, TAPICERÍA...). Cada sección trae filas de insumos,
// líneas de % producción, subtotal, % gastos y total de sección.

export interface FilaCosto {
  id: string;
  concepto: string;
  cantidad?: number;
  unidad?: string;
  v_unit?: number;
  total: number;
  tipo: 'insumo' | 'produccion' | 'subtotal' | 'gastos' | 'negocio' | 'total_seccion';
  nota?: string;
}

export interface SeccionCostoExcel {
  nombre: string;
  filas: FilaCosto[];
  subtotal: number;
  pct_gastos: number;
  gastos: number;
  pct_negocio: number;
  negocio: number;
  total: number;
}

export interface EstructuraCostos {
  producto_id: number;
  producto_nombre: string;
  dimensiones: { ancho: number; largo: number } | null;
  secciones: SeccionCostoExcel[];
  total_produccion: number;
  sin_desglose: boolean;
  nota?: string;
  resumen: {
    costo_total: number;
    ganancia_porcentaje: number;
    ganancia_monto: number;
    precio_venta: number;
    iva_porcentaje: number;
    precio_con_iva: number;
    impuesto_porcentaje: number;
    impuestos: number;
  };
}

const num = (v: unknown): number => (typeof v === 'number' ? v : Number(v ?? 0) || 0);

function normalizarNombreSeccion(nombre: string): string {
  return nombre.normalize('NFD').replace(/[\u0300-\u036f]/g, '').toUpperCase().trim();
}

// Secciones de Shape A (planas): claves normalizadas "EBANISTERIA", "PINTURA"...
// Shape nested: ítems y claves comparten el nombre EXACTO de la sección.
function coincideSeccion(clave: string, nombreFila: string): boolean {
  const a = normalizarNombreSeccion(clave);
  const b = normalizarNombreSeccion(nombreFila);
  // Shape A plana: ítem normalizado a "NOCHEROS" cae en la sección que lo contiene
  if (b === 'NOCHEROS') return a.includes('NOCHEROS');
  // Igualdad exacta (nested) o coincidencia por la base antes del "(" (plana)
  if (a === b) return true;
  const baseA = a.split('(')[0].trim();
  const baseB = b.split('(')[0].trim();
  return baseA !== '' && (baseA === baseB || a.includes(baseB) || baseB.includes(baseA));
}

function construirResumen(data: Record<string, any>): EstructuraCostos['resumen'] {
  const g = num(data.ganancia_porcentaje ?? data.resumen_costos?.ganancia_porcentaje);
  const costo = num(data.costo_total ?? data.resumen_costos?.costo_total);
  const precio = num(data.precio_con_iva ?? data.resumen_costos?.precio_con_iva ?? data.precio_venta);
  return {
    costo_total: num(data.costo_total ?? data.resumen_costos?.costo_total ?? data.costo_produccion),
    ganancia_porcentaje: g,
    ganancia_monto: precio > 0 && g > 0 ? precio - precio / (1 + g / 100) : 0,
    precio_venta: num(data.precio_venta ?? data.resumen_costos?.precio_venta ?? precio),
    iva_porcentaje: num(data.iva_porcentaje ?? data.resumen_costos?.iva_porcentaje),
    precio_con_iva: precio,
    impuesto_porcentaje: num(data.impuesto_porcentaje ?? data.resumen_costos?.impuesto_porcentaje),
    impuestos: num(data.impuestos ?? data.resumen_costos?.impuestos),
  };
}

function filasDesdeInsumos(
  insumos: any[] | undefined,
  nombreSeccion: string,
  idBase: string,
  exacto = false,
): FilaCosto[] {
  return (insumos ?? [])
    .filter((m) => {
      if (m.es_nochero || !m.seccion) return false;
      if (!exacto) return coincideSeccion(nombreSeccion, String(m.seccion));
      // Shape nested: ítems y secciones comparten el nombre EXACTO (la pieza
      // va entre paréntesis). Sin esto, los insumos de "EBANISTERÍA (NOCHEROS)"
      // caerían también en "EBANISTERÍA (CAMA)" por coincidir en la base.
      const a = normalizarNombreSeccion(nombreSeccion);
      const b = normalizarNombreSeccion(String(m.seccion));
      return a === b || (b === 'NOCHEROS' && a.includes('NOCHEROS'));
    })
    .map((m, i) => ({
      id: `${idBase}-ins-${i}`,
      concepto: String(m.material_nombre ?? m.nombre ?? m.nombre_insumo_original ?? 'Insumo'),
      cantidad: num(m.cantidad_calculada ?? m.cantidad ?? m.cantidad_base),
      unidad: String(m.unidad_medida ?? m.unidad ?? ''),
      v_unit: num(m.costo_unitario ?? m.costo_subtotal),
      total: num(m.costo_total ?? m.costo_subtotal),
      tipo: 'insumo' as const,
    }));
}

function construirSeccionNested(
  nombre: string,
  s: any,
  insumos: any[],
): SeccionCostoExcel {
  const filas: FilaCosto[] = filasDesdeInsumos(insumos, nombre, s.id ?? nombre, true);
  (s.costos_produccion ?? []).forEach((cp: any, i: number) => {
    filas.push({
      id: `${nombre}-cp-${i}`,
      concepto: num(cp.porcentaje) > 0 ? `${cp.nombre} (${num(cp.porcentaje)}%)` : String(cp.nombre),
      v_unit: num(cp.aporte),
      total: num(cp.aporte),
      tipo: 'produccion',
    });
  });
  filas.push({ id: `${nombre}-sub`, concepto: 'Sub total', total: num(s.subtotal), tipo: 'subtotal' });
  if (num(s.gasto_seccion) !== 0 || num(s.pct_gastos_seccion) !== 0) {
    filas.push({
      id: `${nombre}-gas`,
      concepto: `Gastos de sección (${num(s.pct_gastos_seccion)}%)`,
      total: num(s.gasto_seccion),
      tipo: 'gastos',
    });
  }
  if (num(s.costo_negocio) !== 0 || num(s.pct_negocio) !== 0) {
    filas.push({
      id: `${nombre}-neg`,
      concepto: `% Negocio (${num(s.pct_negocio)}%)`,
      total: num(s.costo_negocio),
      tipo: 'negocio',
    });
  }
  filas.push({ id: `${nombre}-tot`, concepto: 'Total sección', total: num(s.total_seccion), tipo: 'total_seccion' });
  return {
    nombre,
    filas,
    subtotal: num(s.subtotal),
    pct_gastos: num(s.pct_gastos_seccion),
    gastos: num(s.gasto_seccion),
    pct_negocio: num(s.pct_negocio),
    negocio: num(s.costo_negocio),
    total: num(s.total_seccion),
  };
}

function construirSeccionPlana(
  nombre: string,
  s: any,
  insumos: any[],
): SeccionCostoExcel {
  const filas: FilaCosto[] = filasDesdeInsumos(insumos, nombre, s.id ?? nombre);
  const nota = s.nota ? String(s.nota) : undefined;
  filas.push({ id: `${nombre}-sub`, concepto: 'Sub total', total: num(s.costo_base), tipo: 'subtotal', nota });
  if (num(s.porcentaje_gasto) > 0) {
    filas.push({
      id: `${nombre}-gas`,
      concepto: `Gastos de sección (${num(s.porcentaje_gasto)}%)`,
      total: num(s.gasto_aplicado),
      tipo: 'gastos',
    });
  }
  filas.push({ id: `${nombre}-tot`, concepto: 'Total sección', total: num(s.total ?? s.costo_base), tipo: 'total_seccion', nota });
  return {
    nombre,
    filas,
    subtotal: num(s.costo_base),
    pct_gastos: num(s.porcentaje_gasto),
    gastos: num(s.gasto_aplicado),
    pct_negocio: 0,
    negocio: 0,
    total: num(s.total ?? s.costo_base),
  };
}

// IQE / Cotizador IA: { secciones: [{seccion, subtotal, items:[{nombre,cantidad,unidad,costo_unitario,costo_total}]}], resumen }
export function normalizarEstructuraIQE(data: any): EstructuraCostos {
  const secciones: SeccionCostoExcel[] = (data?.secciones ?? []).map((s: any) => {
    const filas: FilaCosto[] = (s.items ?? [])
      .filter((it: any) => it.activo !== false)
      .map((it: any, i: number) => ({
        id: `${s.seccion}-iqe-${i}`,
        concepto: String(it.nombre),
        cantidad: num(it.cantidad),
        unidad: String(it.unidad ?? ''),
        v_unit: num(it.costo_unitario),
        total: num(it.costo_total),
        tipo: 'insumo' as const,
      }));
    filas.push({ id: `${s.seccion}-sub`, concepto: 'Sub total', total: num(s.subtotal), tipo: 'subtotal' });
    filas.push({ id: `${s.seccion}-tot`, concepto: 'Total sección', total: num(s.subtotal), tipo: 'total_seccion' });
    return {
      nombre: String(s.seccion),
      filas,
      subtotal: num(s.subtotal),
      pct_gastos: 0,
      gastos: 0,
      pct_negocio: 0,
      negocio: 0,
      total: num(s.subtotal),
    };
  });
  const r = data?.resumen ?? {};
  return {
    producto_id: num(data?.producto_base_id ?? 0),
    producto_nombre: String(data?.producto_base_nombre ?? 'Estructura'),
    dimensiones: null,
    secciones,
    total_produccion: secciones.reduce((s, x) => s + x.total, 0),
    sin_desglose: secciones.length === 0,
    resumen: {
      costo_total: num(r.costo_produccion ?? r.costo_total),
      ganancia_porcentaje: num(r.ganancia_porcentaje),
      ganancia_monto: 0,
      precio_venta: num(r.precio_sin_iva ?? r.precio_venta),
      iva_porcentaje: num(r.iva_porcentaje),
      precio_con_iva: num(r.precio_con_iva),
      impuesto_porcentaje: num(r.impuesto_porcentaje),
      impuestos: num(r.impuestos),
    },
  };
}

export function normalizarEstructuraCostos(data: any): EstructuraCostos {
  // IQE
  if (Array.isArray(data?.secciones) && data?.resumen) {
    return normalizarEstructuraIQE(data);
  }

  const desglose = data?.desglose_por_seccion ?? {};
  const claves = Object.keys(desglose);
  const insumos: any[] = data?.materiales_detalle ?? data?.materiales ?? [];
  const secciones: SeccionCostoExcel[] = claves.map((clave) => {
    const s = desglose[clave];
    // Nested (receta por secciones): tiene total_seccion
    if ('total_seccion' in s) {
      return construirSeccionNested(clave, s, insumos);
    }
    // Plana: tiene costo_base + porcentaje_gasto
    return construirSeccionPlana(clave, s, insumos);
  });

  const resumen = construirResumen(data);
  const total = num(data.costo_produccion ?? data.resumen_costos?.costo_produccion ?? resumen.costo_total);

  return {
    producto_id: num(data.producto_id),
    producto_nombre: String(data.producto_nombre ?? 'Producto'),
    dimensiones:
      data.dimensiones_base
        ? { ancho: num(data.dimensiones_base.ancho), largo: num(data.dimensiones_base.largo) }
        : null,
    secciones,
    total_produccion: secciones.reduce((s, x) => s + x.total, 0) || total,
    sin_desglose: secciones.length === 0,
    nota: claves.length ? (desglose[claves[0]].nota ? String(desglose[claves[0]].nota) : undefined) : undefined,
    resumen,
  };
}
