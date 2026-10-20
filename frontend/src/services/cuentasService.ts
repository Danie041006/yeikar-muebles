import api from './api';

export interface MetodoCaja {
  id: number;
  nombre: string;
  codigo: string;
  activo: boolean;
  orden: number;
  moneda_id?: number | null;
  moneda_codigo?: string | null;
  moneda_simbolo?: string | null;
}

export interface Responsable {
  id: number;
  nombre_usuario: string;
  nombre?: string | null;
  email?: string | null;
}

export interface MovimientoCaja {
  id: number;
  metodo_caja_id: number;
  usuario_id?: number | null;
  fecha: string;
  tipo: 'APERTURA' | 'ENTRADA' | 'SALIDA' | 'AJUSTE';
  monto: number;
  moneda_id: number;
  tasa_cambio: number;
  monto_en_moneda_base: number;
  transferencia_id?: number | null;
  pago_id?: number | null;
  referencia?: string | null;
  persona_entidad?: string | null;
  concepto?: string | null;
  created_at?: string | null;
  metodo_caja?: MetodoCaja | null;
  moneda?: { id: number; codigo: string; simbolo: string } | null;
  usuario?: Responsable | null;
}

export interface LineaSaldoMoneda {
  moneda_id: number;
  codigo: string;
  simbolo: string;
  monto: number;
}

export interface ResumenCuenta {
  metodo_caja: MetodoCaja;
  saldo_por_moneda: LineaSaldoMoneda[];
}

export interface Moneda {
  id: number;
  codigo: string;
  nombre: string;
  simbolo: string;
  activo?: boolean;
}

export interface MovimientoCreate {
  metodo_caja_id: number;
  fecha: string;
  tipo: 'APERTURA' | 'ENTRADA' | 'SALIDA' | 'AJUSTE';
  monto: number;
  moneda_id: number;
  tasa_cambio?: number;
  referencia?: string | null;
  persona_entidad?: string | null;
  concepto?: string | null;
}

export interface TransferenciaPayload {
  cuenta_origen_id: number;
  cuenta_destino_id: number;
  monto: number;
  fecha?: string;
  moneda_id?: number | null;
  tasa_cambio?: number | null;
  referencia?: string | null;
  concepto?: string | null;
}

export interface Transferencia {
  transferencia_id: number;
  fecha: string;
  monto_salida: number;
  monto_entrada: number;
  moneda_salida_codigo: string;
  moneda_entrada_codigo: string;
  tasa_cambio: number;
  saldo_disponible_origen: number;
  referencia?: string | null;
  concepto?: string | null;
  pata_salida: MovimientoCaja;
  pata_entrada: MovimientoCaja;
}

// ── Importación del libro de caja (texto pegado) ─────────────────────────
export interface LibroCajaFila {
  linea: number;
  fecha: string;
  tipo: string;
  concepto: string;
  ingreso: string | number;
  egreso: string | number;
  saldo: string | number;
  clasificacion?: string | null;
  codigo?: string | null;
  es_saldo_inicial: boolean;
  duplicado_de?: string | null;
  advertencias: string[];
}

export interface LibroCajaOmitida {
  linea: number;
  texto: string;
  motivo: string;
}

export interface LibroCajaResumen {
  periodo: string;
  cuenta_id: number;
  cuenta_nombre: string;
  filas: number;
  movimientos: number;
  gastos: number;
  duplicados: number;
  omitidos: number;
  saldo_inicial?: string | number | null;
  saldo_final?: string | number | null;
  total_ingresos: string | number;
  total_egresos: string | number;
  saldo_previo_cuenta?: string | number | null;
  diferencia_saldo_inicial?: string | number | null;
  ya_importado: boolean;
  advertencias: string[];
  errores: string[];
  omitidas: LibroCajaOmitida[];
  filas_detalle: LibroCajaFila[];
}

export interface LibroCajaImportarPayload {
  texto: string;
  metodo_caja_id: number;
  cuadrar_saldo_inicial?: boolean;
  permitir_saldo_distinto?: boolean;
  omitir_duplicados?: boolean;
}

export interface LibroCajaDeshacerResponse {
  periodo: string;
  cuenta_nombre: string;
  gastos_borrados: number;
  movimientos_borrados: number;
}

export interface LibroCajaVistaFila {
  id: number;
  fecha: string;
  tipo: string;
  concepto: string;
  ingreso: string | number;
  egreso: string | number;
  saldo: string | number;
  clasificacion?: string | null;
  origen: string;
  referencia?: string | null;
  persona_entidad?: string | null;
}

