import { useState, useEffect, useCallback } from 'react';
import {
  reportesService,
  ResumenDiario,
  MovimientoDiario,
  SaldoCuentaDiaria,
  MonedaVistaDiaria,
} from '../services/reportesService';
import {
  Button, Card, Badge, Spinner, EmptyState, StatCard, PageHeader, Input,
  ResponsiveDataTable, type DataColumn,
} from '../components/ui';
import { nombreMoneda, fmtMoneda, formatCurrency } from '../utils/format';

const TIPO_TONE: Record<string, 'green' | 'red' | 'blue' | 'neutral'> = {
  ENTRADA: 'green',
  APERTURA: 'blue',
  SALIDA: 'red',
  EGRESO: 'red',
  AJUSTE: 'neutral',
};

const TAB_COP: MonedaVistaDiaria = {
  moneda_id: 1, codigo: 'COP', simbolo: '$',
};

export default function EstadoDia() {
  const [fecha, setFecha] = useState(() => new Date().toISOString().split('T')[0]);
  const [monedaVista, setMonedaVista] = useState('COP');
  const [data, setData] = useState<ResumenDiario | null>(null);
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState<string | null>(null);

  const cargar = useCallback(async () => {
    setLoading(true);
    setError(null);
    try {
      const res = await reportesService.getResumenDiario(fecha, monedaVista);
      setData(res);
    } catch {
      setError('No se pudo cargar el estado del día.');
    } finally {
      setLoading(false);
    }
  }, [fecha, monedaVista]);

  useEffect(() => {
    cargar();
  }, [cargar]);

  // Cada vista muestra su moneda en valor nativo, sin conversiones.
  const vista = data?.moneda_vista || monedaVista;
  const tabs = data?.monedas?.length ? data.monedas : [TAB_COP];
  const neto = (data?.total_ingresos_vista || 0) - (data?.total_egresos_vista || 0);

  const saldoColumns: DataColumn<SaldoCuentaDiaria>[] = [
    {
      key: 'cuenta',
      header: 'Cuenta',
      render: (s) => <span className="font-medium text-yeikar-secondary">{s.cuenta_nombre}</span>,
      mobilePrimary: true,
    },
    {
      key: 'inicio',
      header: 'Inicio',
      render: (s) => (
        <span className="font-mono">
          {fmtMoneda(s.saldo_inicial, s.moneda_codigo)}
          <span className="block text-[10px] font-normal text-yeikar-neutral/40">
            ≈ {formatCurrency(s.saldo_inicial_cop, 'COP')}
          </span>
        </span>
      ),
      mobileLabel: 'Inicio',
      align: 'right',
    },
    {
      key: 'final',
      header: 'Final',
      render: (s) => (
        <span className="font-mono font-bold">
          {fmtMoneda(s.saldo_final, s.moneda_codigo)}
          <span className="block text-[10px] font-normal text-yeikar-neutral/40">
            ≈ {formatCurrency(s.saldo_final_cop, 'COP')}
          </span>
        </span>
      ),
      mobileLabel: 'Final',
      align: 'right',
    },
  ];

  const movimientoColumns: DataColumn<MovimientoDiario>[] = [
    {
      key: 'tipo',
      header: 'Tipo',
      render: (m) => <Badge tone={TIPO_TONE[m.tipo] || 'neutral'}>{m.tipo}</Badge>,
      mobileHidden: true,
    },
    {
      key: 'concepto',
      header: 'Concepto',
      // La referencia va como chip solo si el concepto no la contiene ya.
      render: (m) => (
        <span className="font-medium text-yeikar-secondary">
          {m.concepto}
          {m.referencia && !m.concepto.includes(m.referencia) && (
            <span className="ml-1 text-xs font-normal text-yeikar-neutral/40">{m.referencia}</span>
          )}
        </span>
      ),
      mobilePrimary: true,
    },
    {
      key: 'cuenta',
      header: 'Cuenta',
      // Los EGRESO sin caja (fiado, consumo de producción) nunca tocaron
      // una cuenta: se dice explícito en vez de un "-" ambiguo.
      render: (m) => (
        <span className="text-yeikar-neutral/60">
          {m.cuenta_nombre || (m.tipo === 'EGRESO' ? <span className="italic">Sin caja</span> : '-')}
        </span>
      ),
      mobileLabel: 'Cuenta',
    },
    {
      key: 'moneda',
      header: `Monto (${vista})`,
      render: (m) => (
        <span className="font-mono">
          {fmtMoneda(m.monto, m.moneda_codigo)}
          <span className="block text-[10px] font-normal text-yeikar-neutral/40">
            ≈ {formatCurrency(m.monto_cop, 'COP')}
          </span>
        </span>
      ),
      mobileLabel: 'Monto',
      align: 'right',
    },
    {
      key: 'quien',
      header: 'Quién',
      render: (m) => <span className="text-yeikar-neutral/70">{m.quien || '-'}</span>,
      mobileSecondary: true,
    },
  ];

  return (
    <div className="space-y-6">
      <PageHeader
        eyebrow="Reportes"
        title="Estado del día"
        subtitle={`Ingresos y egresos del día, quién los hizo y saldo de caja · vista en ${nombreMoneda(vista)}`}
        actions={
          <div className="flex items-center gap-2">
            <Input
              type="date"
              value={fecha}
              onChange={(e) => setFecha(e.target.value)}
              className="w-auto"
            />
            <Button variant="outline" onClick={cargar} disabled={loading}>
              {loading ? 'Cargando...' : 'Actualizar'}
            </Button>
          </div>
        }
      />

      {/* Tabs de moneda: cada vista muestra su moneda en valor nativo */}
      {data && tabs.length > 0 && (
        <div className="flex flex-wrap items-center gap-3">
          <div className="flex flex-wrap items-center gap-1 rounded-xl border border-yeikar-secondary/10 bg-white p-1 shadow-sm">
            {tabs.map((t) => {
              const activa = t.codigo === vista;
              return (
                <button
                  key={t.codigo}
                  type="button"
                  onClick={() => setMonedaVista(t.codigo)}
                  className={`rounded-lg px-4 py-1.5 text-sm font-mono transition ${
                    activa
                      ? 'bg-yeikar-secondary font-bold text-white shadow'
                      : 'text-yeikar-neutral/60 hover:bg-yeikar-tertiary/60 hover:text-yeikar-secondary'
                  }`}
                >
                  {t.simbolo} {t.codigo}
                </button>
              );
            })}
          </div>
          <p className="text-xs text-yeikar-neutral/50">
            {data.movimientos.length} movimientos · {data.saldos_por_cuenta.length} saldos en {nombreMoneda(vista)} · sin conversiones
          </p>
        </div>
      )}

      {error && (
        <Card className="border-red-200 bg-red-50 p-4 text-sm text-red-700">{error}</Card>
      )}

      {!data ? (
        loading ? (
          <div className="p-10"><Spinner /></div>
        ) : (
          !error && <EmptyState title="Sin datos" description="No hay movimientos para esta fecha." />
        )
      ) : (
        <>
          <div className="grid grid-cols-1 sm:grid-cols-2 lg:grid-cols-4 gap-5">
            <StatCard label={`Saldo inicial (${vista})`} value={formatCurrency(data.saldo_inicial_vista, vista)} accent="from-yeikar-neutral to-yeikar-neutral-light" />
            <StatCard label={`Ingresos del día (${vista})`} value={formatCurrency(data.total_ingresos_vista, vista)} accent="from-green-600 to-green-500" iconBg="bg-green-50" iconText="text-green-700" />
            <StatCard label={`Egresos del día (${vista})`} value={formatCurrency(data.total_egresos_vista, vista)} accent="from-red-500 to-red-400" iconBg="bg-red-50" iconText="text-red-600" />
            <StatCard label={`Saldo final (${vista})`} value={formatCurrency(data.saldo_final_vista, vista)} accent={neto >= 0 ? 'from-yeikar-primary to-yeikar-primary-light' : 'from-red-600 to-red-500'} />
          </div>

          <div className="grid grid-cols-1 lg:grid-cols-3 gap-5">
            <Card className="p-5 lg:col-span-1">
              <h3 className="font-headline font-black text-yeikar-secondary text-sm uppercase tracking-wider mb-1">
                Flujo por moneda
              </h3>
              <p className="text-[11px] text-yeikar-neutral/40 mb-3">Todas las monedas, en su valor nativo</p>
              {data.por_moneda.length === 0 ? (
                <p className="text-sm text-yeikar-neutral/40">Sin movimientos.</p>
              ) : (
                <div className="space-y-2">
                  {data.por_moneda.map((m) => {
                    const netoMoneda = Number(m.monto_ingresos) - Number(m.monto_egresos);
                    const esVista = m.codigo === vista;
                    return (
                      <button
                        key={m.moneda_id}
                        type="button"
                        onClick={() => setMonedaVista(m.codigo)}
                        title={`Ver vista en ${nombreMoneda(m.codigo)}`}
                        className={`w-full rounded-lg px-3 py-2 text-sm text-left transition ${
                          esVista
                            ? 'bg-yeikar-secondary/10 ring-1 ring-yeikar-secondary/30'
                            : 'bg-yeikar-tertiary/40 hover:bg-yeikar-tertiary/70'
                        }`}
                      >
                        <div className="flex items-center justify-between">
                          <span className="font-bold text-yeikar-secondary">{nombreMoneda(m.codigo)}</span>
                          <Badge tone={esVista ? 'blue' : 'neutral'}>{m.simbolo} {m.codigo}</Badge>
                        </div>
                        <div className="mt-1 text-right font-mono text-xs">
                          <p className="text-green-700">+ {fmtMoneda(m.monto_ingresos, m.codigo)}</p>
                          <p className="text-red-600">− {fmtMoneda(m.monto_egresos, m.codigo)}</p>
                          <p className={`font-bold ${netoMoneda >= 0 ? 'text-yeikar-secondary' : 'text-red-600'}`}>
                            = {fmtMoneda(netoMoneda, m.codigo)}
                          </p>
                        </div>
                      </button>
                    );
                  })}
                </div>
              )}
            </Card>

            <Card className="p-5 lg:col-span-2">
              <h3 className="font-headline font-black text-yeikar-secondary text-sm uppercase tracking-wider mb-1">
                Saldos por cuenta en {nombreMoneda(vista)} ({data.saldos_por_cuenta.length})
              </h3>
              <p className="text-[11px] text-yeikar-neutral/40 mb-3">Valor nativo · ≈ referencia en COP</p>
              {data.saldos_por_cuenta.length === 0 ? (
                <p className="text-sm text-yeikar-neutral/40">Sin saldos en {nombreMoneda(vista)} este día.</p>
              ) : (
                <ResponsiveDataTable
                  columns={saldoColumns}
                  rows={data.saldos_por_cuenta}
                  rowKey={(s) => `${s.metodo_caja_id}-${s.moneda_codigo}`}
                />
              )}
            </Card>
          </div>

          <Card>
            <div className="flex items-center justify-between px-5 pt-4">
              <h3 className="font-headline font-black text-yeikar-secondary text-sm uppercase tracking-wider">
                Movimientos del día en {nombreMoneda(vista)} ({data.movimientos.length})
              </h3>
            </div>
            <ResponsiveDataTable
              columns={movimientoColumns}
              rows={data.movimientos}
              rowKey={(m) => `${m.tipo}-${m.id}`}
              cardBadge={(m) => <Badge tone={TIPO_TONE[m.tipo] || 'neutral'}>{m.tipo}</Badge>}
              empty={
                <div className="p-8">
                  <EmptyState compact title="Sin movimientos" description={`No hubo ingresos ni egresos en ${nombreMoneda(vista)} este día.`} />
                </div>
              }
            />
          </Card>
        </>
      )}
    </div>
  );
}
