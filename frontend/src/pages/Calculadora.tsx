import { useState, useEffect, useCallback } from 'react';
import { cotizacionService, Product, CalculationResult } from '../services/cotizacionService';

// ─── Badge de tipo de escala ────────────────────────────────────────────────
function EscalaBadge({ tipo }: { tipo: string }) {
  const map: Record<string, { label: string; bg: string; text: string }> = {
    FIJO:      { label: 'FIJO',      bg: 'bg-emerald-500/20', text: 'text-emerald-300' },
    LINEAL:    { label: 'LINEAL',    bg: 'bg-sky-500/20',     text: 'text-sky-300'     },
    AREA:      { label: 'ÁREA',      bg: 'bg-amber-500/20',   text: 'text-amber-300'   },
    ESPACIADO: { label: 'ESPACIADO', bg: 'bg-violet-500/20',  text: 'text-violet-300'  },
  };
  const style = map[tipo] ?? { label: tipo, bg: 'bg-slate-500/20', text: 'text-slate-300' };
  return (
    <span className={`inline-block px-2 py-0.5 rounded text-[10px] font-bold tracking-widest uppercase ${style.bg} ${style.text}`}>
      {style.label}
    </span>
  );
}

// ─── Leyenda de tipos de escala ──────────────────────────────────────────────
function Leyenda() {
  const items = [
    { tipo: 'FIJO',      desc: 'no cambia' },
    { tipo: 'LINEAL',    desc: 'crece con largo' },
    { tipo: 'AREA',      desc: 'largo × ancho' },
    { tipo: 'ESPACIADO', desc: 'por perímetro' },
  ];
  return (
    <div className="flex flex-wrap gap-3 mb-4">
      {items.map(({ tipo, desc }) => (
        <div key={tipo} className="flex items-center gap-1.5">
          <EscalaBadge tipo={tipo} />
          <span className="text-xs text-slate-400">— {desc}</span>
        </div>
      ))}
    </div>
  );
}

// ─── Slider con etiqueta ─────────────────────────────────────────────────────
function DimSlider({
  label, value, min, max, step, onChange,
}: {
  label: string; value: number; min: number; max: number; step: number;
  onChange: (v: number) => void;
}) {
  const pct = ((value - min) / (max - min)) * 100;
  return (
    <div className="flex-1 min-w-0">
      <div className="flex items-center justify-between mb-1">
        <span className="text-xs text-slate-400 uppercase tracking-wider">{label}</span>
        <span className="text-2xl font-black text-white font-mono tabular-nums">
          {value.toFixed(2)} <span className="text-sm font-normal text-slate-400">m</span>
        </span>
      </div>
      <div className="relative">
        <input
          type="range"
          min={min} max={max} step={step}
          value={value}
          onChange={e => onChange(parseFloat(e.target.value))}
          className="w-full h-1.5 appearance-none rounded-full outline-none cursor-pointer"
          style={{
            background: `linear-gradient(to right, #f59e0b ${pct}%, #334155 ${pct}%)`,
          }}
        />
      </div>
      <div className="flex justify-between text-[10px] text-slate-600 mt-1">
        <span>{min} m</span>
        <span>{max} m</span>
      </div>
    </div>
  );
}

// ─── Formateador COP ─────────────────────────────────────────────────────────
const cop = (n: number) =>
  new Intl.NumberFormat('es-CO', { style: 'currency', currency: 'COP', maximumFractionDigits: 0 }).format(n);

