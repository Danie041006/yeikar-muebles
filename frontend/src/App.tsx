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
import Despachos from './pages/Despachos';
import Usuarios from './pages/Usuarios';
import Gastos from './pages/Gastos';
import CotizadorInteligente from './pages/CotizadorInteligente';
import DashboardLayout from './components/Layout/DashboardLayout';
import { AuthProvider, useAuth } from './context/AuthContext';

// Qué módulo protege cada ruta (claves del catálogo del backend)
const ROUTE_MODULES: Record<string, string> = {
  '/dashboard': 'dashboard',
  '/clientes': 'clientes',
  '/cotizaciones': 'cotizaciones',
  '/cotizaciones-ia': 'cotizaciones_ia',
  '/pedidos': 'pedidos',
  '/produccion': 'produccion',
  '/inventario': 'inventario',
  '/reportes': 'reportes',
  '/productos': 'productos',
  '/costos': 'productos',
  '/ventas': 'ventas',
  '/envios': 'envios',
  '/gastos': 'gastos',
  '/usuarios': 'usuarios',
};

function PrivateRoute({ children }: { children: React.ReactNode }) {
  const location = useLocation();
  const { user, loading, hasModulo } = useAuth();

  const token = localStorage.getItem('token');
  if (!token) return <Navigate to="/login" state={{ from: location }} />;

  if (loading) {
    return (
      <div className="min-h-screen flex items-center justify-center bg-yeikar-tertiary">
        <div className="text-yeikar-secondary font-headline font-bold animate-pulse">Cargando…</div>
      </div>
    );
  }

  if (!user) return <Navigate to="/login" state={{ from: location }} />;

  const modulo = ROUTE_MODULES[location.pathname];
  if (modulo && modulo !== 'dashboard' && !hasModulo(modulo)) {
    return <Navigate to="/dashboard" />;
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
  '/envios': {
    title: 'Despachos',
    description: 'Gestión de envíos y guías de despacho.',
  },
  '/gastos': {
    title: 'Gastos',
    description: 'Control de gastos operativos y administrativos.',
  },
  '/usuarios': {
    title: 'Usuarios',
    description: 'Administración de usuarios y roles del sistema.',
  },
};

function App() {
  return (
    <HelmetProvider>
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
            path="/inventario"
            element={
              <PrivateRoute>
                <DashboardLayout>
                  <><SEO {...pageMeta['/inventario']} /><Inventario /></>
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
            path="/usuarios"
            element={
              <PrivateRoute>
                <DashboardLayout>
                  <><SEO {...pageMeta['/usuarios']} /><Usuarios /></>
                </DashboardLayout>
              </PrivateRoute>
            }
          />
          <Route path="/" element={<Navigate to="/dashboard" />} />
          </Routes>
        </BrowserRouter>
      </AuthProvider>
    </HelmetProvider>
  );
}

export default App;
