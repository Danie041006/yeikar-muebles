import api from './api';

export interface Area {
  id: number;
  nombre: string;
}

export interface PrecioProduccion {
  id: number;
  area_id: number;
  descripcion: string;
  producto_id?: number | null;
  precio: number;
  activo: boolean;
  orden: number;
  area?: Area;
  created_at?: string;
  updated_at?: string;
}

export interface PrecioProduccionCreate {
  area_id: number;
  descripcion: string;
  precio: number;
  activo?: boolean;
  orden?: number;
}

export interface PrecioProduccionUpdate {
  area_id?: number;
  descripcion?: string;
  precio?: number;
  activo?: boolean;
  orden?: number;
}

export async function getPreciosProduccion(params?: {
  area_id?: number;
  buscar?: string;
  activo?: boolean;
  skip?: number;
  limit?: number;
}): Promise<PrecioProduccion[]> {
  const response = await api.get('/costo-produccion/', { params });
  return response.data;
}

export async function crearPrecioProduccion(data: PrecioProduccionCreate): Promise<PrecioProduccion> {
  const response = await api.post('/costo-produccion/', data);
  return response.data;
}

export async function actualizarPrecioProduccion(
  id: number,
  data: PrecioProduccionUpdate,
): Promise<PrecioProduccion> {
  const response = await api.put(`/costo-produccion/${id}`, data);
  return response.data;
}

export async function eliminarPrecioProduccion(id: number): Promise<void> {
  await api.delete(`/costo-produccion/${id}`);
}

export async function getAreas(): Promise<Area[]> {
  const response = await api.get('/catalogos/area/');
  return response.data;
}
