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

/** Fórmula de la casa (21 años de práctica): (L×A×E) × piezas ÷ 10000 = m³.
 *  Con el LARGO en metros y ancho/espesor en cm. El mismo divisor aplica a la
 *  cuenta del ebanista digitada en cm (un solo campo: 832 → 0,0832 m³). */
export const DIVISOR_PIEZA = 10000;

/** Variante con TODAS las medidas en cm: (L×A×E) × piezas ÷ 1.000.000 = m³
 *  (1 m³ = 1.000.000 cm³). Se activa cuando el taller recibe las medidas en cm. */
export const DIVISOR_PIEZA_CM = 1000000;

export type UnidadMedidasPieza = 'M' | 'CM';

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

/** (L×A×E) × piezas ÷ divisor = m³ a descontar, redondeado a 4 decimales
 *  (columna Numeric(12,4): no perder stock con piezas chicas como 0.016 m³).
 *  `unidadMedidas='CM'` = las tres medidas vienen en cm → divide entre 1.000.000. */
export function volumenPieza(
  { largo, ancho, espesor }: CapturaPieza,
  piezas: number,
  unidadMedidas: UnidadMedidasPieza = 'M',
): number {
  const divisor = unidadMedidas === 'CM' ? DIVISOR_PIEZA_CM : DIVISOR_PIEZA;
  return Math.round(((largo * ancho * espesor * piezas) / divisor) * 10000) / 10000;
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

/** Conversión a unidad base de una captura en unidad de uso (vista previa).
 *  La conversión real la hace el backend con el factor del material. */
export function convertirUnidadUso(cantidad: number, factorBase: number): number {
  return Math.round(cantidad * factorBase * 10000) / 10000;
}

/** Etiqueta de trazabilidad: cómo se digitó la cantidad del consumo. */
export function etiquetaCaptura(c: {
  unidad_captura?: 'M' | 'CM' | null;
  pieza_largo?: number | null;
  pieza_ancho?: number | null;
  pieza_espesor?: number | null;
  cantidad?: number | null;
  // Unidad de uso (galón, pistolada, litro…): lo digitado tal cual.
  unidad_uso?: { nombre: string } | null;
  cantidad_uso?: number | null;
}): string | null {
  if (c.unidad_uso && c.cantidad_uso != null) {
    return `${fmtNum4(c.cantidad_uso)} ${c.unidad_uso.nombre}`;
  }
  if (c.pieza_largo || c.pieza_ancho || c.pieza_espesor) {
    const piezas = c.cantidad != null ? ` × ${fmtNum(c.cantidad)}` : '';
    const cm = c.unidad_captura === 'CM' ? ' (cm)' : '';
    return `pieza ${fmtNum(c.pieza_largo!)}×${fmtNum(c.pieza_ancho!)}×${fmtNum(c.pieza_espesor!)}${cm}${piezas}`;
  }
  if (c.unidad_captura === 'CM') return 'digitado en cm';
  if (c.unidad_captura === 'M') return 'digitado en mts';
  return null;
}
