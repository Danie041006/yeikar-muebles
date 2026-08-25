const CURRENCY_CONFIG: Record<string, { locale: string; currency: string }> = {
  COP: { locale: 'es-CO', currency: 'COP' },
  USD: { locale: 'en-US', currency: 'USD' },
  VES: { locale: 'es-VE', currency: 'VES' },
  EUR: { locale: 'de-DE', currency: 'EUR' },
};

const FALLBACK: typeof CURRENCY_CONFIG[string] = { locale: 'es-CO', currency: 'COP' };

// Palabra clara de cada moneda (sin símbolos): Pesos, Dólares, Bolívares, Euros.
// Se usa donde el monto conviene leerse en texto plano (saldos pendientes, resúmenes...).
const MONEDA_NOMBRE: Record<string, string> = {
  COP: 'Pesos',
  USD: 'Dólares',
  VES: 'Bolívares',
  EUR: 'Euros',
};

export function nombreMoneda(currencyCode?: string | null): string {
  if (!currencyCode) return 'Pesos';
  return MONEDA_NOMBRE[currencyCode.toUpperCase()] ?? currencyCode.toUpperCase();
}

/** Formatea un monto seguido del nombre claro de la moneda (sin símbolo). */
export function fmtMoneda(amount: number, currencyCode?: string | null): string {
  const n = Number(amount) || 0;
  const locale = (CURRENCY_CONFIG[String(currencyCode || 'COP').toUpperCase()] ?? FALLBACK).locale;
  return `${n.toLocaleString(locale, { maximumFractionDigits: 2 })} ${nombreMoneda(currencyCode)}`;
}

export function formatCurrency(amount: number, currencyCode?: string): string {
  if (currencyCode == null) {
    return `$${Number(amount).toLocaleString('es-CO')} COP`;
  }

  const cfg = CURRENCY_CONFIG[currencyCode.toUpperCase()] ?? FALLBACK;

  try {
    return new Intl.NumberFormat(cfg.locale, {
      style: 'currency',
      currency: cfg.currency,
      maximumFractionDigits: currencyCode === 'COP' ? 0 : 2,
    }).format(amount);
  } catch {
    return `${amount.toFixed(2)} ${currencyCode}`;
  }
}

export function convertFromCop(amountCop: number, tasaCambio: number): number {
  return amountCop / tasaCambio;
}

export function convertToCop(amount: number, tasaCambio: number): number {
  return amount * tasaCambio;
}

// La "tasa natural" va en el sentido natural: 1 Venta = X Pago (p. ej. 1 USD = 4500 COP).
// El backend almacena la inversa (1 Pago = tasa Venta); estas helpers evitan duplicar esa lógica.

export function tasaNaturalAAlmacenada(tasaNatural: number): number {
  return tasaNatural > 0 ? 1 / tasaNatural : 0;
}

export function convertirConTasaNatural(monto: number, tasaNatural: number): number {
  return tasaNatural > 0 ? monto / tasaNatural : 0;
}
