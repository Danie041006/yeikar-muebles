import { useEffect, useState, useCallback } from 'react';
import { Search, Loader2, Plus } from 'lucide-react';
import { useDebouncedValue } from '../hooks/useDebouncedValue';
import { jsPDF } from 'jspdf';
import html2canvas from 'html2canvas';
import FacturaFiscalPDF from '../components/FacturaFiscalPDF';
import ConfirmDialog from '../components/ui/ConfirmDialog';
import { esperarImagenesCargadas } from '../utils/pdfImagenes';
import { useAuth } from '../context/AuthContext';
import { useToast } from '../context/ToastContext';
import {
  facturacionService,
  Factura,
  FacturaDetalle,
  PedidoFacturable,
  TasaImpuesto,
  type DetalleFactura,
} from '../services/facturacionService';
import { formatCurrency, fmtMoneda } from '../utils/format';
import { fmtFechaVE } from '../utils/fechas';

// ─── Helpers ──────────────────────────────────────────────────────────────────

const ESTADO_FACTURA_STYLE: Record<string, string> = {
  EMITIDA: 'bg-green-100 text-green-800 border-green-200',
  ANULADA: 'bg-red-100 text-red-800 border-red-200',
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

const fmtBs = (n: number) =>
  n.toLocaleString('es-VE', { minimumFractionDigits: 2, maximumFractionDigits: 2 });

const fmtEs = (n: number) => n.toLocaleString('es-ES');

// ─── Generación de PDF (reutilizada en ambos modales) ─────────────────────────
async function generarPdfFactura(idFactura: number) {
  const element = document.getElementById(`pdf-factura-container-${idFactura}`);
  if (!element) return;
  // Las fotos de producto deben estar cargadas antes de capturar.
  await esperarImagenesCargadas(element);
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
      if (ctx) ctx.drawImage(canvas, 0, sliceY, canvas.width, slicePx, 0, 0, canvas.width, slicePx);
      if (pg > 0) pdf.addPage('letter', 'portrait');
      pdf.addImage(sc.toDataURL('image/jpeg', 0.98), 'JPEG', 0, 0, pdfW, (slicePx / canvas.width) * pdfW);
    }
  }
  pdf.save(`Factura_Yeikar_${idFactura}.pdf`);
}

// ─── Modal: Emitir factura ────────────────────────────────────────────────────
interface LineaEmision {
  detalle_pedido_id: number;
  nombre: string;
  cantidad: number;
  precio_referencia: number;
  moneda_codigo?: string;
  precio_usd: string;
}

