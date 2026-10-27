import { useState, useEffect, useCallback, type ReactNode } from 'react';
import {
  cuentasService, ResumenCuenta, MovimientoCaja, Moneda,
  MovimientoCreate, MetodoCaja, TransferenciaPayload,
} from '../services/cuentasService';
import { CLASIFICACIONES_GASTO } from '../services/gastoService';
import {
  Button, Card, Badge, Spinner, EmptyState, StatCard, Modal, PageHeader,
  Field, Input, Select, Textarea, ConfirmDialog, SearchSelect, MontoInput,
  ResponsiveDataTable, type DataColumn,
} from '../components/ui';
import { nombreMoneda, fmtMoneda } from '../utils/format';
import { formatMontoInput, parseMontoInput } from '../utils/monto';
import { useToast } from '../context/ToastContext';
import LibroCajaView from '../components/Cuentas/LibroCajaView';
import ReporteCuentasModal from '../components/Cuentas/ReporteCuentasModal';

const TIPOS = [
  { key: '', label: 'Todos' },
  { key: 'APERTURA', label: 'Apertura' },
  { key: 'ENTRADA', label: 'Entrada' },
  { key: 'SALIDA', label: 'Salida' },
  { key: 'AJUSTE', label: 'Ajuste' },
];

const emptyMovForm = (metodoId = 0, monedaCopId = 1) => ({
  metodo_caja_id: metodoId,
  fecha: new Date().toISOString().split('T')[0],
  tipo: 'ENTRADA' as MovimientoCreate['tipo'],
  monto: '',
  moneda_id: monedaCopId,
  persona_entidad: '',
  concepto: '',
  // Solo para salidas: clasificación opcional del egreso.
  clasificacion: '',
});

const fmt = (n: number) => (Number.isFinite(n) ? n.toLocaleString('es-CO', { maximumFractionDigits: 0 }) : '0');

const fmtTasa = (n: number) => (
  Number.isFinite(n) && n > 0
    ? n.toLocaleString('es-CO', { maximumFractionDigits: 6 })
    : '—'
);

const TIPO_TONE: Record<string, 'neutral' | 'green' | 'red' | 'amber'> = {
  APERTURA: 'neutral',
  ENTRADA: 'green',
  SALIDA: 'red',
  AJUSTE: 'amber',
};

const emptyTransferForm = () => ({
  cuenta_origen_id: 0,
  cuenta_destino_id: 0,
  monto: 0,
  fecha: new Date().toISOString().split('T')[0],
  tasa_conversion: '',
  tasa_invertida: false,
  tasa_cambio: '',
  interes: '',
  interes_signo: 'RESTA' as 'SUMA' | 'RESTA',
  persona_entidad: '',
  referencia: '',
  concepto: '',
});

function DetalleFila({ label, children }: { label: string; children: ReactNode }) {
  return (
    <div className="grid grid-cols-[130px_1fr] gap-3 items-baseline">
      <dt className="font-mono text-[10px] uppercase tracking-wider text-yeikar-neutral/40">{label}</dt>
      <dd className="break-words whitespace-pre-line text-sm text-yeikar-neutral/90">{children}</dd>
    </div>
  );
}

