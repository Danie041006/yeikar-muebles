import { useState, useEffect, useCallback } from 'react';
import {
  getGastos, getTiposGasto, getMonedas, createGasto, deleteGasto,
  Gasto, GastoCreate, TipoGasto, Moneda,
} from '../services/gastoService';
import {
  Button, Card, Badge, Spinner, EmptyState, StatCard, Modal, PageHeader,
  Field, Input, Select, Textarea, ConfirmDialog,
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
  const [categoria, setCategoria] = useState('');
  const [fechaDesde, setFechaDesde] = useState('');
  const [fechaHasta, setFechaHasta] = useState('');
  const [showModal, setShowModal] = useState(false);
  const [loading, setLoading] = useState(false);
  const [confirmDeleteId, setConfirmDeleteId] = useState<number | null>(null);

  const [form, setForm] = useState<GastoCreate>({
    tipo_gasto_id: 0,
    moneda_id: 1,
    fecha: new Date().toISOString().split('T')[0],
    monto: 0,
    tasa_cambio: 1,
    descripcion: '',
    observaciones: '',
  });

  const cargarGastos = useCallback(async () => {
    setLoading(true);
    try {
      const data = await getGastos({
        categoria: categoria || undefined,
        fecha_desde: fechaDesde || undefined,
        fecha_hasta: fechaHasta || undefined,
      });
      setGastos(data);
    } finally {
      setLoading(false);
    }
  }, [categoria, fechaDesde, fechaHasta]);

  const cargarCatalogos = useCallback(async () => {
    const [tipos, monedasData] = await Promise.all([
      getTiposGasto(),
      getMonedas(),
    ]);
    setTiposGasto(tipos);
    setMonedas(monedasData);
    if (tipos.length > 0 && form.tipo_gasto_id === 0) {
      setForm((prev) => ({ ...prev, tipo_gasto_id: tipos[0].id }));
    }
  }, []);

  useEffect(() => {
    cargarCatalogos();
  }, [cargarCatalogos]);

  useEffect(() => {
    cargarGastos();
  }, [cargarGastos]);

  const handleCrear = async () => {
    if (!form.tipo_gasto_id || !form.monto || form.monto <= 0) return;
    await createGasto(form);
    setShowModal(false);
    setForm({
      tipo_gasto_id: tiposGasto[0]?.id || 0,
      moneda_id: 1,
      fecha: new Date().toISOString().split('T')[0],
      monto: 0,
      tasa_cambio: 1,
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
                      {m.simbolo}
                      <span className="text-xs uppercase">{m.codigo}</span>
                    </span>
                    <span className="text-[10px] font-mono text-yeikar-neutral/40">{m.count} registros</span>
                  </div>
                  <p className="font-mono text-2xl font-black text-yeikar-dark">
                    {m.simbolo} {m.total.toLocaleString('es-CO', { maximumFractionDigits: 2 })}
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
                        ≈ $ {m.totalCOP.toLocaleString('es-CO')} COP
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
        <div className="flex items-center gap-2 ml-auto">
          <Input type="date" value={fechaDesde} onChange={(e) => setFechaDesde(e.target.value)} className="w-auto" />
          <span className="text-yeikar-neutral/40 text-sm">a</span>
          <Input type="date" value={fechaHasta} onChange={(e) => setFechaHasta(e.target.value)} className="w-auto" />
        </div>
      </div>

      <div className="card overflow-hidden">
        <div className="overflow-x-auto">
          <table className="w-full text-left border-collapse">
            <thead className="bg-yeikar-tertiary/20 text-yeikar-secondary">
              <tr className="font-headline font-bold text-xs uppercase tracking-wider">
                <th className="table-th">Fecha</th>
                <th className="table-th">Tipo</th>
                <th className="table-th">Categoría</th>
                <th className="table-th">Descripción</th>
                <th className="table-th text-right">Monto</th>
                <th className="table-th text-right">Moneda Base</th>
                <th className="table-th text-right">Acciones</th>
              </tr>
            </thead>
            <tbody className="divide-y divide-yeikar-secondary-light/5 text-sm">
              {loading ? (
                <tr>
                  <td colSpan={7} className="p-8">
                    <Spinner size="sm" />
                  </td>
                </tr>
              ) : gastos.length === 0 ? (
                <tr>
                  <td colSpan={7} className="p-8">
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
                  </td>
                </tr>
              ) : gastos.map((g) => (
                <tr key={g.id} className="hover:bg-yeikar-tertiary/10 transition-colors">
                  <td className="table-td font-mono text-xs text-yeikar-neutral/50">{g.fecha}</td>
                  <td className="table-td font-bold text-yeikar-secondary">{g.tipo_gasto?.nombre || '-'}</td>
                  <td className="table-td">
                    <Badge tone={CAT_TONE[g.tipo_gasto?.categoria ?? ''] ?? 'neutral'}>
                      {g.tipo_gasto?.categoria || '-'}
                    </Badge>
                  </td>
                  <td className="table-td max-w-[200px] truncate">{g.descripcion || '-'}</td>
                  <td className="table-td text-right font-mono font-bold text-yeikar-secondary">
                    {g.moneda?.simbolo} {Number(g.monto).toLocaleString()}
                  </td>
                  <td className="table-td text-right font-mono">${Number(g.monto_en_moneda_base).toLocaleString()}</td>
                  <td className="table-td text-right">
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
                  </td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
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
          <Field label="Tipo de Gasto" required>
            <Select
              value={form.tipo_gasto_id}
              onChange={(e) => setForm({ ...form, tipo_gasto_id: Number(e.target.value) })}
            >
              {tiposGasto.map((t) => (
                <option key={t.id} value={t.id}>{t.nombre}</option>
              ))}
            </Select>
          </Field>
          <Field label="Moneda">
            <Select
              value={form.moneda_id}
              onChange={(e) => setForm({ ...form, moneda_id: Number(e.target.value), tasa_cambio: Number(e.target.value) === 1 ? 1 : form.tasa_cambio })}
            >
              {monedas.map((m) => (
                <option key={m.id} value={m.id}>{m.codigo} - {m.nombre}</option>
              ))}
            </Select>
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
                Equivalente en pesos (COP)
              </p>
              <p className="mt-1 font-mono text-2xl font-bold text-yeikar-dark">
                $ {montoEnCOP.toLocaleString('es-CO', { maximumFractionDigits: 2 })}
              </p>
              {!esCOP && (
                <p className="mt-0.5 text-xs text-yeikar-secondary">
                  {Number(form.monto).toLocaleString()} {monedaSeleccionada?.codigo} × TRM {Number(form.tasa_cambio).toLocaleString()}
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
    </div>
  );
}
