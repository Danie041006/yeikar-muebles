import type { LibroCajaVista, LibroCajaVistaFila } from '../services/cuentasService';
import { nombreClasificacion } from '../services/gastoService';

/** Filtro del detalle del reporte de cuentas. */
export type FiltroReporteCuentas =
  | { tipo: 'TODOS' }
  | { tipo: 'INGRESOS' }
  | { tipo: 'EGRESOS' }
  | { tipo: 'CLASIFICACION'; clasificacion: string; label: string };

export interface ColumnasReporteCuentas {
  persona: boolean;
  registrado: boolean;
  referencia: boolean;
}

export interface ReporteCuentasFila {
  fecha: string;
  tipo: string;
  concepto: string;
  clasificacion: string;
  ingreso: number;
  egreso: number;
  saldo: number;
  persona: string;
  registrado: string;
  referencia: string;
}

export interface ReporteCuentasData {
  cuenta: string;
  moneda: string;
  desde: string;
  hasta: string;
  generadoEn: string;
  saldoInicial: number;
  totalIngresos: number;
  totalEgresos: number;
  saldoFinal: number;
  filas: ReporteCuentasFila[];
  filtroLabel: string;
  filtrado: boolean;
  totalFiltroIngresos: number;
  totalFiltroEgresos: number;
  clasificaciones: Array<{ label: string; count: number; total: number }>;
  incluirResumen: boolean;
  incluirDetalle: boolean;
  incluirClasificaciones: boolean;
  columnas: ColumnasReporteCuentas;
  /** El saldo corrido solo tiene sentido con el libro completo. */
  mostrarSaldoCorrido: boolean;
}

export function etiquetaFiltroReporte(filtro: FiltroReporteCuentas): string {
  switch (filtro.tipo) {
    case 'INGRESOS':
      return 'Solo ingresos';
    case 'EGRESOS':
      return 'Solo egresos';
    case 'CLASIFICACION':
      return `Clasificación: ${filtro.label}`;
    default:
      return 'Todos los movimientos';
  }
}

function coincideFiltro(fila: LibroCajaVistaFila, filtro: FiltroReporteCuentas): boolean {
  if (filtro.tipo === 'INGRESOS') return Number(fila.ingreso) > 0;
  if (filtro.tipo === 'EGRESOS') return Number(fila.egreso) > 0;
  if (filtro.tipo === 'CLASIFICACION') return fila.clasificacion === filtro.clasificacion;
  return true;
}

/**
 * Arma los datos del reporte a partir del libro de caja que devuelve el
 * backend. El resumen (saldo inicial/final) siempre es el de la cuenta
 * completa en el rango; cuando se filtra el detalle, los totales del filtro
 * se calculan aparte para no mostrar cifras engañosas.
 */
export function construirReporteCuentas(
  libro: LibroCajaVista,
  opciones: {
    filtro: FiltroReporteCuentas;
    incluirResumen: boolean;
    incluirDetalle: boolean;
    incluirClasificaciones: boolean;
    columnas: ColumnasReporteCuentas;
    generadoEn: string;
  },
): ReporteCuentasData {
  const seleccionadas = libro.filas.filter((f) => coincideFiltro(f, opciones.filtro));
  const filtrado = opciones.filtro.tipo !== 'TODOS';

  const filas: ReporteCuentasFila[] = seleccionadas.map((f) => ({
    fecha: f.fecha,
    tipo: f.tipo || f.tipo_movimiento,
    concepto: f.concepto || '',
    clasificacion: f.clasificacion ? nombreClasificacion(f.clasificacion) : '',
    ingreso: Number(f.ingreso),
    egreso: Number(f.egreso),
    saldo: Number(f.saldo),
    persona: f.persona_entidad || '',
    registrado: f.usuario_nombre || '',
    referencia: f.referencia || '',
  }));

  return {
    cuenta: libro.cuenta_nombre,
    moneda: libro.moneda_codigo,
    desde: libro.fecha_desde,
    hasta: libro.fecha_hasta,
    generadoEn: opciones.generadoEn,
    saldoInicial: Number(libro.saldo_inicial),
    totalIngresos: Number(libro.total_ingresos),
    totalEgresos: Number(libro.total_egresos),
    saldoFinal: Number(libro.saldo_final),
    filas,
    filtroLabel: etiquetaFiltroReporte(opciones.filtro),
    filtrado,
    totalFiltroIngresos: filas.reduce((s, f) => s + f.ingreso, 0),
    totalFiltroEgresos: filas.reduce((s, f) => s + f.egreso, 0),
    clasificaciones: libro.clasificaciones.map((c) => ({
      label: c.label,
      count: c.count,
      total: Number(c.total),
    })),
    incluirResumen: opciones.incluirResumen,
    incluirDetalle: opciones.incluirDetalle,
    incluirClasificaciones: opciones.incluirClasificaciones,
    columnas: opciones.columnas,
    mostrarSaldoCorrido: !filtrado,
  };
}

export const fmtReporteNumero = (n: number): string =>
  Number(n || 0).toLocaleString('es-CO', {
    minimumFractionDigits: 2,
    maximumFractionDigits: 2,
  });

export const fmtReporteMoneda = (n: number, moneda: string): string =>
  `${moneda} ${fmtReporteNumero(n)}`;

/** Fecha ISO (YYYY-MM-DD) → DD/MM/YYYY. */
export const fmtReporteFecha = (fecha: string): string => {
  const [y, m, d] = String(fecha).slice(0, 10).split('-');
  return y && m && d ? `${d}/${m}/${y}` : String(fecha);
};

/** Nombre de archivo seguro para la descarga. */
export function nombreArchivoReporte(data: ReporteCuentasData, extension: string): string {
  const slug = (s: string) =>
    s
      .normalize('NFD')
      .replace(/[\u0300-\u036f]/g, '')
      .replace(/[^a-zA-Z0-9]+/g, '-')
      .replace(/^-+|-+$/g, '');
  return `Libro-${slug(data.cuenta)}-${data.desde}-${data.hasta}.${extension}`;
}
