import { BrowserRouter, Routes, Route, Navigate, useLocation } from 'react-router-dom';
import { HelmetProvider } from 'react-helmet-async';
import SEO, { OrganizationSchema } from './components/SEO';
import Login from './pages/Login';
import Dashboard from './pages/Dashboard';
import Clientes from './pages/Clientes';
import Cotizaciones from './pages/Cotizaciones';
import Pedidos from './pages/Pedidos';
import ProduccionKanban from './pages/ProduccionKanban';
import Inventario from './pages/Inventario';
import Reportes from './pages/Reportes';
import Productos from './pages/Productos';
import Calculadora from './pages/Calculadora';
import Ventas from './pages/Ventas';
import Facturacion from './pages/Facturacion';
import Despachos from './pages/Despachos';
import MisDespachos from './pages/MisDespachos';
import Usuarios from './pages/Usuarios';
import Gastos from './pages/Gastos';
import Cuentas from './pages/Cuentas';
import CostosProduccion from './pages/CostosProduccion';
import Nomina from './pages/Nomina';
import Empleados from './pages/Empleados';
import CotizadorInteligente from './pages/CotizadorInteligente';
import Auditoria from './pages/Auditoria';
import EstadoDia from './pages/EstadoDia';
import Expediente from './pages/Expediente';
import NotFound from './pages/NotFound';
import DashboardLayout from './components/Layout/DashboardLayout';
import { AuthProvider, useAuth } from './context/AuthContext';
import { ToastProvider } from './context/ToastContext';

// Qué módulo protege cada ruta (claves del catálogo del backend)
const ROUTE_MODULES: Record<string, string> = {
  '/dashboard': 'dashboard',
  '/clientes': 'clientes',
  '/cotizaciones': 'cotizaciones',
  '/cotizaciones-ia': 'cotizaciones_ia',
  '/pedidos': 'pedidos',
  '/historial': 'pedidos',
  '/produccion': 'produccion',
  '/inventario': 'inventario',
  '/reportes': 'reportes',
  '/reporte-diario': 'reportes',
  '/productos': 'productos',
  '/costos': 'productos',
  '/ventas': 'ventas',
  '/facturacion': 'facturacion',
  '/envios': 'envios',
  '/mis-despachos': 'envios',
  '/gastos': 'gastos',
  '/cuentas': 'cuentas',
  '/costos-produccion': 'costos_produccion',
  '/nomina': 'nomina',
  '/empleados': 'empleados',
  '/usuarios': 'usuarios',
  '/auditoria': 'usuarios',
};

function PrivateRoute({ children }: { children: React.ReactNode }) {
  const location = useLocation();
  const { user, loading, hasModulo, esAdmin } = useAuth();

  const token = localStorage.getItem('token');
  if (!token) return <Navigate to="/login" state={{ from: location }} />;

  if (loading) {
    return (
      <div className="premium-grid flex min-h-screen items-center justify-center bg-yeikar-tertiary p-6">
        <div className="flex w-full max-w-xs flex-col items-center rounded-2xl border border-yeikar-secondary-light/10 bg-white/75 p-8 text-center shadow-card backdrop-blur-xl">
          <div className="mb-5 flex h-12 w-12 items-center justify-center rounded-xl bg-yeikar-primary font-headline text-2xl font-black text-yeikar-neutral shadow-gold">Y</div>
          <div className="mb-4 h-1 w-24 overflow-hidden rounded-full bg-yeikar-tertiary">
            <div className="h-full w-1/2 animate-pulse rounded-full bg-yeikar-primary" />
          </div>
          <p className="font-headline text-sm font-bold text-yeikar-secondary">Preparando tu espacio</p>
          <p className="mt-1 text-xs text-yeikar-neutral/45">Validando la sesión de YEIKAR</p>
        </div>
      </div>
    );
  }

  if (!user) return <Navigate to="/login" state={{ from: location }} />;

  const modulo = ROUTE_MODULES[location.pathname];
  if (modulo && modulo !== 'dashboard' && !hasModulo(modulo)) {
    return <Navigate to="/dashboard" />;
  }

  // Vista bifurcada por rol: la administradora ve el panel completo de
  // Despachos (/envios); el chofer ve solo sus repartos (/mis-despachos).
  if (location.pathname === '/envios' && !esAdmin) {
    return <Navigate to="/mis-despachos" replace />;
  }
  if (location.pathname === '/mis-despachos' && esAdmin) {
    return <Navigate to="/envios" replace />;
  }

  // Reportes financieros y datos globales: solo dueños/administradores.
  if ((location.pathname === '/reportes' || location.pathname === '/reporte-diario') && !esAdmin) {
    return <Navigate to="/dashboard" replace />;
  }

  return <>{children}</>;
}

