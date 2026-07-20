import { BrowserRouter, Routes, Route, Navigate } from 'react-router-dom';
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
import CotizadorInteligente from './pages/CotizadorInteligente';
import DashboardLayout from './components/Layout/DashboardLayout';
function PrivateRoute({ children }: { children: React.ReactNode }) {
  const token = localStorage.getItem('token');
  return token ? children : <Navigate to="/login" />;
}
function App() {
  return (
    <BrowserRouter>
      <Routes>
        <Route path="/login" element={<Login />} />
        
        {/* Private Routes wrapped in DashboardLayout */}
        <Route
          path="/dashboard"
          element={
            <PrivateRoute>
              <DashboardLayout>
                <Dashboard />
              </DashboardLayout>
            </PrivateRoute>
          }
        />
        <Route
          path="/clientes"
          element={
            <PrivateRoute>
              <DashboardLayout>
                <Clientes />
              </DashboardLayout>
            </PrivateRoute>
          }
        />
        <Route
          path="/cotizaciones"
          element={
            <PrivateRoute>
              <DashboardLayout>
                <Cotizaciones />
              </DashboardLayout>
            </PrivateRoute>
          }
        />
        <Route
          path="/cotizaciones-ia"
          element={
            <PrivateRoute>
              <DashboardLayout>
                <CotizadorInteligente />
              </DashboardLayout>
            </PrivateRoute>
          }
        />
        <Route
          path="/pedidos"
          element={
            <PrivateRoute>
              <DashboardLayout>
                <Pedidos />
              </DashboardLayout>
            </PrivateRoute>
          }
        />
        <Route
          path="/produccion"
          element={
            <PrivateRoute>
              <DashboardLayout>
                <ProduccionKanban />
              </DashboardLayout>
            </PrivateRoute>
          }
        />
        <Route
          path="/inventario"
          element={
            <PrivateRoute>
              <DashboardLayout>
                <Inventario />
              </DashboardLayout>
            </PrivateRoute>
          }
        />
        <Route
          path="/reportes"
          element={
            <PrivateRoute>
              <DashboardLayout>
                <Reportes />
              </DashboardLayout>
            </PrivateRoute>
          }
        />
        <Route
          path="/productos"
          element={
            <PrivateRoute>
              <DashboardLayout>
                <Productos />
              </DashboardLayout>
            </PrivateRoute>
          }
        />
        <Route
          path="/costos"
          element={
            <PrivateRoute>
              <DashboardLayout>
                <Calculadora />
              </DashboardLayout>
            </PrivateRoute>
          }
        />
        <Route
          path="/ventas"
          element={
            <PrivateRoute>
              <DashboardLayout>
                <Ventas />
              </DashboardLayout>
            </PrivateRoute>
          }
        />
        <Route
          path="/envios"
          element={
            <PrivateRoute>
              <DashboardLayout>
                <Despachos />
              </DashboardLayout>
            </PrivateRoute>
          }
        />
        <Route
          path="/usuarios"
          element={
            <PrivateRoute>
              <DashboardLayout>
                <Usuarios />
              </DashboardLayout>
            </PrivateRoute>
          }
        />
        <Route path="/" element={<Navigate to="/dashboard" />} />
      </Routes>
    </BrowserRouter>
  );
}
export default App;
