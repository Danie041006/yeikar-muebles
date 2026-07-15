import { useEffect, useState, useCallback } from 'react';
import api from '../services/api';
import {
  ventaService,
  pagoService,
  Venta,
  VentaDetalle,
  Pago,
  METODOS_PAGO,
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
  cotizacion?: { total_estimado: number };
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

  // Formulario de nuevo pago
  const [showForm, setShowForm] = useState(false);
  const [monto, setMonto] = useState('');
  const [metodoPago, setMetodoPago] = useState('EFECTIVO_USD');
  const [referencia, setReferencia] = useState('');
  const [observaciones, setObservaciones] = useState('');
  const [submitting, setSubmitting] = useState(false);
  const [errorPago, setErrorPago] = useState('');

  const cargar = useCallback(async () => {
    try {
      setLoading(true);
      const data = await ventaService.getById(ventaId);
      setDetalle(data);
    } finally {
      setLoading(false);
    }
  }, [ventaId]);

  useEffect(() => {
    cargar();
  }, [cargar]);

  const handlePago = async () => {
    if (!detalle) return;
    setErrorPago('');
    if (!monto || isNaN(parseFloat(monto)) || parseFloat(monto) <= 0) {
      setErrorPago('Ingresa un monto válido mayor a 0.');
      return;
    }
    try {
      setSubmitting(true);
      await pagoService.registrar({
        venta_id: detalle.id,
        moneda_id: detalle.moneda_id,
        fecha: new Date().toISOString(),
        monto: parseFloat(monto),
        metodo_pago: metodoPago,
        referencia: referencia || undefined,
        observaciones: observaciones || undefined,
      });
      setMonto('');
      setReferencia('');
      setObservaciones('');
      setShowForm(false);
      await cargar();
      onPagoRegistrado();
    } catch (err: any) {
      setErrorPago(err?.response?.data?.detail || 'Error al registrar el pago.');
    } finally {
      setSubmitting(false);
    }
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
              Factura #{detalle?.id ?? '...'}
            </h3>
            {detalle && (
              <p className="text-xs text-yeikar-tertiary/60 font-mono mt-0.5">
                {detalle.cliente?.nombre} · {detalle.moneda?.codigo}
              </p>
            )}
          </div>
          <button
            onClick={onClose}
            className="text-yeikar-tertiary/50 hover:text-yeikar-tertiary transition-colors"
          >
            <svg className="w-6 h-6" fill="none" stroke="currentColor" viewBox="0 0 24 24">
              <path strokeLinecap="round" strokeLinejoin="round" strokeWidth="2" d="M6 18L18 6M6 6l12 12" />
            </svg>
          </button>
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
                      return (
                        <div
                          key={p.id}
                          className="flex justify-between items-center text-xs bg-green-50 border border-green-100 rounded-lg px-3 py-2"
                        >
                          <div>
                            <span className="font-bold text-green-700">{metodoLabel}</span>
                            {p.referencia && (
                              <span className="ml-2 text-green-600/70 font-mono">#{p.referencia}</span>
                            )}
                            <p className="text-green-600/60 font-mono mt-0.5">
                              {new Date(p.fecha).toLocaleDateString('es-ES')}
                            </p>
                          </div>
                          <span className="font-mono font-bold text-green-700">
                            {detalle.moneda?.simbolo}{Number(p.monto).toLocaleString('es-ES')}
                          </span>
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
                      className="w-full py-2.5 bg-yeikar-primary text-white font-bold font-headline rounded-xl hover:bg-yeikar-primary/90 transition-all text-sm"
                    >
                      + Registrar Cobro
                    </button>
                  ) : (
                    <div className="border border-yeikar-primary/20 rounded-xl p-4 bg-yeikar-primary/5 space-y-3">
                      <h5 className="font-headline font-bold text-sm text-yeikar-secondary">
                        Nuevo Cobro
                      </h5>

                      <div className="grid grid-cols-2 gap-3">
                        <div>
                          <label className="text-xs font-bold text-yeikar-neutral/60 block mb-1">
                            Monto ({detalle.moneda?.codigo})
                          </label>
                          <input
                            type="number"
                            min="0"
                            step="0.01"
                            value={monto}
                            onChange={(e) => setMonto(e.target.value)}
                            placeholder="0.00"
                            className="w-full px-3 py-2 text-sm border border-yeikar-secondary-light/20 rounded-lg focus:outline-none focus:ring-2 focus:ring-yeikar-primary bg-white"
                          />
                        </div>
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
                      </div>

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
                          onClick={() => { setShowForm(false); setErrorPago(''); }}
                          className="flex-1 py-2 text-sm font-bold text-yeikar-neutral/60 border border-yeikar-secondary-light/20 rounded-xl hover:bg-yeikar-tertiary/20 transition-all"
                        >
                          Cancelar
                        </button>
                        <button
                          onClick={handlePago}
                          disabled={submitting}
                          className="flex-1 py-2 text-sm font-bold bg-yeikar-primary text-white rounded-xl hover:bg-yeikar-primary/90 transition-all disabled:opacity-50"
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
  const [monedaId, setMonedaId] = useState<number>(monedas[0]?.id ?? 0);
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
            className="flex-1 py-2.5 text-sm font-bold bg-yeikar-primary text-white rounded-xl hover:bg-yeikar-primary/90 transition-all disabled:opacity-50"
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
            <span className="bg-yeikar-primary text-white text-xs font-bold rounded-full w-5 h-5 flex items-center justify-center">
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
                    ? 'bg-yeikar-primary text-white border-yeikar-primary'
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
                          className="px-3 py-1.5 bg-yeikar-primary text-white hover:bg-yeikar-primary/90 rounded-lg text-xs font-bold font-headline transition-colors"
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
