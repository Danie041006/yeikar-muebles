import api from './api';

export interface Cargo {
  id: number;
  nombre: string;
}

export interface Empleado {
  id: number;
  nombre: string;
  cargo_id: number;
  telefono?: string | null;
  activo: boolean;
  en_nomina: boolean;
  tipo_pago?: string | null;
  sueldo_semanal?: number | null;
  porcentaje_aguinaldo?: number | null;
  saldo_aguinaldo?: number | null;
  cargo?: Cargo | null;
}

export interface EmpleadoCreate {
  nombre: string;
  cargo_id: number;
  telefono?: string;
  activo?: boolean;
  en_nomina?: boolean;
  tipo_pago?: string;
  sueldo_semanal?: number;
  porcentaje_aguinaldo?: number;
}

export interface EmpleadoUpdate {
  nombre?: string;
  cargo_id?: number;
  telefono?: string | null;
  activo?: boolean;
  en_nomina?: boolean;
  tipo_pago?: string | null;
  sueldo_semanal?: number | null;
  porcentaje_aguinaldo?: number | null;
}

export async function getEmpleados(params?: { buscar?: string; limite?: number }): Promise<Empleado[]> {
  const res = await api.get('/empleado/', { params });
  return res.data;
}

export async function crearEmpleado(data: EmpleadoCreate): Promise<Empleado> {
  const res = await api.post('/empleado/', data);
  return res.data;
}

export async function actualizarEmpleado(id: number, data: EmpleadoUpdate): Promise<Empleado> {
  const res = await api.put(`/empleado/${id}`, data);
  return res.data;
}

export async function eliminarEmpleado(id: number): Promise<void> {
  await api.delete(`/empleado/${id}`);
}

export async function getCargos(): Promise<Cargo[]> {
  const res = await api.get('/catalogos/cargo/');
  return res.data;
}
