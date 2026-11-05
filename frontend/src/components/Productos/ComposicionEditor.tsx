import { useCallback, useEffect, useMemo, useRef, useState } from 'react';
import { AlertTriangle, Layers, Loader2, Plus, Save, Trash2, Wand2, X } from 'lucide-react';
import SearchSelect, { SearchSelectOption } from '../ui/SearchSelect';
import {
  productosService,
  type ComposicionProducto,
  type Product,
} from '../../services/productosService';
import { formatCurrency } from '../../utils/format';

/** Fila editable de la composición. Costo/precio son los del producto pieza. */
interface FilaPieza {
  pieza_producto_id: number;
  nombre: string;
  cantidad: string;
  costo: string;
  precio: string;
  moneda_id: number | null;
  costoOriginal: number | null;
  precioOriginal: number | null;
}

interface Props {
  producto: Product;
  esAdmin: boolean;
  onChanged?: (producto: Product) => void;
}

const numero = (v: string): number | null => {
  if (v.trim() === '') return null;
  const n = Number(v);
  return Number.isFinite(n) ? n : null;
};

export default function ComposicionEditor({ producto, esAdmin, onChanged }: Props) {
  const [cargando, setCargando] = useState(true);
  const [filas, setFilas] = useState<FilaPieza[]>([]);
  const [guardando, setGuardando] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [exito, setExito] = useState<string | null>(null);

  const [nuevaPiezaId, setNuevaPiezaId] = useState<number | null>(null);
  const [nuevaPiezaOpcion, setNuevaPiezaOpcion] = useState<SearchSelectOption | undefined>();
  const [nuevaCantidad, setNuevaCantidad] = useState('1');
  const opcionesRef = useRef<Map<number, string>>(new Map());

  const [creandoPieza, setCreandoPieza] = useState(false);
  const [nuevoNombre, setNuevoNombre] = useState('');
  const [nuevoCosto, setNuevoCosto] = useState('');
  const [nuevoPrecio, setNuevoPrecio] = useState('');

  const monedaCodigo = producto.moneda?.codigo ?? 'COP';

  const cargar = useCallback(async () => {
    setCargando(true);
    setError(null);
    try {
      const data: ComposicionProducto = await productosService.getComposicion(producto.id);
      setFilas(data.piezas.map((p) => ({
        pieza_producto_id: p.pieza_producto_id,
        nombre: p.pieza?.nombre ?? `Producto #${p.pieza_producto_id}`,
        cantidad: String(p.cantidad),
        costo: p.pieza?.precio_costo_base != null ? String(p.pieza.precio_costo_base) : '',
        precio: p.pieza?.precio_venta_base != null ? String(p.pieza.precio_venta_base) : '',
        moneda_id: p.pieza?.moneda_id ?? null,
        costoOriginal: p.pieza?.precio_costo_base ?? null,
        precioOriginal: p.pieza?.precio_venta_base ?? null,
      })));
    } catch (e) {
      setError('No se pudo cargar la composición del conjunto.');
      console.error(e);
    } finally {
      setCargando(false);
    }
  }, [producto.id]);

  useEffect(() => { void cargar(); }, [cargar]);

  const buscarPiezas = useCallback(async (query: string): Promise<SearchSelectOption[]> => {
    const encontrados = await productosService.getProductos(query, { limite: 20 });
    const opciones = encontrados
      .filter((p) => p.id !== producto.id && !p.es_conjunto)
      .map((p) => ({ value: p.id, label: p.nombre }));
    opcionesRef.current = new Map(opciones.map((o) => [Number(o.value), o.label]));
    return opciones;
  }, [producto.id]);

  const resumen = useMemo(() => {
    let costo = 0;
    let precio = 0;
    let sinCosto = 0;
    let sinPrecio = 0;
    let monedasDistintas = false;
    for (const f of filas) {
      const cantidad = numero(f.cantidad) ?? 0;
      const c = numero(f.costo);
      const p = numero(f.precio);
      if (c == null) sinCosto += 1; else costo += cantidad * c;
      if (p == null) sinPrecio += 1; else precio += cantidad * p;
      if ((f.moneda_id ?? 1) !== (producto.moneda_id ?? 1)) monedasDistintas = true;
    }
    return { costo, precio, sinCosto, sinPrecio, monedasDistintas };
  }, [filas, producto.moneda_id]);

  const actualizarFila = (id: number, cambios: Partial<FilaPieza>) => {
    setFilas((prev) => prev.map((f) => (f.pieza_producto_id === id ? { ...f, ...cambios } : f)));
    setExito(null);
  };

  const agregarPieza = async () => {
    if (nuevaPiezaId == null) return;
    const id = nuevaPiezaId;
    if (filas.some((f) => f.pieza_producto_id === id)) {
      setError('Esa pieza ya está en la composición.');
      return;
    }
    setError(null);
    // Se trae la ficha de la pieza para prellenar su costo y su precio reales
    // (viven en el producto, no en la composición).
    let pieza: Product | null = null;
    try {
      pieza = await productosService.getById(id);
    } catch (e) {
      console.error(e);
    }
    setFilas((prev) => [...prev, {
      pieza_producto_id: id,
      nombre: pieza?.nombre ?? nuevaPiezaOpcion?.label ?? `Producto #${id}`,
      cantidad: nuevaCantidad || '1',
      costo: pieza?.precio_costo_base != null ? String(pieza.precio_costo_base) : '',
      precio: pieza?.precio_venta_base != null ? String(pieza.precio_venta_base) : '',
      moneda_id: pieza?.moneda_id ?? producto.moneda_id ?? 1,
      costoOriginal: pieza?.precio_costo_base ?? null,
      precioOriginal: pieza?.precio_venta_base ?? null,
    }]);
    setNuevaPiezaId(null);
    setNuevaPiezaOpcion(undefined);
    setNuevaCantidad('1');
    setExito(null);
  };

  const crearPiezaNueva = async () => {
    if (!nuevoNombre.trim()) {
      setError('Ponle un nombre a la pieza nueva (ej. "Mesa Comedor A").');
      return;
    }
    setGuardando(true);
    setError(null);
    try {
      const creada = await productosService.crearProducto({
        nombre: nuevoNombre.trim(),
        tipo_producto_id: producto.tipo_producto_id,
        moneda_id: producto.moneda_id ?? 1,
        es_pieza: true,
        es_reventa: false,
        es_exhibicion: false,
        activo: true,
        precio_costo_base: numero(nuevoCosto),
        precio_venta_base: numero(nuevoPrecio),
      });
      setFilas((prev) => [...prev, {
        pieza_producto_id: creada.id,
        nombre: creada.nombre,
        cantidad: '1',
        costo: nuevoCosto,
        precio: nuevoPrecio,
        moneda_id: creada.moneda_id ?? 1,
        costoOriginal: creada.precio_costo_base ?? null,
        precioOriginal: creada.precio_venta_base ?? null,
      }]);
      setCreandoPieza(false);
      setNuevoNombre('');
      setNuevoCosto('');
      setNuevoPrecio('');
    } catch (e) {
      setError('No se pudo crear la pieza. Revisa los datos e intenta de nuevo.');
      console.error(e);
    } finally {
      setGuardando(false);
    }
  };

  const guardar = async () => {
    for (const f of filas) {
      const cantidad = numero(f.cantidad);
      if (cantidad == null || cantidad <= 0) {
        setError(`La cantidad de "${f.nombre}" debe ser mayor que cero.`);
        return;
      }
    }
    setGuardando(true);
    setError(null);
    setExito(null);
    try {
      // El costo y el precio viven en el producto de la pieza: si cambiaron,
      // se guardan ahí primero y después se guarda la composición.
      for (const f of filas) {
        const costo = numero(f.costo);
        const precio = numero(f.precio);
        if (costo !== f.costoOriginal || precio !== f.precioOriginal) {
          await productosService.actualizarProducto(f.pieza_producto_id, {
            precio_costo_base: costo,
            precio_venta_base: precio,
          });
        }
      }
      await productosService.guardarComposicion(producto.id, filas.map((f, i) => ({
        pieza_producto_id: f.pieza_producto_id,
        cantidad: numero(f.cantidad) ?? 1,
        orden: i,
      })));
      await cargar();
      setExito(filas.length ? 'Composición guardada.' : 'El producto quedó sin piezas (mueble simple).');
      if (onChanged) onChanged(await productosService.getById(producto.id));
    } catch (e) {
      const detalle = (e as { response?: { data?: { detail?: string } } })?.response?.data?.detail;
      setError(detalle ?? 'No se pudo guardar la composición.');
      console.error(e);
    } finally {
      setGuardando(false);
    }
  };

  return (
    <div className="bg-white border border-yeikar-secondary-light/10 rounded-2xl overflow-hidden shadow-sm">
      <div className="p-4 border-b border-yeikar-secondary-light/10 bg-yeikar-tertiary/20">
        <div className="flex items-center gap-2">
          <Layers className="w-4 h-4 text-yeikar-secondary" />
          <h3 className="font-headline font-black text-yeikar-secondary text-sm">Piezas del conjunto</h3>
        </div>
        <p className="text-[11px] text-yeikar-neutral/70 mt-1 leading-snug">
          Un comedor = mesa ×1 + sillas ×6. Cada pieza es un producto con su costo y su precio:
          sirve para armar el conjunto, venderse sola o combinarla con piezas de otros muebles.
        </p>
      </div>

      <div className="p-4 space-y-3">
        {cargando ? (
          <div className="flex items-center gap-2 text-xs text-yeikar-neutral/60 py-3">
            <Loader2 className="w-4 h-4 animate-spin" /> Cargando composición…
          </div>
        ) : (
          <>
            {filas.length === 0 && (
              <p className="text-xs text-yeikar-neutral/60 italic">
                Este mueble todavía no está desglosado en piezas.
              </p>
            )}

            {filas.map((f) => (
              <div key={f.pieza_producto_id} className="border border-yeikar-secondary-light/15 rounded-xl p-2.5 space-y-2">
                <div className="flex items-start justify-between gap-2">
                  <span className="text-xs font-bold text-yeikar-secondary leading-tight">{f.nombre}</span>
                  {esAdmin && (
                    <button
                      type="button"
                      onClick={() => setFilas((prev) => prev.filter((x) => x.pieza_producto_id !== f.pieza_producto_id))}
                      className="text-yeikar-neutral/40 hover:text-red-500 transition-colors"
                      title="Quitar la pieza del conjunto"
                    >
                      <Trash2 className="w-3.5 h-3.5" />
                    </button>
                  )}
                </div>
                <div className="grid grid-cols-3 gap-2">
                  <label className="block">
                    <span className="text-[10px] font-mono text-yeikar-neutral/60">Cant.</span>
                    <input
                      type="number" min="0" step="any" value={f.cantidad} disabled={!esAdmin}
                      onChange={(e) => actualizarFila(f.pieza_producto_id, { cantidad: e.target.value })}
                      className="w-full mt-0.5 px-2 py-1 text-xs border border-yeikar-secondary-light/20 rounded-lg disabled:bg-yeikar-tertiary/20"
                    />
                  </label>
                  <label className="block">
                    <span className="text-[10px] font-mono text-yeikar-neutral/60">Costo</span>
                    <input
                      type="number" min="0" step="any" value={f.costo} disabled={!esAdmin}
                      onChange={(e) => actualizarFila(f.pieza_producto_id, { costo: e.target.value })}
                      className="w-full mt-0.5 px-2 py-1 text-xs border border-yeikar-secondary-light/20 rounded-lg disabled:bg-yeikar-tertiary/20"
                    />
                  </label>
                  <label className="block">
                    <span className="text-[10px] font-mono text-yeikar-neutral/60">Precio</span>
                    <div className="flex items-center gap-1">
                      <input
                        type="number" min="0" step="any" value={f.precio} disabled={!esAdmin}
                        onChange={(e) => actualizarFila(f.pieza_producto_id, { precio: e.target.value })}
                        className="w-full mt-0.5 px-2 py-1 text-xs border border-yeikar-secondary-light/20 rounded-lg disabled:bg-yeikar-tertiary/20"
                      />
                      {esAdmin && (
                        <button
                          type="button"
                          title="Sugerir precio = costo + 40 % (queda editable)"
                          onClick={() => {
                            const c = numero(f.costo);
                            if (c != null) actualizarFila(f.pieza_producto_id, { precio: String(Math.round(c * 1.4 * 100) / 100) });
                          }}
                          className="mt-0.5 p-1 text-yeikar-secondary hover:bg-yeikar-tertiary/40 rounded-lg"
                        >
                          <Wand2 className="w-3.5 h-3.5" />
                        </button>
                      )}
                    </div>
                  </label>
                </div>
              </div>
            ))}

            {filas.length > 0 && (
              <div className="bg-yeikar-tertiary/30 rounded-xl p-3 text-[11px] space-y-1">
                <div className="flex justify-between">
                  <span className="text-yeikar-neutral/70">Suma de las piezas (costo)</span>
                  <span className="font-mono font-bold">{formatCurrency(resumen.costo, monedaCodigo)}</span>
                </div>
                <div className="flex justify-between">
                  <span className="text-yeikar-neutral/70">Suma de las piezas (precio)</span>
                  <span className="font-mono font-bold">{formatCurrency(resumen.precio, monedaCodigo)}</span>
                </div>
                {producto.precio_venta_base != null && (
                  <div className="flex justify-between border-t border-yeikar-secondary-light/10 pt-1">
                    <span className="text-yeikar-neutral/70">Precio del conjunto</span>
                    <span className="font-mono font-bold">{formatCurrency(producto.precio_venta_base, monedaCodigo)}</span>
                  </div>
                )}
                {producto.precio_venta_base != null && Math.abs(producto.precio_venta_base - resumen.precio) > 0.01 && (
                  <p className="text-yeikar-secondary/80 leading-snug">
                    Diferencia de {formatCurrency(producto.precio_venta_base - resumen.precio, monedaCodigo)} entre
                    el precio del conjunto y la suma de sus piezas. No se corrige sola: puede ser el precio de combo.
                  </p>
                )}
                {(resumen.sinCosto > 0 || resumen.sinPrecio > 0) && (
                  <p className="text-amber-700 flex items-start gap-1">
                    <AlertTriangle className="w-3.5 h-3.5 shrink-0 mt-0.5" />
                    <span>
                      {resumen.sinCosto > 0 && `${resumen.sinCosto} pieza(s) sin costo. `}
                      {resumen.sinPrecio > 0 && `${resumen.sinPrecio} pieza(s) sin precio.`}
                    </span>
                  </p>
                )}
                {resumen.monedasDistintas && (
                  <p className="text-amber-700 flex items-start gap-1">
                    <AlertTriangle className="w-3.5 h-3.5 shrink-0 mt-0.5" />
                    <span>Hay piezas en otra moneda: la suma mezcla monedas.</span>
                  </p>
                )}
              </div>
            )}

            {esAdmin && (
              <>
                <div className="flex items-end gap-2">
                  <div className="flex-1">
                    <SearchSelect
                      value={nuevaPiezaId}
                      onChange={(v) => {
                        const id = Number(v);
                        setNuevaPiezaId(id);
                        setNuevaPiezaOpcion({ value: id, label: opcionesRef.current.get(id) ?? `Producto #${id}` });
                      }}
                      loadOptions={buscarPiezas}
                      selectedOption={nuevaPiezaOpcion}
                      placeholder="Agregar pieza del catálogo…"
                      searchPlaceholder="Buscar producto…"
                    />
                  </div>
                  <input
                    type="number" min="0" step="any" value={nuevaCantidad}
                    onChange={(e) => setNuevaCantidad(e.target.value)}
                    className="w-16 px-2 py-2 text-xs border border-yeikar-secondary-light/20 rounded-lg"
                    title="Cantidad por conjunto"
                  />
                  <button
                    type="button" onClick={() => void agregarPieza()} disabled={nuevaPiezaId == null}
                    className="p-2 bg-yeikar-secondary text-white rounded-lg disabled:opacity-40"
                    title="Agregar la pieza"
                  >
                    <Plus className="w-4 h-4" />
                  </button>
                </div>

                {creandoPieza ? (
                  <div className="border border-dashed border-yeikar-secondary-light/30 rounded-xl p-3 space-y-2">
                    <div className="flex items-center justify-between">
                      <span className="text-xs font-bold text-yeikar-secondary">Pieza nueva</span>
                      <button type="button" onClick={() => setCreandoPieza(false)} className="text-yeikar-neutral/50">
                        <X className="w-3.5 h-3.5" />
                      </button>
                    </div>
                    <input
                      type="text" value={nuevoNombre} onChange={(e) => setNuevoNombre(e.target.value)}
                      placeholder={`Mesa ${producto.nombre}`}
                      className="w-full px-2 py-1.5 text-xs border border-yeikar-secondary-light/20 rounded-lg"
                    />
                    <div className="grid grid-cols-2 gap-2">
                      <input
                        type="number" min="0" step="any" value={nuevoCosto} onChange={(e) => setNuevoCosto(e.target.value)}
                        placeholder="Costo"
                        className="w-full px-2 py-1.5 text-xs border border-yeikar-secondary-light/20 rounded-lg"
                      />
                      <input
                        type="number" min="0" step="any" value={nuevoPrecio} onChange={(e) => setNuevoPrecio(e.target.value)}
                        placeholder="Precio de venta"
                        className="w-full px-2 py-1.5 text-xs border border-yeikar-secondary-light/20 rounded-lg"
                      />
                    </div>
                    <button
                      type="button"
                      onClick={() => {
                        const c = numero(nuevoCosto);
                        if (c != null) setNuevoPrecio(String(Math.round(c * 1.4 * 100) / 100));
                      }}
                      className="text-[11px] text-yeikar-secondary underline"
                    >
                      Sugerir precio = costo + 40 %
                    </button>
                    <button
                      type="button" onClick={() => void crearPiezaNueva()} disabled={guardando}
                      className="w-full py-1.5 text-xs font-bold bg-yeikar-secondary text-white rounded-lg disabled:opacity-50"
                    >
                      Crear y agregar al conjunto
                    </button>
                  </div>
                ) : (
                  <button
                    type="button" onClick={() => setCreandoPieza(true)}
                    className="text-[11px] text-yeikar-secondary underline"
                  >
                    + Crear una pieza nueva (no está en el catálogo)
                  </button>
                )}

                <button
                  type="button" onClick={() => void guardar()} disabled={guardando}
                  className="w-full flex items-center justify-center gap-2 py-2 bg-yeikar-primary text-yeikar-secondary font-headline font-black text-xs rounded-xl disabled:opacity-50"
                >
                  {guardando ? <Loader2 className="w-4 h-4 animate-spin" /> : <Save className="w-4 h-4" />}
                  Guardar composición
                </button>
              </>
            )}

            {error && <p className="text-[11px] text-red-600 leading-snug">{error}</p>}
            {exito && <p className="text-[11px] text-green-700 leading-snug">{exito}</p>}
          </>
        )}
      </div>
    </div>
  );
}
