import React, { useEffect, useState } from 'react';
import {
  BarChart,
  Bar,
  XAxis,
  YAxis,
  CartesianGrid,
  Tooltip,
  Legend,
  ResponsiveContainer,
} from 'recharts';
import {
  reportesService,
  PnLDetail,
  RentabilidadProductoResponse,
  ReportAlertaStockResponse,
} from '../services/reportesService';
import InformeMensual from '../components/InformeMensual';

export default function Reportes() {
  const [activeTab, setActiveTab] = useState<'informe' | 'pnl' | 'rentabilidad' | 'alertas'>('informe');
  const [selectedMonth, setSelectedMonth] = useState(() => {
    const d = new Date();
    const month = String(d.getMonth() + 1).padStart(2, '0');
    return `${d.getFullYear()}-${month}`;
  });

  // P&L State
  const [pnlDetails, setPnlDetails] = useState<PnLDetail[]>([]);
  const [pnlLoading, setPnlLoading] = useState(false);
  const [chartData, setChartData] = useState<any[]>([]);
  const [chartLoading, setChartLoading] = useState(false);

  // Rentabilidad State
  const [rentabilidad, setRentabilidad] = useState<RentabilidadProductoResponse[]>([]);
  const [rentabilidadLoading, setRentabilidadLoading] = useState(false);

  // Alertas State
  const [alertas, setAlertas] = useState<ReportAlertaStockResponse[]>([]);
  const [alertasLoading, setAlertasLoading] = useState(false);

  // Load P&L for selected month
  const fetchPnL = async () => {
    try {
      setPnlLoading(true);
      const data = await reportesService.getPnL(selectedMonth);
      setPnlDetails(data.detalles || []);
    } catch (error) {
      console.error('Error fetching P&L:', error);
      setPnlDetails([]);
    } finally {
      setPnlLoading(false);
    }
  };

  // Load last 6 months for chart
  const fetchChartData = async () => {
    try {
      setChartLoading(true);
      const months: string[] = [];
      const [yearStr, monthStr] = selectedMonth.split('-');
      let currentYear = parseInt(yearStr);
      let currentMonth = parseInt(monthStr);

      for (let i = 5; i >= 0; i--) {
        let m = currentMonth - i;
        let y = currentYear;
        if (m <= 0) {
          m += 12;
          y -= 1;
        }
        months.push(`${y}-${String(m).padStart(2, '0')}`);
      }

      const promises = months.map(async (m) => {
        try {
          const res = await reportesService.getPnL(m);
          // Agrupar ingresos y gastos de todas las monedas convirtiendo a un valor base o sumando
          const ingresos = res.detalles.reduce((acc, curr) => acc + Number(curr.ingresos), 0);
          const gastos = res.detalles.reduce((acc, curr) => acc + Number(curr.gastos), 0);
          return {
            name: m,
            Ingresos: ingresos,
            Gastos: gastos,
          };
        } catch {
          return { name: m, Ingresos: 0, Gastos: 0 };
        }
      });

      const results = await Promise.all(promises);
      setChartData(results);
    } catch (error) {
      console.error('Error fetching chart data:', error);
    } finally {
      setChartLoading(false);
    }
  };

  // Load Rentabilidad
  const fetchRentabilidad = async () => {
    try {
      setRentabilidadLoading(true);
      const data = await reportesService.getRentabilidad();
      setRentabilidad(data);
    } catch (error) {
      console.error('Error fetching product profitability:', error);
    } finally {
      setRentabilidadLoading(false);
    }
  };

  // Load Alertas
  const fetchAlertas = async () => {
    try {
      setAlertasLoading(true);
      const data = await reportesService.getAlertasStock(5.0);
      setAlertas(data);
    } catch (error) {
      console.error('Error fetching stock alerts:', error);
    } finally {
      setAlertasLoading(false);
    }
  };

  useEffect(() => {
    if (activeTab === 'informe') {
      // InformeMensual se encarga de sus propios datos
    } else if (activeTab === 'pnl') {
      fetchPnL();
      fetchChartData();
    } else if (activeTab === 'rentabilidad') {
      fetchRentabilidad();
    } else if (activeTab === 'alertas') {
      fetchAlertas();
    }
  }, [activeTab, selectedMonth]);

  return (
    <div className="space-y-8">
      {/* Header */}
      <div>
        <h1 className="text-3xl font-black font-headline text-yeikar-neutral tracking-tight">
          Reportes y Análisis Financiero
        </h1>
        <p className="text-yeikar-neutral/60 mt-1">
          Visualiza pérdidas y ganancias, rentabilidad de recetas y alertas operativas.
        </p>
      </div>

      {/* Tabs Menu */}
      <div className="flex border-b border-yeikar-secondary-light/10 overflow-x-auto scroll-touch [scroll-snap-type:x_proximity]">
        <button
          onClick={() => setActiveTab('informe')}
          className={`px-5 py-3 font-headline font-bold text-sm tracking-tight border-b-2 transition-all whitespace-nowrap snap-start ${
            activeTab === 'informe'
              ? 'border-yeikar-primary text-yeikar-primary'
              : 'border-transparent text-yeikar-neutral/60 hover:text-yeikar-secondary'
          }`}
        >
          Informe Mensual
        </button>
        <button
          onClick={() => setActiveTab('pnl')}
          className={`px-5 py-3 font-headline font-bold text-sm tracking-tight border-b-2 transition-all whitespace-nowrap snap-start ${
            activeTab === 'pnl'
              ? 'border-yeikar-primary text-yeikar-primary'
              : 'border-transparent text-yeikar-neutral/60 hover:text-yeikar-secondary'
          }`}
        >
          Pérdidas y Ganancias (P&L)
        </button>
        <button
          onClick={() => setActiveTab('rentabilidad')}
          className={`px-5 py-3 font-headline font-bold text-sm tracking-tight border-b-2 transition-all whitespace-nowrap snap-start ${
            activeTab === 'rentabilidad'
              ? 'border-yeikar-primary text-yeikar-primary'
              : 'border-transparent text-yeikar-neutral/60 hover:text-yeikar-secondary'
          }`}
        >
          Rentabilidad por Producto
        </button>
        <button
          onClick={() => setActiveTab('alertas')}
          className={`px-5 py-3 font-headline font-bold text-sm tracking-tight border-b-2 transition-all whitespace-nowrap snap-start ${
            activeTab === 'alertas'
              ? 'border-yeikar-primary text-yeikar-primary'
              : 'border-transparent text-yeikar-neutral/60 hover:text-yeikar-secondary'
          }`}
        >
          Alertas de Stock Crítico
        </button>
      </div>

      {/* TAB: INFORME MENSUAL */}
      {activeTab === 'informe' && <InformeMensual />}

      {/* TAB 1: P&L */}
      {activeTab === 'pnl' && (
        <div className="space-y-6">
          <div className="flex flex-wrap items-center justify-between gap-4 bg-white border border-yeikar-secondary-light/10 rounded-2xl p-5 shadow-sm">
            <div className="flex items-center gap-3">
              <label className="text-sm font-bold text-yeikar-secondary">Seleccionar Mes:</label>
              <input
                type="month"
                value={selectedMonth}
                onChange={(e) => setSelectedMonth(e.target.value)}
                className="bg-yeikar-tertiary/40 border border-yeikar-secondary-light/10 rounded-xl px-4 py-2 text-sm text-yeikar-neutral focus:outline-none focus:border-yeikar-primary"
              />
            </div>
          </div>

          <div className="grid grid-cols-1 lg:grid-cols-3 gap-6">
            {/* Table Detail */}
            <div className="lg:col-span-1 bg-white border border-yeikar-secondary-light/10 rounded-3xl p-5 shadow-sm space-y-4">
              <h3 className="text-base font-bold font-headline text-yeikar-secondary">
                Detalle del Mes
              </h3>
              
              {pnlLoading ? (
                <div className="flex flex-col items-center justify-center py-12 space-y-2">
                  <div className="w-8 h-8 border-4 border-yeikar-primary border-t-transparent rounded-full animate-spin"></div>
                  <p className="text-xs font-mono text-yeikar-neutral/50">Cargando cuentas...</p>
                </div>
              ) : pnlDetails.length === 0 ? (
                <p className="text-xs text-yeikar-neutral/40 italic py-8 text-center">
                  No hay registros financieros para este mes.
                </p>
              ) : (
                <div className="space-y-4">
                  {pnlDetails.map((detail) => (
                    <div
                      key={detail.moneda}
                      className="border border-yeikar-secondary-light/5 rounded-2xl p-4 bg-yeikar-tertiary/10 space-y-2.5"
                    >
                      <div className="flex justify-between items-center border-b border-yeikar-secondary-light/5 pb-1.5">
                        <span className="font-mono text-xs font-bold text-yeikar-neutral/40">MONEDA</span>
                        <span className="font-headline font-bold text-yeikar-primary text-sm">{detail.moneda}</span>
                      </div>
                      
                      <div className="flex justify-between text-xs">
                        <span className="text-yeikar-neutral/60">Ingresos (+)</span>
                        <span className="font-mono font-bold text-green-600">
                          ${Number(detail.ingresos_cop).toLocaleString('es-ES')} COP
                        </span>
                      </div>

                      <div className="flex justify-between text-xs">
                        <span className="text-yeikar-neutral/60">Costos/Gastos (-)</span>
                        <span className="font-mono font-bold text-red-500">
                          ${Number(detail.gastos_cop).toLocaleString('es-ES')} COP
                        </span>
                      </div>

                      <div className="flex justify-between text-xs">
                        <span className="text-yeikar-neutral/40 italic">Monto original</span>
                        <span className="font-mono text-yeikar-neutral/50">
                          {Number(detail.ingresos).toLocaleString('es-ES')} / {Number(detail.gastos).toLocaleString('es-ES')} {detail.moneda}
                        </span>
                      </div>

                      <div className="flex justify-between text-sm pt-2 border-t border-dashed border-yeikar-secondary-light/5">
                        <span className="font-headline font-bold text-yeikar-secondary">Utilidad Neta (COP)</span>
                        <span className={`font-mono font-bold ${Number(detail.balance_cop) >= 0 ? 'text-green-600' : 'text-red-500'}`}>
                          ${Number(detail.balance_cop).toLocaleString('es-ES')}
                        </span>
                      </div>
                    </div>
                  ))}
                </div>
              )}
            </div>

            {/* Recharts chart */}
            <div className="lg:col-span-2 bg-white border border-yeikar-secondary-light/10 rounded-3xl p-5 shadow-sm space-y-4 flex flex-col min-h-[350px]">
              <h3 className="text-base font-bold font-headline text-yeikar-secondary">
                Histórico de Ingresos vs Costos (Últimos 6 meses)
              </h3>
              
              <div className="flex-1 min-h-[280px] w-full">
                {chartLoading ? (
                  <div className="h-full flex flex-col items-center justify-center space-y-2">
                    <div className="w-8 h-8 border-4 border-yeikar-primary border-t-transparent rounded-full animate-spin"></div>
                    <p className="text-xs font-mono text-yeikar-neutral/50">Generando gráfico...</p>
                  </div>
                ) : (
                  <ResponsiveContainer width="100%" height={280}>
                    <BarChart data={chartData} margin={{ top: 10, right: 10, left: -20, bottom: 0 }}>
                      <CartesianGrid strokeDasharray="3 3" vertical={false} stroke="#E5E7EB" />
                      <XAxis dataKey="name" stroke="#9CA3AF" fontSize={11} tickLine={false} />
                      <YAxis stroke="#9CA3AF" fontSize={11} tickLine={false} />
                      <Tooltip />
                      <Legend iconType="circle" wrapperStyle={{ fontSize: '12px' }} />
                      <Bar dataKey="Ingresos" fill="#10B981" radius={[4, 4, 0, 0]} />
                      <Bar dataKey="Gastos" fill="#EF4444" radius={[4, 4, 0, 0]} />
                    </BarChart>
                  </ResponsiveContainer>
                )}
              </div>
            </div>
          </div>
        </div>
      )}

      {/* TAB 2: RENTABILIDAD */}
      {activeTab === 'rentabilidad' && (
        <div className="bg-white border border-yeikar-secondary-light/10 rounded-3xl shadow-sm overflow-hidden">
          <div className="p-5 border-b border-yeikar-secondary-light/5">
            <h3 className="text-base font-bold font-headline text-yeikar-secondary">
              Rentabilidad y Márgenes por Producto
            </h3>
          </div>

          {rentabilidadLoading ? (
            <div className="flex flex-col items-center justify-center py-20 space-y-4">
              <div className="w-10 h-10 border-4 border-yeikar-primary border-t-transparent rounded-full animate-spin"></div>
              <p className="text-xs font-mono text-yeikar-neutral/60">Analizando recetas y ventas...</p>
            </div>
          ) : (
            <div className="overflow-x-auto">
              <table className="w-full text-left border-collapse">
                <thead>
                  <tr className="bg-yeikar-tertiary/20 text-yeikar-secondary font-headline font-bold text-xs uppercase tracking-wider">
                    <th className="p-4 border-b border-yeikar-secondary-light/5">Producto</th>
                    <th className="p-4 border-b border-yeikar-secondary-light/5">Unid. Vendidas</th>
                    <th className="p-4 border-b border-yeikar-secondary-light/5">Precio Venta Prom</th>
                    <th className="p-4 border-b border-yeikar-secondary-light/5">Costo Prod Prom</th>
                    <th className="p-4 border-b border-yeikar-secondary-light/5">Margen Prom</th>
                    <th className="p-4 border-b border-yeikar-secondary-light/5">Moneda</th>
                  </tr>
                </thead>
                <tbody className="divide-y divide-yeikar-secondary-light/5 text-sm">
                  {rentabilidad.length === 0 ? (
                    <tr>
                      <td colSpan={6} className="p-8 text-center text-yeikar-neutral/40 italic">
                        No hay datos de rentabilidad disponibles.
                      </td>
                    </tr>
                  ) : (
                    rentabilidad.map((item) => {
                      const isHighMargen = item.margen_promedio >= 40.0;
                      return (
                        <tr key={item.producto_id} className="hover:bg-yeikar-tertiary/10 transition-colors">
                          <td className="p-4 font-semibold text-yeikar-secondary">
                            {item.producto_nombre}
                          </td>
                          <td className="p-4 font-mono font-medium">{item.cantidad_vendida}</td>
                          <td className="p-4 font-mono">
                            ${item.precio_promedio_venta.toLocaleString('es-ES')}
                          </td>
                          <td className="p-4 font-mono text-yeikar-neutral/75">
                            ${item.costo_promedio_produccion.toLocaleString('es-ES')}
                          </td>
                          <td className="p-4 font-mono font-bold">
                            <span
                              className={`px-2.5 py-0.5 rounded-full text-xs font-bold ${
                                isHighMargen
                                  ? 'bg-green-50 text-green-700 border border-green-200'
                                  : 'bg-amber-50 text-amber-700 border border-amber-200'
                              }`}
                            >
                              {item.margen_promedio.toFixed(1)}%
                            </span>
                          </td>
                          <td className="p-4 font-mono text-xs text-yeikar-neutral/50">
                            {item.moneda}
                          </td>
                        </tr>
                      );
                    })
                  )}
                </tbody>
              </table>
            </div>
          )}
        </div>
      )}

      {/* TAB 3: ALERTAS */}
      {activeTab === 'alertas' && (
        <div className="bg-white border border-yeikar-secondary-light/10 rounded-3xl shadow-sm overflow-hidden">
          <div className="p-5 border-b border-yeikar-secondary-light/5">
            <h3 className="text-base font-bold font-headline text-yeikar-secondary">
              Alertas de Stock Bajo / Reabastecimiento
            </h3>
          </div>

          {alertasLoading ? (
            <div className="flex flex-col items-center justify-center py-20 space-y-4">
              <div className="w-10 h-10 border-4 border-yeikar-primary border-t-transparent rounded-full animate-spin"></div>
              <p className="text-xs font-mono text-yeikar-neutral/60">Escaneando inventarios...</p>
            </div>
          ) : (
            <div className="overflow-x-auto">
              <table className="w-full text-left border-collapse">
                <thead>
                  <tr className="bg-yeikar-tertiary/20 text-yeikar-secondary font-headline font-bold text-xs uppercase tracking-wider">
                    <th className="p-4 border-b border-yeikar-secondary-light/5">Material</th>
                    <th className="p-4 border-b border-yeikar-secondary-light/5">Bodega / Ubicación</th>
                    <th className="p-4 border-b border-yeikar-secondary-light/5">Existencia Actual</th>
                    <th className="p-4 border-b border-yeikar-secondary-light/5">Umbral Crítico</th>
                    <th className="p-4 border-b border-yeikar-secondary-light/5">Estado</th>
                  </tr>
                </thead>
                <tbody className="divide-y divide-yeikar-secondary-light/5 text-sm">
                  {alertas.length === 0 ? (
                    <tr>
                      <td colSpan={5} className="p-8 text-center text-green-600 font-semibold italic">
                        Todos los niveles de stock están saludables.
                      </td>
                    </tr>
                  ) : (
                    alertas.map((item) => (
                      <tr key={item.material_id} className="hover:bg-yeikar-tertiary/10 transition-colors">
                        <td className="p-4 font-semibold text-yeikar-secondary">
                          {item.material_nombre}
                        </td>
                        <td className="p-4 text-yeikar-neutral/75">{item.ubicacion_nombre}</td>
                        <td className="p-4 font-mono font-bold text-red-500">
                          {item.cantidad_actual} {item.unidad_medida}
                        </td>
                        <td className="p-4 font-mono text-yeikar-neutral/60">
                          {item.umbral} {item.unidad_medida}
                        </td>
                        <td className="p-4">
                          <span className="bg-red-100 text-red-800 text-xs font-bold px-2.5 py-0.5 rounded-full border border-red-200">
                            Reordenar
                          </span>
                        </td>
                      </tr>
                    ))
                  )}
                </tbody>
              </table>
            </div>
          )}
        </div>
      )}
    </div>
  );
}
