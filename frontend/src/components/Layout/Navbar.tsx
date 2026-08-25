import { useLocation } from 'react-router-dom';
import { CalendarDays, Menu, Search } from 'lucide-react';

interface NavbarProps {
  onMenuClick: () => void;
}

const pageMeta: Record<string, { title: string; category: string }> = {
  '/dashboard': { title: 'Panel principal', category: 'Resumen' },
  '/clientes': { title: 'Clientes', category: 'Operación' },
  '/cotizaciones': { title: 'Cotizaciones', category: 'Operación' },
  '/cotizaciones-ia': { title: 'Cotizador inteligente', category: 'Operación' },
  '/pedidos': { title: 'Pedidos', category: 'Operación' },
  '/historial': { title: 'Expediente', category: 'Operación' },
  '/produccion': { title: 'Producción', category: 'Operación' },
  '/empleados': { title: 'Empleados', category: 'Operación' },
  '/inventario': { title: 'Inventario', category: 'Operación' },
  '/productos': { title: 'Productos', category: 'Operación' },
  '/costos': { title: 'Calculadora de costos', category: 'Operación' },
  '/envios': { title: 'Despachos', category: 'Operación' },
  '/mis-despachos': { title: 'Mis Despachos', category: 'Operación' },
  '/ventas': { title: 'Ventas y cobros', category: 'Finanzas' },
  '/facturacion': { title: 'Facturación', category: 'Finanzas' },
  '/gastos': { title: 'Egresos y gastos', category: 'Finanzas' },
  '/costos-produccion': { title: 'Costos de Producción', category: 'Finanzas' },
  '/nomina': { title: 'Nómina', category: 'Finanzas' },
  '/cuentas': { title: 'Cuentas', category: 'Finanzas' },
  '/reportes': { title: 'Reportes financieros', category: 'Finanzas' },
  '/reporte-diario': { title: 'Estado del día', category: 'Finanzas' },
  '/usuarios': { title: 'Gestión de usuarios', category: 'Administración' },
  '/auditoria': { title: 'Actividad del sistema', category: 'Administración' },
};

export default function Navbar({ onMenuClick }: NavbarProps) {
  const location = useLocation();
  const meta = pageMeta[location.pathname] || { title: 'YEIKAR ERP', category: 'Atelier' };
  const fechaActual = new Date().toLocaleDateString('es-ES', {
    weekday: 'short',
    day: 'numeric',
    month: 'short',
  });

  return (
    <header className="sticky top-0 z-20 flex h-[72px] items-center justify-between border-b border-yeikar-secondary-light/10 bg-yeikar-tertiary/90 px-4 backdrop-blur-xl sm:px-6 lg:px-8">
      <div className="flex min-w-0 items-center gap-3">
        <button
          type="button"
          onClick={onMenuClick}
          className="rounded-xl border border-yeikar-secondary-light/15 bg-white p-2.5 text-yeikar-secondary shadow-subtle transition-colors hover:border-yeikar-primary/50 hover:text-yeikar-primary-dark lg:hidden"
          aria-label="Abrir navegación"
        >
          <Menu className="h-5 w-5" />
        </button>
        <div className="min-w-0">
          <div className="flex items-center gap-2">
            <span className="hidden font-mono text-[10px] font-bold uppercase tracking-[0.16em] text-yeikar-primary-dark sm:inline">{meta.category}</span>
            <span className="hidden text-yeikar-secondary-light/30 sm:inline">/</span>
            <h1 className="truncate font-headline text-base font-bold tracking-tight text-yeikar-neutral sm:text-lg">{meta.title}</h1>
          </div>
          <p className="mt-0.5 hidden text-xs text-yeikar-neutral/45 sm:block">Control operativo con intención.</p>
        </div>
      </div>

      <div className="flex items-center gap-2 sm:gap-4">
        <button
          type="button"
          className="hidden items-center gap-2 rounded-xl border border-yeikar-secondary-light/10 bg-white/70 px-3 py-2 text-xs text-yeikar-neutral/45 shadow-subtle transition-colors hover:border-yeikar-primary/40 hover:text-yeikar-secondary md:flex"
          aria-label="Buscar en YEIKAR"
        >
          <Search className="h-3.5 w-3.5" />
          <span>Buscar</span>
          <kbd className="ml-3 rounded-md border border-yeikar-secondary-light/10 bg-yeikar-tertiary px-1.5 py-0.5 font-mono text-[9px]">⌘ K</kbd>
        </button>
        <div className="hidden items-center gap-2 rounded-xl border border-yeikar-secondary-light/10 bg-white/70 px-3 py-2 text-xs text-yeikar-neutral/55 shadow-subtle lg:flex">
          <CalendarDays className="h-3.5 w-3.5 text-yeikar-primary-dark" />
          <span className="capitalize">{fechaActual}</span>
        </div>
        <div className="flex items-center gap-2 rounded-full border border-emerald-700/10 bg-emerald-50/70 px-2.5 py-1.5 text-[11px] font-bold text-emerald-800 sm:px-3">
          <span className="relative flex h-1.5 w-1.5">
            <span className="absolute inline-flex h-full w-full animate-ping rounded-full bg-emerald-400 opacity-70" />
            <span className="relative inline-flex h-1.5 w-1.5 rounded-full bg-emerald-500" />
          </span>
          <span className="hidden sm:inline">Sistema en línea</span>
        </div>
      </div>
    </header>
  );
}
