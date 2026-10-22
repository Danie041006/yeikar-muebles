/** "2.000.000,50" → 2000000.5 (puntos = miles, coma = decimal). */
export const parseMontoInput = (value: string): number => {
  const limpio = String(value ?? '').trim().replace(/\./g, '').replace(',', '.');
  const n = Number(limpio);
  return Number.isFinite(n) ? n : NaN;
};

/** Formatea mientras se escribe: 2.000.000 y decimales con coma. */
export const formatMontoInput = (value: string): string => {
  const s = String(value ?? '').replace(/[^\d.,]/g, '');
  if (!s) return '';

  let entero = s;
  let decimal = '';
  const coma = s.indexOf(',');
  if (coma >= 0) {
    entero = s.slice(0, coma);
    decimal = s.slice(coma + 1).replace(/[.,]/g, '');
  } else {
    // Sin coma: un único punto con 1-2 dígitos al final se toma como decimal
    // (teclado numérico); si no, el punto es separador de miles.
    const puntos = [...s.matchAll(/\./g)];
    if (puntos.length === 1) {
      const idx = puntos[0].index ?? -1;
      const despues = s.slice(idx + 1);
      if (idx >= 0 && despues.length > 0 && despues.length <= 2 && /^\d+$/.test(despues)) {
        entero = s.slice(0, idx);
        decimal = despues;
      }
    }
  }

  entero = entero.replace(/[.,]/g, '').replace(/^0+(?=\d)/, '');
  decimal = decimal.slice(0, 2);
  const enteroFmt = entero
    ? Number(entero).toLocaleString('es-CO', { maximumFractionDigits: 0 })
    : '0';
  return (coma >= 0 || decimal) ? `${enteroFmt},${decimal}` : enteroFmt;
};