export interface LibroCajaVistaClasificacion {
  clasificacion: string;
  label: string;
  count: number;
  total: string | number;
}

export interface LibroCajaVista {
  cuenta_id: number;
  cuenta_nombre: string;
  moneda_codigo: string;
  fecha_desde: string;
  fecha_hasta: string;
  saldo_inicial: string | number;
  total_ingresos: string | number;
  total_egresos: string | number;
  saldo_final: string | number;
  filas: LibroCajaVistaFila[];
  clasificaciones: LibroCajaVistaClasificacion[];
}

export const cuentasService = {
  getMonedas: async (): Promise<Moneda[]> => {
    const res = await api.get<Moneda[]>('/catalogos/moneda/');
    return res.data;
  },

  // Transferencias entre cuentas (dos patas: SALIDA en origen + ENTRADA en destino)
  transferir: async (data: TransferenciaPayload): Promise<Transferencia> => {
    const res = await api.post<Transferencia>('/cuenta/transferencia', data);
    return res.data;
  },
  getTransferencias: async (params?: { fecha_desde?: string; fecha_hasta?: string }): Promise<Transferencia[]> => {
    const res = await api.get<Transferencia[]>('/cuenta/transferencias', { params });
    return res.data;
  },

  // Resumen de cuentas con saldo por moneda y en COP
  getResumen: async (): Promise<ResumenCuenta[]> => {
    const res = await api.get<ResumenCuenta[]>('/cuenta/resumen');
    return res.data;
  },

  // CRUD de cuentas (medios de pago)
  crearCuenta: async (data: { nombre: string; codigo: string; orden?: number; moneda_id?: number | null }): Promise<MetodoCaja> => {
    const res = await api.post<MetodoCaja>('/cuenta/', data);
    return res.data;
  },
  actualizarCuenta: async (id: number, data: Partial<MetodoCaja>): Promise<MetodoCaja> => {
    const res = await api.put<MetodoCaja>(`/cuenta/${id}`, data);
    return res.data;
  },
  eliminarCuenta: async (id: number): Promise<void> => {
    await api.delete(`/cuenta/${id}`);
  },

  // Movimientos
  getMovimientos: async (params?: { metodo_caja_id?: number; fecha_desde?: string; fecha_hasta?: string }): Promise<MovimientoCaja[]> => {
    const res = await api.get<MovimientoCaja[]>('/cuenta/movimientos', { params });
    return res.data;
  },
  crearMovimiento: async (metodoId: number, data: Omit<MovimientoCreate, 'metodo_caja_id'>): Promise<MovimientoCaja> => {
    const res = await api.post<MovimientoCaja>(`/cuenta/${metodoId}/movimiento`, { ...data, metodo_caja_id: metodoId });
    return res.data;
  },
  actualizarMovimiento: async (id: number, data: Partial<MovimientoCreate>): Promise<MovimientoCaja> => {
    const res = await api.put<MovimientoCaja>(`/cuenta/movimiento/${id}`, data);
    return res.data;
  },
  eliminarMovimiento: async (id: number): Promise<void> => {
    await api.delete(`/cuenta/movimiento/${id}`);
  },

  // Libro de caja: pegar el mes, revisar y confirmar.
  previsualizarLibro: async (data: { texto: string; metodo_caja_id: number }): Promise<LibroCajaResumen> => {
    const res = await api.post<LibroCajaResumen>('/cuenta/libro/preview', data);
    return res.data;
  },
  importarLibro: async (data: LibroCajaImportarPayload): Promise<LibroCajaResumen> => {
    const res = await api.post<LibroCajaResumen>('/cuenta/libro/importar', data);
    return res.data;
  },
  deshacerLibro: async (periodo: string, metodoCajaId: number): Promise<LibroCajaDeshacerResponse> => {
    const res = await api.delete<LibroCajaDeshacerResponse>(`/cuenta/libro/${periodo}`, {
      params: { metodo_caja_id: metodoCajaId },
    });
    return res.data;
  },
  getLibro: async (params: {
    metodo_caja_id: number;
    fecha_desde?: string;
    fecha_hasta?: string;
  }): Promise<LibroCajaVista> => {
    const res = await api.get<LibroCajaVista>('/cuenta/libro', { params });
    return res.data;
  },
};
