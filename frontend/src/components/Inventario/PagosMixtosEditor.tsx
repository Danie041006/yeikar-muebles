/**
 * PagosMixtosEditor — segunda (o tercera) cuenta de pago de una compra.
 *
 * Los pagos de una entrada/abono pueden ser mixtos: la mitad en efectivo y
 * el resto por Zelle. Cada fila elige cuenta + monto (en la moneda DE ESA
 * cuenta) + tasa humana cuando su moneda difiere de la moneda destino, y una
 * fecha opcional (vacía = HOY en hora Venezuela, la pone el servidor).
 */
import { resolverParMonedas, convertirMonedaHumana } from '../../utils/format';

export interface PagoMixtoRow {
  /** key "cuentaId:monedaId" del selector de cuentas. */
  key: string;
  /** Monto pagado en la moneda de esa cuenta. */
  monto: string;
  /** Tasa humana del par (solo si la moneda del pago difiere del destino). */
  tasa: string;
  /** Fecha opcional (YYYY-MM-DD): vacía = HOY en hora Venezuela. */
  fecha: string;
}

export interface CuentaPagoOption {
  key: string;
  label: string;
  monedaId: number;
  codigo: string;
}

/** Equivalente de UNA fila en la moneda destino (0 si falta algo). */
export function equivalentePago(row: PagoMixtoRow, cuentas: CuentaPagoOption[], codigoDestino: string): number {
  const cuenta = cuentas.find((c) => c.key === row.key);
  if (!cuenta) return 0;
  const monto = Number(row.monto);
  if (!monto || monto <= 0) return 0;
  if (!cuenta.codigo || cuenta.codigo === codigoDestino) return monto;
  const tasa = Number(row.tasa) || 0;
  if (!(tasa > 0)) return 0;
  return convertirMonedaHumana(monto, cuenta.codigo, codigoDestino, tasa);
}

/** Equivalente total de todas las filas en la moneda destino. */
export function equivalenteTotal(filas: PagoMixtoRow[], cuentas: CuentaPagoOption[], destino: string): number {
  return filas.reduce((acc, f) => acc + equivalentePago(f, cuentas, destino), 0);
}

/** true cuando todas las filas están listas (cuenta, monto y tasa). */
export function pagosCompletos(filas: PagoMixtoRow[], cuentas: CuentaPagoOption[], destino: string): boolean {
  if (filas.length === 0) return false;
  return filas.every((row) => {
    const cuenta = cuentas.find((c) => c.key === row.key);
    if (!cuenta) return false;
    const monto = Number(row.monto);
    if (!(monto > 0)) return false;
    if (!cuenta.codigo || cuenta.codigo === destino) return true;
    return (Number(row.tasa) || 0) > 0;
  });
}

interface Props {
  filas: PagoMixtoRow[];
  cuentas: CuentaPagoOption[];
  /** Moneda en la que debe cuadrar la compra/abono. */
  codigoDestino: string;
  /** Total a cubrir en la moneda destino (opcional). */
  totalDestino?: number;
  /** Si true, marca faltante/sobrante para exigir el cuadre exacto. */
  exigirCuadre?: boolean;
  onChange: (filas: PagoMixtoRow[]) => void;
  titulo?: string;
}

