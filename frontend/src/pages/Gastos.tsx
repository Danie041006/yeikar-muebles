import { useState, useEffect, useCallback } from 'react';
import {
  getGastos, getTiposGasto, getMonedas, createGasto, deleteGasto,
  Gasto, GastoCreate, TipoGasto, Moneda,
} from '../services/gastoService';

const CATEGORIAS = [
  { key: '', label: 'Todos' },
  { key: 'OPERATIVO', label: 'Operativos' },
  { key: 'PASIVO', label: 'Pasivos' },
  { key: 'PRODUCCION', label: 'Producción' },
];

export default function Gastos() {
  const [gastos, setGastos] = useState<Gasto[]>([]);
  const [tiposGasto, setTiposGasto] = useState<TipoGasto[]>([]);
  const [monedas, setMonedas] = useState<Moneda[]>([]);
  const [categoria, setCategoria] = useState('');
  const [fechaDesde, setFechaDesde] = useState('');
  const [fechaHasta, setFechaHasta] = useState('');
  const [showModal, setShowModal] = useState(false);
  const [loading, setLoading] = useState(false);

  const [form, setForm] = useState<GastoCreate>({
    tipo_gasto_id: 0,
    moneda_id: 1,
    fecha: new Date().toISOString().split('T')[0],
    monto: 0,
    tasa_cambio: 1,
    descripcion: '',
    observaciones: '',
  });

  const cargarGastos = useCallback(async () => {
    setLoading(true);
    try {
      const data = await getGastos({
        categoria: categoria || undefined,
        fecha_desde: fechaDesde || undefined,
        fecha_hasta: fechaHasta || undefined,
      });
      setGastos(data);
    } finally {
      setLoading(false);
    }
  }, [categoria, fechaDesde, fechaHasta]);

  const cargarCatalogos = useCallback(async () => {
    const [tipos, monedasData] = await Promise.all([
      getTiposGasto(),
      getMonedas(),
    ]);
    setTiposGasto(tipos);
    setMonedas(monedasData);
    if (tipos.length > 0 && form.tipo_gasto_id === 0) {
      setForm((prev) => ({ ...prev, tipo_gasto_id: tipos[0].id }));
    }
  }, []);

  useEffect(() => {
    cargarCatalogos();
  }, [cargarCatalogos]);

  useEffect(() => {
    cargarGastos();
  }, [cargarGastos]);

  const handleCrear = async () => {
    if (!form.tipo_gasto_id || !form.monto || form.monto <= 0) return;
    await createGasto(form);
    setShowModal(false);
    setForm({
      tipo_gasto_id: tiposGasto[0]?.id || 0,
      moneda_id: 1,
      fecha: new Date().toISOString().split('T')[0],
      monto: 0,
      tasa_cambio: 1,
      descripcion: '',
      observaciones: '',
    });
    cargarGastos();
  };

  const handleEliminar = async (id: number) => {
    if (!confirm('¿Eliminar este gasto?')) return;
    await deleteGasto(id);
    cargarGastos();
  };

  const monedaSeleccionada = monedas.find((m) => m.id === form.moneda_id);
  const esUSD = form.moneda_id !== 1;

  const totales = {
    total: gastos.reduce((s, g) => s + Number(g.monto_en_moneda_base), 0),
    operativos: gastos.filter((g) => g.tipo_gasto?.categoria === 'OPERATIVO').reduce((s, g) => s + Number(g.monto_en_moneda_base), 0),
    pasivos: gastos.filter((g) => g.tipo_gasto?.categoria === 'PASIVO').reduce((s, g) => s + Number(g.monto_en_moneda_base), 0),
    produccion: gastos.filter((g) => g.tipo_gasto?.categoria === 'PRODUCCION').reduce((s, g) => s + Number(g.monto_en_moneda_base), 0),
  };

  const badgeColor = (cat?: string) => {
    switch (cat) {
      case 'OPERATIVO': return 'bg-blue-100 text-blue-800';
      case 'PASIVO': return 'bg-red-100 text-red-800';
      case 'PRODUCCION': return 'bg-green-100 text-green-800';
      default: return 'bg-gray-100 text-gray-800';
    }
  };

  return (
    <div className="p-6 space-y-6">
      <div className="flex items-center justify-between">
        <h1 className="text-2xl font-bold">Egresos y Gastos</h1>
        <button
          onClick={() => setShowModal(true)}
          className="px-4 py-2 bg-yeikar-primary text-white rounded-lg hover:opacity-90"
        >
          + Nuevo Gasto
        </button>
      </div>

      <div className="grid grid-cols-4 gap-4">
        <div className="bg-white p-4 rounded-lg shadow border-l-4 border-gray-500">
          <p className="text-sm text-gray-500">Total Egresos</p>
          <p className="text-xl font-bold">${totales.total.toLocaleString()}</p>
        </div>
        <div className="bg-white p-4 rounded-lg shadow border-l-4 border-blue-500">
          <p className="text-sm text-gray-500">Operativos</p>
          <p className="text-xl font-bold text-blue-600">${totales.operativos.toLocaleString()}</p>
        </div>
        <div className="bg-white p-4 rounded-lg shadow border-l-4 border-red-500">
          <p className="text-sm text-gray-500">Pasivos</p>
          <p className="text-xl font-bold text-red-600">${totales.pasivos.toLocaleString()}</p>
        </div>
        <div className="bg-white p-4 rounded-lg shadow border-l-4 border-green-500">
          <p className="text-sm text-gray-500">Producción</p>
          <p className="text-xl font-bold text-green-600">${totales.produccion.toLocaleString()}</p>
        </div>
      </div>

      <div className="flex gap-4 items-center flex-wrap">
        {CATEGORIAS.map((cat) => (
          <button
            key={cat.key}
            onClick={() => setCategoria(cat.key)}
            className={`px-4 py-1.5 rounded-full text-sm font-medium transition ${
              categoria === cat.key
                ? 'bg-yeikar-primary text-white'
                : 'bg-gray-100 text-gray-600 hover:bg-gray-200'
            }`}
          >
            {cat.label}
          </button>
        ))}
        <input
          type="date"
          value={fechaDesde}
          onChange={(e) => setFechaDesde(e.target.value)}
          className="border rounded px-2 py-1.5 text-sm"
          placeholder="Desde"
        />
        <input
          type="date"
          value={fechaHasta}
          onChange={(e) => setFechaHasta(e.target.value)}
          className="border rounded px-2 py-1.5 text-sm"
          placeholder="Hasta"
        />
      </div>

      <div className="bg-white rounded-lg shadow overflow-x-auto">
        <table className="w-full text-sm">
          <thead className="bg-gray-50 text-left">
            <tr>
              <th className="p-3 font-medium">Fecha</th>
              <th className="p-3 font-medium">Tipo</th>
              <th className="p-3 font-medium">Categoría</th>
              <th className="p-3 font-medium">Descripción</th>
              <th className="p-3 font-medium">Monto</th>
              <th className="p-3 font-medium">Moneda Base</th>
              <th className="p-3 font-medium">Acciones</th>
            </tr>
          </thead>
          <tbody>
            {loading ? (
              <tr><td colSpan={7} className="p-6 text-center text-gray-400">Cargando...</td></tr>
            ) : gastos.length === 0 ? (
              <tr><td colSpan={7} className="p-6 text-center text-gray-400">Sin registros</td></tr>
            ) : gastos.map((g) => (
              <tr key={g.id} className="border-t hover:bg-gray-50">
                <td className="p-3">{g.fecha}</td>
                <td className="p-3">{g.tipo_gasto?.nombre || '-'}</td>
                <td className="p-3">
                  <span className={`px-2 py-0.5 rounded-full text-xs font-medium ${badgeColor(g.tipo_gasto?.categoria)}`}>
                    {g.tipo_gasto?.categoria || '-'}
                  </span>
                </td>
                <td className="p-3 max-w-[200px] truncate">{g.descripcion || '-'}</td>
                <td className="p-3">
                  {g.moneda?.simbolo} {Number(g.monto).toLocaleString()}
                </td>
                <td className="p-3">${Number(g.monto_en_moneda_base).toLocaleString()}</td>
                <td className="p-3">
                  <button
                    onClick={() => handleEliminar(g.id)}
                    className="text-red-500 hover:text-red-700 text-xs"
                  >
                    Eliminar
                  </button>
                </td>
              </tr>
            ))}
          </tbody>
        </table>
      </div>

      {showModal && (
        <div className="fixed inset-0 bg-black/50 flex items-center justify-center z-50">
          <div className="bg-white rounded-xl p-6 w-full max-w-lg space-y-4">
            <h2 className="text-lg font-bold">Nuevo Gasto / Egreso</h2>

            <div className="grid grid-cols-2 gap-4">
              <div>
                <label className="block text-sm font-medium mb-1">Tipo de Gasto</label>
                <select
                  value={form.tipo_gasto_id}
                  onChange={(e) => setForm({ ...form, tipo_gasto_id: Number(e.target.value) })}
                  className="w-full border rounded px-3 py-2 text-sm"
                >
                  {tiposGasto.map((t) => (
                    <option key={t.id} value={t.id}>{t.nombre}</option>
                  ))}
                </select>
              </div>
              <div>
                <label className="block text-sm font-medium mb-1">Moneda</label>
                <select
                  value={form.moneda_id}
                  onChange={(e) => setForm({ ...form, moneda_id: Number(e.target.value), tasa_cambio: Number(e.target.value) === 1 ? 1 : form.tasa_cambio })}
                  className="w-full border rounded px-3 py-2 text-sm"
                >
                  {monedas.map((m) => (
                    <option key={m.id} value={m.id}>{m.codigo} - {m.nombre}</option>
                  ))}
                </select>
              </div>
              <div>
                <label className="block text-sm font-medium mb-1">Fecha</label>
                <input
                  type="date"
                  value={form.fecha}
                  onChange={(e) => setForm({ ...form, fecha: e.target.value })}
                  className="w-full border rounded px-3 py-2 text-sm"
                />
              </div>
              <div>
                <label className="block text-sm font-medium mb-1">Monto</label>
                <input
                  type="number"
                  step="0.01"
                  value={form.monto}
                  onChange={(e) => setForm({ ...form, monto: Number(e.target.value) })}
                  className="w-full border rounded px-3 py-2 text-sm"
                />
              </div>
              {esUSD && (
                <div>
                  <label className="block text-sm font-medium mb-1">TRM ({monedaSeleccionada?.codigo} → COP)</label>
                  <input
                    type="number"
                    step="0.01"
                    value={form.tasa_cambio}
                    onChange={(e) => setForm({ ...form, tasa_cambio: Number(e.target.value) })}
                    className="w-full border rounded px-3 py-2 text-sm"
                  />
                </div>
              )}
              <div className="col-span-2">
                <label className="block text-sm font-medium mb-1">Descripción</label>
                <input
                  type="text"
                  value={form.descripcion}
                  onChange={(e) => setForm({ ...form, descripcion: e.target.value })}
                  className="w-full border rounded px-3 py-2 text-sm"
                  placeholder="Ej: Pago de alquiler mes de julio"
                />
              </div>
              <div className="col-span-2">
                <label className="block text-sm font-medium mb-1">Observaciones</label>
                <textarea
                  value={form.observaciones}
                  onChange={(e) => setForm({ ...form, observaciones: e.target.value })}
                  className="w-full border rounded px-3 py-2 text-sm"
                  rows={2}
                />
              </div>
            </div>

            <div className="flex justify-end gap-3 pt-2">
              <button
                onClick={() => setShowModal(false)}
                className="px-4 py-2 border rounded-lg text-sm hover:bg-gray-50"
              >
                Cancelar
              </button>
              <button
                onClick={handleCrear}
                className="px-4 py-2 bg-yeikar-primary text-white rounded-lg text-sm hover:opacity-90"
              >
                Guardar
              </button>
            </div>
          </div>
        </div>
      )}
    </div>
  );
}
