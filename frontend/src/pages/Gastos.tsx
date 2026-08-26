import { useState, useEffect, useCallback } from 'react';
import {
  getGastos, getTiposGasto, getMonedas, createGasto, deleteGasto, createTipoGasto, getAreas,
  Gasto, GastoCreate, TipoGasto, Moneda, Area,
} from '../services/gastoService';
import { cuentasService, ResumenCuenta } from '../services/cuentasService';
import { nombreMoneda, fmtMoneda } from '../utils/format';
import { subirAdjunto, TIPO_ADJUNTO } from '../services/adjuntosService';
import AdjuntoImagen from '../components/AdjuntoImagen';
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

export default function Gastos() {
  const [gastos, setGastos] = useState<Gasto[]>([]);
  const [tiposGasto, setTiposGasto] = useState<TipoGasto[]>([]);
  const [monedas, setMonedas] = useState<Moneda[]>([]);
  const [cuentas, setCuentas] = useState<ResumenCuenta[]>([]);
  const [areas, setAreas] = useState<Area[]>([]);
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
    const [tipos, monedasData, cuentasData, areasData] = await Promise.all([
      getTiposGasto(),
      getMonedas(),
      cuentasService.getResumen(),
      getAreas(),
    ]);
    setTiposGasto(tipos);
    setMonedas(monedasData);
    setCuentas(cuentasData);
    setAreas(areasData);
    setForm((prev) => ({
      ...prev,
      metodo_caja_id: prev.metodo_caja_id === 0 ? cuentasData[0]?.metodo_caja.id || 0 : prev.metodo_caja_id,
    }));
  }, []);

  useEffect(() => {
    cargarCatalogos();
  }, [cargarCatalogos]);

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
        title="Egresos y Gastos"
        subtitle={`${gastos.length} registros en la selección actual`}
        actions={
          <Button onClick={() => setShowModal(true)}>
            <svg className="w-4 h-4" fill="none" stroke="currentColor" viewBox="0 0 24 24">
              <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2.5} d="M12 4v16m8-8H4" />
            </svg>
            Nuevo Gasto
          </Button>
        }
      />

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
        <div className="grid grid-cols-2 gap-4">
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
              onChange={(v) => setForm({ ...form, metodo_caja_id: Number(v) })}
              options={cuentas.map((c) => ({
                value: c.metodo_caja.id,
                // Saldo en la moneda propia de cada cuenta (sin conversión a COP:
                // la tasa cambia a diario y se ingresa manualmente por operación).
                label: `${c.metodo_caja.nombre} (saldo ${
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
    </div>
  );
}
