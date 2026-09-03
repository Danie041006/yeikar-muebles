import { useEffect, useState, useCallback } from 'react';
import api from '../services/api';
import { useToast } from '../context/ToastContext';
import { SearchInput, SearchSelect, ResponsiveDataTable, type DataColumn } from '../components/ui';
import {
  ventaService,
  pagoService,
  Venta,
  VentaDetalle,
  Pago,
  METODOS_PAGO,
  cargarMetodosPago,
  labelMetodoPago,
  type PagoCreate,
  type MetodoPagoOption,
} from '../services/ventaService';
import { formatCurrency, nombreMoneda, fmtMoneda, tasaNaturalAAlmacenada, convertirConTasaNatural } from '../utils/format';
import { subirAdjunto, TIPO_ADJUNTO } from '../services/adjuntosService';
import AdjuntoImagen from '../components/AdjuntoImagen';

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
  const toast = useToast();
  const [detalle, setDetalle] = useState<VentaDetalle | null>(null);
  const [loading, setLoading] = useState(true);

  // ── Formulario de nuevo pago ──────────────────────────────────────────────
  const [showForm, setShowForm] = useState(false);
  const [monedaPagoId, setMonedaPagoId] = useState<number | null>(null);
  const [monto, setMonto] = useState('');
  const [metodoPago, setMetodoPago] = useState('EFECTIVO_USD');
  const [tasaNaturalInput, setTasaNaturalInput] = useState('');      // tasa en sentido natural: 1 [V] = X [P]
  const [referencia, setReferencia] = useState('');
  const [observaciones, setObservaciones] = useState('');
  const [submitting, setSubmitting] = useState(false);
  const [errorPago, setErrorPago] = useState('');
  const [reciboArchivo, setReciboArchivo] = useState<File | null>(null);
  const [reciboPreview, setReciboPreview] = useState<string | null>(null);
  const [reciboVer, setReciboVer] = useState<{ id: number; mime: string } | null>(null);
  const [monedas, setMonedas] = useState<{ id: number; codigo: string; nombre: string; simbolo: string }[]>([]);
  // Métodos de pago: cuentas reales (metodo_caja) con fallback al estático.
  const [metodosPago, setMetodosPago] = useState<MetodoPagoOption[]>(METODOS_PAGO.map((m) => ({ ...m })));

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

  const cargarMetodos = useCallback(async () => {
    try {
      const metodos = await cargarMetodosPago();
      if (metodos.length > 0) setMetodosPago(metodos);
    } catch {}
  }, []);

  useEffect(() => {
    cargar();
    cargarMonedas();
    cargarMetodos();
  }, [cargar, cargarMonedas, cargarMetodos]);

  // Cuando cambia el metodo de pago, auto-seleccionar la moneda correspondiente
  useEffect(() => {
    if (!monedas.length) return;
    const meta = metodosPago.find(m => m.value === metodoPago);
    if (!meta) return;
    const found = monedas.find(m => m.codigo === meta.moneda);
    if (found) setMonedaPagoId(found.id);
  }, [metodoPago, monedas, metodosPago]);

  // Si monedaPagoId coincide con la moneda de la venta, TRM no aplica
  const monedaVentaId = detalle?.moneda_id ?? null;
  const necesitaTRM = monedaPagoId !== null && monedaVentaId !== null && monedaPagoId !== monedaVentaId;
  // tasa_natural va en el sentido natural: 1 [V] = X [P] (p. ej. 1 USD = 4500 COP).
  // El backend guarda la inversa (tasa_almacenada = 1 / tasa_natural): 1 [P] = tasa [V].
  const tasaNatural = parseFloat(tasaNaturalInput) || 0;
  const tasaAlmacenada = tasaNatural > 0 ? tasaNaturalAAlmacenada(tasaNatural) : 0;
  const montoNum = parseFloat(monto) || 0;
  const montoEquivalente = necesitaTRM && tasaNatural > 0 ? convertirConTasaNatural(montoNum, tasaNatural) : montoNum;
  const monedaPago = monedas.find(m => m.id === monedaPagoId);
  const monedaVenta = monedas.find(m => m.id === monedaVentaId);
  const saldoRestante = detalle ? Number(detalle.saldo_pendiente) : 0;

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
    if (necesitaTRM && (!tasaNaturalInput || tasaNatural <= 0)) {
      setErrorPago('La moneda del pago difiere de la de la factura. Ingresa la tasa de cambio (1 factura = ? pago).');
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
        ...(necesitaTRM ? { tasa_cambio: tasaNaturalAAlmacenada(tasaNatural) } : {}),
      };
      const pagoCreado = await pagoService.registrar(payload);
      // Recibo digital (opcional): comprobante del pago
      if (reciboArchivo && pagoCreado) {
        await subirAdjunto(reciboArchivo, TIPO_ADJUNTO.PAGO, pagoCreado.id);
      }
      setMonto('');
      setReferencia('');
      setObservaciones('');
      setTasaNaturalInput('');
      setReciboArchivo(null);
      if (reciboPreview) URL.revokeObjectURL(reciboPreview);
      setReciboPreview(null);
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
      if (tasaNatural <= 0) {
        setErrorPago('Ingresa primero la tasa de cambio (1 factura = ? pago) para calcular el monto restante.');
        return;
      }
      // El saldo está en la moneda de la venta; con tasa natural (1 V = X P)
      // el monto a cobrar en la moneda del pago es saldo × tasa_natural.
      const montoCalc = saldoRestante * tasaNatural;
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
              Estado Financiero del pedido #{detalle?.id ?? '...'}
            </h3>
            {detalle && (
              <p className="text-xs text-yeikar-tertiary/60 font-mono mt-0.5">
                {detalle.cliente?.nombre} 
              </p>
            )}
          </div>
          <div className="flex items-center gap-3">
            {detalle?.pedido_id && (
              <button
                onClick={() => { window.location.href = `/historial?tipo=pedido&id=${detalle.pedido_id}`; }}
                className="px-3 py-1.5 bg-yeikar-secondary text-yeikar-primary hover:bg-yeikar-secondary-light rounded-xl text-xs font-bold font-headline transition-all flex items-center gap-1.5 shadow-sm"
                title="Ver expediente completo del pedido"
              >
                <svg className="w-4 h-4" fill="none" stroke="currentColor" viewBox="0 0 24 24">
                  <path strokeLinecap="round" strokeLinejoin="round" strokeWidth="2" d="M3 7v10a2 2 0 002 2h14a2 2 0 002-2V9a2 2 0 00-2-2h-6l-2-2H5a2 2 0 00-2 2z" />
                </svg>
                Expediente
              </button>
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
              <div className="grid grid-cols-1 min-[420px]:grid-cols-3 gap-3">
                <div className="bg-yeikar-tertiary/20 rounded-xl p-3 text-center">
                  <p className="text-xs text-yeikar-neutral/50 font-mono mb-1">
                    Total Factura
                    {detalle.moneda && (
                      <span className="ml-1 px-1.5 py-0.5 rounded bg-yeikar-secondary/20 text-yeikar-secondary font-bold text-[10px]">
                        {detalle.moneda.codigo}
                      </span>
                    )}
                  </p>
                  <p className="font-headline font-bold text-yeikar-secondary">
                    {detalle.moneda?.simbolo}{Number(detalle.total).toLocaleString('es-ES')}
                  </p>
                  {detalle.moneda?.codigo !== 'COP' && (
                    <p className="text-[10px] font-mono text-yeikar-neutral/40 mt-0.5">
                      ≈ {formatCurrency(Number(detalle.total_en_moneda_base), 'COP')}
                    </p>
                  )}
                </div>
                <div className="bg-green-50 rounded-xl p-3 text-center border border-green-100">
                  <p className="text-xs text-green-600 font-mono mb-1">
                    Pagado
                    {detalle.moneda && (
                      <span className="ml-1 px-1.5 py-0.5 rounded bg-green-200/60 text-green-800 font-bold text-[10px]">
                        {detalle.moneda.codigo}
                      </span>
                    )}
                  </p>
                  <p className="font-headline font-bold text-green-700">
                    {detalle.moneda?.simbolo}{Number(detalle.total_pagado).toLocaleString('es-ES')}
                  </p>
                  {detalle.moneda?.codigo !== 'COP' && (
                    <p className="text-[10px] font-mono text-green-600/50 mt-0.5">
                      ≈ {formatCurrency(Number(detalle.total_pagado) * Number(detalle.tasa_cambio), 'COP')}
                    </p>
                  )}
                </div>
                <div className="bg-amber-50 rounded-xl p-3 text-center border border-amber-100">
                  <p className="text-xs text-amber-600 font-mono mb-1">
                    Saldo
                    {detalle.moneda && (
                      <span className="ml-1 px-1.5 py-0.5 rounded bg-amber-200/60 text-amber-800 font-bold text-[10px]">
                        {detalle.moneda.codigo}
                      </span>
                    )}
                  </p>
                  <p className="font-headline font-bold text-amber-700">
                    {detalle.moneda?.simbolo}{Number(detalle.saldo_pendiente).toLocaleString('es-ES')}
                  </p>
                  {detalle.moneda?.codigo !== 'COP' && (
                    <p className="text-[10px] font-mono text-amber-600/50 mt-0.5">
                      ≈ {formatCurrency(Number(detalle.saldo_pendiente) * Number(detalle.tasa_cambio), 'COP')}
                    </p>
                  )}
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
                        {d.tipo_item === 'INSUMO'
                          ? d.material?.nombre ?? `Material #${d.material_id}`
                          : d.producto?.nombre ?? `Producto #${d.producto_id}`}
                        {d.tipo_item === 'INSUMO' && (
                          <span className="ml-1.5 text-[9px] font-bold uppercase px-1.5 py-0.5 rounded bg-emerald-50 text-emerald-700 border border-emerald-200">Insumo</span>
                        )}
                        {d.tipo_item === 'REVENTA' && (
                          <span className="ml-1.5 text-[9px] font-bold uppercase px-1.5 py-0.5 rounded bg-sky-50 text-sky-700 border border-sky-200">Reventa</span>
                        )}
                      </span>
                      <span className="font-mono text-yeikar-neutral/70">
                        {d.cantidad} × {detalle.moneda?.simbolo}{Number(d.precio).toLocaleString('es-ES')}
                        <span className="ml-1 text-[10px] font-bold text-yeikar-neutral/40">
                          {detalle.moneda?.codigo ?? ''}
                        </span>
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
                      const metodoLabel = labelMetodoPago(metodosPago, p.metodo_pago);
                      const esMultimoneda = p.tasa_cambio && p.tasa_cambio !== 1;
                      const pagoCodigo = p.moneda?.codigo ?? '?';
                      const ventaCodigo = detalle.moneda?.codigo ?? '?';
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
                              {/* Recibos del cobro (comprobantes digitales) */}
                              {p.recibos && p.recibos.length > 0 && (
                                <div className="flex gap-1.5 mt-1.5">
                                  {p.recibos.map((r) => (
                                    <AdjuntoImagen
                                      key={r.id}
                                      adjunto={r}
                                      alt="recibo"
                                      className="h-10 w-10 rounded border border-green-200 hover:border-green-400 transition-colors"
                                      onClick={() => setReciboVer({ id: r.id, mime: r.mime })}
                                    />
                                  ))}
                                </div>
                              )}
                            </div>
                            <div className="text-right">
                              <span className="font-mono font-bold text-green-700">
                                {p.moneda?.simbolo ?? ''}{Number(p.monto).toLocaleString('es-ES')}
                                {p.moneda && <span className="ml-1 font-semibold">{p.moneda.codigo}</span>}
                              </span>
                              {esMultimoneda && (
                                <p className="text-green-600/60 font-mono mt-0.5">
                                  ≈ {fmtMoneda(Number(p.monto_en_moneda_base), ventaCodigo)}
                                  <span className="ml-1 opacity-60">
                                    (1 {pagoCodigo} = {Number(p.tasa_cambio).toLocaleString('es-ES')} {nombreMoneda(ventaCodigo)})
                                  </span>
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
                            {metodosPago.map((m) => (
                              <option key={m.value} value={m.value}>
                                {m.label} · {m.moneda}
                              </option>
                            ))}
                          </select>
                        </div>
                        <div>
                          <label className="text-xs font-bold text-yeikar-neutral/60 block mb-1">
                            Moneda del pago
                          </label>
                          <SearchSelect
                            value={monedaPagoId}
                            onChange={(v) => setMonedaPagoId(Number(v))}
                            options={monedas.map((m) => ({
                              value: m.id,
                              label: `${m.codigo} — ${m.nombre}`,
                            }))}
                            placeholder="Seleccione moneda..."
                          />
                        </div>
                      </div>

                      {/* Fila 2: Monto + TRM (condicional) */}
                      <div className="grid grid-cols-1 min-[420px]:grid-cols-2 gap-3">
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
                               Pagar Restante
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
                              Tasa: 1 {monedaVenta?.codigo} = X {monedaPago?.codigo}
                            </label>
                            <input
                              type="number"
                              min="0"
                              step="0.01"
                              value={tasaNaturalInput}
                              onChange={(e) => setTasaNaturalInput(e.target.value)}
                              placeholder={`1 ${monedaVenta?.codigo} = ? ${monedaPago?.codigo}`}
                              className="w-full px-3 py-2 text-sm border border-amber-300 rounded-lg focus:outline-none focus:ring-2 focus:ring-amber-400 bg-amber-50"
                            />
                          </div>
                        )}
                      </div>

                      {/* Preview de conversión */}
                      {necesitaTRM && montoNum > 0 && tasaNatural > 0 && (
                        <div className="bg-amber-50 border border-amber-200 rounded-lg px-3 py-2">
                          <p className="text-sm font-bold text-amber-800 font-mono">
                            ≈ {montoEquivalente.toLocaleString('es-ES', { minimumFractionDigits: 2 })} {nombreMoneda(monedaVenta?.codigo)}
                          </p>
                          <p className="text-[10px] text-amber-600/70 font-mono mt-0.5">
                            equivale a 1 {nombreMoneda(monedaPago?.codigo)} = {tasaAlmacenada.toLocaleString('es-ES', { maximumFractionDigits: 6 })} {nombreMoneda(monedaVenta?.codigo)}
                          </p>
                          {monedaVenta?.codigo === 'COP' && (
                            <p className="text-[10px] text-emerald-700 font-mono mt-0.5 bg-emerald-50 rounded px-1.5 py-0.5">
                              Se registrará en COP: {Math.round(montoEquivalente / 1000) * 1000} (redondeado al millar)
                            </p>
                          )}
                          {montoEquivalente > saldoRestante + (monedaVenta?.codigo === 'COP' ? 1000 : 0.01) && (
                            <p className="text-xs text-red-600 font-bold mt-1">
                              El equivalente excede el saldo pendiente ({saldoRestante.toLocaleString('es-ES')} {nombreMoneda(monedaVenta?.codigo)})
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

                      {/* Recibo digital (opcional) */}
                      <div>
                        <label className="text-xs font-bold text-yeikar-neutral/60 block mb-1">
                          Recibo / transferencia (opcional)
                        </label>
                        <div className="flex items-center gap-2">
                          {reciboPreview && (
                            <img
                              src={reciboPreview}
                              alt="recibo"
                              className="h-12 w-12 rounded-lg object-cover border border-yeikar-secondary-light/20"
                            />
                          )}
                          <label className="flex items-center justify-center gap-1.5 h-12 px-3 rounded-lg border-2 border-dashed border-yeikar-secondary-light/20 hover:border-yeikar-primary/50 cursor-pointer text-[11px] font-bold text-yeikar-neutral/50 transition-colors flex-1">
                            <svg className="w-4 h-4" fill="none" stroke="currentColor" viewBox="0 0 24 24">
                              <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M4 16l4.586-4.586a2 2 0 012.828 0L16 16m-2-2l1.586-1.586a2 2 0 012.828 0L20 14m-6-6h.01M6 20h12a2 2 0 002-2V6a2 2 0 00-2-2H6a2 2 0 00-2 2v12a2 2 0 002 2z" />
                            </svg>
                            {reciboArchivo ? reciboArchivo.name : 'Adjuntar imagen'}
                            <input
                              type="file"
                              accept="image/jpeg,image/png,image/webp,image/heic"
                              className="hidden"
                              onChange={(e) => {
                                const f = e.target.files?.[0];
                                if (!f) return;
                                setReciboArchivo(f);
                                if (reciboPreview) URL.revokeObjectURL(reciboPreview);
                                setReciboPreview(URL.createObjectURL(f));
                              }}
                            />
                          </label>
                          {reciboArchivo && (
                            <button
                              type="button"
                              onClick={() => {
                                setReciboArchivo(null);
                                if (reciboPreview) URL.revokeObjectURL(reciboPreview);
                                setReciboPreview(null);
                              }}
                              className="text-[11px] font-bold text-red-500 hover:underline"
                            >
                              Quitar
                            </button>
                          )}
                        </div>
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
                          onClick={() => { setShowForm(false); setErrorPago(''); setTasaNaturalInput(''); }}
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

            </>
          )}
        </div>
      </div>

      {/* Visor de recibo (comprobante digital ampliado) */}
      {reciboVer && (
        <div
          className="fixed inset-0 bg-black/70 backdrop-blur-sm flex items-center justify-center p-4 z-[60]"
          onClick={() => setReciboVer(null)}
        >
          <div className="relative max-w-2xl w-full bg-white rounded-2xl overflow-hidden shadow-2xl">
            <button
              onClick={() => setReciboVer(null)}
              className="absolute top-2 right-2 bg-black/60 text-white rounded-full w-8 h-8 flex items-center justify-center text-sm hover:bg-black/80"
            >
              ×
            </button>
            <AdjuntoImagen
              adjunto={{ id: reciboVer.id, mime: reciboVer.mime }}
              alt="recibo"
              className="w-full max-h-[85vh] object-contain"
            />
          </div>
        </div>
      )}
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
          <SearchSelect
            value={monedaId}
            onChange={(v) => setMonedaId(Number(v))}
            options={monedas.map((m) => ({
              value: m.id,
              label: `${m.nombre} (${m.codigo} ${m.simbolo})`,
            }))}
            placeholder="Seleccione moneda..."
          />
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
  const toast = useToast();

  const [ventas, setVentas] = useState<Venta[]>([]);
  const [ventasLoading, setVentasLoading] = useState(false);

  const [pedidosSinFactura, setPedidosSinFactura] = useState<PedidoSinFactura[]>([]);
  const [pedidosLoading, setPedidosLoading] = useState(false);

  const [monedas, setMonedas] = useState<Moneda[]>([]);

  // Modales
  const [detalleVentaId, setDetalleVentaId] = useState<number | null>(null);
  const [pedidoParaFactura, setPedidoParaFactura] = useState<PedidoSinFactura | null>(null);

  // Filtro de estado: por defecto solo cobros pendientes (PENDIENTE/ABONADA);
  // las pagadas/canceladas quedan en su pill o en 'Todas'.
  const [filtroEstado, setFiltroEstado] = useState<string>('COBROS');

  // Búsqueda
  const [busqueda, setBusqueda] = useState('');

  const cargarVentas = useCallback(async (termino?: string) => {
    try {
      setVentasLoading(true);
      const data = await ventaService.getAll(termino ? { buscar: termino } : undefined);
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
    if (activeTab === 'pendientes') {
      cargarPedidosSinFactura();
    }
  }, [activeTab, cargarPedidosSinFactura, cargarMonedas]);

  useEffect(() => {
    if (activeTab !== 'facturas') return;
    const t = setTimeout(() => cargarVentas(busqueda.trim() || undefined), 300);
    return () => clearTimeout(t);
  }, [busqueda, activeTab, cargarVentas]);

  const ventasFiltradas = filtroEstado === 'COBROS'
    ? ventas.filter((v) => v.estado === 'PENDIENTE' || v.estado === 'ABONADA')
    : filtroEstado
      ? ventas.filter((v) => v.estado === filtroEstado)
      : ventas;

  const totalPendiente = ventas
    .filter((v) => v.estado !== 'PAGADA' && v.estado !== 'CANCELADA')
    .length;

  const facturasColumns: DataColumn<Venta>[] = [
    {
      key: 'id',
      header: '# Factura',
      render: (v) => <span className="font-mono font-bold text-yeikar-secondary">#{v.id}</span>,
      mobilePrimary: true,
    },
    {
      key: 'cliente',
      header: 'Cliente',
      render: (v) => <span className="font-semibold text-yeikar-secondary">{v.cliente?.nombre ?? `Cliente #${v.cliente_id}`}</span>,
      mobileSecondary: true,
    },
    {
      key: 'pedido',
      header: 'Pedido',
      render: (v) => <span className="font-mono text-yeikar-neutral/60">Pedido #{v.pedido_id}</span>,
      mobileLabel: 'Pedido',
    },
    {
      key: 'fecha',
      header: 'Fecha',
      render: (v) => <span className="font-mono text-yeikar-neutral/70">{new Date(v.fecha).toLocaleDateString('es-ES')}</span>,
      mobileLabel: 'Fecha',
    },
    {
      key: 'total',
      header: 'Total',
      render: (v) => <span className="font-mono font-bold text-yeikar-secondary">{Number(v.total).toLocaleString('es-ES')}</span>,
      mobileLabel: 'Total',
    },
    {
      key: 'moneda',
      header: 'Moneda',
      render: (v) => (
        <span className="font-mono text-xs font-bold bg-yeikar-tertiary/30 px-2 py-0.5 rounded-md">
          {v.moneda?.codigo ?? '—'}
        </span>
      ),
      mobileLabel: 'Moneda',
    },
    {
      key: 'estado',
      header: 'Estado',
      render: (v) => <Badge text={v.estado} className={ESTADO_VENTA_STYLE[v.estado] ?? ''} />,
      mobileHidden: true,
    },
  ];

  const renderAccionFactura = (v: Venta) => (
    <button
      id={`btn-ver-factura-${v.id}`}
      onClick={() => setDetalleVentaId(v.id)}
      className="px-3 py-2 bg-yeikar-secondary text-yeikar-tertiary hover:bg-yeikar-secondary-light rounded-lg text-xs font-bold font-headline transition-colors"
    >
      {v.estado !== 'PAGADA' && v.estado !== 'CANCELADA' ? 'Ver / Cobrar' : 'Ver Detalle'}
    </button>
  );

  const pendientesColumns: DataColumn<PedidoSinFactura>[] = [
    {
      key: 'id',
      header: '# Pedido',
      render: (p) => <span className="font-mono font-bold text-yeikar-secondary">#{p.id}</span>,
      mobilePrimary: true,
    },
    {
      key: 'cliente',
      header: 'Cliente',
      render: (p) => <span className="font-semibold text-yeikar-secondary">{p.cliente?.nombre ?? '—'}</span>,
      mobileSecondary: true,
    },
    {
      key: 'fecha',
      header: 'Fecha',
      render: (p) => <span className="font-mono text-yeikar-neutral/70">{p.fecha}</span>,
      mobileLabel: 'Fecha',
    },
    {
      key: 'estado',
      header: 'Estado',
      render: (p) => <Badge text={p.estado} className={`${ESTADO_PEDIDO_STYLE[p.estado] ?? ''} border border-transparent`} />,
      mobileHidden: true,
    },
  ];

  const renderCrearFactura = (p: PedidoSinFactura) => (
    <button
      id={`btn-crear-factura-${p.id}`}
      onClick={() => setPedidoParaFactura(p)}
      className="px-3 py-2 bg-yeikar-primary text-yeikar-neutral hover:bg-yeikar-primary/90 rounded-lg text-xs font-bold font-headline transition-colors"
    >
      Crear Factura
    </button>
  );

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
      <div className="flex border-b border-yeikar-secondary-light/10 overflow-x-auto scroll-touch whitespace-nowrap">
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
          {/* Filtro de estado + búsqueda */}
          <div className="flex flex-col sm:flex-row sm:items-center justify-between gap-3">
            <div className="flex items-center gap-3">
              <span className="text-xs font-bold text-yeikar-neutral/50 font-mono">FILTRAR:</span>
              {['COBROS', 'PAGADA', 'CANCELADA', ''].map((est) => (
                <button
                  key={est}
                  onClick={() => setFiltroEstado(est)}
                  className={`px-3 py-1 rounded-full text-xs font-bold border transition-all ${
                    filtroEstado === est
                      ? 'bg-yeikar-primary text-yeikar-neutral border-yeikar-primary'
                      : 'bg-white text-yeikar-neutral/60 border-yeikar-secondary-light/20 hover:border-yeikar-primary/40'
                  }`}
                >
                  {est === '' ? 'Todas' : est === 'COBROS' ? 'Pendientes de cobro' : est}
                </button>
              ))}
            </div>
            <SearchInput
              value={busqueda}
              onChange={(e) => setBusqueda(e.target.value)}
              placeholder="Buscar factura por cliente o estado..."
              className="w-full sm:w-72"
            />
          </div>

          <div className="bg-white rounded-2xl border border-yeikar-secondary-light/10 shadow-sm overflow-hidden">
            {ventasLoading ? (
              <Spinner />
            ) : ventasFiltradas.length === 0 ? (
              <div className="p-10 text-center text-yeikar-neutral/40 italic text-sm">
                No hay facturas para mostrar.
              </div>
            ) : (
              <ResponsiveDataTable
                columns={facturasColumns}
                rows={ventasFiltradas}
                rowKey={(v) => v.id}
                cardBadge={(v) => <Badge text={v.estado} className={ESTADO_VENTA_STYLE[v.estado] ?? ''} />}
                tableActions={renderAccionFactura}
                cardActions={renderAccionFactura}
                darkHeader
              />
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
              Todos los pedidos activos ya tienen factura emitida.
            </div>
          ) : (
            <ResponsiveDataTable
              columns={pendientesColumns}
              rows={pedidosSinFactura}
              rowKey={(p) => p.id}
              cardBadge={(p) => (
                <Badge text={p.estado} className={`${ESTADO_PEDIDO_STYLE[p.estado] ?? ''} border border-transparent`} />
              )}
              tableActions={renderCrearFactura}
              cardActions={renderCrearFactura}
              darkHeader
            />
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
