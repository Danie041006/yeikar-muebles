/**
 * Captura flexible de madera: espejo frontend de
 * backend/app/modules/production/unidades.py (punto único de conversión).
 *
 * La unidad BASE del inventario es la de compra del material (`unidad_medida`).
 * El operario digita como le quede cómodo y el backend convierte antes de
 * descontar; aquí solo viven los helpers de detección y la vista previa.
 */

export type UnidadCaptura = 'M' | 'CM';

export const CM_POR_METRO = 100;

/** Fórmula de la casa (21 años de práctica): (L×A×E) × piezas ÷ 10000 = m³. */
export const DIVISOR_PIEZA = 10000;

export type Dimensionalidad = 'LONGITUD' | 'AREA' | 'VOLUMEN' | 'OTRA';

export function dimensionalidad(abreviatura?: string | null): Dimensionalidad {
  const a = (abreviatura ?? '')
    .trim()
    .toLowerCase()
    .replace(/³/g, '3')
    .replace(/²/g, '2')
    .replace(/\^/g, '')
    .replace(/ /g, '');
  if (['m3', 'mt3', 'mc'].includes(a)) return 'VOLUMEN';
  if (['m2', 'mt2'].includes(a)) return 'AREA';
  if (['m', 'mt', 'mts', 'cm'].includes(a)) return 'LONGITUD';
  return 'OTRA';
}

export interface CapturaPieza {
  largo: number;
  ancho: number;
  espesor: number;
}

/** (L×A×E) × piezas ÷ 10000 = m³ a descontar, redondeado a 4 decimales
 *  (columna Numeric(12,4): no perder stock con piezas chicas como 0.016 m³). */
export function volumenPieza({ largo, ancho, espesor }: CapturaPieza, piezas: number): number {
  return Math.round(((largo * ancho * espesor * piezas) / DIVISOR_PIEZA) * 10000) / 10000;
}

/** Conversión lineal solo para la VISTA PREVIA (la real la hace el backend). */
export function convertirCapturaLineal(cantidad: number, unidad: UnidadCaptura, baseEnMetros = true): number {
  if (unidad === 'CM') return baseEnMetros ? cantidad / CM_POR_METRO : cantidad;
  return baseEnMetros ? cantidad : cantidad * CM_POR_METRO;
}

export function fmtNum(n: number): string {
  return new Intl.NumberFormat('es-CO', { maximumFractionDigits: 2 }).format(n);
}

/** Formato con 4 decimales (para la vista previa de la fórmula de la casa). */
export function fmtNum4(n: number): string {
  return new Intl.NumberFormat('es-CO', { maximumFractionDigits: 4 }).format(n);
}

/** Etiqueta de trazabilidad: cómo se digitó la cantidad del consumo. */
export function etiquetaCaptura(c: {
  unidad_captura?: 'M' | 'CM' | null;
  pieza_largo?: number | null;
  pieza_ancho?: number | null;
  pieza_espesor?: number | null;
  cantidad?: number | null;
}): string | null {
  if (c.pieza_largo || c.pieza_ancho || c.pieza_espesor) {
    const piezas = c.cantidad != null ? ` × ${fmtNum(c.cantidad)}` : '';
    return `pieza ${fmtNum(c.pieza_largo!)}×${fmtNum(c.pieza_ancho!)}×${fmtNum(c.pieza_espesor!)}${piezas}`;
  }
  if (c.unidad_captura === 'CM') return 'digitado en cm';
  if (c.unidad_captura === 'M') return 'digitado en mts';
  return null;
}
