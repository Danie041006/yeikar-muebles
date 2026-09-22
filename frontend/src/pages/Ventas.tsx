import { useEffect, useMemo, useState, useCallback, useRef, type ReactNode } from 'react';
import api from '../services/api';
import { SearchInput, SearchSelect, ResponsiveDataTable, Button as UiButton, EmptyState, type DataColumn } from '../components/ui';
import {
  ventaService,
  pagoService,
  descuentoService,
  Venta,
  VentaDetalle,
  DetalleVenta,
  CuentaPorCobrar,
  Pago,
  METODOS_PAGO,
  cargarMetodosPago,
  labelMetodoPago,
  type PagoCreate,
  type DescuentoCreate,
  type MetodoPagoOption,
} from '../services/ventaService';
import { formatCurrency, nombreMoneda, fmtMoneda, tasaNaturalAAlmacenada, convertirConTasaNatural, resolverParMonedas, convertirMonedaHumana, calcularTasaAlmacenadaPago, redondearCobroEntero, extractErrorMessage } from '../utils/format';
import { subirAdjunto, TIPO_ADJUNTO } from '../services/adjuntosService';
import { fmtFechaVE } from '../utils/fechas';
import AdjuntoImagen from '../components/AdjuntoImagen';

// ─── Tipos locales ────────────────────────────────────────────────────────────
// ─── Badges helpers ───────────────────────────────────────────────────────────
const ESTADO_VENTA_STYLE: Record<string, string> = {
  PENDIENTE: 'bg-amber-100 text-amber-800 border-amber-200',
  ABONADA: 'bg-blue-100 text-blue-800 border-blue-200',
  PAGADA: 'bg-green-100 text-green-800 border-green-200',
  CANCELADA: 'bg-red-100 text-red-800 border-red-200',
};

function Badge({ text, className }: { text: string; className: string }) {
  return (
    <span className={`px-2.5 py-0.5 rounded-full text-xs font-bold border ${className}`}>
      {text}
    </span>
  );
}

// El catálogo manda para el nombre; si no hay producto ni material, el ítem
// es a medida y se muestra su descripción guardada (nunca "Producto #null").
function nombreItemVenta(d: DetalleVenta): string {
  if (d.tipo_item === 'INSUMO') return d.material?.nombre ?? d.descripcion_especifica ?? 'Material';
  return d.producto?.nombre ?? d.descripcion_especifica ?? 'Ítem personalizado';
}

function esItemAMedida(d: DetalleVenta): boolean {
  return !d.producto && !d.material;
}

function Spinner() {
  return (
    <div className="flex flex-col items-center justify-center py-20 gap-3">
      <div className="w-10 h-10 border-4 border-yeikar-primary border-t-transparent rounded-full animate-spin" />
      <p className="text-xs font-mono text-yeikar-neutral/50">Cargando...</p>
    </div>
  );
}

// Los pendientes de cobro se tocan decenas de veces al día: cada uno es un
// botón grande con su saldo a la vista, y el detalle (deuda + pedido) vive dentro.
interface CobroPendiente {
  venta: Venta;
  total: number;
  pagado: number;
  descontado: number;
  saldo: number;
  codigo: string;
}

function progresoCobro(total: number, pagado: number): number {
  if (!total || total <= 0) return 0;
  return Math.min(100, Math.max(0, (pagado / total) * 100));
}

function ChipPedido({ venta }: { venta: Venta }) {
  const entregado = venta.pedido_estado === 'ENTREGADO';
  return (
    <span
      className={`inline-flex items-center gap-1 rounded-full border px-2 py-0.5 font-mono text-[11px] font-bold ${
        entregado
          ? 'border-emerald-200 bg-emerald-50 text-emerald-700'
          : 'border-yeikar-secondary-light/20 bg-yeikar-tertiary/25 text-yeikar-secondary'
      }`}
    >
      Pedido #{venta.pedido_id} · {entregado ? 'Entregado' : 'En proceso'}
    </span>
  );
}

function ResumenCobro({
  cobro,
  buttonId,
  panelId,
  abierta,
  onToggle,
}: {
  cobro: CobroPendiente;
  buttonId: string;
  panelId: string;
  abierta: boolean;
  onToggle: () => void;
}) {
  const { venta, total, pagado, saldo, codigo } = cobro;
  const entregado = venta.pedido_estado === 'ENTREGADO';
  const progreso = progresoCobro(total, pagado);

  return (
    <button
      type="button"
      id={buttonId}
      aria-expanded={abierta}
      aria-controls={panelId}
      onClick={onToggle}
      className={`block w-full p-4 text-left sm:p-5 ${
        entregado ? 'bg-gradient-to-br from-amber-50/80 via-white to-white' : 'bg-white'
      }`}
    >
      <span className="flex items-start justify-between gap-3">
        <span className="min-w-0">
          <span className="block truncate font-headline text-[15px] font-black tracking-tight text-yeikar-neutral">
            {venta.cliente?.nombre ?? `Cliente #${venta.cliente_id}`}
          </span>
          <span className="mt-1.5 flex flex-wrap items-center gap-1.5">
            <Badge text={venta.estado} className={ESTADO_VENTA_STYLE[venta.estado] ?? ''} />
            <ChipPedido venta={venta} />
          </span>
        </span>
        <svg
          aria-hidden
          className={`mt-1 h-5 w-5 shrink-0 text-yeikar-neutral/40 transition-transform ${abierta ? 'rotate-180' : ''}`}
          fill="none"
          stroke="currentColor"
          viewBox="0 0 24 24"
        >
          <path strokeLinecap="round" strokeLinejoin="round" strokeWidth="2" d="M19 9l-7 7-7-7" />
        </svg>
      </span>

      <span className="mt-3 block">
        <span className="text-[11px] font-bold uppercase tracking-widest text-yeikar-neutral/45">
          Saldo por cobrar
        </span>
        <span className="mt-0.5 flex flex-wrap items-baseline gap-x-2">
          <span className="font-headline text-2xl font-black tracking-tight text-yeikar-neutral">
            {formatCurrency(saldo, codigo)}
          </span>
          <span className="font-headline text-2xl font-black tracking-tight text-yeikar-neutral">
            {nombreMoneda(codigo).toLowerCase()}
          </span>
        </span>
        <span className="mt-0.5 block font-mono text-xs text-yeikar-neutral/55">
          Pagado {formatCurrency(pagado, codigo)} de {formatCurrency(total, codigo)} · Venta #{venta.id}
        </span>
      </span>

      <span className="mt-3 block h-2 overflow-hidden rounded-full bg-yeikar-tertiary/40">
        <span
          className="block h-full rounded-full bg-gradient-to-r from-yeikar-primary via-amber-400 to-emerald-500 transition-all"
          style={{ width: `${progreso}%` }}
        />
      </span>

      <span className="mt-2 flex items-center justify-between text-[11px] font-bold text-yeikar-neutral/45">
        <span>{fmtFechaVE(venta.fecha)}</span>
        <span>{abierta ? 'Ocultar detalle' : 'Toca para ver deuda y pedido'}</span>
      </span>
    </button>
  );
}

function BloqueDeuda({
  total,
  pagado,
  descontado,
  saldo,
  codigo,
}: {
  total: number;
  pagado: number;
  descontado: number;
  saldo: number;
  codigo: string;
}) {
  return (
    <div className="rounded-xl bg-white/90 p-3">
      <p className="font-headline text-xs font-black uppercase tracking-widest text-yeikar-secondary">
        Lo que se debe
      </p>
      <dl className="mt-2 space-y-1 font-mono text-xs text-yeikar-neutral/70">
        <div className="flex justify-between"><dt>Total</dt><dd className="font-bold">{formatCurrency(total, codigo)}</dd></div>
        <div className="flex justify-between"><dt>Pagado</dt><dd className="font-bold text-emerald-700">{formatCurrency(pagado, codigo)}</dd></div>
        {descontado > 0 && (
          <div className="flex justify-between"><dt>Descontado</dt><dd className="font-bold text-amber-700">−{formatCurrency(descontado, codigo)}</dd></div>
        )}
        <div className="flex justify-between border-t border-yeikar-secondary-light/10 pt-1"><dt>Saldo</dt><dd className="font-black text-yeikar-neutral">{formatCurrency(saldo, codigo)}</dd></div>
      </dl>
    </div>
  );
}

