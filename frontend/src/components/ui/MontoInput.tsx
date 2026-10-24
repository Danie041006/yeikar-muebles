import { useEffect, useRef, useState } from 'react';
import type { InputHTMLAttributes } from 'react';
import { Input } from './Field';
import { formatMontoInput } from '../../utils/monto';

type MontoInputProps = Omit<
  InputHTMLAttributes<HTMLInputElement>,
  'type' | 'value' | 'onChange'
> & {
  /** Valor crudo del formulario ("1500000.5", ""). */
  value: string | number | null | undefined;
  /** Devuelve el valor crudo, sin puntos de miles y con punto decimal. */
  onChange: (raw: string) => void;
};

const aRaw = (v: MontoInputProps['value']) =>
  v === null || v === undefined ? '' : String(v);

const aTexto = (v: MontoInputProps['value']) => formatMontoInput(aRaw(v));

/**
 * Input de dinero con separador de miles en vivo: se escribe 1500000 y se ve
 * "1.500.000" (igual que en Cuentas → Movimiento).
 *
 * Para el formulario el valor sigue siendo CRUDO ("1500000.5"): los
 * `parseFloat`/`Number` de las pantallas existentes no cambian.
 */
export default function MontoInput({ value, onChange, ...rest }: MontoInputProps) {
  const raw = aRaw(value);
  const [texto, setTexto] = useState(() => aTexto(value));
  const ultimoRaw = useRef(raw);

  // Sincroniza cuando el formulario cambia el valor por fuera (prefill,
  // "pagar restante", edición de un registro, limpiar tras guardar).
  // Se comparan los VALORES numéricos: mientras el usuario escribe "0," el
  // padre puede guardar 0 y no queremos borrarle la coma en cada tecla.
  useEffect(() => {
    const mismoValor =
      raw === ultimoRaw.current ||
      (raw.trim() !== '' &&
        ultimoRaw.current.trim() !== '' &&
        Number(raw) === Number(ultimoRaw.current));
    if (!mismoValor) {
      ultimoRaw.current = raw;
      setTexto(aTexto(value));
    }
  }, [raw, value]);

  return (
    <Input
      {...rest}
      type="text"
      inputMode="decimal"
      autoComplete="off"
      value={texto}
      onChange={(e) => {
        const formateado = formatMontoInput(e.target.value);
        setTexto(formateado);
        const limpio = formateado.replace(/\./g, '').replace(',', '.');
        ultimoRaw.current = limpio;
        onChange(limpio);
      }}
    />
  );
}
