import { useCallback, useEffect, useState, type ReactNode } from 'react';
import {
  cuentasService, type LibroCajaVista, type LibroCajaVistaFila,
  type ResumenCuenta,
} from '../../services/cuentasService';
import {
  CLASIFICACIONES_GASTO, nombreClasificacion,
} from '../../services/gastoService';
import {
  Badge, Button, Card, EmptyState, Field, Input, Modal, SearchSelect,
  Select, Spinner, StatCard, Textarea, ResponsiveDataTable, type DataColumn,
} from '../ui';
import { fmtMoneda } from '../../utils/format';
import { fmtFechaHoraVE } from '../../utils/fechas';
import { formatMontoInput, parseMontoInput } from '../../utils/monto';
import { useToast } from '../../context/ToastContext';

const iso = (d: Date) =>
  `${d.getFullYear()}-${String(d.getMonth() + 1).padStart(2, '0')}-${String(d.getDate()).padStart(2, '0')}`;

const POR_PAGINA = 40;

const primerDiaMes = () => {
  const hoy = new Date();
  return iso(new Date(hoy.getFullYear(), hoy.getMonth(), 1));
};
const ultimoDiaMes = () => {
  const hoy = new Date();
  return iso(new Date(hoy.getFullYear(), hoy.getMonth() + 1, 0));
};

const TONE: Record<string, 'green' | 'blue' | 'amber' | 'purple' | 'gold' | 'neutral'> =
  Object.fromEntries(CLASIFICACIONES_GASTO.map((c) => [c.value, c.tone]));

function FilaDetalle({ label, children }: { label: string; children: ReactNode }) {
  return (
    <div className="grid grid-cols-[140px_1fr] gap-3 items-baseline">
      <dt className="font-mono text-[10px] uppercase tracking-wider text-yeikar-neutral/40">{label}</dt>
      <dd className="break-words whitespace-pre-line text-sm text-yeikar-neutral/90">{children}</dd>
    </div>
  );
}

interface Props {
  cuentas: ResumenCuenta[];
  /** Avisa al padre la cuenta y el rango que se están viendo (para el reporte). */
  onFiltroChange?: (filtro: { cuentaId: number; desde: string; hasta: string }) => void;
}

