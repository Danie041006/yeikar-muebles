import { useState, useEffect, useCallback } from 'react';
import {
  nominaService,
  Nomina as NominaData, NominaDraft, SaldoAguinaldo, NominaAreaConfig, NominaDetalle, NominaLinea,
  ResumenSemanal,
} from '../services/nominaService';
import { cuentasService, ResumenCuenta } from '../services/cuentasService';
import { useToast } from '../context/ToastContext';
import {
  Button, Card, Badge, Spinner, EmptyState, StatCard, PageHeader,
  Field, Input, Modal, ConfirmDialog, SearchSelect,
  ResponsiveDataTable, type DataColumn,
} from '../components/ui';

function fmt(d: Date): string {
  const m = String(d.getMonth() + 1).padStart(2, '0');
  const day = String(d.getDate()).padStart(2, '0');
  return `${d.getFullYear()}-${m}-${day}`;
}

function lunesDeSemana(): string {
  const d = new Date();
  const day = d.getDay();
  const diff = day === 0 ? 6 : day - 1;
  d.setDate(d.getDate() - diff);
  return fmt(d);
}

function sabadoDeSemana(): string {
  const d = new Date(lunesDeSemana() + 'T12:00:00');
  d.setDate(d.getDate() + 5);
  return fmt(d);
}

const fmtCOP = (n: number) => `$ ${(Number(n) || 0).toLocaleString('es-CO')}`;

const ESTADO_TONE: Record<string, 'blue' | 'green' | 'neutral'> = {
  BORRADOR: 'blue',
  PAGADA: 'green',
  ANULADA: 'neutral',
};

