import { useEffect, useState } from 'react';
import { Link } from 'react-router-dom';
import api from '../services/api';
import { useAuth } from '../context/AuthContext';
import {
  ShoppingBag,
  Hammer,
  AlertTriangle,
  DollarSign,
  TrendingUp,
  Sparkles,
  Clock,
  ArrowUpRight,
  CheckCircle2,
  Package,
  Layers,
  BarChart3,
  Users,
} from 'lucide-react';
import { Card, StatCard, Badge, Button } from '../components/ui';

interface IngresoMesDetail {
  moneda: string;
  monto: number;
}

interface DashboardMetrics {
  pedidos_activos: number;
  ordenes_produccion_activas: number;
  alertas_stock: number;
  ingresos_mes: IngresoMesDetail[];
}

interface RecentOrder {
  id: number;
  cliente?: {
    nombre: string;
  };
  fecha: string;
  estado: string;
  fecha_entrega_estimada?: string;
}

interface StockAlerta {
  material_id: number;
  material_nombre: string;
  stock_actual: number;
  stock_minimo: number;
  ubicacion_nombre: string;
}

const orderStatusLabels: Record<string, string> = {
  COTIZADO: 'Cotizado',
  PRODUCCION: 'En producción',
  EN_PRODUCCION: 'En producción',
  TERMINADO: 'Terminado',
  ENTREGADO: 'Entregado',
};