export default function LibroCajaView({ cuentas, onFiltroChange }: Props) {
  const cuentaCop = cuentas.find((c) => c.metodo_caja.codigo === 'EFECTIVO_COP')
    || cuentas.find((c) => c.metodo_caja.moneda_codigo === 'COP');

  const [cuentaId, setCuentaId] = useState<number>(cuentaCop?.metodo_caja.id || 0);
  const [desde, setDesde] = useState(primerDiaMes());
  const [hasta, setHasta] = useState(ultimoDiaMes());
  const [data, setData] = useState<LibroCajaVista | null>(null);
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState('');
  const [pagina, setPagina] = useState(1);
  const toast = useToast();

  // Detalle / edición de una fila del libro. No hay iconos: se abre al
  // hacer clic en la fila.
  const [detalle, setDetalle] = useState<LibroCajaVistaFila | null>(null);
  const [editando, setEditando] = useState(false);
  const [guardando, setGuardando] = useState(false);
  const [errorMov, setErrorMov] = useState('');
  const [editForm, setEditForm] = useState({
    fecha: '',
    tipo: 'ENTRADA' as LibroCajaVistaFila['tipo_movimiento'],
    monto: '',
    persona_entidad: '',
    concepto: '',
  });

  // Si las cuentas llegan después del primer render, se elige la de COP.
  useEffect(() => {
    if (!cuentaId && cuentaCop) setCuentaId(cuentaCop.metodo_caja.id);
  }, [cuentaId, cuentaCop]);

  // Mantiene al padre al tanto de cuenta y rango (el reporte abre con esto).
  useEffect(() => {
    if (cuentaId) onFiltroChange?.({ cuentaId, desde, hasta });
  }, [cuentaId, desde, hasta, onFiltroChange]);

  const cargar = useCallback(async () => {
    if (!cuentaId) return;
    setLoading(true);
    setError('');
    try {
      const res = await cuentasService.getLibro({
        metodo_caja_id: cuentaId,
        fecha_desde: desde || undefined,
        fecha_hasta: hasta || undefined,
      });
      setData(res);
    } catch (e: any) {
      setError(e?.response?.data?.detail ?? 'No se pudo cargar el libro de caja.');
      setData(null);
    } finally {
      setLoading(false);
    }
  }, [cuentaId, desde, hasta]);

  useEffect(() => {
    setPagina(1);
  }, [cuentaId, desde, hasta]);

  useEffect(() => {
    cargar();
  }, [cargar]);

  const abrirDetalle = (fila: LibroCajaVistaFila) => {
    const monto = Number(fila.ingreso) > 0 ? Number(fila.ingreso) : Number(fila.egreso);
    setDetalle(fila);
    setEditando(false);
    setErrorMov('');
    setEditForm({
      fecha: fila.fecha,
      tipo: fila.tipo_movimiento,
      monto: formatMontoInput(String(monto)),
      persona_entidad: fila.persona_entidad ?? '',
      concepto: fila.concepto ?? '',
    });
  };

  const cerrarDetalle = () => {
    setDetalle(null);
    setEditando(false);
    setErrorMov('');
  };

  const guardarEdicion = async () => {
    if (!detalle) return;
    const monto = parseMontoInput(editForm.monto);
    if (!editForm.fecha) {
      setErrorMov('La fecha es obligatoria.');
      return;
    }
    if (!Number.isFinite(monto) || monto <= 0) {
      setErrorMov('El monto debe ser mayor a 0.');
      return;
    }
    setGuardando(true);
    setErrorMov('');
    try {
      await cuentasService.actualizarMovimiento(detalle.id, {
        fecha: editForm.fecha,
        tipo: editForm.tipo,
        monto,
        persona_entidad: editForm.persona_entidad.trim() || null,
        concepto: editForm.concepto.trim() || null,
      });
      toast.success('Movimiento corregido');
      cerrarDetalle();
      await cargar();
    } catch (e: any) {
      setErrorMov(e?.response?.data?.detail ?? 'No se pudo corregir el movimiento.');
    } finally {
      setGuardando(false);
    }
  };

  const movimientoEditable = !!detalle
    && detalle.origen !== 'VENTA'
    && detalle.origen !== 'TRANSFERENCIA';
  const puedeCambiarTipo = !!detalle
    && detalle.origen !== 'GASTO'
    && (detalle.tipo_movimiento === 'ENTRADA' || detalle.tipo_movimiento === 'SALIDA');

  const moneda = data?.moneda_codigo || 'COP';
  const fmt = (v: string | number) => fmtMoneda(Number(v || 0), moneda);

  // El libro se calcula de viejo a nuevo para el saldo corrido, pero se
  // muestra de lo más reciente a lo más viejo.
  const filasOrdenadas = [...(data?.filas ?? [])].reverse();
  const totalFilas = filasOrdenadas.length;
  const totalPaginas = Math.max(1, Math.ceil(totalFilas / POR_PAGINA));
  const paginaActual = Math.min(pagina, totalPaginas);
  const inicioPagina = (paginaActual - 1) * POR_PAGINA;
  const filasPagina = filasOrdenadas.slice(inicioPagina, inicioPagina + POR_PAGINA);

  const columns: DataColumn<LibroCajaVistaFila>[] = [
    {
      key: 'fecha',
      header: 'Fecha',
      render: (f) => (
        <span className="font-mono text-xs text-yeikar-neutral/60 whitespace-nowrap">
          {new Date(`${f.fecha}T00:00:00`).toLocaleDateString('es-CO')}
        </span>
      ),
      mobilePrimary: true,
    },
    {
      key: 'persona_entidad',
      header: 'Persona o entidad',
      render: (f) => (
        <span className="text-xs font-bold text-yeikar-secondary">
          {f.persona_entidad || '—'}
        </span>
      ),
      mobileLabel: 'Persona o entidad',
    },
    {
      key: 'registro',
      header: 'Registrado por',
      render: (f) => (
        <span className="block text-xs leading-tight">
          <span className="font-bold text-yeikar-secondary">
            {f.usuario_nombre || '—'}
          </span>
          <span className="block font-mono text-[10px] text-yeikar-neutral/45">
            {fmtFechaHoraVE(f.created_at)}
          </span>
        </span>
      ),
      mobileLabel: 'Registrado por',
    },
    {
      key: 'concepto',
      header: 'Concepto',
      render: (f) => (
        <span className="text-sm text-yeikar-neutral/80 break-words">
          {f.concepto || '—'}
        </span>
      ),
      mobileLabel: 'Concepto',
      mobileFull: true,
    },
    {
      key: 'clasificacion',
      header: 'Clasificación',
      render: (f) => (
        f.clasificacion ? (
          <Badge tone={TONE[f.clasificacion] ?? 'neutral'} size="sm">
            {nombreClasificacion(f.clasificacion)}
          </Badge>
        ) : (
          <span className="text-[11px] text-yeikar-neutral/25">—</span>
        )
      ),
      mobileLabel: 'Clasificación',
    },
    {
      key: 'ingreso',
      header: 'Ingreso',
      align: 'right',
      render: (f) => (
        Number(f.ingreso) > 0
          ? <span className="font-mono text-sm font-semibold text-emerald-700">{fmt(f.ingreso)}</span>
          : <span className="text-yeikar-neutral/20">—</span>
      ),
      mobileLabel: 'Ingreso',
    },
    {
      key: 'egreso',
      header: 'Egreso',
      align: 'right',
      render: (f) => (
        Number(f.egreso) > 0
          ? <span className="font-mono text-sm font-semibold text-rose-700">{fmt(f.egreso)}</span>
          : <span className="text-yeikar-neutral/20">—</span>
      ),
      mobileLabel: 'Egreso',
    },
    {
      key: 'saldo',
      header: 'Saldo',
      align: 'right',
      render: (f) => (
        <span className={`font-mono text-sm font-black ${Number(f.saldo) < 0 ? 'text-rose-700' : 'text-yeikar-secondary'}`}>
          {fmt(f.saldo)}
        </span>
      ),
      mobileLabel: 'Saldo',
    },
  ];

  return (
    <div className="space-y-5">
      <div className="card p-4 flex flex-wrap items-end gap-3">
        <div className="w-full sm:w-64">
          <label className="block text-[10px] font-mono font-bold uppercase tracking-wider text-yeikar-neutral/45 mb-1">
            Cuenta
          </label>
          <SearchSelect
            value={cuentaId}
            onChange={(v) => setCuentaId(Number(v))}
            options={cuentas.map((c) => ({
              value: c.metodo_caja.id,
              label: `${c.metodo_caja.nombre} · ${c.metodo_caja.moneda_codigo || '?'}`,
            }))}
            placeholder="Seleccione la cuenta..."
          />
        </div>
        <div>
          <label className="block text-[10px] font-mono font-bold uppercase tracking-wider text-yeikar-neutral/45 mb-1">
            Desde
          </label>
          <Input type="date" value={desde} onChange={(e) => setDesde(e.target.value)} className="w-auto" />
        </div>
        <div>
          <label className="block text-[10px] font-mono font-bold uppercase tracking-wider text-yeikar-neutral/45 mb-1">
            Hasta
          </label>
          <Input type="date" value={hasta} onChange={(e) => setHasta(e.target.value)} className="w-auto" />
        </div>
        <Button variant="outline" onClick={cargar} disabled={loading}>
          {loading ? 'Cargando...' : 'Actualizar'}
        </Button>
        <p className="ml-auto text-[11px] text-yeikar-neutral/35">
          Saldo corrido del libro, como la hoja
        </p>
      </div>

      {error && (
        <div className="bg-red-50 border border-red-200 text-red-700 px-4 py-3 rounded-xl text-sm">
          {error}
        </div>
      )}

      {loading && !data ? (
        <div className="py-12"><Spinner label="Cargando libro..." /></div>
      ) : data ? (
        <>
          <div className="grid grid-cols-1 sm:grid-cols-2 lg:grid-cols-4 gap-4">
            <StatCard
              label="Saldo inicial"
              value={fmt(data.saldo_inicial)}
              accent="from-yeikar-secondary to-yeikar-secondary-light"
              hint="Antes del período"
            />
            <StatCard
              label="Ingresos"
              value={fmt(data.total_ingresos)}
              accent="from-emerald-500 to-emerald-400"
            />
            <StatCard
              label="Egresos"
              value={fmt(data.total_egresos)}
              accent="from-rose-500 to-rose-400"
            />
            <StatCard
              label="Saldo final"
              value={fmt(data.saldo_final)}
              accent="from-yeikar-primary to-yeikar-primary-light"
              hint={`${data.filas.length} movimientos`}
            />
          </div>

          {data.clasificaciones.length > 0 && (
            <div className="card p-4">
              <p className="text-[10px] font-mono font-bold uppercase tracking-wider text-yeikar-neutral/45 mb-2">
                Gastos del período por clasificación
              </p>
              <div className="flex flex-wrap gap-2">
                {data.clasificaciones.map((c) => (
                  <div key={c.clasificacion} className="rounded-xl border border-yeikar-secondary-light/10 bg-yeikar-tertiary/20 px-3 py-2">
                    <Badge tone={TONE[c.clasificacion] ?? 'neutral'} size="sm">{c.label}</Badge>
                    <span className="ml-2 font-mono text-sm font-black text-yeikar-secondary">{fmt(c.total)}</span>
                    <span className="ml-1 text-[10px] text-yeikar-neutral/40">({c.count})</span>
                  </div>
                ))}
              </div>
            </div>
          )}

          <Card
            title="Libro de caja"
            subtitle={`${data.cuenta_nombre} · ${new Date(`${data.fecha_desde}T00:00:00`).toLocaleDateString('es-CO')} a ${new Date(`${data.fecha_hasta}T00:00:00`).toLocaleDateString('es-CO')}`}
            bodyClassName="p-0"
          >
            <ResponsiveDataTable
              columns={columns}
              rows={filasPagina}
              rowKey={(f) => f.id}
              onRowClick={(f) => abrirDetalle(f)}
              empty={
                <div className="p-8">
                  <EmptyState
                    compact
                    title="Sin movimientos"
                    description="No hay movimientos en esta cuenta para el período."
                  />
                </div>
              }
            />
            {totalFilas > POR_PAGINA && (
              <div className="flex flex-wrap items-center justify-between gap-3 border-t border-yeikar-secondary-light/10 px-4 py-3">
                <span className="text-[11px] font-mono text-yeikar-neutral/45">
                  Mostrando {inicioPagina + 1}–{Math.min(inicioPagina + POR_PAGINA, totalFilas)} de {totalFilas}
                </span>
                <div className="flex items-center gap-2">
                  <Button
                    variant="outline"
                    size="sm"
                    disabled={paginaActual <= 1}
                    onClick={() => setPagina((p) => Math.max(1, p - 1))}
                  >
                    Más recientes
                  </Button>
                  <span className="text-xs font-bold text-yeikar-neutral/60">
                    Página {paginaActual} de {totalPaginas}
                  </span>
                  <Button
                    variant="outline"
                    size="sm"
                    disabled={paginaActual >= totalPaginas}
                    onClick={() => setPagina((p) => Math.min(totalPaginas, p + 1))}
                  >
                    Más antiguos
                  </Button>
                </div>
              </div>
            )}
          </Card>
        </>
      ) : null}

      <Modal
        open={detalle !== null}
        onClose={cerrarDetalle}
        title={editando ? 'Editar movimiento' : 'Detalle del movimiento'}
        subtitle={detalle ? new Date(`${detalle.fecha}T00:00:00`).toLocaleDateString('es-CO') : undefined}
        size="md"
        footer={
          <div className="flex flex-wrap items-center justify-end gap-2">
            {!editando && detalle && !movimientoEditable && (
              <span className="mr-auto self-center text-xs text-yeikar-neutral/45">
                Se corrige desde {detalle.origen === 'VENTA' ? 'la venta' : 'la transferencia'} de origen.
              </span>
            )}
            {editando ? (
              <>
                <Button variant="outline" onClick={() => { setEditando(false); setErrorMov(''); }}>
                  Cancelar
                </Button>
                <Button onClick={guardarEdicion} disabled={guardando}>
                  {guardando ? 'Guardando...' : 'Guardar cambios'}
                </Button>
              </>
            ) : (
              <>
                <Button variant="outline" onClick={cerrarDetalle}>Cerrar</Button>
                {detalle && movimientoEditable && (
                  <Button onClick={() => setEditando(true)}>Editar</Button>
                )}
              </>
            )}
          </div>
        }
      >
        {detalle && !editando && (
          <dl className="space-y-3">
            <FilaDetalle label="Fecha">
              {new Date(`${detalle.fecha}T00:00:00`).toLocaleDateString('es-CO')}
            </FilaDetalle>
            <FilaDetalle label="Persona o entidad">
              {detalle.persona_entidad || '—'}
            </FilaDetalle>
            <FilaDetalle label="Registrado por">
              {detalle.usuario_nombre || '—'}
            </FilaDetalle>
            <FilaDetalle label="Hora de registro">
              {fmtFechaHoraVE(detalle.created_at)}
            </FilaDetalle>
            <FilaDetalle label="Concepto">
              {detalle.concepto || '—'}
            </FilaDetalle>
            <FilaDetalle label="Clasificación">
              {detalle.clasificacion ? (
                <Badge tone={TONE[detalle.clasificacion] ?? 'neutral'} size="sm">
                  {nombreClasificacion(detalle.clasificacion)}
                </Badge>
              ) : '—'}
            </FilaDetalle>
            <FilaDetalle label="Ingreso">
              {Number(detalle.ingreso) > 0 ? fmt(detalle.ingreso) : '—'}
            </FilaDetalle>
            <FilaDetalle label="Egreso">
              {Number(detalle.egreso) > 0 ? fmt(detalle.egreso) : '—'}
            </FilaDetalle>
            <FilaDetalle label="Saldo">
              {fmt(detalle.saldo)}
            </FilaDetalle>
          </dl>
        )}

        {detalle && editando && (
          <div className="space-y-4">
            <Field label="Fecha" required>
              <Input
                type="date"
                value={editForm.fecha}
                onChange={(e) => setEditForm({ ...editForm, fecha: e.target.value })}
              />
            </Field>
            <Field label="Tipo">
              {puedeCambiarTipo ? (
                <Select
                  value={editForm.tipo}
                  onChange={(e) => setEditForm({
                    ...editForm,
                    tipo: e.target.value as LibroCajaVistaFila['tipo_movimiento'],
                  })}
                >
                  <option value="ENTRADA">Entrada</option>
                  <option value="SALIDA">Salida</option>
                </Select>
              ) : (
                <div className="rounded-lg border border-yeikar-secondary-light/20 bg-yeikar-tertiary/30 px-3 py-2 text-sm text-yeikar-neutral/70">
                  {detalle.tipo}
                </div>
              )}
            </Field>
            <Field label="Monto" required hint="Puedes corregir el monto sin borrar el movimiento.">
              <Input
                type="text"
                inputMode="decimal"
                value={editForm.monto}
                onChange={(e) => setEditForm({ ...editForm, monto: formatMontoInput(e.target.value) })}
                placeholder="0"
              />
            </Field>
            <Field label="Persona o entidad">
              <Input
                value={editForm.persona_entidad}
                onChange={(e) => setEditForm({ ...editForm, persona_entidad: e.target.value })}
                placeholder="Cliente, proveedor, empleado..."
              />
            </Field>
            <Field label="Concepto">
              <Textarea
                rows={3}
                value={editForm.concepto}
                onChange={(e) => setEditForm({ ...editForm, concepto: e.target.value })}
                placeholder="Motivo del movimiento..."
              />
            </Field>
            {detalle.clasificacion && (
              <p className="text-xs text-yeikar-neutral/45">
                La clasificación ({nombreClasificacion(detalle.clasificacion)}) se corrige desde Gastos.
              </p>
            )}
            {errorMov && (
              <p className="text-sm font-medium text-red-600">{errorMov}</p>
            )}
          </div>
        )}
      </Modal>
    </div>
  );
}