function ModalEmitirFactura({
  pedido,
  tasas,
  onClose,
  onCreado,
}: {
  pedido: PedidoFacturable;
  tasas: Record<string, number>;
  onClose: () => void;
  onCreado: (id: number) => void;
}) {
  const [lineas, setLineas] = useState<LineaEmision[]>(
    pedido.lineas.map((l) => ({
      detalle_pedido_id: l.detalle_pedido_id,
      nombre: l.nombre,
      cantidad: l.cantidad,
      precio_referencia: l.precio_referencia,
      moneda_codigo: l.moneda_codigo,
      precio_usd: '',
    })),
  );
  const [tasaUsdVes, setTasaUsdVes] = useState('');
  const [observaciones, setObservaciones] = useState('');
  const [permitirSaldo, setPermitirSaldo] = useState(false);
  const [submitting, setSubmitting] = useState(false);
  const [error, setError] = useState('');

  const { esAdmin } = useAuth();
  const tieneSaldoPendiente = pedido.saldo_pendiente > 0.01;

  const tasaIVA = tasas['IVA'] ?? 16;
  const tasaIGTF = tasas['IGTF'] ?? 3;
  const tasa = parseFloat(tasaUsdVes) || 0;

  const totalUsd = lineas.reduce((acc, l) => acc + (parseFloat(l.precio_usd) || 0) * l.cantidad, 0);
  const baseImponibleBs = totalUsd * tasa;
  const ivaBs = baseImponibleBs * (tasaIVA / 100);
  const totalConIvaBs = baseImponibleBs + ivaBs;
  const igtfBs = totalConIvaBs * (tasaIGTF / 100);
  const totalBs = totalConIvaBs + igtfBs;

  const handlePrecio = (detallePedidoId: number, value: string) => {
    setLineas((prev) => prev.map((l) => (l.detalle_pedido_id === detallePedidoId ? { ...l, precio_usd: value } : l)));
  };

  const handleEmitir = async () => {
    setError('');
    if (tasa <= 0) {
      setError('Ingresa la tasa de cambio (1 USD = X Bs.).');
      return;
    }
    for (const l of lineas) {
      if (!l.precio_usd || parseFloat(l.precio_usd) <= 0) {
        setError(`Ingresa el monto en USD a facturar para "${l.nombre}".`);
        return;
      }
    }
    try {
      setSubmitting(true);
      const creada = await facturacionService.crear({
        pedido_id: pedido.pedido_id,
        tasa_usd_ves: tasa,
        observaciones: observaciones || undefined,
        lineas: lineas.map((l) => ({ detalle_pedido_id: l.detalle_pedido_id, precio_usd: parseFloat(l.precio_usd) })),
        permitir_saldo_pendiente: permitirSaldo,
      });
      onCreado(creada.id);
    } catch (err: any) {
      setError(err?.response?.data?.detail || 'Error al emitir la factura.');
    } finally {
      setSubmitting(false);
    }
  };

  return (
    <div className="fixed inset-0 bg-black/50 backdrop-blur-sm flex items-center justify-center p-4 z-50">
      <div className="bg-white rounded-2xl border border-yeikar-secondary-light/10 shadow-2xl w-full max-w-3xl overflow-hidden flex flex-col max-h-[90vh]">
        <div className="bg-yeikar-neutral p-5 text-yeikar-tertiary flex items-center justify-between">
          <div>
            <h3 className="font-headline font-bold text-lg text-yeikar-primary">
              Emitir Factura — Pedido #{pedido.pedido_id}
            </h3>
            <p className="text-xs text-yeikar-tertiary/60 font-mono mt-0.5">
              {pedido.cliente_nombre} · Venta {pedido.venta_estado}
            </p>
          </div>
          <button onClick={onClose} className="text-yeikar-tertiary/50 hover:text-yeikar-tertiary transition-colors">
            <svg className="w-6 h-6" fill="none" stroke="currentColor" viewBox="0 0 24 24">
              <path strokeLinecap="round" strokeLinejoin="round" strokeWidth="2" d="M6 18L18 6M6 6l12 12" />
            </svg>
          </button>
        </div>

        <div className="overflow-y-auto flex-1 p-5 space-y-5">
          {/* Tasa USD → Bs */}
          <div className="grid grid-cols-2 gap-3">
            <div>
              <label className="text-xs font-bold text-yeikar-neutral/60 block mb-1">
                Tasa de cambio (1 USD = X Bs.)
              </label>
              <input
                type="number"
                min="0"
                step="0.01"
                value={tasaUsdVes}
                onChange={(e) => setTasaUsdVes(e.target.value)}
                placeholder="Ej: 50"
                className="w-full px-3 py-2 text-sm border border-yeikar-secondary-light/20 rounded-lg focus:outline-none focus:ring-2 focus:ring-yeikar-primary bg-white"
              />
            </div>
            <div className="flex items-end pb-1">
              <p className="text-xs text-yeikar-neutral/50">
                IVA <strong>{tasaIVA}%</strong> · IGTF <strong>{tasaIGTF}%</strong>
              </p>
            </div>
          </div>

          {tieneSaldoPendiente && (
            <div className="bg-amber-50 border border-amber-200 rounded-xl p-4 space-y-3">
              <div className="flex items-start justify-between gap-3">
                <div>
                  <p className="font-headline font-black text-sm text-amber-900">
                    Saldo pendiente: {fmtMoneda(pedido.saldo_pendiente, pedido.venta_moneda_codigo)}
                  </p>
                  <p className="text-xs text-amber-700 mt-0.5">
                    Este pedido no está cobrado al 100%. Emitir la factura deja constancia del saldo pendiente.
                  </p>
                </div>
              </div>
              {esAdmin ? (
                <label className="flex items-center gap-2 cursor-pointer text-sm font-bold text-amber-900 select-none">
                  <input
                    type="checkbox"
                    checked={permitirSaldo}
                    onChange={(e) => setPermitirSaldo(e.target.checked)}
                    className="w-4 h-4 accent-yeikar-primary"
                  />
                  Facturar sin pago completo (autoriza saldo pendiente)
                </label>
              ) : (
                <p className="text-xs font-bold text-red-600">Solo un administrador puede facturar con saldo pendiente.</p>
              )}
            </div>
          )}

          {/* Productos del pedido */}
          <div>
            <h4 className="font-headline font-bold text-sm text-yeikar-secondary mb-2 uppercase tracking-wider">
              Monto a facturar por producto (USD) — la cantidad es la del pedido
            </h4>
            <div className="space-y-2">
              {lineas.map((l) => (
                <div key={l.detalle_pedido_id} className="bg-yeikar-tertiary/10 rounded-lg px-3 py-2 flex items-center gap-3">
                  <div className="flex-1 min-w-0">
                    <p className="text-sm font-medium text-yeikar-secondary truncate">{l.nombre}</p>
                    <p className="text-[11px] font-mono text-yeikar-neutral/50">
                      Cantidad fija: <strong>{l.cantidad}</strong> · Ref. pedido:{' '}
                      {l.moneda_codigo ? `${l.moneda_codigo} ` : ''}{fmtEs(l.precio_referencia)}
                    </p>
                  </div>
                  <div className="flex items-center gap-1.5">
                    <span className="text-xs font-mono font-bold text-yeikar-neutral/40">$</span>
                    <input
                      type="number"
                      min="0"
                      step="0.01"
                      value={l.precio_usd}
                      onChange={(e) => handlePrecio(l.detalle_pedido_id, e.target.value)}
                      placeholder="0.00"
                      className="w-28 px-2 py-1.5 text-sm text-right border border-yeikar-secondary-light/20 rounded-lg focus:outline-none focus:ring-2 focus:ring-yeikar-primary bg-white font-mono"
                    />
                    <span className="text-[10px] font-bold text-yeikar-neutral/40 w-10 text-right">
                      {((parseFloat(l.precio_usd) || 0) * l.cantidad).toFixed(2)}
                    </span>
                  </div>
                </div>
              ))}
            </div>
          </div>

          {/* Vista previa fiscal */}
          <div className="bg-amber-50 border border-amber-200 rounded-xl p-4 space-y-1 font-mono text-sm">
            <div className="flex justify-between text-amber-900">
              <span>Total en USD</span>
              <span className="font-bold">${totalUsd.toFixed(2)}</span>
            </div>
            <div className="flex justify-between text-amber-900">
              <span>Base imponible (Bs.)</span>
              <span className="font-bold">Bs. {fmtBs(baseImponibleBs)}</span>
            </div>
            <div className="flex justify-between text-amber-900">
              <span>IVA {tasaIVA}%</span>
              <span className="font-bold">Bs. {fmtBs(ivaBs)}</span>
            </div>
            <div className="flex justify-between text-amber-900">
              <span>IGTF {tasaIGTF}%</span>
              <span className="font-bold">Bs. {fmtBs(igtfBs)}</span>
            </div>
            <div className="flex justify-between border-t border-amber-300 pt-1.5 text-amber-950">
              <span className="font-headline font-black uppercase">Total a pagar</span>
              <span className="font-black">Bs. {fmtBs(totalBs)}</span>
            </div>
          </div>

          <div>
            <label className="text-xs font-bold text-yeikar-neutral/60 block mb-1">Observaciones (opcional)</label>
            <textarea
              value={observaciones}
              onChange={(e) => setObservaciones(e.target.value)}
              rows={2}
              className="w-full px-3 py-2 text-sm border border-yeikar-secondary-light/20 rounded-lg focus:outline-none focus:ring-2 focus:ring-yeikar-primary bg-white resize-none"
            />
          </div>

          {error && (
            <p className="text-xs text-red-600 bg-red-50 border border-red-200 rounded-lg px-3 py-2">{error}</p>
          )}

          <div className="flex gap-2">
            <button
              onClick={onClose}
              className="flex-1 py-2.5 text-sm font-bold text-yeikar-neutral/60 border border-yeikar-secondary-light/20 rounded-xl hover:bg-yeikar-tertiary/20 transition-all"
            >
              Cancelar
            </button>
            <button
              onClick={handleEmitir}
              disabled={submitting}
              className="flex-1 py-2.5 text-sm font-bold bg-yeikar-primary text-yeikar-neutral rounded-xl hover:bg-yeikar-primary/90 transition-all disabled:opacity-50"
            >
              {submitting ? 'Emitiendo...' : 'Emitir Factura'}
            </button>
          </div>
        </div>
      </div>
    </div>
  );
}