function BloquePedido({ venta }: { venta: Venta }) {
  return (
    <div className="rounded-xl bg-white/90 p-3">
      <p className="font-headline text-xs font-black uppercase tracking-widest text-yeikar-secondary">
        Pedido
      </p>
      <p className="mt-2 font-mono text-xs font-bold text-yeikar-secondary">Pedido #{venta.pedido_id}</p>
      <p className="mt-1 font-mono text-xs text-yeikar-neutral/60">
        Estado: {venta.pedido_estado === 'ENTREGADO' ? 'Entregado al cliente' : 'Todavía en proceso'}
      </p>
      <p className="mt-1 font-mono text-xs text-yeikar-neutral/60">
        Venta #{venta.id} · {fmtFechaVE(venta.fecha)}
      </p>
    </div>
  );
}

function PanelCobro({
  cobro,
  buttonId,
  onCobrar,
}: {
  cobro: CobroPendiente;
  buttonId: string;
  onCobrar: () => void;
}) {
  const { venta, total, pagado, descontado, saldo, codigo } = cobro;
  return (
    <div
      id={`panel-cobro-${venta.id}`}
      role="region"
      aria-labelledby={buttonId}
      className="border-t border-yeikar-secondary-light/10 bg-yeikar-tertiary/15 p-4 sm:p-5"
    >
      <div className="grid gap-3 sm:grid-cols-2">
        <BloqueDeuda total={total} pagado={pagado} descontado={descontado} saldo={saldo} codigo={codigo} />
        <BloquePedido venta={venta} />
      </div>
      <div className="mt-3 flex flex-col gap-2 sm:flex-row sm:items-center sm:justify-between">
        <p className="text-[11px] text-yeikar-neutral/50">El cobro se registra en el detalle, con recibo opcional.</p>
        <UiButton size="sm" onClick={onCobrar}>Cobrar ahora</UiButton>
      </div>
    </div>
  );
}

function TarjetaCobro({
  cobro,
  abierta,
  onToggle,
  onCobrar,
}: {
  cobro: CobroPendiente;
  abierta: boolean;
  onToggle: () => void;
  onCobrar: () => void;
}) {
  const entregado = cobro.venta.pedido_estado === 'ENTREGADO';
  const buttonId = `btn-cobro-${cobro.venta.id}`;
  const panelId = `panel-cobro-${cobro.venta.id}`;

  return (
    <div
      className={`relative overflow-hidden rounded-2xl border bg-white shadow-card transition-all duration-200 hover:-translate-y-0.5 hover:shadow-lift ${
        abierta ? 'border-yeikar-primary/50 ring-2 ring-yeikar-primary/15' : 'border-yeikar-secondary-light/15'
      } ${entregado ? 'border-l-4 border-l-amber-400' : 'border-l-4 border-l-yeikar-secondary/50'}`}
    >
      <ResumenCobro cobro={cobro} buttonId={buttonId} panelId={panelId} abierta={abierta} onToggle={onToggle} />
      {abierta && <PanelCobro cobro={cobro} buttonId={buttonId} onCobrar={onCobrar} />}
    </div>
  );
}

