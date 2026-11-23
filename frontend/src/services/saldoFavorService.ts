import api from './api';
import type { MonedaInfo, Pago } from './ventaService';

export interface SaldoFavor {
  id: number;
  cliente_id: number;
  cliente_nombre: string;
  moneda_id: number;
  moneda: MonedaInfo;
  monto: number;
  monto_usado: number;
  saldo: number;
  referencia: string;
  created_at: string;
  creador_nombre?: string | null;
}

export interface AplicarSaldo {
  venta_id: number;
  saldo_favor_id: number;
  monto: number;
  tasa_cambio?: number;
  operacion_id: string;
}

export const saldoFavorService = {
  listar: async (params: { cliente_id?: number; salto?: number; limite?: number }): Promise<SaldoFavor[]> => {
    const res = await api.get<SaldoFavor[]>('/saldo-favor/', { params });
    return res.data;
  },
  aplicar: async (payload: AplicarSaldo): Promise<Pago> => {
    const res = await api.post<Pago>('/saldo-favor/aplicar', payload);
    return res.data;
  },
};
