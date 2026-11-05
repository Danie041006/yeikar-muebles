import { useEffect, useMemo, useRef, useState } from 'react';
import { Camera, Layers, Loader2, Plus, Store, Trash2, X } from 'lucide-react';
import SearchSelect, { type SearchSelectOption } from '../ui/SearchSelect';
import MontoInput from '../ui/MontoInput';
import { productosService, type ProductoPieza } from '../../services/productosService';
import { formatCurrency } from '../../utils/format';

/** Mínimo que el editor necesita de un producto del catálogo.
 *
 *  Hay dos tipos `Product` en el frontend (cotizaciones y productos) con
 *  campos opcionales distintos; este contrato estructural acepta ambos.
 */
export interface ProductoCatalogo {
  id: number;
  nombre: string;
  codigo?: string | null;
  es_conjunto?: boolean;
  es_pieza?: boolean;
  es_exhibicion?: boolean;
  moneda?: { codigo?: string | null } | null;
  precio_venta_base?: number | null;
  precio_costo_base?: number | null;
}

/** Pieza declarada de un renglón-juego.
 *
 *  Sin los campos comerciales es una pieza clásica (solo producción interna
 *  con precio global del renglón). Con `producto_id` + `precio` es una pieza
 *  de la composición: el precio del renglón se calcula sumando sus piezas.
 */
export interface PiezaJuegoForm {
  nombre: string;
  /** Cantidad por UNIDAD del renglón (por juego): 6 sillas por comedor. */
  cantidad: number;
  notas: string;
  /** Foto opcional de la pieza, ya comprimida como data URL. */
  foto?: string | null;
  /** Producto del catálogo que ES la pieza. */
  producto_id?: number | null;
  /** Precio unitario en la moneda de la cotización. */
  precio?: number | null;
  /** FABRICADO (se produce) o EXHIBICION (se toma del showroom). */
  origen?: 'FABRICADO' | 'EXHIBICION';
  /** Conjunto de exhibición del que se despieza la pieza. */
  conjunto_origen_id?: number | null;
  modificacion?: string;
  requiere_retrabajo?: boolean;
  precio_modificacion?: number | null;
}

export const MAX_PIEZAS_JUEGO = 50;

const MAX_FOTO_LADO = 900;

/** True si alguna pieza usa la composición comercial (producto/precio/origen). */
export function composicionActiva(piezas: PiezaJuegoForm[]): boolean {
  return (piezas ?? []).some(
    (p) =>
      p.producto_id != null ||
      p.precio != null ||
      p.conjunto_origen_id != null ||
      p.requiere_retrabajo === true,
  );
}

/** Total de UNA unidad del renglón en la moneda de la cotización.
 *
 *  Devuelve null si no todas las piezas tienen precio: en ese caso el renglón
 *  conserva su precio global manual (juego clásico).
 */
export function totalPiezasEnMoneda(piezas: PiezaJuegoForm[]): number | null {
  if (!piezas?.length) return null;
  if (piezas.some((p) => p.precio == null || !Number.isFinite(Number(p.precio)))) {
    return null;
  }
  const total = piezas.reduce((suma, p) => {
    const cantidad = Number(p.cantidad) || 0;
    const precio = Number(p.precio) || 0;
    const modificacion = p.requiere_retrabajo ? Number(p.precio_modificacion) || 0 : 0;
    return suma + cantidad * (precio + modificacion);
  }, 0);
  return Math.round(total * 100) / 100;
}

/** Reduce la foto en el navegador para que el data URL no infle la cotización. */
async function comprimirFotoPieza(file: File): Promise<string | null> {
  if (!file.type.startsWith('image/')) return null;
  try {
    const bitmap = await createImageBitmap(file);
    const escala = Math.min(1, MAX_FOTO_LADO / Math.max(bitmap.width, bitmap.height));
    const ancho = Math.max(1, Math.round(bitmap.width * escala));
    const alto = Math.max(1, Math.round(bitmap.height * escala));
    const canvas = document.createElement('canvas');
    canvas.width = ancho;
    canvas.height = alto;
    const ctx = canvas.getContext('2d');
    if (!ctx) return null;
    // Fondo blanco: si la imagen trae transparencia (PNG), el JPEG no la
    // convierte en negro.
    ctx.fillStyle = '#ffffff';
    ctx.fillRect(0, 0, ancho, alto);
    ctx.drawImage(bitmap, 0, 0, ancho, alto);
    bitmap.close();
    return canvas.toDataURL('image/jpeg', 0.78);
  } catch {
    return null;
  }
}