// ─── Modal: Detalle de factura + PDF ──────────────────────────────────────────
// Nombre visible de una línea facturada: la descripción copiada del pedido
// cubre insumos (nombre del material); los fallbacks distinguen insumo/producto.
const nombreLineaFactura = (d: DetalleFactura): string =>
  d.descripcion ?? d.producto?.nombre ?? (d.material_id ? `Insumo #${d.material_id}` : `Producto #${d.producto_id ?? '?'}`);

function ModalDetalleFactura({
  facturaId,
  onClose,
  onAnulada,
}: {
  facturaId: number;
  onClose: () => void;
  onAnulada: () => void;
}) {
  const [factura, setFactura] = useState<FacturaDetalle | null>(null);
  const [loading, setLoading] = useState(true);
  const [isGeneratingPdf, setIsGeneratingPdf] = useState(false);
  const [anulando, setAnulando] = useState(false);
  const [confirmarAnulacion, setConfirmarAnulacion] = useState(false);
  const [error, setError] = useState('');
  const toast = useToast();

  const cargar = useCallback(async () => {
    try {
      setLoading(true);
      const data = await facturacionService.getById(facturaId);
      setFactura(data);
    } finally {
      setLoading(false);
    }
  }, [facturaId]);

  useEffect(() => {
    cargar();
  }, [cargar]);

  const handlePdf = async () => {
    if (!factura) return;
    setIsGeneratingPdf(true);
    try {
      await generarPdfFactura(factura.id);
    } catch (err) {
      console.error('Error al generar PDF:', err);
      toast.error('Hubo un error al generar el archivo PDF.');
    } finally {
      setIsGeneratingPdf(false);
    }
  };

  const handleAnular = async () => {
    if (!factura) return;
    setError('');
    try {
      setAnulando(true);
      await facturacionService.anular(factura.id);
      setConfirmarAnulacion(false);
      await cargar();
      onAnulada();
      toast.success(`Factura #${factura.id} anulada. El pedido puede volver a facturarse.`);
    } catch (err: any) {
      setError(err?.response?.data?.detail || 'Error al anular la factura.');
    } finally {
      setAnulando(false);
    }
  };

  const tasa = factura?.tasa_usd_ves ?? 1;
  const totalVentaBs = factura ? Number(factura.base_imponible_bs) + Number(factura.iva_bs) : 0;

  return (
    <>
    <div className="fixed inset-0 bg-black/50 backdrop-blur-sm flex items-center justify-center p-4 z-50">
      <div className="bg-white rounded-2xl border border-yeikar-secondary-light/10 shadow-2xl w-full max-w-2xl overflow-hidden flex flex-col max-h-[90vh]">
        <div className="bg-yeikar-neutral p-5 text-yeikar-tertiary flex items-center justify-between">
          <div>
            <h3 className="font-headline font-bold text-lg text-yeikar-primary">
              Factura Fiscal #{factura?.id ?? '...'}
            </h3>
            <p className="text-xs text-yeikar-tertiary/60 font-mono mt-0.5">
              {factura?.cliente?.nombre} · Pedido #{factura?.pedido_id}
            </p>
          </div>
          <div className="flex items-center gap-3">
            {factura && (
              <>
                <button
                  onClick={handlePdf}
                  disabled={isGeneratingPdf}
                  className="px-3 py-1.5 bg-yeikar-primary text-yeikar-neutral hover:bg-yeikar-primary/90 rounded-xl text-xs font-bold font-headline transition-all flex items-center gap-1.5 shadow-sm disabled:opacity-50"
                >
                  <svg className="w-4 h-4" fill="none" stroke="currentColor" viewBox="0 0 24 24">
                    <path strokeLinecap="round" strokeLinejoin="round" strokeWidth="2" d="M12 10v6m0 0l-3-3m3 3l3-3m2 8H7a2 2 0 01-2-2V5a2 2 0 012-2h5.586a1 1 0 01.707.293l5.414 5.414a1 1 0 01.293.707V19a2 2 0 01-2 2z" />
                  </svg>
                  {isGeneratingPdf ? 'Generando PDF…' : 'Descargar PDF'}
                </button>
                {factura.estado === 'EMITIDA' && (
                  <button
                    onClick={() => setConfirmarAnulacion(true)}
                    disabled={anulando}
                    className="px-3 py-1.5 border border-red-300 text-red-600 hover:bg-red-50 rounded-xl text-xs font-bold transition-all disabled:opacity-50"
                  >
                    {anulando ? 'Anulando...' : 'Anular'}
                  </button>
                )}
              </>
            )}
            <button onClick={onClose} className="text-yeikar-tertiary/50 hover:text-yeikar-tertiary transition-colors">
              <svg className="w-6 h-6" fill="none" stroke="currentColor" viewBox="0 0 24 24">
                <path strokeLinecap="round" strokeLinejoin="round" strokeWidth="2" d="M6 18L18 6M6 6l12 12" />
              </svg>
            </button>
          </div>
        </div>

        <div className="overflow-y-auto flex-1 p-5 space-y-5">
          {loading || !factura ? (
            <Spinner />
          ) : (
            <>
              <div className="grid grid-cols-1 min-[420px]:grid-cols-3 gap-3">
                <div className="bg-yeikar-tertiary/20 rounded-xl p-3 text-center">
                  <p className="text-xs text-yeikar-neutral/50 font-mono mb-1">Total USD</p>
                  <p className="font-headline font-bold text-yeikar-secondary">${fmtEs(Number(factura.total_usd))}</p>
                </div>
                <div className="bg-green-50 rounded-xl p-3 text-center border border-green-100">
                  <p className="text-xs text-green-600 font-mono mb-1">Tasa (1 USD → Bs.)</p>
                  <p className="font-headline font-bold text-green-700">Bs. {fmtEs(Number(factura.tasa_usd_ves))}</p>
                </div>
                <div className="bg-amber-50 rounded-xl p-3 text-center border border-amber-100">
                  <p className="text-xs text-amber-600 font-mono mb-1">Total a pagar</p>
                  <p className="font-headline font-bold text-amber-700">Bs. {fmtBs(Number(factura.total_bs))}</p>
                </div>
              </div>

              <div className="flex items-center gap-2">
                <Badge text={factura.estado} className={ESTADO_FACTURA_STYLE[factura.estado]} />
                <span className="text-xs text-yeikar-neutral/40 font-mono">
                  Emitida el {fmtFechaVE(factura.fecha_emision)} por {factura.creador_nombre || '—'}
                </span>
              </div>

              <div>
                <h4 className="font-headline font-bold text-sm text-yeikar-secondary mb-2 uppercase tracking-wider">
                  Productos facturados
                </h4>
                <div className="space-y-2">
                  {factura.detalles.map((d: DetalleFactura) => (
                    <div key={d.id} className="flex justify-between items-center text-sm bg-yeikar-tertiary/10 rounded-lg px-3 py-2">
                      <span className="font-medium text-yeikar-secondary">{nombreLineaFactura(d)}</span>
                      <span className="font-mono text-yeikar-neutral/70">
                        {d.cantidad} × ${Number(d.precio_usd).toLocaleString('es-ES')} USD
                        <span className="ml-2 text-[10px] font-bold text-yeikar-neutral/40">
                          = Bs. {fmtBs(Number(d.subtotal_bs))}
                        </span>
                      </span>
                    </div>
                  ))}
                </div>
              </div>

              {error && (
                <p className="text-xs text-red-600 bg-red-50 border border-red-200 rounded-lg px-3 py-2">{error}</p>
              )}

              {/* Plantilla del PDF (oculta, para captura) */}
              <div className="fixed -left-[9999px] top-0 pointer-events-none z-[-100]">
                <FacturaFiscalPDF
                  id={`pdf-factura-container-${factura.id}`}
                  numero={`00 – ${factura.id.toString().padStart(5, '0')}`}
                  numeroControl={`00 – ${factura.id.toString().padStart(6, '0')}`}
                  fechaEmision={fmtFechaVE(factura.fecha_emision)}
                  cliente={factura.cliente}
                  monedaCodigo="USD"
                  tasaBs={tasa}
                  lineas={factura.detalles.map((d) => ({
                    key: d.id,
                    descripcion: nombreLineaFactura(d),
                    foto: d.producto?.fotos?.[0]?.url ?? null,
                    cantidad: Number(d.cantidad),
                    precioBs: Number(d.precio_usd) * tasa,
                    subtotalBs: Number(d.subtotal_bs),
                  }))}
                  baseImponibleBs={Number(factura.base_imponible_bs)}
                  ivaBs={Number(factura.iva_bs)}
                  totalVentaBs={totalVentaBs}
                  igtfBs={Number(factura.igtf_bs)}
                  totalAPagarBs={Number(factura.total_bs)}
                />
              </div>
            </>
          )}
        </div>
      </div>
    </div>
    <ConfirmDialog
      open={confirmarAnulacion}
      title="Anular factura"
      message="¿Anular esta factura? Quedará registrada como ANULADA y el pedido podrá volver a facturarse con una corrección."
      confirmLabel="Sí, anular"
      danger
      onConfirm={handleAnular}
      onCancel={() => setConfirmarAnulacion(false)}
    />
    </>
  );
}

