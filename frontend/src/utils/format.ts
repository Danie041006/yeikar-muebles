const CURRENCY_CONFIG: Record<string, { locale: string; currency: string }> = {
  COP: { locale: 'es-CO', currency: 'COP' },
  USD: { locale: 'en-US', currency: 'USD' },
  VES: { locale: 'es-VE', currency: 'VES' },
  EUR: { locale: 'de-DE', currency: 'EUR' },
};

const FALLBACK: typeof CURRENCY_CONFIG[string] = { locale: 'es-CO', currency: 'COP' };

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
