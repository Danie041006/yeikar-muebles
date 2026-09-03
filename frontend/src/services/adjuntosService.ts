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
  CRUDO: 'CRUDO',
  PAGO: 'PAGO',
  GASTO: 'GASTO',
  COMPRA: 'COMPRA',
} as const;

// Por debajo de este tamaño NO vale la pena recomprimir (calidad original).
const TAMANO_COMPRESION_MIN = 2.5 * 1024 * 1024;
// Plataformas serverless (Vercel) limitan el cuerpo de la petición a ~4.5MB:
// las fotos de celular (2-8MB) se recomprimen en el navegador antes de subirlas.
const MAX_LADO_PIXELES = 3000;

/**
 * Recomprime en el navegador imágenes grandes (JPEG/PNG/WebP → JPEG) para
 * caber en los límites de subida. HEIC y otros formatos pasan tal cual: si el
 * navegador no los decodifica, el servidor los convierte (pillow-heif).
 */
async function comprimirImagen(archivo: File): Promise<File> {
  if (!archivo.type.startsWith('image/') || archivo.size <= TAMANO_COMPRESION_MIN) return archivo;
  if (!['image/jpeg', 'image/png', 'image/webp'].includes(archivo.type)) return archivo;
  try {
    const bitmap = await createImageBitmap(archivo);
    const escala = Math.min(1, MAX_LADO_PIXELES / Math.max(bitmap.width, bitmap.height));
    const ancho = Math.max(1, Math.round(bitmap.width * escala));
    const alto = Math.max(1, Math.round(bitmap.height * escala));
    const canvas = document.createElement('canvas');
    canvas.width = ancho;
    canvas.height = alto;
    canvas.getContext('2d')?.drawImage(bitmap, 0, 0, ancho, alto);
    bitmap.close();
    const blob = await new Promise<Blob | null>((resolve) => canvas.toBlob(resolve, 'image/jpeg', 0.85));
    if (!blob || blob.size >= archivo.size) return archivo;
    return new File([blob], `${archivo.name.replace(/\.[^.]+$/, '')}.jpg`, { type: 'image/jpeg' });
  } catch {
    return archivo;
  }
}

/** Sube una imagen; el servidor la redimensiona/comprime según el tipo. */
export async function subirAdjunto(
  archivo: File,
  entidadTipo: string,
  entidadId: number,
): Promise<AdjuntoUpload> {
  const archivoListo = await comprimirImagen(archivo);
  const form = new FormData();
  form.append('entidad_tipo', entidadTipo);
  form.append('entidad_id', String(entidadId));
  form.append('archivo', archivoListo);
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