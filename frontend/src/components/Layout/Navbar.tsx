import { useLocation } from 'react-router-dom';

export default function Navbar() {
  const location = useLocation();

  // Obtener el título legible del módulo actual
  const getPageTitle = () => {
    switch (location.pathname) {
      case '/dashboard':
        return 'Panel de Control';
      case '/clientes':
        return 'Gestión de Clientes';
      case '/cotizaciones':
        return 'Cotizaciones';
      case '/pedidos':
        return 'Pedidos';
      case '/produccion':
        return 'Seguimiento de Producción';
      case '/inventario':
        return 'Inventario de Materiales';
      case '/costos':
        return 'Calculadora de Costos';
      default:
        return 'YEIKAR ERP';
    }
  };

  return (
    <header className="bg-white border-b border-yeikar-secondary-light/10 h-16 px-8 flex items-center justify-between shadow-sm">
      <div>
        <h2 className="text-xl font-black text-yeikar-secondary tracking-tight font-headline">
          {getPageTitle()}
        </h2>
      </div>
      <div className="flex items-center gap-4">
        {/* Fecha Actual */}
        <span className="text-sm text-yeikar-neutral/60 font-mono hidden md:inline">
          {new Date().toLocaleDateString('es-ES', {
            weekday: 'long',
            year: 'numeric',
            month: 'long',
            day: 'numeric',
          })}
        </span>
        <div className="w-1.5 h-1.5 bg-yeikar-primary rounded-full" />
      </div>
    </header>
  );
}
