import { useEffect, useState, useCallback } from 'react';
import { jsPDF } from 'jspdf';
import html2canvas from 'html2canvas';
import api from '../services/api';
import {
  ventaService,
  pagoService,
  Venta,
  VentaDetalle,
  Pago,
  METODOS_PAGO,
  type PagoCreate,
} from '../services/ventaService';

// ─── Tipos locales ────────────────────────────────────────────────────────────
interface Moneda {
  id: number;
  nombre: string;
  codigo: string;
  simbolo: string;
}

interface PedidoSinFactura {
  id: number;
  fecha: string;
  estado: string;
  cliente?: { nombre: string };
  cotizacion?: { total_estimado: number; moneda_id?: number };
}

// ─── Badges helpers ───────────────────────────────────────────────────────────
const ESTADO_VENTA_STYLE: Record<string, string> = {
  PENDIENTE: 'bg-amber-100 text-amber-800 border-amber-200',
  ABONADA: 'bg-blue-100 text-blue-800 border-blue-200',
  PAGADA: 'bg-green-100 text-green-800 border-green-200',
  CANCELADA: 'bg-red-100 text-red-800 border-red-200',
};

const ESTADO_PEDIDO_STYLE: Record<string, string> = {
  APROBADO: 'bg-blue-100 text-blue-800',
  PRODUCCION: 'bg-orange-100 text-orange-800',
  TERMINADO: 'bg-purple-100 text-purple-800',
  ENTREGADO: 'bg-gray-200 text-gray-800',
};

function Badge({ text, className }: { text: string; className: string }) {
  return (
    <span className={`px-2.5 py-0.5 rounded-full text-xs font-bold border ${className}`}>
      {text}
    </span>
  );
}

function Spinner() {
  return (
    <div className="flex flex-col items-center justify-center py-20 gap-3">
      <div className="w-10 h-10 border-4 border-yeikar-primary border-t-transparent rounded-full animate-spin" />
      <p className="text-xs font-mono text-yeikar-neutral/50">Cargando...</p>
    </div>
  );
}

