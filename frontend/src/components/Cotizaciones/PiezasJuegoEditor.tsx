import { useEffect, useRef, useState } from 'react';
import { Camera, Layers, Plus, Trash2, X } from 'lucide-react';

/** Pieza declarada de un renglón-juego (sin precio propio). */
export interface PiezaJuegoForm {
  nombre: string;
  /** Cantidad por UNIDAD del renglón (por juego): 6 sillas por comedor. */
  cantidad: number;
  notas: string;
  /** Foto opcional de la pieza, ya comprimida como data URL. */
  foto?: string | null;
}

export const MAX_PIEZAS_JUEGO = 50;

const MAX_FOTO_LADO = 900;

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
  }
  return null;
}

interface Props {
  piezas: PiezaJuegoForm[];
  onChange: (piezas: PiezaJuegoForm[]) => void;
  disabled?: boolean;
}

/** Input decimal para la cantidad de una pieza.
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
 * No maneja precios: el renglón conserva su precio global. Las piezas solo
 * abren la producción y el costo por dentro. Se muestra plegado para no
 * cargar la vista de renglones normales.
 */
export default function PiezasJuegoEditor({ piezas, onChange, disabled = false }: Props) {
  const totalUnidades = piezas.reduce(
    (total, pieza) => total + (Number(pieza.cantidad) || 0),
    0,
  );

  // La foto se comprime de forma asíncrona; el ref evita que dos selecciones
  // seguidas se pisen con una lista vieja del render anterior.
  const piezasRef = useRef(piezas);
  useEffect(() => {
    piezasRef.current = piezas;
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
      { nombre: `Pieza ${base.length + 1}`, cantidad: 1, notas: '', foto: null },
    ];
    piezasRef.current = next;
    onChange(next);
  };

  const quitar = (indice: number) => {
    const next = piezasRef.current.filter((_, i) => i !== indice);
    piezasRef.current = next;
    onChange(next);
  };

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
        <span className="ml-auto text-[9px] font-normal text-yeikar-neutral/45">
          {piezas.length > 0 ? 'Editar' : 'Se fabrican y costean por separado'}
        </span>
      </summary>

      <div className="space-y-2 border-t border-yeikar-secondary-light/10 px-3 py-2.5">
        <p className="text-[10px] leading-snug text-yeikar-neutral/55">
          El precio sigue siendo el del renglón completo. Cada pieza genera su
          propia orden de producción y su costo.
        </p>

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
            <div className="space-y-1.5">
              {piezas.map((pieza, indice) => (
                <div
                  key={indice}
                  className="flex items-start gap-1.5 sm:grid sm:grid-cols-[44px_minmax(0,1fr)_76px_minmax(0,1fr)_28px] sm:items-center"
                >
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
                      className="w-full rounded-lg border border-stone-200 bg-white px-2 py-1.5 text-xs focus:border-yeikar-primary focus:outline-none focus:ring-1 focus:ring-yeikar-primary disabled:bg-stone-50"
                    />
                    <CantidadPiezaInput
                      value={pieza.cantidad}
                      onChange={(cantidad) => actualizar(indice, { cantidad })}
                      disabled={disabled}
                      ariaLabel={`Cantidad de ${pieza.nombre || `la pieza ${indice + 1}`}`}
                      className="w-full rounded-lg border border-stone-200 bg-white px-2 py-1.5 text-center font-mono text-xs focus:border-yeikar-primary focus:outline-none focus:ring-1 focus:ring-yeikar-primary disabled:bg-stone-50"
                    />
                    <input
                      type="text"
                      value={pieza.notas}
                      onChange={(e) => actualizar(indice, { notas: e.target.value })}
                      placeholder="Nota (opcional)"
                      disabled={disabled}
                      aria-label={`Nota de ${pieza.nombre || `la pieza ${indice + 1}`}`}
                      className="w-full rounded-lg border border-stone-200 bg-white px-2 py-1.5 text-xs focus:border-yeikar-primary focus:outline-none focus:ring-1 focus:ring-yeikar-primary disabled:bg-stone-50"
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
              ))}
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
