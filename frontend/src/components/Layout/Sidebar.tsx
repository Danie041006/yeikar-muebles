import { Link, useLocation, useNavigate } from 'react-router-dom';
import { useEffect } from 'react';
import { useAuth } from '../../context/AuthContext';
import {
  Activity,
  BarChart3,
  Box,
  ChevronRight,
  CreditCard,
  FileCheck2,
  FileText,
  FolderOpen,
  Hammer,
  LayoutDashboard,
  LogOut,
  Package,
  Receipt,
  ScrollText,
  ShieldCheck,
  ShoppingBag,
  Truck,
  Users,
  X,
} from 'lucide-react';

interface SidebarProps {
  mobileOpen: boolean;
  onClose: () => void;
}

interface MenuItem {
  name: string;
  path: string;
  module: string;
  icon: typeof LayoutDashboard;
  badge?: string;
  children?: { name: string; path: string }[];
}

const groups: { label: string; items: MenuItem[] }[] = [
  {
    label: 'Resumen',
    items: [
      { name: 'Panel principal', path: '/dashboard', module: 'dashboard', icon: LayoutDashboard },
    ],
  },
  {
    label: 'Operación',
    items: [
      { name: 'Clientes', path: '/clientes', module: 'clientes', icon: Users },
      { name: 'Cotizaciones', path: '/cotizaciones', module: 'cotizaciones', icon: FileText },
      { name: 'Expediente', path: '/historial', module: 'pedidos', icon: FolderOpen },
      { name: 'Pedidos', path: '/pedidos', module: 'pedidos', icon: ShoppingBag },
      { name: 'Producción', path: '/produccion', module: 'produccion', icon: Hammer, children: [
        { name: 'Producción por Pedido', path: '/produccion' },
        { name: 'Producción de Productos en Crudo', path: '/produccion-crudo' },
      ] },
      { name: 'Empleados', path: '/empleados', module: 'empleados', icon: Users },
      { name: 'Inventario', path: '/inventario', module: 'inventario', icon: Package },
      { name: 'Productos', path: '/productos', module: 'productos', icon: Box },
      { name: 'Despachos', path: '/envios', module: 'envios', icon: Truck },
    ],
  },
  {
    label: 'Finanzas',
    items: [
      { name: 'Ventas y cobros', path: '/ventas', module: 'ventas', icon: Activity },
      { name: 'Facturación', path: '/facturacion', module: 'facturacion', icon: FileCheck2 },
      { name: 'Egresos y gastos', path: '/gastos', module: 'gastos', icon: Receipt },
      { name: 'Costos de Producción', path: '/costos-produccion', module: 'costos_produccion', icon: Hammer },
      { name: 'Nómina', path: '/nomina', module: 'nomina', icon: Receipt },
      { name: 'Cuentas', path: '/cuentas', module: 'cuentas', icon: CreditCard },
      { name: 'Reportes financieros', path: '/reportes', module: 'reportes', icon: BarChart3 },
      { name: 'Estado del día', path: '/reporte-diario', module: 'reportes', icon: CreditCard },
    ],
  },
  {
    label: 'Administración',
    items: [
      { name: 'Gestión de usuarios', path: '/usuarios', module: 'usuarios', icon: Users },
      { name: 'Actividad y auditoría', path: '/auditoria', module: 'usuarios', icon: ScrollText },
    ],
  },
];