// ─── Modal de detalle + cobro ─────────────────────────────────────────────────
function ModalDetalle({
  ventaId,
  onClose,
  onPagoRegistrado,
}: {
  ventaId: number;
  onClose: () => void;
  onPagoRegistrado: () => void;
}) {
  const [detalle, setDetalle] = useState<VentaDetalle | null>(null);
  const [loading, setLoading] = useState(true);
  const [isGeneratingPdf, setIsGeneratingPdf] = useState(false);

  // ── Formulario de nuevo pago ──────────────────────────────────────────────
  const [showForm, setShowForm] = useState(false);
  const [monedaPagoId, setMonedaPagoId] = useState<number | null>(null);
  const [monto, setMonto] = useState('');
  const [metodoPago, setMetodoPago] = useState('EFECTIVO_USD');
  const [trmInput, setTrmInput] = useState('');       // TRM ingresada manualmente
  const [referencia, setReferencia] = useState('');
  const [observaciones, setObservaciones] = useState('');
  const [submitting, setSubmitting] = useState(false);
  const [errorPago, setErrorPago] = useState('');
  const [monedas, setMonedas] = useState<{ id: number; codigo: string; nombre: string; simbolo: string }[]>([]);
  const [tasaBsInput, setTasaBsInput] = useState<string>('50');

  // ── Generación de PDF ───────────────────────────────────────────────────
  const handleGeneratePdf = async () => {
    if (!detalle) return;
    setIsGeneratingPdf(true);
    const element = document.getElementById(`pdf-factura-container-${detalle.id}`);
    if (!element) {
      setIsGeneratingPdf(false);
      return;
    }
    try {
      const canvas = await html2canvas(element, { scale: 2, useCORS: true });
      const pdf = new jsPDF({ orientation: 'portrait', unit: 'mm', format: 'letter' });
      const pdfW = pdf.internal.pageSize.getWidth();
      const pdfH = pdf.internal.pageSize.getHeight();
      const totalH = (canvas.height * pdfW) / canvas.width;

      if (totalH <= pdfH) {
        pdf.addImage(canvas.toDataURL('image/jpeg', 0.98), 'JPEG', 0, 0, pdfW, totalH);
      } else {
        const pxPerMm = canvas.width / pdfW;
        const pageHpx = Math.floor(pdfH * pxPerMm);
        const totalPages = Math.ceil(canvas.height / pageHpx);

        for (let pg = 0; pg < totalPages; pg++) {
          const sliceY = pg * pageHpx;
          const slicePx = Math.min(pageHpx, canvas.height - sliceY);
          const sc = document.createElement('canvas');
          sc.width = canvas.width;
          sc.height = slicePx;
          const ctx = sc.getContext('2d');
          if (ctx) {
            ctx.drawImage(canvas, 0, sliceY, canvas.width, slicePx, 0, 0, canvas.width, slicePx);
          }
          if (pg > 0) pdf.addPage('letter', 'portrait');
          pdf.addImage(sc.toDataURL('image/jpeg', 0.98), 'JPEG', 0, 0, pdfW, (slicePx / canvas.width) * pdfW);
        }
      }
      pdf.save(`Factura_Yeikar_${detalle.id}.pdf`);
    } catch (err) {
      console.error('Error al generar PDF:', err);
      alert('Hubo un error al generar el archivo PDF.');
    } finally {
      setIsGeneratingPdf(false);
    }
  };

  const cargar = useCallback(async () => {
    try {
      setLoading(true);
      const data = await ventaService.getById(ventaId);
      setDetalle(data);
    } finally {
      setLoading(false);
    }
  }, [ventaId]);

  const cargarMonedas = useCallback(async () => {
    try {
      const res = await api.get('/catalogos/moneda/');
      setMonedas(res.data);
    } catch {}
  }, []);

  useEffect(() => {
    cargar();
    cargarMonedas();
  }, [cargar, cargarMonedas]);

  // Cuando cambia el metodo de pago, auto-seleccionar la moneda correspondiente
  useEffect(() => {
    if (!monedas.length) return;
    const meta = METODOS_PAGO.find(m => m.value === metodoPago);
    if (!meta) return;
    const found = monedas.find(m => m.codigo === meta.moneda);
    if (found) setMonedaPagoId(found.id);
  }, [metodoPago, monedas]);

  // Si monedaPagoId coincide con la moneda de la venta, TRM no aplica
  const monedaVentaId = detalle?.moneda_id ?? null;
  const necesitaTRM = monedaPagoId !== null && monedaVentaId !== null && monedaPagoId !== monedaVentaId;
  const trm = parseFloat(trmInput) || 0;
  const montoNum = parseFloat(monto) || 0;
  const montoEquivalente = necesitaTRM && trm > 0 ? montoNum * trm : montoNum;
  const monedaPago = monedas.find(m => m.id === monedaPagoId);
  const monedaVenta = monedas.find(m => m.id === monedaVentaId);
  const saldoRestante = detalle ? Number(detalle.saldo_pendiente) : 0;

  // ── Cálculos Fiscales SENIAT Venezuela (en Bolívares Bs.) ──
  useEffect(() => {
    if (detalle?.moneda?.codigo === 'VES') {
      setTasaBsInput('1');
    } else if (detalle?.moneda?.codigo === 'USD') {
      setTasaBsInput('50');
    } else if (detalle?.moneda?.codigo === 'COP') {
      setTasaBsInput('0.0125');
    }
  }, [detalle]);

  const tasaBs = parseFloat(tasaBsInput) || 1;
  const baseImponibleBase = detalle ? Number(detalle.total) : 0;
  const baseImponibleBs = baseImponibleBase * tasaBs;
  const iva16Bs = baseImponibleBs * 0.16;
  const totalVentaBs = baseImponibleBs + iva16Bs;
  const igtf3Bs = totalVentaBs * 0.03;
  const totalAPagarBs = totalVentaBs + igtf3Bs;

  const handlePago = async () => {
    if (!detalle) return;
    setErrorPago('');
    if (!monto || isNaN(parseFloat(monto)) || parseFloat(monto) <= 0) {
      setErrorPago('Ingresa un monto válido mayor a 0.');
      return;
    }
    if (!monedaPagoId) {
      setErrorPago('Selecciona la moneda del pago.');
      return;
    }
    if (necesitaTRM && (!trmInput || trm <= 0)) {
      setErrorPago('La moneda del pago difiere de la de la factura. Ingresa la tasa de cambio (TRM).');
      return;
    }
    try {
      setSubmitting(true);
      const payload: PagoCreate = {
        venta_id: detalle.id,
        moneda_id: monedaPagoId,
        fecha: new Date().toISOString(),
        monto: parseFloat(monto),
        metodo_pago: metodoPago,
        referencia: referencia || undefined,
        observaciones: observaciones || undefined,
        ...(necesitaTRM ? { tasa_cambio: trm } : {}),
      };
      await pagoService.registrar(payload);
      setMonto('');
      setReferencia('');
      setObservaciones('');
      setTrmInput('');
      setShowForm(false);
      await cargar();
      onPagoRegistrado();
    } catch (err: any) {
      setErrorPago(err?.response?.data?.detail || 'Error al registrar el pago.');
    } finally {
      setSubmitting(false);
    }
  };

  const handleSetRestante = () => {
    if (!detalle) return;
    if (necesitaTRM) {
      if (trm <= 0) {
        setErrorPago('Ingresa primero la tasa de cambio (TRM) para calcular el monto restante.');
        return;
      }
      const montoCalc = saldoRestante / trm;
      // Usamos toFixed(4) para máxima precisión
      setMonto(montoCalc.toFixed(4));
    } else {
      setMonto(saldoRestante.toString());
    }
    setErrorPago('');
  };

  const porcentajePagado = detalle
    ? Math.min(100, (detalle.total_pagado / detalle.total) * 100)
    : 0;

  return (
    <div className="fixed inset-0 bg-black/50 backdrop-blur-sm flex items-center justify-center p-4 z-50">
      <div className="bg-white rounded-2xl border border-yeikar-secondary-light/10 shadow-2xl w-full max-w-2xl overflow-hidden flex flex-col max-h-[90vh]">
        {/* Header */}
        <div className="bg-yeikar-neutral p-5 text-yeikar-tertiary flex items-center justify-between">
          <div>
            <h3 className="font-headline font-bold text-lg text-yeikar-primary">
              Factura / Estado de Cuenta #{detalle?.id ?? '...'}
            </h3>
            {detalle && (
              <p className="text-xs text-yeikar-tertiary/60 font-mono mt-0.5">
                {detalle.cliente?.nombre} 
              </p>
            )}
          </div>
          <div className="flex items-center gap-3">
            {detalle && (
              <div className="flex items-center gap-2">
                <div className="flex items-center gap-1 bg-yeikar-tertiary/20 px-2.5 py-1 rounded-xl text-xs border border-yeikar-tertiary/30">
                  <span className="text-yeikar-tertiary/80 text-[10px] font-bold uppercase">Tasa Bs.:</span>
                  <input
                    type="number"
                    step="any"
                    value={tasaBsInput}
                    onChange={(e) => setTasaBsInput(e.target.value)}
                    className="w-16 bg-white text-yeikar-neutral text-xs font-mono font-bold px-1.5 py-0.5 rounded border border-yeikar-secondary-light/30 focus:outline-none focus:ring-1 focus:ring-yeikar-primary text-center"
                    placeholder="50"
                  />
                </div>
                <button
                  onClick={handleGeneratePdf}
                  disabled={isGeneratingPdf}
                  className="px-3 py-1.5 bg-yeikar-primary text-yeikar-neutral hover:bg-yeikar-primary/90 rounded-xl text-xs font-bold font-headline transition-all flex items-center gap-1.5 shadow-sm disabled:opacity-50"
                >
                  <svg className="w-4 h-4" fill="none" stroke="currentColor" viewBox="0 0 24 24">
                    <path strokeLinecap="round" strokeLinejoin="round" strokeWidth="2" d="M12 10v6m0 0l-3-3m3 3l3-3m2 8H7a2 2 0 01-2-2V5a2 2 0 012-2h5.586a1 1 0 01.707.293l5.414 5.414a1 1 0 01.293.707V19a2 2 0 01-2 2z" />
                  </svg>
                  {isGeneratingPdf ? 'Generando PDF…' : 'Descargar PDF'}
                </button>
              </div>
            )}
            <button
              onClick={onClose}
              className="text-yeikar-tertiary/50 hover:text-yeikar-tertiary transition-colors"
            >
              <svg className="w-6 h-6" fill="none" stroke="currentColor" viewBox="0 0 24 24">
                <path strokeLinecap="round" strokeLinejoin="round" strokeWidth="2" d="M6 18L18 6M6 6l12 12" />
              </svg>
            </button>
          </div>
        </div>

        {/* Body */}
        <div className="overflow-y-auto flex-1 p-5 space-y-5">
          {loading || !detalle ? (
            <Spinner />
          ) : (
            <>
              {/* Resumen financiero */}
              <div className="grid grid-cols-3 gap-3">
                <div className="bg-yeikar-tertiary/20 rounded-xl p-3 text-center">
                  <p className="text-xs text-yeikar-neutral/50 font-mono mb-1">Total Factura</p>
                  <p className="font-headline font-bold text-yeikar-secondary">
                    {detalle.moneda?.simbolo}{Number(detalle.total).toLocaleString('es-ES')}
                  </p>
                </div>
                <div className="bg-green-50 rounded-xl p-3 text-center border border-green-100">
                  <p className="text-xs text-green-600 font-mono mb-1">Pagado</p>
                  <p className="font-headline font-bold text-green-700">
                    {detalle.moneda?.simbolo}{Number(detalle.total_pagado).toLocaleString('es-ES')}
                  </p>
                </div>
                <div className="bg-amber-50 rounded-xl p-3 text-center border border-amber-100">
                  <p className="text-xs text-amber-600 font-mono mb-1">Saldo</p>
                  <p className="font-headline font-bold text-amber-700">
                    {detalle.moneda?.simbolo}{Number(detalle.saldo_pendiente).toLocaleString('es-ES')}
                  </p>
                </div>
              </div>

              {/* Barra de progreso */}
              <div>
                <div className="flex justify-between text-xs font-mono text-yeikar-neutral/50 mb-1">
                  <span>Progreso de cobro</span>
                  <span>{porcentajePagado.toFixed(1)}%</span>
                </div>
                <div className="h-2 bg-yeikar-tertiary/30 rounded-full overflow-hidden">
                  <div
                    className="h-full bg-green-500 rounded-full transition-all duration-500"
                    style={{ width: `${porcentajePagado}%` }}
                  />
                </div>
              </div>

              {/* Productos */}
              <div>
                <h4 className="font-headline font-bold text-sm text-yeikar-secondary mb-2 uppercase tracking-wider">
                  Productos facturados
                </h4>
                <div className="space-y-2">
                  {detalle.detalles.map((d) => (
                    <div
                      key={d.id}
                      className="flex justify-between items-center text-sm bg-yeikar-tertiary/10 rounded-lg px-3 py-2"
                    >
                      <span className="font-medium text-yeikar-secondary">
                        {d.producto?.nombre ?? `Producto #${d.producto_id}`}
                      </span>
                      <span className="font-mono text-yeikar-neutral/70">
                        {d.cantidad} × {detalle.moneda?.simbolo}{Number(d.precio).toLocaleString('es-ES')}
                      </span>
                    </div>
                  ))}
                </div>
              </div>

              {/* Historial de pagos */}
              <div>
                <h4 className="font-headline font-bold text-sm text-yeikar-secondary mb-2 uppercase tracking-wider">
                  Historial de cobros ({detalle.pagos.length})
                </h4>
                {detalle.pagos.length === 0 ? (
                  <p className="text-xs text-yeikar-neutral/40 italic text-center py-4">
                    Sin cobros registrados aún.
                  </p>
                ) : (
                  <div className="space-y-2">
                    {detalle.pagos.map((p: Pago) => {
                      const metodoLabel = METODOS_PAGO.find((m) => m.value === p.metodo_pago)?.label ?? p.metodo_pago;
                      const esMultimoneda = p.tasa_cambio && p.tasa_cambio !== 1;
                      return (
                        <div
                          key={p.id}
                          className="text-xs bg-green-50 border border-green-100 rounded-lg px-3 py-2"
                        >
                          <div className="flex justify-between items-start">
                            <div>
                              <span className="font-bold text-green-700">{metodoLabel}</span>
                              {p.referencia && (
                                <span className="ml-2 text-green-600/70 font-mono">#{p.referencia}</span>
                              )}
                              <p className="text-green-600/60 font-mono mt-0.5">
                                {new Date(p.fecha).toLocaleDateString('es-ES')}
                              </p>
                            </div>
                            <div className="text-right">
                              <span className="font-mono font-bold text-green-700">
                                {p.moneda?.simbolo ?? ''}{Number(p.monto).toLocaleString('es-ES')}
                              </span>
                              {esMultimoneda && (
                                <p className="text-green-600/60 font-mono mt-0.5">
                                  ≈ {detalle.moneda?.simbolo}{Number(p.monto_en_moneda_base).toLocaleString('es-ES')}
                                  <span className="ml-1 opacity-60">(TRM: {Number(p.tasa_cambio).toLocaleString('es-ES')})</span>
                                </p>
                              )}
                            </div>
                          </div>
                        </div>
                      );
                    })}
                  </div>
                )}
              </div>

              {/* Formulario de nuevo cobro */}
              {detalle.estado !== 'PAGADA' && detalle.estado !== 'CANCELADA' && (
                <div>
                  {!showForm ? (
                    <button
                      onClick={() => setShowForm(true)}
                      className="w-full py-2.5 bg-yeikar-primary text-yeikar-neutral font-bold font-headline rounded-xl hover:bg-yeikar-primary/90 transition-all text-sm"
                    >
                      + Registrar Cobro
                    </button>
                  ) : (
                    <div className="border border-yeikar-primary/20 rounded-xl p-4 bg-yeikar-primary/5 space-y-3">
                      <h5 className="font-headline font-bold text-sm text-yeikar-secondary">
                        Nuevo Cobro
                      </h5>

                      {/* Fila 1: Método de pago + Moneda del pago */}
                      <div className="grid grid-cols-2 gap-3">
                        <div>
                          <label className="text-xs font-bold text-yeikar-neutral/60 block mb-1">
                            Método de pago
                          </label>
                          <select
                            value={metodoPago}
                            onChange={(e) => setMetodoPago(e.target.value)}
                            className="w-full px-3 py-2 text-sm border border-yeikar-secondary-light/20 rounded-lg focus:outline-none focus:ring-2 focus:ring-yeikar-primary bg-white"
                          >
                            {METODOS_PAGO.map((m) => (
                              <option key={m.value} value={m.value}>
                                {m.label}
                              </option>
                            ))}
                          </select>
                        </div>
                        <div>
                          <label className="text-xs font-bold text-yeikar-neutral/60 block mb-1">
                            Moneda del pago
                          </label>
                          <select
                            value={monedaPagoId ?? ''}
                            onChange={(e) => setMonedaPagoId(Number(e.target.value))}
                            className="w-full px-3 py-2 text-sm border border-yeikar-secondary-light/20 rounded-lg focus:outline-none focus:ring-2 focus:ring-yeikar-primary bg-white"
                          >
                            {monedas.map((m) => (
                              <option key={m.id} value={m.id}>
                                {m.codigo} — {m.nombre}
                              </option>
                            ))}
                          </select>
                        </div>
                      </div>

                      {/* Fila 2: Monto + TRM (condicional) */}
                      <div className="grid grid-cols-2 gap-3">
                        <div>
                          <div className="flex justify-between items-center mb-1">
                            <label className="text-xs font-bold text-yeikar-neutral/60 block">
                              Monto ({monedaPago?.codigo ?? '...'})
                            </label>
                            <button
                              type="button"
                              onClick={handleSetRestante}
                              className="text-[10px] font-bold text-yeikar-primary hover:underline hover:text-yeikar-primary-light flex items-center gap-0.5"
                            >
                              ⚡ Pagar Restante
                            </button>
                          </div>
                          <input
                            type="number"
                            min="0"
                            step="0.0001"
                            value={monto}
                            onChange={(e) => setMonto(e.target.value)}
                            placeholder="0.00"
                            className="w-full px-3 py-2 text-sm border border-yeikar-secondary-light/20 rounded-lg focus:outline-none focus:ring-2 focus:ring-yeikar-primary bg-white"
                          />
                        </div>
                        {necesitaTRM && (
                          <div>
                            <label className="text-xs font-bold text-amber-600 block mb-1">
                              Tasa de cambio (TRM) ⚠️
                            </label>
                            <input
                              type="number"
                              min="0"
                              step="0.01"
                              value={trmInput}
                              onChange={(e) => setTrmInput(e.target.value)}
                              placeholder={`1 ${monedaPago?.codigo} = ? ${monedaVenta?.codigo}`}
                              className="w-full px-3 py-2 text-sm border border-amber-300 rounded-lg focus:outline-none focus:ring-2 focus:ring-amber-400 bg-amber-50"
                            />
                          </div>
                        )}
                      </div>

                      {/* Preview de conversión */}
                      {necesitaTRM && montoNum > 0 && trm > 0 && (
                        <div className="bg-amber-50 border border-amber-200 rounded-lg px-3 py-2">
                          <p className="text-xs text-amber-700 font-mono">
                            <span className="font-bold">{monedaPago?.simbolo}{montoNum.toLocaleString('es-ES')}</span>
                            <span className="mx-2 opacity-60">×</span>
                            <span className="font-bold">{trm.toLocaleString('es-ES')}</span>
                            <span className="mx-2 opacity-60">=</span>
                            <span className="font-bold text-amber-800">
                              {monedaVenta?.simbolo}{montoEquivalente.toLocaleString('es-ES', { minimumFractionDigits: 2 })}
                            </span>
                            <span className="ml-2 opacity-60">en {monedaVenta?.codigo}</span>
                          </p>
                          {montoEquivalente > saldoRestante + 0.01 && (
                            <p className="text-xs text-red-600 font-bold mt-1">
                              El equivalente excede el saldo pendiente ({monedaVenta?.simbolo}{saldoRestante.toLocaleString('es-ES')})
                            </p>
                          )}
                        </div>
                      )}

                      <div>
                        <label className="text-xs font-bold text-yeikar-neutral/60 block mb-1">
                          Referencia / Comprobante (opcional)
                        </label>
                        <input
                          type="text"
                          value={referencia}
                          onChange={(e) => setReferencia(e.target.value)}
                          placeholder="N° de transacción, comprobante..."
                          className="w-full px-3 py-2 text-sm border border-yeikar-secondary-light/20 rounded-lg focus:outline-none focus:ring-2 focus:ring-yeikar-primary bg-white"
                        />
                      </div>

                      <div>
                        <label className="text-xs font-bold text-yeikar-neutral/60 block mb-1">
                          Observaciones (opcional)
                        </label>
                        <textarea
                          value={observaciones}
                          onChange={(e) => setObservaciones(e.target.value)}
                          rows={2}
                          className="w-full px-3 py-2 text-sm border border-yeikar-secondary-light/20 rounded-lg focus:outline-none focus:ring-2 focus:ring-yeikar-primary bg-white resize-none"
                        />
                      </div>

                      {errorPago && (
                        <p className="text-xs text-red-600 bg-red-50 border border-red-200 rounded-lg px-3 py-2">
                          {errorPago}
                        </p>
                      )}

                      <div className="flex gap-2">
                        <button
                          onClick={() => { setShowForm(false); setErrorPago(''); setTrmInput(''); }}
                          className="flex-1 py-2 text-sm font-bold text-yeikar-neutral/60 border border-yeikar-secondary-light/20 rounded-xl hover:bg-yeikar-tertiary/20 transition-all"
                        >
                          Cancelar
                        </button>
                        <button
                          onClick={handlePago}
                          disabled={submitting}
                          className="flex-1 py-2 text-sm font-bold bg-yeikar-primary text-yeikar-neutral rounded-xl hover:bg-yeikar-primary/90 transition-all disabled:opacity-50"
                        >
                          {submitting ? 'Guardando...' : 'Confirmar Cobro'}
                        </button>
                      </div>
                    </div>
                  )}
                </div>
              )}

              {/* ── Plantilla para la generación del PDF con jsPDF (Factura Fiscal Oficial Yeikar) ── */}
              <div className="fixed -left-[9999px] top-0 pointer-events-none z-[-100]">
                <div
                  id={`pdf-factura-container-${detalle.id}`}
                  className="bg-white text-stone-900 font-sans p-8 relative"
                  style={{ width: '215.9mm', minHeight: '279.4mm', boxSizing: 'border-box' }}
                >
                  {/* Filigrana / Logo Marca de Agua */}
                  <div className="absolute inset-0 flex items-center justify-center pointer-events-none opacity-[0.03] select-none z-0">
                    <img src="/logo-marca-de-agua.PNG" alt="" className="w-[400px] h-auto" />
                  </div>

                  <div className="relative z-10 flex flex-col justify-between min-h-[255mm]">
                    <div>
                      {/* Encabezado Oficial */}
                      <div className="flex justify-between items-start pb-3 border-b-2 border-stone-800">
                        <div className="space-y-1 max-w-[62%]">
                          <img src="/Logo-yeikar.png" alt="Yeikar" className="h-10 object-contain mb-1" />
                          <h1 className="font-serif font-black text-stone-900 text-sm tracking-widest uppercase">
                            Comercializadora Yeikar
                          </h1>
                          <p className="text-[9px] font-bold text-stone-700">RIF. V-18969838-7 · Lilia Carolina Bautista (Propietaria)</p>
                          <p className="text-[8px] text-stone-600 leading-tight">
                            Fabricación, Compra, Venta, Importación, Comercialización al Mayor y Detal de todo tipo de Muebles.
                          </p>
                          <p className="text-[8px] text-stone-600">
                            <strong>Dirección:</strong> Av. Intercomunal con Calle 16 Local N° 15-205 B. Simón Bolívar, Ureña, Edo. Táchira
                          </p>
                          <p className="text-[8px] text-stone-600 font-mono">
                            <strong>Tel:</strong> (0276) 7874095 · Cel: 0414-7393699 / 0414-7398817
                          </p>
                          <p className="text-[8px] text-stone-600 font-mono">
                            <strong>Instagram:</strong> @mueblesyeikar.fabricantes &nbsp;·&nbsp; <strong>Facebook:</strong> Muebles Yeikar
                          </p>
                        </div>

                        {/* Recuadro de Control / Número */}
                        <div className="text-right border-2 border-stone-800 rounded-lg p-3 bg-stone-50/80 min-w-[170px] shadow-sm">
                          <div className="text-[9px] font-black text-stone-800 uppercase tracking-widest">FACTURA DE VENTA</div>
                          <div className="text-sm font-black text-amber-800 font-mono tracking-widest mt-1">
                            N°: 00 – {detalle.id.toString().padStart(5, '0')}
                          </div>
                          <div className="text-[8px] font-mono text-stone-700 font-bold mt-1">
                            N° DE CONTROL: 00 – {detalle.id.toString().padStart(6, '0')}
                          </div>
                          <div className="text-[8px] font-mono text-stone-700 font-bold mt-0.5">
                            FECHA DE EMISIÓN: {new Date(detalle.fecha).toLocaleDateString('es-ES')}
                          </div>
                        </div>
                      </div>

                      {/* Datos del Cliente — Conforme SENIAT */}
                      <div className="grid grid-cols-4 gap-x-3 gap-y-2 bg-stone-50/80 border border-stone-300 rounded-xl p-3 my-3 text-[9px] shadow-sm">
                        <div className="col-span-4">
                          <span className="font-bold text-stone-500 uppercase text-[7.5px] block">Nombre y Apellido o Razón Social</span>
                          <span className="font-extrabold text-stone-950 text-xs">{detalle.cliente?.nombre ?? '—'}</span>
                        </div>
                        <div className="col-span-2 border-t border-stone-200 pt-1.5">
                          <span className="font-bold text-stone-500 uppercase text-[7.5px] block">Identificación</span>
                          <span className="font-bold text-stone-900 font-mono text-[8.5px]">RIF&#160;(&#160;&#160;)&#160;&#160;&#160;C.I.&#160;(&#160;&#160;)</span>
                        </div>
                        <div className="col-span-2 border-t border-stone-200 pt-1.5">
                          <span className="font-bold text-stone-500 uppercase text-[7.5px] block">Teléfono</span>
                          <span className="font-extrabold text-stone-900 font-mono">{detalle.cliente?.telefono || '—'}</span>
                        </div>
                        <div className="col-span-4 border-t border-stone-200 pt-1.5">
                          <span className="font-bold text-stone-500 uppercase text-[7.5px] block">Domicilio Fiscal</span>
                          <span className="font-semibold text-stone-900 italic">{detalle.cliente?.direccion || '—'}</span>
                        </div>
                        <div className="col-span-4 border-t border-stone-200 pt-1.5">
                          <span className="font-bold text-stone-500 uppercase text-[7.5px] block">Forma de Pago</span>
                          <span className="font-bold text-stone-900 font-mono text-[8px]">
                            Efectivo&#160;(&#160;&#160;)&#160;&#160;Tarjeta de Débito&#160;(&#160;&#160;)&#160;&#160;Tarjeta de Crédito&#160;(&#160;&#160;)&#160;&#160;Otros&#160;(&#160;&#160;)
                          </span>
                        </div>
                      </div>

                      {/* Tabla de Productos / Concepto o Descripción con montos en Bolívares */}
                      <div className="mb-4 border border-stone-300 rounded-lg overflow-hidden shadow-sm">
                        <table className="w-full border-collapse text-[9.5px]">
                          <thead>
                            <tr className="bg-stone-900 text-stone-100 uppercase font-serif text-[8px] tracking-wider">
                              <th className="p-2 text-center w-[8%]">Cant.</th>
                              <th className="p-2 text-left">Concepto o Descripción</th>
                              <th className="p-2 text-right w-[20%]">P. Unitario (Bs.)</th>
                              <th className="p-2 text-right w-[22%]">Monto Total (Bs.)</th>
                            </tr>
                          </thead>
                          <tbody className="divide-y divide-stone-200">
                            {detalle.detalles.map((d, i) => {
                              const precioBs = Number(d.precio) * tasaBs;
                              const rowTotalBs = d.cantidad * precioBs;
                              return (
                                <tr key={d.id} className={i % 2 === 0 ? 'bg-white' : 'bg-stone-50/60'}>
                                  <td className="p-2 text-center font-mono font-bold text-stone-900">{d.cantidad}</td>
                                  <td className="p-2 font-serif font-bold text-stone-950">
                                    {d.producto?.nombre ?? `Producto #${d.producto_id}`}
                                  </td>
                                  <td className="p-2 text-right font-mono text-stone-800">
                                    Bs. {precioBs.toLocaleString('es-VE', { minimumFractionDigits: 2, maximumFractionDigits: 2 })}
                                  </td>
                                  <td className="p-2 text-right font-mono font-black text-stone-950">
                                    Bs. {rowTotalBs.toLocaleString('es-VE', { minimumFractionDigits: 2, maximumFractionDigits: 2 })}
                                  </td>
                                </tr>
                              );
                            })}
                          </tbody>
                        </table>
                      </div>
                    </div>

                    {/* Sección Inferior: Desglose Fiscal SENIAT Venezuela y Firmas */}
                    <div>
                      <div className="grid grid-cols-2 gap-4 items-end mb-4">
                        {/* Nota Legal izquierda */}
                        <div className="text-[8px] text-stone-600 space-y-1.5">
                          <p className="font-bold text-stone-800 uppercase tracking-wider">Esta factura va sin enmienda ni tachadura.</p>
                          <p className="italic">ORIGINAL · Comprobante fiscal de venta Comercializadora Yeikar (Ureña, Edo. Táchira).</p>
                          <p className="text-[7.5px] text-stone-500 font-mono">
                            Tasa de Cambio Oficial: 1 {detalle.moneda?.codigo} = {tasaBs.toLocaleString('es-VE')} Bs.
                          </p>
                        </div>

                        {/* Tarjeta de Resumen Fiscal SENIAT Oficial (Sin fondo negro, alta legibilidad) */}
                        <div className="border border-stone-400 rounded-xl overflow-hidden shadow-sm font-mono text-[8.5px]">
                          <div className="bg-stone-900 text-stone-100 px-3 py-1 font-serif font-bold uppercase tracking-wider text-[7.5px] flex justify-between items-center">
                            <span>Resumen Fiscal</span>                           
                          </div>
                          <div className="p-2.5 space-y-1 bg-stone-50/90">
                            <div className="flex justify-between items-center text-stone-700 border-t border-stone-200 pt-1">
                              <span>Monto Total de la Base Imponible al Valor Agregado Bs:</span>
                              <span className="font-bold text-stone-900">{baseImponibleBs.toLocaleString('es-VE', { minimumFractionDigits: 2, maximumFractionDigits: 2 })}</span>
                            </div>
                            <div className="flex justify-between items-center text-stone-700">
                              <span>Monto Total del Impuesto al Valor Agregado — Alícuota 16% Bs:</span>
                              <span className="font-bold text-stone-900">{iva16Bs.toLocaleString('es-VE', { minimumFractionDigits: 2, maximumFractionDigits: 2 })}</span>
                            </div>
                            <div className="flex justify-between items-center text-stone-800 font-bold border-t border-stone-300 pt-1">
                              <span>Monto Total de la Venta de los Bienes o la Prestación del Servicio Bs:</span>
                              <span>{totalVentaBs.toLocaleString('es-VE', { minimumFractionDigits: 2, maximumFractionDigits: 2 })}</span>
                            </div>
                            <div className="flex justify-between items-center text-stone-700">
                              <span>Monto Total de la Base Imponible del IGTF (3%) Bs:</span>
                              <span className="font-bold text-stone-900">{igtf3Bs.toLocaleString('es-VE', { minimumFractionDigits: 2, maximumFractionDigits: 2 })}</span>
                            </div>
                          </div>

                          {/* Destacado de TOTAL A PAGAR Bs. */}
                          <div className="bg-amber-100/90 border-t-2 border-stone-800 p-2.5 flex justify-between items-center">
                            <div>
                              <span className="font-serif font-black text-stone-950 uppercase text-[9px] tracking-wider block">TOTAL A PAGAR</span>                              
                            </div>
                            <div className="text-right">
                              <span className="text-sm font-black text-amber-950 font-mono tracking-tight block">
                                Bs. {totalAPagarBs.toLocaleString('es-VE', { minimumFractionDigits: 2, maximumFractionDigits: 2 })}
                              </span>
                            </div>
                          </div>
                        </div>
                      </div>

                      {/* el men es el men */}
                      
                    </div>
                  </div>
                </div>
              </div>
            </>
          )}
        </div>
      </div>
    </div>
  );
}

