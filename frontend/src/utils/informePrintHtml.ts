import { InformeMensualResponse } from '../services/reportesService';

const NOMBRES_MESES = [
  'Enero', 'Febrero', 'Marzo', 'Abril', 'Mayo', 'Junio',
  'Julio', 'Agosto', 'Septiembre', 'Octubre', 'Noviembre', 'Diciembre',
];

function nombreMes(mes: string): string {
  const [year, month] = mes.split('-').map(Number);
  if (!year || !month) return mes;
  return `${NOMBRES_MESES[month - 1]} ${year}`;
}

const fmtCop = (n: number | null | undefined): string =>
  `$${Math.round(Number(n) || 0).toLocaleString('es-CO')}`;

const esc = (s: unknown): string =>
  String(s ?? '')
    .replace(/&/g, '&amp;')
    .replace(/</g, '&lt;')
    .replace(/>/g, '&gt;')
    .replace(/"/g, '&quot;')
    .replace(/'/g, '&#39;');

type LineaGasto = { tipo_id: number; nombre: string; monto: number };

const CSS = `
  @page { size: A4 landscape; margin: 10mm 12mm; }
  * { box-sizing: border-box; }
  body { font-family: Arial, Helvetica, sans-serif; font-size: 11px; color: #111; margin: 0; }
  table { border-collapse: collapse; width: 100%; }
  table.grid td, table.grid th { border: 1px solid #999; padding: 3px 6px; }
  table.grid thead th { background: #eee; font-weight: bold; text-align: left; vertical-align: bottom; }
  table.grid tr.total-row td { font-weight: bold; background: #eee; }
  table.grid td.num, table.grid th.num { text-align: right; }
  .num { text-align: right; font-variant-numeric: tabular-nums; }
  .dev td { background: #fdeaea; }
  .neg { color: #c0392b; }
  .muted { color: #555; }
  table, thead th, tr.total-row td, .dev td { -webkit-print-color-adjust: exact; print-color-adjust: exact; }
  .page-break { page-break-before: always; }
  .encabezado { display: flex; justify-content: space-between; align-items: flex-end; margin-bottom: 6px; }
  .encabezado .marca { font-size: 22px; font-weight: 900; letter-spacing: -0.5px; }
  .encabezado .marca span { font-weight: 400; font-size: 11px; display: block; letter-spacing: 2px; text-transform: uppercase; color: #333; }
  .encabezado .der { text-align: right; }
  .encabezado .der .titulo { font-size: 18px; font-weight: 900; text-transform: uppercase; letter-spacing: -0.5px; }
  .encabezado .der .mes { font-size: 13px; font-weight: 700; margin-top: 2px; }
  .encabezado .der .gen { font-size: 10px; color: #555; margin-top: 2px; }
  .divisor { border-bottom: 3px solid #111; margin-bottom: 10px; }
  h2 { font-size: 14px; font-weight: 900; text-transform: uppercase; letter-spacing: -0.3px; border-bottom: 2px solid #111; padding-bottom: 3px; margin: 16px 0 8px; }
  .resumen td { border: 1px solid #999; padding: 8px 10px; text-align: center; }
  .resumen .label { font-size: 9px; font-weight: 700; text-transform: uppercase; letter-spacing: 1px; color: #555; display: block; }
  .resumen .valor { font-size: 20px; font-weight: 900; font-variant-numeric: tabular-nums; margin-top: 4px; }
  .er-table { width: 100%; }
  .er-table > tr > td, .er-left, .er-right { vertical-align: top; }
  .er-left { width: 50%; padding-right: 14px; }
  .er-right { width: 50%; padding-left: 14px; border-left: 1px solid #999; }
  table.detalle { margin-bottom: 12px; }
  table.detalle td { border: none; border-bottom: 1px solid #ddd; padding: 3px 4px; }
  table.detalle tr.cat td { font-weight: 700; text-transform: uppercase; font-size: 10px; letter-spacing: 1px; color: #333; border-bottom: 1px solid #111; padding-top: 8px; }
  table.detalle tr.total td { font-weight: 700; border-bottom: 1px solid #111; }
  table.detalle tr.total td.num { font-weight: 700; }
  .detalle .nota { font-size: 9px; font-weight: 400; color: #666; }
  .utilidad { display: flex; justify-content: space-between; align-items: center; border-top: 2px solid #111; margin-top: 6px; padding-top: 8px; }
  .utilidad .lab { font-size: 15px; font-weight: 900; text-transform: uppercase; letter-spacing: -0.5px; }
  .utilidad .val { font-size: 19px; font-weight: 900; font-variant-numeric: tabular-nums; }
  .vacio { padding: 14px; text-align: center; font-style: italic; color: #555; }
  .estado-sub { font-size: 9px; color: #555; }
`;

function seccion1(informe: InformeMensualResponse): string {
  const ci = informe.control_interno_ingresos;
  const filas =
    ci.lineas.length === 0
      ? `<tr><td colspan="11" class="vacio">No hay ventas registradas para este mes.</td></tr>`
      : ci.lineas
          .map((l) => {
            const pct = l.porcentaje_ganancia != null ? `${l.porcentaje_ganancia.toFixed(1)}%` : '—';
            const tasa = l.tasa_cambio ? l.tasa_cambio.toLocaleString('es-CO') : '—';
            return `<tr class="${l.es_devolucion ? 'dev' : ''}">
              <td>${esc(l.fecha.slice(0, 10))}</td>
              <td>${esc(l.cliente)}</td>
              <td class="num">${esc(l.cantidad)}</td>
              <td>${esc(l.producto)}</td>
              <td class="num">${fmtCop(l.precio_costo)}</td>
              <td class="num">${esc(pct)}</td>
              <td class="num">${fmtCop(l.utilidad)}</td>
              <td class="num">${fmtCop(l.precio_venta)}</td>
              <td class="num">${esc(l.moneda)}</td>
              <td class="num">${esc(tasa)}</td>
              <td class="num">${fmtCop(l.precio_venta_en_base)}</td>
            </tr>`;
          })
          .join('');
  return `
    <h2>1. Control Interno de Ingresos</h2>
    <table class="grid">
      <thead>
        <tr>
          <th>Fecha</th><th>Cliente</th><th class="num">Cant.</th><th>Detalle Producto</th>
          <th class="num">Precio Costo</th><th class="num">% Gan.</th><th class="num">Utilidad</th>
          <th class="num">Precio de Venta</th><th class="num">Mon.</th><th class="num">Tasa</th><th class="num">Valor en COP</th>
        </tr>
      </thead>
      <tbody>${filas}</tbody>
      <tfoot>
        <tr class="total-row">
          <td colspan="4">TOTALES</td>
          <td class="num">${fmtCop(ci.totales.precio_costo)}</td>
          <td></td>
          <td class="num">${fmtCop(ci.totales.utilidad)}</td>
          <td class="num">${fmtCop(ci.totales.precio_venta)}</td>
          <td></td>
          <td></td>
          <td class="num">${fmtCop(ci.totales.precio_venta_en_base)}</td>
        </tr>
      </tfoot>
    </table>`;
}

function seccion2(informe: InformeMensualResponse): string {
  const r = informe.resumen;
  const dispCls = r.disponible < 0 ? 'neg' : '';
  return `
    <h2>2. Resumen del Mes</h2>
    <table class="resumen">
      <tr>
        <td><span class="label">Ingresos (+)</span><span class="valor" style="color:#0a7d2c">${fmtCop(r.ingresos)}</span></td>
        <td><span class="label">Egresos (−)</span><span class="valor neg">${fmtCop(r.egresos)}</span></td>
        <td><span class="label">Disponible</span><span class="valor ${dispCls}">${fmtCop(r.disponible)}</span></td>
      </tr>
    </table>`;
}

function filaDetalle(label: string, valor: number, total?: boolean, nota?: string): string {
  return `<tr class="${total ? 'total' : ''}"><td>${esc(label)}${nota ? `<div class="nota">${esc(nota)}</div>` : ''}</td><td class="num">${fmtCop(valor)}</td></tr>`;
}

function bloqueInventario(titulo: string, lineas: { concepto_id: number; nombre: string; valor: number }[], total: number): string {
  const cuerpo =
    lineas.length === 0
      ? `<tr><td class="muted">Sin líneas registradas.</td><td class="num"></td></tr>`
      : lineas.map((l) => filaDetalle(l.nombre, l.valor)).join('');
  return `
    <table class="detalle">
      <tr class="cat"><td colspan="2">${esc(titulo)}</td></tr>
      ${cuerpo}
      ${filaDetalle(`Total ${titulo}`, total, true)}
    </table>`;
}

function bloqueGastos(titulo: string, lineas: LineaGasto[], subtotal: number): string {
  const cuerpo =
    lineas.length === 0
      ? `<tr><td class="muted">Sin gastos registrados.</td><td class="num"></td></tr>`
      : lineas.map((l) => filaDetalle(l.nombre, l.monto)).join('');
  return `
    <tr class="cat"><td colspan="2">${esc(titulo)}</td></tr>
    ${cuerpo}
    <tr class="total"><td>Subtotal ${esc(titulo)}</td><td class="num">${fmtCop(subtotal)}</td></tr>`;
}

function seccion3(informe: InformeMensualResponse): string {
  const er = informe.estado_resultados;
  const g = er.gastos;
  const utilCls = er.utilidad_periodo < 0 ? 'neg' : '';
  return `
    <div class="page-break"></div>
    <h2>3. Estado de Resultados</h2>
    <table class="er-table"><tr>
      <td class="er-left">
        <table class="detalle">
          <tr class="cat"><td colspan="2">Ventas</td></tr>
          ${filaDetalle('Contado', er.ventas.contado)}
          ${filaDetalle('Crédito', er.ventas.credito)}
          ${filaDetalle('(−) Devoluciones', -er.ventas.devoluciones)}
          ${filaDetalle('(−) Descuentos', -er.ventas.descuentos)}
          ${filaDetalle('Total Ventas Netas', er.ventas.total_ventas_netas, true)}
        </table>
        ${bloqueInventario('Inventario Inicial', er.inventarios_iniciales, er.total_inventarios_iniciales)}
        <table class="detalle">
          <tr class="cat"><td colspan="2">Compras</td></tr>
          ${filaDetalle('Contado', er.compras.contado)}
          ${filaDetalle('Crédito', er.compras.credito)}
          ${filaDetalle('Total Mercancía', er.compras.total_mercancia, true)}
        </table>
        ${bloqueInventario('Inventario Final', er.inventarios_finales, er.total_inventarios_finales)}
      </td>
      <td class="er-right">
        <table class="detalle">
          ${filaDetalle('Compras Netas', er.compras_netas, true, 'Inv. Inicial + Mercancía − Inv. Final')}
          ${filaDetalle('Utilidad Bruta', er.utilidad_bruta, true)}
        </table>
        <table class="detalle">
          <tr class="cat"><td colspan="2">Gastos del Periodo</td></tr>
          ${bloqueGastos('Operativos', g.operativos, g.total_gastos_operativos)}
          ${bloqueGastos('Administrativos', g.administrativos, g.total_gastos_administrativos)}
          ${bloqueGastos('Financieros', g.financieros, g.total_financieros)}
          ${bloqueGastos('Impuestos', g.impuestos, g.total_impuestos)}
          <tr class="total"><td>Total Gastos</td><td class="num">${fmtCop(g.total_gastos)}</td></tr>
        </table>
        <div class="utilidad">
          <span class="lab">Utilidad del Periodo</span>
          <span class="val ${utilCls}">${fmtCop(er.utilidad_periodo)}</span>
        </div>
      </td>
    </tr></table>`;
}

function seccion4(informe: InformeMensualResponse): string {
  const pp = informe.pendientes_de_pago;
  const filas =
    pp.lineas.length === 0
      ? `<tr><td colspan="9" class="vacio">No hay pendientes de pago al cierre de este mes.</td></tr>`
      : pp.lineas
          .map((l) => {
            const estado = l.estado_venta
              ? `<span>${esc(l.estado_venta)}</span>`
              : `<span>SIN FACTURAR</span><div class="estado-sub">${esc(l.estado_pedido)}</div>`;
            return `<tr>
              <td>#${esc(l.pedido_id)}</td>
              <td>${esc(l.fecha.slice(0, 10))}</td>
              <td>${esc(l.cliente)}</td>
              <td>${esc(l.producto)}</td>
              <td>${estado}</td>
              <td class="num">${esc(l.moneda)}</td>
              <td class="num">${fmtCop(l.total_en_base)}</td>
              <td class="num">${fmtCop(l.pagado_en_base)}</td>
              <td class="num" style="font-weight:bold">${fmtCop(l.saldo_en_base)}</td>
            </tr>`;
          })
          .join('');
  return `
    <div class="page-break"></div>
    <h2>4. Pendientes de Pago al Cierre</h2>
    <table class="grid">
      <thead>
        <tr>
          <th>Pedido</th><th>Fecha</th><th>Cliente</th><th>Productos</th><th>Estado</th>
          <th class="num">Mon.</th><th class="num">Total</th><th class="num">Pagado</th><th class="num">Saldo</th>
        </tr>
      </thead>
      <tbody>${filas}</tbody>
      <tfoot>
        <tr class="total-row">
          <td colspan="8">TOTAL PENDIENTE DE PAGO</td>
          <td class="num">${fmtCop(pp.total_pendiente)}</td>
        </tr>
      </tfoot>
    </table>`;
}

export function buildInformePrintHtml(informe: InformeMensualResponse, mes: string): string {
  const fecha = new Date().toLocaleDateString('es-CO');
  return `<!DOCTYPE html>
<html>
<head>
<meta charset="utf-8">
<title>Informe Mensual — ${esc(nombreMes(mes))}</title>
<style>${CSS}</style>
</head>
<body>
  <div class="encabezado">
    <div class="marca">YEIKAR<span>Fábrica de Muebles</span></div>
    <div class="der">
      <div class="titulo">Informe Mensual</div>
      <div class="mes">${esc(nombreMes(mes))}</div>
      <div class="gen">Generado el ${esc(fecha)} · Todas las cifras en COP</div>
    </div>
  </div>
  <div class="divisor"></div>
  ${seccion1(informe)}
  ${seccion2(informe)}
  ${seccion3(informe)}
  ${seccion4(informe)}
</body>
</html>`;
}
