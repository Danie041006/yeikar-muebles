import {
  ReporteCuentasData,
  fmtReporteFecha,
  fmtReporteMoneda,
  fmtReporteNumero,
} from './reporteCuentas';

const esc = (s: unknown): string =>
  String(s ?? '')
    .replace(/&/g, '&amp;')
    .replace(/</g, '&lt;')
    .replace(/>/g, '&gt;')
    .replace(/"/g, '&quot;')
    .replace(/'/g, '&#39;');

const CSS = `
  @page { size: A4 landscape; margin: 9mm 11mm; }
  * { box-sizing: border-box; }
  body { font-family: Arial, Helvetica, sans-serif; font-size: 10.5px; color: #111; margin: 0; }
  table { border-collapse: collapse; width: 100%; }
  table.grid td, table.grid th { border: 1px solid #a8a29e; padding: 3px 6px; }
  table.grid thead th { background: #f1e8d7; font-weight: bold; text-align: left; vertical-align: bottom; }
  table.grid thead { display: table-header-group; }
  table.grid tr { page-break-inside: avoid; }
  table.grid tbody tr:nth-child(even) td { background: #fbf8f1; }
  table.grid tr.total-row td { font-weight: bold; background: #f1e8d7; border-top: 2px solid #57534e; }
  .num { text-align: right; font-variant-numeric: tabular-nums; white-space: nowrap; }
  .center { text-align: center; }
  .muted { color: #57534e; }
  .page-break { page-break-before: always; }
  .encabezado { display: flex; justify-content: space-between; align-items: flex-end; margin-bottom: 6px; }
  .encabezado .marca { font-size: 22px; font-weight: 900; letter-spacing: -0.5px; }
  .encabezado .marca span { font-weight: 400; font-size: 10px; display: block; letter-spacing: 2px; text-transform: uppercase; color: #444; }
  .encabezado .der { text-align: right; }
  .encabezado .der .titulo { font-size: 17px; font-weight: 900; text-transform: uppercase; letter-spacing: -0.4px; }
  .encabezado .der .gen { font-size: 9.5px; color: #555; margin-top: 2px; }
  .divisor { border-bottom: 3px solid #111; margin-bottom: 9px; }
  .meta { width: 100%; margin-bottom: 9px; }
  .meta td { padding: 2px 12px 2px 0; vertical-align: top; }
  .meta .lab { font-size: 8.5px; font-weight: 700; text-transform: uppercase; letter-spacing: 1px; color: #666; display: block; }
  .meta .val { font-size: 11.5px; font-weight: 700; }
  .resumen { width: 100%; border-collapse: separate; border-spacing: 6px 0; margin: 0 -6px 10px; }
  .resumen td { border: 1px solid #b8b0a1; padding: 7px 10px; text-align: center; background: #fdfbf7; }
  .resumen .label { font-size: 8.5px; font-weight: 700; text-transform: uppercase; letter-spacing: 1px; color: #555; display: block; }
  .resumen .valor { font-size: 16px; font-weight: 900; font-variant-numeric: tabular-nums; margin-top: 3px; white-space: nowrap; }
  .resumen .valor.neg { color: #a4161a; }
  h2 { font-size: 12.5px; font-weight: 900; text-transform: uppercase; letter-spacing: -0.2px; border-bottom: 2px solid #111; padding-bottom: 3px; margin: 14px 0 7px; }
  .nota { font-size: 9px; color: #555; margin: 0 0 7px; }
  .vacio { padding: 14px; text-align: center; font-style: italic; color: #555; }
  .pie { margin-top: 14px; border-top: 1px solid #a8a29e; padding-top: 5px; font-size: 8.5px; color: #555; display: flex; justify-content: space-between; }
  table, thead th, tr.total-row td, tbody tr:nth-child(even) td { -webkit-print-color-adjust: exact; print-color-adjust: exact; }
`;

function celdaResumen(label: string, valor: string, negativo = false): string {
  return `<td><span class="label">${esc(label)}</span>
    <span class="valor ${negativo ? 'neg' : ''}">${esc(valor)}</span></td>`;
}

function tablaDetalle(data: ReporteCuentasData): string {
  const cols: string[] = ['Fecha', 'Tipo'];
  if (data.columnas.persona) cols.push('Persona o entidad');
  if (data.columnas.registrado) cols.push('Registrado por');
  cols.push('Concepto', 'Clasificación');
  if (data.columnas.referencia) cols.push('Referencia');
  cols.push('Ingreso', 'Egreso');
  if (data.mostrarSaldoCorrido) cols.push('Saldo');

  const head = `<tr>${cols
    .map((c) =>
      c === 'Ingreso' || c === 'Egreso' || c === 'Saldo'
        ? `<th class="num">${esc(c)}</th>`
        : `<th>${esc(c)}</th>`,
    )
    .join('')}</tr>`;

  const cuerpo = data.filas.length === 0
    ? `<tr><td colspan="${cols.length}" class="vacio">No hay movimientos con el filtro seleccionado.</td></tr>`
    : data.filas
        .map((f) => {
          const celdas: string[] = [
            `<td>${esc(fmtReporteFecha(f.fecha))}</td>`,
            `<td>${esc(f.tipo)}</td>`,
          ];
          if (data.columnas.persona) celdas.push(`<td>${esc(f.persona || '—')}</td>`);
          if (data.columnas.registrado) celdas.push(`<td>${esc(f.registrado || '—')}</td>`);
          celdas.push(`<td>${esc(f.concepto || '—')}</td>`);
          celdas.push(`<td>${esc(f.clasificacion || '—')}</td>`);
          if (data.columnas.referencia) celdas.push(`<td>${esc(f.referencia || '—')}</td>`);
          celdas.push(`<td class="num">${f.ingreso ? esc(fmtReporteNumero(f.ingreso)) : ''}</td>`);
          celdas.push(`<td class="num">${f.egreso ? esc(fmtReporteNumero(f.egreso)) : ''}</td>`);
          if (data.mostrarSaldoCorrido) {
            celdas.push(`<td class="num">${esc(fmtReporteNumero(f.saldo))}</td>`);
          }
          return `<tr>${celdas.join('')}</tr>`;
        })
        .join('');

  const etiquetaTotal = data.filtrado ? 'TOTAL DEL FILTRO' : 'TOTALES DEL RANGO';
  const totalCeldas: string[] = [
    `<td colspan="${cols.length - (data.mostrarSaldoCorrido ? 3 : 2)}">${etiquetaTotal}</td>`,
    `<td class="num">${esc(fmtReporteNumero(data.totalFiltroIngresos))}</td>`,
    `<td class="num">${esc(fmtReporteNumero(data.totalFiltroEgresos))}</td>`,
  ];
  if (data.mostrarSaldoCorrido) {
    totalCeldas.push(`<td class="num">${esc(fmtReporteNumero(data.saldoFinal))}</td>`);
  }
  const totales = `<tr class="total-row">${totalCeldas.join('')}</tr>`;

  return `
    <h2>${data.filtrado ? 'Detalle de movimientos (filtrado)' : 'Detalle de movimientos'}</h2>
    ${data.filtrado ? `<p class="nota">Detalle filtrado por: <strong>${esc(data.filtroLabel)}</strong>.
      El saldo corrido no se muestra porque depende de todos los movimientos del rango.</p>` : ''}
    <table class="grid">
      <thead>${head}</thead>
      <tbody>${cuerpo}${totales}</tbody>
    </table>`;
}

function tablaClasificaciones(data: ReporteCuentasData): string {
  const filas = data.clasificaciones.length === 0
    ? `<tr><td colspan="3" class="vacio">Sin gastos clasificados en el rango.</td></tr>`
    : data.clasificaciones
        .map(
          (c) => `<tr>
            <td>${esc(c.label)}</td>
            <td class="num">${esc(String(c.count))}</td>
            <td class="num">${esc(fmtReporteNumero(c.total))}</td>
          </tr>`,
        )
        .join('');
  const total = data.clasificaciones.reduce((s, c) => s + c.total, 0);
  const movs = data.clasificaciones.reduce((s, c) => s + c.count, 0);
  return `
    <h2>Resumen por clasificación</h2>
    <table class="grid">
      <thead><tr><th>Clasificación</th><th class="num">Movimientos</th><th class="num">Total</th></tr></thead>
      <tbody>
        ${filas}
        <tr class="total-row">
          <td>TOTAL</td>
          <td class="num">${esc(String(movs))}</td>
          <td class="num">${esc(fmtReporteNumero(total))}</td>
        </tr>
      </tbody>
    </table>`;
}

/** Documento imprimible (Guardar como PDF) del libro de caja. */
export function buildReporteCuentasHtml(data: ReporteCuentasData): string {
  const resumen = data.incluirResumen
    ? `<table class="resumen"><tr>
        ${celdaResumen('Saldo inicial', fmtReporteMoneda(data.saldoInicial, data.moneda))}
        ${celdaResumen('Ingresos', fmtReporteMoneda(data.totalIngresos, data.moneda))}
        ${celdaResumen('Egresos', fmtReporteMoneda(data.totalEgresos, data.moneda))}
        ${celdaResumen('Saldo final', fmtReporteMoneda(data.saldoFinal, data.moneda), data.saldoFinal < 0)}
      </tr></table>
      ${data.filtrado ? `<p class="nota">El resumen corresponde a <strong>todos</strong> los movimientos de la cuenta en el rango,
        sin aplicar el filtro del detalle.</p>` : ''}`
    : '';

  const detalle = data.incluirDetalle ? tablaDetalle(data) : '';
  const clasificaciones = data.incluirClasificaciones ? tablaClasificaciones(data) : '';

  return `<!DOCTYPE html>
<html lang="es">
<head>
<meta charset="utf-8" />
<title>Libro de caja · ${esc(data.cuenta)}</title>
<style>${CSS}</style>
</head>
<body>
  <div class="encabezado">
    <div class="marca">COMERCIALIZADORA YEIKAR<span>Mueblería · ERP</span></div>
    <div class="der">
      <div class="titulo">Libro de caja</div>
      <div class="gen">Generado el ${esc(data.generadoEn)}</div>
    </div>
  </div>
  <div class="divisor"></div>

  <table class="meta"><tr>
    <td><span class="lab">Cuenta</span><span class="val">${esc(data.cuenta)}</span></td>
    <td><span class="lab">Moneda</span><span class="val">${esc(data.moneda)}</span></td>
    <td><span class="lab">Periodo</span><span class="val">${esc(fmtReporteFecha(data.desde))} a ${esc(fmtReporteFecha(data.hasta))}</span></td>
    <td><span class="lab">Filtro</span><span class="val">${esc(data.filtroLabel)}</span></td>
  </tr></table>

  ${resumen}
  ${detalle}
  ${clasificaciones}

  <div class="pie">
    <span>COMERCIALIZADORA YEIKAR · Documento generado desde el ERP</span>
    <span>${esc(data.cuenta)} · ${esc(data.moneda)}</span>
  </div>
</body>
</html>`;
}

/** Abre una ventana con el documento y dispara el diálogo de impresión. */
export function imprimirReporteCuentas(data: ReporteCuentasData): boolean {
  const ventana = window.open('', '_blank');
  if (!ventana) return false;
  ventana.document.write(buildReporteCuentasHtml(data));
  ventana.document.close();
  ventana.focus();
  setTimeout(() => ventana.print(), 300);
  return true;
}