// ─── Modal para crear factura ────────────────────────────────────────────────
function ModalCrearFactura({
  pedido,
  monedas,
  onClose,
  onCreado,
}: {
  pedido: PedidoSinFactura;
  monedas: Moneda[];
  onClose: () => void;
  onCreado: () => void;
}) {
  const [monedaId, setMonedaId] = useState<number>(
    pedido.cotizacion?.moneda_id ?? monedas[0]?.id ?? 0
  );
  const [submitting, setSubmitting] = useState(false);
  const [error, setError] = useState('');

  const handleCrear = async () => {
    setError('');
    if (!monedaId) { setError('Selecciona una moneda.'); return; }
    try {
      setSubmitting(true);
      await ventaService.create({ pedido_id: pedido.id, moneda_id: monedaId });
      onCreado();
      onClose();
    } catch (err: any) {
      setError(err?.response?.data?.detail || 'Error al crear la factura.');
    } finally {
      setSubmitting(false);
    }
  };

  return (
    <div className="fixed inset-0 bg-black/50 backdrop-blur-sm flex items-center justify-center p-4 z-50">
      <div className="bg-white rounded-2xl shadow-2xl w-full max-w-md p-6 space-y-4">
        <h3 className="font-headline font-bold text-lg text-yeikar-secondary">
          Crear Factura — Pedido #{pedido.id}
        </h3>
        <p className="text-sm text-yeikar-neutral/70">
          Cliente: <strong>{pedido.cliente?.nombre ?? '—'}</strong>
        </p>
        <div>
          <label className="text-xs font-bold text-yeikar-neutral/60 block mb-1">
            Moneda de facturación
          </label>
          {pedido.cotizacion?.moneda_id && (
            <p className="text-xs text-yeikar-neutral/50 mb-2">
              Moneda sugerida de la cotización (puedes cambiarla).
            </p>
          )}
          <select
            value={monedaId}
            onChange={(e) => setMonedaId(Number(e.target.value))}
            className="w-full px-3 py-2 text-sm border border-yeikar-secondary-light/20 rounded-lg focus:outline-none focus:ring-2 focus:ring-yeikar-primary bg-white"
          >
            {monedas.map((m) => (
              <option key={m.id} value={m.id}>
                {m.nombre} ({m.codigo} {m.simbolo})
              </option>
            ))}
          </select>
        </div>
        {error && (
          <p className="text-xs text-red-600 bg-red-50 border border-red-200 rounded-lg px-3 py-2">
            {error}
          </p>
        )}
        <div className="flex gap-2 pt-1">
          <button
            onClick={onClose}
            className="flex-1 py-2.5 text-sm font-bold text-yeikar-neutral/60 border border-yeikar-secondary-light/20 rounded-xl hover:bg-yeikar-tertiary/20 transition-all"
          >
            Cancelar
          </button>
          <button
            onClick={handleCrear}
            disabled={submitting}
            className="flex-1 py-2.5 text-sm font-bold bg-yeikar-primary text-yeikar-neutral rounded-xl hover:bg-yeikar-primary/90 transition-all disabled:opacity-50"
          >
            {submitting ? 'Creando...' : 'Crear Factura'}
          </button>
        </div>
      </div>
    </div>
  );
}

