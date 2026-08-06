import { useState, useEffect, useCallback } from 'react';
import {
  cuentasService, ResumenCuenta, MovimientoCaja, Moneda,
  MovimientoCreate, MetodoCaja,
} from '../services/cuentasService';
import {
  Button, Card, Badge, Spinner, EmptyState, StatCard, Modal, PageHeader,
  Field, Input, Select, Textarea, ConfirmDialog,
} from '../components/ui';

const TIPOS = [
  { key: '', label: 'Todos' },
  { key: 'APERTURA', label: 'Apertura' },
  { key: 'ENTRADA', label: 'Entrada' },
  { key: 'SALIDA', label: 'Salida' },
  { key: 'AJUSTE', label: 'Ajuste' },
];

const emptyMovForm = (metodoId = 0, monedaCopId = 1): Omit<MovimientoCreate, 'tasa_cambio' | 'referencia' | 'observaciones'> & { tasa_cambio: number; referencia: string; observaciones: string } => ({
  metodo_caja_id: metodoId,
  fecha: new Date().toISOString().split('T')[0],
  tipo: 'ENTRADA',
  monto: 0,
  moneda_id: monedaCopId,
  tasa_cambio: 1,
  referencia: '',
  observaciones: '',
});

const fmt = (n: number) => (Number.isFinite(n) ? n.toLocaleString('es-CO', { maximumFractionDigits: 0 }) : '0');

const TIPO_TONE: Record<string, 'neutral' | 'green' | 'red' | 'amber'> = {
  APERTURA: 'neutral',
  ENTRADA: 'green',
  SALIDA: 'red',
  AJUSTE: 'amber',
};