const pageMeta: Record<string, { title: string; description: string }> = {
  '/login': {
    title: 'Iniciar Sesión',
    description: 'Accede al sistema de gestión ERP para tu mueblería.',
  },
  '/dashboard': {
    title: 'Dashboard',
    description: 'Panel de control con indicadores clave de producción, ventas e inventario.',
  },
  '/clientes': {
    title: 'Clientes',
    description: 'Gestión de clientes y base de datos de contactos.',
  },
  '/cotizaciones': {
    title: 'Cotizaciones',
    description: 'Crea y gestiona cotizaciones para tus proyectos de mueblería.',
  },
  '/cotizaciones-ia': {
    title: 'Cotizador Inteligente',
    description: 'Cotizaciones asistidas por inteligencia artificial para tu mueblería.',
  },
  '/pedidos': {
    title: 'Pedidos',
    description: 'Administración de pedidos y órdenes de compra.',
  },
  '/historial': {
    title: 'Expediente',
    description: 'Historial completo de cada negocio: cotización, pedido, producción, cobros, factura y despacho.',
  },
  '/produccion': {
    title: 'Producción',
    description: 'Gestión de producción con tablero Kanban para seguimiento de etapas.',
  },
  '/inventario': {
    title: 'Inventario',
    description: 'Control de inventario, existencias y movimientos de materiales.',
  },
  '/reportes': {
    title: 'Reportes',
    description: 'Reportes financieros y de rentabilidad para tu negocio de muebles.',
  },
  '/reporte-diario': {
    title: 'Estado del día',
    description: 'Ingresos y egresos del día, quién los hizo y saldo de caja.',
  },
  '/productos': {
    title: 'Productos',
    description: 'Catálogo de productos con recetas, costos y precios.',
  },
  '/costos': {
    title: 'Calculadora de Costos',
    description: 'Calculadora de costos de fabricación para muebles y productos.',
  },
  '/ventas': {
    title: 'Ventas',
    description: 'Registro y seguimiento de ventas con generación de facturas.',
  },
  '/facturacion': {
    title: 'Facturación',
    description: 'Emisión de facturas fiscales de pedidos pagados al 100% con montos en USD.',
  },
  '/envios': {
    title: 'Despachos',
    description: 'Gestión de envíos y guías de despacho.',
  },
  '/mis-despachos': {
    title: 'Mis Despachos',
    description: 'Tus repartos asignados: dirección, muebles a entregar y monitoreo de tu recorrido.',
  },
  '/gastos': {
    title: 'Gastos',
    description: 'Control de gastos operativos y administrativos.',
  },
  '/cuentas': {
    title: 'Cuentas',
    description: 'Medios de pago (efectivo, Zelle, bancos) y movimientos de cada cuenta con responsable.',
  },
  '/costos-produccion': {
    title: 'Costos de Producción',
    description: 'Listado de precios de producción por área (Ebanistería, Preparación, Pintura, Tapicería).',
  },
  '/nomina': {
    title: 'Nómina',
    description: 'Nómina semanal, pagos por empleado y acumulación de aguinaldo.',
  },
  '/empleados': {
    title: 'Empleados',
    description: 'Registro del personal y configuración de nómina.',
  },
  '/usuarios': {
    title: 'Usuarios',
    description: 'Administración de usuarios y roles del sistema.',
  },
  '/auditoria': {
    title: 'Actividad del sistema',
    description: 'Trazabilidad de acciones, cambios y responsables dentro de YEIKAR.',
  },
};

