import { useState, useEffect, useCallback } from 'react';
import {
  getGastos, getTiposGasto, getMonedas, createGasto, deleteGasto, createTipoGasto, getAreas,
  Gasto, GastoCreate, TipoGasto, Moneda, Area,
} from '../services/gastoService';
import { cuentasService, ResumenCuenta } from '../services/cuentasService';
import {
  cuentasPorPagarService, CuentaPorPagar, ResumenCuentasPorPagar, Abono,
} from '../services/cuentasPorPagarService';
import { nombreMoneda, fmtMoneda } from '../utils/format';
import { subirAdjunto, TIPO_ADJUNTO } from '../services/adjuntosService';
import AdjuntoImagen from '../components/AdjuntoImagen';
import { useToast } from '../context/ToastContext';
import {
  Button, Card, Badge, Spinner, EmptyState, StatCard, Modal, PageHeader,
  Field, Input, Select, Textarea, ConfirmDialog, SearchSelect,
  ResponsiveDataTable, type DataColumn,
} from '../components/ui';

const CATEGORIAS = [
  { key: '', label: 'Todos' },
  { key: 'OPERATIVO', label: 'Operativos' },
  { key: 'PASIVO', label: 'Pasivos' },
  { key: 'PRODUCCION', label: 'Producción' },
];

const CAT_TONE: Record<string, 'blue' | 'red' | 'green' | 'neutral'> = {
  OPERATIVO: 'blue',
  PASIVO: 'red',
  PRODUCCION: 'green',
};

const hoy = () => new Date().toISOString().split('T')[0];

