import api from './api';

export interface TipoGasto {
  id: number;
  nombre: string;
  categoria: string;
  created_at?: string;
  updated_at?: string;
}

export interface Moneda {
  id: number;
  codigo: string;
  nombre: string;
  simbolo: string;
  activo: boolean;
}

export interface Gasto {
  id: number;
  tipo_gasto_id: number;
  moneda_id: number;
  fecha: string;
  descripcion?: string;
  monto: number;
  tasa_cambio: number;
  monto_en_moneda_base: number;
  observaciones?: string;
  tipo_gasto?: TipoGasto;
  moneda?: Moneda;
  created_at: string;
  updated_at?: string;
}

export interface GastoCreate {
  tipo_gasto_id: number;
  moneda_id: number;
  fecha: string;
  descripcion?: string;
  monto: number;
  tasa_cambio?: number;
  observaciones?: string;
}

export interface GastoUpdate {
  tipo_gasto_id?: number;
  moneda_id?: number;
  fecha?: string;
  descripcion?: string;
  monto?: number;
  tasa_cambio?: number;
  observaciones?: string;
}

export async function getGastos(params?: {
  skip?: number;
  limit?: number;
  tipo_gasto_id?: number;
  categoria?: string;
  fecha_desde?: string;
  fecha_hasta?: string;
}): Promise<Gasto[]> {
  const response = await api.get('/gasto/gastos/', { params });
  return response.data;
}

export async function getGasto(id: number): Promise<Gasto> {
  const response = await api.get(`/gasto/gastos/${id}`);
  return response.data;
}

export async function createGasto(data: GastoCreate): Promise<Gasto> {
  const response = await api.post('/gasto/gastos/', data);
  return response.data;
}

export async function updateGasto(id: number, data: GastoUpdate): Promise<Gasto> {
  const response = await api.put(`/gasto/gastos/${id}`, data);
  return response.data;
}

export async function deleteGasto(id: number): Promise<void> {
  await api.delete(`/gasto/gastos/${id}`);
}

export async function getTiposGasto(params?: {
  categoria?: string;
}): Promise<TipoGasto[]> {
  const response = await api.get('/catalogos/tipo-gasto/', { params });
  return response.data;
}

export async function getMonedas(): Promise<Moneda[]> {
  const response = await api.get('/catalogos/moneda/');
  return response.data;
}