function App() {
  return (
    <HelmetProvider>
      <ToastProvider>
        <AuthProvider>
          <BrowserRouter>
          <OrganizationSchema />
          <Routes>
          <Route path="/login" element={<><SEO {...pageMeta['/login']} /><Login /></>} />
          <Route
            path="/dashboard"
            element={
              <PrivateRoute>
                <DashboardLayout>
                  <><SEO {...pageMeta['/dashboard']} /><Dashboard /></>
                </DashboardLayout>
              </PrivateRoute>
            }
          />
          <Route
            path="/clientes"
            element={
              <PrivateRoute>
                <DashboardLayout>
                  <><SEO {...pageMeta['/clientes']} /><Clientes /></>
                </DashboardLayout>
              </PrivateRoute>
            }
          />
          <Route
            path="/cotizaciones"
            element={
              <PrivateRoute>
                <DashboardLayout>
                  <><SEO {...pageMeta['/cotizaciones']} /><Cotizaciones /></>
                </DashboardLayout>
              </PrivateRoute>
            }
          />
          <Route
            path="/cotizaciones-ia"
            element={
              <PrivateRoute>
                <DashboardLayout>
                  <><SEO {...pageMeta['/cotizaciones-ia']} /><CotizadorInteligente /></>
                </DashboardLayout>
              </PrivateRoute>
            }
          />
          <Route
            path="/pedidos"
            element={
              <PrivateRoute>
                <DashboardLayout>
                  <><SEO {...pageMeta['/pedidos']} /><Pedidos /></>
                </DashboardLayout>
              </PrivateRoute>
            }
          />
          <Route
            path="/historial"
            element={
              <PrivateRoute>
                <DashboardLayout>
                  <><SEO {...pageMeta['/historial']} /><Expediente /></>
                </DashboardLayout>
              </PrivateRoute>
            }
          />
          <Route
            path="/produccion"
            element={
              <PrivateRoute>
                <DashboardLayout>
                  <><SEO {...pageMeta['/produccion']} /><ProduccionKanban /></>
                </DashboardLayout>
              </PrivateRoute>
            }
          />
          <Route
            path="/reportes"
            element={
              <PrivateRoute>
                <DashboardLayout>
                  <><SEO {...pageMeta['/reportes']} /><Reportes /></>
                </DashboardLayout>
              </PrivateRoute>
            }
          />
          <Route
            path="/reporte-diario"
            element={
              <PrivateRoute>
                <DashboardLayout>
                  <><SEO {...pageMeta['/reporte-diario']} /><EstadoDia /></>
                </DashboardLayout>
              </PrivateRoute>
            }
          />
          <Route
            path="/productos"
            element={
              <PrivateRoute>
                <DashboardLayout>
                  <><SEO {...pageMeta['/productos']} /><Productos /></>
                </DashboardLayout>
              </PrivateRoute>
            }
          />
          <Route
            path="/costos"
            element={
              <PrivateRoute>
                <DashboardLayout>
                  <><SEO {...pageMeta['/costos']} /><Calculadora /></>
                </DashboardLayout>
              </PrivateRoute>
            }
          />
          <Route
            path="/ventas"
            element={
              <PrivateRoute>
                <DashboardLayout>
                  <><SEO {...pageMeta['/ventas']} /><Ventas /></>
                </DashboardLayout>
              </PrivateRoute>
            }
          />
          <Route
            path="/facturacion"
            element={
              <PrivateRoute>
                <DashboardLayout>
                  <><SEO {...pageMeta['/facturacion']} /><Facturacion /></>
                </DashboardLayout>
              </PrivateRoute>
            }
          />
          <Route
            path="/envios"
            element={
              <PrivateRoute>
                <DashboardLayout>
                  <><SEO {...pageMeta['/envios']} /><Despachos /></>
                </DashboardLayout>
              </PrivateRoute>
            }
          />
          <Route
            path="/mis-despachos"
            element={
              <PrivateRoute>
                <DashboardLayout>
                  <><SEO {...pageMeta['/mis-despachos']} /><MisDespachos /></>
                </DashboardLayout>
              </PrivateRoute>
            }
          />
          <Route
            path="/gastos"
            element={
              <PrivateRoute>
                <DashboardLayout>
                  <><SEO {...pageMeta['/gastos']} /><Gastos /></>
                </DashboardLayout>
              </PrivateRoute>
            }
          />
          <Route
            path="/cuentas"
            element={
              <PrivateRoute>
                <DashboardLayout>
                  <><SEO {...pageMeta['/cuentas']} /><Cuentas /></>
                </DashboardLayout>
              </PrivateRoute>
            }
          />
          <Route
            path="/costos-produccion"
            element={
              <PrivateRoute>
                <DashboardLayout>
                  <><SEO {...pageMeta['/costos-produccion']} /><CostosProduccion /></>
                </DashboardLayout>
              </PrivateRoute>
            }
          />
          <Route
            path="/nomina"
            element={
              <PrivateRoute>
                <DashboardLayout>
                  <><SEO {...pageMeta['/nomina']} /><Nomina /></>
                </DashboardLayout>
              </PrivateRoute>
            }
          />
          <Route
            path="/empleados"
            element={
              <PrivateRoute>
                <DashboardLayout>
                  <><SEO {...pageMeta['/empleados']} /><Empleados /></>
                </DashboardLayout>
              </PrivateRoute>
            }
          />
          <Route
            path="/usuarios"
            element={
              <PrivateRoute>
                <DashboardLayout>
                  <><SEO {...pageMeta['/usuarios']} /><Usuarios /></>
                </DashboardLayout>
              </PrivateRoute>
            }
          />
          <Route
            path="/auditoria"
            element={
              <PrivateRoute>
                <DashboardLayout>
                  <><SEO {...pageMeta['/auditoria']} /><Auditoria /></>
                </DashboardLayout>
              </PrivateRoute>
            }
          />
          <Route path="/" element={<Navigate to="/dashboard" />} />
          <Route path="*" element={<NotFound />} />
          </Routes>
        </BrowserRouter>
      </AuthProvider>
    </ToastProvider>
  </HelmetProvider>
  );
}

export default App;
