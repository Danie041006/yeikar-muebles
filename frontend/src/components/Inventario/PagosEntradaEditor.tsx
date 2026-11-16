import { AlertCircle, Plus, Trash2 } from 'lucide-react';

export interface CuentaPagoEntrada {
  key: string;
  cuentaId: number;
  nombre: string;
  monedaId: number;
  codigo: string;
}

export interface PagoEntradaDraft {
  key: string;
  cuentaKey: string;
  monto: string;
  tasa: string;
  observacion: string;
}

export const importeCOP = (monto: number) => `COP ${monto.toLocaleString('es-CO', { minimumFractionDigits: 2, maximumFractionDigits: 2 })}`;

export function totalPagosCOP(pagos: PagoEntradaDraft[], cuentas: CuentaPagoEntrada[]): number {
  return Math.round(pagos.reduce((suma, pago) => {
    const cuenta = cuentas.find((opcion) => opcion.key === pago.cuentaKey);
    const tasa = cuenta?.codigo === 'COP' ? 1 : Number(pago.tasa || 0);
    return suma + Math.round(Number(pago.monto || 0) * tasa * 100) / 100;
  }, 0) * 100) / 100;
}

export function capturaPagos(pagos: PagoEntradaDraft[], cuentas: CuentaPagoEntrada[]) {
  return pagos.map((pago) => {
    const cuenta = cuentas.find((opcion) => opcion.key === pago.cuentaKey);
    if (!cuenta) throw new Error('Selecciona la cuenta de cada pago.');
    return { pago_id: pago.key, metodo_caja_id: cuenta.cuentaId, monto: Number(pago.monto),
      tasa_cambio: cuenta.codigo === 'COP' ? 1 : Number(pago.tasa), observacion: pago.observacion.trim() || undefined };
  });
}

interface Props {
  pagos: PagoEntradaDraft[];
  cuentas: CuentaPagoEntrada[];
  totalCOP: number;
  aplicadoPosterior?: number;
  onChange: (pagos: PagoEntradaDraft[]) => void;
}

const campo = 'w-full rounded-xl border border-yeikar-secondary-light/20 bg-white px-3 py-2.5 text-sm text-yeikar-neutral outline-none focus:border-yeikar-primary';

function nuevaClavePago(): string {
  return globalThis.crypto?.randomUUID?.() ?? `pago-${Date.now()}-${Math.random().toString(16).slice(2)}`;
}