export default function Sidebar({ mobileOpen, onClose }: SidebarProps) {
  const location = useLocation();
  const navigate = useNavigate();
  const { user, hasModulo, esAdmin, logout } = useAuth();
  const roles = user?.roles?.map((role) => role.nombre) || [];
  const nombreUsuario = user?.nombre || user?.nombre_usuario || 'Usuario';
  const initials = nombreUsuario.slice(0, 2).toUpperCase();

  // Vista bifurcada por rol: la administradora administra los Despachos
  // (/envios); el chofer ve solo sus repartos (/mis-despachos).
  const esChofer = !esAdmin && !!user?.empleado_id;
  const despachoItem: MenuItem = esChofer
    ? { name: 'Mis Despachos', path: '/mis-despachos', module: 'envios', icon: Truck }
    : { name: 'Despachos', path: '/envios', module: 'envios', icon: Truck };

  const handleLogout = () => {
    logout();
    navigate('/login', { replace: true });
  };

  useEffect(() => {
    if (!mobileOpen) return;
    const onKey = (e: KeyboardEvent) => {
      if (e.key === 'Escape') onClose();
    };
    window.addEventListener('keydown', onKey);
    return () => window.removeEventListener('keydown', onKey);
  }, [mobileOpen, onClose]);

  return (
    <>
      {mobileOpen && (
        <button
          type="button"
          aria-label="Cerrar navegación"
          onClick={onClose}
          className="fixed inset-0 z-40 bg-yeikar-neutral/45 backdrop-blur-sm lg:hidden"
        />
      )}

      <aside
        className={`fixed inset-y-0 left-0 z-50 flex w-[278px] -translate-x-full flex-col border-r border-white/10 bg-yeikar-neutral text-yeikar-tertiary shadow-shell transition-transform duration-300 ease-out lg:sticky lg:top-0 lg:z-30 lg:h-screen lg:translate-x-0 ${
          mobileOpen ? 'translate-x-0' : ''
        }`}
      >
        <div className="flex items-center justify-between border-b border-white/10 px-6 py-5 pt-safe">
          <Link to="/dashboard" onClick={onClose} className="group flex items-center gap-3.5">
            <span className="flex h-10 w-10 items-center justify-center rounded-xl bg-yeikar-primary font-headline text-xl font-black text-yeikar-neutral shadow-gold transition-transform duration-200 group-hover:scale-105">
              Y
            </span>
            <span className="flex flex-col">
              <span className="font-headline text-[17px] font-black tracking-[0.22em] text-white">YEIKAR</span>
              <span className="mt-1 font-mono text-[9px] uppercase tracking-[0.18em] text-yeikar-primary/70">Atelier ERP</span>
            </span>
          </Link>
          <button
            type="button"
            onClick={onClose}
            className="rounded-lg p-2 text-white/45 transition-colors hover:bg-white/10 hover:text-white lg:hidden"
            aria-label="Cerrar menú"
          >
            <X className="h-5 w-5" />
          </button>
          <span className="hidden h-2 w-2 rounded-full bg-yeikar-primary shadow-[0_0_12px_rgba(212,175,55,0.8)] lg:block" aria-label="Sistema en línea" />
        </div>

        <nav className="flex-1 overflow-y-auto px-4 py-5" aria-label="Navegación principal">
          {groups.map((group) => {
            const items = group.items
              .map((item) => (item.path === '/envios' ? despachoItem : item))
              .filter((item) => {
                if (item.path === '/dashboard') return true;
                if (item.path === '/reportes' && !esAdmin) return false;
                return hasModulo(item.module);
              });
            if (items.length === 0) return null;

            return (
              <div key={group.label} className="mb-6 last:mb-0">
                <p className="mb-2 px-3 font-mono text-[9px] font-bold uppercase tracking-[0.2em] text-white/35">{group.label}</p>
                <div className="space-y-1">
                  {items.map((item) => {
                    const Icon = item.icon;
                    const isActive = location.pathname === item.path;
                    const hasChildren = !!item.children?.length;
                    const childActive = hasChildren
                      ? item.children!.some((c) => location.pathname === c.path)
                      : false;

                    if (hasChildren) {
                      return (
                        <div key={item.path} className="group">
                          <div
                            aria-current={childActive ? 'page' : undefined}
                            className={`flex min-h-10 cursor-default items-center justify-between rounded-xl px-3.5 text-[13px] font-medium transition-all duration-200 ${
                              childActive
                                ? 'bg-yeikar-primary font-bold text-yeikar-neutral shadow-gold'
                                : 'text-white/60 hover:bg-white/[0.06] hover:text-white'
                            }`}
                          >
                            <span className="flex items-center gap-3">
                              <Icon className={`h-[17px] w-[17px] transition-colors ${childActive ? 'text-yeikar-neutral' : 'text-white/40 group-hover:text-yeikar-primary'}`} strokeWidth={1.8} />
                              <span>{item.name}</span>
                            </span>
                            <ChevronRight className={`h-3.5 w-3.5 transition-transform duration-200 ${childActive ? 'text-yeikar-neutral' : 'text-white/40'} group-hover:rotate-90`} />
                          </div>

                          {/* Submenú desplegable al hacer hover */}
                          <div className="mt-1 hidden space-y-1 pl-4 group-hover:block">
                            {item.children!.map((child) => {
                              const childSelected = location.pathname === child.path;
                              return (
                                <Link
                                  key={child.path}
                                  to={child.path}
                                  onClick={onClose}
                                  aria-current={childSelected ? 'page' : undefined}
                                  className={`flex min-h-9 items-center gap-2.5 rounded-lg border-l-2 px-3.5 text-[13px] font-medium transition-all duration-150 ${
                                    childSelected
                                      ? 'border-yeikar-primary bg-yeikar-primary/15 font-bold text-yeikar-primary'
                                      : 'border-white/10 text-white/60 hover:bg-white/[0.06] hover:text-white'
                                  }`}
                                >
                                  <span className="h-1.5 w-1.5 rounded-full bg-current opacity-60" />
                                  <span>{child.name}</span>
                                </Link>
                              );
                            })}
                          </div>
                        </div>
                      );
                    }

                    return (
                      <Link
                        key={item.path}
                        to={item.path}
                        onClick={onClose}
                        aria-current={isActive ? 'page' : undefined}
                        className={`group relative flex min-h-10 items-center justify-between rounded-xl px-3.5 text-[13px] font-medium transition-all duration-200 ${
                          isActive
                            ? 'bg-yeikar-primary font-bold text-yeikar-neutral shadow-gold'
                            : 'text-white/60 hover:bg-white/[0.06] hover:text-white'
                        }`}
                      >
                        <span className="flex items-center gap-3">
                          <Icon className={`h-[17px] w-[17px] transition-colors ${isActive ? 'text-yeikar-neutral' : 'text-white/40 group-hover:text-yeikar-primary'}`} strokeWidth={1.8} />
                          <span>{item.name}</span>
                        </span>
                        {item.badge ? (
                          <span className={`rounded-md px-1.5 py-0.5 font-mono text-[9px] font-bold ${isActive ? 'bg-yeikar-neutral text-yeikar-primary' : 'border border-yeikar-primary/25 bg-yeikar-primary/10 text-yeikar-primary'}`}>
                            {item.badge}
                          </span>
                        ) : isActive ? (
                          <ChevronRight className="h-3.5 w-3.5" />
                        ) : null}
                      </Link>
                    );
                  })}
                </div>
              </div>
            );
          })}
        </nav>

        <div className="border-t border-white/10 bg-black/10 p-4 pb-safe">
          <div className="mb-3 flex items-center gap-3 rounded-xl border border-white/10 bg-white/[0.045] p-2.5">
            <div className="flex h-9 w-9 shrink-0 items-center justify-center rounded-lg border border-yeikar-primary/30 bg-yeikar-secondary font-headline text-xs font-bold text-yeikar-primary">
              {initials}
            </div>
            <div className="min-w-0 flex-1">
              <p className="truncate font-headline text-xs font-bold text-white">{nombreUsuario}</p>
              <p className="mt-0.5 truncate font-mono text-[9px] uppercase tracking-wider text-white/40">{roles.join(', ') || 'Usuario'}</p>
            </div>
          </div>
          <div className="mb-2 space-y-1">
            <button
              type="button"
              onClick={() => { navigate('/seguridad'); onClose(); }}
              aria-current={location.pathname === '/seguridad' ? 'page' : undefined}
              className={`flex w-full items-center justify-center gap-2 rounded-xl border py-2.5 text-xs font-bold transition-colors ${
                location.pathname === '/seguridad'
                  ? 'border-yeikar-primary/40 bg-yeikar-primary/10 text-yeikar-primary'
                  : 'border-white/10 text-white/50 hover:bg-white/[0.06] hover:text-white'
              }`}
            >
              <ShieldCheck className="h-3.5 w-3.5" />
              Mi seguridad
            </button>
          </div>
          <button
            type="button"
            onClick={handleLogout}
            className="flex w-full items-center justify-center gap-2 rounded-xl border border-white/10 py-2.5 text-xs font-bold text-white/50 transition-colors hover:border-rose-300/20 hover:bg-rose-400/10 hover:text-rose-200"
          >
            <LogOut className="h-3.5 w-3.5" />
            Cerrar sesión
          </button>
        </div>
      </aside>
    </>
  );
}
