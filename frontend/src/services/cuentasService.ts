import api from './api';

export interface MetodoCaja {
  id: number;
  nombre: string;
  codigo: string;
  activo: boolean;
  orden: number;
}

export interface Responsable {
  id: number;
  nombre_usuario: string;
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
  referencia?: string | null;
  observaciones?: string | null;
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
  observaciones?: string | null;
}

export const cuentasService = {
  getMonedas: async (): Promise<Moneda[]> => {
    const res = await api.get<Moneda[]>('/catalogos/moneda/');
    return res.data;
  },

  // Resumen de cuentas con saldo por moneda y en COP
  getResumen: async (): Promise<ResumenCuenta[]> => {
    const res = await api.get<ResumenCuenta[]>('/cuenta/resumen');
    return res.data;
  },

  // CRUD de cuentas (medios de pago)
  crearCuenta: async (data: { nombre: string; codigo: string; orden?: number }): Promise<MetodoCaja> => {
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
};
