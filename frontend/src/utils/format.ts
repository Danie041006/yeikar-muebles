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

/**
 * Jerarquía oficial de monedas de YEIKAR:
 * EUR > USD > VES > COP
 *
 * Determina qué moneda es la BASE y cuál la COTIZADA en cualquier par.
 * La tasa humana SIEMPRE se expresa como: "1 [base] = X [cotizada]".
 *
 * Ejemplos:
 *  - USD y COP -> 1 USD = ? COP
 *  - USD y VES -> 1 USD = ? VES
 *  - EUR y COP -> 1 EUR = ? COP
 *  - EUR y VES -> 1 EUR = ? VES
 *  - EUR y USD -> 1 EUR = ? USD
 *  - VES y COP -> 1 VES = ? COP
 */
export const CURRENCY_PRIORITY: readonly string[] = ['EUR', 'USD', 'VES', 'COP'];

export interface ParMonedaHumana {
  baseCod: string;
  quoteCod: string;
  label: string; // "1 USD = ? VES"
  placeholder: string;
}

export function resolverParMonedas(codA?: string | null, codB?: string | null): ParMonedaHumana {
  const a = (codA || 'COP').toUpperCase();
  const b = (codB || 'COP').toUpperCase();

  if (a === b) {
    return {
      baseCod: a,
      quoteCod: b,
      label: `1 ${a} = 1 ${b}`,
      placeholder: '1',
    };
  }

  const idxA = CURRENCY_PRIORITY.indexOf(a);
  const idxB = CURRENCY_PRIORITY.indexOf(b);

  let baseCod: string;
  let quoteCod: string;

  if (idxA !== -1 && idxB !== -1) {
    baseCod = idxA < idxB ? a : b;
    quoteCod = idxA < idxB ? b : a;
  } else if (idxA !== -1) {
    baseCod = a;
    quoteCod = b;
  } else if (idxB !== -1) {
    baseCod = b;
    quoteCod = a;
  } else {
    baseCod = a;
    quoteCod = b;
  }

  const ejemplos: Record<string, string> = {
    'USD-COP': '4200',
    'USD-VES': '75',
    'EUR-COP': '4500',
    'EUR-VES': '80',
    'EUR-USD': '1.08',
    'VES-COP': '55',
  };
  const key = `${baseCod}-${quoteCod}`;
  const placeholder = ejemplos[key] || '1.0';

  return {
    baseCod,
    quoteCod,
    label: `1 ${baseCod} = ? ${quoteCod}`,
    placeholder,
  };
}

/**
 * Convierte un monto entre dos monedas usando la tasa humana (1 base = tasa quote).
 */
export function convertirMonedaHumana(
  monto: number,
  codOrigen: string | undefined | null,
  codDestino: string | undefined | null,
  tasaHumana: number
): number {
  const m = Number(monto) || 0;
  const t = Number(tasaHumana) || 0;
  const origen = (codOrigen || 'COP').toUpperCase();
  const destino = (codDestino || 'COP').toUpperCase();

  if (origen === destino || m === 0) return m;
  if (t <= 0) return 0;

  const { baseCod, quoteCod } = resolverParMonedas(origen, destino);

  if (origen === baseCod && destino === quoteCod) {
    return m * t;
  } else if (origen === quoteCod && destino === baseCod) {
    return m / t;
  }

  return m;
}

/**
 * Calcula la tasa a almacenar en el backend para un pago (tasa_cambio en modelo Pago).
 * En el backend de ventas: monto_en_moneda_venta = monto_pago * tasa_almacenada.
 */
export function calcularTasaAlmacenadaPago(
  monedaPagoCod: string | undefined | null,
  monedaVentaCod: string | undefined | null,
  tasaHumana: number
): number {
  const pago = (monedaPagoCod || 'COP').toUpperCase();
  const venta = (monedaVentaCod || 'COP').toUpperCase();
  const t = Number(tasaHumana) || 0;

  if (pago === venta) return 1.0;
  if (t <= 0) return 0;

  const { baseCod, quoteCod } = resolverParMonedas(pago, venta);

  // Si pago es quote y venta es base (ej. pago VES, venta USD con tasa 1 USD = 75 VES):
  // monto_venta = monto_pago / 75 = monto_pago * (1 / 75) -> tasa = 1 / t
  if (pago === quoteCod && venta === baseCod) {
    return 1 / t;
  }
  // Si pago es base y venta es quote (ej. pago USD, venta COP con tasa 1 USD = 4200 COP):
  // monto_venta = monto_pago * 4200 -> tasa = t
  if (pago === baseCod && venta === quoteCod) {
    return t;
  }

  return t;
}

/**
 * Extrae un string seguro de un error (incluyendo errores 422 de Pydantic v2
 * donde error.response.data.detail es una lista de objetos {type, loc, msg, input, ctx}).
 * Evita colapsar React con Minified React error #31.
 */
export function extractErrorMessage(error: any, fallback = 'Ha ocurrido un error inesperado.'): string {
  if (!error) return fallback;
  const detail = error.response?.data?.detail;
  if (!detail) {
    if (typeof error.message === 'string' && error.message) return error.message;
    return fallback;
  }
  if (typeof detail === 'string') return detail;
  if (Array.isArray(detail)) {
    const msgs = detail
      .map((d: any) => {
        if (!d) return '';
        if (typeof d === 'string') return d;
        if (d.msg) {
          const campo = Array.isArray(d.loc) && d.loc.length > 1 ? d.loc[d.loc.length - 1] : null;
          return campo ? `${campo}: ${d.msg}` : d.msg;
        }
        return JSON.stringify(d);
      })
      .filter(Boolean);
    return msgs.length > 0 ? msgs.join(' · ') : fallback;
  }
  if (typeof detail === 'object') {
    return detail.msg || JSON.stringify(detail);
  }
  return String(detail);
}

