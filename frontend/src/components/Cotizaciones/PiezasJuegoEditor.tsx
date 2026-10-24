import { Layers, Plus, Trash2 } from 'lucide-react';

/** Pieza declarada de un renglón-juego (sin precio propio). */
export interface PiezaJuegoForm {
  nombre: string;
  /** Cantidad por UNIDAD del renglón (por juego): 6 sillas por comedor. */
  cantidad: number;
  notas: string;
}

export const MAX_PIEZAS_JUEGO = 50;

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

  const actualizar = (indice: number, cambios: Partial<PiezaJuegoForm>) => {
    onChange(piezas.map((pieza, i) => (i === indice ? { ...pieza, ...cambios } : pieza)));
  };

  const agregar = () => {
    if (piezas.length >= MAX_PIEZAS_JUEGO) return;
    onChange([
      ...piezas,
      { nombre: `Pieza ${piezas.length + 1}`, cantidad: 1, notas: '' },
    ]);
  };

  const quitar = (indice: number) => {
    onChange(piezas.filter((_, i) => i !== indice));
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
                  className="grid grid-cols-1 gap-1.5 sm:grid-cols-[minmax(0,1fr)_76px_minmax(0,1fr)_28px] sm:items-center"
                >
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
                  <input
                    type="number"
                    min="0.01"
                    step="1"
                    value={pieza.cantidad}
                    onChange={(e) => actualizar(indice, { cantidad: Number(e.target.value) })}
                    disabled={disabled}
                    aria-label={`Cantidad de ${pieza.nombre || `la pieza ${indice + 1}`}`}
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
