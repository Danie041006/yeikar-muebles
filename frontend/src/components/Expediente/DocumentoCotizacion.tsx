import React from 'react';
import { formatCurrency, fmtConversionTasa } from '../../utils/format';
import { fmtFechaVE } from '../../utils/fechas';
import { METODOS_PAGO } from '../../services/ventaService';

export interface PagoDocumento {
  id?: number;
  fecha: string;
  metodo_pago?: string | null;
  referencia?: string | null;
  observaciones?: string | null;
  monto: number;
  moneda?: { simbolo?: string | null; codigo?: string | null } | null;
  monto_en_moneda_base?: number | null;
  tasa_cambio?: number | null;
}

export interface DetalleDocumento {
  producto_id?: number | null;
  material_id?: number | null;
  tipo_item?: string | null;
  producto_nombre?: string | null;
  /** Nombre del material cuando el renglón es un INSUMO (respaldo por si el
   *  llamador no pudo resolver `producto_nombre` con su catálogo paginado). */
  material_nombre?: string | null;
  /** Descripción del mueble a la medida (lo que se escribió en el renglón). */
  descripcion_especifica?: string | null;
  cantidad: number;
  precio: number;
  ancho?: number | null;
  largo?: number | null;
  observaciones?: string | null;
  foto?: string | null | undefined;
  /** Unidad vendida del insumo (cm/m) y equivalencia en la unidad base. */
  unidad_captura?: 'M' | 'CM' | null;
  cantidad_base?: number | null;
  unidad_medida?: string | null;
  /** Fotos del producto EN ORDEN DE SUBIDA (la primera es la portada). El
   * documento muestra hasta 2; las demás solo salen en la Hoja de Trabajo. */
  fotos?: string[] | null;
  /** Piezas del juego: se listan como "Incluye: …" (con su precio si lo traen). */
  piezas?: {
    nombre: string;
    cantidad: number;
    precio?: number | null;
    precio_modificacion?: number | null;
    requiere_retrabajo?: boolean;
  }[] | null;
}

/**
 * Miniaturas de un renglón: 1 foto se ve como siempre (64 px); con 2 fotos
 * se muestran lado a lado un poco más chicas para no apretar la columna.
 */
function FotosRenglon({ urls, alt }: { urls: string[]; alt: string }) {
  if (urls.length === 0) return null;
  const doble = urls.length > 1;
  return (
    <div className="flex shrink-0 items-center gap-1">
      {urls.map((u, i) => (
        <img
          key={i}
          src={u}
          alt={doble ? `${alt} (vista ${i + 1})` : alt}
          className={`${doble ? 'h-14 w-14' : 'h-[84px] w-[84px]'} rounded-lg object-cover border border-stone-300 shrink-0`}
          loading="lazy"
        />
      ))}
    </div>
  );
}

export interface ClienteDocumento {
  nombre?: string | null;
  telefono?: string | null;
  direccion?: string | null;
  cedula?: string | null;
}

export interface VentaDocumento {
  total?: number;
  total_pagado: number;
  saldo_pendiente: number;
  pagos: PagoDocumento[];
}

type PagoConSaldo = {
  pago: PagoDocumento;
  abono: number;
  saldo: number;
};

const FILAS_TABLA_NEGOCIO = 24;
const FILAS_TOTAL_NEGOCIO = 1;
const FILAS_CABECERA_ABONOS_NEGOCIO = 1;

function pagosConSaldo(pagos: PagoDocumento[], saldoInicial: number): PagoConSaldo[] {
  let saldo = Math.max(0, Number(saldoInicial) || 0);
  return [...pagos]
    .sort((a, b) => a.fecha.localeCompare(b.fecha) || (a.id ?? 0) - (b.id ?? 0))
    .map((pago) => {
      const abono = Math.max(0, Number(pago.monto_en_moneda_base ?? pago.monto) || 0);
      saldo = Math.max(0, saldo - abono);
      return { pago, abono, saldo };
    });
}

function esAbonoInicial(pago: PagoDocumento): boolean {
  return pago.referencia
    ?.toLocaleLowerCase()
    .startsWith('adelanto conversión cotización') ?? false;
}