export default function PagosMixtosEditor({
  filas, cuentas, codigoDestino, totalDestino, exigirCuadre, onChange,
}: Props) {
  const inputCls =
    'w-full bg-white border border-yeikar-secondary-light/20 rounded-lg px-2.5 py-1.5 text-sm text-yeikar-neutral focus:outline-none focus:ring-2 focus:ring-yeikar-primary font-mono';
  if (filas.length === 0) return null;

  const equivTotal = equivalenteTotal(filas, cuentas, codigoDestino);
  const faltante = totalDestino != null
    ? Math.round(((totalDestino || 0) - equivTotal) * 100) / 100
    : null;
  const cuadreOk = faltante == null
    ? true
    : exigirCuadre
      ? Math.abs(faltante) <= 1
      : faltante <= 0.01;

  return (
    <div className="space-y-2 rounded-xl border border-amber-200 bg-amber-50/40 p-3">
      <p className="text-[10px] font-mono font-bold uppercase tracking-[0.15em] text-yeikar-neutral/50">
        Pagos mixtos · lo pagado en cada cuenta / método
      </p>
      {filas.map((row, i) => {
        const cuenta = cuentas.find((c) => c.key === row.key);
        const pagCod = cuenta?.codigo ?? 'COP';
        const necesitaTasa = !!cuenta && pagCod !== codigoDestino;
        const equivRow = equivalentePago(row, cuentas, codigoDestino);
        return (
          <div key={i} className="grid grid-cols-1 min-[480px]:grid-cols-12 gap-2 items-end">
            <div className="min-[480px]:col-span-5 space-y-1">
              <label className="text-[10px] font-bold text-yeikar-neutral/60">Cuenta / método {i + 1}</label>
              <select
                value={row.key}
                onChange={(e) => {
                  const sel = cuentas.find((c) => c.key === e.target.value);
                  const mismaMoneda = !!sel && (sel.codigo === codigoDestino || sel.monedaId.toString() === e.target.value.split(':')[1] && sel.codigo === codigoDestino);
                  const next = [...filas];
                  next[i] = { ...row, key: e.target.value, tasa: mismaMoneda ? '' : row.tasa };
                  onChange(next);
                }}
                className="w-full bg-white border border-yeikar-secondary-light/20 rounded-lg px-2.5 py-1.5 text-sm"
              >
                <option value="">Elige cuenta...</option>
                {cuentas.map((c) => (
                  <option key={c.key} value={c.key}>{c.label} · {c.codigo}</option>
                ))}
              </select>
            </div>
            {necesitaTasa && (
              <div className="min-[480px]:col-span-3 space-y-1">
                <label className="text-[10px] font-bold text-amber-700">
                  Tasa ({resolverParMonedas(codigoDestino, pagCod).label})
                </label>
                <input
                  type="number" step="any" min="0"
                  value={row.tasa}
                  onChange={(e) => {
                    const next = [...filas];
                    next[i] = { ...row, tasa: e.target.value };
                    onChange(next);
                  }}
                  placeholder={resolverParMonedas(codigoDestino, pagCod).placeholder}
                  className={inputCls}
                />
              </div>
            )}
            <div className={`${necesitaTasa ? 'min-[480px]:col-span-2' : 'min-[480px]:col-span-4'} space-y-1`}>
              <label className="text-[10px] font-bold text-yeikar-neutral/60">Monto ({pagCod})</label>
              <input
                type="number" step="0.01" min="0"
                value={row.monto}
                onChange={(e) => {
                  const next = [...filas];
                  next[i] = { ...row, monto: e.target.value };
                  onChange(next);
                }}
                className={inputCls}
              />
            </div>
            <div className="min-[480px]:col-span-2 flex items-center gap-2 pb-1">
              <span className="text-[10px] font-mono text-yeikar-neutral/50 whitespace-nowrap">
                ≈ {equivRow.toLocaleString('es-CO', { maximumFractionDigits: 2 })} {codigoDestino}
              </span>
              <button
                type="button"
                onClick={() => onChange(filas.filter((_, j) => j !== i))}
                className="rounded-lg px-2 py-1 text-xs font-bold text-red-500 hover:bg-red-50"
                title="Quitar este pago"
              >
                ✕
              </button>
            </div>
            <label className="min-[480px]:col-span-12 flex items-center gap-2 text-[11px] text-yeikar-neutral/60">
              Fecha (opcional):{' '}
              <input
                type="date"
                value={row.fecha}
                onChange={(e) => {
                  const next = [...filas];
                  next[i] = { ...row, fecha: e.target.value };
                  onChange(next);
                }}
                className="border-b border-yeikar-secondary-light/30 bg-transparent px-1 py-0.5 font-mono text-[11px]"
              />
              <span className="text-[10px] text-yeikar-neutral/40">vacía = hoy (hora Venezuela)</span>
            </label>
          </div>
        );
      })}
      {faltante != null && (
        <div className={`space-y-0.5 text-[11px] rounded-lg px-3 py-2 border ${cuadreOk ? 'text-emerald-900 bg-emerald-50/70 border-emerald-100' : 'text-red-700 bg-red-50/80 border-red-200 font-bold'}`}>
          {exigirCuadre ? (
            <>
              <p>
                Pagado: <b className="font-mono">{equivTotal.toLocaleString('es-CO', { maximumFractionDigits: 2 })} {codigoDestino}</b>
                {' ·Compra: '}<b className="font-mono">{(totalDestino || 0).toLocaleString('es-CO')} {codigoDestino}</b>
              </p>
              {Math.abs(faltante) > 1 && (
                <p>
                  {faltante > 0
                    ? `Faltan $${faltante.toLocaleString('es-CO')} ${codigoDestino} para cuadrar la compra`
                    : `Sobran $${Math.abs(faltante).toLocaleString('es-CO')} ${codigoDestino} — ajusta los montos`}
                </p>
              )}
            </>
          ) : (
            <p>
              Total abonado: <b className="font-mono">{equivTotal.toLocaleString('es-CO', { maximumFractionDigits: 2 })} {codigoDestino}</b>
              {faltante > 0 && (
                <> · queda <b className="font-mono">{faltante.toLocaleString('es-CO')} {codigoDestino}</b> por cobrar</>
              )}
            </p>
          )}
        </div>
      )}
    </div>
  );
}