const normalizarNombre = (nombre: string): string =>
  nombre
    .normalize('NFD')
    .replace(/[\u0300-\u036f]/g, '')
    .trim()
    .toUpperCase();

/** Devuelve el primer error de la lista, o null si las piezas son válidas. */
export function validarPiezasJuego(piezas: PiezaJuegoForm[]): string | null {
  if (piezas.length > MAX_PIEZAS_JUEGO) {
    return `Un renglón no puede tener más de ${MAX_PIEZAS_JUEGO} piezas.`;
  }
  const vistas = new Set<string>();
  for (const pieza of piezas) {
    const nombre = pieza.nombre.trim();
    if (!nombre) return 'Cada pieza del juego debe tener un nombre.';
    if (!(Number(pieza.cantidad) > 0)) {
      return `La cantidad de "${nombre}" debe ser mayor que cero.`;
    }
    const clave = normalizarNombre(nombre);
    if (vistas.has(clave)) return `La pieza "${nombre}" está repetida en el juego.`;
    vistas.add(clave);
    if (pieza.origen === 'EXHIBICION' && !pieza.producto_id) {
      return `La pieza "${nombre}" es de exhibición: indica el producto del catálogo.`;
    }
    if (pieza.conjunto_origen_id && pieza.origen !== 'EXHIBICION') {
      return `El conjunto de origen solo aplica a piezas de exhibición ("${nombre}").`;
    }
    if (pieza.requiere_retrabajo) {
      if (!pieza.producto_id) {
        return `La pieza "${nombre}" requiere retrabajo: indica el producto del catálogo.`;
      }
      if (!pieza.modificacion?.trim()) {
        return `La pieza "${nombre}" requiere retrabajo: describe la modificación.`;
      }
    } else if (pieza.precio_modificacion != null) {
      return `La pieza "${nombre}" tiene precio de modificación sin requerir retrabajo.`;
    }
  }

  const comercial = composicionActiva(piezas);
  if (comercial) {
    const sinProducto = piezas.find((p) => !p.producto_id);
    if (sinProducto) {
      return `La pieza "${sinProducto.nombre}" debe tener un producto del catálogo.`;
    }
    const conPrecio = piezas.filter((p) => p.precio != null);
    if (conPrecio.length !== piezas.length) {
      const faltan = piezas.filter((p) => p.precio == null).map((p) => p.nombre);
      return `Las piezas deben tener TODAS precio o NINGUNA. Falta: ${faltan.join(', ')}.`;
    }
  }
  return null;
}

interface Props {
  piezas: PiezaJuegoForm[];
  onChange: (piezas: PiezaJuegoForm[]) => void;
  disabled?: boolean;
  /** Catálogo para elegir el producto de cada pieza. */
  productos?: ProductoCatalogo[];
  /** Precio sugerido en la moneda de la cotización (catálogo → moneda). */
  precioSugerido?: (producto: ProductoCatalogo) => number | null;
  monedaCodigo?: string;
}

/** Input de cantidad de una pieza.
 *
 *  Un <input type="number"> controlado con min/step hace que el navegador
 *  considere válidos solo 0.01, 1.01, 2.01… y BLOQUEE el submit del formulario
 *  con "los dos valores válidos más cercanos son…" aunque la cantidad sea 1.
 *  Además, al borrar el campo el estado numérico vuelve a 0 y no deja teclear.
 *  Este input guarda el TEXTO mientras el usuario escribe y solo publica
 *  números válidos (> 0) al formulario (mismo patrón que CantidadDecimalInput
 *  de Cotizaciones.tsx). */
