import { useState, useEffect, useCallback } from 'react';
import {
  reportesService,
  ResumenDiario,
  MovimientoDiario,
  SaldoCuentaDiaria,
} from '../services/reportesService';
import {
  Button, Card, Badge, Spinner, EmptyState, StatCard, PageHeader, Input,
  ResponsiveDataTable, type DataColumn,
} from '../components/ui';
import { nombreMoneda, fmtMoneda } from '../utils/format';

const fmtCOP = (n: number) => `$ ${(Number(n) || 0).toLocaleString('es-CO')}`;

const TIPO_TONE: Record<string, 'green' | 'red' | 'blue' | 'neutral'> = {
  ENTRADA: 'green',
  APERTURA: 'blue',
  SALIDA: 'red',
  EGRESO: 'red',
  AJUSTE: 'neutral',
};

export default function EstadoDia() {
  const [fecha, setFecha] = useState(() => new Date().toISOString().split('T')[0]);
  const [data, setData] = useState<ResumenDiario | null>(null);
  const [loading, setLoading] = useState(false);

  const cargar = useCallback(async () => {
    setLoading(true);
    try {
      const res = await reportesService.getResumenDiario(fecha);
      setData(res);
    } finally {
      setLoading(false);
    }
  }, [fecha]);

  useEffect(() => {
    cargar();
  }, [cargar]);

  const neto = (data?.total_ingresos_cop || 0) - (data?.total_egresos_cop || 0);

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
      render: (s) => <span className="font-mono">{fmtCOP(s.saldo_inicial_cop)}</span>,
      mobileLabel: 'Inicio',
      align: 'right',
    },
    {
      key: 'final',
      header: 'Final',
      render: (s) => <span className="font-mono font-bold">{fmtCOP(s.saldo_final_cop)}</span>,
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
      render: (m) => (
        <span className="font-medium text-yeikar-secondary">
          {m.concepto}
          {m.referencia && <span className="ml-1 text-xs text-yeikar-neutral/40">{m.referencia}</span>}
        </span>
      ),
      mobilePrimary: true,
    },
    {
      key: 'cuenta',
      header: 'Cuenta',
      render: (m) => <span className="text-yeikar-neutral/60">{m.cuenta_nombre || '-'}</span>,
      mobileLabel: 'Cuenta',
    },
    {
      key: 'moneda',
      header: 'Moneda',
      render: (m) => (
        <span className="font-mono">
          {m.moneda_simbolo} {Number(m.monto).toLocaleString()}
          <span className="ml-1 text-xs text-yeikar-neutral/40">{nombreMoneda(m.moneda_codigo)}</span>
        </span>
      ),
      mobileLabel: 'Moneda',
      align: 'right',
    },
    {
      key: 'cop',
      header: 'COP',
      render: (m) => <span className="font-mono font-bold">{fmtCOP(m.monto_cop)}</span>,
      mobileLabel: 'COP',
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
        subtitle="Ingresos y egresos del día, quién los hizo y saldo de caja"
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

      {!data ? (
        loading ? (
          <div className="p-10"><Spinner /></div>
        ) : (
          <EmptyState title="Sin datos" description="No hay movimientos para esta fecha." />
        )
      ) : (
        <>
          <div className="grid grid-cols-1 sm:grid-cols-2 lg:grid-cols-4 gap-5">
            <StatCard label="Saldo inicial (COP)" value={fmtCOP(data.saldo_inicial_cop)} accent="from-yeikar-neutral to-yeikar-neutral-light" />
            <StatCard label="Ingresos del día" value={fmtCOP(data.total_ingresos_cop)} accent="from-green-600 to-green-500" iconBg="bg-green-50" iconText="text-green-700" />
            <StatCard label="Egresos del día" value={fmtCOP(data.total_egresos_cop)} accent="from-red-500 to-red-400" iconBg="bg-red-50" iconText="text-red-600" />
            <StatCard label="Saldo final (COP)" value={fmtCOP(data.saldo_final_cop)} accent={neto >= 0 ? 'from-yeikar-primary to-yeikar-primary-light' : 'from-red-600 to-red-500'} />
          </div>

          <div className="grid grid-cols-1 lg:grid-cols-3 gap-5">
            <Card className="p-5 lg:col-span-1">
              <h3 className="font-headline font-black text-yeikar-secondary text-sm uppercase tracking-wider mb-3">
                Por moneda
              </h3>
              {data.por_moneda.length === 0 ? (
                <p className="text-sm text-yeikar-neutral/40">Sin movimientos.</p>
              ) : (
                <div className="space-y-2">
                  {data.por_moneda.map((m) => (
                    <div key={m.moneda_id} className="flex items-center justify-between rounded-lg bg-yeikar-tertiary/40 px-3 py-2 text-sm">
                      <span className="font-bold text-yeikar-secondary">{nombreMoneda(m.codigo)}</span>
                      <div className="text-right font-mono text-xs">
                        <p className="text-green-700">+ {m.monto_ingresos.toLocaleString()} {nombreMoneda(m.codigo)}</p>
                        <p className="text-red-600">− {m.monto_egresos.toLocaleString()} {nombreMoneda(m.codigo)}</p>
                        <p className="text-yeikar-neutral/50">≈ {fmtMoneda(m.monto_cop, 'COP')}</p>
                      </div>
                    </div>
                  ))}
                </div>
              )}
            </Card>

            <Card className="p-5 lg:col-span-2">
              <h3 className="font-headline font-black text-yeikar-secondary text-sm uppercase tracking-wider mb-3">
                Saldos por cuenta
              </h3>
              {data.saldos_por_cuenta.length === 0 ? (
                <p className="text-sm text-yeikar-neutral/40">Sin cuentas con movimiento.</p>
              ) : (
                <ResponsiveDataTable
                  columns={saldoColumns}
                  rows={data.saldos_por_cuenta}
                  rowKey={(s) => s.metodo_caja_id}
                />
              )}
            </Card>
          </div>

          <Card>
            <ResponsiveDataTable
              columns={movimientoColumns}
              rows={data.movimientos}
              rowKey={(m) => m.id}
              cardBadge={(m) => <Badge tone={TIPO_TONE[m.tipo] || 'neutral'}>{m.tipo}</Badge>}
              empty={
                <div className="p-8">
                  <EmptyState compact title="Sin movimientos" description="No hubo ingresos ni egresos este día." />
                </div>
              }
            />
          </Card>
        </>
      )}
    </div>
  );
}
