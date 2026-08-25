import api from './api';

export interface AdjuntoInfo {
  id: number;
  nombre?: string;
  mime: string;
  tamano?: number;
  /** Solo para PRODUCTO: URL pública (sale en el PDF de la cotización). */
  url?: string;
}

export interface AdjuntoUpload {
  id: number;
  entidad_tipo: string;
  entidad_id: number;
  uuid: string;
  nombre?: string;
  mime: string;
  tamano: number;
  url?: string;
}

/** Tipos de entidad que aceptan adjuntos. */
export const TIPO_ADJUNTO = {
  PRODUCTO: 'PRODUCTO',
  PAGO: 'PAGO',
  GASTO: 'GASTO',
  COMPRA: 'COMPRA',
} as const;

/** Sube una imagen; el servidor la redimensiona/comprime según el tipo. */
export async function subirAdjunto(
  archivo: File,
  entidadTipo: string,
  entidadId: number,
): Promise<AdjuntoUpload> {
  const form = new FormData();
  form.append('entidad_tipo', entidadTipo);
  form.append('entidad_id', String(entidadId));
  form.append('archivo', archivo);
  const { data } = await api.post<AdjuntoUpload>('/adjunto/upload', form);
  return data;
}

/** Lista los adjuntos de una entidad (no trae los bytes). */
export async function listarAdjuntos(
  entidadTipo: string,
  entidadId: number,
): Promise<AdjuntoUpload[]> {
  const { data } = await api.get<AdjuntoUpload[]>('/adjunto', {
    params: { entidad_tipo: entidadTipo, entidad_id: entidadId },
  });
  return data;
}

/** Descarga los bytes de un adjunto (con token). Para recibos/comprobantes. */
export async function descargarAdjunto(id: number): Promise<Blob> {
  const { data } = await api.get<Blob>(`/adjunto/${id}/contenido`, { responseType: 'blob' });
  return data;
}

export async function eliminarAdjunto(id: number): Promise<void> {
  await api.delete(`/adjunto/${id}`);
}