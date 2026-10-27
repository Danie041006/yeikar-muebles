import type { Cell, CellObject, Sheet, SheetData } from 'write-excel-file/browser';
import {
  ReporteCuentasData,
  fmtReporteFecha,
  nombreArchivoReporte,
} from './reporteCuentas';

const BORDE = '#A8A29E';
const FONDO_CABECERA = '#F1E8D7';

type Estilo = Omit<CellObject, 'value'>;

const celda = (value: string | number | Date | null | undefined, estilo: Estilo = {}): Cell => ({
  value: value ?? '',
  borderColor: BORDE,
  borderStyle: 'thin',
  ...estilo,
});

const encabezado = (value: string, align: 'left' | 'right' | 'center' = 'left'): Cell =>
  celda(value, {
    fontWeight: 'bold',
    backgroundColor: FONDO_CABECERA,
    align,
    alignVertical: 'bottom',
  });

const numero = (value: number): Cell =>
  celda(value, { type: Number, format: '#,##0.00', align: 'right' });

const vacia = (): Cell => celda(null);

/** Ancho de columnas del detalle, en el mismo orden que `columnasDetalle`. */
function columnasDetalle(data: ReporteCuentasData): Array<{ width: number }> {
  const cols = [12, 16];
  if (data.columnas.persona) cols.push(20);
  if (data.columnas.registrado) cols.push(18);
  cols.push(40, 18);
  if (data.columnas.referencia) cols.push(16);
  cols.push(15, 15);
  if (data.mostrarSaldoCorrido) cols.push(15);
  return cols.map((width) => ({ width }));
}

function titulosDetalle(data: ReporteCuentasData): Cell[] {
  const cols: Cell[] = [encabezado('Fecha'), encabezado('Tipo')];
  if (data.columnas.persona) cols.push(encabezado('Persona o entidad'));
  if (data.columnas.registrado) cols.push(encabezado('Registrado por'));
  cols.push(encabezado('Concepto'), encabezado('Clasificación'));
  if (data.columnas.referencia) cols.push(encabezado('Referencia'));
  cols.push(encabezado('Ingreso', 'right'), encabezado('Egreso', 'right'));
  if (data.mostrarSaldoCorrido) cols.push(encabezado('Saldo', 'right'));
  return cols;
}

function filaDetalle(data: ReporteCuentasData, indice: number): Cell[] {
  const f = data.filas[indice];
  const cols: Cell[] = [
    celda(new Date(`${f.fecha}T00:00:00`), { type: Date, format: 'DD/MM/YYYY', align: 'center' }),
    celda(f.tipo),
  ];
  if (data.columnas.persona) cols.push(celda(f.persona || '—'));
  if (data.columnas.registrado) cols.push(celda(f.registrado || '—'));
  cols.push(celda(f.concepto || '—'), celda(f.clasificacion || '—'));
  if (data.columnas.referencia) cols.push(celda(f.referencia || '—'));
  cols.push(f.ingreso ? numero(f.ingreso) : vacia());
  cols.push(f.egreso ? numero(f.egreso) : vacia());
  if (data.mostrarSaldoCorrido) cols.push(numero(f.saldo));
  return cols;
}