// ─── Configuración de impuestos (admin) ───────────────────────────────────────
function ConfigImpuestos({ tasas, onUpdated }: { tasas: TasaImpuesto[]; onUpdated: () => void }) {
  const [editing, setEditing] = useState<Record<string, string>>({});
  const [saving, setSaving] = useState(false);
  const [msg, setMsg] = useState('');

  useEffect(() => {
    setEditing(
      Object.fromEntries(tasas.map((t) => [t.clave, String(t.tasa)])),
    );
  }, [tasas]);

  const handleGuardar = async (t: TasaImpuesto) => {
    setMsg('');
    const value = parseFloat(editing[t.clave]);
    if (!value || value <= 0) return;
    try {
      setSaving(true);
      await facturacionService.actualizarTasa(t.clave, value);
      setMsg(`Tasa ${t.clave} actualizada a ${value}%.`);
      onUpdated();
    } catch (err: any) {
      setMsg(err?.response?.data?.detail || 'Error al guardar la tasa.');
    } finally {
      setSaving(false);
    }
  };

  return (
    <div className="bg-yeikar-tertiary/5 border border-yeikar-secondary-light/10 rounded-2xl p-4 space-y-3">
      <div className="flex items-center justify-between">
        <h3 className="font-headline font-bold text-sm text-yeikar-secondary uppercase tracking-wider">
          Tasas de impuestos
        </h3>
        {msg && <span className="text-xs font-bold text-yeikar-primary">{msg}</span>}
      </div>
      <p className="text-xs text-yeikar-neutral/50">
        Configurables sin tocar código: aplican a las próximas facturas.
      </p>
      <div className="grid grid-cols-2 gap-3">
        {tasas.map((t) => (
          <div key={t.clave} className="flex items-center gap-2">
            <label className="text-xs font-bold text-yeikar-neutral/60 flex-1">{t.nombre}</label>
            <input
              type="number"
              min="0"
              step="0.01"
              value={editing[t.clave] ?? ''}
              onChange={(e) => setEditing((prev) => ({ ...prev, [t.clave]: e.target.value }))}
              className="w-20 px-2 py-1.5 text-sm text-right border border-yeikar-secondary-light/20 rounded-lg focus:outline-none focus:ring-2 focus:ring-yeikar-primary bg-white font-mono"
            />
            <span className="text-xs text-yeikar-neutral/40">%</span>
            <button
              onClick={() => handleGuardar(t)}
              disabled={saving}
              className="px-3 py-1.5 bg-yeikar-primary text-yeikar-neutral rounded-lg text-xs font-bold hover:bg-yeikar-primary/90 transition-all disabled:opacity-50"
            >
              Guardar
            </button>
          </div>
        ))}
      </div>
    </div>
  );
}