function CantidadPiezaInput({
  value,
  onChange,
  disabled = false,
  ariaLabel,
  className,
}: {
  value: number;
  onChange: (n: number) => void;
  disabled?: boolean;
  ariaLabel: string;
  className?: string;
}) {
  const [texto, setTexto] = useState(() => (value ? String(value) : ''));
  const enfocado = useRef(false);

  useEffect(() => {
    if (!enfocado.current) setTexto(value ? String(value) : '');
  }, [value]);

  const normalizar = (t: string): number | null => {
    const n = Number(t.replace(',', '.'));
    return Number.isFinite(n) && n > 0 ? n : null;
  };

  return (
    <input
      type="text"
      inputMode="decimal"
      value={texto}
      onFocus={() => { enfocado.current = true; }}
      onChange={(e) => {
        const t = e.target.value;
        setTexto(t);
        const n = normalizar(t);
        if (n !== null) onChange(n);
      }}
      onBlur={() => {
        enfocado.current = false;
        const n = normalizar(texto);
        if (n !== null) {
          onChange(n);
          setTexto(String(n));
        } else {
          setTexto(value ? String(value) : '');
        }
      }}
      disabled={disabled}
      aria-label={ariaLabel}
      className={className}
    />
  );
}

/**
 * Editor compacto de las piezas de un juego.
 *
 * Dos modos:
 *  - Clásico (por defecto): solo nombres/cantidades/fotos; el renglón conserva
 *    su precio global y cada pieza genera su orden interna.
 *  - Composición: cada pieza apunta a un producto del catálogo, lleva su
 *    precio y puede salir del showroom (`EXHIBICION`) o requerir retrabajo.
 *    El precio del renglón es la suma de las piezas.
 */