export default function PagosEntradaEditor({ pagos, cuentas, totalCOP, aplicadoPosterior = 0, onChange }: Props) {
  const pagado = totalPagosCOP(pagos, cuentas);
  const pendiente = Math.round((totalCOP - pagado - aplicadoPosterior) * 100) / 100;
  const cambiarPago = (clave: string, cambios: Partial<PagoEntradaDraft>) =>
    onChange(pagos.map((pago) => pago.key === clave ? { ...pago, ...cambios } : pago));

  return (
    <section className="grid gap-4 lg:grid-cols-[1fr_0.85fr]" aria-label="Pagos de la entrada">
      <div className="space-y-3 rounded-2xl border border-yeikar-secondary-light/15 bg-white p-4">
        <div className="flex items-center justify-between gap-3">
          <h3 className="font-headline text-lg font-black text-yeikar-secondary">¿Cuánto salió de cada cuenta?</h3>
          <button type="button" onClick={() => onChange([...pagos, { key: nuevaClavePago(), cuentaKey: '', monto: '', tasa: '', observacion: '' }])} className="inline-flex shrink-0 items-center gap-1 rounded-xl border px-3 py-2 text-xs font-bold text-yeikar-secondary"><Plus size={15} /> Agregar pago</button>
        </div>
        <p className="text-xs text-yeikar-neutral/60">Escribe el monto real, incluso si usaste una sola cuenta. Agregar cuentas no reparte ni cambia los montos escritos.</p>
        {pagos.length === 0 && <p className="flex gap-2 rounded-xl bg-yeikar-tertiary/50 p-3 text-xs"><AlertCircle size={16} className="shrink-0" />Sin pagos: el total quedará fiado al proveedor en Gastos → Por Pagar.</p>}
        {pagos.map((pago, indice) => {
          const cuenta = cuentas.find((opcion) => opcion.key === pago.cuentaKey);
          return (
            <div key={pago.key} className="space-y-2 rounded-xl bg-[#faf8f1] p-3">
              <label className="block text-xs font-semibold text-yeikar-secondary">Concepto u observación del pago {indice + 1}
                <input className={`${campo} mt-1`} value={pago.observacion} maxLength={250} placeholder="Se verá primero en el concepto de caja" onChange={(evento) => cambiarPago(pago.key, { observacion: evento.target.value })} />
              </label>
              <div className="grid items-end gap-2 sm:grid-cols-[1.2fr_1fr_auto]">
                <label className="text-xs font-semibold text-yeikar-secondary">Cuenta / medio {indice + 1}
                  <select className={`${campo} mt-1`} value={pago.cuentaKey} onChange={(evento) => cambiarPago(pago.key, { cuentaKey: evento.target.value, tasa: '' })} required>
                    <option value="">Selecciona cuenta</option>
                    {cuentas.map((opcion) => <option key={opcion.key} value={opcion.key}>{opcion.nombre} · {opcion.codigo}</option>)}
                  </select>
                </label>
                <label className="text-xs font-semibold text-yeikar-secondary">Monto que salió {cuenta ? `(${cuenta.codigo})` : ''}
                  <input className={`${campo} mt-1`} type="number" min="0.01" step="0.01" required value={pago.monto} onChange={(evento) => cambiarPago(pago.key, { monto: evento.target.value })} />
                </label>
                <button type="button" aria-label={`Quitar pago ${indice + 1}`} onClick={() => onChange(pagos.filter((anterior) => anterior.key !== pago.key))} className="rounded-lg p-2 text-red-600"><Trash2 size={17} /></button>
              </div>
              {cuenta && cuenta.codigo !== 'COP' && <label className="block text-xs font-semibold text-yeikar-secondary">1 {cuenta.codigo} = ¿cuántos COP?
                <input className={`${campo} mt-1`} type="number" min="0.000001" step="0.000001" required value={pago.tasa} onChange={(evento) => cambiarPago(pago.key, { tasa: evento.target.value })} />
              </label>}
            </div>
          );
        })}
      </div>
      <div className="space-y-3 rounded-2xl bg-yeikar-secondary p-5 text-white" aria-live="polite">
        <h3 className="font-headline font-black">Resumen en COP</h3>
        <div className="flex justify-between gap-3 text-sm"><span>Total de la entrada</span><b className="font-mono">{importeCOP(totalCOP)}</b></div>
        <div className="flex justify-between gap-3 text-sm"><span>Pagado al registrar</span><b className="font-mono">{importeCOP(pagado)}</b></div>
        {aplicadoPosterior > 0 && <div className="flex justify-between gap-3 text-sm"><span>Abonos / descuentos desde Gastos</span><b className="font-mono">{importeCOP(aplicadoPosterior)}</b></div>}
        <div className="flex justify-between gap-3 border-t border-white/20 pt-3"><span>Saldo pendiente (COP)</span><strong className={`font-mono ${pendiente < 0 ? 'text-red-300' : 'text-yeikar-primary'}`}>{importeCOP(pendiente)}</strong></div>
        {pendiente < 0 ? <p role="alert" className="text-xs text-red-200">Los pagos y abonos superan el total. Revisa los montos; no se ajustarán automáticamente.</p>
          : <p className="text-xs leading-relaxed text-white/70">Lo pendiente queda en Gastos → Por Pagar. Los abonos posteriores se registran allí, no como una corrección de esta entrada.</p>}
      </div>
    </section>
  );
}
