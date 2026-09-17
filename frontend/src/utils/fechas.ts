/**
 * Fechas del ERP en hora de Venezuela.
 *
 * Convención del backend (ver `backend/app/core/hora_ve.py`): los timestamps
 * de negocio se guardan como hora pared de Venezuela en columnas naive, así
 * que un datetime `2026-09-17T15:01:00` ya ES hora VE y se muestra tal cual.
 *
 * El único caso que hay que tratar con cuidado es el **solo-fecha**
 * (`YYYY-MM-DD` de columnas Date): `new Date('2026-09-17')` lo interpreta
 * como medianoche UTC y en Venezuela (UTC-4) mostraría el día anterior.
 * `fmtFechaVE` lo ancla al mediodía local para que el día nunca se corra.
 */

export function fmtFechaVE(
  v: string | Date | null | undefined,
  vacio = '—',
): string {
  if (v === null || v === undefined || v === '') return vacio;
  let d: Date;
  if (v instanceof Date) {
    d = v;
  } else {
    const s = String(v).trim();
    if (!s) return vacio;
    d = /^\d{4}-\d{2}-\d{2}/.test(s)
      ? new Date(`${s.slice(0, 10)}T12:00:00`)
      : new Date(s);
  }
  if (isNaN(d.getTime())) return vacio;
  return d.toLocaleDateString('es-VE', {
    day: '2-digit',
    month: '2-digit',
    year: 'numeric',
  });
}