// ─── Página principal ─────────────────────────────────────────────────────────
export default function Facturacion() {
  const { esAdmin } = useAuth();
  const [activeTab, setActiveTab] = useState<'facturas' | 'porFacturar'>('facturas');

  const [facturas, setFacturas] = useState<Factura[]>([]);
  const [facturasLoading, setFacturasLoading] = useState(false);

  const [pedidos, setPedidos] = useState<PedidoFacturable[]>([]);
  const [pedidosLoading, setPedidosLoading] = useState(false);

  const [tasas, setTasas] = useState<TasaImpuesto[]>([]);

  const [detalleFacturaId, setDetalleFacturaId] = useState<number | null>(null);
  const [pedidoParaFactura, setPedidoParaFactura] = useState<PedidoFacturable | null>(null);

  const [filtroEstado, setFiltroEstado] = useState<string>('');
  const [buscarFacturas, setBuscarFacturas] = useState('');
  const [totalFacturas, setTotalFacturas] = useState(0);
  const [cargandoMasFacturas, setCargandoMasFacturas] = useState(false);
  const buscarFacturasDeb = useDebouncedValue(buscarFacturas, 400);
  const PAGE_FACTURAS = 100;

  const cargarFacturas = useCallback(async () => {
    setFacturasLoading(true);
    try {
      const { items, total } = await facturacionService.getAll({
        buscar: buscarFacturasDeb.trim() || undefined,
        estado: filtroEstado || undefined,
        salto: 0,
        limite: PAGE_FACTURAS,
      });
      setFacturas(items);
      setTotalFacturas(total);
    } catch {
      // dejar la lista como está
    } finally {
      setFacturasLoading(false);
    }
  }, [buscarFacturasDeb, filtroEstado]);

  const cargarMasFacturas = useCallback(async () => {
    setCargandoMasFacturas(true);
    try {
      const { items, total } = await facturacionService.getAll({
        buscar: buscarFacturasDeb.trim() || undefined,
        estado: filtroEstado || undefined,
        salto: facturas.length,
        limite: PAGE_FACTURAS,
      });
      setFacturas((prev) => [...prev, ...items]);
      setTotalFacturas(total);
    } catch {
      // dejar la lista como está
    } finally {
      setCargandoMasFacturas(false);
    }
  }, [buscarFacturasDeb, filtroEstado, facturas.length]);

  const cargarPedidos = useCallback(async () => {
    try {
      setPedidosLoading(true);
      const data = await facturacionService.getPedidosFacturables();
      setPedidos(data);
    } finally {
      setPedidosLoading(false);
    }
  }, []);

  const cargarTasas = useCallback(async () => {
    try {
      const data = await facturacionService.getTasas();
      setTasas(data);
    } catch {
      setTasas([]);
    }
  }, []);

  useEffect(() => {
    cargarTasas();
    if (activeTab === 'facturas') {
      cargarFacturas();
    } else {
      cargarPedidos();
    }
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [activeTab, buscarFacturasDeb, filtroEstado]);

  const tasasMap: Record<string, number> = Object.fromEntries(tasas.map((t) => [t.clave, Number(t.tasa)]));

  return (
    <div className="space-y-6">
      {/* Header */}
      <div className="flex flex-col sm:flex-row items-start sm:items-center justify-between gap-4">
        <div>
          <h1 className="text-2xl sm:text-3xl font-black font-headline text-yeikar-neutral tracking-tight">Facturación</h1>
          <p className="text-yeikar-neutral/60 mt-1 text-sm">
            Emite facturas fiscales de pedidos, con el monto en USD que decidas por producto.
          </p>
        </div>
        {activeTab === 'porFacturar' && pedidos.length > 0 && (
          <div className="flex items-center gap-2 bg-amber-50 border border-amber-200 text-amber-700 px-4 py-2 rounded-xl text-sm font-bold">
            {pedidos.length} pedido{pedidos.length !== 1 ? 's' : ''} por facturar
          </div>
        )}
      </div>

      {esAdmin && tasas.length > 0 && <ConfigImpuestos tasas={tasas} onUpdated={cargarTasas} />}

      {/* Tabs */}
      <div className="flex border-b border-yeikar-secondary-light/10">
        <button
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
          onClick={() => setActiveTab('porFacturar')}
          className={`px-5 py-3 font-headline font-bold text-sm tracking-tight border-b-2 transition-all flex items-center gap-2 ${
            activeTab === 'porFacturar'
              ? 'border-yeikar-primary text-yeikar-primary'
              : 'border-transparent text-yeikar-neutral/60 hover:text-yeikar-secondary'
          }`}
        >
          Pedidos por Facturar
          {pedidos.length > 0 && (
            <span className="bg-yeikar-primary text-yeikar-neutral text-xs font-bold rounded-full w-5 h-5 flex items-center justify-center">
              {pedidos.length}
            </span>
          )}
        </button>
      </div>

      {/* TAB: Facturas emitidas */}
      {activeTab === 'facturas' && (
        <div className="space-y-4">
          <div className="flex items-center gap-3 flex-wrap">
            <span className="text-xs font-bold text-yeikar-neutral/50 font-mono">FILTRAR:</span>
            {['', 'EMITIDA', 'ANULADA'].map((est) => (
              <button
                key={est}
                onClick={() => setFiltroEstado(est)}
                className={`px-3 py-1 rounded-full text-xs font-bold border transition-all ${
                  filtroEstado === est
                    ? 'bg-yeikar-primary text-yeikar-neutral border-yeikar-primary'
                    : 'text-yeikar-neutral/60 border-yeikar-secondary-light/20 hover:border-yeikar-primary/50'
                }`}
              >
                {est === '' ? 'Todas' : est}
              </button>
            ))}

            <div className="relative ml-auto">
              <Search className="absolute left-3 top-1/2 -translate-y-1/2 h-4 w-4 text-yeikar-neutral/40" />
              <input
                type="text"
                value={buscarFacturas}
                onChange={(e) => setBuscarFacturas(e.target.value)}
                placeholder="Buscar por # factura, pedido o cliente..."
                className="w-64 rounded-xl border border-yeikar-secondary-light/15 bg-white py-2 pl-9 pr-3 text-sm focus:outline-none focus:border-yeikar-primary shadow-sm"
              />
            </div>
          </div>

          <div className="text-xs text-yeikar-neutral/50 font-medium">
            Mostrando <strong className="text-yeikar-secondary">{facturas.length}</strong>
            {totalFacturas > 0 ? <> de <strong className="text-yeikar-secondary">{totalFacturas}</strong></> : null} facturas
          </div>

          {facturasLoading ? (
            <Spinner />
          ) : facturas.length === 0 ? (
            <div className="text-center py-16 text-yeikar-neutral/40">
              <p className="text-sm font-bold">No hay facturas para mostrar.</p>
              <p className="text-xs mt-1">Emite la primera desde la pestaña "Pedidos por Facturar".</p>
            </div>
          ) : (
            <div className="bg-white rounded-2xl border border-yeikar-secondary-light/10 shadow-card overflow-hidden">
              <div className="overflow-x-auto">
                <table className="w-full text-sm">
                  <thead>
                    <tr className="bg-yeikar-tertiary/60 text-left text-xs font-bold uppercase tracking-wider text-yeikar-neutral/50">
                      <th className="px-5 py-4 border-b border-yeikar-secondary/20"># Factura</th>
                      <th className="px-5 py-4 border-b border-yeikar-secondary/20">Cliente</th>
                      <th className="px-5 py-4 border-b border-yeikar-secondary/20">Emisión</th>
                      <th className="px-5 py-4 border-b border-yeikar-secondary/20 text-right">Total USD</th>
                      <th className="px-5 py-4 border-b border-yeikar-secondary/20 text-right">Total Bs.</th>
                      <th className="px-5 py-4 border-b border-yeikar-secondary/20">Estado</th>
                      <th className="px-5 py-4 border-b border-yeikar-secondary/20"></th>
                    </tr>
                  </thead>
                  <tbody>
                    {facturas.map((f) => (
                      <tr key={f.id} className="hover:bg-yeikar-tertiary/30 transition-colors">
                        <td className="px-5 py-3.5 font-mono font-bold text-yeikar-primary">
                          00-{f.id.toString().padStart(5, '0')}
                        </td>
                        <td className="px-5 py-3.5 font-medium text-yeikar-secondary">{f.cliente?.nombre ?? '—'}</td>
                        <td className="px-5 py-3.5 text-yeikar-neutral/70 font-mono text-xs">
                          {fmtFechaVE(f.fecha_emision)}
                        </td>
                        <td className="px-5 py-3.5 text-right font-mono text-yeikar-neutral/70">
                          ${fmtEs(Number(f.total_usd))}
                        </td>
                        <td className="px-5 py-3.5 text-right font-mono font-bold text-yeikar-secondary">
                          Bs. {fmtEs(Number(f.total_bs))}
                        </td>
                        <td className="px-5 py-3.5">
                          <Badge text={f.estado} className={ESTADO_FACTURA_STYLE[f.estado]} />
                        </td>
                        <td className="px-5 py-3.5 text-right">
                          <button
                            onClick={() => setDetalleFacturaId(f.id)}
                            className="px-3 py-1.5 bg-yeikar-primary text-yeikar-neutral rounded-lg text-xs font-bold hover:bg-yeikar-primary/90 transition-all"
                          >
                            Ver / PDF
                          </button>
                        </td>
                      </tr>
                    ))}
                  </tbody>
                </table>
              </div>
            </div>
          )}

          {!facturasLoading && facturas.length < totalFacturas && (
            <div className="flex justify-center pt-1">
              <button
                type="button"
                onClick={cargarMasFacturas}
                disabled={cargandoMasFacturas}
                className="flex items-center gap-2 px-5 py-2.5 rounded-xl text-xs font-bold font-headline bg-white border border-yeikar-secondary-light/20 text-yeikar-secondary hover:bg-yeikar-tertiary/50 transition-all shadow-xs disabled:opacity-50"
              >
                {cargandoMasFacturas ? <Loader2 className="w-4 h-4 animate-spin" /> : <Plus className="w-4 h-4" />}
                {cargandoMasFacturas ? 'Cargando…' : `Cargar más (${totalFacturas - facturas.length} restantes)`}
              </button>
            </div>
          )}
        </div>
      )}

      {/* TAB: Pedidos por facturar */}
      {activeTab === 'porFacturar' && (
        <div className="space-y-4">
          {pedidosLoading ? (
            <Spinner />
          ) : pedidos.length === 0 ? (
            <div className="text-center py-16 text-yeikar-neutral/40">
              <p className="text-sm font-bold">No hay pedidos por facturar.</p>
              <p className="text-xs mt-1">Los pedidos aparecen aquí cuando su venta está registrada y aún no tienen factura.</p>
            </div>
          ) : (
            <div className="grid grid-cols-1 md:grid-cols-2 gap-4">
              {pedidos.map((p) => (
                <div key={p.pedido_id} className="bg-white rounded-2xl border border-yeikar-secondary-light/10 shadow-card p-5 flex flex-col gap-3">
                  <div className="flex items-start justify-between gap-3">
                    <div>
                      <p className="font-headline font-bold text-yeikar-neutral">Pedido #{p.pedido_id}</p>
                      <p className="text-sm text-yeikar-neutral/60">{p.cliente_nombre}</p>
                      <p className="text-xs font-mono text-yeikar-neutral/40 mt-0.5">
                        {fmtFechaVE(p.fecha)} · {p.lineas.length} producto{p.lineas.length !== 1 ? 's' : ''}
                      </p>
                    </div>
                    <Badge
                      text={p.saldo_pendiente > 0.01 ? `SALDO ${fmtMoneda(p.saldo_pendiente, p.venta_moneda_codigo)}` : 'PAGADA'}
                      className={p.saldo_pendiente > 0.01 ? 'bg-amber-100 text-amber-800 border-amber-200' : 'bg-green-100 text-green-800 border-green-200'}
                    />
                  </div>
                  <div className="text-xs font-mono text-yeikar-neutral/50">
                    Pagado: <strong>{fmtMoneda(p.total_pagado, p.venta_moneda_codigo)}</strong>
                    {p.saldo_pendiente > 0.01 && (
                      <>
                        <span className="mx-1">·</span> Saldo pendiente:{' '}
                        <strong className="text-amber-700">{fmtMoneda(p.saldo_pendiente, p.venta_moneda_codigo)}</strong>
                      </>
                    )}
                  </div>
                  <button
                    onClick={() => setPedidoParaFactura(p)}
                    className="w-full py-2.5 bg-yeikar-primary text-yeikar-neutral font-bold font-headline rounded-xl hover:bg-yeikar-primary/90 transition-all text-sm"
                  >
                    Facturar
                  </button>
                </div>
              ))}
            </div>
          )}
        </div>
      )}

      {/* Modales */}
      {pedidoParaFactura && (
        <ModalEmitirFactura
          pedido={pedidoParaFactura}
          tasas={tasasMap}
          onClose={() => setPedidoParaFactura(null)}
          onCreado={(id) => {
            setPedidoParaFactura(null);
            cargarPedidos();
            cargarFacturas();
            setDetalleFacturaId(id);
            setActiveTab('facturas');
          }}
        />
      )}
      {detalleFacturaId !== null && (
        <ModalDetalleFactura
          facturaId={detalleFacturaId}
          onClose={() => setDetalleFacturaId(null)}
          onAnulada={cargarFacturas}
        />
      )}
    </div>
  );
}