function hojaLibro(data: ReporteCuentasData): SheetData {
  const filas: Cell[][] = [];

  filas.push([celda('COMERCIALIZADORA YEIKAR', { fontWeight: 'bold', fontSize: 15, borderStyle: undefined })]);
  filas.push([celda('Libro de caja', { fontWeight: 'bold', fontSize: 12, borderStyle: undefined })]);
  filas.push([]);
  filas.push([celda('Cuenta', { fontWeight: 'bold', borderStyle: undefined }), celda(data.cuenta)]);
  filas.push([
    celda('Moneda', { fontWeight: 'bold', borderStyle: undefined }),
    celda(data.moneda),
  ]);
  filas.push([
    celda('Periodo', { fontWeight: 'bold', borderStyle: undefined }),
    celda(`${fmtReporteFecha(data.desde)} a ${fmtReporteFecha(data.hasta)}`),
  ]);
  filas.push([
    celda('Filtro', { fontWeight: 'bold', borderStyle: undefined }),
    celda(data.filtroLabel),
  ]);
  filas.push([
    celda('Generado', { fontWeight: 'bold', borderStyle: undefined }),
    celda(data.generadoEn),
  ]);
  filas.push([]);

  if (data.incluirResumen) {
    const resumen: Array<[string, number]> = [
      ['Saldo inicial', data.saldoInicial],
      ['Ingresos', data.totalIngresos],
      ['Egresos', data.totalEgresos],
      ['Saldo final', data.saldoFinal],
    ];
    filas.push([celda('Resumen de la cuenta', { fontWeight: 'bold', fontSize: 11, borderStyle: undefined })]);
    if (data.filtrado) {
      filas.push([
        celda('Corresponde a todos los movimientos del rango, sin aplicar el filtro del detalle.', {
          fontStyle: 'italic',
          textColor: '#57534E',
          borderStyle: undefined,
        }),
      ]);
    }
    for (const [label, valor] of resumen) {
      // `columnSpan` exige null en las celdas que quedan tapadas.
      filas.push([
        celda(`${label} (${data.moneda})`, { columnSpan: 2, fontWeight: 'bold' }),
        null,
        numero(valor),
      ]);
    }
    filas.push([]);
  }

  if (data.incluirDetalle) {
    filas.push(titulosDetalle(data));
    if (data.filas.length === 0) {
      const ancho = titulosDetalle(data).length;
      filas.push([
        celda('No hay movimientos con el filtro seleccionado.', {
          columnSpan: ancho,
          align: 'center',
          fontStyle: 'italic',
        }),
        ...Array(ancho - 1).fill(null),
      ]);
    } else {
      data.filas.forEach((_, i) => filas.push(filaDetalle(data, i)));
    }

    const cols = titulosDetalle(data).length;
    const span = cols - (data.mostrarSaldoCorrido ? 3 : 2);
    const total: Cell[] = [
      celda(data.filtrado ? 'TOTAL DEL FILTRO' : 'TOTALES DEL RANGO', {
        columnSpan: span,
        fontWeight: 'bold',
        backgroundColor: FONDO_CABECERA,
      }),
      ...Array(span - 1).fill(null),
      celda(data.totalFiltroIngresos, {
        type: Number,
        format: '#,##0.00',
        align: 'right',
        fontWeight: 'bold',
        backgroundColor: FONDO_CABECERA,
      }),
      celda(data.totalFiltroEgresos, {
        type: Number,
        format: '#,##0.00',
        align: 'right',
        fontWeight: 'bold',
        backgroundColor: FONDO_CABECERA,
      }),
    ];
    if (data.mostrarSaldoCorrido) {
      total.push(
        celda(data.saldoFinal, {
          type: Number,
          format: '#,##0.00',
          align: 'right',
          fontWeight: 'bold',
          backgroundColor: FONDO_CABECERA,
        }),
      );
    }
    filas.push(total);
  }

  return filas;
}

function hojaClasificaciones(data: ReporteCuentasData): SheetData {
  const filas: Cell[][] = [
    [celda('Resumen por clasificación', { fontWeight: 'bold', fontSize: 12, borderStyle: undefined })],
    [celda(`Cuenta: ${data.cuenta} · ${data.moneda}`, { borderStyle: undefined })],
    [celda(`Periodo: ${fmtReporteFecha(data.desde)} a ${fmtReporteFecha(data.hasta)}`, { borderStyle: undefined })],
    [],
    [encabezado('Clasificación'), encabezado('Movimientos', 'right'), encabezado('Total', 'right')],
  ];

  if (data.clasificaciones.length === 0) {
    filas.push([
      celda('Sin gastos clasificados en el rango.', { columnSpan: 3, align: 'center', fontStyle: 'italic' }),
      null,
      null,
    ]);
    return filas;
  }

  for (const c of data.clasificaciones) {
    filas.push([celda(c.label), celda(c.count, { align: 'right' }), numero(c.total)]);
  }
  filas.push([
    celda('TOTAL', { fontWeight: 'bold', backgroundColor: FONDO_CABECERA }),
    celda(data.clasificaciones.reduce((s, c) => s + c.count, 0), {
      align: 'right',
      fontWeight: 'bold',
      backgroundColor: FONDO_CABECERA,
    }),
    celda(data.clasificaciones.reduce((s, c) => s + c.total, 0), {
      type: Number,
      format: '#,##0.00',
      align: 'right',
      fontWeight: 'bold',
      backgroundColor: FONDO_CABECERA,
    }),
  ]);
  return filas;
}

/** Descarga el reporte como un .xlsx real (una o dos hojas). */
export async function exportarReporteCuentasExcel(data: ReporteCuentasData): Promise<void> {
  const { default: writeXlsxFile } = await import('write-excel-file/browser');

  const hojas: Sheet<Blob>[] = [
    {
      data: hojaLibro(data),
      sheet: 'Libro de caja',
      orientation: 'landscape',
      columns: columnasDetalle(data),
      showGridLines: false,
    },
  ];

  if (data.incluirClasificaciones) {
    hojas.push({
      data: hojaClasificaciones(data),
      sheet: 'Clasificaciones',
      columns: [{ width: 34 }, { width: 16 }, { width: 18 }],
      showGridLines: false,
    });
  }

  await writeXlsxFile(hojas).toFile(nombreArchivoReporte(data, 'xlsx'));
}