export default function Cuentas() {
  const toast = useToast();
  const [vista, setVista] = useState<'libro' | 'cuentas'>('libro');
  const [resumen, setResumen] = useState<ResumenCuenta[]>([]);
  const [movimientos, setMovimientos] = useState<MovimientoCaja[]>([]);
  const [monedas, setMonedas] = useState<Moneda[]>([]);
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState('');

  const [showCuentaModal, setShowCuentaModal] = useState(false);
  const [editCuenta, setEditCuenta] = useState<MetodoCaja | null>(null);
  const [cuentaForm, setCuentaForm] = useState<{ nombre: string; codigo: string; orden: number; moneda_id: number | null }>({ nombre: '', codigo: '', orden: 1, moneda_id: null });

  const [showMovModal, setShowMovModal] = useState(false);
  const [editMov, setEditMov] = useState<MovimientoCaja | null>(null);
  const [movForm, setMovForm] = useState(emptyMovForm());

  const [showTransferModal, setShowTransferModal] = useState(false);
  const [transferForm, setTransferForm] = useState(emptyTransferForm());
  const [transferTasaManual, setTransferTasaManual] = useState(false);

  const [filtroCuenta, setFiltroCuenta] = useState<number | ''>('');
  const [filtroTipo, setFiltroTipo] = useState('');
  const [fechaDesde, setFechaDesde] = useState('');
  const [fechaHasta, setFechaHasta] = useState('');

  const [confirmAccion, setConfirmAccion] = useState<null | { tipo: 'cuenta' | 'movimiento'; id: number; nombre?: string }>(null);
  const [detalleMov, setDetalleMov] = useState<MovimientoCaja | null>(null);

  // Reporte del libro de caja (PDF / Excel)
  const [showReporteModal, setShowReporteModal] = useState(false);
  const [reporteDefaults, setReporteDefaults] = useState<{
    cuentaId: number; desde: string; hasta: string;
  } | null>(null);
  const handleLibroFiltro = useCallback((filtro: {
    cuentaId: number; desde: string; hasta: string;
  }) => setReporteDefaults(filtro), []);

  const cargarTodo = useCallback(async () => {
    setLoading(true);
    setError('');
    try {
      const [res, movs, mon] = await Promise.all([
        cuentasService.getResumen(),
        cuentasService.getMovimientos({
          metodo_caja_id: filtroCuenta || undefined,
          fecha_desde: fechaDesde || undefined,
          fecha_hasta: fechaHasta || undefined,
        }),
        cuentasService.getMonedas(),
      ]);
      setResumen(res);
      setMovimientos(filtroTipo
        ? movs.filter((m) => m.tipo === filtroTipo)
        : movs);
      setMonedas(mon);
    } catch (e: any) {
      setError(e?.response?.data?.detail ?? 'Error al cargar las cuentas.');
    } finally {
      setLoading(false);
    }
  }, [filtroCuenta, filtroTipo, fechaDesde, fechaHasta]);

  useEffect(() => {
    cargarTodo();
  }, [cargarTodo]);

  const monedaCopId = monedas.find((m) => m.codigo === 'COP')?.id ?? 1;
  const monedaDe = (id?: number) => monedas.find((m) => m.id === id);

  // ─── Cuentas ───────────────────────────────────────────────────────────
  const abrirCuenta = (cuenta?: MetodoCaja) => {
    setEditCuenta(cuenta ?? null);
    setCuentaForm(cuenta
      ? { nombre: cuenta.nombre, codigo: cuenta.codigo, orden: cuenta.orden, moneda_id: cuenta.moneda_id ?? null }
      : { nombre: '', codigo: '', orden: resumen.length + 1, moneda_id: monedaCopId });
    setShowCuentaModal(true);
  };

  const guardarCuenta = async () => {
    if (!cuentaForm.nombre.trim() || !cuentaForm.codigo.trim()) {
      setError('Nombre y código son obligatorios.');
      return;
    }
    if (!cuentaForm.moneda_id) {
      setError('Selecciona la moneda de la cuenta.');
      return;
    }
    try {
      if (editCuenta) {
        await cuentasService.actualizarCuenta(editCuenta.id, {
          nombre: cuentaForm.nombre.trim(),
          codigo: cuentaForm.codigo.trim().toUpperCase(),
          orden: cuentaForm.orden,
          moneda_id: cuentaForm.moneda_id,
        });
      } else {
        await cuentasService.crearCuenta({
          nombre: cuentaForm.nombre.trim(),
          codigo: cuentaForm.codigo.trim().toUpperCase(),
          orden: cuentaForm.orden,
          moneda_id: cuentaForm.moneda_id,
        });
      }
      setShowCuentaModal(false);
      cargarTodo();
    } catch (e: any) {
      setError(e?.response?.data?.detail ?? 'Error al guardar la cuenta.');
    }
  };

  const eliminarCuenta = async (id: number) => {
    try {
      await cuentasService.eliminarCuenta(id);
      cargarTodo();
    } catch (e: any) {
      setError(e?.response?.data?.detail ?? 'Error al eliminar la cuenta.');
    } finally {
      setConfirmAccion(null);
    }
  };

  // ─── Movimientos ───────────────────────────────────────────────────────
  const abrirMovimiento = (cuentaId: number, mov?: MovimientoCaja) => {
    setEditMov(mov ?? null);
    if (mov) {
      setMovForm({
        metodo_caja_id: mov.metodo_caja_id,
        fecha: mov.fecha.slice(0, 10),
        tipo: mov.tipo,
        monto: formatMontoInput(String(mov.monto)),
        moneda_id: mov.moneda_id,
        persona_entidad: mov.persona_entidad ?? '',
        concepto: mov.concepto ?? '',
        clasificacion: '',
      });
    } else {
      // Movimiento nuevo: la moneda arranca en la moneda propia de la cuenta.
      const cuentaSel = resumen.find((r) => r.metodo_caja.id === cuentaId);
      const monedaCuenta = cuentaSel?.metodo_caja.moneda_id || monedaCopId;
      setMovForm(emptyMovForm(cuentaId, monedaCuenta));
    }
    setShowMovModal(true);
  };

  const guardarMovimiento = async () => {
    const monto = parseMontoInput(movForm.monto);
    if (!movForm.metodo_caja_id || !Number.isFinite(monto) || monto <= 0) {
      setError('Cuenta y monto son obligatorios (mayor a 0).');
      return;
    }
    const payload = {
      fecha: movForm.fecha,
      tipo: movForm.tipo,
      monto,
      moneda_id: movForm.moneda_id,
      persona_entidad: movForm.persona_entidad.trim() || null,
      concepto: movForm.concepto.trim() || null,
      // La clasificación solo aplica a salidas nuevas: el alta crea además el
      // Gasto clasificado. En edición se cambia desde el módulo Gastos.
      ...(!editMov && movForm.tipo === 'SALIDA' && movForm.clasificacion
        ? { clasificacion: movForm.clasificacion }
        : {}),
    };
    try {
      if (editMov) {
        await cuentasService.actualizarMovimiento(editMov.id, payload);
      } else {
        await cuentasService.crearMovimiento(movForm.metodo_caja_id, payload);
      }
      setShowMovModal(false);
      cargarTodo();
    } catch (e: any) {
      setError(e?.response?.data?.detail ?? 'Error al guardar el movimiento.');
    }
  };

  const eliminarMovimiento = async (id: number) => {
    try {
      await cuentasService.eliminarMovimiento(id);
      cargarTodo();
    } catch (e: any) {
      setError(e?.response?.data?.detail ?? 'Error al eliminar el movimiento.');
    } finally {
      setConfirmAccion(null);
    }
  };

  // ─── Transferencias entre cuentas ──────────────────────────────────────
  const saldoDe = (cuentaId: number, monedaId: number) => {
    const r = resumen.find((x) => x.metodo_caja.id === cuentaId);
    if (!r) return 0;
    return Number(r.saldo_por_moneda.find((l) => l.moneda_id === monedaId)?.monto ?? 0);
  };

  const transferCuenta = (id: number) => resumen.find((r) => r.metodo_caja.id === id)?.metodo_caja;
  const sugerirTasaInvertida = (origenId: number, destinoId: number) => {
    const moOrigen = transferCuenta(origenId)?.moneda_id || monedaCopId;
    const moDestino = transferCuenta(destinoId)?.moneda_id || moOrigen;
    return moOrigen === monedaCopId && moDestino !== monedaCopId;
  };
  const transferMonedaSalida = transferCuenta(transferForm.cuenta_origen_id)?.moneda_id || monedaCopId;
  // El backend, si la cuenta destino no tiene moneda, usa la de origen.
  const transferMonedaDestino = transferCuenta(transferForm.cuenta_destino_id)?.moneda_id || transferMonedaSalida;
  const transferCodigoOrigen = transferCuenta(transferForm.cuenta_origen_id)?.moneda_codigo
    || monedaDe(transferMonedaSalida)?.codigo || 'COP';
  const transferCodigoDestino = transferCuenta(transferForm.cuenta_destino_id)?.moneda_codigo
    || monedaDe(transferMonedaDestino)?.codigo || 'COP';
  const transferSaldoDisponible = saldoDe(transferForm.cuenta_origen_id, transferMonedaSalida);
  const transferSaldoExcede = transferForm.monto > transferSaldoDisponible + 0.005;
  const transferMultimoneda = transferMonedaSalida !== transferMonedaDestino;
  const transferMontoValido = transferForm.monto > 0;
  // La tasa → COP solo hace falta cuando la moneda origen no es COP y la
  // contraparte tampoco (incluye transferencias USD→USD): sirve para valorar
  // la pata en moneda base si no hay TRM registrada.
  const transferNecesitaTasaCop = transferMonedaSalida !== monedaCopId
    && transferMonedaDestino !== monedaCopId;

  // La tasa interna siempre es "unidades de destino por 1 de origen".
  // El formulario puede mostrarla invertida (1 destino = X origen).
  const transferTasaInput = Number(transferForm.tasa_conversion) || 0;
  const transferTasaConversion = !transferMultimoneda
    ? 1
    : (transferForm.tasa_invertida
        ? (transferTasaInput > 0 ? 1 / transferTasaInput : 0)
        : transferTasaInput);
  const transferTasaValida = !transferMultimoneda || transferTasaConversion > 0;
  const transferMontoConvertido = transferMultimoneda
    ? transferForm.monto * transferTasaConversion
    : transferForm.monto;
  const transferInteresMonto = Number(transferForm.interes) || 0;
  const transferInteresFirmado = transferForm.interes_signo === 'SUMA'
    ? transferInteresMonto
    : -transferInteresMonto;
  const transferMontoEntrada = Number(
    (transferMontoConvertido + transferInteresFirmado).toFixed(2)
  );
  const transferEntradaValida = transferMontoEntrada > 0;
  const transferFormListo = transferForm.cuenta_origen_id > 0
    && transferForm.cuenta_destino_id > 0
    && transferForm.cuenta_origen_id !== transferForm.cuenta_destino_id
    && transferForm.monto > 0;
  const transferEtiquetaTasa = transferForm.tasa_invertida
    ? `1 ${transferCodigoDestino} = ? ${transferCodigoOrigen}`
    : `1 ${transferCodigoOrigen} = ? ${transferCodigoDestino}`;
  const transferTasaEquivalente = transferTasaConversion > 0
    ? (transferForm.tasa_invertida
        ? `Equivale a 1 ${transferCodigoOrigen} = ${fmtTasa(transferTasaConversion)} ${transferCodigoDestino}`
        : `Equivale a 1 ${transferCodigoDestino} = ${fmtTasa(1 / transferTasaConversion)} ${transferCodigoOrigen}`)
    : '';
  const transferTasaHint = transferTasaConversion > 0
    ? `${transferTasaEquivalente}. Usa la tasa real de la operación.`
    : 'No hay TRM registrada para este par: escribe la tasa real de la operación.';
  const transferMontoEntradaFmt = fmtMoneda(transferMontoEntrada, transferCodigoDestino);

  // Prellena la tasa con la TRM registrada; si no hay, se digita a mano.
  useEffect(() => {
    if (!showTransferModal) return;
    const origenId = transferForm.cuenta_origen_id;
    const destinoId = transferForm.cuenta_destino_id;
    if (!origenId || !destinoId || origenId === destinoId) return;
    if (!transferMultimoneda) {
      if (transferForm.tasa_conversion !== '1') {
        setTransferForm((f) => ({ ...f, tasa_conversion: '1', tasa_invertida: false }));
      }
      return;
    }
    if (transferTasaManual) return;
    let cancelado = false;
    cuentasService.getTasaTransferencia({
      cuenta_origen_id: origenId,
      cuenta_destino_id: destinoId,
      fecha: transferForm.fecha,
    }).then((data) => {
      if (cancelado) return;
      setTransferForm((f) => {
        if (f.cuenta_origen_id !== origenId || f.cuenta_destino_id !== destinoId) return f;
        // El usuario pudo escribir la tasa mientras respondía la petición.
        if (f.tasa_conversion.trim() !== '') return f;
        const valor = Number(data.tasa_conversion);
        // Si una punta es COP, se muestra en la dirección humana:
        // 1 USD = 4.000 COP (no 1 COP = 0,00025 USD).
        const invertida = f.tasa_invertida
          || (transferMonedaSalida === monedaCopId && transferMonedaDestino !== monedaCopId);
        const mostrado = invertida
          ? (valor > 0 ? 1 / valor : 0)
          : valor;
        return {
          ...f,
          tasa_invertida: invertida,
          tasa_conversion: String(mostrado),
        };
      });
    }).catch(() => {
      // Sin TRM registrada para el par: la tasa se puede escribir a mano.
    });
    return () => { cancelado = true; };
  }, [
    showTransferModal,
    transferForm.cuenta_origen_id,
    transferForm.cuenta_destino_id,
    transferForm.fecha,
    transferMultimoneda,
    transferTasaManual,
    monedaCopId,
    transferMonedaSalida,
    transferMonedaDestino,
  ]);

  const abrirTransfer = () => {
    setTransferForm(emptyTransferForm());
    setTransferTasaManual(false);
    setShowTransferModal(true);
  };

  const invertirTasa = () => {
    setTransferForm({
      ...transferForm,
      tasa_conversion: transferTasaInput > 0 ? String(1 / transferTasaInput) : '',
      tasa_invertida: !transferForm.tasa_invertida,
    });
    setTransferTasaManual(true);
  };

  const guardarTransferencia = async () => {
    if (!transferForm.cuenta_origen_id || !transferForm.cuenta_destino_id) {
      setError('Selecciona la cuenta de origen y la de destino.');
      return;
    }
    if (transferForm.cuenta_origen_id === transferForm.cuenta_destino_id) {
      setError('La cuenta de origen y la de destino deben ser distintas.');
      return;
    }
    if (!transferMontoValido) {
      setError('El monto debe ser mayor a 0.');
      return;
    }
    if (!transferTasaValida) {
      setError('Escribe la tasa de cambio de la transferencia.');
      return;
    }
    if (!transferEntradaValida) {
      setError('El interés deja en cero o negativo lo que entra a la cuenta destino.');
      return;
    }
    if (transferSaldoExcede) {
      setError('La cuenta de origen no tiene saldo suficiente para ese monto.');
      return;
    }
    const payload: TransferenciaPayload = {
      cuenta_origen_id: transferForm.cuenta_origen_id,
      cuenta_destino_id: transferForm.cuenta_destino_id,
      monto: Number(transferForm.monto),
      fecha: transferForm.fecha,
      moneda_id: transferMonedaSalida,
      tasa_conversion: transferMultimoneda ? Number(transferTasaConversion) : null,
      tasa_cambio: transferNecesitaTasaCop && transferForm.tasa_cambio
        ? Number(transferForm.tasa_cambio)
        : null,
      interes: transferInteresMonto > 0 ? transferInteresMonto : null,
      interes_signo: transferForm.interes_signo,
      persona_entidad: transferForm.persona_entidad.trim() || null,
      referencia: transferForm.referencia.trim() || null,
      concepto: transferForm.concepto.trim() || null,
    };
    try {
      await cuentasService.transferir(payload);
      setShowTransferModal(false);
      cargarTodo();
    } catch (e: any) {
      setError(e?.response?.data?.detail ?? 'Error al registrar la transferencia.');
    }
  };

  const confirmMovEsTransferencia = confirmAccion?.tipo === 'movimiento'
    && !!movimientos.find((m) => m.id === confirmAccion.id)?.transferencia_id;

  const renderAccionesMov = (m: MovimientoCaja) => (
    <>
      <Button
        variant="ghost"
        size="sm"
        className="text-yeikar-primary-dark"
        onClick={(e) => { e.stopPropagation(); abrirMovimiento(m.metodo_caja_id, m); }}
      >
        Editar
      </Button>
      <Button
        variant="ghost"
        size="sm"
        className="text-red-600 hover:text-red-700 hover:bg-red-50"
        onClick={(e) => { e.stopPropagation(); setConfirmAccion({ tipo: 'movimiento', id: m.id }); }}
      >
        Eliminar
      </Button>
    </>
  );

  const movColumns: DataColumn<MovimientoCaja>[] = [
    {
      key: 'fecha',
      header: 'Fecha',
      render: (m) => <span className="font-mono text-xs text-yeikar-neutral/50">{m.fecha.slice(0, 10)}</span>,
      mobilePrimary: true,
    },
    {
      key: 'cuenta',
      header: 'Cuenta',
      render: (m) => <span className="font-bold text-yeikar-secondary">{m.metodo_caja?.nombre ?? '-'}</span>,
      mobileSecondary: true,
    },
    {
      key: 'tipo',
      header: 'Tipo',
      render: (m) => <Badge tone={TIPO_TONE[m.tipo] ?? 'neutral'}>{m.tipo}</Badge>,
      mobileHidden: true,
    },
    {
      key: 'monto',
      header: 'Monto',
      align: 'right',
      render: (m) => (
        <div className="flex flex-col items-end">
          <span className="font-mono font-semibold">{monedaDe(m.moneda_id)?.simbolo ?? ''}{fmt(Number(m.monto))}</span>
          {m.tipo === 'ENTRADA' && m.interes != null && Number(m.interes) !== 0 && (
            <span className={`text-[10px] font-medium ${Number(m.interes) > 0 ? 'text-green-700' : 'text-red-600'}`}>
              incl. interés {Number(m.interes) > 0 ? '+' : '−'}
              {fmtMoneda(Math.abs(Number(m.interes)), m.moneda?.codigo)}
            </span>
          )}
        </div>
      ),
      mobileLabel: 'Monto',
    },
    {
      key: 'persona_entidad',
      header: 'Persona o entidad',
      render: (m) => (
        <span className="font-medium text-yeikar-secondary">
          {m.persona_entidad || '—'}
        </span>
      ),
      mobileLabel: 'Persona o entidad',
    },
    {
      key: 'concepto',
      header: 'Concepto',
      render: (m) => (
        <span className="text-yeikar-neutral/60 max-w-xs truncate" title={m.concepto ?? ''}>
          {m.concepto || '—'}
        </span>
      ),
      mobileLabel: 'Concepto',
      mobileFull: true,
    },
    {
      key: 'responsable',
      header: 'Responsable',
      render: (m) => <span>{m.usuario?.nombre || m.usuario?.nombre_usuario || '-'}</span>,
      mobileLabel: 'Responsable',
    },
  ];

  return (
    <div className="space-y-6">
      <PageHeader
        eyebrow="Finanzas"
        title="Cuentas y Medios de Pago"
        subtitle={vista === 'libro'
          ? 'Libro de caja con tipo, concepto, ingreso, egreso y saldo corrido'
          : `${resumen.length} cuentas · ${movimientos.length} movimientos en el filtro`}
        actions={
          <>
            <Button variant="outline" onClick={() => setShowReporteModal(true)}>
              <svg className="w-4 h-4" fill="none" stroke="currentColor" viewBox="0 0 24 24">
                <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M12 10v6m0 0l-3-3m3 3l3-3M4 18V7a2 2 0 012-2h5l2 2h5a2 2 0 012 2v9a2 2 0 01-2 2H6a2 2 0 01-2-2z" />
              </svg>
              Reporte
            </Button>
            <Button variant="outline" onClick={abrirTransfer}>
              <svg className="w-4 h-4" fill="none" stroke="currentColor" viewBox="0 0 24 24">
                <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2.5} d="M8 7h12m0 0l-4-4m4 4l-4 4m0 6H4m0 0l4 4m-4-4l4-4" />
              </svg>
              Transferir
            </Button>
            <Button onClick={() => abrirCuenta()}>
              <svg className="w-4 h-4" fill="none" stroke="currentColor" viewBox="0 0 24 24">
                <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2.5} d="M12 4v16m8-8H4" />
              </svg>
              Nueva Cuenta
            </Button>
          </>
        }
      />

      {/* El "apartadito": Libro de caja ↔ Cuentas y saldos */}
      <div className="flex items-center gap-1 bg-white border border-yeikar-secondary-light/10 rounded-xl p-1 shadow-card w-fit">
        <button
          type="button"
          onClick={() => setVista('libro')}
          className={`px-4 py-1.5 rounded-lg text-sm font-bold font-headline transition-colors ${
            vista === 'libro'
              ? 'bg-yeikar-primary text-yeikar-neutral shadow-sm'
              : 'text-yeikar-neutral/50 hover:text-yeikar-secondary hover:bg-yeikar-tertiary'
          }`}
        >
          Libro de caja
        </button>
        <button
          type="button"
          onClick={() => setVista('cuentas')}
          className={`px-4 py-1.5 rounded-lg text-sm font-bold font-headline transition-colors ${
            vista === 'cuentas'
              ? 'bg-yeikar-primary text-yeikar-neutral shadow-sm'
              : 'text-yeikar-neutral/50 hover:text-yeikar-secondary hover:bg-yeikar-tertiary'
          }`}
        >
          Cuentas y saldos
        </button>
      </div>

      {error && (
        <div className="bg-red-50 border border-red-200 text-red-700 px-4 py-3 rounded-xl text-sm animate-fade-in">
          {error}
        </div>
      )}

      {vista === 'libro' ? (
        <LibroCajaView cuentas={resumen} onFiltroChange={handleLibroFiltro} />
      ) : (
        <>
      <div className="grid grid-cols-1 gap-5">
        <StatCard
          label="Cuentas activas"
          value={resumen.filter((r) => r.metodo_caja.activo).length}
          accent="from-yeikar-secondary to-yeikar-secondary-light"
          hint={`${resumen.filter((r) => !r.metodo_caja.activo).length} inactivas`}
        />
      </div>

      {/* Tarjetas por cuenta */}
      <div className="grid grid-cols-1 md:grid-cols-2 xl:grid-cols-3 gap-5">
        {loading && resumen.length === 0 ? (
          <div className="col-span-full py-10">
            <Spinner label="Cargando cuentas..." />
          </div>
        ) : resumen.map((r) => (
          <div
            key={r.metodo_caja.id}
            className={`card p-4 flex flex-col gap-3 hover:shadow-lift transition-shadow ${!r.metodo_caja.activo ? 'opacity-70' : ''}`}
          >
            <div className={`absolute top-0 left-0 right-0 h-1 rounded-t-2xl ${r.metodo_caja.activo ? 'bg-gradient-to-r from-yeikar-primary to-yeikar-primary-light' : 'bg-yeikar-secondary-light/20'}`} />
            <div className="flex items-start justify-between">
              <div>
                <h3 className="font-black font-headline text-yeikar-secondary">{r.metodo_caja.nombre}</h3>
                <p className="text-xs text-yeikar-neutral/40 font-mono uppercase tracking-widest">{r.metodo_caja.codigo}</p>
              </div>
              {!r.metodo_caja.activo && (
                <Badge tone="neutral" className="text-[10px]">Inactiva</Badge>
              )}
            </div>
            <div className="space-y-1">
              {r.saldo_por_moneda.length === 0 ? (
                <p className="text-sm text-yeikar-neutral/40 italic">Sin movimientos</p>
              ) : r.saldo_por_moneda.map((l) => {
                const label = r.metodo_caja.moneda_codigo || nombreMoneda(l.codigo);
                const sym = r.metodo_caja.moneda_simbolo || l.simbolo;
                return (
                  <div key={l.moneda_id} className="flex justify-between text-sm">
                    <span className="text-yeikar-neutral/50">{label}</span>
                    <span className="font-mono font-semibold">
                      {sym} {fmt(Number(l.monto))}
                    </span>
                  </div>
                );
              })}
            </div>
            <div className="flex gap-2 mt-auto">
              <Button size="sm" className="flex-1" onClick={() => abrirMovimiento(r.metodo_caja.id)}>
                + Movimiento
              </Button>
              <Button variant="outline" size="sm" onClick={() => abrirCuenta(r.metodo_caja)}>
                Editar
              </Button>
              <Button
                variant="danger"
                size="sm"
                onClick={() => setConfirmAccion({ tipo: 'cuenta', id: r.metodo_caja.id, nombre: r.metodo_caja.nombre })}
              >
                Eliminar
              </Button>
            </div>
          </div>
        ))}
      </div>

      {/* Historial de movimientos */}
      <Card
        title="Movimientos"
        bodyClassName="p-0"
        action={
          <div className="flex flex-wrap items-center gap-2">
            <SearchSelect
              value={filtroCuenta}
              onChange={(v) => setFiltroCuenta(v === '' ? '' : Number(v))}
              className="w-52"
              options={[
                { value: '', label: 'Todas las cuentas' },
                ...resumen.map((r) => ({ value: r.metodo_caja.id, label: `${r.metodo_caja.nombre} · ${r.metodo_caja.moneda_codigo || '?'}` })),
              ]}
              placeholder="Todas las cuentas"
            />
            <Select
              value={filtroTipo}
              onChange={(e) => setFiltroTipo(e.target.value)}
              className="w-auto py-1.5 text-xs"
            >
              {TIPOS.map((t) => <option key={t.key} value={t.key}>{t.label}</option>)}
            </Select>
            <Input type="date" value={fechaDesde} onChange={(e) => setFechaDesde(e.target.value)} className="w-auto py-1.5 text-xs" />
            <Input type="date" value={fechaHasta} onChange={(e) => setFechaHasta(e.target.value)} className="w-auto py-1.5 text-xs" />
          </div>
        }
      >
        {loading ? (
          <div className="p-8 flex justify-center">
            <Spinner size="sm" />
          </div>
        ) : (
          <ResponsiveDataTable
            columns={movColumns}
            rows={movimientos}
            rowKey={(m) => m.id}
            onRowClick={(m) => setDetalleMov(m)}
            cardBadge={(m) => <Badge tone={TIPO_TONE[m.tipo] ?? 'neutral'}>{m.tipo}</Badge>}
            tableActions={renderAccionesMov}
            cardActions={renderAccionesMov}
            empty={
              <div className="p-8">
                <EmptyState
                  compact
                  icon={
                    <svg className="w-7 h-7" fill="none" stroke="currentColor" viewBox="0 0 24 24">
                      <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M3 6l3 1m0 0l-3 9a5.002 5.002 0 006.001 0M6 7l3 9M6 7l6-2m6 2l3-1m-3 1l-3 9a5.002 5.002 0 006.001 0M18 7l3 9m-3-9l-6-2m0 0a2 2 0 11-4 0m4 0a2 2 0 10-4 0" />
                    </svg>
                  }
                  title="Sin movimientos"
                  description="No hay movimientos con los filtros actuales."
                />
              </div>
            }
          />
        )}
      </Card>

        </>
      )}

      {/* Modal cuenta */}
      <Modal
        open={showCuentaModal}
        onClose={() => setShowCuentaModal(false)}
        title={editCuenta ? 'Editar Cuenta' : 'Nueva Cuenta'}
        subtitle="Define un medio de pago para registrar movimientos"
        size="md"
        footer={
          <>
            <Button variant="outline" onClick={() => setShowCuentaModal(false)}>Cancelar</Button>
            <Button onClick={guardarCuenta}>Guardar Cuenta</Button>
          </>
        }
      >
        <div className="space-y-4">
          <Field label="Nombre" required>
            <Input
              value={cuentaForm.nombre}
              onChange={(e) => setCuentaForm({ ...cuentaForm, nombre: e.target.value })}
              placeholder="Ej: Zelle, Nequi, Bancolombia..."
            />
          </Field>
          <Field label="Código" required>
            <Input
              value={cuentaForm.codigo}
              onChange={(e) => setCuentaForm({ ...cuentaForm, codigo: e.target.value })}
              placeholder="Ej: ZELLE, NEQUI"
            />
          </Field>
          <Field label="Moneda" required hint="Solo se podrán cobrar pagos en esta moneda hacia esta cuenta.">
            <Select
              value={cuentaForm.moneda_id ?? ''}
              onChange={(e) => setCuentaForm({ ...cuentaForm, moneda_id: e.target.value ? Number(e.target.value) : null })}
            >
              <option value="">Seleccione...</option>
              {monedas.map((m) => (
                <option key={m.id} value={m.id}>{m.codigo} — {m.nombre}</option>
              ))}
            </Select>
          </Field>
          <Field label="Orden">
            <Input
              type="number"
              value={cuentaForm.orden}
              onChange={(e) => setCuentaForm({ ...cuentaForm, orden: Number(e.target.value) || 1 })}
            />
          </Field>
        </div>
      </Modal>

      {/* Modal movimiento */}
      <Modal
        open={showMovModal}
        onClose={() => setShowMovModal(false)}
        title={editMov ? 'Editar Movimiento' : 'Registrar Movimiento'}
        subtitle="Entrada, salida, apertura o ajuste de caja"
        size="xl"
        footer={
          <>
            <Button variant="outline" onClick={() => setShowMovModal(false)}>Cancelar</Button>
            <Button onClick={guardarMovimiento}>Guardar Movimiento</Button>
          </>
        }
      >
        <div className="space-y-4">
          <Field label="Cuenta" required>
            <SearchSelect
              value={movForm.metodo_caja_id}
              onChange={(v) => {
                const cuenta = resumen.find((r) => r.metodo_caja.id === Number(v));
                setMovForm((prev) => ({
                  ...prev,
                  metodo_caja_id: Number(v),
                  // La moneda del movimiento sigue a la moneda propia de la cuenta.
                  moneda_id: cuenta?.metodo_caja.moneda_id || prev.moneda_id,
                }));
              }}
              options={[
                { value: 0, label: 'Seleccione...' },
                ...resumen.map((r) => ({
                  value: r.metodo_caja.id,
                  label: `${r.metodo_caja.nombre} · ${r.metodo_caja.moneda_codigo || '?'}${r.metodo_caja.activo ? '' : ' (inactiva)'}`,
                })),
              ]}
              placeholder="Seleccione..."
            />
          </Field>
          <div className="grid grid-cols-2 gap-4">
            <Field label="Tipo" required>
              <Select
                value={movForm.tipo}
                onChange={(e) => {
                  const tipo = e.target.value as MovimientoCreate['tipo'];
                  setMovForm((prev) => ({
                    ...prev,
                    tipo,
                    // La clasificación es solo para salidas.
                    clasificacion: tipo === 'SALIDA' ? prev.clasificacion : '',
                  }));
                }}
              >
                <option value="APERTURA">Apertura</option>
                <option value="ENTRADA">Entrada (entró dinero)</option>
                <option value="SALIDA">Salida (salió dinero)</option>
                <option value="AJUSTE">Ajuste</option>
              </Select>
            </Field>
            <Field label="Fecha" required>
              <Input
                type="date"
                value={movForm.fecha}
                onChange={(e) => setMovForm({ ...movForm, fecha: e.target.value })}
              />
            </Field>
          </div>
          {!editMov && movForm.tipo === 'SALIDA' && (
            <Field
              label="Tipo de gasto (opcional)"
              hint="Si lo eliges, la salida queda registrada también como Gasto clasificado (aparece en Gastos y reportes)."
            >
              <Select
                value={movForm.clasificacion}
                onChange={(e) => setMovForm({ ...movForm, clasificacion: e.target.value })}
              >
                <option value="">Sin clasificar</option>
                {CLASIFICACIONES_GASTO.map((c) => (
                  <option key={c.value} value={c.value}>{c.label}</option>
                ))}
              </Select>
            </Field>
          )}
          <Field label="Monto" required>
            <Input
              type="text"
              inputMode="decimal"
              value={movForm.monto}
              onChange={(e) => setMovForm({ ...movForm, monto: formatMontoInput(e.target.value) })}
              placeholder="0"
            />
          </Field>
          <Field
            label="Persona o entidad"
            hint="Cliente, proveedor, empleado, familiar... Es la otra parte del movimiento, no quien lo registra."
          >
            <Input
              value={movForm.persona_entidad}
              onChange={(e) => setMovForm({ ...movForm, persona_entidad: e.target.value })}
              placeholder="Ej: DOÑA ROSA, CAMARA DE COMERCIO, un cliente..."
            />
          </Field>
          <Field label="Concepto">
            <Textarea
              rows={2}
              value={movForm.concepto}
              onChange={(e) => setMovForm({ ...movForm, concepto: e.target.value })}
              placeholder="Ej: pago de mercado, compra de madera, abono de cliente..."
            />
          </Field>
        </div>
      </Modal>

      {/* Modal transferencia */}
      <Modal
        open={showTransferModal}
        onClose={() => setShowTransferModal(false)}
        title="Transferir entre Cuentas"
        subtitle="Sale de una cuenta y entra en la otra; si cambias de moneda, la tasa manda"
        size="lg"
        footer={
          <>
            <Button variant="outline" onClick={() => setShowTransferModal(false)}>Cancelar</Button>
            <Button onClick={guardarTransferencia}>Transferir</Button>
          </>
        }
      >
        <div className="space-y-4">
          <div className="grid grid-cols-2 gap-4">
            <Field label="Cuenta origen" required>
              <SearchSelect
                value={transferForm.cuenta_origen_id}
                onChange={(v) => {
                  const origenId = Number(v);
                  setTransferForm({
                    ...transferForm,
                    cuenta_origen_id: origenId,
                    tasa_conversion: '',
                    tasa_invertida: sugerirTasaInvertida(origenId, transferForm.cuenta_destino_id),
                    tasa_cambio: '',
                  });
                  setTransferTasaManual(false);
                }}
                options={[
                  { value: 0, label: 'Seleccione...' },
                  ...resumen.filter((r) => r.metodo_caja.activo).map((r) => ({
                    value: r.metodo_caja.id,
                    label: `${r.metodo_caja.nombre} · ${r.metodo_caja.moneda_codigo || '?'}`,
                  })),
                ]}
                placeholder="De dónde sale el dinero..."
              />
            </Field>
            <Field label="Cuenta destino" required>
              <SearchSelect
                value={transferForm.cuenta_destino_id}
                onChange={(v) => {
                  const destinoId = Number(v);
                  setTransferForm({
                    ...transferForm,
                    cuenta_destino_id: destinoId,
                    tasa_conversion: '',
                    tasa_invertida: sugerirTasaInvertida(transferForm.cuenta_origen_id, destinoId),
                    tasa_cambio: '',
                  });
                  setTransferTasaManual(false);
                }}
                options={[
                  { value: 0, label: 'Seleccione...' },
                  ...resumen.filter((r) => r.metodo_caja.activo && r.metodo_caja.id !== transferForm.cuenta_origen_id).map((r) => ({
                    value: r.metodo_caja.id,
                    label: `${r.metodo_caja.nombre} · ${r.metodo_caja.moneda_codigo || '?'}`,
                  })),
                ]}
                placeholder="A dónde entra el dinero..."
              />
            </Field>
          </div>

          <div className="grid grid-cols-1 min-[420px]:grid-cols-2 gap-4">
            <Field label="Monto" required>
              <MontoInput
                min="0"
                value={transferForm.monto || ''}
                onChange={(v) => setTransferForm({ ...transferForm, monto: Number(v) || 0 })}
              />
            </Field>
            <Field label="Fecha" required>
              <Input
                type="date"
                value={transferForm.fecha}
                onChange={(e) => {
                  setTransferForm({ ...transferForm, fecha: e.target.value, tasa_conversion: '', tasa_cambio: '' });
                  setTransferTasaManual(false);
                }}
              />
            </Field>
          </div>

          {transferMultimoneda && transferForm.cuenta_origen_id > 0 && transferForm.cuenta_destino_id > 0 && (
            <Field
              label={transferEtiquetaTasa}
              hint={transferTasaHint}
            >
              <div className="flex gap-2">
                <Input
                  type="number"
                  step="0.000001"
                  min="0"
                  value={transferForm.tasa_conversion}
                  onChange={(e) => {
                    setTransferForm({ ...transferForm, tasa_conversion: e.target.value });
                    setTransferTasaManual(true);
                  }}
                  placeholder={transferForm.tasa_invertida ? 'Ej: 4000' : 'Ej: 0.00025'}
                />
                <Button type="button" variant="outline" onClick={invertirTasa} title="Invertir la dirección de la tasa">
                  Invertir
                </Button>
              </div>
            </Field>
          )}

          {transferNecesitaTasaCop && (
            <Field
              label={`Tasa ${transferCodigoOrigen} → COP (opcional)`}
              hint="Si la dejas vacía se usa la TRM registrada del día."
            >
              <Input
                type="number"
                step="0.01"
                min="0"
                value={transferForm.tasa_cambio}
                onChange={(e) => setTransferForm({ ...transferForm, tasa_cambio: e.target.value })}
                placeholder="Tasa del día (auto)"
              />
            </Field>
          )}

          {transferForm.cuenta_origen_id > 0 && (
            <p className="text-sm text-yeikar-neutral/50">
              Disponible en origen:{' '}
              <span className={`font-mono font-semibold ${transferSaldoExcede ? 'text-red-600' : 'text-yeikar-primary-dark'}`}>
                {transferCuenta(transferForm.cuenta_origen_id)?.moneda_simbolo || ''} {fmt(transferSaldoDisponible)}
              </span>
              {transferSaldoExcede && transferMontoValido && (
                <span className="text-red-600 font-semibold"> · saldo insuficiente</span>
              )}
            </p>
          )}

          <div className="grid grid-cols-1 min-[420px]:grid-cols-[1fr_180px] gap-4">
            <Field
              label={`Interés (opcional, en ${transferForm.cuenta_destino_id > 0 ? transferCodigoDestino : 'la moneda destino'})`}
              hint="Se aplica a lo que entra a la cuenta destino; puede sumar o restar."
            >
              <MontoInput
                min="0"
                value={transferForm.interes}
                onChange={(v) => setTransferForm({ ...transferForm, interes: v })}
                placeholder="0"
              />
            </Field>
            <Field label="Efecto del interés">
              <Select
                value={transferForm.interes_signo}
                onChange={(e) => setTransferForm({
                  ...transferForm,
                  interes_signo: e.target.value as 'SUMA' | 'RESTA',
                })}
              >
                <option value="RESTA">Resta (se descuenta)</option>
                <option value="SUMA">Suma (se agrega)</option>
              </Select>
            </Field>
          </div>

          <Field
            label="Persona o entidad (tercero)"
            hint="Banco, prestamista, intermediario... Opcional."
          >
            <Input
              value={transferForm.persona_entidad}
              onChange={(e) => setTransferForm({ ...transferForm, persona_entidad: e.target.value })}
              placeholder="Ej: Banco XYZ, prestamista..."
            />
          </Field>

          {transferFormListo && (
            <div className="space-y-1.5 rounded-xl border border-yeikar-secondary-light/20 bg-yeikar-tertiary/30 p-4 text-sm">
              <div className="flex items-start justify-between gap-3">
                <span className="text-yeikar-neutral/55">
                  Sale de {transferCuenta(transferForm.cuenta_origen_id)?.nombre ?? '—'}
                </span>
                <span className="font-mono font-semibold">
                  {fmtMoneda(transferForm.monto, transferCodigoOrigen)}
                </span>
              </div>
              {transferMultimoneda && (
                <div className="flex items-start justify-between gap-3">
                  <span className="text-yeikar-neutral/55">Tasa aplicada</span>
                  <span className="font-mono">
                    1 {transferCodigoOrigen} = {fmtTasa(transferTasaConversion)} {transferCodigoDestino}
                  </span>
                </div>
              )}
              {transferInteresMonto > 0 && (
                <div className="flex items-start justify-between gap-3">
                  <span className="text-yeikar-neutral/55">
                    Interés ({transferForm.interes_signo === 'SUMA' ? 'suma' : 'resta'})
                  </span>
                  <span className={`font-mono ${transferForm.interes_signo === 'SUMA' ? 'text-green-700' : 'text-red-600'}`}>
                    {transferForm.interes_signo === 'SUMA' ? '+' : '−'}
                    {fmtMoneda(transferInteresMonto, transferCodigoDestino)}
                  </span>
                </div>
              )}
              <div className="flex items-start justify-between gap-3 border-t border-yeikar-secondary-light/20 pt-1.5">
                <span className="text-yeikar-neutral/55">
                  Llega a {transferCuenta(transferForm.cuenta_destino_id)?.nombre ?? '—'}
                </span>
                <span className={`font-mono font-bold ${transferEntradaValida ? 'text-yeikar-primary-dark' : 'text-red-600'}`}>
                  {transferMontoEntradaFmt}
                </span>
              </div>
              {!transferEntradaValida && (
                <p className="text-xs text-red-600">
                  El interés deja en cero o negativo lo que entra a la cuenta destino.
                </p>
              )}
            </div>
          )}

          <Field label="Referencia">
            <Input
              value={transferForm.referencia}
              onChange={(e) => setTransferForm({ ...transferForm, referencia: e.target.value })}
              placeholder="Ej: consignación Banco → caja, arqueo de fin de día"
            />
          </Field>
          <Field label="Concepto">
            <Textarea
              rows={2}
              value={transferForm.concepto}
              onChange={(e) => setTransferForm({ ...transferForm, concepto: e.target.value })}
              placeholder="Ej: consignación Banco → caja, arqueo de fin de día"
            />
          </Field>
        </div>
      </Modal>

      {/* Detalle del movimiento */}
      <Modal
        open={detalleMov !== null}
        onClose={() => setDetalleMov(null)}
        title="Detalle del Movimiento"
        subtitle={detalleMov ? `${detalleMov.metodo_caja?.nombre ?? '-'} · ${detalleMov.fecha.slice(0, 10)}` : undefined}
        size="md"
        footer={
          <div className="flex flex-wrap justify-end gap-2">
            {detalleMov && (detalleMov.pago_id || detalleMov.transferencia_id) && (
              <span className="mr-auto self-center text-xs text-yeikar-neutral/45">
                Se genera desde {detalleMov.pago_id ? 'un pago' : 'una transferencia'}; corrígelo desde su origen.
              </span>
            )}
            <Button variant="outline" onClick={() => setDetalleMov(null)}>Cerrar</Button>
            {detalleMov && !detalleMov.pago_id && !detalleMov.transferencia_id && (
              <Button
                onClick={() => {
                  const mov = detalleMov;
                  setDetalleMov(null);
                  abrirMovimiento(mov.metodo_caja_id, mov);
                }}
              >
                Editar movimiento
              </Button>
            )}
          </div>
        }
      >
        {detalleMov && (
          <div className="space-y-5">
            <div className="rounded-xl border border-yeikar-secondary-light/20 bg-yeikar-tertiary/30 p-4">
              <div className="flex items-center justify-between gap-2">
                <span className="font-mono text-[10px] uppercase tracking-widest text-yeikar-neutral/45">
                  {detalleMov.metodo_caja?.codigo ?? ''}
                </span>
                <Badge tone={TIPO_TONE[detalleMov.tipo] ?? 'neutral'}>{detalleMov.tipo}</Badge>
              </div>
              <p className="mt-2 font-mono text-3xl font-bold text-yeikar-secondary">
                {monedaDe(detalleMov.moneda_id)?.simbolo ?? ''}{fmt(Number(detalleMov.monto))}
                <span className="ml-1.5 text-sm font-normal text-yeikar-neutral/50">
                  {monedaDe(detalleMov.moneda_id)?.codigo ?? ''}
                </span>
              </p>
            </div>

            <dl className="space-y-3">
              <DetalleFila label="Cuenta">
                {detalleMov.metodo_caja?.nombre ?? '-'}
                <span className="ml-1 font-mono text-xs text-yeikar-neutral/40">
                  {monedaDe(detalleMov.metodo_caja?.moneda_id ?? detalleMov.moneda_id)?.codigo ?? ''}
                </span>
              </DetalleFila>
              <DetalleFila label="Fecha">
                <span className="font-mono">{detalleMov.fecha.slice(0, 10)}</span>
              </DetalleFila>
              <DetalleFila label="Registrado">
                {detalleMov.created_at
                  ? new Date(detalleMov.created_at).toLocaleString('es-CO', { dateStyle: 'medium', timeStyle: 'short' })
                  : '—'}
              </DetalleFila>
              <DetalleFila label="Responsable">
                {detalleMov.usuario?.nombre || detalleMov.usuario?.nombre_usuario || (detalleMov.usuario_id ? `Usuario #${detalleMov.usuario_id}` : 'Sistema')}
              </DetalleFila>
              <DetalleFila label="Persona o entidad">
                {detalleMov.persona_entidad || '—'}
              </DetalleFila>
              {detalleMov.tasa_conversion != null && Number(detalleMov.tasa_conversion) !== 1 && (
                <DetalleFila label="Tasa de conversión">
                  <span className="font-mono">
                    {fmtTasa(Number(detalleMov.tasa_conversion))}
                  </span>
                  <span className="ml-1 text-xs text-yeikar-neutral/40">(destino por 1 de origen)</span>
                </DetalleFila>
              )}
              {detalleMov.interes != null && Number(detalleMov.interes) !== 0 && (
                <DetalleFila label="Interés">
                  <span className={Number(detalleMov.interes) > 0 ? 'font-semibold text-green-700' : 'font-semibold text-red-600'}>
                    {Number(detalleMov.interes) > 0 ? '+' : '−'}
                    {detalleMov.tipo === 'ENTRADA'
                      ? fmtMoneda(Math.abs(Number(detalleMov.interes)), detalleMov.moneda?.codigo)
                      : Number(Math.abs(Number(detalleMov.interes))).toLocaleString('es-CO', { maximumFractionDigits: 2 })}
                  </span>
                  {detalleMov.tipo !== 'ENTRADA' && (
                    <span className="ml-1 text-xs text-yeikar-neutral/40">(en moneda destino)</span>
                  )}
                </DetalleFila>
              )}
              <DetalleFila label="Concepto">
                {detalleMov.concepto || '—'}
              </DetalleFila>
              {(detalleMov.pago_id || detalleMov.transferencia_id) && (
                <DetalleFila label="Origen">
                  {detalleMov.pago_id
                    ? `Cobro de venta · pago #${detalleMov.pago_id}`
                    : `Transferencia #T${detalleMov.transferencia_id} (sale de una cuenta y entra en la otra)`}
                </DetalleFila>
              )}
            </dl>
          </div>
        )}
      </Modal>

      {/* Reporte del libro de caja (PDF / Excel) */}
      <ReporteCuentasModal
        open={showReporteModal}
        onClose={() => setShowReporteModal(false)}
        cuentas={resumen}
        cuentaInicialId={reporteDefaults?.cuentaId}
        desdeInicial={reporteDefaults?.desde}
        hastaInicial={reporteDefaults?.hasta}
      />

      <ConfirmDialog
        open={confirmAccion !== null}
        title={confirmAccion?.tipo === 'cuenta' ? 'Eliminar cuenta' : 'Eliminar movimiento'}
        message={
          confirmAccion?.tipo === 'cuenta'
            ? `¿Eliminar la cuenta "${confirmAccion.nombre}"? Los movimientos asociados se conservan.`
            : confirmMovEsTransferencia
              ? 'Este movimiento es la pata de una transferencia: se eliminarán ambas patas (la salida y la entrada).'
              : '¿Eliminar este movimiento?'
        }
        confirmLabel="Eliminar"
        onConfirm={() => {
          if (!confirmAccion) return;
          if (confirmAccion.tipo === 'cuenta') eliminarCuenta(confirmAccion.id);
          else eliminarMovimiento(confirmAccion.id);
        }}
        onCancel={() => setConfirmAccion(null)}
      />
    </div>
  );
}