function descripcionPagoInterno(pago: PagoDocumento): string {
  const metodo = METODOS_PAGO.find((m) => m.value === pago.metodo_pago)?.label ?? pago.metodo_pago;
  return [
    esAbonoInicial(pago) ? 'Abono inicial' : metodo,
    esAbonoInicial(pago) ? metodo : pago.referencia,
    pago.observaciones,
  ].filter(Boolean).join(' · ') || 'Abono registrado';
}

interface Props {
  cotizacion: {
    id: number;
    fecha?: string | null;
    moneda_codigo?: string | null;
    tasa_cambio?: number | null;
    total_estimado: number;
    cliente?: ClienteDocumento | null;
    detalles: DetalleDocumento[];
  };
  rif?: string;
  direccion?: string;
  telefono?: string;
  descuentoPct?: number;
  ivaPct?: number;
  venta?: VentaDocumento | null;
  copia?: 'cliente' | 'interna';
  containerId?: string;
  className?: string;
}

/**
 * Documento de Cotización YEIKAR — la MISMA plantilla que se usa para
 * generar el PDF en Cotizaciones.tsx (fuente única del documento).
 * También se usa en el Expediente en modo SOLO LECTURA (sin descarga).
 */
export default function DocumentoCotizacion({
  cotizacion,
  rif = 'J-50146039-3',
  direccion = 'AV. INTERCOMUNAL CON CALLE 16 LOCAL Nro 15-205, BARRIO SIMÓN BOLÍVAR, UREÑA, TÁCHIRA',
  telefono = '+58 412-1234567',
  descuentoPct = 0,
  ivaPct = 0,
  venta,
  copia = 'cliente',
  containerId,
  className = '',
}: Props) {
  const moneda = cotizacion.moneda_codigo || 'COP';
  const subTotal = Number(cotizacion.total_estimado) || 0;
  const discountVal = subTotal * (Number(descuentoPct || 0) / 100);
  const netSubTotal = subTotal - discountVal;
  const ivaVal = netSubTotal * (Number(ivaPct || 0) / 100);
  const grandTotal = netSubTotal + ivaVal;
  const saldoInicialControl = Number(venta?.total ?? grandTotal);
  const pagosControl = pagosConSaldo(venta?.pagos ?? [], saldoInicialControl);
  const filasControlVacias = Math.max(
    0,
    FILAS_TABLA_NEGOCIO
      - cotizacion.detalles.length
      - pagosControl.length
      - FILAS_TOTAL_NEGOCIO
      - FILAS_CABECERA_ABONOS_NEGOCIO,
  );

  return (
    <div
      id={containerId}
      className={`bg-white shadow-2xl relative text-stone-800 font-sans mx-auto ${copia === 'interna' ? 'cotizacion-interna' : ''} ${className}`}
      style={{
        width: '215.9mm',
        minHeight: '279.4mm',
        padding: copia === 'interna' ? '8mm 10mm' : '14mm 15mm',
        boxSizing: 'border-box',
        display: 'flex',
        flexDirection: 'column',
      }}
    >
      {/* Watermark */}
      <div className={`absolute inset-0 flex items-center justify-center pointer-events-none z-0 select-none ${copia === 'interna' ? 'opacity-[0.16]' : 'opacity-[0.06]'}`}>
        <img src="/logo-marca-de-agua.PNG" alt="" className={`${copia === 'interna' ? 'w-[460px]' : 'w-[420px]'} h-auto`} />
      </div>

      {/* ── All content above watermark ── */}
      <div className={`relative z-10 flex flex-1 flex-col ${copia === 'interna' ? 'gap-2' : 'gap-4'}`}>
        <div className={`flex flex-col ${copia === 'interna' ? 'gap-2' : 'gap-4'}`}>

          {/* ── Header ── */}
          <div className="flex justify-between items-start pb-3 border-b border-stone-300">
            <div className={`${copia === 'interna' ? 'space-y-0.5' : 'space-y-1.5'} max-w-[60%]`}>
              <img src="/Logo-yeikar.png" alt="Yeikar" className={`${copia === 'interna' ? 'h-10' : 'h-14'} object-contain`} />
              <div className={`font-serif font-bold text-stone-955 tracking-widest uppercase ${copia === 'interna' ? 'text-[11px] mt-0.5' : 'text-[12.5px] mt-1'}`}>
                Comercializadora Yeikar
              </div>
              <div className="text-[9px] text-stone-600 font-mono font-semibold">RIF: {rif}</div>
              <div className="text-[9px] text-stone-650 font-medium leading-snug">DIRECCIÓN: {direccion}</div>
              <div className="text-[9px] text-stone-600 font-mono font-semibold">TELÉFONO: {telefono}</div>
            </div>

            <div className={`text-right border border-stone-300 rounded-lg bg-stone-50 shadow-sm ${copia === 'interna' ? 'p-2 min-w-[150px]' : 'p-3 min-w-[170px]'}`}>
              <div className="text-[9px] font-bold text-stone-700 uppercase tracking-[0.15em]">Cotización Inicial</div>
              <div className="text-base font-bold text-amber-800 font-mono tracking-widest mt-0.5">
                N°: 00 – {String(cotizacion.id).padStart(5, '0')}
              </div>
              <div className="text-[9px] text-stone-600 font-mono font-bold mt-1 uppercase tracking-wider">
                Fecha: {cotizacion.fecha || '—'}
              </div>
              <div className={`mt-1 text-[8px] font-bold uppercase tracking-[0.14em] ${copia === 'interna' ? 'text-amber-800' : 'text-stone-500'}`}>
                {copia === 'interna' ? 'Para el negocio' : 'Para el cliente'}
              </div>
            </div>
          </div>

          {/* ── Client Info ── */}
          <div className={`grid grid-cols-3 ${copia === 'interna' ? 'gap-x-3 gap-y-1 px-3 py-1.5 my-0' : 'gap-4 px-4 py-3 my-1'} bg-stone-50/40 border border-stone-250 rounded-xl shadow-sm`}>
            {[
              { label: 'CLIENTE', value: cotizacion.cliente?.nombre },
              { label: 'TELÉFONO', value: cotizacion.cliente?.telefono || '—' },
              { label: 'DIRECCIÓN', value: cotizacion.cliente?.direccion || '—' },
              { label: 'CEDULA', value: cotizacion.cliente?.cedula || '—' },
            ].map(({ label, value }) => (
              <div key={label} className="min-w-0">
                <div className={`${copia === 'interna' ? 'text-[9px]' : 'text-[8px]'} uppercase tracking-[0.14em] text-stone-550 font-bold mb-0.5`}>{label}</div>
                <div className={`${copia === 'interna' ? 'text-[10px] leading-tight' : 'text-[11px] leading-relaxed'} text-stone-950 font-extrabold whitespace-pre-wrap break-words`} title={value || '—'}>{value}</div>
              </div>
            ))}
          </div>

          {/* ── Items Table ── */}
          <div className={`border border-stone-300 overflow-hidden ${copia === 'interna' ? 'rounded-md' : 'rounded-lg shadow-sm'}`}>
            <table className={`w-full border-collapse ${copia === 'interna' ? 'text-[10px]' : 'text-[11px]'}`} style={{ tableLayout: 'fixed' }}>
              {/* Modelo y Descripción van en UNA sola columna ancha: el nombre
                  del mueble debe leerse en una línea horizontal junto a la foto. */}
              <colgroup>
                <col style={{ width: copia === 'interna' ? '14%' : '70%' }} />
                <col style={{ width: copia === 'interna' ? '48%' : '5.5%' }} />
                <col style={{ width: copia === 'interna' ? '19%' : '12.5%' }} />
                <col style={{ width: copia === 'interna' ? '19%' : '12%' }} />
              </colgroup>
              <thead>
                <tr className="bg-stone-900 text-stone-100">
                  {(copia === 'interna'
                    ? ['Cantidad', 'Descripción', 'P. unit.', 'Total']
                    : ['Descripción', 'Cant.', 'P. Unitario', 'Total']
                  ).map((h, i) => (
                    <th key={h} className={`${copia === 'interna' ? 'border-r border-stone-600 last:border-r-0 px-1 py-1 text-[9px]' : 'py-2 text-[9px]'} font-serif font-bold uppercase tracking-[0.1em]
                      ${i === 0 ? 'text-left' : i === 1 ? 'text-center' : 'text-right'}`}>{h}</th>
                  ))}
                </tr>
              </thead>
              <tbody className={copia === 'interna' ? 'font-mono' : 'divide-y divide-stone-200'}>
                {cotizacion.detalles && cotizacion.detalles.length > 0 ? (
                  cotizacion.detalles.map((det, idx) => {
                    // INSUMO: material vendido suelto (producto_id NULL) — sin
                    // medidas paramétricas; su descripción son las observaciones.
                    const esInsumo = det.tipo_item === 'INSUMO';
                    // Ítem sin producto ni insumo asociado (importación
                    // histórica): nombre y descripción se FUSIONAN en un solo
                    // campo — nunca se muestra "Prod #?".
                    const sinAsociar = !det.producto_id && !det.material_id;
                    // A la medida: se imprime lo que la vendedora escribió en
                    // el renglón (descripción específica), no "Ítem a medida".
                    const textoItem = det.descripcion_especifica
                      || det.producto_nombre
                      || det.material_nombre
                      || det.observaciones
                      || 'ÍTEM A MEDIDA';
                    // Nota extra del renglón (si escribieron descripción y
                    // además observaciones) para no perder nada de lo tecleado.
                    const notaItem = det.observaciones && det.observaciones !== textoItem
                      ? det.observaciones
                      : null;
                    const modelName = det.producto_nombre
                      || det.material_nombre
                      || (det.material_id ? `Insumo #${det.material_id}` : 'Ítem a medida');
                    // Las medidas solo se imprimen si las escribieron de verdad.
                    // El 1×1 por defecto del formulario NO es una medida: ya
                    // no se capturan medidas y no debe salir en el documento.
                    const anchoNum = Number(det.ancho);
                    const largoNum = Number(det.largo);
                    const tieneMedidas = !sinAsociar
                      && !esInsumo
                      && det.ancho != null
                      && det.largo != null
                      && anchoNum > 0
                      && largoNum > 0
                      && !(anchoNum === 1 && largoNum === 1);
                    const dims = tieneMedidas ? `${det.ancho}×${det.largo} m` : null;
                    // Unidad vendida del insumo: cm/m capturados o la unidad
                    // base del material. En la cotización se muestra lo que
                    // ve el cliente (1128 cm), no la equivalencia interna.
                    const unidadInsumo = esInsumo
                      ? (det.unidad_captura === 'CM'
                        ? 'cm'
                        : det.unidad_captura === 'M'
                          ? 'm'
                          : (det.unidad_medida || ''))
                      : '';
                    const equivalencia = esInsumo
                      && det.cantidad_base != null
                      && unidadInsumo === 'cm'
                      && det.unidad_medida
                      ? `${Number(det.cantidad_base).toLocaleString('es-CO', { maximumFractionDigits: 4 })} ${det.unidad_medida}`
                      : null;
                    const piezasTxt = (det.piezas?.length ?? 0) > 0
                      ? `Incluye: ${det.piezas!
                          .map((p) => {
                            const extra = p.requiere_retrabajo
                              ? Number(p.precio_modificacion) || 0
                              : 0;
                            const precioTxt = p.precio != null
                              ? ` (${formatCurrency(Number(p.precio) + extra, moneda)})`
                              : '';
                            const cantTxt = Number(p.cantidad) > 1
                              ? ` × ${Number(p.cantidad).toLocaleString('es-CO')}`
                              : '';
                            return `${p.nombre}${cantTxt}${precioTxt}`;
                          })
                          .join(', ')}`
                      : null;
                    const desc = [
                      dims,
                      det.observaciones,
                      equivalencia ? `Equivale a ${equivalencia}` : null,
                      piezasTxt,
                    ].filter(Boolean).join(' — ');
                    const rowTotal = Number(det.precio) * Number(det.cantidad);
                    const cantidadTxt = Number.isFinite(Number(det.cantidad))
                      ? Number(det.cantidad).toLocaleString('es-CO', { maximumFractionDigits: 4 })
                      : '0';
                    const cantTexto = unidadInsumo ? `${cantidadTxt} ${unidadInsumo}` : cantidadTxt;
                    // Hasta 2 fotos por renglón (portada + segunda vista). El
                    // resto queda para la Hoja de Trabajo del taller.
                    const fotosDet = copia === 'cliente'
                      ? (
                          det.fotos && det.fotos.length > 0
                            ? det.fotos
                            : det.foto
                              ? [det.foto]
                              : []
                        ).filter((u): u is string => !!u).slice(0, 2)
                      : [];
                    if (copia === 'interna') {
                      const descripcionInterna = sinAsociar
                        ? [notaItem, equivalencia, piezasTxt].filter(Boolean).join(' — ')
                        : desc;
                      return (
                        <tr key={idx} className={`${idx % 2 === 0 ? 'bg-white/55' : 'bg-stone-50/55'} h-6 border-b border-stone-300 break-inside-avoid`}>
                          <td className="border-r border-stone-300 px-1 py-0.5 text-center align-top font-mono font-bold text-stone-800">{cantTexto}</td>
                          <td className="border-r border-stone-300 px-1.5 py-0.5 align-top leading-tight break-words">
                            <span className="font-serif font-bold text-stone-950">{sinAsociar ? textoItem : modelName}</span>
                            {descripcionInterna && <span className="ml-1 font-normal italic text-stone-600">{descripcionInterna}</span>}
                          </td>
                          <td className="border-r border-stone-300 px-1 py-0.5 text-right align-top font-mono text-stone-800">{formatCurrency(Number(det.precio), moneda)}</td>
                          <td className="px-1 py-0.5 text-right align-top font-mono font-bold text-stone-950">{formatCurrency(rowTotal, moneda)}</td>
                        </tr>
                      );
                    }
                    return (
                      <tr key={idx} className={idx % 2 === 0 ? 'bg-white' : 'bg-stone-50/60'}>
                        {sinAsociar ? (
                          <td colSpan={2} className="px-3 py-2 font-serif font-bold text-stone-950">
                            <div className="flex items-center gap-2.5">
                              <FotosRenglon urls={fotosDet} alt={textoItem} />
                              <span className="min-w-0 flex-1 whitespace-nowrap text-[10px] leading-normal">
                                <span className="font-mono font-extrabold mr-1.5">{cantTexto} ×</span>
                                {textoItem}
                                {notaItem && (
                                  <span className="ml-2 text-[9px] text-stone-600 italic font-medium">{notaItem}</span>
                                )}
                              </span>
                            </div>
                          </td>
                        ) : (
                          <>
                            <td className="px-2.5 py-2 font-serif font-bold text-stone-950">
                              <div className="flex items-center gap-2.5">
                                <FotosRenglon urls={fotosDet} alt={modelName} />
                                {/* Una sola línea: el nombre manda; la descripción
                                    (medidas/notas/piezas) va inline en menor tamaño. */}
                                <span className="min-w-0 flex-1 whitespace-nowrap text-[10px] leading-normal">
                                  <span className="font-serif font-extrabold">{modelName}</span>
                                  {desc && (
                                    <span className="ml-2 text-[9px] font-medium italic text-stone-600">
                                      {desc}
                                    </span>
                                  )}
                                </span>
                              </div>
                            </td>
                            <td className="px-1 py-2 text-center font-mono font-extrabold text-[10px] text-stone-900">{cantTexto}</td>
                          </>
                        )}
                        <td className="px-1.5 py-2 text-right font-mono text-stone-850 font-medium text-[10px]">{formatCurrency(Number(det.precio), moneda)}</td>
                        <td className="px-1.5 py-2 text-right font-mono font-extrabold text-[10px] text-stone-950">{formatCurrency(rowTotal, moneda)}</td>
                      </tr>
                    );
                  })
                ) : (
                  <tr><td colSpan={4} className="px-3 py-4 text-center text-stone-400 italic">Sin renglones.</td></tr>
                )}
                {copia === 'interna' && (
                  <>
                    <tr className="h-6 border-y border-stone-400 bg-amber-50/85 font-mono text-[10.5px] font-extrabold">
                      <td className="border-r border-stone-300 px-1 py-0.5" />
                      <td className="border-r border-stone-300 px-1.5 py-0.5" />
                      <td className="border-r border-stone-300 px-1 py-0.5 text-right">TOTAL</td>
                      <td className="px-1 py-0.5 text-right text-stone-950">{formatCurrency(grandTotal, moneda)}</td>
                    </tr>
                    <tr className="border-y border-stone-400 bg-stone-100/85 text-[9px] font-bold uppercase tracking-wider text-stone-800">
                      <th className="border-r border-stone-300 px-1 py-1 text-left">Fecha</th>
                      <th className="border-r border-stone-300 px-1.5 py-1 text-left">Detalle / método</th>
                      <th className="border-r border-stone-300 px-1 py-1 text-right">Abono</th>
                      <th className="px-1 py-1 text-right">Saldo</th>
                    </tr>
                    {pagosControl.map(({ pago, abono, saldo }, idx) => (
                      <tr key={pago.id ?? `pago-control-${idx}`} className="h-6 border-b border-stone-300 bg-white/55 break-inside-avoid text-[10.5px]">
                        <td className="border-r border-stone-300 px-1 py-0.5 align-top whitespace-nowrap text-stone-700">{fmtFechaVE(pago.fecha)}</td>
                        <td className="border-r border-stone-300 px-1.5 py-0.5 align-top leading-tight break-words font-semibold text-stone-800">{descripcionPagoInterno(pago)}</td>
                        <td className="border-r border-stone-300 px-1 py-0.5 text-right align-top font-bold text-stone-900">{formatCurrency(abono, moneda)}</td>
                        <td className="px-1 py-0.5 text-right align-top font-bold text-stone-900">{formatCurrency(saldo, moneda)}</td>
                      </tr>
                    ))}
                    {Array.from({ length: filasControlVacias }, (_, idx) => (
                      <tr key={`abono-manual-${idx}`} className="h-6 border-b border-stone-300 bg-white/35 break-inside-avoid">
                        <td className="border-r border-stone-300 px-1 py-0.5">&nbsp;</td>
                        <td className="border-r border-stone-300 px-1.5 py-0.5" />
                        <td className="border-r border-stone-300 px-1 py-0.5" />
                        <td className="px-1 py-0.5" />
                      </tr>
                    ))}
                  </>
                )}
              </tbody>
            </table>
          </div>

          {/* ── Dynamic Payments History (Seguimiento de Abonos) ── */}
          {copia === 'cliente' && venta && venta.pagos && venta.pagos.length > 0 && (
            <div className="my-1">
              <div className="text-[8.5px] font-serif font-bold uppercase tracking-wider text-stone-800 mb-1 flex items-center justify-between">
                <span>Historial de Abonos / Pagos Realizados</span>
                <span className="font-mono text-stone-600 font-normal">({venta.pagos.length} registros)</span>
              </div>
              <div className="border border-stone-300 rounded-lg overflow-hidden shadow-sm">
                <table className="w-full border-collapse text-[10px]">
                  <thead>
                    <tr className="bg-stone-100 text-stone-800 font-bold uppercase text-[8.5px] tracking-wider border-b border-stone-300">
                      <th className="px-2 py-1 text-left">Fecha</th>
                      <th className="px-2 py-1 text-left">Método</th>
                      <th className="px-2 py-1 text-left">Ref.</th>
                      <th className="px-2 py-1 text-right">Monto Recibido</th>
                      <th className="px-2 py-1 text-right">Equivalente en {moneda}</th>
                    </tr>
                  </thead>
                  <tbody className="divide-y divide-stone-200 font-mono">
                    {venta.pagos.map((p, idx) => {
                      const metodoLabel = METODOS_PAGO.find((m) => m.value === p.metodo_pago)?.label ?? p.metodo_pago;
                      const inicial = esAbonoInicial(p);
                      const simbolo = p.moneda?.simbolo ?? '';
                      const conversion = fmtConversionTasa(
                        Number(p.monto),
                        Number(p.monto_en_moneda_base ?? 0),
                        p.tasa_cambio,
                        p.moneda?.codigo,
                        moneda,
                      );
                      return (
                        <tr key={p.id || idx} className={idx % 2 === 0 ? 'bg-white' : 'bg-stone-50/50'}>
                          <td className="px-2 py-1 text-stone-700">{fmtFechaVE(p.fecha)}</td>
                          <td className="px-2 py-1 font-bold text-stone-900">
                            {inicial ? `Abono inicial · ${metodoLabel}` : metodoLabel}
                          </td>
                          <td className="px-2 py-1 text-stone-600">{inicial ? '—' : p.referencia || '—'}</td>
                          <td className="px-2 py-1 text-right font-bold text-stone-800">
                            {simbolo}{Number(p.monto).toLocaleString('es-ES')}
                          </td>
                          <td className="px-2 py-1 text-right font-bold text-emerald-800">
                            {formatCurrency(Number(p.monto_en_moneda_base || p.monto), moneda)}
                            {conversion && (
                              <span className="block text-[7px] text-stone-500 font-normal">{conversion}</span>
                            )}
                          </td>
                        </tr>
                      );
                    })}
                  </tbody>
                </table>
              </div>
            </div>
          )}

          {/* ── Totals: Left=breakdown, Right=grand total card ── */}
          {copia === 'cliente' && <div className="grid grid-cols-2 gap-4 pt-1">
            {/* Left — subtotal breakdown */}
            <div className="space-y-1.5 text-[11px] text-stone-700 pr-2">
              {[
                { label: 'Sub-Total', value: subTotal, color: 'text-stone-900 font-bold' },
                ...(Number(descuentoPct) > 0 ? [{ label: `Descuento (${descuentoPct}%)`, value: -discountVal, color: 'text-emerald-800 font-bold' }] : []),
                { label: 'Neto Sub-Total', value: netSubTotal, color: 'text-stone-900 font-bold' },
                ...(Number(ivaPct) > 0 ? [{ label: `IVA (${ivaPct}%)`, value: ivaVal, color: 'text-stone-900 font-bold' }] : []),
              ].map(({ label, value, color }, i, arr) => (
                <div key={label} className={`flex justify-between items-center ${i === arr.length - 1 ? 'border-t border-stone-300 pt-1' : ''}`}>
                  <span className="text-[8.5px] uppercase tracking-wider font-bold text-stone-500">{label}</span>
                  <span className={`font-mono font-extrabold ${color}`}>
                    {value < 0 ? '-' : ''}{formatCurrency(Math.abs(value), moneda)}
                  </span>
                </div>
              ))}
            </div>

            {/* Right — grand total card */}
            <div className="bg-amber-50/60 rounded-xl p-4 flex flex-col gap-1.5 border border-amber-300/80 shadow-sm">
              <div className="flex justify-between items-baseline gap-3">
                <span className="text-[10px] tracking-[0.15em] font-bold text-stone-700 uppercase">Total Cotización</span>
                <span className="text-xl font-black text-amber-900 font-mono">
                  {formatCurrency(grandTotal, moneda)}
                </span>
              </div>

              {venta && Number(venta.total_pagado) > 0 && (
                <div className="flex justify-between items-baseline text-[10px] text-emerald-800 font-mono font-extrabold border-t border-amber-200/60 pt-1">
                  <span>TOTAL ABONADO:</span>
                  <span>-{formatCurrency(Number(venta.total_pagado), moneda)}</span>
                </div>
              )}

              <div className="border-t border-amber-200/80 pt-1.5 space-y-0.5 text-[10px]">
                {venta && (
                  <div className="flex justify-between text-amber-900 font-mono font-black text-[11px]">
                    <span>SALDO PENDIENTE:</span>
                    <span>{formatCurrency(Number(venta.saldo_pendiente), moneda)}</span>
                  </div>
                )}
              </div>
            </div>
          </div>}

          {/* ── Terms ── */}
          <div className={`border border-stone-300 rounded-lg bg-stone-55/40 font-medium text-stone-750 ${copia === 'interna' ? 'px-2 py-1.5 text-[8px] leading-tight' : 'px-4 py-3 text-[12px] leading-relaxed'}`}>
            <span className={`font-bold text-stone-900 uppercase tracking-wider mr-1 ${copia === 'interna' ? 'text-[8px]' : 'text-[11px]'}`}>Términos y Condiciones:</span>
            Una vez aceptado el pedido y firmado este comprobante se procederá con la fabricación personalizada. Debido a que el producto entra en proceso de corte e insumos a la medida,{' '}
            <strong className="text-stone-950 font-bold">no se aceptan cambios a último minuto</strong>.
          </div>
        </div>

        {/* ── Signatures ── */}
        <div className={`grid grid-cols-2 ${copia === 'interna' ? 'gap-8 pt-3' : 'gap-10 pt-8'} mt-auto`}>
          {['FIRMA DEL CLIENTE', 'FIRMA DEL EMISOR'].map((label) => (
            <div key={label} className="text-center">
              <div className="w-40 border-t border-stone-400 mx-auto mb-1" />
              <div className={`${copia === 'interna' ? 'text-[8px]' : 'text-[10px]'} font-serif font-bold uppercase tracking-wider text-stone-800`}>{label}</div>
              <div className={`${copia === 'interna' ? 'text-[7px]' : 'text-[9px]'} text-stone-500 font-medium mt-0.5`}>
                {label.includes('CLIENTE') ? 'Acepto Conforme' : 'Autorizado'}
              </div>
            </div>
          ))}
        </div>
      </div>{/* end z-10 */}
    </div>
  );
}
