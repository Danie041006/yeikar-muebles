import api from './api';

export interface PnLDetail {
  moneda: string;
  ingresos: number;
  gastos: number;
  balance: number;
  ingresos_cop?: number;
  gastos_cop?: number;
  balance_cop?: number;
}

export interface PnLResponse {
  mes: string;
  detalles: PnLDetail[];
}

export interface RentabilidadProductoResponse {
  producto_id: number;
  producto_nombre: string;
  cantidad_vendida: number;
  precio_promedio_venta: number;
  costo_promedio_produccion: number;
  margen_promedio: number;
  moneda: string;
}

export interface ReportAlertaStockResponse {
  material_id: number;
  material_nombre: string;
  cantidad_actual: number;
  umbral: number;
  unidad_medida: string;
  ubicacion_nombre: string;
}

// ---------------- Estado del día (reporte diario) ----------------
export interface MovimientoDiario {
  id: number;
  tipo: string; // APERTURA | ENTRADA | SALIDA | AJUSTE
  moneda_codigo: string;
  moneda_simbolo: string;
  monto: number;
  monto_cop: number;
  cuenta_nombre?: string | null;
  referencia?: string | null;
  concepto: string;
  quien?: string | null;
}

export interface LineaMonedaDiaria {
  moneda_id: number;
  codigo: string;
  simbolo: string;
  monto_ingresos: number;
  monto_egresos: number;
  monto_cop: number;
}

export interface SaldoCuentaDiaria {
  metodo_caja_id: number;
  cuenta_nombre: string;
  saldo_inicial_cop: number;
  saldo_final_cop: number;
}

export interface ResumenDiario {
  fecha: string;
  saldo_inicial_cop: number;
  total_ingresos_cop: number;
  total_egresos_cop: number;
  saldo_final_cop: number;
  movimientos: MovimientoDiario[];
  por_moneda: LineaMonedaDiaria[];
  saldos_por_cuenta: SaldoCuentaDiaria[];
}

export const reportesService = {
  getPnL: async (mes: string): Promise<PnLResponse> => {
    const response = await api.get<PnLResponse>('/reports/pnl', {
      params: { mes },
    });
    return response.data;
  },

  getRentabilidad: async (): Promise<RentabilidadProductoResponse[]> => {
    const response = await api.get<RentabilidadProductoResponse[]>('/reports/rentabilidad-producto');
    return response.data;
  },

  getAlertasStock: async (umbral: number = 5.0): Promise<ReportAlertaStockResponse[]> => {
    const response = await api.get<ReportAlertaStockResponse[]>('/reports/alertas-stock', {
      params: { umbral },
    });
    return response.data;
  },

  // ---------------- Informe Mensual ----------------
  getInformeMensual: async (mes: string): Promise<InformeMensualResponse> => {
    const response = await api.get<InformeMensualResponse>('/reports/informe-mensual', { params: { mes } });
    return response.data;
  },

  // ---------------- Estado del día ----------------
  getResumenDiario: async (fecha?: string): Promise<ResumenDiario> => {
    const response = await api.get<ResumenDiario>('/reports/diario', { params: fecha ? { fecha } : {} });
    return response.data;
  },

  // Conceptos (líneas de inventario configurables)
  getConceptos: async (seccion?: string): Promise<ConceptoReporte[]> => {
    const response = await api.get<ConceptoReporte[]>('/reports/conceptos', { params: { seccion } });
    return response.data;
  },
  crearConcepto: async (data: { nombre: string; seccion?: string; orden?: number }): Promise<ConceptoReporte> => {
    const response = await api.post<ConceptoReporte>('/reports/conceptos', data);
    return response.data;
  },
  actualizarConcepto: async (id: number, data: Partial<ConceptoReporte>): Promise<ConceptoReporte> => {
    const response = await api.put<ConceptoReporte>(`/reports/conceptos/${id}`, data);
    return response.data;
  },
  eliminarConcepto: async (id: number): Promise<void> => {
    await api.delete(`/reports/conceptos/${id}`);
  },

  // Valores mensuales (corte de inventario)
  getValoresMensuales: async (mes: string): Promise<ValorConceptoMensual[]> => {
    const response = await api.get<ValorConceptoMensual[]>('/reports/valores-mensuales', { params: { mes } });
    return response.data;
  },
  guardarValoresMensuales: async (mes: string, valores: ValorConceptoMensual[]): Promise<ValorConceptoMensual[]> => {
    const response = await api.put<ValorConceptoMensual[]>(`/reports/valores-mensuales/${mes}`, valores);
    return response.data;
  },

  // Métodos de caja
  getMetodosCaja: async (): Promise<MetodoCaja[]> => {
    const response = await api.get<MetodoCaja[]>('/reports/metodos-caja');
    return response.data;
  },
  crearMetodoCaja: async (data: { nombre: string; codigo: string }): Promise<MetodoCaja> => {
    const response = await api.post<MetodoCaja>('/reports/metodos-caja', data);
    return response.data;
  },

  // Movimientos de caja
  getMovimientosCaja: async (params?: { metodo_caja_id?: number; fecha_desde?: string; fecha_hasta?: string }): Promise<MovimientoCaja[]> => {
    const response = await api.get<MovimientoCaja[]>('/reports/movimientos-caja', { params });
    return response.data;
  },
  crearMovimientoCaja: async (data: {
    metodo_caja_id: number;
    fecha: string;
    tipo: 'APERTURA' | 'ENTRADA' | 'SALIDA' | 'AJUSTE';
    monto: number;
    moneda_id: number;
    tasa_cambio?: number;
    referencia?: string;
    observaciones?: string;
  }): Promise<MovimientoCaja> => {
    const response = await api.post<MovimientoCaja>('/reports/movimientos-caja', data);
    return response.data;
  },
  eliminarMovimientoCaja: async (id: number): Promise<void> => {
    await api.delete(`/reports/movimientos-caja/${id}`);
  },

  // Devoluciones de venta
  getDevoluciones: async (params?: { fecha_desde?: string; fecha_hasta?: string }): Promise<DevolucionVenta[]> => {
    const response = await api.get<DevolucionVenta[]>('/reports/devoluciones', { params });
    return response.data;
  },
  crearDevolucion: async (data: {
    venta_id: number;
    detalle_venta_id?: number;
    fecha: string;
    cantidad?: number;
    motivo?: string;
    monto_devuelto: number;
    moneda_id: number;
    tasa_cambio?: number;
  }): Promise<DevolucionVenta> => {
    const response = await api.post<DevolucionVenta>('/reports/devoluciones', data);
    return response.data;
  },
  eliminarDevolucion: async (id: number): Promise<void> => {
    await api.delete(`/reports/devoluciones/${id}`);
  },
};