// ─── Página principal ─────────────────────────────────────────────────────────
export default function Ventas() {
  const [activeTab, setActiveTab] = useState<'facturas' | 'pendientes'>('facturas');

  const [ventas, setVentas] = useState<Venta[]>([]);
  const [ventasLoading, setVentasLoading] = useState(false);

  const [pedidosSinFactura, setPedidosSinFactura] = useState<PedidoSinFactura[]>([]);
  const [pedidosLoading, setPedidosLoading] = useState(false);

  const [monedas, setMonedas] = useState<Moneda[]>([]);

  // Modales
  const [detalleVentaId, setDetalleVentaId] = useState<number | null>(null);
  const [pedidoParaFactura, setPedidoParaFactura] = useState<PedidoSinFactura | null>(null);

  // Filtro de estado
  const [filtroEstado, setFiltroEstado] = useState<string>('');

  const cargarVentas = useCallback(async () => {
    try {
      setVentasLoading(true);
      const data = await ventaService.getAll();
      setVentas(data);
    } finally {
      setVentasLoading(false);
    }
  }, []);

  const cargarPedidosSinFactura = useCallback(async () => {
    try {
      setPedidosLoading(true);
      // Pedidos en estados facturables
      const res = await api.get<PedidoSinFactura[]>('/pedido/');
      const facturables = ['APROBADO', 'PRODUCCION', 'TERMINADO', 'ENTREGADO'];
      const todos = res.data.filter((p) => facturables.includes(p.estado));
      // Excluir los que ya tienen factura (cruzando con ventas cargadas)
      // Cargamos ventas actuales para evitar llamada extra
      const ventasRes = await ventaService.getAll();
      const pedidosConFactura = new Set(ventasRes.map((v) => v.pedido_id));
      setPedidosSinFactura(todos.filter((p) => !pedidosConFactura.has(p.id)));
    } finally {
      setPedidosLoading(false);
    }
  }, []);

  const cargarMonedas = useCallback(async () => {
    try {
      const res = await api.get<Moneda[]>('/catalogos/moneda/');
      setMonedas(res.data);
    } catch {
      setMonedas([]);
    }
  }, []);

  useEffect(() => {
    cargarMonedas();
    if (activeTab === 'facturas') {
      cargarVentas();
    } else {
      cargarPedidosSinFactura();
    }
  }, [activeTab, cargarVentas, cargarPedidosSinFactura, cargarMonedas]);

  const ventasFiltradas = filtroEstado
    ? ventas.filter((v) => v.estado === filtroEstado)
    : ventas;

  const totalPendiente = ventas
    .filter((v) => v.estado !== 'PAGADA' && v.estado !== 'CANCELADA')
    .length;

  return (
    <div className="space-y-6">
      {/* Header */}
      <div className="flex flex-col sm:flex-row items-start sm:items-center justify-between gap-4">
        <div>
          <h1 className="text-3xl font-black font-headline text-yeikar-neutral tracking-tight">
            Ventas y Cobros
          </h1>
          <p className="text-yeikar-neutral/60 mt-1 text-sm">
            Gestiona facturas, registra pagos y controla cuentas por cobrar.
          </p>
        </div>
        {totalPendiente > 0 && (
          <div className="flex items-center gap-2 bg-amber-50 border border-amber-200 text-amber-700 px-4 py-2 rounded-xl text-sm font-bold">
            <svg className="w-4 h-4" fill="none" stroke="currentColor" viewBox="0 0 24 24">
              <path strokeLinecap="round" strokeLinejoin="round" strokeWidth="2" d="M12 8v4m0 4h.01M21 12a9 9 0 11-18 0 9 9 0 0118 0z" />
            </svg>
            {totalPendiente} factura{totalPendiente !== 1 ? 's' : ''} por cobrar
          </div>
        )}
      </div>

      {/* Tabs */}
      <div className="flex border-b border-yeikar-secondary-light/10">
        <button
          id="tab-facturas"
          onClick={() => setActiveTab('facturas')}
          className={`px-5 py-3 font-headline font-bold text-sm tracking-tight border-b-2 transition-all ${
            activeTab === 'facturas'
              ? 'border-yeikar-primary text-yeikar-primary'
              : 'border-transparent text-yeikar-neutral/60 hover:text-yeikar-secondary'
          }`}
        >
          Facturas Emitidas
        </button>
        <button
          id="tab-pendientes"
          onClick={() => setActiveTab('pendientes')}
          className={`px-5 py-3 font-headline font-bold text-sm tracking-tight border-b-2 transition-all flex items-center gap-2 ${
            activeTab === 'pendientes'
              ? 'border-yeikar-primary text-yeikar-primary'
              : 'border-transparent text-yeikar-neutral/60 hover:text-yeikar-secondary'
          }`}
        >
          Pedidos sin Factura
          {pedidosSinFactura.length > 0 && (
            <span className="bg-yeikar-primary text-yeikar-neutral text-xs font-bold rounded-full w-5 h-5 flex items-center justify-center">
              {pedidosSinFactura.length}
            </span>
          )}
        </button>
      </div>

      {/* ── TAB: Facturas emitidas ── */}
      {activeTab === 'facturas' && (
        <div className="space-y-4">
          {/* Filtro de estado */}
          <div className="flex items-center gap-3">
            <span className="text-xs font-bold text-yeikar-neutral/50 font-mono">FILTRAR:</span>
            {['', 'PENDIENTE', 'ABONADA', 'PAGADA', 'CANCELADA'].map((est) => (
              <button
                key={est}
                onClick={() => setFiltroEstado(est)}
                className={`px-3 py-1 rounded-full text-xs font-bold border transition-all ${
                  filtroEstado === est
                    ? 'bg-yeikar-primary text-yeikar-neutral border-yeikar-primary'
                    : 'bg-white text-yeikar-neutral/60 border-yeikar-secondary-light/20 hover:border-yeikar-primary/40'
                }`}
              >
                {est === '' ? 'Todas' : est}
              </button>
            ))}
          </div>

          <div className="bg-white rounded-2xl border border-yeikar-secondary-light/10 shadow-sm overflow-hidden">
            {ventasLoading ? (
              <Spinner />
            ) : ventasFiltradas.length === 0 ? (
              <div className="p-10 text-center text-yeikar-neutral/40 italic text-sm">
                No hay facturas para mostrar.
              </div>
            ) : (
              <div className="overflow-x-auto">
                <table className="w-full text-left border-collapse text-sm">
                  <thead>
                    <tr className="bg-yeikar-neutral text-yeikar-tertiary font-headline uppercase text-xs tracking-wider">
                      <th className="px-5 py-4 border-b border-yeikar-secondary/20"># Factura</th>
                      <th className="px-5 py-4 border-b border-yeikar-secondary/20">Cliente</th>
                      <th className="px-5 py-4 border-b border-yeikar-secondary/20">Pedido</th>
                      <th className="px-5 py-4 border-b border-yeikar-secondary/20">Fecha</th>
                      <th className="px-5 py-4 border-b border-yeikar-secondary/20">Total</th>
                      <th className="px-5 py-4 border-b border-yeikar-secondary/20">Moneda</th>
                      <th className="px-5 py-4 border-b border-yeikar-secondary/20">Estado</th>
                      <th className="px-5 py-4 border-b border-yeikar-secondary/20 text-right">Acción</th>
                    </tr>
                  </thead>
                  <tbody className="divide-y divide-yeikar-secondary-light/10">
                    {ventasFiltradas.map((v) => (
                      <tr key={v.id} className="hover:bg-yeikar-tertiary/10 transition-colors">
                        <td className="px-5 py-4 font-mono font-bold text-yeikar-secondary">
                          #{v.id}
                        </td>
                        <td className="px-5 py-4 font-semibold text-yeikar-secondary">
                          {v.cliente?.nombre ?? `Cliente #${v.cliente_id}`}
                        </td>
                        <td className="px-5 py-4 font-mono text-yeikar-neutral/60">
                          Pedido #{v.pedido_id}
                        </td>
                        <td className="px-5 py-4 font-mono text-yeikar-neutral/70">
                          {new Date(v.fecha).toLocaleDateString('es-ES')}
                        </td>
                        <td className="px-5 py-4 font-mono font-bold text-yeikar-secondary">
                          {Number(v.total).toLocaleString('es-ES')}
                        </td>
                        <td className="px-5 py-4">
                          <span className="font-mono text-xs font-bold bg-yeikar-tertiary/30 px-2 py-0.5 rounded-md">
                            {v.moneda?.codigo ?? '—'}
                          </span>
                        </td>
                        <td className="px-5 py-4">
                          <Badge
                            text={v.estado}
                            className={ESTADO_VENTA_STYLE[v.estado] ?? ''}
                          />
                        </td>
                        <td className="px-5 py-4 text-right">
                          <button
                            id={`btn-ver-factura-${v.id}`}
                            onClick={() => setDetalleVentaId(v.id)}
                            className="px-3 py-1.5 bg-yeikar-secondary text-yeikar-tertiary hover:bg-yeikar-secondary-light rounded-lg text-xs font-bold font-headline transition-colors"
                          >
                            {v.estado !== 'PAGADA' && v.estado !== 'CANCELADA' ? 'Ver / Cobrar' : 'Ver Detalle'}
                          </button>
                        </td>
                      </tr>
                    ))}
                  </tbody>
                </table>
              </div>
            )}
          </div>
        </div>
      )}

      {/* ── TAB: Pedidos sin factura ── */}
      {activeTab === 'pendientes' && (
        <div className="bg-white rounded-2xl border border-yeikar-secondary-light/10 shadow-sm overflow-hidden">
          {pedidosLoading ? (
            <Spinner />
          ) : pedidosSinFactura.length === 0 ? (
            <div className="p-10 text-center text-green-600 font-semibold italic text-sm">
              ✓ Todos los pedidos activos ya tienen factura emitida.
            </div>
          ) : (
            <div className="overflow-x-auto">
              <table className="w-full text-left border-collapse text-sm">
                <thead>
                  <tr className="bg-yeikar-neutral text-yeikar-tertiary font-headline uppercase text-xs tracking-wider">
                    <th className="px-5 py-4 border-b border-yeikar-secondary/20"># Pedido</th>
                    <th className="px-5 py-4 border-b border-yeikar-secondary/20">Cliente</th>
                    <th className="px-5 py-4 border-b border-yeikar-secondary/20">Fecha</th>
                    <th className="px-5 py-4 border-b border-yeikar-secondary/20">Estado</th>
                    <th className="px-5 py-4 border-b border-yeikar-secondary/20 text-right">Acción</th>
                  </tr>
                </thead>
                <tbody className="divide-y divide-yeikar-secondary-light/10">
                  {pedidosSinFactura.map((p) => (
                    <tr key={p.id} className="hover:bg-yeikar-tertiary/10 transition-colors">
                      <td className="px-5 py-4 font-mono font-bold text-yeikar-secondary">#{p.id}</td>
                      <td className="px-5 py-4 font-semibold text-yeikar-secondary">
                        {p.cliente?.nombre ?? '—'}
                      </td>
                      <td className="px-5 py-4 font-mono text-yeikar-neutral/70">{p.fecha}</td>
                      <td className="px-5 py-4">
                        <Badge
                          text={p.estado}
                          className={`${ESTADO_PEDIDO_STYLE[p.estado] ?? ''} border border-transparent`}
                        />
                      </td>
                      <td className="px-5 py-4 text-right">
                        <button
                          id={`btn-crear-factura-${p.id}`}
                          onClick={() => setPedidoParaFactura(p)}
                          className="px-3 py-1.5 bg-yeikar-primary text-yeikar-neutral hover:bg-yeikar-primary/90 rounded-lg text-xs font-bold font-headline transition-colors"
                        >
                          Crear Factura
                        </button>
                      </td>
                    </tr>
                  ))}
                </tbody>
              </table>
            </div>
          )}
        </div>
      )}

      {/* Modales */}
      {detalleVentaId !== null && (
        <ModalDetalle
          ventaId={detalleVentaId}
          onClose={() => setDetalleVentaId(null)}
          onPagoRegistrado={cargarVentas}
        />
      )}

      {pedidoParaFactura && (
        <ModalCrearFactura
          pedido={pedidoParaFactura}
          monedas={monedas}
          onClose={() => setPedidoParaFactura(null)}
          onCreado={() => {
            cargarVentas();
            cargarPedidosSinFactura();
          }}
        />
      )}
    </div>
  );
}
