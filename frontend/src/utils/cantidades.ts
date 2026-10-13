/**
 * Cantidades "a la humana" del taller: "0,75" · "3/4" · "medio" · "tres
 * cuartos" · "dos y medio" · "un litro y medio".
 *
 * El taller a veces recibe la cantidad dictada así y teclearla en un input
 * numérico la rompe en silencio ("3/4" → 3 con parseFloat). Este parser es de
 * ENTRADA (solo UI): devuelve null cuando no entiende y el formulario muestra
 * "= 0,75" en vivo antes de registrar, para que nadie confirme una cantidad
 * mal interpretada. La conversión a unidad base la hace SIEMPRE el backend.
 */

const PALABRAS: Record<string, number> = {
  un: 1, uno: 1, una: 1, dos: 2, tres: 3, cuatro: 4, cinco: 5,
  seis: 6, siete: 7, ocho: 8, nueve: 9, diez: 10,
};

/** Fracciones en palabras (plurales incluidos: "tres cuartos"). */
const FRACCIONES: Record<string, number> = {
  medio: 0.5, media: 0.5, medios: 0.5, medias: 0.5,
  cuarto: 0.25, cuartos: 0.25,
  octavo: 0.125, octavos: 0.125,
};

/** Palabras de unidad (y relleno) que se ignoran: "un litro y medio" → 1,5. */
const UNIDADES: Set<string> = new Set([
  'de', 'del',
  'litro', 'litros', 'l', 'galon', 'galones', 'gal',
  'pistolada', 'pistoladas', 'pist', 'cunete', 'cunetes',
  'tetero', 'teteros', 'libra', 'libras', 'kilo', 'kilos',
  'gramo', 'gramos', 'ml', 'mililitro', 'mililitros', 'onza', 'onzas',
]);

const sinAcentos = (s: string) =>
  s.normalize('NFD').replace(/[\u0300-\u036f]/g, '');

const positivo = (v: number): number | null =>
  Number.isFinite(v) && v > 0 ? v : null;

const numeroSimple = (w: string): number | null => {
  if (/^\d+(?:[.,]\d+)?$/.test(w)) return parseFloat(w.replace(',', '.'));
  const m = w.match(/^(\d+(?:[.,]\d+)?)\s*\/\s*(\d+(?:[.,]\d+)?)$/);
  if (m) {
    const b = parseFloat(m[2].replace(',', '.'));
    if (!(b > 0)) return null;
    return parseFloat(m[1].replace(',', '.')) / b;
  }
  return null;
};

const valorToken = (w: string): number | null => {
  const n = numeroSimple(w);
  if (n !== null) return n;
  if (w in PALABRAS) return PALABRAS[w];
  if (w in FRACCIONES) return FRACCIONES[w];
  return null;
};

/** Devuelve la cantidad en número (ej. "tres cuartos" → 0.75) o null. */
export function parseCantidadHumana(texto: string): number | null {
  if (texto == null) return null;
  let t = sinAcentos(String(texto))
    .replace(/½/g, ' 1/2 ')
    .replace(/¼/g, ' 1/4 ')
    .replace(/¾/g, ' 3/4 ')
    .trim()
    .toLowerCase()
    .replace(/\s+/g, ' ')
    .trim();
  if (!t) return null;

  // 1) Número decimal o fracción simple: 0,75 · 0.75 · 2 · 3/4 · 3 / 4
  const n = numeroSimple(t);
  if (n !== null) return positivo(n);

  // Tokens sin las palabras de unidad ("un litro y medio" → un y medio)
  const tokens = t.split(' ').filter((w) => !UNIDADES.has(w));
  if (tokens.length === 0) return null;

  // 2) "N y medio" / "2 y 1/2" / "tres y cuarto"
  const iy = tokens.indexOf('y');
  if (iy > 0 && iy === tokens.length - 2) {
    const entero = valorToken(tokens[iy - 1]);
    const frac = FRACCIONES[tokens[iy + 1]] ?? numeroSimple(tokens[iy + 1]);
    if (entero !== null && frac !== null && frac < 1) return positivo(entero + frac);
    return null;
  }

  // 3) Un solo token: "tres" · "medio" · "3/4" · "0,75"
  if (tokens.length === 1) {
    const v = valorToken(tokens[0]);
    return v !== null ? positivo(v) : null;
  }

  // 4) "<número> <fracción en palabra>": "tres cuartos" · "un octavo"
  if (tokens.length === 2) {
    const v = valorToken(tokens[0]);
    const f = FRACCIONES[tokens[1]];
    if (v !== null && f !== undefined) return positivo(v * f);
  }

  return null;
}

/** Formatea la cantidad ya parseada para la vista "= 0,75". */
export function fmtCantidadHumana(v: number): string {
  return new Intl.NumberFormat('es-CO', { maximumFractionDigits: 4 }).format(v);
}