export default function Nomina() {
  const [nominas, setNominas] = useState<NominaData[]>([]);
  const [loading, setLoading] = useState(false);

  // Nueva nómina
  const [showNueva, setShowNueva] = useState(false);
  const [desde, setDesde] = useState(lunesDeSemana());
  const [hasta, setHasta] = useState(sabadoDeSemana());
  const [generando, setGenerando] = useState(false);
  const [draft, setDraft] = useState<NominaDraft | null>(null);
  const [resumenSem, setResumenSem] = useState<ResumenSemanal | null>(null);
  const [cargandoResumen, setCargandoResumen] = useState(false);

  // Detalle
  const [detalle, setDetalle] = useState<NominaData | null>(null);
  const [cuentas, setCuentas] = useState<ResumenCuenta[]>([]);
  const [lineaForm, setLineaForm] = useState<Record<number, { descripcion: string; cantidad: string; precio: string }>>({});
  const [varioForm, setVarioForm] = useState({ descripcion: '', monto: '' });
  const [confirmAnular, setConfirmAnular] = useState(false);
  const [paginando, setPaginando] = useState(false);

  // Aguinaldo y config
  const [showAguinaldo, setShowAguinaldo] = useState(false);
  const [saldos, setSaldos] = useState<SaldoAguinaldo[]>([]);
  const [showConfig, setShowConfig] = useState(false);
  const [areaConfig, setAreaConfig] = useState<NominaAreaConfig[]>([]);
  // Entrega de aguinaldo
  const [entregandoId, setEntregandoId] = useState<number | null>(null);
  const [cuentaAguinaldo, setCuentaAguinaldo] = useState<number | null>(null);
  const [pagandoAguinaldoId, setPagandoAguinaldoId] = useState<number | null>(null);

  const toast = useToast();

  const cargarNominas = useCallback(async () => {
    setLoading(true);
    try {
      const data = await nominaService.listar();
      setNominas(data);
    } finally {
      setLoading(false);
    }
  }, []);

  const cargarCuentas = useCallback(async () => {
    const data = await cuentasService.getResumen();
    setCuentas(data);
  }, []);

  useEffect(() => {
    cargarNominas();
    cargarCuentas();
  }, [cargarNominas, cargarCuentas]);

  const totalPagado = nominas.filter((n) => n.estado === 'PAGADA').reduce((s, n) => s + Number(n.total_nomina), 0);
  const enBorrador = nominas.filter((n) => n.estado === 'BORRADOR').length;

  // ── Cuentas de pago por empleado ─────────────────────────────────────────
  // Cada empleado puede cobrar por una cuenta distinta (efectivo, Nequi,
  // Bancolombia...). El pago no se habilita hasta que TODOS los que tienen
  // monto > 0 tengan su cuenta asignada.
  const [cuentaMasiva, setCuentaMasiva] = useState<number | null>(null);
  const [aplicandoMasivo, setAplicandoMasivo] = useState(false);

  const detallesConPago = detalle?.detalles.filter((d) => Number(d.monto_a_pagar) > 0) ?? [];
  const sinCuenta = detallesConPago.filter((d) => !d.metodo_caja_id);

  // La semana del modal ya tiene nómina activa (BORRADOR o PAGADA)?
  const semanaYaExiste = nominas.some(
    (n) =>
      (n.estado === 'BORRADOR' || n.estado === 'PAGADA') &&
      String(n.periodo_desde) === String(desde) &&
      String(n.periodo_hasta) === String(hasta),
  );

  const aplicarCuentaATodos = async () => {
    if (!detalle || !cuentaMasiva) return;
    setAplicandoMasivo(true);
    try {
      for (const d of sinCuenta) {
        await nominaService.actualizarDetalle(d.id, { metodo_caja_id: cuentaMasiva });
      }
      refrescarDetalle();
    } catch (err: any) {
      toast.error(err?.response?.data?.detail || 'Error al asignar la cuenta.');
    } finally {
      setAplicandoMasivo(false);
    }
  };

  const generarDraft = async () => {
    setGenerando(true);
    try {
      const d = await nominaService.generar(desde, hasta);
      setDraft(d);
    } catch (err: any) {
      toast.error(err?.response?.data?.detail || 'Error al generar la vista previa.');
    } finally {
      setGenerando(false);
    }
  };

  const cargarResumenSemanal = async () => {
    if (!desde || !hasta) return;
    setCargandoResumen(true);
    setResumenSem(null);
    try {
      setResumenSem(await nominaService.resumenSemanal(desde, hasta));
    } catch (e: any) {
      toast.error(e?.response?.data?.detail || 'No se pudo cargar la producción de la semana.');
    } finally {
      setCargandoResumen(false);
    }
  };

  const crearBorrador = async () => {    try {
      const n = await nominaService.crear(desde, hasta);
      setShowNueva(false);
      setDraft(null);
      await cargarNominas();
      await abrirDetalle(n.id);
      toast.success('Nómina creada.');
    } catch (err: any) {
      // Ej.: "Ya existe una nómina para esa semana" — mostrar el motivo real.
      toast.error(err?.response?.data?.detail || 'Error al crear la nómina.');
    }
  };

  const abrirDetalle = async (id: number) => {
    const n = await nominaService.obtener(id);
    setDetalle(n);
    setVarioForm({ descripcion: '', monto: '' });
    if (!cuentas.length) cargarCuentas();
  };

  const refrescarDetalle = async () => {
    if (!detalle) return;
    const n = await nominaService.obtener(detalle.id);
    setDetalle(n);
    cargarNominas();
  };

  const guardarMonto = async (d: NominaDetalle, monto: number) => {
    if (isNaN(monto) || monto < 0) return;
    try {
      await nominaService.actualizarDetalle(d.id, { monto_a_pagar: monto });
      refrescarDetalle();
    } catch (err: any) {
      toast.error(err?.response?.data?.detail || 'Error al guardar el monto.');
    }
  };

  const cambiarCuenta = async (d: NominaDetalle, cuentaId: number) => {
    try {
      await nominaService.actualizarDetalle(d.id, { metodo_caja_id: cuentaId });
      refrescarDetalle();
    } catch (err: any) {
      toast.error(err?.response?.data?.detail || 'Error al asignar la cuenta.');
    }
  };

  const agregarLinea = async (d: NominaDetalle) => {
    const f = lineaForm[d.id];
    if (!f || !f.descripcion.trim() || !Number(f.cantidad) || !Number(f.precio)) return;
    try {
      await nominaService.agregarLinea(d.id, {
        descripcion: f.descripcion.trim(),
        cantidad: Number(f.cantidad),
        precio_unitario: Number(f.precio),
      });
      refrescarDetalle();
    } catch (err: any) {
      toast.error(err?.response?.data?.detail || 'Error al agregar la línea.');
    }
  };

  const eliminarLinea = async (lineaId: number) => {
    try {
      await nominaService.eliminarLinea(lineaId);
      refrescarDetalle();
    } catch (err: any) {
      toast.error(err?.response?.data?.detail || 'Error al eliminar la línea.');
    }
  };

  const agregarVario = async () => {
    if (!detalle || !varioForm.descripcion.trim() || !Number(varioForm.monto)) return;
    try {
      await nominaService.agregarConceptoVario(detalle.id, {
        descripcion: varioForm.descripcion.trim(),
        monto: Number(varioForm.monto),
      });
      refrescarDetalle();
    } catch (err: any) {
      toast.error(err?.response?.data?.detail || 'Error al agregar el concepto.');
    }
  };

  const eliminarVario = async (conceptoId: number) => {
    try {
      await nominaService.eliminarConceptoVario(conceptoId);
      refrescarDetalle();
    } catch (err: any) {
      toast.error(err?.response?.data?.detail || 'Error al eliminar el concepto.');
    }
  };

  const pagar = async () => {
    if (!detalle) return;
    setPaginando(true);
    try {
      const n = await nominaService.pagar(detalle.id);
      setDetalle(n);
      await cargarNominas();
      toast.success('Nómina pagada: se generaron los gastos y salidas de caja.');
    } catch (err: any) {
      toast.error(err?.response?.data?.detail || 'Error al pagar la nómina.');
    } finally {
      setPaginando(false);
    }
  };

  const anular = async () => {
    if (!detalle) return;
    try {
      const n = await nominaService.anular(detalle.id);
      setDetalle(n);
      setConfirmAnular(false);
      await cargarNominas();
      toast.success('Nómina anulada y gastos revertidos.');
    } catch (err: any) {
      toast.error(err?.response?.data?.detail || 'Error al anular la nómina.');
    }
  };

  const verAguinaldo = async () => {
    const s = await nominaService.saldosAguinaldo();
    setSaldos(s);
    setShowAguinaldo(true);
  };

  const usarSemanaActual = () => {
    setDesde(lunesDeSemana());
    setHasta(sabadoDeSemana());
    setDraft(null);
  };

  const entregarAguinaldo = async (empleadoId: number) => {
    if (!cuentaAguinaldo) return;
    setPagandoAguinaldoId(empleadoId);
    try {
      const res = await nominaService.pagarAguinaldo(empleadoId, cuentaAguinaldo);
      toast.success(`Aguinaldo entregado a ${res.empleado_nombre}`);
      setSaldos(await nominaService.saldosAguinaldo());
      setEntregandoId(null);
      setCuentaAguinaldo(null);
    } catch (err: any) {
      toast.error(err?.response?.data?.detail || 'Error al entregar el aguinaldo.');
    } finally {
      setPagandoAguinaldoId(null);
    }
  };

  const verConfig = async () => {
    const c = await nominaService.getAreaConfig();
    setAreaConfig(c);
    setShowConfig(true);
  };

  const guardarConfig = async (cfg: NominaAreaConfig, pct: number) => {
    await nominaService.actualizarAreaConfig(cfg.area_id, pct);
    verConfig();
  };

  // ---------------- Resumen TRABAJADOR ----------------
  const resumenPorCargo = detalle ? (() => {
    const grupos = new Map<string, { cargo: string; total: number }>();
    detalle.detalles.forEach((d) => {
      const cargo = d.cargo_nombre || 'SIN CARGO';
      const g = grupos.get(cargo) || { cargo, total: 0 };
      g.total += Number(d.monto_a_pagar);
      grupos.set(cargo, g);
    });
    return Array.from(grupos.values());
  })() : [];

  // ---------------- Impresión estilo Excel ----------------
  const imprimir = (n: NominaData) => {
    const esc = (s: string) => s.replace(/&/g, '&amp;').replace(/</g, '&lt;').replace(/>/g, '&gt;');
    const fila = (l: { descripcion: string; cliente_nombre?: string | null; cantidad: number; precio_unitario: number; total: number }) =>
      `<tr><td class="c">${l.cantidad}</td><td>${esc(l.descripcion)}</td><td>${esc(l.cliente_nombre || '')}</td><td class="r">${fmtCOP(Number(l.precio_unitario))}</td><td class="r">${fmtCOP(Number(l.total))}</td></tr>`;
    const cab = `<div class="cab">COMERCIALIZADORA YEIKAR<br/>NOMINA DEL ${n.periodo_desde} AL ${n.periodo_hasta}</div>`;
    const bloques = n.detalles.map((d) => `
      <div class="bloque">
        <h3>${esc(d.empleado_nombre)}</h3>
        <table>
          <tr><th>CANT.</th><th>DESCRIPCION</th><th>CLIENTE</th><th>PRECIO UNI</th><th>TOTAL</th></tr>
          ${d.lineas.map(fila).join('')}
        </table>
        <div class="tot">
          <span>TOTAL DE PRODUCCION</span><span class="r">${fmtCOP(Number(d.total_produccion))}</span>
        </div>
        ${Number(d.bono_aguinaldo) > 0 ? `<div class="tot"><span>BONO AGUINALDO ACUMULADO</span><span class="r">${fmtCOP(Number(d.bono_aguinaldo))}</span></div>` : ''}
        <div class="tot nomina"><span>NOMINA</span><span class="r">${fmtCOP(Number(d.monto_a_pagar))}</span></div>
        <div class="firmas"><span>ENTREGA __________________</span><span>RECIBE __________________</span></div>
      </div>`).join('');
    const varios = n.conceptos_varios.length ? `
      <div class="bloque">
        <h3>VARIOS</h3>
        ${n.conceptos_varios.map((c) => `<div class="tot"><span>${esc(c.descripcion)}</span><span class="r">${fmtCOP(Number(c.monto))}</span></div>`).join('')}
      </div>` : '';
    const resumen = n.detalles.map((d) => `<tr><td>${esc(d.cargo_nombre || '')}</td><td>${esc(d.empleado_nombre)}</td><td class="r">${fmtCOP(Number(d.monto_a_pagar))}</td></tr>`).join('');
    const html = `<html><head><title>Nómina ${n.periodo_desde}</title>
      <style>
        body { font-family: 'Courier New', monospace; color: #000; padding: 20px; }
        .cab { text-align: center; font-weight: bold; font-size: 16px; margin-bottom: 18px; }
        .bloque { border: 1px solid #000; padding: 12px; margin-bottom: 16px; page-break-inside: avoid; }
        h3 { margin: 0 0 6px; font-size: 14px; }
        table { width: 100%; border-collapse: collapse; font-size: 12px; }
        th { border-bottom: 1px solid #000; text-align: left; padding: 3px 6px; }
        td { padding: 3px 6px; }
        .r { text-align: right; } .c { text-align: center; }
        .tot { display: flex; justify-content: space-between; margin-top: 6px; font-weight: bold; }
        .nomina { border-top: 1px solid #000; padding-top: 6px; font-size: 14px; }
        .firmas { display: flex; justify-content: space-between; margin-top: 14px; }
      </style></head><body>
      ${cab}${bloques}${varios}
      <div class="bloque"><h3>RESUMEN TRABAJADOR</h3>
        <table><tr><th>CARGO</th><th>TRABAJADOR</th><th class="r">MONTO</th></tr>${resumen}</table>
        <div class="tot nomina"><span>TOTAL NOMINA</span><span class="r">${fmtCOP(Number(n.total_nomina))}</span></div>
      </div>
      </body></html>`;
    const w = window.open('', '_blank');
    if (!w) return;
    w.document.write(html);
    w.document.close();
    w.focus();
    w.print();
  };

  const columns: DataColumn<NominaData>[] = [
    {
      key: 'periodo',
      header: 'Periodo',
      render: (n) => <span className="font-mono text-xs">{n.periodo_desde} → {n.periodo_hasta}</span>,
      mobilePrimary: true,
    },
    {
      key: 'estado',
      header: 'Estado',
      render: (n) => <Badge tone={ESTADO_TONE[n.estado]}>{n.estado}</Badge>,
      mobileHidden: true,
    },
    {
      key: 'creador',
      header: 'Creada por',
      render: (n) => <span className="text-yeikar-neutral/60">{n.creador_nombre || '-'}</span>,
      mobileLabel: 'Creada por',
    },
    {
      key: 'total',
      header: 'Total Nómina',
      align: 'right',
      render: (n) => <span className="font-mono font-bold text-yeikar-secondary">{fmtCOP(Number(n.total_nomina))}</span>,
      mobileLabel: 'Total Nómina',
    },
  ];

  const renderActions = (n: NominaData) => (
    <div className="inline-flex items-center gap-1">
      <Button variant="ghost" size="sm" onClick={() => abrirDetalle(n.id)}>Ver</Button>
      <Button variant="ghost" size="sm" onClick={() => imprimir(n)}>Imprimir</Button>
    </div>
  );

  const lineasColumns: DataColumn<NominaLinea>[] = [
    {
      key: 'cantidad',
      header: 'CANT',
      render: (l) => <span className="font-mono text-xs">{l.cantidad}</span>,
      mobileLabel: 'Cant.',
    },
    {
      key: 'descripcion',
      header: 'DESCRIPCIÓN',
      render: (l) => (
        <span>
          {l.descripcion}
          {l.origen === 'ETAPA' ? <span className="ml-1 text-[10px] text-yeikar-primary">auto</span> : null}
        </span>
      ),
      mobilePrimary: true,
    },
    {
      key: 'area',
      header: 'ÁREA',
      render: (l) => <span className="text-xs text-yeikar-neutral/50">{l.area?.nombre || '-'}</span>,
      mobileLabel: 'Área',
    },
    {
      key: 'cliente',
      header: 'CLIENTE',
      render: (l) => <span className="text-xs text-yeikar-neutral/50">{l.cliente_nombre || '-'}</span>,
      mobileLabel: 'Cliente',
    },
    {
      key: 'precio',
      header: 'PRECIO UNI',
      align: 'right',
      render: (l) => <span className="font-mono text-xs">{fmtCOP(Number(l.precio_unitario))}</span>,
      mobileLabel: 'Precio Uni',
    },
    {
      key: 'total',
      header: 'TOTAL',
      align: 'right',
      render: (l) => <span className="font-mono font-bold">{fmtCOP(Number(l.total))}</span>,
      mobileLabel: 'Total',
    },
  ];

  const renderLineaActions = (l: NominaLinea) => (
    <button
      className="text-red-500 hover:text-red-700 text-xs"
      onClick={() => eliminarLinea(l.id)}
      title="Eliminar línea"
    >×</button>
  );

  return (
    <div className="space-y-6">
      <PageHeader
        eyebrow="Finanzas"
        title="Nómina Semanal"
        subtitle="Genera, revisa y paga la nómina de cada semana"
        actions={
          <>
            <Button variant="outline" onClick={verConfig}>
              % Aguinaldo por área
            </Button>
            <Button variant="outline" onClick={verAguinaldo}>
              Saldos de aguinaldo
            </Button>
            <Button onClick={() => setShowNueva(true)}>
              <svg className="w-4 h-4" fill="none" stroke="currentColor" viewBox="0 0 24 24">
                <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2.5} d="M12 4v16m8-8H4" />
              </svg>
              Nueva Nómina
            </Button>
          </>
        }
      />

      <div className="grid grid-cols-1 sm:grid-cols-3 gap-5">
        <StatCard label="Semanas registradas" value={`${nominas.length}`} accent="from-yeikar-primary to-yeikar-primary-light" />
        <StatCard label="En borrador" value={`${enBorrador}`} accent="from-blue-600 to-blue-500" iconBg="bg-blue-50" iconText="text-blue-600" />
        <StatCard label="Total pagado (COP)" value={fmtCOP(totalPagado)} accent="from-green-600 to-green-500" iconBg="bg-green-50" iconText="text-green-700" />
      </div>

      <Card>
        {loading ? (
          <div className="p-8 flex justify-center">
            <Spinner size="sm" />
          </div>
        ) : (
          <ResponsiveDataTable
            columns={columns}
            rows={nominas}
            rowKey={(n) => n.id}
            cardBadge={(n) => <Badge tone={ESTADO_TONE[n.estado]}>{n.estado}</Badge>}
            tableActions={renderActions}
            cardActions={renderActions}
            empty={
              <div className="p-8">
                <EmptyState compact title="Sin nóminas" description="Genera la primera nómina semanal."
                  action={<Button size="sm" onClick={() => setShowNueva(true)}>Nueva Nómina</Button>} />
              </div>
            }
          />
        )}
      </Card>

      {/* ---------------- Modal: Nueva Nómina ---------------- */}
      <Modal
        open={showNueva}
        onClose={() => { setShowNueva(false); setDraft(null); setResumenSem(null); }}
        title="Nueva Nómina"
        subtitle="Selecciona la semana de la nómina (lunes a sábado por defecto)"
        size="xl"
        footer={
          <>
            <Button variant="outline" onClick={() => { setShowNueva(false); setDraft(null); setResumenSem(null); }}>Cancelar</Button>
            <Button onClick={crearBorrador} disabled={!draft || semanaYaExiste} title={semanaYaExiste ? 'Esa semana ya tiene una nómina' : undefined}>
              Guardar borrador
            </Button>
          </>
        }
      >
        <div className="space-y-4">
          {/* Aviso preventivo: no se puede duplicar la semana */}
          {semanaYaExiste && (
            <div className="rounded-xl border border-amber-300 bg-amber-50/70 px-3 py-2 text-xs font-bold text-amber-900">
              Ya existe una nómina para {desde} → {hasta}. Elige otra semana o trabaja sobre la existente.
            </div>
          )}
          <div className="grid grid-cols-2 gap-4">
            <Field label="Desde" required>
              <Input type="date" value={desde} onChange={(e) => setDesde(e.target.value)} />
            </Field>
            <Field label="Hasta" required>
              <Input type="date" value={hasta} onChange={(e) => setHasta(e.target.value)} />
            </Field>
          </div>
          <div className="flex items-center gap-2 flex-wrap">
            <Button variant="outline" size="sm" onClick={usarSemanaActual}>
              Usar esta semana
            </Button>
            <Button
              variant="outline"
              size="sm"
              onClick={cargarResumenSemanal}
              disabled={cargandoResumen || !desde || !hasta}
            >
              {cargandoResumen ? 'Cargando…' : 'Ver producción de la semana'}
            </Button>
            <span className="text-xs text-yeikar-neutral/50">
              Lunes → Sábado (hoy: {lunesDeSemana()} → {sabadoDeSemana()})
            </span>
          </div>

          {resumenSem && (
            <div className="space-y-3 border border-yeikar-secondary-light/15 rounded-xl p-4 bg-yeikar-tertiary/20">
              <p className="text-xs font-bold uppercase tracking-wider text-yeikar-neutral/50">
                Producción completada {resumenSem.desde} → {resumenSem.hasta}
              </p>
              {resumenSem.empleados.length === 0 && (
                <p className="text-sm text-yeikar-neutral/50">Sin producción completada ni mano de obra en este rango.</p>
              )}
              {resumenSem.empleados.map((e) => (
                <div key={e.empleado_id} className="bg-white rounded-xl border border-yeikar-secondary-light/10 p-3 space-y-2">
                  <div className="flex items-center justify-between gap-2 flex-wrap">
                    <p className="font-headline font-bold text-sm text-yeikar-secondary">
                      {e.nombre}
                      {e.cargo && <span className="ml-1.5 text-xs font-normal text-yeikar-neutral/50">{e.cargo}</span>}
                    </p>
                    <div className="flex items-center gap-1.5">
                      <Badge tone={e.tipo_pago === 'DESTAJO' ? 'blue' : 'neutral'}>{e.tipo_pago || '—'}</Badge>
                      {!e.en_nomina && <Badge tone="red">fuera de nómina</Badge>}
                    </div>
                  </div>
                  {e.piezas.length > 0 && (
                    <table className="w-full text-xs">
                      <thead>
                        <tr className="text-left text-[10px] uppercase text-yeikar-neutral/45 border-b border-yeikar-secondary-light/10">
                          <th className="py-1">Producto</th>
                          <th className="py-1">Área</th>
                          <th className="py-1">Cliente</th>
                          <th className="py-1 text-right">Cant</th>
                          <th className="py-1 text-right">Precio</th>
                          <th className="py-1 text-right">Total</th>
                        </tr>
                      </thead>
                      <tbody>
                        {e.piezas.map((pz, i) => (
                          <tr key={i} className="border-b border-yeikar-secondary-light/5">
                            <td className="py-1 pr-2 text-yeikar-secondary">{pz.producto}</td>
                            <td className="py-1 pr-2 text-yeikar-neutral/70">{pz.area ?? '—'}</td>
                            <td className="py-1 pr-2 text-yeikar-neutral/70">{pz.cliente ?? '—'}</td>
                            <td className="py-1 text-right font-mono">{pz.cantidad}</td>
                            <td className="py-1 text-right font-mono">
                              {pz.precio_unitario != null ? fmtCOP(pz.precio_unitario) : (
                                <span className="text-red-600 font-bold">SIN PRECIO</span>
                              )}
                            </td>
                            <td className="py-1 text-right font-mono font-semibold">
                              {pz.total != null ? fmtCOP(pz.total) : '—'}
                            </td>
                          </tr>
                        ))}
                      </tbody>
                    </table>
                  )}
                  <div className="flex flex-wrap gap-x-5 gap-y-1 text-xs">
                    <span>Total destajo: <b className="font-mono">{fmtCOP(e.total_destajo)}</b></span>
                    {e.piezas_sin_precio > 0 && (
                      <span className="text-red-600 font-bold">{e.piezas_sin_precio} pieza(s) SIN PRECIO en el tarifario</span>
                    )}
                    <span>Aguinaldo estimado: <b className="font-mono">{fmtCOP(e.aguinaldo_estimado)}</b></span>
                    {e.mano_obra.total > 0 && (
                      <span>Mano de obra: <b className="font-mono">{fmtCOP(e.mano_obra.total)}</b>
                        {' '}({fmtCOP(e.mano_obra.pagado)} pagada / {fmtCOP(e.mano_obra.pendiente)} pendiente)
                      </span>
                    )}
                  </div>
                  {e.mano_obra.lineas.length > 0 && (
                    <ul className="text-[11px] text-yeikar-neutral/60 space-y-0.5 pl-3 list-disc">
                      {e.mano_obra.lineas.map((l, i) => (
                        <li key={i}>
                          MO {l.descripcion} — {fmtCOP(l.monto)} {l.pagado ? '(pagada)' : '(pendiente)'}
                        </li>
                      ))}
                    </ul>
                  )}
                </div>
              ))}
            </div>
          )}

          <Button variant="outline" onClick={generarDraft} disabled={generando || !desde || !hasta}>
            {generando ? 'Generando...' : 'Generar borrador automático'}
          </Button>
          {draft && (
            <div className="rounded-xl border border-yeikar-primary/30 bg-yeikar-primary/5 p-4 space-y-3 max-h-80 overflow-y-auto">
              <p className="text-sm font-bold text-yeikar-secondary">
                {draft.detalles.length} empleados en nómina · Total: {fmtCOP(Number(draft.total_nomina))}
              </p>
              {draft.detalles.map((d) => (
                <div key={d.empleado_id} className="flex items-center justify-between rounded-lg bg-white/70 px-3 py-2 text-sm">
                  <span className="font-medium text-yeikar-secondary">
                    {d.empleado_nombre}
                    {d.cargo_nombre && <span className="ml-2 text-xs text-yeikar-neutral/40">{d.cargo_nombre}</span>}
                  </span>
                  <div className="flex items-center gap-3 font-mono">
                    <span className="text-xs text-yeikar-neutral/50">{d.lineas.length} líneas</span>
                    <span className="font-bold text-yeikar-dark">{fmtCOP(Number(d.monto_a_pagar))}</span>
                    {Number(d.bono_aguinaldo) > 0 && (
                      <Badge tone="gold">+{fmtCOP(Number(d.bono_aguinaldo))} aguinaldo</Badge>
                    )}
                  </div>
                </div>
              ))}
            </div>
          )}
        </div>
      </Modal>

      {/* ---------------- Modal: Detalle de nómina ---------------- */}
      <Modal
        open={detalle !== null}
        onClose={() => setDetalle(null)}
        title={`Nómina ${detalle?.periodo_desde} → ${detalle?.periodo_hasta}`}
        subtitle={detalle ? `Estado: ${detalle.estado} · Total: ${fmtCOP(Number(detalle.total_nomina))}` : ''}
        size="4xl"
        footer={
          detalle && detalle.estado === 'BORRADOR' ? (
            <>
              <Button variant="outline" onClick={() => setDetalle(null)}>Cerrar</Button>
              <Button variant="outline" onClick={() => imprimir(detalle)}>Imprimir</Button>
              <span className="text-[11px] font-bold text-red-600 max-w-[220px] text-right leading-tight">
                {sinCuenta.length > 0 ? `Asigna la cuenta de ${sinCuenta.length} empleado(s) para poder pagar` : ''}
              </span>
              <Button onClick={pagar} disabled={paginando || sinCuenta.length > 0} title={sinCuenta.length > 0 ? 'Faltan cuentas de pago por asignar' : undefined}>
                {paginando ? 'Pagando...' : 'Pagar Nómina'}
              </Button>
            </>
          ) : detalle && detalle.estado === 'PAGADA' ? (
            <>
              <Button variant="outline" onClick={() => setDetalle(null)}>Cerrar</Button>
              <Button variant="outline" onClick={() => imprimir(detalle)}>Imprimir</Button>
              <Button variant="danger" onClick={() => setConfirmAnular(true)}>Anular</Button>
            </>
          ) : (
            <>
              <Button variant="outline" onClick={() => setDetalle(null)}>Cerrar</Button>
              <Button variant="outline" onClick={() => imprimir(detalle!)}>Imprimir</Button>
            </>
          )
        }
      >
        {detalle && (
          <div className="space-y-4">
            {/* Aviso de cuentas pendientes: cada empleado puede cobrar por una
                cuenta distinta; el pago se bloquea hasta asignarlas todas. */}
            {detalle.estado === 'BORRADOR' && sinCuenta.length > 0 && (
              <div className="rounded-xl border border-amber-300 bg-amber-50/70 p-3 space-y-2">
                <p className="text-xs font-bold text-amber-900">
                  Falta la cuenta de pago de {sinCuenta.length} empleado(s): {sinCuenta.map((d) => d.empleado_nombre).join(', ')}
                </p>
                <div className="flex flex-wrap items-center gap-2">
                  <span className="text-[11px] text-amber-900/70">Asignar una misma cuenta a todos los faltantes:</span>
                  <div className="w-56">
                    <SearchSelect
                      value={cuentaMasiva ?? 0}
                      onChange={(v) => setCuentaMasiva(Number(v))}
                      options={cuentas.map((c) => ({ value: c.metodo_caja.id, label: c.metodo_caja.nombre }))}
                      placeholder="Seleccionar..."
                    />
                  </div>
                  <Button size="sm" variant="outline" disabled={!cuentaMasiva || aplicandoMasivo} onClick={aplicarCuentaATodos}>
                    {aplicandoMasivo ? 'Aplicando...' : 'Aplicar a todos'}
                  </Button>
                  <span className="text-[10px] text-amber-800/60 italic">Luego ajusta individualmente quien pida otro método (Nequi, etc.).</span>
                </div>
              </div>
            )}
            {detalle.detalles.map((d) => (
              <div key={d.id} className="rounded-xl border border-yeikar-secondary-light/10 bg-white/60 p-4 space-y-3">
                <div className="flex flex-wrap items-center justify-between gap-2">
                  <div className="flex items-center gap-2">
                    <span className="font-headline font-black text-yeikar-secondary">{d.empleado_nombre}</span>
                    <Badge tone={d.tipo_pago === 'DESTAJO' ? 'purple' : 'neutral'}>{d.tipo_pago}</Badge>
                    {d.cargo_nombre && <span className="text-xs text-yeikar-neutral/40">{d.cargo_nombre}</span>}
                  </div>
                  <div className="flex items-center gap-3">
                    <span className={`text-xs ${!d.metodo_caja_id && Number(d.monto_a_pagar) > 0 ? 'font-bold text-red-600' : 'text-yeikar-neutral/50'}`}>
                      Cuenta:{!d.metodo_caja_id && Number(d.monto_a_pagar) > 0 ? ' ¡falta!' : ''}
                    </span>
                    <div className={`w-52 rounded-lg ${!d.metodo_caja_id && Number(d.monto_a_pagar) > 0 ? 'ring-2 ring-red-400' : ''}`}>
                      <SearchSelect
                        value={d.metodo_caja_id || 0}
                        onChange={(v) => cambiarCuenta(d, Number(v))}
                        options={cuentas.map((c) => ({ value: c.metodo_caja.id, label: c.metodo_caja.nombre }))}
                        placeholder="Seleccione cuenta..."
                      />
                    </div>
                  </div>
                </div>

                <div className="space-y-3">
                  <ResponsiveDataTable
                    columns={lineasColumns}
                    rows={d.lineas}
                    rowKey={(l) => l.id}
                    tableActions={detalle.estado === 'BORRADOR' ? renderLineaActions : undefined}
                    cardActions={detalle.estado === 'BORRADOR' ? renderLineaActions : undefined}
                  />
                  {detalle.estado === 'BORRADOR' && (
                    <div className="flex flex-wrap items-center gap-2 border-t border-yeikar-secondary-light/10 pt-3">
                      <Input
                        type="number"
                        className="w-16 font-mono"
                        placeholder="Cant"
                        value={lineaForm[d.id]?.cantidad || ''}
                        onChange={(e) => setLineaForm((p) => ({ ...p, [d.id]: { descripcion: p[d.id]?.descripcion || '', cantidad: e.target.value, precio: p[d.id]?.precio || '' } }))}
                      />
                      <Input
                        type="text"
                        className="flex-1 min-w-[200px]"
                        placeholder="Línea manual (horas, cortes, préstamo...)"
                        value={lineaForm[d.id]?.descripcion || ''}
                        onChange={(e) => setLineaForm((p) => ({ ...p, [d.id]: { descripcion: e.target.value, cantidad: p[d.id]?.cantidad || '', precio: p[d.id]?.precio || '' } }))}
                      />
                      <Input
                        type="number"
                        className="w-32 font-mono"
                        placeholder="Precio"
                        value={lineaForm[d.id]?.precio || ''}
                        onChange={(e) => setLineaForm((p) => ({ ...p, [d.id]: { descripcion: p[d.id]?.descripcion || '', cantidad: p[d.id]?.cantidad || '', precio: e.target.value } }))}
                      />
                      <Button size="sm" variant="outline" onClick={() => agregarLinea(d)}>+</Button>
                    </div>
                  )}
                </div>

                <div className="flex flex-wrap items-end justify-end gap-5">
                  <div className="text-right">
                    <p className="text-[10px] font-bold uppercase tracking-wider text-yeikar-neutral/40">Total producción</p>
                    <p className="font-mono font-bold text-yeikar-secondary">{fmtCOP(Number(d.total_produccion))}</p>
                  </div>
                  <div className="text-right">
                    <p className="text-[10px] font-bold uppercase tracking-wider text-yeikar-neutral/40">Aguinaldo semana</p>
                    <p className="font-mono font-bold text-amber-700">+{fmtCOP(Number(d.bono_aguinaldo))}</p>
                  </div>
                  <div className="text-right">
                    <p className="text-[10px] font-bold uppercase tracking-wider text-yeikar-neutral/40">Monto a pagar</p>
                    {detalle.estado === 'BORRADOR' ? (
                      <Input
                        type="number"
                        className="w-40 font-mono font-bold text-right"
                        defaultValue={d.monto_a_pagar}
                        onBlur={(e) => guardarMonto(d, Number(e.target.value))}
                        onKeyDown={(e) => {
                          if (e.key === 'Enter') guardarMonto(d, Number((e.target as HTMLInputElement).value));
                        }}
                      />
                    ) : (
                      <p className="font-mono text-xl font-black text-yeikar-dark">{fmtCOP(Number(d.monto_a_pagar))}</p>
                    )}
                  </div>
                </div>
              </div>
            ))}

            {/* Conceptos varios */}
            <div className="rounded-xl border border-dashed border-yeikar-secondary-light/20 p-4 space-y-3">
              <h4 className="font-headline font-black text-sm text-yeikar-secondary uppercase tracking-wider">Varios</h4>
              {detalle.conceptos_varios.map((c) => (
                <div key={c.id} className="flex items-center justify-between text-sm">
                  <span className="text-yeikar-neutral/70">{c.descripcion}</span>
                  <div className="flex items-center gap-3">
                    <span className="font-mono font-bold">{fmtCOP(Number(c.monto))}</span>
                    {detalle.estado === 'BORRADOR' && (
                      <button className="text-red-500 hover:text-red-700 text-xs" onClick={() => eliminarVario(c.id)}>×</button>
                    )}
                  </div>
                </div>
              ))}
              {detalle.estado === 'BORRADOR' && (
                <div className="flex items-center gap-2">
                  <Input
                    type="text"
                    className="flex-1"
                    placeholder="Concepto (CARMEN MANILLAS, ALMUERZOS...)"
                    value={varioForm.descripcion}
                    onChange={(e) => setVarioForm((p) => ({ ...p, descripcion: e.target.value }))}
                  />
                  <Input
                    type="number"
                    className="w-36 font-mono"
                    placeholder="Monto"
                    value={varioForm.monto}
                    onChange={(e) => setVarioForm((p) => ({ ...p, monto: e.target.value }))}
                  />
                  <Button size="sm" variant="outline" onClick={agregarVario}>Agregar</Button>
                </div>
              )}
            </div>

            {/* Resumen TRABAJADOR */}
            {resumenPorCargo.length > 0 && (
              <div className="rounded-xl border border-yeikar-primary/25 bg-yeikar-primary/5 p-4 space-y-2">
                <h4 className="font-headline font-black text-sm text-yeikar-secondary uppercase tracking-wider">Resumen trabajador</h4>
                {resumenPorCargo.map((g) => (
                  <div key={g.cargo} className="flex items-center justify-between text-sm">
                    <span className="font-bold text-yeikar-secondary">{g.cargo}</span>
                    <span className="font-mono">{fmtCOP(g.total)}</span>
                  </div>
                ))}
                <div className="flex items-center justify-between border-t border-yeikar-primary/20 pt-2">
                  <span className="font-headline font-black text-yeikar-secondary">TOTAL NOMINA</span>
                  <span className="font-mono text-lg font-black text-yeikar-dark">{fmtCOP(Number(detalle.total_nomina))}</span>
                </div>
              </div>
            )}
          </div>
        )}
      </Modal>

      {/* ---------------- Modal: Saldos de aguinaldo ---------------- */}
      <Modal
        open={showAguinaldo}
        onClose={() => setShowAguinaldo(false)}
        title="Saldos de aguinaldo"
        subtitle="Bono acumulado por producción (para entregar a fin de año)"
      >
        <div className="space-y-2 max-h-96 overflow-y-auto">
          {saldos.length === 0 && <p className="text-sm text-yeikar-neutral/50">No hay empleados en nómina.</p>}
          {saldos.map((s) => (
            <div key={s.empleado_id} className="rounded-lg bg-white/70 px-3 py-2 text-sm">
              {entregandoId === s.empleado_id ? (
                <div className="space-y-2">
                  <div className="flex items-center justify-between">
                    <span className="font-medium text-yeikar-secondary">
                      {s.empleado_nombre}
                      {s.cargo_nombre && <span className="ml-2 text-xs text-yeikar-neutral/40">{s.cargo_nombre}</span>}
                    </span>
                    <span className="font-mono font-bold text-amber-700">{fmtCOP(Number(s.saldo_aguinaldo))}</span>
                  </div>
                  <div className="flex items-center gap-2">
                    <div className="flex-1">
                      <SearchSelect
                        value={cuentaAguinaldo || 0}
                        onChange={(v) => setCuentaAguinaldo(Number(v))}
                        options={cuentas.map((c) => ({ value: c.metodo_caja.id, label: c.metodo_caja.nombre }))}
                        placeholder="Seleccione cuenta..."
                      />
                    </div>
                    <Button
                      size="sm"
                      onClick={() => entregarAguinaldo(s.empleado_id)}
                      disabled={!cuentaAguinaldo || pagandoAguinaldoId === s.empleado_id}
                    >
                      {pagandoAguinaldoId === s.empleado_id ? 'Entregando...' : 'Confirmar'}
                    </Button>
                    <Button
                      size="sm"
                      variant="outline"
                      onClick={() => { setEntregandoId(null); setCuentaAguinaldo(null); }}
                    >
                      Cancelar
                    </Button>
                  </div>
                </div>
              ) : (
                <div className="flex items-center justify-between">
                  <span className="font-medium text-yeikar-secondary">
                    {s.empleado_nombre}
                    {s.cargo_nombre && <span className="ml-2 text-xs text-yeikar-neutral/40">{s.cargo_nombre}</span>}
                  </span>
                  <div className="flex items-center gap-3">
                    <span className="font-mono font-bold text-amber-700">{fmtCOP(Number(s.saldo_aguinaldo))}</span>
                    {Number(s.saldo_aguinaldo) > 0 && (
                      <Button size="sm" variant="outline" onClick={() => { setEntregandoId(s.empleado_id); setCuentaAguinaldo(null); }}>
                        Entregar
                      </Button>
                    )}
                  </div>
                </div>
              )}
            </div>
          ))}
        </div>
      </Modal>

      {/* ---------------- Modal: Config % aguinaldo por área ---------------- */}
      <Modal
        open={showConfig}
        onClose={() => setShowConfig(false)}
        title="Aguinaldo por área"
        subtitle="Porcentaje de cada producción que se acumula al bono del trabajador"
      >
        <div className="space-y-3">
          {areaConfig.map((cfg) => (
            <div key={cfg.id} className="flex items-center justify-between rounded-lg bg-white/70 px-3 py-2 text-sm">
              <span className="font-medium text-yeikar-secondary">{cfg.area?.nombre}</span>
              <div className="flex items-center gap-2">
                <Input
                  type="number"
                  min="0"
                  max="100"
                  step="0.5"
                  className="w-24 font-mono text-right"
                  defaultValue={cfg.porcentaje_aguinaldo}
                  onBlur={(e) => {
                    const v = Number(e.target.value);
                    if (!isNaN(v) && v !== Number(cfg.porcentaje_aguinaldo)) guardarConfig(cfg, v);
                  }}
                />
                <span className="text-xs text-yeikar-neutral/40">%</span>
              </div>
            </div>
          ))}
        </div>
      </Modal>

      <ConfirmDialog
        open={confirmAnular}
        title="Anular nómina"
        message="Se revierten los egresos, los movimientos de caja y el aguinaldo acumulado. ¿Continuar?"
        confirmLabel="Anular"
        onConfirm={anular}
        onCancel={() => setConfirmAnular(false)}
      />
    </div>
  );
}
