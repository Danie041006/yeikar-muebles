import React from 'react';
import { formatCurrency } from '../../utils/format';
import { fmtFechaVE } from '../../utils/fechas';
import { METODOS_PAGO } from '../../services/ventaService';

export interface PagoDocumento {
  id?: number;
  fecha: string;
  metodo_pago?: string | null;
  referencia?: string | null;
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
  cantidad: number;
  precio: number;
  ancho?: number | null;
  largo?: number | null;
  observaciones?: string | null;
  foto?: string | null | undefined;
}

export interface ClienteDocumento {
  nombre?: string | null;
  telefono?: string | null;
  direccion?: string | null;
  cedula?: string | null;
}

export interface VentaDocumento {
  total_pagado: number;
  saldo_pendiente: number;
  pagos: PagoDocumento[];
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
  containerId,
  className = '',
}: Props) {
  const moneda = cotizacion.moneda_codigo || 'COP';
  const subTotal = Number(cotizacion.total_estimado) || 0;
  const discountVal = subTotal * (Number(descuentoPct || 0) / 100);
  const netSubTotal = subTotal - discountVal;
  const ivaVal = netSubTotal * (Number(ivaPct || 0) / 100);
  const grandTotal = netSubTotal + ivaVal;

  return (
    <div
      id={containerId}
      className={`bg-white shadow-2xl relative text-stone-800 font-sans mx-auto ${className}`}
      style={{
        width: '215.9mm',
        minHeight: '279.4mm',
        padding: '14mm 15mm',
        boxSizing: 'border-box',
        display: 'flex',
        flexDirection: 'column',
      }}
    >
      {/* Watermark */}
      <div className="absolute inset-0 flex items-center justify-center pointer-events-none opacity-[0.06] z-0 select-none">
        <img src="/logo-marca-de-agua.PNG" alt="" className="w-[420px] h-auto" />
      </div>

      {/* ── All content above watermark ── */}
      <div className="relative z-10 flex flex-col gap-4 flex-1">
        <div className="flex flex-col gap-4">

          {/* ── Header ── */}
          <div className="flex justify-between items-start pb-3 border-b border-stone-300">
            <div className="space-y-1.5 max-w-[60%]">
              <img src="/Logo-yeikar.png" alt="Yeikar" className="h-14 object-contain" />
              <div className="font-serif font-bold text-stone-955 text-[11.5px] tracking-widest uppercase mt-1">
                Comercializadora Yeikar
              </div>
              <div className="text-[8px] text-stone-600 font-mono font-semibold">RIF: {rif}</div>
              <div className="text-[8px] text-stone-650 font-medium leading-snug">DIRECCIÓN: {direccion}</div>
              <div className="text-[8px] text-stone-600 font-mono font-semibold">TELÉFONO: {telefono}</div>
            </div>

            <div className="text-right border border-stone-300 rounded-lg p-3 bg-stone-50 min-w-[170px] shadow-sm">
              <div className="text-[8.5px] font-bold text-stone-700 uppercase tracking-[0.15em]">Cotización Inicial </div>
              <div className="text-sm font-bold text-amber-800 font-mono tracking-widest mt-0.5">
                N°: 00 – {String(cotizacion.id).padStart(5, '0')}
              </div>
              <div className="text-[8px] text-stone-600 font-mono font-bold mt-1 uppercase tracking-wider">
                Fecha: {cotizacion.fecha || '—'}
              </div>
            </div>
          </div>

          {/* ── Client Info ── */}
          <div className="grid grid-cols-3 gap-4 bg-stone-50/40 border border-stone-250 rounded-xl px-4 py-3 my-1 shadow-sm">
            {[
              { label: 'CLIENTE', value: cotizacion.cliente?.nombre },
              { label: 'TELÉFONO', value: cotizacion.cliente?.telefono || '—' },
              { label: 'DIRECCIÓN', value: cotizacion.cliente?.direccion || '—' },
              { label: 'CEDULA', value: cotizacion.cliente?.cedula || '—' },
            ].map(({ label, value }) => (
              <div key={label} className="min-w-0">
                <div className="text-[7.5px] uppercase tracking-[0.14em] text-stone-550 font-bold mb-1">{label}</div>
                <div className="text-[10px] text-stone-950 font-extrabold leading-relaxed whitespace-pre-wrap break-words" title={value || '—'}>{value}</div>
              </div>
            ))}
          </div>

          {/* ── Items Table ── */}
          <div className="border border-stone-300 rounded-lg overflow-hidden shadow-sm">
            <table className="w-full border-collapse text-[9.5px]">
              <thead>
                <tr className="bg-stone-900 text-stone-100">
                  {['Modelo', 'Cant.', 'Descripción / Medidas', 'P. Unitario', 'Total'].map((h, i) => (
                    <th key={h} className={`px-3 py-2 font-serif font-bold uppercase tracking-[0.12em] text-[8px]
                      ${i === 0 ? 'text-left w-[20%]' : i === 1 ? 'text-center w-[8%]' : i === 2 ? 'text-left' : 'text-right w-[13%]'}`}>{h}</th>
                  ))}
                </tr>
              </thead>
              <tbody className="divide-y divide-stone-200">
                {cotizacion.detalles && cotizacion.detalles.length > 0 ? (
                  cotizacion.detalles.map((det, idx) => {
                    // INSUMO: material vendido suelto (producto_id NULL) — sin
                    // medidas paramétricas; su descripción son las observaciones.
                    const esInsumo = det.tipo_item === 'INSUMO';
                    // Ítem sin producto ni insumo asociado (importación
                    // histórica): nombre y descripción se FUSIONAN en un solo
                    // campo — nunca se muestra "Prod #?".
                    const sinAsociar = !det.producto_id && !det.material_id;
                    const textoItem = det.observaciones || det.producto_nombre || 'ÍTEM A MEDIDA';
                    const modelName = det.producto_nombre
                      || (det.material_id ? `Insumo #${det.material_id}` : 'Ítem a medida');
                    const dims = sinAsociar || esInsumo ? null : `${det.ancho ?? 1.0}×${det.largo ?? 1.0} m`;
                    const desc = [dims, det.observaciones].filter(Boolean).join(' — ');
                    const rowTotal = Number(det.precio) * Number(det.cantidad);
                    const cantTexto = Number(det.cantidad) % 1 === 0
                      ? Number(det.cantidad).toFixed(0)
                      : Number(det.cantidad).toFixed(2);
                    return (
                      <tr key={idx} className={idx % 2 === 0 ? 'bg-white' : 'bg-stone-50/60'}>
                        {sinAsociar ? (
                          <td colSpan={3} className="px-3 py-2 font-serif font-bold text-stone-950">
                            <div className="flex items-start gap-2">
                              {det.foto && (
                                <img
                                  src={det.foto || undefined}
                                  alt={textoItem}
                                  className="h-16 w-16 rounded-lg object-cover border border-stone-300 shrink-0"
                                  loading="lazy"
                                />
                              )}
                              <span>
                                <span className="font-mono font-extrabold mr-1.5">{cantTexto} ×</span>
                                {textoItem}
                              </span>
                            </div>
                          </td>
                        ) : (
                          <>
                            <td className="px-3 py-2 font-serif font-bold text-stone-950">
                              <div className="flex items-center gap-2">
                                {det.foto && (
                                  <img
                                    src={det.foto || undefined}
                                    alt={modelName}
                                    className="h-16 w-16 rounded-lg object-cover border border-stone-300 shrink-0"
                                    loading="lazy"
                                  />
                                )}
                                <span>{modelName}</span>
                              </div>
                            </td>
                            <td className="px-3 py-2 text-center font-mono font-extrabold text-stone-900">{cantTexto}</td>
                            <td className="px-3 py-2 text-stone-700 italic font-medium">{desc}</td>
                          </>
                        )}
                        <td className="px-3 py-2 text-right font-mono text-stone-850 font-medium">{formatCurrency(Number(det.precio), moneda)}</td>
                        <td className="px-3 py-2 text-right font-mono font-extrabold text-stone-950">{formatCurrency(rowTotal, moneda)}</td>
                      </tr>
                    );
                  })
                ) : (
                  <tr><td colSpan={5} className="px-3 py-4 text-center text-stone-400 italic">Sin renglones.</td></tr>
                )}
              </tbody>
            </table>
          </div>

          {/* ── Dynamic Payments History (Seguimiento de Abonos) ── */}
          {venta && venta.pagos && venta.pagos.length > 0 && (
            <div className="my-1">
              <div className="text-[8.5px] font-serif font-bold uppercase tracking-wider text-stone-800 mb-1 flex items-center justify-between">
                <span>Historial de Abonos / Pagos Realizados</span>
                <span className="font-mono text-stone-600 font-normal">({venta.pagos.length} registros)</span>
              </div>
              <div className="border border-stone-300 rounded-lg overflow-hidden shadow-sm">
                <table className="w-full border-collapse text-[8.5px]">
                  <thead>
                    <tr className="bg-stone-100 text-stone-800 font-bold uppercase text-[7.5px] tracking-wider border-b border-stone-300">
                      <th className="px-2 py-1 text-left">Fecha</th>
                      <th className="px-2 py-1 text-left">Método</th>
                      <th className="px-2 py-1 text-left">Ref.</th>
                      <th className="px-2 py-1 text-right">Monto Recibido</th>
                      <th className="px-2 py-1 text-right">Equivalente en COP</th>
                    </tr>
                  </thead>
                  <tbody className="divide-y divide-stone-200 font-mono">
                    {venta.pagos.map((p, idx) => {
                      const metodoLabel = METODOS_PAGO.find((m) => m.value === p.metodo_pago)?.label ?? p.metodo_pago;
                      const simbolo = p.moneda?.simbolo ?? '';
                      return (
                        <tr key={p.id || idx} className={idx % 2 === 0 ? 'bg-white' : 'bg-stone-50/50'}>
                          <td className="px-2 py-1 text-stone-700">{fmtFechaVE(p.fecha)}</td>
                          <td className="px-2 py-1 font-bold text-stone-900">{metodoLabel}</td>
                          <td className="px-2 py-1 text-stone-600">{p.referencia || '—'}</td>
                          <td className="px-2 py-1 text-right font-bold text-stone-800">
                            {simbolo}{Number(p.monto).toLocaleString('es-ES')}
                          </td>
                          <td className="px-2 py-1 text-right font-bold text-emerald-800">
                            {formatCurrency(Number(p.monto_en_moneda_base || p.monto), 'COP')}
                            {p.tasa_cambio && p.tasa_cambio !== 1 && (
                              <span className="block text-[7px] text-stone-500 font-normal">Tasa: {p.tasa_cambio}</span>
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
          <div className="grid grid-cols-2 gap-4 pt-1">
            {/* Left — subtotal breakdown */}
            <div className="space-y-1 text-[9.5px] text-stone-700 pr-2">
              {[
                { label: 'Sub-Total', value: subTotal, color: 'text-stone-900 font-bold' },
                ...(Number(descuentoPct) > 0 ? [{ label: `Descuento (${descuentoPct}%)`, value: -discountVal, color: 'text-emerald-800 font-bold' }] : []),
                { label: 'Neto Sub-Total', value: netSubTotal, color: 'text-stone-900 font-bold' },
                ...(Number(ivaPct) > 0 ? [{ label: `IVA (${ivaPct}%)`, value: ivaVal, color: 'text-stone-900 font-bold' }] : []),
              ].map(({ label, value, color }, i, arr) => (
                <div key={label} className={`flex justify-between items-center ${i === arr.length - 1 ? 'border-t border-stone-300 pt-1' : ''}`}>
                  <span className="text-[7.5px] uppercase tracking-wider font-bold text-stone-500">{label}</span>
                  <span className={`font-mono font-extrabold ${color}`}>
                    {value < 0 ? '-' : ''}{formatCurrency(Math.abs(value), moneda)}
                  </span>
                </div>
              ))}
            </div>

            {/* Right — grand total card */}
            <div className="bg-amber-50/60 rounded-xl p-3 flex flex-col gap-1.5 border border-amber-300/80 shadow-sm">
              <div className="flex justify-between items-baseline">
                <span className="text-[8px] tracking-[0.15em] font-bold text-stone-700 uppercase">Total Cotización</span>
                <span className="text-base font-black text-amber-900 font-mono">
                  {formatCurrency(grandTotal, moneda)}
                </span>
              </div>

              {venta && Number(venta.total_pagado) > 0 && (
                <div className="flex justify-between items-baseline text-[8.5px] text-emerald-800 font-mono font-extrabold border-t border-amber-200/60 pt-1">
                  <span>TOTAL ABONADO:</span>
                  <span>-{formatCurrency(Number(venta.total_pagado), 'COP')}</span>
                </div>
              )}

              <div className="border-t border-amber-200/80 pt-1.5 space-y-0.5 text-[8.5px]">
                {venta && (
                  <div className="flex justify-between text-amber-900 font-mono font-black text-[9.5px]">
                    <span>SALDO PENDIENTE:</span>
                    <span>{formatCurrency(Number(venta.saldo_pendiente), 'COP')}</span>
                  </div>
                )}
              </div>
            </div>
          </div>

          {/* ── Terms ── */}
          <div className="border border-stone-300 rounded-lg px-3 py-2 bg-stone-55/40 text-[10.5px] text-stone-750 leading-relaxed font-medium">
            <span className="font-bold text-stone-900 text-[10px] uppercase tracking-wider mr-1">Términos y Condiciones:</span>
            Una vez aceptado el pedido y firmado este comprobante se procederá con la fabricación personalizada. Debido a que el producto entra en proceso de corte e insumos a la medida,{' '}
            <strong className="text-stone-950 font-bold">no se aceptan cambios a último minuto</strong>.
          </div>
        </div>

        {/* ── Signatures ── */}
        <div className="grid grid-cols-2 gap-10 pt-8 mt-auto">
          {['FIRMA DEL CLIENTE', 'FIRMA DEL EMISOR'].map((label) => (
            <div key={label} className="text-center">
              <div className="w-36 border-t border-stone-400 mx-auto mb-1" />
              <div className="text-[8px] font-serif font-bold uppercase tracking-wider text-stone-800">{label}</div>
              <div className="text-[7px] text-stone-500 font-medium mt-0.5">
                {label.includes('CLIENTE') ? 'Acepto Conforme' : 'Autorizado'}
              </div>
            </div>
          ))}
        </div>
      </div>{/* end z-10 */}
    </div>
  );
}