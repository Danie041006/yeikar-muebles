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

/**
 * Hoy en Venezuela como `YYYY-MM-DD` (para inputs `type="date"` y payloads).
 * NO usar `new Date().toISOString()` para esto: es UTC y en Venezuela
 * (UTC-4) después de las 8:00 pm la fecha ya saltó a mañana. `en-CA`
 * formatea como YYYY-MM-DD y `America/Caracas` garantiza el día correcto.
 */
export function hoyVE(): string {
  return new Date().toLocaleDateString('en-CA', { timeZone: 'America/Caracas' });
}

/**
 * Ahora en Venezuela como timestamp naive `YYYY-MM-DDTHH:mm:ss` (hora pared
 * VE, sin zona), igual que los guarda el backend (`ahora_ve()`).
 *
 * Para payloads de negocio (etapas de producción, despachos, consumos):
 * `new Date().toISOString()` manda UTC y después de las 8:00 pm el timestamp
 * cae en el día siguiente (rompe nómina y reportes diarios).
 */
export function ahoraVE(): string {
  const partes = new Intl.DateTimeFormat('en-CA', {
    timeZone: 'America/Caracas',
    year: 'numeric',
    month: '2-digit',
    day: '2-digit',
    hour: '2-digit',
    minute: '2-digit',
    second: '2-digit',
    hourCycle: 'h23',
  }).formatToParts(new Date());
  const valor = (tipo: string) =>
    partes.find((p) => p.type === tipo)?.value ?? '00';
  return `${valor('year')}-${valor('month')}-${valor('day')}T${valor('hour')}:${valor('minute')}:${valor('second')}`;
}

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

/**
 * Fecha + hora de un timestamp de negocio.
 *
 * El backend guarda los `created_at` como hora pared de Venezuela en columnas
 * naive (ej. `2026-10-19T09:15:00`). Se leen los componentes del string tal
 * cual, sin `new Date()`, para que un navegador en otra zona horaria no corra
 * la hora. Si el valor trae zona (`Z` o `-04:00`), se respeta con `Date`.
 */
export function fmtFechaHoraVE(
  v: string | Date | null | undefined,
  vacio = '—',
): string {
  if (v === null || v === undefined || v === '') return vacio;
  if (v instanceof Date) {
    if (isNaN(v.getTime())) return vacio;
    const hh = String(v.getHours()).padStart(2, '0');
    const mm = String(v.getMinutes()).padStart(2, '0');
    return `${fmtFechaVE(v)} ${hh}:${mm}`;
  }
  const s = String(v).trim();
  if (!s) return vacio;

  // Si trae zona explícita (Z o -04:00), se interpreta con Date y se muestra
  // en hora de Venezuela. El backend actual guarda naive (sin zona).
  if (/(?:Z|[+-]\d{2}:?\d{2})$/i.test(s)) {
    const d = new Date(s);
    if (isNaN(d.getTime())) return vacio;
    return d.toLocaleString('es-VE', {
      timeZone: 'America/Caracas',
      day: '2-digit',
      month: '2-digit',
      year: 'numeric',
      hour: '2-digit',
      minute: '2-digit',
      hour12: false,
    });
  }

  // Timestamp naive: se muestran los componentes tal cual (ya son hora VE).
  const m = s.match(/^(\d{4})-(\d{2})-(\d{2})[T ](\d{2}):(\d{2})/);
  if (m) return `${m[3]}/${m[2]}/${m[1]} ${m[4]}:${m[5]}`;

  // Solo fecha (`YYYY-MM-DD`) u otro formato: delega en fmtFechaVE.
  return fmtFechaVE(s, vacio);
}