export default function Dashboard() {
  const { user, hasModulo } = useAuth();
  const [metrics, setMetrics] = useState<DashboardMetrics | null>(null);
  const [recentOrders, setRecentOrders] = useState<RecentOrder[]>([]);
  const [stockAlerts, setStockAlerts] = useState<StockAlerta[]>([]);
  const [delayedOrdersCount, setDelayedOrdersCount] = useState(0);

  const today = new Date().toLocaleDateString('es-ES', {
    weekday: 'long',
    year: 'numeric',
    month: 'long',
    day: 'numeric',
  });

  const puedePedidos = hasModulo('pedidos');
  const puedeInventario = hasModulo('inventario');
  const esAdmin = hasModulo('usuarios');

  useEffect(() => {
    api.get<DashboardMetrics>('/dashboard/metrics').then((r) => setMetrics(r.data)).catch(() => {});

    if (puedePedidos) {
      api.get<RecentOrder[]>('/pedido/', { params: { limite: 5 } })
        .then((r) => setRecentOrders(r.data))
        .catch(() => {});

      api.get<RecentOrder[]>('/pedido/')
        .then((r) => {
          const todayStr = new Date().toISOString().split('T')[0];
          const delayed = r.data.filter(
            (p) =>
              (p.estado === 'COTIZADO' || p.estado === 'PRODUCCION') &&
              p.fecha_entrega_estimada &&
              p.fecha_entrega_estimada < todayStr
          );
          setDelayedOrdersCount(delayed.length);
        })
        .catch(() => {});
    }

    if (puedeInventario) {
      api.get<StockAlerta[]>('/inventario/alertas', { params: { umbral: 5.0 } })
        .then((r) => setStockAlerts(r.data))
        .catch(() => {});
    }
  }, [puedePedidos, puedeInventario]);

  const cards = [
    {
      label: 'Pedidos Activos',
      value: metrics?.pedidos_activos ?? 0,
       icon: <ShoppingBag className="w-5 h-5 text-yeikar-primary-dark" />,
       accent: 'from-yeikar-primary to-yeikar-primary-light',
       iconBg: 'bg-yeikar-primary/10 border border-yeikar-primary/20',
       iconText: 'text-yeikar-primary-dark',
      hint: 'Pedidos en curso',
      module: 'pedidos',
    },
    {
      label: 'En Producción',
      value: metrics?.ordenes_produccion_activas ?? 0,
       icon: <Hammer className="w-5 h-5 text-yeikar-secondary" />,
       accent: 'from-yeikar-secondary to-yeikar-secondary-light',
       iconBg: 'bg-yeikar-secondary/10 border border-yeikar-secondary/15',
       iconText: 'text-yeikar-secondary',
      hint: 'Órdenes en taller',
      module: 'produccion',
    },
    {
      label: 'Alertas de Stock',
      value: metrics?.alertas_stock ?? 0,
      icon: <AlertTriangle className="w-5 h-5 text-rose-700" />,
       accent: 'from-rose-500 to-yeikar-primary',
      iconBg: 'bg-rose-500/10 border border-rose-500/20',
      iconText: 'text-rose-700',
      hint: 'Materiales bajo mínimo',
      module: 'inventario',
    },
    {
      label: 'Ingresos del Mes',
      value: metrics?.ingresos_mes
        ? metrics.ingresos_mes
            .map((i) => `${i.moneda} $${i.monto.toLocaleString('es-ES')}`)
            .join(' | ') || '$0'
        : '$0',
      icon: <DollarSign className="w-5 h-5 text-emerald-700" />,
       accent: 'from-emerald-600 to-yeikar-primary',
      iconBg: 'bg-emerald-500/10 border border-emerald-200/60',
      iconText: 'text-emerald-700',
      hint: 'Cobros facturados',
      module: 'ventas',
    },
  ];

  const visibleCards = cards.filter((card) => {
    if (esAdmin) return true;
    return hasModulo(card.module);
  });

  const quickActions = [
    { label: 'Nueva Cotización IA', href: '/cotizaciones-ia', icon: Sparkles, primary: true, module: 'cotizaciones_ia' },
    { label: 'Nueva Cotización', href: '/cotizaciones', icon: ArrowUpRight, primary: false, module: 'cotizaciones' },
    { label: 'Taller de Producción', href: '/produccion', icon: Hammer, primary: false, module: 'produccion' },
    { label: 'Inventario', href: '/inventario', icon: Package, primary: false, module: 'inventario' },
    { label: 'Reportes Financieros', href: '/reportes', icon: BarChart3, primary: false, module: 'reportes' },
  ].filter((item) => hasModulo(item.module));

  return (
    <div className="space-y-8">
      {/* Header Banner */}
      <div className="relative flex flex-wrap items-center justify-between gap-6 overflow-hidden rounded-2xl border border-yeikar-primary/20 bg-gradient-to-br from-yeikar-neutral via-yeikar-secondary to-yeikar-neutral-dark p-7 text-white shadow-lift sm:p-9">
        <div className="pointer-events-none absolute -right-16 -top-28 h-80 w-80 rounded-full border border-yeikar-primary/15" />
        <div className="pointer-events-none absolute -right-4 -top-16 h-56 w-56 rounded-full border border-yeikar-primary/10" />
        <div className="relative z-10 space-y-1">
           <p className="eyebrow text-yeikar-primary-light">
            {today}
          </p>
           <h1 className="text-3xl font-black font-headline tracking-[-0.04em] text-white sm:text-4xl">
            Hola, <span className="text-yeikar-primary">{user?.nombre_usuario || 'Admin'}</span>
          </h1>
           <p className="max-w-xl text-sm leading-relaxed text-white/55">
            Resumen ejecutivo del ERP. Supervisa la fabricación, presupuestos y salud financiera de la mueblería.
          </p>
        </div>
        <div className="relative z-10 flex items-center gap-3">
          {hasModulo('cotizaciones_ia') && (
            <Link to="/cotizaciones-ia">
              <Button variant="primary" icon={<Sparkles className="w-4 h-4" />}>
                Cotizar con IA
              </Button>
            </Link>
          )}
        </div>
      </div>

      {/* KPI Cards Grid */}
      <div className="grid grid-cols-1 sm:grid-cols-2 lg:grid-cols-4 gap-5">
        {visibleCards.map((card) => (
          <StatCard
            key={card.label}
            label={card.label}
            value={card.value}
            icon={card.icon}
            accent={card.accent}
            iconBg={card.iconBg}
            iconText={card.iconText}
            hint={card.hint}
          />
        ))}
      </div>

      {/* Main Content Grid */}
      <div className="grid grid-cols-1 lg:grid-cols-3 gap-6">
        {/* Recent Orders Table (2/3 width) */}
        <div className="lg:col-span-2">
          <Card
            title={
              <div className="flex items-center justify-between">
                <div className="flex items-center gap-2">
                   <ShoppingBag className="w-5 h-5 text-yeikar-primary-dark" />
                  <span className="font-bold font-headline text-yeikar-neutral">
                    Pedidos Recientes
                  </span>
                </div>
                {puedePedidos && (
                  <Link
                    to="/pedidos"
                     className="flex items-center gap-1 text-xs font-bold text-yeikar-primary-dark hover:text-yeikar-secondary"
                  >
                    Ver Todos <ArrowUpRight className="w-3.5 h-3.5" />
                  </Link>
                )}
              </div>
            }
          >
            <div className="overflow-x-auto -mx-6 -mb-6">
              <table className="w-full text-left border-collapse">
                <thead>
                  <tr>
                    <th className="table-th">Código</th>
                    <th className="table-th">Cliente</th>
                    <th className="table-th">Fecha</th>
                    <th className="table-th">Estado</th>
                  </tr>
                </thead>
               <tbody className="divide-y divide-yeikar-secondary-light/10">
                  {recentOrders.length === 0 ? (
                    <tr>
                       <td colSpan={4} className="p-8 text-center text-sm italic text-yeikar-neutral/45">
                        No hay pedidos recientes en el sistema.
                      </td>
                    </tr>
                  ) : (
                    recentOrders.map((order) => (
                       <tr key={order.id} className="transition-colors hover:bg-yeikar-tertiary/55">
                        <td className="table-td font-mono font-bold text-yeikar-secondary">
                          #{order.id}
                        </td>
                        <td className="table-td font-semibold text-yeikar-neutral">
                          {order.cliente?.nombre || '—'}
                        </td>
                         <td className="table-td font-mono text-xs text-yeikar-neutral/50">
                          {new Date(order.fecha).toLocaleDateString('es-ES')}
                        </td>
                        <td className="table-td">
                          <Badge
                            tone={
                              (['ENTREGADO', 'TERMINADO'] as string[]).includes(order.estado)
                                ? 'green'
                                : (['PRODUCCION', 'EN_PRODUCCION'] as string[]).includes(order.estado)
                                ? 'blue'
                                : 'gold'
                            }
                            dot
                          >
                             {orderStatusLabels[order.estado] || order.estado}
                          </Badge>
                        </td>
                      </tr>
                    ))
                  )}
                </tbody>
              </table>
            </div>
          </Card>
        </div>

        {/* Alerts & System Notifications (1/3 width) */}
        <div className="space-y-6">
          <Card
            title={
              <div className="flex items-center gap-2">
                 <AlertTriangle className="w-5 h-5 text-yeikar-primary-dark" />
                <span className="font-bold font-headline text-yeikar-neutral">
                  Alertas del Sistema
                </span>
              </div>
            }
          >
            <div className="space-y-3">
              {/* Critical Stock Alerts */}
              {stockAlerts.length > 0 && (esAdmin || puedeInventario) && (
                <div className="p-4 bg-rose-50/80 border border-rose-200/70 rounded-xl flex items-start gap-3">
                  <AlertTriangle className="w-5 h-5 text-rose-600 shrink-0 mt-0.5" />
                  <div>
                       <h5 className="font-bold text-xs text-rose-900 font-headline">
                      Stock Crítico
                    </h5>
                    <p className="text-xs text-rose-700 mt-0.5 leading-relaxed">
                      {stockAlerts.length} materiales han alcanzado el nivel de pedido mínimo.
                    </p>
                    <Link
                      to="/inventario"
                      className="text-xs font-bold text-rose-800 underline mt-1.5 inline-block"
                    >
                      Revisar Inventario →
                    </Link>
                  </div>
                </div>
              )}

              {/* Delayed Orders Alert */}
              {delayedOrdersCount > 0 && (esAdmin || puedePedidos) && (
                <div className="p-4 bg-amber-50/80 border border-amber-200/70 rounded-xl flex items-start gap-3">
                  <Clock className="w-5 h-5 text-amber-700 shrink-0 mt-0.5" />
                  <div>
                     <h5 className="font-bold text-xs text-amber-900 font-headline">
                      Entregas Vencidas
                    </h5>
                    <p className="text-xs text-amber-800 mt-0.5 leading-relaxed">
                      Hay {delayedOrdersCount} pedidos cuya fecha estimada ha expirado.
                    </p>
                    <Link
                      to="/pedidos"
                      className="text-xs font-bold text-amber-900 underline mt-1.5 inline-block"
                    >
                      Ver Pedidos Pendientes →
                    </Link>
                  </div>
                </div>
              )}

              {/* All clear fallback */}
              {stockAlerts.length === 0 && delayedOrdersCount === 0 && (
                <div className="p-5 bg-emerald-50/70 border border-emerald-200/60 rounded-xl flex items-center gap-3">
                  <CheckCircle2 className="w-5 h-5 text-emerald-600 shrink-0" />
                  <div>
                    <h5 className="font-bold text-xs text-emerald-900 font-headline">
                      Sin Alertas Pendientes
                    </h5>
                    <p className="text-xs text-emerald-700 mt-0.5">
                      Todas las órdenes e inventarios están funcionando normalmente.
                    </p>
                  </div>
                </div>
              )}
            </div>
          </Card>
        </div>
      </div>

      {/* Quick Action Dock */}
      <Card title="Acciones Rápidas">
        <div className="flex flex-wrap gap-3">
          {quickActions.map((action) => {
            const Icon = action.icon;
            return (
              <Link key={action.label} to={action.href}>
                <Button
                  variant={action.primary ? 'primary' : 'outline'}
                  icon={<Icon className="w-4 h-4" />}
                >
                  {action.label}
                </Button>
              </Link>
            );
          })}
        </div>
      </Card>
    </div>
  );
}