export default function Cuentas() {
  const [resumen, setResumen] = useState<ResumenCuenta[]>([]);
  const [movimientos, setMovimientos] = useState<MovimientoCaja[]>([]);
  const [monedas, setMonedas] = useState<Moneda[]>([]);
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState('');

  const [showCuentaModal, setShowCuentaModal] = useState(false);
  const [editCuenta, setEditCuenta] = useState<MetodoCaja | null>(null);
  const [cuentaForm, setCuentaForm] = useState({ nombre: '', codigo: '', orden: 1 });

  const [showMovModal, setShowMovModal] = useState(false);
  const [editMov, setEditMov] = useState<MovimientoCaja | null>(null);
  const [movForm, setMovForm] = useState(emptyMovForm());

  const [filtroCuenta, setFiltroCuenta] = useState<number | ''>('');
  const [filtroTipo, setFiltroTipo] = useState('');
  const [fechaDesde, setFechaDesde] = useState('');
  const [fechaHasta, setFechaHasta] = useState('');

  const [confirmAccion, setConfirmAccion] = useState<null | { tipo: 'cuenta' | 'movimiento'; id: number; nombre?: string }>(null);

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

  const totalCop = resumen.reduce((s, r) => s + Number(r.saldo_cop || 0), 0);

  // ─── Cuentas ───────────────────────────────────────────────────────────
  const abrirCuenta = (cuenta?: MetodoCaja) => {
    setEditCuenta(cuenta ?? null);
    setCuentaForm(cuenta
      ? { nombre: cuenta.nombre, codigo: cuenta.codigo, orden: cuenta.orden }
      : { nombre: '', codigo: '', orden: resumen.length + 1 });
    setShowCuentaModal(true);
  };

  const guardarCuenta = async () => {
    if (!cuentaForm.nombre.trim() || !cuentaForm.codigo.trim()) {
      setError('Nombre y código son obligatorios.');
      return;
    }
    try {
      if (editCuenta) {
        await cuentasService.actualizarCuenta(editCuenta.id, {
          nombre: cuentaForm.nombre.trim(),
          codigo: cuentaForm.codigo.trim().toUpperCase(),
          orden: cuentaForm.orden,
        });
      } else {
        await cuentasService.crearCuenta({
          nombre: cuentaForm.nombre.trim(),
          codigo: cuentaForm.codigo.trim().toUpperCase(),
          orden: cuentaForm.orden,
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
        monto: Number(mov.monto),
        moneda_id: mov.moneda_id,
        tasa_cambio: Number(mov.tasa_cambio || 1),
        referencia: mov.referencia ?? '',
        observaciones: mov.observaciones ?? '',
      });
    } else {
      setMovForm(emptyMovForm(cuentaId, monedaCopId));
    }
    setShowMovModal(true);
  };

  const guardarMovimiento = async () => {
    if (!movForm.metodo_caja_id || !movForm.monto || movForm.monto <= 0) {
      setError('Cuenta y monto son obligatorios (mayor a 0).');
      return;
    }
    const payload = {
      fecha: movForm.fecha,
      tipo: movForm.tipo,
      monto: Number(movForm.monto),
      moneda_id: movForm.moneda_id,
      tasa_cambio: Number(movForm.tasa_cambio || 1),
      referencia: movForm.referencia.trim() || null,
      observaciones: movForm.observaciones.trim() || null,
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

  return (
    <div className="space-y-6">
      <PageHeader
        eyebrow="Finanzas"
        title="Cuentas y Medios de Pago"
        subtitle={`${resumen.length} cuentas · ${movimientos.length} movimientos en el filtro`}
        actions={
          <Button onClick={() => abrirCuenta()}>
            <svg className="w-4 h-4" fill="none" stroke="currentColor" viewBox="0 0 24 24">
              <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2.5} d="M12 4v16m8-8H4" />
            </svg>
            Nueva Cuenta
          </Button>
        }
      />

      {error && (
        <div className="bg-red-50 border border-red-200 text-red-700 px-4 py-3 rounded-xl text-sm animate-fade-in">
          {error}
        </div>
      )}

      <div className="grid grid-cols-1 md:grid-cols-4 gap-5">
        <StatCard
          label="Total en cuentas (COP)"
          value={`$${fmt(totalCop)}`}
          accent="from-yeikar-primary to-yeikar-primary-light"
          hint="Suma de saldos convertidos"
        />
        <div className="md:col-span-3">
          <StatCard
            label="Cuentas activas"
            value={resumen.filter((r) => r.metodo_caja.activo).length}
            accent="from-yeikar-secondary to-yeikar-secondary-light"
            hint={`${resumen.filter((r) => !r.metodo_caja.activo).length} inactivas`}
          />
        </div>
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
              ) : r.saldo_por_moneda.map((l) => (
                <div key={l.moneda_id} className="flex justify-between text-sm">
                  <span className="text-yeikar-neutral/50">{l.simbolo} en {l.codigo}</span>
                  <span className="font-mono font-semibold">
                    {l.simbolo} {fmt(Number(l.monto))}
                    {l.codigo !== 'COP' && <span className="text-yeikar-neutral/40 text-xs"> · ≈ ${fmt(Number(l.monto_cop))}</span>}
                  </span>
                </div>
              ))}
              <div className="flex justify-between text-sm border-t border-yeikar-secondary-light/10 pt-2 mt-2">
                <span className="text-yeikar-neutral/50">Saldo COP</span>
                <span className={`font-mono font-bold ${Number(r.saldo_cop) < 0 ? 'text-red-600' : 'text-yeikar-primary-dark'}`}>
                  ${fmt(Number(r.saldo_cop))}
                </span>
              </div>
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
            <Select
              value={filtroCuenta}
              onChange={(e) => setFiltroCuenta(e.target.value ? Number(e.target.value) : '')}
              className="w-auto py-1.5 text-xs"
            >
              <option value="">Todas las cuentas</option>
              {resumen.map((r) => (
                <option key={r.metodo_caja.id} value={r.metodo_caja.id}>{r.metodo_caja.nombre}</option>
              ))}
            </Select>
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
        <div className="overflow-x-auto">
          <table className="w-full text-left border-collapse">
            <thead className="bg-yeikar-tertiary/20 text-yeikar-secondary">
              <tr className="font-headline font-bold text-xs uppercase tracking-wider">
                <th className="table-th">Fecha</th>
                <th className="table-th">Cuenta</th>
                <th className="table-th">Tipo</th>
                <th className="table-th text-right">Monto</th>
                <th className="table-th text-right">COP</th>
                <th className="table-th">Referencia / Razón</th>
                <th className="table-th">Responsable</th>
                <th className="table-th text-right">Acciones</th>
              </tr>
            </thead>
            <tbody className="divide-y divide-yeikar-secondary-light/5 text-sm">
              {loading ? (
                <tr>
                  <td colSpan={8} className="p-8">
                    <Spinner size="sm" />
                  </td>
                </tr>
              ) : movimientos.length === 0 ? (
                <tr>
                  <td colSpan={8} className="p-8">
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
                  </td>
                </tr>
              ) : movimientos.map((m) => {
                const mon = monedaDe(m.moneda_id);
                return (
                  <tr key={m.id} className="hover:bg-yeikar-tertiary/10 transition-colors">
                    <td className="table-td font-mono text-xs text-yeikar-neutral/50">{m.fecha.slice(0, 10)}</td>
                    <td className="table-td font-bold text-yeikar-secondary">{m.metodo_caja?.nombre ?? '-'}</td>
                    <td className="table-td"><Badge tone={TIPO_TONE[m.tipo] ?? 'neutral'}>{m.tipo}</Badge></td>
                    <td className="table-td text-right font-mono font-semibold">{mon?.simbolo ?? ''}{fmt(Number(m.monto))}</td>
                    <td className="table-td text-right font-mono">${fmt(Number(m.monto_en_moneda_base))}</td>
                    <td className="table-td text-yeikar-neutral/60 max-w-xs truncate" title={m.referencia ?? m.observaciones ?? ''}>
                      {m.referencia || m.observaciones || '-'}
                    </td>
                    <td className="table-td">{m.usuario?.nombre_usuario ?? '-'}</td>
                    <td className="table-td text-right whitespace-nowrap">
                      <Button variant="ghost" size="sm" className="text-yeikar-primary-dark" onClick={() => abrirMovimiento(m.metodo_caja_id, m)}>
                        Editar
                      </Button>
                      <Button
                        variant="ghost"
                        size="sm"
                        className="text-red-600 hover:text-red-700 hover:bg-red-50"
                        onClick={() => setConfirmAccion({ tipo: 'movimiento', id: m.id })}
                      >
                        Eliminar
                      </Button>
                    </td>
                  </tr>
                );
              })}
            </tbody>
          </table>
        </div>
      </Card>

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
            <Select
              value={movForm.metodo_caja_id}
              onChange={(e) => setMovForm({ ...movForm, metodo_caja_id: Number(e.target.value) })}
            >
              <option value={0}>Seleccione...</option>
              {resumen.map((r) => (
                <option key={r.metodo_caja.id} value={r.metodo_caja.id}>{r.metodo_caja.nombre}</option>
              ))}
            </Select>
          </Field>
          <div className="grid grid-cols-2 gap-4">
            <Field label="Tipo" required>
              <Select
                value={movForm.tipo}
                onChange={(e) => setMovForm({ ...movForm, tipo: e.target.value as MovimientoCreate['tipo'] })}
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
          <div className="grid grid-cols-3 gap-4">
            <Field label="Monto" required>
              <Input
                type="number"
                step="0.01"
                min="0"
                value={movForm.monto}
                onChange={(e) => setMovForm({ ...movForm, monto: Number(e.target.value) })}
              />
            </Field>
            <Field label="Moneda">
              <Select
                value={movForm.moneda_id}
                onChange={(e) => setMovForm({ ...movForm, moneda_id: Number(e.target.value) })}
              >
                {monedas.map((m) => <option key={m.id} value={m.id}>{m.codigo} ({m.simbolo})</option>)}
              </Select>
            </Field>
            <Field label="Tasa → COP">
              <Input
                type="number"
                step="0.01"
                min="0"
                value={movForm.tasa_cambio}
                onChange={(e) => setMovForm({ ...movForm, tasa_cambio: Number(e.target.value) || 1 })}
              />
            </Field>
          </div>
          <Field label="Referencia">
            <Input
              value={movForm.referencia}
              onChange={(e) => setMovForm({ ...movForm, referencia: e.target.value })}
              placeholder="Ej: Pago de venta #10, compra de madera"
            />
          </Field>
          <Field label="Observaciones">
            <Textarea
              rows={2}
              value={movForm.observaciones}
              onChange={(e) => setMovForm({ ...movForm, observaciones: e.target.value })}
            />
          </Field>
          {movForm.moneda_id !== monedaCopId && movForm.monto > 0 && (
            <p className="text-sm text-yeikar-neutral/50">
              ≈ <span className="font-mono font-semibold text-yeikar-primary-dark">${fmt(Number(movForm.monto) * Number(movForm.tasa_cambio || 1))}</span> COP
            </p>
          )}
        </div>
      </Modal>

      <ConfirmDialog
        open={confirmAccion !== null}
        title={confirmAccion?.tipo === 'cuenta' ? 'Eliminar cuenta' : 'Eliminar movimiento'}
        message={
          confirmAccion?.tipo === 'cuenta'
            ? `¿Eliminar la cuenta "${confirmAccion.nombre}"? Los movimientos asociados se conservan.`
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
