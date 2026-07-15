import { useEffect, useState } from 'react';
import { authApi } from '../services/api';
import api from '../services/api';

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

export default function Dashboard() {
  const [user, setUser] = useState<any>(null);
  const [metrics, setMetrics] = useState<DashboardMetrics | null>(null);
  const [recentOrders, setRecentOrders] = useState<RecentOrder[]>([]);
  const [stockAlerts, setStockAlerts] = useState<StockAlerta[]>([]);
  const [delayedOrdersCount, setDelayedOrdersCount] = useState(0);

  const today = new Date().toLocaleDateString('es-ES', {
    weekday: 'long', year: 'numeric', month: 'long', day: 'numeric'
  });

  useEffect(() => {
    authApi.get('/me').then(r => setUser(r.data)).catch(() => {});
    api.get<DashboardMetrics>('/dashboard/metrics').then(r => setMetrics(r.data)).catch(() => {});
    
    // Recent orders (last 5)
    api.get<RecentOrder[]>('/pedido/', { params: { limite: 5 } })
      .then(r => setRecentOrders(r.data))
      .catch(() => {});

    // Stock alerts
    api.get<StockAlerta[]>('/inventario/alertas', { params: { umbral: 5.0 } })
      .then(r => setStockAlerts(r.data))
      .catch(() => {});

    // Delayed orders count
    api.get<RecentOrder[]>('/pedido/')
      .then(r => {
        const todayStr = new Date().toISOString().split('T')[0];
        const delayed = r.data.filter(p => 
          (p.estado === 'PENDIENTE' || p.estado === 'EN_PROCESO') && 
          p.fecha_entrega_estimada && 
          p.fecha_entrega_estimada < todayStr
        );
        setDelayedOrdersCount(delayed.length);
      })
      .catch(() => {});
  }, []);

  const roles = user?.roles?.map((r: any) => r.nombre) || [];
  const isAdmin = roles.includes('Dueño') || roles.includes('Administrador');

  const cards = [
    {
      label: 'Pedidos Activos',
      value: metrics?.pedidos_activos ?? 0,
      icon: (
        <svg className="w-6 h-6" fill="none" stroke="currentColor" viewBox="0 0 24 24">
          <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M16 11V7a4 4 0 00-8 0v4M5 9h14l1 12H4L5 9z" />
        </svg>
      ),
      color: 'from-amber-500 to-yellow-400',
      bg: 'bg-amber-50',
      border: 'border-amber-200',
      text: 'text-amber-700',
    },
    {
      label: 'En Producción',
      value: metrics?.ordenes_produccion_activas ?? 0,
      icon: (
        <svg className="w-6 h-6" fill="none" stroke="currentColor" viewBox="0 0 24 24">
          <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M9 5H7a2 2 0 00-2 2v12a2 2 0 002 2h10a2 2 0 002-2V7a2 2 0 00-2-2h-2M9 5a2 2 0 002 2h2a2 2 0 002-2M9 5a2 2 0 012-2h2a2 2 0 012 2" />
        </svg>
      ),
      color: 'from-blue-500 to-cyan-400',
      bg: 'bg-blue-50',
      border: 'border-blue-200',
      text: 'text-blue-700',
    },
    {
      label: 'Alertas de Stock',
      value: metrics?.alertas_stock ?? 0,
      icon: (
        <svg className="w-6 h-6" fill="none" stroke="currentColor" viewBox="0 0 24 24">
          <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M12 9v2m0 4h.01m-6.938 4h13.856c1.54 0 2.502-1.667 1.732-3L13.732 4c-.77-1.333-2.694-1.333-3.464 0L3.34 16c-.77 1.333.192 3 1.732 3z" />
        </svg>
      ),
      color: 'from-red-500 to-orange-400',
      bg: 'bg-red-50',
      border: 'border-red-200',
      text: 'text-red-700',
    },
    {
      label: 'Ingresos del Mes',
      value: metrics?.ingresos_mes
        ? metrics.ingresos_mes
            .map((i) => `${i.moneda} ${i.monto.toLocaleString('es-ES')}`)
            .join(' | ') || '$0'
        : '$0',
      icon: (
        <svg className="w-6 h-6" fill="none" stroke="currentColor" viewBox="0 0 24 24">
          <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M12 8c-1.657 0-3 .895-3 2s1.343 2 3 2 3 .895 3 2-1.343 2-3 2m0-8c1.11 0 2.08.402 2.599 1M12 8V7m0 1v8m0 0v1m0-1c-1.11 0-2.08-.402-2.599-1M21 12a9 9 0 11-18 0 9 9 0 0118 0z" />
        </svg>
      ),
      color: 'from-green-500 to-emerald-400',
      bg: 'bg-green-50',
      border: 'border-green-200',
      text: 'text-green-700',
    },
  ];

  const visibleCards = cards.filter(card => {
    if (isAdmin || roles.length === 0) return true;
    if (roles.includes('Fletes')) {
      return card.label === 'Pedidos Activos';
    }
    if (roles.includes('Producción')) {
      return card.label === 'En Producción';
    }
    if (roles.includes('Inventario')) {
      return card.label === 'Alertas de Stock';
    }
    return card.label === 'Pedidos Activos' || card.label === 'Ingresos del Mes';
  });

  const allQuickLinks = [
    { label: 'Nueva Cotización', href: '/cotizaciones', color: 'bg-yeikar-primary hover:bg-yeikar-primary-dark text-yeikar-neutral', roles: ['Dueño', 'Administrador', 'Ventas'] },
    { label: 'Producción', href: '/produccion', color: 'bg-yeikar-secondary hover:bg-yeikar-secondary-light text-yeikar-tertiary', roles: ['Dueño', 'Administrador', 'Producción'] },
    { label: 'Ver Inventario', href: '/inventario', color: 'bg-yeikar-secondary hover:bg-yeikar-secondary-light text-yeikar-tertiary', roles: ['Dueño', 'Administrador', 'Inventario'] },
    { label: 'Ver Reportes', href: '/reportes', color: 'bg-yeikar-secondary hover:bg-yeikar-secondary-light text-yeikar-tertiary', roles: ['Dueño', 'Administrador'] },
    { label: 'Ver Envíos', href: '/envios', color: 'bg-yeikar-secondary hover:bg-yeikar-secondary-light text-yeikar-tertiary', roles: ['Dueño', 'Administrador', 'Fletes'] },
    { label: 'Ver Pedidos', href: '/pedidos', color: 'bg-yeikar-secondary hover:bg-yeikar-secondary-light text-yeikar-tertiary', roles: ['Dueño', 'Administrador', 'Fletes'] },
  ];

  const quickLinks = allQuickLinks.filter(link => {
    if (isAdmin || roles.length === 0) return link.roles.includes('Dueño') || link.roles.includes('Administrador');
    return link.roles.some(r => roles.includes(r));
  });

  return (
    <div className="space-y-8">
      {/* Header */}
      <div className="flex items-start justify-between">
        <div>
          <p className="text-sm text-yeikar-neutral/50 font-mono uppercase tracking-widest mb-1">{today}</p>
          <h1 className="text-3xl font-black font-headline text-yeikar-neutral tracking-tight">
            Panel de Control
          </h1>
          {user && (
            <p className="text-yeikar-neutral/60 mt-1">
              Bienvenido de nuevo, <span className="font-bold text-yeikar-secondary">{user.nombre_usuario}</span> 
            </p>
          )}
        </div>
        <div className="hidden md:flex items-center gap-2 bg-white border border-yeikar-secondary/10 rounded-xl px-4 py-2 shadow-sm">
          <span className="w-2 h-2 rounded-full bg-green-400 animate-pulse"></span>
          <span className="text-sm text-yeikar-neutral/60 font-mono">Sistema Activo</span>
        </div>
      </div>

      {/* KPI Cards */}
      <div className="grid grid-cols-1 sm:grid-cols-2 lg:grid-cols-4 gap-5">
        {visibleCards.map((card) => (
          <div
            key={card.label}
            className={`relative bg-white border ${card.border} rounded-2xl p-5 shadow-sm hover:shadow-md transition-shadow duration-200 overflow-hidden`}
          >
            <div className={`absolute top-0 left-0 right-0 h-1 bg-gradient-to-r ${card.color} rounded-t-2xl`} />
            <div className="flex items-start justify-between">
              <div>
                <p className="text-xs font-mono uppercase tracking-widest text-yeikar-neutral/50 mb-2">{card.label}</p>
                <p className={`text-2xl font-black font-headline ${card.text} leading-none`}>
                  {card.value}
                </p>
              </div>
              <div className={`${card.bg} ${card.text} p-2.5 rounded-xl`}>
                {card.icon}
              </div>
            </div>
          </div>
        ))}
      </div>

      {/* Main Grid: Recent Orders & Alerts */}
      <div className="grid grid-cols-1 lg:grid-cols-3 gap-6">
        
        {/* Recent Orders (2/3 width on large screens) */}
        <div className="lg:col-span-2 bg-white border border-yeikar-secondary-light/10 rounded-3xl p-6 shadow-sm space-y-4">
          <h2 className="text-lg font-black font-headline text-yeikar-secondary tracking-tight">
            Pedidos Recientes
          </h2>
          <div className="overflow-x-auto">
            <table className="w-full text-left border-collapse">
              <thead>
                <tr className="bg-yeikar-tertiary/20 text-yeikar-secondary font-headline font-bold text-xs uppercase tracking-wider">
                  <th className="p-3 border-b border-yeikar-secondary-light/5">Pedido</th>
                  <th className="p-3 border-b border-yeikar-secondary-light/5">Cliente</th>
                  <th className="p-3 border-b border-yeikar-secondary-light/5">Fecha</th>
                  <th className="p-3 border-b border-yeikar-secondary-light/5">Estado</th>
                </tr>
              </thead>
              <tbody className="divide-y divide-yeikar-secondary-light/5 text-sm">
                {recentOrders.length === 0 ? (
                  <tr>
                    <td colSpan={4} className="p-4 text-center text-yeikar-neutral/40 italic">
                      No hay pedidos registrados.
                    </td>
                  </tr>
                ) : (
                  recentOrders.map((order) => (
                    <tr key={order.id} className="hover:bg-yeikar-tertiary/10 transition-colors">
                      <td className="p-3 font-mono font-bold text-yeikar-secondary">
                        #{order.id}
                      </td>
                      <td className="p-3 text-yeikar-neutral/80">
                        {order.cliente?.nombre || '—'}
                      </td>
                      <td className="p-3 font-mono text-xs text-yeikar-neutral/50">
                        {new Date(order.fecha).toLocaleDateString('es-ES')}
                      </td>
                      <td className="p-3">
                        <span className={`px-2 py-0.5 rounded-full text-xs font-bold ${
                          order.estado === 'Entregado' || order.estado === 'Terminado'
                            ? 'bg-green-50 text-green-700'
                            : order.estado === 'En producción'
                            ? 'bg-blue-50 text-blue-700'
                            : 'bg-amber-50 text-amber-700'
                        }`}>
                          {order.estado}
                        </span>
                      </td>
                    </tr>
                  ))
                )}
              </tbody>
            </table>
          </div>
        </div>

        {/* Alerts Panel (1/3 width) */}
        <div className="bg-white border border-yeikar-secondary-light/10 rounded-3xl p-6 shadow-sm space-y-4">
          <h2 className="text-lg font-black font-headline text-yeikar-secondary tracking-tight">
            Panel de Alertas
          </h2>
          
          <div className="space-y-3">
            {/* Stock Alerts */}
            {stockAlerts.length > 0 && (isAdmin || roles.includes('Inventario') || roles.length === 0) && (
              <div className="bg-red-50 border border-red-200 rounded-2xl p-4 flex gap-3 text-xs">
                <svg className="w-5 h-5 text-red-600 flex-shrink-0" fill="none" stroke="currentColor" viewBox="0 0 24 24">
                  <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M12 9v2m0 4h.01m-6.938 4h13.856c1.54 0 2.502-1.667 1.732-3L13.732 4c-.77-1.333-2.694-1.333-3.464 0L3.34 16c-.77 1.333.192 3 1.732 3z" />
                </svg>
                <div>
                  <h4 className="font-bold text-red-800">Materiales Críticos</h4>
                  <p className="text-red-700 mt-0.5">
                    Hay {stockAlerts.length} materiales por debajo del stock mínimo.
                  </p>
                  <a href="/inventario" className="text-red-800 font-bold underline mt-1 block">
                    Ver Inventario
                  </a>
                </div>
              </div>
            )}

            {/* Delayed Orders Alerts */}
            {delayedOrdersCount > 0 && (isAdmin || roles.includes('Fletes') || roles.includes('Ventas') || roles.length === 0) && (
              <div className="bg-amber-50 border border-amber-200 rounded-2xl p-4 flex gap-3 text-xs">
                <svg className="w-5 h-5 text-amber-600 flex-shrink-0" fill="none" stroke="currentColor" viewBox="0 0 24 24">
                  <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M12 8v4l3 3m6-3a9 9 0 11-18 0 9 9 0 0118 0z" />
                </svg>
                <div>
                  <h4 className="font-bold text-amber-800">Pedidos Retrasados</h4>
                  <p className="text-amber-700 mt-0.5">
                    Hay {delayedOrdersCount} pedidos pendientes con fecha de entrega vencida.
                  </p>
                  <a href="/pedidos" className="text-amber-800 font-bold underline mt-1 block">
                    Ver Pedidos
                  </a>
                </div>
              </div>
            )}

            {/* If no alerts */}
            {((stockAlerts.length === 0 || !(isAdmin || roles.includes('Inventario') || roles.length === 0)) &&
              (delayedOrdersCount === 0 || !(isAdmin || roles.includes('Fletes') || roles.includes('Ventas') || roles.length === 0))) && (
              <div className="bg-green-50 border border-green-200 rounded-2xl p-4 flex gap-3 text-xs">
                <svg className="w-5 h-5 text-green-600 flex-shrink-0" fill="none" stroke="currentColor" viewBox="0 0 24 24">
                  <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M9 12l2 2 4-4m6 2a9 9 0 11-18 0 9 9 0 0118 0z" />
                </svg>
                <div>
                  <h4 className="font-bold text-green-800">Todo al día</h4>
                  <p className="text-green-700 mt-0.5">
                    No se detectan alertas críticas en el sistema.
                  </p>
                </div>
              </div>
            )}
          </div>
        </div>

      </div>

      {/* Quick Actions */}
      <div className="bg-white border border-yeikar-secondary/10 rounded-2xl p-6 shadow-sm">
        <h2 className="text-lg font-black font-headline text-yeikar-neutral mb-4 tracking-tight">
          Acciones Rápidas
        </h2>
        <div className="flex flex-wrap gap-3">
          {quickLinks.map((link) => (
            <a
              key={link.label}
              href={link.href}
              className={`${link.color} px-5 py-2.5 rounded-xl text-sm font-bold font-headline transition-all duration-200 hover:scale-105 shadow-sm`}
            >
              {link.label}
            </a>
          ))}
        </div>
      </div>

      {/* Status bar */}
      <div className="bg-yeikar-secondary rounded-2xl p-6 text-yeikar-tertiary">
        <div className="flex flex-wrap items-center justify-between gap-4">
          <div>
            <h2 className="text-lg font-black font-headline text-yeikar-primary tracking-tight">YEIKAR ERP</h2>
            <p className="text-sm text-yeikar-tertiary/60 font-mono">Sistema de Gestión Empresarial v1.0</p>
          </div>
          <div className="flex items-center gap-4 text-sm font-mono text-yeikar-tertiary/60">
            <span>Backend: <span className="text-green-400">●  Online</span></span>
            <span>Base de Datos: <span className="text-green-400">●  Online</span></span>
          </div>
        </div>
      </div>
    </div>
  );
}