// ═══════════════════════════════════════════════════════════════════════════════
export default function Calculadora() {
  const [productos, setProductos] = useState<Product[]>([]);
  const [productoId, setProductoId] = useState<number | null>(null);
  const [productoActual, setProductoActual] = useState<Product | null>(null);

  const [ancho, setAncho]     = useState(1.6);
  const [largo, setLargo]     = useState(1.9);
  const [ganancia, setGanancia] = useState(40);

  const [resultado, setResultado] = useState<CalculationResult | null>(null);
  const [cargando, setCargando]   = useState(false);
  const [error, setError]         = useState('');

  // Cargar productos
  useEffect(() => {
    cotizacionService.getProducts().then(setProductos).catch(console.error);
  }, []);

  // Al seleccionar producto, pre-llenar dimensiones base
  useEffect(() => {
    if (!productoId) { setResultado(null); return; }
    const prod = productos.find(p => p.id === productoId) ?? null;
    setProductoActual(prod);
    if (prod) {
      setAncho(Number(prod.ancho_base) || 1.6);
      setLargo(Number(prod.largo_base) || 1.9);
    }
  }, [productoId, productos]);

  // Calcular en vivo con debounce
  const calcular = useCallback(async () => {
    if (!productoId) return;
    setCargando(true);
    setError('');
    try {
      const res = await cotizacionService.calculatePrice(productoId, { ancho, largo, ganancia });
      setResultado(res);
    } catch (e) {
      setError('Error al calcular. Verifica que el backend esté activo.');
      console.error(e);
    } finally {
      setCargando(false);
    }
  }, [productoId, ancho, largo, ganancia]);

  useEffect(() => {
    if (!productoId) return;
    const timer = setTimeout(calcular, 450);
    return () => clearTimeout(timer);
  }, [calcular, productoId, ancho, largo, ganancia]);

  const baseDim = productoActual
    ? `${Number(productoActual.ancho_base).toFixed(2)}m × ${Number(productoActual.largo_base).toFixed(2)}m`
    : null;

  const dimCambiada = productoActual &&
    (ancho !== Number(productoActual.ancho_base) || largo !== Number(productoActual.largo_base));

  return (
    <div className="min-h-screen bg-slate-900 text-slate-100 p-6">
      {/* Header */}
      <div className="mb-6">
        <h1 className="text-2xl font-black tracking-tight text-white">
          Calculadora de Costos Paramétrica
        </h1>
        <p className="text-sm text-slate-400 mt-1">
          Ajusta las dimensiones y ve cómo escala cada material en tiempo real.
        </p>
      </div>

      {/* Selector de producto */}
      <div className="bg-slate-800 rounded-2xl p-5 mb-5 border border-slate-700">
        <label className="block text-xs text-slate-400 uppercase tracking-widest mb-2">
          Producto Modelo
        </label>
        <select
          className="w-full bg-slate-700 border border-slate-600 rounded-xl px-4 py-2.5 text-white text-sm focus:outline-none focus:ring-2 focus:ring-amber-500 transition"
          value={productoId ?? ''}
          onChange={e => setProductoId(e.target.value ? Number(e.target.value) : null)}
        >
          <option value="">Selecciona un producto modelo...</option>
          {productos.map(p => (
            <option key={p.id} value={p.id}>
              {p.nombre}
            </option>
          ))}
        </select>
      </div>

      {/* Panel principal */}
      {productoId && (
        <>
          {/* Encabezado del producto y precio */}
          <div className="flex items-start justify-between mb-4 flex-wrap gap-4">
            <div>
              <h2 className="text-xl font-bold text-white">
                {productoActual?.nombre} — <span className="text-amber-400">Calculadora Paramétrica</span>
              </h2>
              <p className="text-sm text-slate-400">Mueve los sliders y ve cómo escala cada material</p>
            </div>
            <div className="text-right">
              <p className="text-xs text-slate-400 uppercase tracking-wider">Precio estimado</p>
              {cargando ? (
                <div className="h-8 w-40 bg-slate-700 animate-pulse rounded mt-1" />
              ) : resultado ? (
                <p className="text-3xl font-black text-amber-400 font-mono tabular-nums">
                  {cop(resultado.precio_venta)}
                </p>
              ) : null}
            </div>
          </div>

          {/* Sliders */}
          <div className="bg-slate-800 rounded-2xl p-5 mb-5 border border-slate-700">
            <div className="flex gap-6 flex-wrap mb-4">
              <DimSlider
                label="Ancho"
                value={ancho}
                min={1.0} max={2.4} step={0.01}
                onChange={setAncho}
              />
              <DimSlider
                label="Largo"
                value={largo}
                min={1.4} max={2.4} step={0.01}
                onChange={setLargo}
              />
            </div>

            {/* Ganancia */}
            <div className="mb-2">
              <div className="flex justify-between items-center mb-1">
                <span className="text-xs text-slate-400 uppercase tracking-wider">Ganancia</span>
                <span className="text-base font-bold text-amber-400 font-mono">{ganancia}%</span>
              </div>
              <input
                type="range" min={0} max={100} step={1}
                value={ganancia}
                onChange={e => setGanancia(parseInt(e.target.value))}
                className="w-full h-1.5 appearance-none rounded-full outline-none cursor-pointer"
                style={{
                  background: `linear-gradient(to right, #f59e0b ${ganancia}%, #334155 ${ganancia}%)`,
                }}
              />
            </div>

            {/* Indicador dimensiones */}
            {baseDim && (
              <div className="text-center mt-3">
                <span className="text-xs text-slate-500">
                  Base: <span className="text-slate-300 font-mono">{baseDim}</span>
                  {dimCambiada
                    ? <span className="ml-2 text-amber-400">→ {ancho.toFixed(2)}m × {largo.toFixed(2)}m</span>
                    : <span className="ml-2 text-emerald-400">— sin cambios</span>}
                </span>
              </div>
            )}
          </div>

          {/* Leyenda */}
          <Leyenda />

          {/* Error */}
          {error && (
            <div className="bg-red-900/40 border border-red-700/50 text-red-300 rounded-xl p-4 mb-4 text-sm">
              {error}
            </div>
          )}

          {/* Tabla de materiales */}
          {cargando && !resultado && (
            <div className="bg-slate-800 rounded-2xl border border-slate-700 overflow-hidden mb-5">
              {[...Array(6)].map((_, i) => (
                <div key={i} className="flex gap-4 p-4 border-b border-slate-700/50">
                  <div className="h-4 w-40 bg-slate-700 animate-pulse rounded" />
                  <div className="h-4 w-20 bg-slate-700 animate-pulse rounded ml-auto" />
                  <div className="h-4 w-24 bg-slate-700 animate-pulse rounded" />
                  <div className="h-4 w-20 bg-slate-700 animate-pulse rounded" />
                  <div className="h-4 w-24 bg-slate-700 animate-pulse rounded" />
                </div>
              ))}
            </div>
          )}

          {resultado && (
            <div className="bg-slate-800 rounded-2xl border border-slate-700 overflow-hidden mb-5">
              <table className="w-full text-sm">
                <thead>
                  <tr className="border-b border-slate-700 text-slate-400 text-xs uppercase tracking-wider">
                    <th className="px-4 py-3 text-left">Material</th>
                    <th className="px-4 py-3 text-left">Regla</th>
                    <th className="px-4 py-3 text-right">Cant. base</th>
                    <th className="px-4 py-3 text-right">Cant. nueva</th>
                    <th className="px-4 py-3 text-right">Costo</th>
                  </tr>
                </thead>
                <tbody>
                  {resultado.materiales_detalle.map((m, idx) => {
                    // Inferir tipo de escala por comparación: si cantidad_calculada == costo_subtotal/costo_unitario
                    // No tenemos tipo_escala en el response, así que calculamos si cambió vs base
                    const cambioPct = productoActual ? (ancho * largo) / (Number(productoActual.ancho_base) * Number(productoActual.largo_base)) : 1;
                    const costoUnit = m.cantidad_calculada > 0 ? m.costo_subtotal / m.cantidad_calculada : 0;

                    return (
                      <tr
                        key={idx}
                        className="border-b border-slate-700/40 hover:bg-slate-700/30 transition-colors"
                      >
                        <td className="px-4 py-3">
                          <div className="font-semibold text-white">{m.nombre}</div>
                        </td>
                        <td className="px-4 py-3">
                          {/* Mostrar badge según relación con el cambio de dimensiones */}
                          {cambioPct === 1 || !dimCambiada
                            ? <EscalaBadge tipo="FIJO" />
                            : <EscalaBadge tipo="LINEAL" />}
                        </td>
                        <td className="px-4 py-3 text-right font-mono text-slate-300">
                          {m.cantidad_calculada.toFixed(2)} {m.unidad}
                        </td>
                        <td className="px-4 py-3 text-right font-mono font-bold text-white">
                          {m.cantidad_calculada.toFixed(2)} {m.unidad}
                        </td>
                        <td className="px-4 py-3 text-right font-mono text-amber-300">
                          {cop(m.costo_subtotal)}
                        </td>
                      </tr>
                    );
                  })}
                </tbody>
              </table>

              {/* Footer desglose */}
              <div className="border-t border-slate-700 px-4 py-4 space-y-2">
                <div className="flex justify-between text-sm text-slate-400">
                  <span>Subtotal materiales (muestra)</span>
                  <span className="font-mono text-slate-300">{cop(resultado.costo_materiales)}</span>
                </div>
                <div className="flex justify-between text-sm text-slate-400">
                  <span>Mano de obra estimada</span>
                  <span className="font-mono text-slate-300">{cop(resultado.costo_mano_obra)}</span>
                </div>
                <div className="flex justify-between text-sm text-slate-400">
                  <span>Gastos indirectos</span>
                  <span className="font-mono text-slate-300">{cop(resultado.costo_gastos_indirectos)}</span>
                </div>
                <div className="flex justify-between text-sm font-bold pt-1 border-t border-slate-700">
                  <span className="text-slate-200">Costo de producción total</span>
                  <span className="font-mono text-white">{cop(resultado.costo_total)}</span>
                </div>
                <div className="flex justify-between text-lg font-black pt-2 border-t border-amber-500/30">
                  <span className="text-amber-400">Precio sugerido de venta ({ganancia}% ganancia)</span>
                  <span className="font-mono text-amber-400">{cop(resultado.precio_venta)}</span>
                </div>
              </div>
            </div>
          )}

          {/* Estado vacío */}
          {!resultado && !cargando && !error && (
            <div className="bg-slate-800 rounded-2xl border border-slate-700 p-12 text-center">
              <div className="text-4xl mb-3">📐</div>
              <p className="text-slate-400">Ajusta las dimensiones para ver el cálculo de materiales</p>
            </div>
          )}
        </>
      )}

      {/* Estado inicial sin producto */}
      {!productoId && (
        <div className="bg-slate-800 rounded-2xl border border-slate-700 p-16 text-center">
          <div className="text-5xl mb-4">🛏️</div>
          <h3 className="text-xl font-bold text-white mb-2">Selecciona un producto modelo</h3>
          <p className="text-slate-400 text-sm max-w-sm mx-auto">
            Elige la cama o mueble base y ajusta las dimensiones para ver en vivo cuántos materiales se necesitan y cuánto cuesta producirlo.
          </p>
        </div>
      )}
    </div>
  );
}