export default function PiezasJuegoEditor({
  piezas,
  onChange,
  disabled = false,
  productos = [],
  precioSugerido,
  monedaCodigo = 'COP',
}: Props) {
  const [modoComposicion, setModoComposicion] = useState(() => composicionActiva(piezas));
  const [composiciones, setComposiciones] = useState<Record<number, ProductoPieza[]>>({});
  const [cargandoConjunto, setCargandoConjunto] = useState<Record<number, boolean>>({});
  const [errorConjunto, setErrorConjunto] = useState<string | null>(null);
  // Productos traídos por el buscador server-side (el catálogo puede superar
  // la página de 1000 que carga Cotizaciones).
  const [productosExtra, setProductosExtra] = useState<Record<number, ProductoCatalogo>>({});

  const totalUnidades = piezas.reduce(
    (total, pieza) => total + (Number(pieza.cantidad) || 0),
    0,
  );
  const totalMoneda = totalPiezasEnMoneda(piezas);

  // La foto se comprime de forma asíncrona; el ref evita que dos selecciones
  // seguidas se pisen con una lista vieja del render anterior.
  const piezasRef = useRef(piezas);
  useEffect(() => {
    piezasRef.current = piezas;
  }, [piezas]);
  useEffect(() => {
    if (composicionActiva(piezas)) setModoComposicion(true);
  }, [piezas]);

  const productosPorId = useMemo(() => {
    const mapa = new Map<number, ProductoCatalogo>();
    for (const p of productos) mapa.set(p.id, p);
    for (const p of Object.values(productosExtra)) mapa.set(p.id, p);
    return mapa;
  }, [productos, productosExtra]);

  const opcionesConjunto = useMemo<SearchSelectOption[]>(
    () =>
      productos
        .filter((p) => p.es_conjunto || p.es_exhibicion)
        .map((p) => ({
          value: p.id,
          label: p.nombre,
          group: p.es_conjunto ? 'Conjuntos con piezas' : 'Otros muebles de exhibición',
        })),
    [productos],
  );

  const opcionesProductoBase = useMemo<SearchSelectOption[]>(
    () =>
      productos.map((p) => ({
        value: p.id,
        label: p.nombre,
        group: p.es_conjunto ? 'Conjuntos' : p.es_pieza ? 'Piezas' : 'Muebles',
      })),
    [productos],
  );

  const cargarComposicion = async (conjuntoId: number) => {
    if (!conjuntoId || composiciones[conjuntoId] || cargandoConjunto[conjuntoId]) return;
    setCargandoConjunto((prev) => ({ ...prev, [conjuntoId]: true }));
    setErrorConjunto(null);
    try {
      const [data, conjunto] = await Promise.all([
        productosService.getComposicion(conjuntoId),
        productosService.getById(conjuntoId).catch(() => null),
      ]);
      if (conjunto) {
        setProductosExtra((prev) => ({ ...prev, [conjunto.id]: conjunto }));
      }
      setComposiciones((prev) => ({ ...prev, [conjuntoId]: data.piezas }));
    } catch {
      setErrorConjunto(
        'No se pudo leer la composición del conjunto. Revisa que tenga piezas en Productos.',
      );
    } finally {
      setCargandoConjunto((prev) => ({ ...prev, [conjuntoId]: false }));
    }
  };

  // Al editar una cotización guardada, las piezas ya traen su conjunto: se
  // carga su composición para mostrar las piezas disponibles y sus cantidades.
  useEffect(() => {
    const ids = new Set(
      piezas
        .map((p) => p.conjunto_origen_id)
        .filter((id): id is number => typeof id === 'number' && id > 0),
    );
    ids.forEach((id) => { void cargarComposicion(id); });
    // cargarComposicion tiene guardas de caché/en vuelo; solo importan los ids.
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [piezas]);

  const actualizar = (indice: number, cambios: Partial<PiezaJuegoForm>) => {
    const next = piezasRef.current.map((pieza, i) =>
      i === indice ? { ...pieza, ...cambios } : pieza,
    );
    piezasRef.current = next;
    onChange(next);
  };

  const agregar = () => {
    const base = piezasRef.current;
    if (base.length >= MAX_PIEZAS_JUEGO) return;
    const next = [
      ...base,
      {
        nombre: `Pieza ${base.length + 1}`,
        cantidad: 1,
        notas: '',
        foto: null,
        ...(modoComposicion
          ? { producto_id: null, precio: 0, origen: 'FABRICADO' as const }
          : {}),
      },
    ];
    piezasRef.current = next;
    onChange(next);
  };

  const quitar = (indice: number) => {
    const next = piezasRef.current.filter((_, i) => i !== indice);
    piezasRef.current = next;
    onChange(next);
  };

  const alternarModo = () => {
    const activar = !modoComposicion;
    setModoComposicion(activar);
    const next = activar
      ? piezasRef.current.map((p) => ({
          ...p,
          precio: p.precio ?? 0,
          origen: p.origen ?? ('FABRICADO' as const),
        }))
      : piezasRef.current.map((p) => ({
          ...p,
          producto_id: null,
          precio: null,
          origen: 'FABRICADO' as const,
          conjunto_origen_id: null,
          modificacion: '',
          requiere_retrabajo: false,
          precio_modificacion: null,
        }));
    piezasRef.current = next;
    onChange(next);
  };

  const seleccionarProducto = async (indice: number, valor: string | number) => {
    const pieza = piezasRef.current[indice];
    if (!pieza) return;
    let producto = productosPorId.get(Number(valor));
    if (!producto) {
      // El buscador server-side devuelve la opción, pero no el objeto completo
      // (moneda/precio): se pide al catálogo al seleccionarla.
      try {
        producto = await productosService.getById(Number(valor));
        setProductosExtra((prev) => ({ ...prev, [producto!.id]: producto! }));
      } catch {
        producto = undefined;
      }
    }
    if (!producto) return;
    const sugerido = precioSugerido
      ? precioSugerido(producto)
      : producto.precio_venta_base != null
        ? Number(producto.precio_venta_base)
        : null;
    const reemplazarNombre = /^Pieza \d+$/.test(pieza.nombre.trim()) || !pieza.nombre.trim();
    const precioActual = pieza.precio == null ? null : Number(pieza.precio);
    actualizar(indice, {
      producto_id: producto.id,
      precio:
        precioActual == null || precioActual === 0
          ? sugerido != null && Number.isFinite(sugerido)
            ? Math.round(sugerido * 100) / 100
            : 0
          : pieza.precio,
      nombre: reemplazarNombre ? producto.nombre : pieza.nombre,
    });
  };

  const seleccionarConjunto = (indice: number, valor: string | number) => {
    const conjuntoId = Number(valor) || null;
    actualizar(indice, { conjunto_origen_id: conjuntoId });
    if (conjuntoId) void cargarComposicion(conjuntoId);
  };

  const opcionesProductoFila = (pieza: PiezaJuegoForm): SearchSelectOption[] => {
    const conjuntoId = pieza.conjunto_origen_id;
    if (!conjuntoId) return opcionesProductoBase;
    const composicion = composiciones[conjuntoId];
    if (!composicion) return opcionesProductoBase;
    return composicion
      .map((fila) => {
        const producto = productosPorId.get(fila.pieza_producto_id);
        const nombre = producto?.nombre
          ?? fila.pieza?.nombre
          ?? `Producto #${fila.pieza_producto_id}`;
        return { value: fila.pieza_producto_id, label: nombre, group: 'Piezas del conjunto' };
      });
  };

  const nombreProducto = (id?: number | null): string => {
    if (!id) return '';
    return productosPorId.get(id)?.nombre ?? '';
  };

  /** Búsqueda server-side de conjuntos/muebles de exhibición. */
  const buscarConjuntos = async (query: string): Promise<SearchSelectOption[]> => {
    try {
      const data = await productosService.getProductos(query.trim() || undefined, {
        es_exhibicion: true,
        limite: 50,
      });
      setProductosExtra((prev) => {
        const next = { ...prev };
        for (const p of data) next[p.id] = p;
        return next;
      });
      return data
        .filter((p) => p.es_conjunto || p.es_exhibicion)
        .map((p) => ({
          value: p.id,
          label: p.nombre,
          group: p.es_conjunto ? 'Conjuntos con piezas' : 'Muebles de exhibición',
        }));
    } catch {
      return [];
    }
  };

  /** Búsqueda server-side del catálogo completo para el selector de producto. */
  const buscarProductos = async (query: string): Promise<SearchSelectOption[]> => {
    try {
      const data = await productosService.getProductos(query.trim() || undefined, {
        limite: 25,
      });
      setProductosExtra((prev) => {
        const next = { ...prev };
        for (const p of data) next[p.id] = p;
        return next;
      });
      return data.map((p) => ({
        value: p.id,
        label: p.nombre,
        group: p.es_conjunto ? 'Conjuntos' : p.es_pieza ? 'Piezas' : 'Muebles',
      }));
    } catch {
      return [];
    }
  };

  const hintComposicion = (pieza: PiezaJuegoForm): string | null => {
    if (!pieza.conjunto_origen_id) return null;
    const composicion = composiciones[pieza.conjunto_origen_id];
    if (!composicion) {
      return cargandoConjunto[pieza.conjunto_origen_id]
        ? 'Leyendo las piezas del conjunto…'
        : null;
    }
    if (!composicion.length) return 'Este mueble aún no tiene piezas configuradas.';
    const resumen = composicion
      .map((f) => {
        const nombre = f.pieza?.nombre
          || nombreProducto(f.pieza_producto_id)
          || `Producto #${f.pieza_producto_id}`;
        return `${nombre} ×${Number(f.cantidad)}`;
      })
      .join(' · ');
    return `Piezas del conjunto: ${resumen}`;
  };

  const clsInput =
    'w-full rounded-lg border border-stone-200 bg-white px-2 py-1.5 text-xs focus:border-yeikar-primary focus:outline-none focus:ring-1 focus:ring-yeikar-primary disabled:bg-stone-50';

  return (
    <details className="group rounded-xl border border-dashed border-yeikar-secondary-light/25 bg-yeikar-tertiary/20">
      <summary className="flex cursor-pointer select-none items-center gap-2 px-3 py-2 text-[11px] font-bold text-yeikar-secondary/75 hover:text-yeikar-secondary">
        <Layers className="h-3.5 w-3.5 shrink-0 text-yeikar-primary-dark" aria-hidden="true" />
        <span>
          Piezas del juego
          {piezas.length > 0
            ? ` · ${piezas.length} ${piezas.length === 1 ? 'pieza' : 'piezas'} · ${totalUnidades.toLocaleString('es-CO')} und`
            : ' (opcional)'}
        </span>
        {totalMoneda != null && (
          <span className="rounded-full bg-white px-2 py-0.5 font-mono text-[10px] font-bold text-yeikar-secondary">
            {formatCurrency(totalMoneda, monedaCodigo)}
          </span>
        )}
        <span className="ml-auto text-[9px] font-normal text-yeikar-neutral/45">
          {piezas.length > 0 ? 'Editar' : 'Se fabrican y costean por separado'}
        </span>
      </summary>

      <div className="space-y-2 border-t border-yeikar-secondary-light/10 px-3 py-2.5">
        <div className="flex flex-wrap items-center justify-between gap-2">
          <p className="text-[10px] leading-snug text-yeikar-neutral/55">
            {modoComposicion
              ? 'Cada pieza lleva su producto y su precio. El precio del renglón es la suma de sus piezas.'
              : 'El precio es el del renglón completo. Cada pieza genera su propia orden de producción y su costo.'}
          </p>
          <button
            type="button"
            onClick={alternarModo}
            disabled={disabled}
            className={`inline-flex shrink-0 items-center gap-1 rounded-full border px-2.5 py-1 text-[10px] font-bold transition-colors disabled:opacity-50 ${
              modoComposicion
                ? 'border-yeikar-primary/40 bg-yeikar-primary/10 text-yeikar-primary-dark'
                : 'border-stone-200 bg-white text-yeikar-neutral/60 hover:border-yeikar-primary/40'
            }`}
          >
            <Store className="h-3 w-3" aria-hidden="true" />
            {modoComposicion ? 'Composición con precio' : 'Usar precio por pieza'}
          </button>
        </div>

        {errorConjunto && (
          <p className="rounded-lg border border-red-200 bg-red-50 px-2 py-1.5 text-[10px] font-bold text-red-700">
            {errorConjunto}
          </p>
        )}

        {piezas.length === 0 ? (
          <button
            type="button"
            onClick={agregar}
            disabled={disabled}
            className="inline-flex items-center gap-1 rounded-lg border border-yeikar-primary/30 bg-white px-2.5 py-1.5 text-[10px] font-bold text-yeikar-primary-dark hover:bg-yeikar-primary/10 disabled:opacity-50"
          >
            <Plus className="h-3 w-3" aria-hidden="true" />
            Agregar pieza
          </button>
        ) : (
          <>
            <div className="space-y-2">
              {piezas.map((pieza, indice) => {
                const esExhibicion = pieza.origen === 'EXHIBICION';
                const opciones = opcionesProductoFila(pieza);
                const hint = hintComposicion(pieza);
                return (
                  <div
                    key={indice}
                    className="rounded-xl border border-yeikar-secondary-light/15 bg-white/80 p-2"
                  >
                    <div className="flex items-start gap-1.5 sm:grid sm:grid-cols-[44px_minmax(0,1fr)_76px_minmax(0,1fr)_28px] sm:items-center">
                      <div className="relative mt-0.5 shrink-0 sm:mt-0">
                        <label
                          className={`flex h-10 w-10 cursor-pointer items-center justify-center overflow-hidden rounded-lg border transition-colors ${
                            pieza.foto
                              ? 'border-yeikar-primary/40 bg-white'
                              : 'border-dashed border-stone-300 bg-white hover:border-yeikar-primary/50'
                          } ${disabled ? 'cursor-not-allowed opacity-50' : ''}`}
                          title={pieza.foto ? 'Cambiar foto de la pieza' : 'Agregar foto de la pieza (opcional)'}
                        >
                          <input
                            type="file"
                            accept="image/*"
                            className="sr-only"
                            disabled={disabled}
                            aria-label={`Foto de ${pieza.nombre || `la pieza ${indice + 1}`} (opcional)`}
                            onChange={async (e) => {
                              const file = e.target.files?.[0];
                              e.target.value = '';
                              if (!file) return;
                              const foto = await comprimirFotoPieza(file);
                              if (!foto) {
                                window.alert('No se pudo leer la foto. Usa una imagen JPG o PNG.');
                                return;
                              }
                              actualizar(indice, { foto });
                            }}
                          />
                          {pieza.foto ? (
                            <img src={pieza.foto} alt="" className="h-full w-full object-cover" />
                          ) : (
                            <Camera className="h-4 w-4 text-stone-400" aria-hidden="true" />
                          )}
                        </label>
                        {pieza.foto && !disabled && (
                          <button
                            type="button"
                            onClick={() => actualizar(indice, { foto: null })}
                            aria-label={`Quitar foto de ${pieza.nombre || `la pieza ${indice + 1}`}`}
                            title="Quitar foto"
                            className="absolute -right-1.5 -top-1.5 flex h-4 w-4 items-center justify-center rounded-full bg-red-500 text-white shadow-sm hover:bg-red-600"
                          >
                            <X className="h-2.5 w-2.5" aria-hidden="true" />
                          </button>
                        )}
                      </div>

                      <div className="grid flex-1 grid-cols-1 gap-1.5 sm:contents">
                        <input
                          type="text"
                          value={pieza.nombre}
                          onChange={(e) => actualizar(indice, { nombre: e.target.value })}
                          placeholder="Ej: Mesa de comedor"
                          maxLength={150}
                          disabled={disabled}
                          aria-label={`Nombre de la pieza ${indice + 1}`}
                          className={clsInput}
                        />
                        <CantidadPiezaInput
                          value={pieza.cantidad}
                          onChange={(cantidad) => actualizar(indice, { cantidad })}
                          disabled={disabled}
                          ariaLabel={`Cantidad de ${pieza.nombre || `la pieza ${indice + 1}`}`}
                          className={`${clsInput} text-center font-mono`}
                        />
                        <input
                          type="text"
                          value={pieza.notas}
                          onChange={(e) => actualizar(indice, { notas: e.target.value })}
                          placeholder="Nota (opcional)"
                          disabled={disabled}
                          aria-label={`Nota de ${pieza.nombre || `la pieza ${indice + 1}`}`}
                          className={clsInput}
                        />
                        <button
                          type="button"
                          onClick={() => quitar(indice)}
                          disabled={disabled}
                          aria-label={`Quitar ${pieza.nombre || `la pieza ${indice + 1}`}`}
                          title="Quitar pieza"
                          className="justify-self-start rounded-lg p-1.5 text-red-500 hover:bg-red-50 hover:text-red-700 disabled:opacity-40 sm:justify-self-center"
                        >
                          <Trash2 className="h-3.5 w-3.5" aria-hidden="true" />
                        </button>
                      </div>
                    </div>

                    {modoComposicion && (
                      <div className="mt-2 space-y-1.5 border-t border-yeikar-secondary-light/10 pt-2">
                        <div className="grid grid-cols-1 gap-1.5 sm:grid-cols-2">
                          <div>
                            <label className="mb-0.5 block text-[9px] font-bold uppercase tracking-wider text-yeikar-neutral/50">
                              Producto de la pieza
                            </label>
                            <SearchSelect
                              value={pieza.producto_id ?? ''}
                              onChange={(valor) => { void seleccionarProducto(indice, valor); }}
                              options={opciones}
                              loadOptions={
                                pieza.conjunto_origen_id && composiciones[pieza.conjunto_origen_id]
                                  ? undefined
                                  : buscarProductos
                              }
                              selectedOption={
                                pieza.producto_id
                                  ? {
                                      value: pieza.producto_id,
                                      label:
                                        nombreProducto(pieza.producto_id)
                                        || pieza.nombre
                                        || `Producto #${pieza.producto_id}`,
                                    }
                                  : undefined
                              }
                              placeholder="Buscar producto…"
                              searchPlaceholder="Nombre o código…"
                              disabled={disabled}
                            />
                          </div>
                          <div>
                            <label className="mb-0.5 block text-[9px] font-bold uppercase tracking-wider text-yeikar-neutral/50">
                              Precio en {monedaCodigo}
                            </label>
                            <MontoInput
                              min="0"
                              value={pieza.precio ?? ''}
                              onChange={(raw) =>
                                actualizar(indice, {
                                  precio: raw.trim() === '' ? null : Number(raw),
                                })
                              }
                              disabled={disabled}
                              placeholder="0"
                              aria-label={`Precio de ${pieza.nombre || `la pieza ${indice + 1}`}`}
                              className={`${clsInput} font-mono font-bold`}
                            />
                          </div>
                        </div>

                        <div className="grid grid-cols-1 gap-1.5 sm:grid-cols-2">
                          <div>
                            <label className="mb-0.5 block text-[9px] font-bold uppercase tracking-wider text-yeikar-neutral/50">
                              Origen
                            </label>
                            <select
                              value={pieza.origen ?? 'FABRICADO'}
                              onChange={(e) => {
                                const origen = e.target.value as 'FABRICADO' | 'EXHIBICION';
                                actualizar(indice, {
                                  origen,
                                  ...(origen === 'FABRICADO'
                                    ? {
                                        conjunto_origen_id: null,
                                        requiere_retrabajo: false,
                                        modificacion: '',
                                        precio_modificacion: null,
                                      }
                                    : {}),
                                });
                              }}
                              disabled={disabled}
                              aria-label={`Origen de ${pieza.nombre || `la pieza ${indice + 1}`}`}
                              className={clsInput}
                            >
                              <option value="FABRICADO">Se fabrica (nuevo)</option>
                              <option value="EXHIBICION">Del showroom (exhibición)</option>
                            </select>
                          </div>
                          {esExhibicion && (
                            <div>
                              <label className="mb-0.5 block text-[9px] font-bold uppercase tracking-wider text-yeikar-neutral/50">
                                Conjunto del que sale
                              </label>
                              <SearchSelect
                                value={pieza.conjunto_origen_id ?? ''}
                                onChange={(valor) => seleccionarConjunto(indice, valor)}
                                options={opcionesConjunto}
                                loadOptions={buscarConjuntos}
                                selectedOption={
                                  pieza.conjunto_origen_id
                                    ? {
                                        value: pieza.conjunto_origen_id,
                                        label:
                                          nombreProducto(pieza.conjunto_origen_id)
                                          || `Conjunto #${pieza.conjunto_origen_id}`,
                                      }
                                    : undefined
                                }
                                placeholder="Pieza suelta / elegir conjunto…"
                                searchPlaceholder="Buscar conjunto…"
                                disabled={disabled}
                              />
                            </div>
                          )}
                        </div>

                        {hint && (
                          <p className="rounded-lg bg-yeikar-tertiary/40 px-2 py-1 text-[10px] text-yeikar-neutral/60">
                            {cargandoConjunto[pieza.conjunto_origen_id ?? 0] ? (
                              <span className="inline-flex items-center gap-1">
                                <Loader2 className="h-3 w-3 animate-spin" aria-hidden="true" />
                                {hint}
                              </span>
                            ) : (
                              hint
                            )}
                          </p>
                        )}

                        {esExhibicion && (
                          <div className="rounded-lg border border-amber-200/70 bg-amber-50/50 px-2 py-1.5">
                            <label className="flex items-center gap-1.5 text-[10px] font-bold text-amber-900">
                              <input
                                type="checkbox"
                                checked={!!pieza.requiere_retrabajo}
                                onChange={(e) => {
                                  const activo = e.target.checked;
                                  actualizar(indice, {
                                    requiere_retrabajo: activo,
                                    ...(activo
                                      ? {}
                                      : { modificacion: '', precio_modificacion: null }),
                                  });
                                }}
                                disabled={disabled}
                                className="h-3.5 w-3.5 rounded border-amber-300 text-amber-600 focus:ring-amber-400"
                              />
                              Requiere retrabajo (recolor, retapizado, ajuste…)
                            </label>
                            {pieza.requiere_retrabajo && (
                              <div className="mt-1.5 grid grid-cols-1 gap-1.5 sm:grid-cols-[minmax(0,1fr)_110px]">
                                <input
                                  type="text"
                                  value={pieza.modificacion ?? ''}
                                  onChange={(e) => actualizar(indice, { modificacion: e.target.value })}
                                  placeholder="Ej: repintar en nogal oscuro"
                                  maxLength={2000}
                                  disabled={disabled}
                                  aria-label={`Modificación de ${pieza.nombre || `la pieza ${indice + 1}`}`}
                                  className={clsInput}
                                />
                                <MontoInput
                                  min="0"
                                  value={pieza.precio_modificacion ?? ''}
                                  onChange={(raw) =>
                                    actualizar(indice, {
                                      precio_modificacion:
                                        raw.trim() === '' ? null : Number(raw),
                                    })
                                  }
                                  disabled={disabled}
                                  placeholder="Cobro retoque"
                                  aria-label={`Precio de la modificación de ${pieza.nombre || `la pieza ${indice + 1}`}`}
                                  className={`${clsInput} font-mono`}
                                />
                              </div>
                            )}
                          </div>
                        )}
                      </div>
                    )}
                  </div>
                );
              })}
            </div>
            {piezas.length < MAX_PIEZAS_JUEGO && (
              <button
                type="button"
                onClick={agregar}
                disabled={disabled}
                className="inline-flex items-center gap-1 text-[10px] font-bold text-yeikar-primary-dark hover:underline disabled:opacity-50"
              >
                <Plus className="h-3 w-3" aria-hidden="true" />
                Agregar otra pieza
              </button>
            )}
          </>
        )}
      </div>
    </details>
  );
}