// ---------------- Tipos ----------------
export interface LineaIngresoInforme {
  fecha: string;
  cliente: string;
  cantidad: number;
  producto: string;
  costo_unitario: number;
  precio_costo: number;
  porcentaje_ganancia: number | null;
  utilidad: number;
  precio_venta: number;
  descuento: number;
  moneda: string;
  tasa_cambio: number;
  precio_venta_en_base: number;
  es_devolucion: boolean;
}

export interface TotalesIngresoInforme {
  precio_costo: number;
  utilidad: number;
  precio_venta: number;
  precio_venta_en_base: number;
  descuentos: number;
}

export interface ControlInternoIngresos {
  lineas: LineaIngresoInforme[];
  totales: TotalesIngresoInforme;
}

export interface ResumenMes {
  ingresos: number;
  egresos: number;
  disponible: number;
}

export interface LineaValorConcepto {
  concepto_id: number;
  nombre: string;
  valor: number;
}

export interface VentasEstadoResultados {
  contado: number;
  credito: number;
  extraordinarias: number;
  devoluciones: number;
  descuentos: number;
  total_ventas_netas: number;
}

export interface ComprasEstadoResultados {
  contado: number;
  credito: number;
  total_compras_brutas: number;
  total_mercancia: number;
}

export interface LineaGastoInforme {
  tipo_id: number;
  nombre: string;
  monto: number;
}

export interface GastosEstadoResultados {
  operativos: LineaGastoInforme[];
  administrativos: LineaGastoInforme[];
  financieros: LineaGastoInforme[];
  impuestos: LineaGastoInforme[];
  produccion?: LineaGastoInforme[];
  total_gastos_operativos: number;
  total_gastos_administrativos: number;
  total_financieros: number;
  total_impuestos: number;
  total_gastos_produccion?: number;
  total_gastos: number;
}

export interface EstadoResultados {
  ventas: VentasEstadoResultados;
  inventarios_iniciales: LineaValorConcepto[];
  total_inventarios_iniciales: number;
  compras: ComprasEstadoResultados;
  inventarios_finales: LineaValorConcepto[];
  total_inventarios_finales: number;
  compras_netas: number;
  utilidad_bruta: number;
  gastos: GastosEstadoResultados;
  utilidad_periodo: number;
}

export interface InformeMensualResponse {
  mes: string;
  control_interno_ingresos: ControlInternoIngresos;
  resumen: ResumenMes;
  estado_resultados: EstadoResultados;
  pendientes_de_pago: PendientesDePagoInforme;
  saldos_caja?: LineaValorConcepto[];
}

export interface PendientePagoLinea {
  pedido_id: number;
  venta_id: number | null;
  fecha: string;
  cliente: string;
  producto: string;
  estado_pedido: string;
  estado_venta: string | null;
  moneda: string;
  total_en_base: number;
  pagado_en_base: number;
  saldo_en_base: number;
}

export interface PendientesDePagoInforme {
  lineas: PendientePagoLinea[];
  total_pendiente: number;
}

export interface ConceptoReporte {
  id: number;
  nombre: string;
  seccion: string;
  orden: number;
  activo: boolean;
}

export interface ValorConceptoMensual {
  id?: number;
  mes: string;
  concepto_id: number;
  valor_inicial: number;
  valor_final: number;
  moneda_id: number;
  observaciones?: string | null;
  concepto?: ConceptoReporte | null;
}

export interface MetodoCaja {
  id: number;
  nombre: string;
  codigo: string;
  activo: boolean;
  orden: number;
}

export interface MovimientoCaja {
  id: number;
  metodo_caja_id: number;
  fecha: string;
  tipo: 'APERTURA' | 'ENTRADA' | 'SALIDA' | 'AJUSTE';
  monto: number;
  moneda_id: number;
  tasa_cambio: number;
  monto_en_moneda_base: number;
  referencia?: string | null;
  observaciones?: string | null;
  metodo_caja?: MetodoCaja | null;
  moneda?: { codigo: string } | null;
}

export interface DevolucionVenta {
  id: number;
  venta_id: number;
  detalle_venta_id?: number | null;
  fecha: string;
  cantidad: number;
  motivo?: string | null;
  monto_devuelto: number;
  moneda_id: number;
  tasa_cambio: number;
  monto_en_moneda_base?: number | null;
  moneda?: { codigo: string } | null;
  venta?: {
    id: number;
    total: number;
    cliente?: { nombre: string } | null;
  } | null;
}