function SeccionCobros({
  titulo,
  descripcion,
  icono,
  tono,
  hayPendientes,
  vacio,
  loading,
  cobros,
  abiertoId,
  onToggle,
  onCobrar,
}: {
  titulo: string;
  descripcion: string;
  icono: ReactNode;
  tono: 'urgente' | 'proceso';
  hayPendientes: boolean;
  vacio: string;
  loading: boolean;
  cobros: CobroPendiente[];
  abiertoId: number | null;
  onToggle: (id: number) => void;
  onCobrar: (id: number) => void;
}) {
  return (
    <section>
      <EncabezadoSeccion
        titulo={titulo}
        descripcion={descripcion}
        icono={icono}
        tono={tono}
        hayPendientes={hayPendientes}
        conteo={cobros.length}
      />
      {loading ? (
        <Spinner />
      ) : cobros.length === 0 ? (
        <EmptyState title="Sin cobros aquí" description={vacio} compact />
      ) : (
        <div className="grid gap-3 md:grid-cols-2">
          {cobros.map((cobro) => (
            <TarjetaCobro
              key={cobro.venta.id}
              cobro={cobro}
              abierta={abiertoId === cobro.venta.id}
              onToggle={() => onToggle(cobro.venta.id)}
              onCobrar={() => onCobrar(cobro.venta.id)}
            />
          ))}
        </div>
      )}
    </section>
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
  // ── Formulario de descuento (rebaja sin movimiento de caja) ───────────────
  const [showDescForm, setShowDescForm] = useState(false);
  const [descMonedaId, setDescMonedaId] = useState<number | null>(null);
  const [descMonto, setDescMonto] = useState('');
  const [descTasaInput, setDescTasaInput] = useState('');
  const [descMotivo, setDescMotivo] = useState('');
  const [descSubmitting, setDescSubmitting] = useState(false);
  const [descError, setDescError] = useState('');
  const [anulandoDescId, setAnulandoDescId] = useState<number | null>(null);
  const [monedas, setMonedas] = useState<{ id: number; codigo: string; nombre: string; simbolo: string }[]>([]);  const cuerpoRef = useRef<HTMLDivElement>(null);
  // Métodos de pago: cuentas reales (metodo_caja) con fallback al estático.
  const [metodosPago, setMetodosPago] = useState<MetodoPagoOption[]>(METODOS_PAGO.map((m) => ({ ...m })));

  // Al abrir cualquier formulario, la vista enfocada arranca arriba
  useEffect(() => {
    if (showForm || showDescForm) cuerpoRef.current?.scrollTo({ top: 0 });
  }, [showForm, showDescForm]);

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
  const monedaPago = monedas.find(m => m.id === monedaPagoId);
  const monedaVenta = monedas.find(m => m.id === monedaVentaId);
  const parPago = resolverParMonedas(monedaVenta?.codigo, monedaPago?.codigo);
  const tasaHumana = parseFloat(tasaNaturalInput) || 0;
  const tasaAlmacenada = tasaHumana > 0
    ? calcularTasaAlmacenadaPago(monedaPago?.codigo, monedaVenta?.codigo, tasaHumana)
    : 0;
  const montoNum = parseFloat(monto) || 0;
  const montoEquivalente = necesitaTRM && tasaHumana > 0
    ? redondearCobroEntero(convertirMonedaHumana(montoNum, monedaPago?.codigo, monedaVenta?.codigo, tasaHumana))
    : montoNum;
  const saldoRestante = detalle ? Number(detalle.saldo_pendiente) : 0;

  // ── Descuento: misma conversión multimoneda que el cobro ──────────────────
  const necesitaTRMDesc = descMonedaId !== null && monedaVentaId !== null && descMonedaId !== monedaVentaId;
  const monedaDesc = monedas.find(m => m.id === descMonedaId);
  const parDesc = resolverParMonedas(monedaVenta?.codigo, monedaDesc?.codigo);
  const tasaHumanaDesc = parseFloat(descTasaInput) || 0;
  const tasaAlmDesc = tasaHumanaDesc > 0
    ? calcularTasaAlmacenadaPago(monedaDesc?.codigo, monedaVenta?.codigo, tasaHumanaDesc)
    : 0;
  const descMontoNum = parseFloat(descMonto) || 0;
  const descEquivalente = necesitaTRMDesc && tasaHumanaDesc > 0
    ? redondearCobroEntero(convertirMonedaHumana(descMontoNum, monedaDesc?.codigo, monedaVenta?.codigo, tasaHumanaDesc))
    : descMontoNum;

  const abrirDescForm = () => {
    setShowDescForm(true);
    setShowForm(false);
    setDescError('');
    // Por defecto el descuento se expresa en la moneda de la venta.
    if (descMonedaId === null && detalle) setDescMonedaId(detalle.moneda_id);
  };

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
    if (necesitaTRM && (!tasaNaturalInput || tasaHumana <= 0)) {
      setErrorPago(`La moneda del pago difiere de la de la venta. Ingresa la tasa de cambio (${parPago.label}).`);
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
        ...(necesitaTRM ? { tasa_cambio: tasaAlmacenada } : {}),
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
      setErrorPago(extractErrorMessage(err, 'Error al registrar el pago.'));
    } finally {
      setSubmitting(false);
    }
  };

  const handleSetRestante = () => {
    if (!detalle) return;
    if (necesitaTRM) {
      if (tasaHumana <= 0) {
        setErrorPago(`Ingresa primero la tasa de cambio (${parPago.label}) para calcular el monto restante.`);
        return;
      }
      const montoCalc = redondearCobroEntero(convertirMonedaHumana(saldoRestante, monedaVenta?.codigo, monedaPago?.codigo, tasaHumana));
      setMonto(montoCalc.toFixed(2));
    } else {
      setMonto(saldoRestante.toString());
    }
    setErrorPago('');
  };

  const handleDescuento = async () => {
    if (!detalle) return;
    setDescError('');
    if (!descMonto || isNaN(parseFloat(descMonto)) || parseFloat(descMonto) <= 0) {
      setDescError('Ingresa un monto válido mayor a 0.');
      return;
    }
    if (!descMonedaId) {
      setDescError('Selecciona la moneda del descuento.');
      return;
    }
    if (necesitaTRMDesc && (!descTasaInput || tasaHumanaDesc <= 0)) {
      setDescError(`La moneda del descuento difiere de la de la venta. Ingresa la tasa de cambio (${parDesc.label}).`);
      return;
    }
    try {
      setDescSubmitting(true);
      const payload: DescuentoCreate = {
        venta_id: detalle.id,
        moneda_id: descMonedaId,
        fecha: new Date().toISOString(),
        monto: parseFloat(descMonto),
        motivo: descMotivo || undefined,
        ...(necesitaTRMDesc ? { tasa_cambio: tasaAlmDesc } : {}),
      };
      await descuentoService.registrar(payload);
      setDescMonto('');
      setDescMotivo('');
      setDescTasaInput('');
      setShowDescForm(false);
      await cargar();
      onPagoRegistrado();
    } catch (err: any) {
      setDescError(extractErrorMessage(err, 'Error al registrar el descuento.'));
    } finally {
      setDescSubmitting(false);
    }
  };

  const handleSetDescRestante = () => {
    if (!detalle) return;
    if (necesitaTRMDesc) {
      if (tasaHumanaDesc <= 0) {
        setDescError(`Ingresa primero la tasa de cambio (${parDesc.label}) para calcular el monto restante.`);
        return;
      }
      const montoCalc = redondearCobroEntero(convertirMonedaHumana(saldoRestante, monedaVenta?.codigo, monedaDesc?.codigo, tasaHumanaDesc));
      setDescMonto(montoCalc.toFixed(2));
    } else {
      setDescMonto(saldoRestante.toString());
    }
    setDescError('');
  };

  const handleAnularDescuento = async (id: number) => {
    if (!window.confirm('¿Anular este descuento? El saldo pendiente volverá a subir.')) return;
    try {
      setAnulandoDescId(id);
      await descuentoService.anular(id);
      await cargar();
      onPagoRegistrado();
    } catch (err: any) {
      setDescError(extractErrorMessage(err, 'Error al anular el descuento.'));
    } finally {
      setAnulandoDescId(null);
    }
  };

  const porcentajePagado = detalle
    ? Math.min(100, (detalle.total_pagado / detalle.total) * 100)
    : 0;
  const tasaVenta = Number(detalle?.tasa_cambio ?? 0);
  // El "≈ COP" solo aporta cuando hay conversión real: moneda extranjera con
  // TRM mayor a 1 y base registrada. Así no sale "≈ $ 0" en históricas 1:1.
  const muestraEquivalente = (base: number) =>
    !!detalle && detalle.moneda?.codigo !== 'COP' && tasaVenta > 1 && Number.isFinite(base) && base > 0;

  return (
    <div className="fixed inset-0 bg-black/50 backdrop-blur-sm flex items-center justify-center p-4 z-50">
      <div className="bg-white rounded-2xl border border-yeikar-secondary-light/10 shadow-2xl w-full max-w-2xl overflow-hidden flex flex-col max-h-[90vh]">
        {/* Header */}
        <div className="bg-yeikar-neutral p-5 text-yeikar-tertiary">
          <div className="flex items-start justify-between gap-3">
            <div className="min-w-0">
              <p className="font-mono text-[11px] font-bold uppercase tracking-[0.2em] text-yeikar-primary">
                Estado de cobro
              </p>
              <h3 className="mt-0.5 font-headline text-xl font-black tracking-tight text-yeikar-tertiary">
                Venta #{detalle?.id ?? '...'}
              </h3>
              {detalle && (
                <p className="mt-0.5 truncate text-xs text-yeikar-tertiary/70">
                  {detalle.cliente?.nombre} · {fmtFechaVE(detalle.fecha)}
                </p>
              )}
            </div>
            <div className="flex shrink-0 items-center gap-2">
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
                aria-label="Cerrar"
              >
                <svg className="w-6 h-6" fill="none" stroke="currentColor" viewBox="0 0 24 24">
                  <path strokeLinecap="round" strokeLinejoin="round" strokeWidth="2" d="M6 18L18 6M6 6l12 12" />
                </svg>
              </button>
            </div>
          </div>
          {detalle && (
            <div className="mt-3 flex flex-wrap items-center gap-1.5">
              <Badge text={detalle.estado} className={ESTADO_VENTA_STYLE[detalle.estado] ?? ''} />
              {detalle.pedido_id && (
                <span className="inline-flex items-center rounded-full border border-yeikar-tertiary/20 px-2.5 py-0.5 font-mono text-[11px] font-bold text-yeikar-tertiary/80">
                  Pedido #{detalle.pedido_id}
                  {detalle.pedido_estado === 'ENTREGADO' ? ' · Entregado' : ' · En proceso'}
                </span>
              )}
            </div>
          )}
        </div>

        {/* Body */}
        <div ref={cuerpoRef} className="overflow-y-auto flex-1 p-5 space-y-5">
          {loading || !detalle ? (
            <Spinner />
          ) : (
            <>
              {showForm || showDescForm ? (
                /* Modo formulario: resumen compacto (sin contenido detrás que se pise) */
                <div className="flex items-center justify-between gap-3 rounded-2xl border border-amber-200 bg-amber-50 px-4 py-3">
                  <div className="min-w-0">
                    <p className="font-mono text-[10px] font-bold uppercase tracking-[0.2em] text-amber-700">
                      Saldo pendiente
                    </p>
                    <p className="mt-0.5 font-headline text-2xl font-black tracking-tight text-yeikar-neutral">
                      {detalle.moneda?.simbolo}{Number(detalle.saldo_pendiente).toLocaleString('es-ES')}
                      <span className="ml-1.5 align-middle font-body text-xs font-semibold tracking-normal text-yeikar-neutral/50">
                        {nombreMoneda(detalle.moneda?.codigo).toLowerCase()}
                      </span>
                      {detalle.moneda && (
                        <span className="ml-2 rounded bg-amber-100 px-1.5 py-0.5 align-middle font-mono text-[10px] font-black text-amber-800">
                          {detalle.moneda.codigo}
                        </span>
                      )}
                    </p>
                  </div>
                  <div className="shrink-0 text-right font-mono text-[11px] leading-relaxed text-yeikar-neutral/55">
                    <p>
                      Pagado <span className="font-bold text-emerald-700">{detalle.moneda?.simbolo}{Number(detalle.total_pagado).toLocaleString('es-ES')}</span>
                      {' '}de {detalle.moneda?.simbolo}{Number(detalle.total).toLocaleString('es-ES')}
                    </p>
                    <p className="font-bold text-yeikar-neutral/70">
                      {detalle.pagos.length} cobro{detalle.pagos.length !== 1 ? 's' : ''}
                    </p>
                  </div>
                </div>
              ) : (
              <>
              {/* Héroe del saldo */}
              <div className="overflow-hidden rounded-2xl border border-amber-200 bg-gradient-to-br from-amber-50 via-white to-white">
                <div className="p-4 sm:p-5">
                  <div className="flex items-center justify-between">
                    <p className="font-mono text-[11px] font-bold uppercase tracking-[0.2em] text-amber-700">
                      Saldo pendiente
                    </p>
                    {detalle.moneda && (
                      <span className="rounded-md bg-amber-100 px-2 py-0.5 font-mono text-[11px] font-black text-amber-800">
                        {detalle.moneda.codigo}
                      </span>
                    )}
                  </div>
                  <p className="mt-1 font-headline text-4xl font-black tracking-tight text-yeikar-neutral">
                    {detalle.moneda?.simbolo}{Number(detalle.saldo_pendiente).toLocaleString('es-ES')}
                    <span className="ml-2 align-middle font-body text-sm font-semibold tracking-normal text-yeikar-neutral/50">
                      {nombreMoneda(detalle.moneda?.codigo).toLowerCase()}
                    </span>
                  </p>
                  <p className="mt-1 font-mono text-xs text-yeikar-neutral/55">
                    Pagado {detalle.moneda?.simbolo}{Number(detalle.total_pagado).toLocaleString('es-ES')} de {detalle.moneda?.simbolo}{Number(detalle.total).toLocaleString('es-ES')}
                    {Number(detalle.total_descontado ?? 0) > 0 && (
                      <span className="text-amber-700">
                        {' '}· Descontado {detalle.moneda?.simbolo}{Number(detalle.total_descontado).toLocaleString('es-ES')}
                      </span>
                    )}
                  </p>
                  {muestraEquivalente(Number(detalle.saldo_pendiente) * tasaVenta) && (
                    <p className="mt-0.5 font-mono text-[11px] text-amber-700/70">
                      ≈ {formatCurrency(Number(detalle.saldo_pendiente) * tasaVenta, 'COP')}
                    </p>
                  )}
                  <div className="mt-3 h-2.5 overflow-hidden rounded-full bg-amber-100">
                    <div
                      className="h-full rounded-full bg-gradient-to-r from-yeikar-primary via-amber-400 to-emerald-500 transition-all duration-500"
                      style={{ width: `${porcentajePagado}%` }}
                    />
                  </div>
                  <div className="mt-1 flex justify-between font-mono text-[11px] text-yeikar-neutral/50">
                    <span>Progreso de cobro</span>
                    <span className="font-bold">{porcentajePagado.toFixed(1)}%</span>
                  </div>
                </div>
                <div className="flex items-center justify-between border-t border-amber-100 bg-white/60 px-4 py-2.5 sm:px-5">
                  <span className="font-mono text-xs text-yeikar-neutral/55">
                    Total {detalle.moneda?.simbolo}{Number(detalle.total).toLocaleString('es-ES')}
                    {muestraEquivalente(Number(detalle.total_en_moneda_base)) && (
                      <> · ≈ {formatCurrency(Number(detalle.total_en_moneda_base), 'COP')}</>
                    )}
                  </span>
                  <span className="font-mono text-xs font-bold text-emerald-700">
                    {detalle.pagos.length} cobro{detalle.pagos.length !== 1 ? 's' : ''}
                  </span>
                </div>
              </div>

              {/* Qué incluye la venta */}
              <div>
                <h4 className="font-headline font-bold text-sm text-yeikar-secondary mb-2 uppercase tracking-wider">
                  Qué incluye la venta ({detalle.detalles.length})
                </h4>
                <div className="overflow-hidden rounded-2xl border border-yeikar-secondary-light/10">
                  {detalle.detalles.map((d, i) => (
                    <div
                      key={d.id}
                      className={`flex items-start justify-between gap-3 px-3.5 py-3 text-sm ${i % 2 ? 'bg-white' : 'bg-yeikar-tertiary/10'}`}
                    >
                      <span className="min-w-0">
                        <span className="block font-medium leading-snug text-yeikar-secondary">
                          {nombreItemVenta(d)}
                        </span>
                        <span className="mt-1 flex flex-wrap gap-1">
                          {d.tipo_item === 'INSUMO' && (
                            <span className="text-[9px] font-bold uppercase px-1.5 py-0.5 rounded bg-emerald-50 text-emerald-700 border border-emerald-200">Insumo</span>
                          )}
                          {d.tipo_item === 'REVENTA' && !esItemAMedida(d) && (
                            <span className="text-[9px] font-bold uppercase px-1.5 py-0.5 rounded bg-sky-50 text-sky-700 border border-sky-200">Reventa</span>
                          )}
                          {esItemAMedida(d) && (
                            <span className="text-[9px] font-bold uppercase px-1.5 py-0.5 rounded bg-amber-50 text-amber-700 border border-amber-200">A medida</span>
                          )}
                        </span>
                      </span>
                      <span className="shrink-0 text-right">
                        <span className="block font-mono text-xs text-yeikar-neutral/60">
                          {d.cantidad} × {detalle.moneda?.simbolo}{Number(d.precio).toLocaleString('es-ES')}
                        </span>
                        <span className="block font-mono text-sm font-black text-yeikar-secondary">
                          {detalle.moneda?.simbolo}{(Number(d.cantidad) * Number(d.precio)).toLocaleString('es-ES')}
                        </span>
                      </span>
                    </div>
                  ))}
                </div>
              </div>

              {/* Cobros */}
              <div>
                <h4 className="font-headline font-bold text-sm text-yeikar-secondary mb-2 uppercase tracking-wider">
                  Cobros ({detalle.pagos.length})
                </h4>
                {detalle.pagos.length === 0 ? (
                  <div className="rounded-2xl border border-dashed border-yeikar-secondary-light/25 bg-yeikar-tertiary/10 p-6 text-center">
                    <p className="text-sm font-bold text-yeikar-secondary">Sin cobros todavía</p>
                    <p className="mt-0.5 text-xs text-yeikar-neutral/50">
                      Registra el primero con el botón dorado de abajo.
                    </p>
                  </div>
                ) : (
                  <div className="overflow-hidden rounded-2xl border border-yeikar-secondary-light/10">
                    {detalle.pagos.map((p: Pago, i: number) => {
                      const metodoLabel = labelMetodoPago(metodosPago, p.metodo_pago);
                      const esMultimoneda = p.tasa_cambio && p.tasa_cambio !== 1;
                      const pagoCodigo = p.moneda?.codigo ?? '?';
                      const ventaCodigo = detalle.moneda?.codigo ?? '?';
                      return (
                        <div
                          key={p.id}
                          className={`flex items-start justify-between gap-3 px-3.5 py-3 text-sm ${i % 2 ? 'bg-white' : 'bg-yeikar-tertiary/10'}`}
                        >
                          <span className="min-w-0">
                            <span className="flex items-center gap-1.5 font-medium leading-snug text-yeikar-secondary">
                              <span className="h-2 w-2 shrink-0 rounded-full bg-emerald-500" />
                              {metodoLabel}
                              {p.referencia && (
                                <span className="font-mono text-[11px] text-yeikar-neutral/50">#{p.referencia}</span>
                              )}
                            </span>
                            <span className="mt-0.5 block font-mono text-[11px] text-yeikar-neutral/50">
                              {fmtFechaVE(p.fecha)}
                            </span>
                            {/* Recibos del cobro (comprobantes digitales) */}
                            {p.recibos && p.recibos.length > 0 && (
                              <span className="mt-1.5 flex gap-1.5">
                                {p.recibos.map((r) => (
                                  <AdjuntoImagen
                                    key={r.id}
                                    adjunto={r}
                                    alt="recibo"
                                    className="h-10 w-10 rounded-lg border border-yeikar-secondary-light/20 hover:border-yeikar-primary/50 transition-colors"
                                    onClick={() => setReciboVer({ id: r.id, mime: r.mime })}
                                  />
                                ))}
                              </span>
                            )}
                            {esMultimoneda && (
                              <span className="mt-0.5 block font-mono text-[11px] text-yeikar-neutral/50">
                                ≈ {fmtMoneda(Number(p.monto_en_moneda_base), ventaCodigo)}
                                <span className="opacity-70">
                                  {' '}(1 {pagoCodigo} = {Number(p.tasa_cambio).toLocaleString('es-ES')} {nombreMoneda(ventaCodigo)})
                                </span>
                              </span>
                            )}
                          </span>
                          <span className="shrink-0 text-right">
                            <span className="block font-mono text-sm font-black text-yeikar-secondary">
                              {p.moneda?.simbolo ?? ''}{Number(p.monto).toLocaleString('es-ES')}
                            </span>
                            {p.moneda && (
                              <span className="mt-1 inline-block rounded bg-emerald-100/70 px-1.5 py-0.5 font-mono text-[10px] font-black text-emerald-800">
                                {p.moneda.codigo}
                              </span>
                            )}
                          </span>
                        </div>
                      );
                    })}
                  </div>
                )}
              </div>
              {/* Descuentos otorgados al cobrar (no mueven caja) */}
              {(detalle.descuentos ?? []).length > 0 && (
                <div>
                  <h4 className="font-headline font-bold text-sm text-yeikar-secondary mb-2 uppercase tracking-wider">
                    Descuentos ({(detalle.descuentos ?? []).length})
                  </h4>
                  <div className="overflow-hidden rounded-2xl border border-yeikar-secondary-light/10">
                    {(detalle.descuentos ?? []).map((d, i) => {
                      const esMulti = d.tasa_cambio && d.tasa_cambio !== 1;
                      const descCodigo = d.moneda?.codigo ?? '?';
                      const ventaCodigo = detalle.moneda?.codigo ?? '?';
                      return (
                        <div
                          key={d.id}
                          className={`flex items-start justify-between gap-3 px-3.5 py-3 text-sm ${i % 2 ? 'bg-white' : 'bg-yeikar-tertiary/10'}`}
                        >
                          <span className="min-w-0">
                            <span className="flex items-center gap-1.5 font-medium leading-snug text-yeikar-secondary">
                              <span className="h-2 w-2 shrink-0 rounded-full bg-amber-500" />
                              Descuento
                            </span>
                            {d.motivo && (
                              <span className="mt-0.5 block break-words text-xs text-yeikar-neutral/60">{d.motivo}</span>
                            )}
                            <span className="mt-0.5 block font-mono text-[11px] text-yeikar-neutral/50">
                              {fmtFechaVE(d.fecha)} · sin movimiento de caja
                            </span>
                            {esMulti && (
                              <span className="mt-0.5 block font-mono text-[11px] text-yeikar-neutral/50">
                                ≈ {fmtMoneda(Number(d.monto_en_moneda_base), ventaCodigo)}
                                <span className="opacity-70">
                                  {' '}(1 {descCodigo} = {Number(d.tasa_cambio).toLocaleString('es-ES')} {nombreMoneda(ventaCodigo)})
                                </span>
                              </span>
                            )}
                          </span>
                          <span className="shrink-0 text-right">
                            <span className="block font-mono text-sm font-black text-amber-700">
                              −{d.moneda?.simbolo ?? ''}{Number(d.monto).toLocaleString('es-ES')}
                            </span>
                            {d.moneda && (
                              <span className="mt-1 inline-block rounded bg-amber-100 px-1.5 py-0.5 font-mono text-[10px] font-black text-amber-800">
                                {d.moneda.codigo}
                              </span>
                            )}
                            <span className="block">
                              <button
                                type="button"
                                onClick={() => handleAnularDescuento(d.id)}
                                disabled={anulandoDescId === d.id}
                                className="mt-1 text-[11px] font-bold text-red-500 hover:underline disabled:opacity-50"
                              >
                                {anulandoDescId === d.id ? 'Anulando...' : 'Anular'}
                              </button>
                            </span>
                          </span>
                        </div>
                      );
                    })}
                  </div>
                </div>
              )}
              {descError && !showDescForm && (
                <p className="text-xs text-red-600 bg-red-50 border border-red-200 rounded-lg px-3 py-2">
                  {descError}
                </p>
              )}
              </>
              )}

              {/* Registrar cobro / descuento */}
              {detalle.estado !== 'PAGADA' && detalle.estado !== 'CANCELADA' && !showForm && !showDescForm && (
                <div className="sticky bottom-0 -mx-1 bg-gradient-to-t from-white via-white to-transparent px-1 pb-1 pt-4 space-y-2">
                  <button
                    onClick={() => setShowForm(true)}
                    className="w-full py-3 bg-gradient-to-r from-yeikar-primary to-amber-500 text-yeikar-neutral font-black font-headline rounded-2xl hover:brightness-105 active:scale-[0.99] transition-all shadow-lift"
                  >
                    + Registrar cobro
                  </button>
                  <button
                    onClick={abrirDescForm}
                    className="w-full py-2.5 text-sm font-bold text-amber-800 border border-amber-300 bg-amber-50 rounded-2xl hover:bg-amber-100 active:scale-[0.99] transition-all"
                  >
                    Aplicar descuento (no mueve caja)
                  </button>
                </div>
              )}

              {detalle.estado !== 'PAGADA' && detalle.estado !== 'CANCELADA' && showForm && (
                  <div className="rounded-2xl border border-yeikar-primary/25 bg-white p-4 space-y-3 shadow-card">
                      <div className="flex items-center justify-between gap-2 border-b border-yeikar-secondary-light/10 pb-2.5">
                        <div className="flex items-center gap-1">
                          <button
                            onClick={() => { setShowForm(false); setErrorPago(''); setTasaNaturalInput(''); }}
                            className="flex h-8 w-8 shrink-0 items-center justify-center rounded-full text-yeikar-neutral/50 transition-colors hover:bg-yeikar-tertiary/40 hover:text-yeikar-neutral"
                            aria-label="Volver al resumen"
                            title="Volver al resumen"
                          >
                            <svg className="h-4 w-4" fill="none" stroke="currentColor" viewBox="0 0 24 24">
                              <path strokeLinecap="round" strokeLinejoin="round" strokeWidth="2" d="M15 19l-7-7 7-7" />
                            </svg>
                          </button>
                          <h5 className="font-headline font-black text-sm text-yeikar-secondary">
                            Nuevo cobro
                          </h5>
                        </div>
                        <span className="rounded-full bg-amber-100 px-2.5 py-0.5 font-mono text-[11px] font-bold text-amber-800">
                          Saldo {detalle.moneda?.simbolo}{Number(detalle.saldo_pendiente).toLocaleString('es-ES')}
                        </span>
                      </div>

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
                              className="flex items-center gap-1 rounded-full border border-yeikar-primary/30 bg-amber-100/70 px-2.5 py-1 text-[10px] font-black uppercase tracking-wide text-amber-800 transition-colors hover:bg-amber-200"
                            >
                              Pagar restante
                            </button>
                          </div>
                          <input
                            type="number"
                            min="0"
                            step="0.0001"
                            inputMode="decimal"
                            autoFocus
                            value={monto}
                            onChange={(e) => setMonto(e.target.value)}
                            placeholder="0.00"
                            className="w-full px-3 py-2 text-sm border border-yeikar-secondary-light/20 rounded-lg focus:outline-none focus:ring-2 focus:ring-yeikar-primary bg-white"
                          />
                        </div>
                        {necesitaTRM && (
                          <div>
                            <label className="text-xs font-bold text-amber-600 block mb-1">
                              Tasa: {parPago.label}
                            </label>
                            <input
                              type="number"
                              min="0"
                              step="any"
                              value={tasaNaturalInput}
                              onChange={(e) => setTasaNaturalInput(e.target.value)}
                              placeholder={`Ej: ${parPago.placeholder}`}
                              className="w-full px-3 py-2 text-sm border border-amber-300 rounded-lg focus:outline-none focus:ring-2 focus:ring-amber-400 bg-amber-50"
                            />
                          </div>
                        )}
                      </div>

                      {/* Preview de conversión */}
                      {necesitaTRM && montoNum > 0 && tasaHumana > 0 && (
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

                      <div className="flex gap-2 pt-1">
                        <button
                          onClick={() => { setShowForm(false); setErrorPago(''); setTasaNaturalInput(''); }}
                          className="flex-1 py-2.5 text-sm font-bold text-yeikar-neutral/70 border border-yeikar-secondary-light/20 rounded-xl hover:bg-yeikar-tertiary/20 transition-all"
                        >
                          Cancelar
                        </button>
                        <button
                          onClick={handlePago}
                          disabled={submitting}
                          className="flex-1 py-2.5 text-sm font-black bg-yeikar-primary text-yeikar-neutral rounded-xl hover:bg-yeikar-primary/90 transition-all disabled:opacity-50"
                        >
                          {submitting ? 'Guardando...' : 'Confirmar cobro'}
                        </button>
                      </div>
                  </div>
              )}

              {detalle.estado !== 'PAGADA' && detalle.estado !== 'CANCELADA' && showDescForm && (
                  <div className="rounded-2xl border border-amber-300 bg-amber-50/50 p-4 space-y-3 shadow-card">
                      <div className="flex items-center justify-between gap-2 border-b border-amber-200 pb-2.5">
                        <div className="flex items-center gap-1">
                          <button
                            onClick={() => { setShowDescForm(false); setDescError(''); setDescTasaInput(''); }}
                            className="flex h-8 w-8 shrink-0 items-center justify-center rounded-full text-yeikar-neutral/50 transition-colors hover:bg-amber-100 hover:text-yeikar-neutral"
                            aria-label="Volver al resumen"
                            title="Volver al resumen"
                          >
                            <svg className="h-4 w-4" fill="none" stroke="currentColor" viewBox="0 0 24 24">
                              <path strokeLinecap="round" strokeLinejoin="round" strokeWidth="2" d="M15 19l-7-7 7-7" />
                            </svg>
                          </button>
                          <h5 className="font-headline font-black text-sm text-yeikar-secondary">
                            Aplicar descuento
                          </h5>
                        </div>
                        <span className="rounded-full bg-amber-100 px-2.5 py-0.5 font-mono text-[11px] font-bold text-amber-800">
                          Saldo {detalle.moneda?.simbolo}{Number(detalle.saldo_pendiente).toLocaleString('es-ES')}
                        </span>
                      </div>

                      <p className="text-[11px] text-amber-700/80 bg-amber-100/70 border border-amber-200 rounded-lg px-3 py-2">
                        Lo descontado resta del saldo pero <strong>no entra a ninguna cuenta de caja</strong>.
                      </p>

                      {/* Fila 1: Moneda + Monto */}
                      <div className="grid grid-cols-1 min-[420px]:grid-cols-2 gap-3">
                        <div>
                          <label className="text-xs font-bold text-yeikar-neutral/60 block mb-1">
                            Moneda del descuento
                          </label>
                          <SearchSelect
                            value={descMonedaId}
                            onChange={(v) => setDescMonedaId(Number(v))}
                            options={monedas.map((m) => ({
                              value: m.id,
                              label: `${m.codigo} — ${m.nombre}`,
                            }))}
                            placeholder="Seleccione moneda..."
                          />
                        </div>
                        <div>
                          <div className="flex justify-between items-center mb-1">
                            <label className="text-xs font-bold text-yeikar-neutral/60 block">
                              Monto ({monedaDesc?.codigo ?? '...'})
                            </label>
                            <button
                              type="button"
                              onClick={handleSetDescRestante}
                              className="flex items-center gap-1 rounded-full border border-amber-300 bg-amber-100/70 px-2.5 py-1 text-[10px] font-black uppercase tracking-wide text-amber-800 transition-colors hover:bg-amber-200"
                            >
                              Descontar restante
                            </button>
                          </div>
                          <input
                            type="number"
                            min="0"
                            step="0.0001"
                            inputMode="decimal"
                            autoFocus
                            value={descMonto}
                            onChange={(e) => setDescMonto(e.target.value)}
                            placeholder="0.00"
                            className="w-full px-3 py-2 text-sm border border-amber-300 rounded-lg focus:outline-none focus:ring-2 focus:ring-amber-400 bg-white"
                          />
                        </div>
                      </div>

                      {necesitaTRMDesc && (
                        <div>
                          <label className="text-xs font-bold text-amber-600 block mb-1">
                            Tasa: {parDesc.label}
                          </label>
                          <input
                            type="number"
                            min="0"
                            step="any"
                            value={descTasaInput}
                            onChange={(e) => setDescTasaInput(e.target.value)}
                            placeholder={`Ej: ${parDesc.placeholder}`}
                            className="w-full px-3 py-2 text-sm border border-amber-300 rounded-lg focus:outline-none focus:ring-2 focus:ring-amber-400 bg-amber-50"
                          />
                        </div>
                      )}

                      {/* Preview de conversión */}
                      {necesitaTRMDesc && descMontoNum > 0 && tasaHumanaDesc > 0 && (
                        <div className="bg-amber-50 border border-amber-200 rounded-lg px-3 py-2">
                          <p className="text-sm font-bold text-amber-800 font-mono">
                            ≈ {descEquivalente.toLocaleString('es-ES', { minimumFractionDigits: 2 })} {nombreMoneda(monedaVenta?.codigo)}
                          </p>
                          {descEquivalente > saldoRestante + (monedaVenta?.codigo === 'COP' ? 1000 : 0.01) && (
                            <p className="text-xs text-red-600 font-bold mt-1">
                              El equivalente excede el saldo pendiente ({saldoRestante.toLocaleString('es-ES')} {nombreMoneda(monedaVenta?.codigo)})
                            </p>
                          )}
                        </div>
                      )}

                      <div>
                        <label className="text-xs font-bold text-yeikar-neutral/60 block mb-1">
                          Motivo (opcional)
                        </label>
                        <input
                          type="text"
                          value={descMotivo}
                          onChange={(e) => setDescMotivo(e.target.value)}
                          placeholder="Ej: acuerdo con el dueño"
                          className="w-full px-3 py-2 text-sm border border-yeikar-secondary-light/20 rounded-lg focus:outline-none focus:ring-2 focus:ring-amber-400 bg-white"
                        />
                      </div>

                      {descError && (
                        <p className="text-xs text-red-600 bg-red-50 border border-red-200 rounded-lg px-3 py-2">
                          {descError}
                        </p>
                      )}

                      <div className="flex gap-2 pt-1">
                        <button
                          onClick={() => { setShowDescForm(false); setDescError(''); setDescTasaInput(''); }}
                          className="flex-1 py-2.5 text-sm font-bold text-yeikar-neutral/70 border border-yeikar-secondary-light/20 rounded-xl hover:bg-yeikar-tertiary/20 transition-all"
                        >
                          Cancelar
                        </button>
                        <button
                          onClick={handleDescuento}
                          disabled={descSubmitting}
                          className="flex-1 py-2.5 text-sm font-black bg-amber-500 text-white rounded-xl hover:bg-amber-600 transition-all disabled:opacity-50"
                        >
                          {descSubmitting ? 'Guardando...' : 'Confirmar descuento'}
                        </button>
                      </div>
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

// ─── Encabezado compartido de secciones (título + contador + tono urgente) ───
function EncabezadoSeccion({
  titulo,
  descripcion,
  icono,
  tono,
  hayPendientes,
  conteo,
}: {
  titulo: string;
  descripcion: string;
  icono: ReactNode;
  tono: 'urgente' | 'proceso';
  hayPendientes: boolean;
  conteo: number;
}) {
  const esUrgente = tono === 'urgente' && hayPendientes;
  return (
    <div className="mb-2.5 flex items-start gap-3 sm:items-center">
      <span
        className={`flex h-8 w-8 shrink-0 items-center justify-center rounded-lg ${
          esUrgente ? 'bg-amber-100 text-amber-700' : 'bg-yeikar-tertiary/40 text-yeikar-secondary'
        }`}
      >
        {icono}
      </span>
      <div className="min-w-0">
        <h2 className="flex items-center gap-2 font-headline text-lg font-black leading-none tracking-tight text-yeikar-neutral">
          {titulo}
          <span
            className={`rounded-full px-2 py-0.5 font-mono text-xs font-bold ${
              hayPendientes ? 'bg-amber-100 text-amber-700' : 'bg-yeikar-tertiary/30 text-yeikar-neutral/60'
            }`}
          >
            {conteo}
          </span>
        </h2>
        <p className="mt-0.5 text-xs text-yeikar-neutral/50">{descripcion}</p>
      </div>
    </div>
  );
}

// ─── Sección de grupo de cobros (Entregados / En proceso) ────────────────────
function SeccionVentas({
  titulo,
  descripcion,
  icono,
  tono,
  hayPendientes,
  vacio,
  loading,
  rows,
  columns,
  acciones,
}: {
  titulo: string;
  descripcion: string;
  icono: ReactNode;
  tono: 'urgente' | 'proceso';
  hayPendientes: boolean;
  vacio: string;
  loading: boolean;
  rows: Venta[];
  columns: DataColumn<Venta>[];
  acciones: (v: Venta) => ReactNode;
}) {
  const esUrgente = tono === 'urgente' && hayPendientes;
  return (
    <section>
      <EncabezadoSeccion
        titulo={titulo}
        descripcion={descripcion}
        icono={icono}
        tono={tono}
        hayPendientes={hayPendientes}
        conteo={rows.length}
      />
      <div
        className={`bg-white rounded-2xl border shadow-sm overflow-hidden ${
          esUrgente ? 'border-amber-300 border-l-4' : 'border-yeikar-secondary-light/10'
        }`}
      >
        {loading ? (
          <Spinner />
        ) : rows.length === 0 ? (
          <div className="p-8 text-center text-yeikar-neutral/40 italic text-sm">{vacio}</div>
        ) : (
          <ResponsiveDataTable
            columns={columns}
            rows={rows}
            rowKey={(v) => v.id}
            cardBadge={(v) => <Badge text={v.estado} className={ESTADO_VENTA_STYLE[v.estado] ?? ''} />}
            tableActions={acciones}
            cardActions={acciones}
            darkHeader
          />
        )}
      </div>
    </section>
  );
}

// ─── Pill de filtro (misma píldora para estado y para grupo) ─────────────────
function PillFiltro({ activo, onClick, children }: { activo: boolean; onClick: () => void; children: ReactNode }) {
  return (
    <button
      onClick={onClick}
      className={`px-3 py-1 rounded-full text-xs font-bold border transition-all ${
        activo
          ? 'bg-yeikar-primary text-yeikar-neutral border-yeikar-primary'
          : 'bg-white text-yeikar-neutral/60 border-yeikar-secondary-light/20 hover:border-yeikar-primary/40'
      }`}
    >
      {children}
    </button>
  );
}

// ─── Página principal ─────────────────────────────────────────────────────────
export default function Ventas() {
  const [ventas, setVentas] = useState<Venta[]>([]);
  const [ventasLoading, setVentasLoading] = useState(false);
  const [cuentas, setCuentas] = useState<CuentaPorCobrar[]>([]);
  const [cobroAbiertoId, setCobroAbiertoId] = useState<number | null>(null);

  // Modales
  const [detalleVentaId, setDetalleVentaId] = useState<number | null>(null);

  // Filtro de estado: por defecto solo cobros pendientes (PENDIENTE/ABONADA);
  // las pagadas/canceladas quedan en su pill o en 'Todas'.
  const [filtroEstado, setFiltroEstado] = useState<string>('COBROS');

  // Filtro de grupo: qué secciones se ven. 'todos' apila Entregados y En proceso.
  const [filtroGrupo, setFiltroGrupo] = useState<'todos' | 'entregados' | 'proceso'>('todos');

  // Búsqueda
  const [busqueda, setBusqueda] = useState('');

  const cargarVentas = useCallback(async (termino?: string) => {
    try {
      setVentasLoading(true);
      const [data, cuentasData] = await Promise.all([
        ventaService.getAll(termino ? { buscar: termino } : undefined),
        // Si el endpoint de saldos falla, igual mostramos la lista usando el
        // total como saldo (fallback visible en la tarjeta, no un vacío).
        ventaService.getCuentasPorCobrar().catch(() => [] as CuentaPorCobrar[]),
      ]);
      setVentas(data);
      setCuentas(cuentasData);
    } finally {
      setVentasLoading(false);
    }
  }, []);

  useEffect(() => {
    const t = setTimeout(() => cargarVentas(busqueda.trim() || undefined), 300);
    return () => clearTimeout(t);
  }, [busqueda, cargarVentas]);

  useEffect(() => {
    setCobroAbiertoId(null);
  }, [filtroEstado, filtroGrupo, busqueda]);

  const ventasFiltradas = filtroEstado === 'COBROS'
    ? ventas.filter((v) => v.estado === 'PENDIENTE' || v.estado === 'ABONADA')
    : filtroEstado
      ? ventas.filter((v) => v.estado === filtroEstado)
      : ventas;

  // Ubicación del dinero pendiente: lo define el pedido (ya entregado vs. en
  // proceso). El backend deriva pedido_estado del envío confirmado.
  const esEntregada = (v: Venta) => v.pedido_estado === 'ENTREGADO';
  const ventasEntregadas = ventasFiltradas.filter(esEntregada);
  const ventasEnProceso = ventasFiltradas.filter((v) => !esEntregada(v));

  const cuentasPorVenta = useMemo(() => new Map(cuentas.map((c) => [c.venta_id, c])), [cuentas]);
  const combinarVentaConCuenta = (v: Venta): CobroPendiente => {
    const cuenta = cuentasPorVenta.get(v.id);
    const total = cuenta ? Number(cuenta.total) : Number(v.total);
    const pagado = cuenta ? Number(cuenta.total_pagado) : 0;
    const descontado = cuenta ? Number(cuenta.total_descontado ?? 0) : 0;
    const saldo = cuenta ? Number(cuenta.saldo_pendiente) : Math.max(total - pagado, 0);
    const codigo = cuenta?.moneda_codigo ?? v.moneda?.codigo ?? 'USD';
    return { venta: v, total, pagado, descontado, saldo, codigo };
  };
  const cobrosEntregados = ventasEntregadas.map(combinarVentaConCuenta);
  const cobrosEnProceso = ventasEnProceso.map(combinarVentaConCuenta);

  const totalPendiente = ventas
    .filter((v) => v.estado !== 'PAGADA' && v.estado !== 'CANCELADA')
    .length;

  const ventasColumns: DataColumn<Venta>[] = [
    {
      key: 'id',
      header: '# Venta',
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
      render: (v) => <span className="font-mono text-yeikar-neutral/70">{fmtFechaVE(v.fecha)}</span>,
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

  const renderAccionVenta = (v: Venta) => (
    <button
      id={`btn-ver-venta-${v.id}`}
      onClick={() => setDetalleVentaId(v.id)}
      className="px-3 py-2 bg-yeikar-secondary text-yeikar-tertiary hover:bg-yeikar-secondary-light rounded-lg text-xs font-bold font-headline transition-colors"
    >
      {v.estado !== 'PAGADA' && v.estado !== 'CANCELADA' ? 'Ver / Cobrar' : 'Ver Detalle'}
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
            Quién debe y en qué etapa está. Toca Ver / Cobrar para registrar un abono.
          </p>
        </div>
        {totalPendiente > 0 && (
          <div className="flex items-center gap-2 bg-amber-50 border border-amber-200 text-amber-700 px-4 py-2 rounded-xl text-sm font-bold">
            <svg className="w-4 h-4" fill="none" stroke="currentColor" viewBox="0 0 24 24">
              <path strokeLinecap="round" strokeLinejoin="round" strokeWidth="2" d="M12 8v4m0 4h.01M21 12a9 9 0 11-18 0 9 9 0 0118 0z" />
            </svg>
            {totalPendiente} cuenta{totalPendiente !== 1 ? 's' : ''} por cobrar
          </div>
        )}
      </div>

      {/* Filtros: estado de cobro + qué grupo ver, y búsqueda */}
      <div className="flex flex-col gap-3">
        <div className="flex flex-col sm:flex-row sm:items-center justify-between gap-3">
          <div className="flex items-center gap-3 flex-wrap">
            <span className="text-xs font-bold text-yeikar-neutral/50 font-mono">FILTRAR:</span>
            {['COBROS', 'PAGADA', 'CANCELADA', ''].map((est) => (
              <PillFiltro key={est} activo={filtroEstado === est} onClick={() => setFiltroEstado(est)}>
                {est === '' ? 'Todas' : est === 'COBROS' ? 'Pendientes de cobro' : est}
              </PillFiltro>
            ))}
          </div>
          <SearchInput
            value={busqueda}
            onChange={(e) => setBusqueda(e.target.value)}
            placeholder="Buscar por cliente o estado..."
            className="w-full sm:w-72"
          />
        </div>
        <div className="flex items-center gap-3 flex-wrap">
          <span className="text-xs font-bold text-yeikar-neutral/50 font-mono">VER:</span>
          {([
            { key: 'todos', label: 'Ambos' },
            { key: 'entregados', label: 'Entregados' },
            { key: 'proceso', label: 'En proceso' },
          ] as const).map((g) => (
            <PillFiltro key={g.key} activo={filtroGrupo === g.key} onClick={() => setFiltroGrupo(g.key)}>
              {g.label}
            </PillFiltro>
          ))}
        </div>
      </div>

      {/* ── GRUPO: Entregados (dinero en la calle) ── */}
      {filtroGrupo !== 'proceso' && (
        filtroEstado === 'COBROS' ? (
          <SeccionCobros
            tono="urgente"
            hayPendientes={ventasEntregadas.some((v) => v.estado === 'PENDIENTE' || v.estado === 'ABONADA')}
            titulo="Entregados"
            descripcion="El cliente ya recibió el mueble. Toca una tarjeta para ver la deuda y el pedido."
            icono={
              <svg className="w-4 h-4" fill="none" stroke="currentColor" viewBox="0 0 24 24">
                <path strokeLinecap="round" strokeLinejoin="round" strokeWidth="2" d="M5 8h14M5 8a2 2 0 110-4h14a2 2 0 110 4M5 8v10a2 2 0 002 2h10a2 2 0 002-2V8m-9 4h4" />
              </svg>
            }
            vacio="No hay entregas pendientes de cobro. Todo cobrado."
            loading={ventasLoading}
            cobros={cobrosEntregados}
            abiertoId={cobroAbiertoId}
            onToggle={(id) => setCobroAbiertoId((abierto) => (abierto === id ? null : id))}
            onCobrar={(id) => setDetalleVentaId(id)}
          />
        ) : (
          <SeccionVentas
            tono="urgente"
            hayPendientes={ventasEntregadas.some((v) => v.estado === 'PENDIENTE' || v.estado === 'ABONADA')}
            titulo="Entregados"
            descripcion="El cliente ya recibió el mueble. Son las cobranzas más urgentes."
            icono={
              <svg className="w-4 h-4" fill="none" stroke="currentColor" viewBox="0 0 24 24">
                <path strokeLinecap="round" strokeLinejoin="round" strokeWidth="2" d="M5 8h14M5 8a2 2 0 110-4h14a2 2 0 110 4M5 8v10a2 2 0 002 2h10a2 2 0 002-2V8m-9 4h4" />
              </svg>
            }
            vacio={filtroEstado === 'COBROS'
              ? 'No hay entregas pendientes de cobro. Todo cobrado.'
              : 'Ninguna venta entregada con este filtro.'}
            loading={ventasLoading}
            rows={ventasEntregadas}
            columns={ventasColumns}
            acciones={renderAccionVenta}
          />
        )
      )}

      {/* ── GRUPO: En proceso (aún no entregados) ── */}
      {filtroGrupo !== 'entregados' && (
        filtroEstado === 'COBROS' ? (
          <SeccionCobros
            tono="proceso"
            hayPendientes={ventasEnProceso.some((v) => v.estado === 'PENDIENTE' || v.estado === 'ABONADA')}
            titulo="En proceso"
            descripcion="En fabricación o listos para despacho. Al confirmarse la entrega pasan arriba, a Entregados."
            icono={
              <svg className="w-4 h-4" fill="none" stroke="currentColor" viewBox="0 0 24 24">
                <path strokeLinecap="round" strokeLinejoin="round" strokeWidth="2" d="M10.325 4.317c.426-1.756 2.924-1.756 3.35 0a1.724 1.724 0 002.573 1.066c1.543-.94 3.31.826 2.37 2.37a1.724 1.724 0 001.065 2.572c1.756.426 1.756 2.924 0 3.35a1.724 1.724 0 00-1.066 2.573c.94 1.543-.826 3.31-2.37 2.37a1.724 1.724 0 00-2.572 1.065c-.426 1.756-2.924 1.756-3.35 0a1.724 1.724 0 00-2.573-1.066c-1.543.94-3.31-.826-2.37-2.37a1.724 1.724 0 00-1.065-2.572c-1.756-.426-1.756-2.924 0-3.35a1.724 1.724 0 001.066-2.573c-.94-1.543.826-3.31 2.37-2.37.996.608 2.296.07 2.572-1.065z" />
                <path strokeLinecap="round" strokeLinejoin="round" strokeWidth="2" d="M15 12a3 3 0 11-6 0 3 3 0 016 0z" />
              </svg>
            }
            vacio="No hay ventas en proceso pendientes de cobro."
            loading={ventasLoading}
            cobros={cobrosEnProceso}
            abiertoId={cobroAbiertoId}
            onToggle={(id) => setCobroAbiertoId((abierto) => (abierto === id ? null : id))}
            onCobrar={(id) => setDetalleVentaId(id)}
          />
        ) : (
          <SeccionVentas
            tono="proceso"
            hayPendientes={ventasEnProceso.some((v) => v.estado === 'PENDIENTE' || v.estado === 'ABONADA')}
            titulo="En proceso"
            descripcion="En fabricación o listos para despacho. Al confirmarse la entrega pasan arriba, a Entregados."
            icono={
              <svg className="w-4 h-4" fill="none" stroke="currentColor" viewBox="0 0 24 24">
                <path strokeLinecap="round" strokeLinejoin="round" strokeWidth="2" d="M10.325 4.317c.426-1.756 2.924-1.756 3.35 0a1.724 1.724 0 002.573 1.066c1.543-.94 3.31.826 2.37 2.37a1.724 1.724 0 001.065 2.572c1.756.426 1.756 2.924 0 3.35a1.724 1.724 0 00-1.066 2.573c.94 1.543-.826 3.31-2.37 2.37a1.724 1.724 0 00-2.572 1.065c-.426 1.756-2.924 1.756-3.35 0a1.724 1.724 0 00-2.573-1.066c-1.543.94-3.31-.826-2.37-2.37a1.724 1.724 0 00-1.065-2.572c-1.756-.426-1.756-2.924 0-3.35a1.724 1.724 0 001.066-2.573c-.94-1.543.826-3.31 2.37-2.37.996.608 2.296.07 2.572-1.065z" />
                <path strokeLinecap="round" strokeLinejoin="round" strokeWidth="2" d="M15 12a3 3 0 11-6 0 3 3 0 016 0z" />
              </svg>
            }
            vacio={filtroEstado === 'COBROS'
              ? 'No hay ventas en proceso pendientes de cobro.'
              : 'Ninguna venta en proceso con este filtro.'}
            loading={ventasLoading}
            rows={ventasEnProceso}
            columns={ventasColumns}
            acciones={renderAccionVenta}
          />
        )
      )}

      {/* Modales */}
      {detalleVentaId !== null && (
        <ModalDetalle
          ventaId={detalleVentaId}
          onClose={() => setDetalleVentaId(null)}
          onPagoRegistrado={() => cargarVentas(busqueda.trim() || undefined)}
        />
      )}
    </div>
  );
}