export default function Gastos() {
  const toast = useToast();
  // "apartadito": la página vive en Egresos y Gastos pero las deudas (fiar)
  // se manejan en su propia vista.
  const [vista, setVista] = useState<'gastos' | 'por-pagar'>('gastos');
  const [gastos, setGastos] = useState<Gasto[]>([]);
  const [tiposGasto, setTiposGasto] = useState<TipoGasto[]>([]);
  const [monedas, setMonedas] = useState<Moneda[]>([]);
  const [cuentas, setCuentas] = useState<ResumenCuenta[]>([]);
  const [areas, setAreas] = useState<Area[]>([]);
  const [proveedores, setProveedores] = useState<{ id: number; nombre: string }[]>([]);
  const [deudas, setDeudas] = useState<CuentaPorPagar[]>([]);
  const [resumen, setResumen] = useState<ResumenCuentasPorPagar | null>(null);
  const [categoria, setCategoria] = useState('');
  const [areaFiltro, setAreaFiltro] = useState('');
  const [fechaDesde, setFechaDesde] = useState('');
  const [fechaHasta, setFechaHasta] = useState('');
  const [showModal, setShowModal] = useState(false);
  const [loading, setLoading] = useState(false);
  const [confirmDeleteId, setConfirmDeleteId] = useState<number | null>(null);
  const [tipoTexto, setTipoTexto] = useState('');
  const [comprobanteArchivo, setComprobanteArchivo] = useState<File | null>(null);
  const [comprobantePreview, setComprobantePreview] = useState<string | null>(null);
  const [comprobanteVer, setComprobanteVer] = useState<{ id: number; mime: string } | null>(null);
  const [showDeudaModal, setShowDeudaModal] = useState(false);
  const [abonarDeuda, setAbonarDeuda] = useState<CuentaPorPagar | null>(null);
  const [historialDeuda, setHistorialDeuda] = useState<CuentaPorPagar | null>(null);
  const [confirmDeleteDeuda, setConfirmDeleteDeuda] = useState<number | null>(null);
  const [confirmDeleteAbono, setConfirmDeleteAbono] = useState<{ deudaId: number; abonoId: number } | null>(null);

  const [deudaForm, setDeudaForm] = useState({
    proveedor_id: 0,
    tipoTexto: '',
    moneda_id: 1,
    fecha: hoy(),
    monto: 0,
    descripcion: '',
  });
  const [abonoForm, setAbonoForm] = useState({
    fecha: hoy(),
    monto: 0,
    metodo_caja_id: 0,
    tasa_cambio: 1,
  });

  const [form, setForm] = useState<GastoCreate>({
    tipo_gasto_id: 0,
    moneda_id: 1,
    area_id: 0,
    fecha: new Date().toISOString().split('T')[0],
    monto: 0,
    tasa_cambio: 1,
    metodo_caja_id: 0,
    descripcion: '',
    observaciones: '',
  });

  const cargarGastos = useCallback(async () => {
    setLoading(true);
    try {
      const data = await getGastos({
        categoria: categoria || undefined,
        area_id: areaFiltro ? Number(areaFiltro) : undefined,
        fecha_desde: fechaDesde || undefined,
        fecha_hasta: fechaHasta || undefined,
      });
      setGastos(data);
    } finally {
      setLoading(false);
    }
  }, [categoria, fechaDesde, fechaHasta, areaFiltro]);

  const cargarCatalogos = useCallback(async () => {
    const [tipos, monedasData, cuentasData, areasData, proveedoresData] = await Promise.all([
      getTiposGasto(),
      getMonedas(),
      cuentasService.getResumen(),
      getAreas(),
      cuentasPorPagarService.getProveedores().catch(() => [] as any[]),
    ]);
    setTiposGasto(tipos);
    setMonedas(monedasData);
    setCuentas(cuentasData);
    setAreas(areasData);
    setProveedores(proveedoresData);
    setForm((prev) => ({
      ...prev,
      metodo_caja_id: prev.metodo_caja_id === 0 ? cuentasData[0]?.metodo_caja.id || 0 : prev.metodo_caja_id,
      // La moneda del gasto arranca en la moneda propia de la cuenta por defecto.
      moneda_id: cuentasData[0]?.metodo_caja.moneda_id || prev.moneda_id,
    }));
    setAbonoForm((prev) => ({
      ...prev,
      metodo_caja_id: prev.metodo_caja_id === 0 ? cuentasData[0]?.metodo_caja.id || 0 : prev.metodo_caja_id,
    }));
  }, []);

  const cargarPorPagar = useCallback(async () => {
    const [deudasData, resumenData] = await Promise.all([
      cuentasPorPagarService.getAll(),
      cuentasPorPagarService.getResumen(),
    ]);
    setDeudas(deudasData);
    setResumen(resumenData);
  }, []);

  useEffect(() => {
    cargarCatalogos();
  }, [cargarCatalogos]);

  useEffect(() => {
    if (vista === 'por-pagar') cargarPorPagar();
  }, [vista, cargarPorPagar]);

  useEffect(() => {
    cargarGastos();
  }, [cargarGastos]);

  // Resuelve el motivo escrito: usa un TipoGasto existente (por nombre) o lo crea
  // sobre la marcha para no limitar a una lista fija.
  const resolverTipoGasto = async (nombre: string): Promise<number> => {
    const limpio = nombre.trim();
    const existente = tiposGasto.find((t) => t.nombre.trim().toLowerCase() === limpio.toLowerCase());
    if (existente) return existente.id;
    const nuevo = await createTipoGasto({ nombre: limpio, categoria: categoria || 'OPERATIVO' });
    setTiposGasto((prev) => [...prev, nuevo]);
    return nuevo.id;
  };

  const handleCrear = async () => {
    if (!tipoTexto.trim() || !form.monto || form.monto <= 0) return;
    if (!form.metodo_caja_id) return;
    const tipo_gasto_id = await resolverTipoGasto(tipoTexto);
    const gastoCreado = await createGasto({ ...form, tipo_gasto_id, area_id: form.area_id ? form.area_id : null });
    // Comprobante digital (opcional): evidencia del egreso
    if (comprobanteArchivo && gastoCreado) {
      await subirAdjunto(comprobanteArchivo, TIPO_ADJUNTO.GASTO, gastoCreado.id);
    }
    setShowModal(false);
    setTipoTexto('');
    setComprobanteArchivo(null);
    if (comprobantePreview) URL.revokeObjectURL(comprobantePreview);
    setComprobantePreview(null);
    setForm({
      tipo_gasto_id: 0,
      moneda_id: 1,
      area_id: 0,
      fecha: new Date().toISOString().split('T')[0],
      monto: 0,
      tasa_cambio: 1,
      metodo_caja_id: cuentas[0]?.metodo_caja.id || 0,
      descripcion: '',
      observaciones: '',
    });
    cargarGastos();
  };

  const handleEliminar = async (id: number) => {
    await deleteGasto(id);
    setConfirmDeleteId(null);
    cargarGastos();
  };

  // ── Por Pagar: registrar deuda manual ──
  const handleCrearDeuda = async () => {
    if (!deudaForm.proveedor_id || !deudaForm.tipoTexto.trim() || !deudaForm.monto || deudaForm.monto <= 0) {
      return;
    }
    try {
      const tipo_gasto_id = await resolverTipoGasto(deudaForm.tipoTexto);
      await cuentasPorPagarService.create({
        proveedor_id: Number(deudaForm.proveedor_id),
        tipo_gasto_id,
        moneda_id: deudaForm.moneda_id,
        fecha: deudaForm.fecha,
        descripcion: deudaForm.descripcion.trim() || null,
        monto: deudaForm.monto,
      });
      setShowDeudaModal(false);
      setDeudaForm({ proveedor_id: 0, tipoTexto: '', moneda_id: 1, fecha: hoy(), monto: 0, descripcion: '' });
      cargarPorPagar();
      toast.success('Deuda registrada. Aparecerá en Por Pagar.');
    } catch (e: any) {
      toast.error(e?.response?.data?.detail || 'No se pudo registrar la deuda.');
    }
  };

  // ── Por Pagar: abonar (parcial o pago completo) ──
  const handleAbonar = async () => {
    if (!abonarDeuda || !abonoForm.metodo_caja_id) return;
    const monto = Number(abonoForm.monto);
    if (!(monto > 0)) return;
    try {
      const cuentaAbono = cuentas.find((c) => c.metodo_caja.id === Number(abonoForm.metodo_caja_id));
      await cuentasPorPagarService.abonar(abonarDeuda.id, {
        fecha: abonoForm.fecha,
        monto,
        metodo_caja_id: Number(abonoForm.metodo_caja_id),
        tasa_cambio: cuentaAbono && cuentaAbono.metodo_caja.moneda_id !== 1 ? Number(abonoForm.tasa_cambio) : undefined,
      });
      const saldoCubierto = monto >= Number(abonarDeuda.saldo) - 0.005;
      setAbonarDeuda(null);
      setAbonoForm({ fecha: hoy(), monto: 0, metodo_caja_id: abonoForm.metodo_caja_id, tasa_cambio: 1 });
      cargarPorPagar();
      toast.success(saldoCubierto ? 'Deuda pagada por completo.' : 'Abono registrado.');
    } catch (e: any) {
      toast.error(e?.response?.data?.detail || 'No se pudo registrar el abono.');
    }
  };

  const handleEliminarDeuda = async (id: number) => {
    try {
      await cuentasPorPagarService.eliminar(id);
      toast.success('Deuda eliminada.');
    } catch (e: any) {
      toast.error(e?.response?.data?.detail || 'No se pudo eliminar la deuda.');
    }
    setConfirmDeleteDeuda(null);
    cargarPorPagar();
  };

  const handleEliminarAbono = async (abonoId: number) => {
    if (!confirmDeleteAbono) return;
    try {
      await cuentasPorPagarService.eliminarAbono(abonoId);
      toast.success('Abono revertido: el saldo volvió a la deuda.');
    } catch (e: any) {
      toast.error(e?.response?.data?.detail || 'No se pudo revertir el abono.');
    }
    setConfirmDeleteAbono(null);
    cargarPorPagar();
    const deudasRefresca = await cuentasPorPagarService.getAll();
    setHistorialDeuda(deudasRefresca.find((d) => d.id === confirmDeleteAbono.deudaId) || null);
  };

  const monedaSeleccionada = monedas.find((m) => m.id === form.moneda_id);
  const esCOP = monedaSeleccionada?.codigo === 'COP';
  const montoEnCOP = esCOP
    ? Number(form.monto) || 0
    : (Number(form.monto) || 0) * (Number(form.tasa_cambio) || 0);

  const totales = {
    total: gastos.reduce((s, g) => s + Number(g.monto_en_moneda_base), 0),
    operativos: gastos.filter((g) => g.tipo_gasto?.categoria === 'OPERATIVO').reduce((s, g) => s + Number(g.monto_en_moneda_base), 0),
    pasivos: gastos.filter((g) => g.tipo_gasto?.categoria === 'PASIVO').reduce((s, g) => s + Number(g.monto_en_moneda_base), 0),
    produccion: gastos.filter((g) => g.tipo_gasto?.categoria === 'PRODUCCION').reduce((s, g) => s + Number(g.monto_en_moneda_base), 0),
  };

  // Desglose de egresos por moneda (total en su moneda + equivalente COP)
  const porMoneda: Record<string, { codigo: string; simbolo: string; total: number; totalCOP: number; count: number }> = {};
  gastos.forEach((g) => {
    const codigo = g.moneda?.codigo || '—';
    const simbolo = g.moneda?.simbolo || '$';
    if (!porMoneda[codigo]) porMoneda[codigo] = { codigo, simbolo, total: 0, totalCOP: 0, count: 0 };
    porMoneda[codigo].total += Number(g.monto);
    porMoneda[codigo].totalCOP += Number(g.monto_en_moneda_base);
    porMoneda[codigo].count += 1;
  });
  const monedasResumen = Object.values(porMoneda).sort((a, b) => b.totalCOP - a.totalCOP);

  // ── Derivados de la vista "Por Pagar" ──
  const deudaAbonoSel = abonarDeuda;
  const cuentaAbonoSel = cuentas.find((c) => c.metodo_caja.id === Number(abonoForm.metodo_caja_id));
  const necesitaTasaAbono = !!cuentaAbonoSel && cuentaAbonoSel.metodo_caja.moneda_id !== 1;
  const abonoExcede = deudaAbonoSel ? Number(abonoForm.monto) > Number(deudaAbonoSel.saldo) + 0.005 : false;
  const deducAbono = (() => {
    if (!deudaAbonoSel || !cuentaAbonoSel || !(Number(abonoForm.monto) > 0)) return 0;
    const montoCop = Number(abonoForm.monto) * Number(deudaAbonoSel.tasa_cambio || 1);
    const tasa = necesitaTasaAbono ? Number(abonoForm.tasa_cambio) || 0 : 1;
    if (necesitaTasaAbono && !(tasa > 0)) return 0;
    return necesitaTasaAbono ? montoCop / tasa : montoCop;
  })();

  const pctAbonado = (d: CuentaPorPagar) =>
    Number(d.monto) > 0 ? Math.min(100, (Number(d.monto_pagado) / Number(d.monto)) * 100) : 0;

  // Abrir el modal de abono desde la tarjeta del proveedor: usa la deuda
  // pendiente con mayor saldo de ese proveedor (la operación abona por deuda).
  const abrirAbonoProveedor = (proveedorId: number) => {
    const deuda = deudas
      .filter((d) => d.proveedor_id === proveedorId && d.estado === 'PENDIENTE')
      .sort((a, b) => Number(b.saldo) - Number(a.saldo))[0];
    if (!deuda) {
      toast.error('Este proveedor no tiene deudas pendientes para abonar.');
      return;
    }
    setAbonarDeuda(deuda);
    setAbonoForm((prev) => ({ ...prev, monto: Number(deuda.saldo), metodo_caja_id: prev.metodo_caja_id }));
  };

  const renderAccionesDeuda = (d: CuentaPorPagar) => (
    <div className="flex flex-wrap gap-1.5">
      {d.estado === 'PENDIENTE' && (
        <Button variant="ghost" size="sm" className="text-emerald-700 hover:bg-emerald-50"
          onClick={() => { setAbonarDeuda(d); setAbonoForm((prev) => ({ ...prev, monto: Number(d.saldo), metodo_caja_id: prev.metodo_caja_id })); }}>
          Abonar
        </Button>
      )}
      {d.pagos && d.pagos.length > 0 && (
        <Button variant="ghost" size="sm" className="text-yeikar-secondary hover:bg-yeikar-tertiary/40"
          onClick={() => setHistorialDeuda(d)}>
          Historial ({d.pagos.length})
        </Button>
      )}
      <Button variant="ghost" size="sm" className="text-red-600 hover:bg-red-50"
        onClick={() => setConfirmDeleteDeuda(d.id)}>
        Eliminar
      </Button>
    </div>
  );

  const deudasColumns: DataColumn<CuentaPorPagar>[] = [
    {
      key: 'proveedor',
      header: 'Proveedor',
      render: (d) => <span className="font-bold text-yeikar-secondary">{d.proveedor?.nombre || '-'}</span>,
      mobilePrimary: true,
    },
    {
      key: 'descripcion',
      header: 'Descripción',
      render: (d) => <span className="break-words">{d.descripcion || '-'}</span>,
      mobileLabel: 'Descripción',
      mobileFull: true,
    },
    {
      key: 'fecha',
      header: 'Fecha',
      render: (d) => <span className="font-mono text-xs text-yeikar-neutral/50">{d.fecha}</span>,
      mobileLabel: 'Fecha',
    },
    {
      key: 'monto',
      header: 'Debía',
      render: (d) => <span className="font-mono font-bold">{d.moneda?.simbolo} {Number(d.monto).toLocaleString()}</span>,
      mobileLabel: 'Debía',
      align: 'right',
    },
    {
      key: 'progreso',
      header: 'Abonado',
      render: (d) => (
        <div className="min-w-[110px]">
          <div className="flex justify-between text-[10px] font-mono text-yeikar-neutral/50 mb-0.5">
            <span>{fmtMoneda(Number(d.monto_pagado), d.moneda?.codigo || 'COP')}</span>
            <span>{pctAbonado(d).toFixed(0)}%</span>
          </div>
          <div className="h-1.5 rounded-full bg-yeikar-secondary-light/10 overflow-hidden">
            <div className={`h-full rounded-full ${d.estado === 'PAGADA' ? 'bg-emerald-500' : 'bg-yeikar-primary'}`}
              style={{ width: `${pctAbonado(d)}%` }} />
          </div>
        </div>
      ),
      mobileLabel: 'Abonado',
    },
    {
      key: 'saldo',
      header: 'Saldo',
      render: (d) => (
        <span className={`font-mono font-bold ${Number(d.saldo) > 0 ? 'text-red-600' : 'text-emerald-600'}`}>
          {d.moneda?.simbolo} {Number(d.saldo).toLocaleString()}
        </span>
      ),
      mobileLabel: 'Saldo',
      align: 'right',
    },
    {
      key: 'estado',
      header: 'Estado',
      render: (d) => (
        <Badge tone={d.estado === 'PAGADA' ? 'green' : 'red'}>
          {d.estado === 'PAGADA' ? 'Pagada' : 'Por pagar'}
        </Badge>
      ),
      mobileLabel: 'Estado',
    },
  ];

  const renderAcciones = (g: Gasto) => (
    <Button
      variant="ghost"
      size="sm"
      className="text-red-600 hover:text-red-700 hover:bg-red-50"
      onClick={() => setConfirmDeleteId(g.id)}
    >
      <svg className="w-4 h-4" fill="none" stroke="currentColor" viewBox="0 0 24 24">
        <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M19 7l-.867 12.142A2 2 0 0116.138 21H7.862a2 2 0 01-1.995-1.858L5 7m5 4v6m4-6v6m1-10V4a1 1 0 00-1-1h-4a1 1 0 00-1 1v3M4 7h16" />
      </svg>
      Eliminar
    </Button>
  );

  const columns: DataColumn<Gasto>[] = [
    {
      key: 'fecha',
      header: 'Fecha',
      render: (g) => <span className="font-mono text-xs text-yeikar-neutral/50">{g.fecha}</span>,
      mobileLabel: 'Fecha',
    },
    {
      key: 'tipo',
      header: 'Tipo',
      render: (g) => <span className="font-bold text-yeikar-secondary">{g.tipo_gasto?.nombre || '-'}</span>,
      mobilePrimary: true,
    },
    {
      key: 'categoria',
      header: 'Categoría',
      render: (g) => (
        <Badge tone={CAT_TONE[g.tipo_gasto?.categoria ?? ''] ?? 'neutral'}>
          {g.tipo_gasto?.categoria || '-'}
        </Badge>
      ),
      mobileHidden: true,
    },
    {
      key: 'area',
      header: 'Área',
      render: (g) => <span className="font-medium text-yeikar-neutral/70">{g.area?.nombre || '-'}</span>,
      mobileLabel: 'Área',
    },
    {
      key: 'cuenta',
      header: 'Cuenta',
      render: (g) => <span className="font-medium text-yeikar-neutral/70">{g.metodo_caja_nombre || '-'}</span>,
      mobileLabel: 'Cuenta',
    },
    {
      key: 'descripcion',
      header: 'Descripción',
      render: (g) => <span className="break-words">{g.descripcion || '-'}</span>,
      mobileLabel: 'Descripción',
      mobileFull: true,
    },
    {
      key: 'comprobante',
      header: 'Comprobante',
      render: (g) =>
        g.comprobantes && g.comprobantes.length > 0 ? (
          <div className="flex gap-1.5">
            {g.comprobantes.map((c) => (
              <AdjuntoImagen
                key={c.id}
                adjunto={c}
                alt="comprobante"
                className="h-9 w-9 rounded-lg border border-yeikar-secondary-light/20 hover:border-yeikar-primary/50 transition-colors"
                onClick={() => setComprobanteVer({ id: c.id, mime: c.mime })}
              />
            ))}
          </div>
        ) : (
          <span className="text-[11px] text-yeikar-neutral/30">—</span>
        ),
      mobileLabel: 'Comprobante',
    },
    {
      key: 'monto',
      header: 'Monto',
      render: (g) => (
        <span className="font-mono font-bold text-yeikar-secondary">
          {g.moneda?.simbolo} {Number(g.monto).toLocaleString()}
        </span>
      ),
      mobileLabel: 'Monto',
      align: 'right',
    },
    {
      key: 'base',
      header: 'Moneda Base',
      render: (g) => <span className="font-mono">${Number(g.monto_en_moneda_base).toLocaleString()}</span>,
      mobileLabel: 'Base COP',
      align: 'right',
    },
  ];

  return (
    <div className="space-y-6">
      <PageHeader
        eyebrow="Finanzas"
        title={vista === 'gastos' ? 'Egresos y Gastos' : 'Por Pagar (Fiado)'}
        subtitle={vista === 'gastos'
          ? `${gastos.length} registros en la selección actual`
          : `${deudas.filter((d) => d.estado === 'PENDIENTE').length} deudas por pagar en total`}
        actions={
          vista === 'gastos' ? (
            <Button onClick={() => setShowModal(true)}>
              <svg className="w-4 h-4" fill="none" stroke="currentColor" viewBox="0 0 24 24">
                <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2.5} d="M12 4v16m8-8H4" />
              </svg>
              Nuevo Gasto
            </Button>
          ) : (
            <Button onClick={() => setShowDeudaModal(true)}>
              <svg className="w-4 h-4" fill="none" stroke="currentColor" viewBox="0 0 24 24">
                <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2.5} d="M12 4v16m8-8H4" />
              </svg>
              Registrar Deuda
            </Button>
          )
        }
      />

      {/* El "apartadito": Egresos y Gastos ↔ Por Pagar */}
      <div className="flex items-center gap-1 bg-white border border-yeikar-secondary-light/10 rounded-xl p-1 shadow-card w-fit">
        <button
          type="button"
          onClick={() => setVista('gastos')}
          className={`px-4 py-1.5 rounded-lg text-sm font-bold font-headline transition-colors ${
            vista === 'gastos'
              ? 'bg-yeikar-primary text-yeikar-neutral shadow-sm'
              : 'text-yeikar-neutral/50 hover:text-yeikar-secondary hover:bg-yeikar-tertiary'
          }`}
        >
          Egresos y Gastos
        </button>
        <button
          type="button"
          onClick={() => setVista('por-pagar')}
          className={`px-4 py-1.5 rounded-lg text-sm font-bold font-headline transition-colors flex items-center gap-2 ${
            vista === 'por-pagar'
              ? 'bg-red-600 text-white shadow-sm'
              : 'text-yeikar-neutral/50 hover:text-red-600 hover:bg-red-50'
          }`}
        >
          Por Pagar
          {resumen && resumen.total_pendiente > 0 && (
            <span className={`text-[10px] font-mono px-1.5 py-0.5 rounded-md ${
              vista === 'por-pagar' ? 'bg-white/20 text-white' : 'bg-red-100 text-red-700'
            }`}>
              ${Number(resumen.total_pendiente).toLocaleString()}
            </span>
          )}
        </button>
      </div>

      {vista === 'por-pagar' ? (
        <div className="space-y-6">
          {/* Totales de la deuda */}
          <div className="grid grid-cols-1 sm:grid-cols-2 lg:grid-cols-4 gap-5">
            <StatCard
              label="Por pagar"
              value={`$${(resumen?.total_pendiente ?? 0).toLocaleString()}`}
              accent="from-red-500 to-red-400"
              iconBg="bg-red-50"
              iconText="text-red-600"
            />
            <StatCard
              label="Deudas activas"
              value={String(resumen?.total_deudas ?? 0)}
              accent="from-amber-500 to-amber-400"
              iconBg="bg-amber-50"
              iconText="text-amber-600"
            />
            <StatCard
              label="Ya abonado"
              value={`$${(resumen?.total_pagado ?? 0).toLocaleString()}`}
              accent="from-emerald-500 to-emerald-400"
              iconBg="bg-emerald-50"
              iconText="text-emerald-600"
            />
            <StatCard
              label="Proveedores con saldo"
              value={String(resumen?.por_proveedor.length ?? 0)}
              accent="from-yeikar-primary to-yeikar-primary-light"
              iconBg="bg-yeikar-primary/10"
              iconText="text-yeikar-primary"
            />
          </div>

          {/* Saldo por proveedor */}
          {resumen && resumen.por_proveedor.length > 0 && (
            <div className="card p-5">
              <div className="flex items-center justify-between mb-4">
                <h3 className="font-headline font-black text-yeikar-secondary text-sm uppercase tracking-wider">
                  Saldo por proveedor
                </h3>
                <span className="text-xs font-mono text-yeikar-neutral/40">
                  {resumen.por_proveedor.length} {resumen.por_proveedor.length === 1 ? 'proveedor' : 'proveedores'}
                </span>
              </div>
              <div className="grid grid-cols-1 sm:grid-cols-2 lg:grid-cols-3 xl:grid-cols-4 gap-4">
                {resumen.por_proveedor.map((p) => (
                  <button
                    key={p.proveedor_id}
                    type="button"
                    onClick={() => abrirAbonoProveedor(p.proveedor_id)}
                    title="Clic para abonar a este proveedor"
                    className="group rounded-xl border border-red-100 bg-red-50/50 p-4 space-y-1.5 text-left w-full transition-all hover:border-emerald-300 hover:bg-emerald-50/60 hover:shadow-md cursor-pointer"
                  >
                    <div className="flex items-center justify-between gap-2">
                      <span className="font-headline font-black text-yeikar-secondary text-xs uppercase tracking-wider truncate">
                        {p.proveedor_nombre}
                      </span>
                    </div>
                    <p className="font-mono text-2xl font-black text-red-700">
                      ${Number(p.saldo).toLocaleString()}
                    </p>
                    <p className="text-[10px] font-mono text-red-400/70 group-hover:hidden">pendiente por abonar</p>
                    <p className="hidden text-[10px] font-mono text-emerald-600/80 group-hover:block">clic para abonar</p>
                  </button>
                ))}
              </div>
            </div>
          )}

          {/* Tabla de deudas */}
          <div className="card overflow-hidden">
            <ResponsiveDataTable
              columns={deudasColumns}
              rows={deudas}
              rowKey={(d) => d.id}
              empty={
                <div className="p-8">
                  <EmptyState
                    compact
                    icon={
                      <svg className="w-7 h-7" fill="none" stroke="currentColor" viewBox="0 0 24 24">
                        <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M12 8c-1.657 0-3 .895-3 2s1.343 2 3 2 3 .895 3 2-1.343 2-3 2m0-8c1.11 0 2.08.402 2.599 1M12 8V7m0 1v8m0 0v1m0-1c-1.11 0-2.08-.402-2.599-1M21 12a9 9 0 11-18 0 9 9 0 0118 0z" />
                      </svg>
                    }
                    title="Sin deudas"
                    description="No hay deudas fiadas con los filtros actuales."
                    action={<Button size="sm" onClick={() => setShowDeudaModal(true)}>Registrar la primera</Button>}
                  />
                </div>
              }
              cardBadge={(d) => (
                <Badge tone={d.estado === 'PAGADA' ? 'green' : 'red'}>
                  {d.estado === 'PAGADA' ? 'Pagada' : 'Por pagar'}
                </Badge>
              )}
              tableActions={renderAccionesDeuda}
              cardActions={renderAccionesDeuda}
            />
          </div>
        </div>
      ) : (
        <>
      {/* ── Vista de gastos existente ── */}
      <div className="grid grid-cols-1 sm:grid-cols-2 lg:grid-cols-4 gap-5">
        <StatCard
          label="Total Egresos"
          value={`$${totales.total.toLocaleString()}`}
          accent="from-yeikar-primary to-yeikar-primary-light"
        />
        <StatCard
          label="Operativos"
          value={`$${totales.operativos.toLocaleString()}`}
          accent="from-blue-500 to-blue-400"
          iconBg="bg-blue-50"
          iconText="text-blue-600"
        />
        <StatCard
          label="Pasivos"
          value={`$${totales.pasivos.toLocaleString()}`}
          accent="from-red-500 to-red-400"
          iconBg="bg-red-50"
          iconText="text-red-600"
        />
        <StatCard
          label="Producción"
          value={`$${totales.produccion.toLocaleString()}`}
          accent="from-green-500 to-green-400"
          iconBg="bg-green-50"
          iconText="text-green-600"
        />
      </div>

      {/* Egresos por moneda */}
      {monedasResumen.length > 0 && (
        <div className="card p-5">
          <div className="flex items-center justify-between mb-4">
            <h3 className="font-headline font-black text-yeikar-secondary text-sm uppercase tracking-wider">
              Egresos por moneda
            </h3>
            <span className="text-xs font-mono text-yeikar-neutral/40">
              {monedasResumen.length} {monedasResumen.length === 1 ? 'moneda' : 'monedas'} en la selección
            </span>
          </div>
          <div className="grid grid-cols-1 sm:grid-cols-2 lg:grid-cols-4 gap-4">
            {monedasResumen.map((m) => {
              const pct = totales.total > 0 ? (m.totalCOP / totales.total) * 100 : 0;
              return (
                <div key={m.codigo} className="rounded-xl border border-yeikar-secondary-light/10 bg-yeikar-tertiary/10 p-4 space-y-2">
                  <div className="flex items-center justify-between">
                    <span className="inline-flex items-center gap-1.5 font-headline font-black text-yeikar-secondary">
                      <span className="text-xs uppercase">{nombreMoneda(m.codigo)}</span>
                    </span>
                    <span className="text-[10px] font-mono text-yeikar-neutral/40">{m.count} registros</span>
                  </div>
                  <p className="font-mono text-2xl font-black text-yeikar-dark">
                    {fmtMoneda(m.total, m.codigo)}
                  </p>
                  <div className="space-y-1">
                    <div className="h-1.5 rounded-full bg-yeikar-secondary-light/10 overflow-hidden">
                      <div
                        className="h-full rounded-full bg-yeikar-primary"
                        style={{ width: `${Math.min(100, pct)}%` }}
                      />
                    </div>
                    <div className="flex items-center justify-between text-[11px]">
                      <span className="font-mono text-yeikar-neutral/60">
                        ≈ {fmtMoneda(m.totalCOP, 'COP')}
                      </span>
                      <span className="font-bold text-yeikar-primary">{pct.toFixed(1)}%</span>
                    </div>
                  </div>
                </div>
              );
            })}
          </div>
        </div>
      )}

      <div className="flex flex-wrap gap-3 items-center">
        <div className="flex items-center gap-1 bg-white border border-yeikar-secondary-light/10 rounded-xl p-1 shadow-card">
          {CATEGORIAS.map((cat) => (
            <button
              key={cat.key}
              onClick={() => setCategoria(cat.key)}
              className={`px-3.5 py-1.5 rounded-lg text-sm font-bold font-headline transition-colors ${
                categoria === cat.key
                  ? 'bg-yeikar-primary text-yeikar-neutral shadow-sm'
                  : 'text-yeikar-neutral/50 hover:text-yeikar-secondary hover:bg-yeikar-tertiary'
              }`}
            >
              {cat.label}
            </button>
          ))}
        </div>
        <div className="w-56">
          <SearchSelect
            value={areaFiltro}
            onChange={(v) => setAreaFiltro(String(v))}
            options={[
              { value: '', label: 'Todas las áreas' },
              ...areas.map((a) => ({ value: a.id, label: a.nombre })),
            ]}
            placeholder="Filtrar por área"
          />
        </div>
        <div className="flex items-center gap-2 ml-auto">
          <Input type="date" value={fechaDesde} onChange={(e) => setFechaDesde(e.target.value)} className="w-auto" />
          <span className="text-yeikar-neutral/40 text-sm">a</span>
          <Input type="date" value={fechaHasta} onChange={(e) => setFechaHasta(e.target.value)} className="w-auto" />
        </div>
      </div>

      <div className="card overflow-hidden">
        <ResponsiveDataTable
          columns={columns}
          rows={gastos}
          rowKey={(g) => g.id}
          empty={
            loading ? (
              <div className="p-8"><Spinner size="sm" /></div>
            ) : (
              <div className="p-8">
                <EmptyState
                  compact
                  icon={
                    <svg className="w-7 h-7" fill="none" stroke="currentColor" viewBox="0 0 24 24">
                      <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M9 17V7m0 10a2 2 0 01-2 2H5a2 2 0 01-2-2V7a2 2 0 012-2h2a2 2 0 012 2m0 10a2 2 0 002 2h2a2 2 0 002-2M9 7a2 2 0 012-2h2a2 2 0 012 2m0 10V7m0 10a2 2 0 002 2h2a2 2 0 002-2V7a2 2 0 00-2-2h-2a2 2 0 00-2 2" />
                    </svg>
                  }
                  title="Sin registros"
                  description="No hay gastos con los filtros actuales."
                  action={<Button size="sm" onClick={() => setShowModal(true)}>Registrar el primero</Button>}
                />
              </div>
            )
          }
          cardBadge={(g) => (
            <Badge tone={CAT_TONE[g.tipo_gasto?.categoria ?? ''] ?? 'neutral'}>
              {g.tipo_gasto?.categoria || '-'}
            </Badge>
          )}
          tableActions={renderAcciones}
          cardActions={renderAcciones}
        />
      </div>

      <Modal
        open={showModal}
        onClose={() => setShowModal(false)}
        title="Nuevo Gasto / Egreso"
        subtitle="Registra un egreso operativo, pasivo o de producción"
        size="xl"
        footer={
          <>
            <Button variant="outline" onClick={() => setShowModal(false)}>Cancelar</Button>
            <Button onClick={handleCrear}>Guardar Gasto</Button>
          </>
        }
      >
        <div className="grid grid-cols-1 min-[420px]:grid-cols-2 gap-4">
          <Field label="Tipo de Gasto" required hint="Escribe el motivo; si no existe, se crea al guardar">
            <Input
              list="tipos-gasto-lista"
              type="text"
              value={tipoTexto}
              onChange={(e) => setTipoTexto(e.target.value)}
              placeholder="Ej: Reparación de aire acondicionado"
            />
            <datalist id="tipos-gasto-lista">
              {tiposGasto.map((t) => (
                <option key={t.id} value={t.nombre} />
              ))}
            </datalist>
          </Field>
          <Field label="Cuenta de egreso" required>
            <SearchSelect
              value={form.metodo_caja_id}
              onChange={(v) => {
                const cuenta = cuentas.find((c) => c.metodo_caja.id === Number(v));
                setForm((prev) => ({
                  ...prev,
                  metodo_caja_id: Number(v),
                  // Al elegir cuenta, la moneda del gasto sigue a la de la cuenta
                  // (se puede cambiar manualmente después si hace falta).
                  moneda_id: cuenta?.metodo_caja.moneda_id || prev.moneda_id,
                  tasa_cambio: Number(v) && cuenta?.metodo_caja.moneda_id === 1 ? 1 : prev.tasa_cambio,
                }));
              }}
              options={cuentas.map((c) => ({
                value: c.metodo_caja.id,
                // Nombre · MONEDA (saldo en la moneda propia de la cuenta, sin
                // conversión a COP: la tasa cambia a diario y se ingresa manual).
                label: `${c.metodo_caja.nombre} · ${c.metodo_caja.moneda_codigo || '?'} (saldo ${
                  c.saldo_por_moneda.length
                    ? c.saldo_por_moneda.map((l) => `${l.simbolo} ${fmtMoneda(Number(l.monto), l.codigo)}`).join(' / ')
                    : 'sin movimientos'
                })`,
              }))}
              placeholder="Seleccione la cuenta..."
            />
          </Field>
          <Field label="Área / Departamento" hint="Opcional">
            <SearchSelect
              value={form.area_id}
              onChange={(v) => setForm({ ...form, area_id: v ? Number(v) : 0 })}
              options={[
                { value: 0, label: 'Sin área' },
                ...areas.map((a) => ({ value: a.id, label: a.nombre })),
              ]}
              placeholder="Seleccione el área..."
            />
          </Field>
          <Field label="Moneda">
            <SearchSelect
              value={form.moneda_id}
              onChange={(v) => setForm({ ...form, moneda_id: Number(v), tasa_cambio: Number(v) === 1 ? 1 : form.tasa_cambio })}
              options={monedas.map((m) => ({ value: m.id, label: `${m.codigo} - ${m.nombre}` }))}
              placeholder="Seleccione moneda..."
            />
          </Field>
          <Field label="Fecha">
            <Input
              type="date"
              value={form.fecha}
              onChange={(e) => setForm({ ...form, fecha: e.target.value })}
            />
          </Field>
          {esCOP ? (
            <Field label="Monto (COP)">
              <Input
                type="number"
                step="0.01"
                value={form.monto}
                onChange={(e) => setForm({ ...form, monto: Number(e.target.value) })}
              />
            </Field>
          ) : (
            <>
              <Field label="Monto" required>
                <Input
                  type="number"
                  step="0.01"
                  value={form.monto}
                  onChange={(e) => setForm({ ...form, monto: Number(e.target.value) })}
                />
              </Field>
              <Field label={`TRM (${monedaSeleccionada?.codigo} → COP)`}>
                <Input
                  type="number"
                  step="0.01"
                  value={form.tasa_cambio}
                  onChange={(e) => setForm({ ...form, tasa_cambio: Number(e.target.value) })}
                />
              </Field>
            </>
          )}
          {Number(form.monto) > 0 && (
            <div className="col-span-2 rounded-lg border border-yeikar-primary/30 bg-yeikar-primary/10 px-4 py-3">
              <p className="text-xs font-medium uppercase tracking-wide text-yeikar-primary">
                Equivalente en Pesos
              </p>
              <p className="mt-1 font-mono text-2xl font-bold text-yeikar-dark">
                {fmtMoneda(montoEnCOP, 'COP')}
              </p>
              {!esCOP && (
                <p className="mt-0.5 text-xs text-yeikar-secondary">
                  {fmtMoneda(Number(form.monto), monedaSeleccionada?.codigo)} × TRM {Number(form.tasa_cambio).toLocaleString()}
                </p>
              )}
            </div>
          )}
          <div className="col-span-2">
            <Field label="Descripción">
              <Input
                type="text"
                value={form.descripcion}
                onChange={(e) => setForm({ ...form, descripcion: e.target.value })}
                placeholder="Ej: Pago de alquiler mes de julio"
              />
            </Field>
          </div>
          <div className="col-span-2">
            <Field label="Observaciones">
              <Textarea
                value={form.observaciones}
                onChange={(e) => setForm({ ...form, observaciones: e.target.value })}
                rows={2}
              />
            </Field>
          </div>
          {/* Comprobante digital (opcional) */}
          <div className="col-span-2">
            <Field label="Comprobante digital (opcional)" hint="Ej: transferencia bancaria, factura de compra. Se optimiza al subirla.">
              <div className="flex items-center gap-2">
                {comprobantePreview && (
                  <img
                    src={comprobantePreview}
                    alt="comprobante"
                    className="h-14 w-14 rounded-lg object-cover border border-yeikar-secondary-light/20"
                  />
                )}
                <label className="flex items-center justify-center gap-1.5 h-14 px-3 rounded-xl border-2 border-dashed border-yeikar-secondary-light/20 hover:border-yeikar-primary/50 cursor-pointer text-[11px] font-bold text-yeikar-neutral/50 transition-colors flex-1">
                  <svg className="w-4 h-4" fill="none" stroke="currentColor" viewBox="0 0 24 24">
                    <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M4 16l4.586-4.586a2 2 0 012.828 0L16 16m-2-2l1.586-1.586a2 2 0 012.828 0L20 14m-6-6h.01M6 20h12a2 2 0 002-2V6a2 2 0 00-2-2H6a2 2 0 00-2 2v12a2 2 0 002 2z" />
                  </svg>
                  {comprobanteArchivo ? comprobanteArchivo.name : 'Adjuntar imagen'}
                  <input
                    type="file"
                    accept="image/jpeg,image/png,image/webp,image/heic"
                    className="hidden"
                    onChange={(e) => {
                      const f = e.target.files?.[0];
                      if (!f) return;
                      setComprobanteArchivo(f);
                      if (comprobantePreview) URL.revokeObjectURL(comprobantePreview);
                      setComprobantePreview(URL.createObjectURL(f));
                    }}
                  />
                </label>
                {comprobanteArchivo && (
                  <button
                    type="button"
                    onClick={() => {
                      setComprobanteArchivo(null);
                      if (comprobantePreview) URL.revokeObjectURL(comprobantePreview);
                      setComprobantePreview(null);
                    }}
                    className="text-[11px] font-bold text-red-500 hover:underline"
                  >
                    Quitar
                  </button>
                )}
              </div>
            </Field>
          </div>
        </div>
      </Modal>

      <ConfirmDialog
        open={confirmDeleteId !== null}
        title="Eliminar gasto"
        message="¿Eliminar este gasto? Esta acción no se puede deshacer."
        confirmLabel="Eliminar"
        onConfirm={() => confirmDeleteId !== null && handleEliminar(confirmDeleteId)}
        onCancel={() => setConfirmDeleteId(null)}
      />

      {/* Visor de comprobante (ampliado) */}
      {comprobanteVer && (
        <div
          className="fixed inset-0 bg-black/70 backdrop-blur-sm flex items-center justify-center p-4 z-[60]"
          onClick={() => setComprobanteVer(null)}
        >
          <div className="relative max-w-2xl w-full bg-white rounded-2xl overflow-hidden shadow-2xl">
            <button
              onClick={() => setComprobanteVer(null)}
              className="absolute top-2 right-2 bg-black/60 text-white rounded-full w-8 h-8 flex items-center justify-center text-sm hover:bg-black/80"
            >
              ×
            </button>
            <AdjuntoImagen
              adjunto={{ id: comprobanteVer.id, mime: comprobanteVer.mime }}
              alt="comprobante"
              className="w-full max-h-[85vh] object-contain"
            />
          </div>
        </div>
      )}
        </>
      )}

      {/* ════════════ Modales de la vista "Por Pagar" ════════════ */}
      <Modal
        open={showDeudaModal}
        onClose={() => setShowDeudaModal(false)}
        title="Registrar Deuda (Fiado)"
        subtitle="Le debes a un proveedor y lo pagarás después, de a poco"
        size="xl"
        footer={
          <>
            <Button variant="outline" onClick={() => setShowDeudaModal(false)}>Cancelar</Button>
            <Button onClick={handleCrearDeuda}>Guardar Deuda</Button>
          </>
        }
      >
        <div className="grid grid-cols-1 min-[420px]:grid-cols-2 gap-4">
          <Field label="Proveedor" required hint="A quién le quedaste debiendo">
            <SearchSelect
              value={deudaForm.proveedor_id}
              onChange={(v) => setDeudaForm((prev) => ({ ...prev, proveedor_id: Number(v) }))}
              options={[
                { value: 0, label: 'Selecciona el proveedor...' },
                ...proveedores.map((p) => ({ value: p.id, label: p.nombre })),
              ]}
              placeholder="Buscar proveedor..."
            />
          </Field>
          <Field label="Motivo de la deuda" required hint="Escribe el motivo; si no existe, se crea al guardar">
            <Input
              list="tipos-gasto-lista"
              type="text"
              value={deudaForm.tipoTexto}
              onChange={(e) => setDeudaForm((prev) => ({ ...prev, tipoTexto: e.target.value }))}
              placeholder="Ej: Compra de madera, herrajes..."
            />
            <datalist id="tipos-gasto-lista">
              {tiposGasto.map((t) => (
                <option key={t.id} value={t.nombre} />
              ))}
            </datalist>
          </Field>
          <Field label="Moneda">
            <SearchSelect
              value={deudaForm.moneda_id}
              onChange={(v) => setDeudaForm((prev) => ({ ...prev, moneda_id: Number(v) }))}
              options={monedas.map((m) => ({ value: m.id, label: `${m.codigo} - ${m.nombre}` }))}
              placeholder="Seleccione moneda..."
            />
          </Field>
          <Field label="Fecha">
            <Input
              type="date"
              value={deudaForm.fecha}
              onChange={(e) => setDeudaForm((prev) => ({ ...prev, fecha: e.target.value }))}
            />
          </Field>
          <Field label="Monto de la deuda (COP)" required>
            <Input
              type="number"
              step="0.01"
              min="0"
              value={deudaForm.monto}
              onChange={(e) => setDeudaForm((prev) => ({ ...prev, monto: Number(e.target.value) }))}
            />
          </Field>
          <div className="col-span-2">
            <Field label="Descripción (opcional)">
              <Input
                type="text"
                value={deudaForm.descripcion}
                onChange={(e) => setDeudaForm((prev) => ({ ...prev, descripcion: e.target.value }))}
                placeholder="Ej: Madera para la cama del cliente Pérez"
              />
            </Field>
          </div>
          <div className="col-span-2 rounded-lg border border-red-200 bg-red-50/70 px-4 py-3">
            <p className="text-xs font-medium uppercase tracking-wide text-red-600">Cómo funciona</p>
            <p className="mt-1 text-xs text-red-700/80 leading-relaxed">
              La deuda queda en <b>Por Pagar</b> y su egreso entra al P&amp;L hoy (sin descontar caja).
              Cuando abones, el dinero saldrá de la cuenta que elijas.
            </p>
          </div>
        </div>
      </Modal>

      <Modal
        open={abonarDeuda !== null}
        onClose={() => setAbonarDeuda(null)}
        title={abonarDeuda ? `Abonar a ${abonarDeuda.proveedor?.nombre || 'proveedor'}` : 'Abonar'}
        subtitle={abonarDeuda ? `Debía ${fmtMoneda(Number(abonarDeuda.monto), abonarDeuda.moneda?.codigo || 'COP')} · Saldo ${fmtMoneda(Number(abonarDeuda.saldo), abonarDeuda.moneda?.codigo || 'COP')}` : ''}
        size="lg"
        footer={
          <>
            <Button variant="outline" onClick={() => setAbonarDeuda(null)}>Cancelar</Button>
            <Button
              disabled={!abonoForm.metodo_caja_id || !(Number(abonoForm.monto) > 0) || abonoExcede || (necesitaTasaAbono && !(Number(abonoForm.tasa_cambio) > 0))}
              onClick={handleAbonar}
            >
              Abonar
            </Button>
          </>
        }
      >
        <div className="grid grid-cols-1 min-[420px]:grid-cols-2 gap-4">
          <Field label="¿Cuánto abonas?" required>
            <Input
              type="number"
              step="0.01"
              min="0"
              value={abonoForm.monto}
              onChange={(e) => setAbonoForm((prev) => ({ ...prev, monto: Number(e.target.value) }))}
            />
          </Field>
          <div className="flex items-end pb-1">
            <Button size="sm" variant="outline" onClick={() => setAbonoForm((prev) => ({ ...prev, monto: Number(abonarDeuda?.saldo || 0) }))}>
              Pagar todo
            </Button>
          </div>
          <Field label="¿Desde qué cuenta sale el dinero?" required>
            <SearchSelect
              value={abonoForm.metodo_caja_id}
              onChange={(v) => setAbonoForm((prev) => ({ ...prev, metodo_caja_id: Number(v) }))}
              options={cuentas.map((c) => ({
                value: c.metodo_caja.id,
                label: `${c.metodo_caja.nombre} · ${c.metodo_caja.moneda_codigo || '?'} (saldo ${
                  c.saldo_por_moneda.length
                    ? c.saldo_por_moneda.map((l) => `${l.simbolo} ${fmtMoneda(Number(l.monto), l.codigo)}`).join(' / ')
                    : 'sin movimientos'
                })`,
              }))}
              placeholder="Seleccione la cuenta..."
            />
          </Field>
          <Field label="Fecha del abono">
            <Input
              type="date"
              value={abonoForm.fecha}
              onChange={(e) => setAbonoForm((prev) => ({ ...prev, fecha: e.target.value }))}
            />
          </Field>
          {necesitaTasaAbono && (
            <Field label={`Tasa de cambio * (1 ${cuentaAbonoSel?.metodo_caja.moneda_codigo} = ? COP)`}>
              <Input
                type="number"
                step="0.01"
                min="0"
                value={abonoForm.tasa_cambio}
                onChange={(e) => setAbonoForm((prev) => ({ ...prev, tasa_cambio: Number(e.target.value) }))}
              />
            </Field>
          )}
          <div className="col-span-2 space-y-2">
            {abonoExcede && (
              <p className="text-xs font-bold text-red-600">
                El abono excede el saldo de la deuda ({fmtMoneda(Number(abonarDeuda?.saldo || 0), abonarDeuda?.moneda?.codigo || 'COP')}).
              </p>
            )}
            {Number(abonoForm.monto) > 0 && cuentaAbonoSel && (
              <p className="text-[11px] text-yeikar-neutral/70 bg-emerald-50/70 border border-emerald-100 rounded-lg px-3 py-2">
                Saldrán ≈ <b>{fmtMoneda(deducAbono, cuentaAbonoSel.metodo_caja.moneda_codigo || 'COP')}</b> desde{' '}
                <b>{cuentaAbonoSel.metodo_caja.nombre}</b>
                {necesitaTasaAbono && !(Number(abonoForm.tasa_cambio) > 0) ? ' · falta la tasa' : ''}
              </p>
            )}
          </div>
        </div>
      </Modal>

      <Modal
        open={historialDeuda !== null}
        onClose={() => setHistorialDeuda(null)}
        title={historialDeuda ? `Abonos — ${historialDeuda.proveedor?.nombre || 'proveedor'}` : 'Historial'}
        subtitle={historialDeuda ? `${historialDeuda.pagos?.length || 0} abonos registrados` : ''}
        size="lg"
      >
        <div className="space-y-2 max-h-[50vh] overflow-y-auto pr-1">
          {historialDeuda?.pagos && historialDeuda.pagos.length > 0 ? (
            historialDeuda.pagos.map((p: Abono) => (
              <div key={p.id} className="flex items-center justify-between gap-3 rounded-xl border border-yeikar-secondary-light/10 bg-yeikar-tertiary/10 px-4 py-3">
                <div>
                  <p className="text-sm font-bold text-yeikar-secondary">
                    {fmtMoneda(Number(p.monto), historialDeuda.moneda?.codigo || 'COP')}
                    <span className="ml-2 text-[11px] font-mono text-yeikar-neutral/50">≈ {fmtMoneda(Number(p.monto_en_moneda_base), 'COP')}</span>
                  </p>
                  <p className="text-[11px] text-yeikar-neutral/60">
                    {p.fecha} · desde <b>{p.metodo_caja_nombre || 'cuenta'}</b>
                  </p>
                </div>
                <Button
                  variant="ghost"
                  size="sm"
                  className="text-red-600 hover:bg-red-50"
                  onClick={() => setConfirmDeleteAbono({ deudaId: historialDeuda.id, abonoId: p.id })}
                >
                  Revertir
                </Button>
              </div>
            ))
          ) : (
            <div className="p-6 text-center text-sm text-yeikar-neutral/50">Esta deuda no tiene abonos todavía.</div>
          )}
        </div>
      </Modal>

      <ConfirmDialog
        open={confirmDeleteDeuda !== null}
        title="Eliminar deuda"
        message="¿Eliminar esta deuda y su gasto asociado? Solo se puede si no tiene abonos."
        confirmLabel="Eliminar"
        onConfirm={() => confirmDeleteDeuda !== null && handleEliminarDeuda(confirmDeleteDeuda)}
        onCancel={() => setConfirmDeleteDeuda(null)}
      />

      <ConfirmDialog
        open={confirmDeleteAbono !== null}
        title="Revertir abono"
        message="¿Revertir este abono? Se devuelve el saldo de la deuda y se elimina la salida de caja."
        confirmLabel="Revertir"
        onConfirm={() => confirmDeleteAbono && handleEliminarAbono(confirmDeleteAbono.abonoId)}
        onCancel={() => setConfirmDeleteAbono(null)}
      />
    </div>
  );
}
