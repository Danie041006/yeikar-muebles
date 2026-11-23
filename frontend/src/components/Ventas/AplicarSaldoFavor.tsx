import { useEffect, useRef, useState } from 'react';
import { Button, MontoInput } from '../ui';
import { saldoFavorService, type SaldoFavor, type AplicarSaldo } from '../../services/saldoFavorService';
import type { VentaDetalle } from '../../services/ventaService';
import { calcularTasaAlmacenadaPago, extractErrorMessage, formatCurrency, resolverParMonedas } from '../../utils/format';

export default function AplicarSaldoFavor({ venta, onAplicado }: { venta: VentaDetalle; onAplicado: () => Promise<void> }) {
  const [creditos, setCreditos] = useState<SaldoFavor[]>([]);
  const [indice, setIndice] = useState('');
  const [monto, setMonto] = useState('');
  const [tasa, setTasa] = useState('');
  const [error, setError] = useState('');
  const [ocupado, setOcupado] = useState(false);
  const [pagina, setPagina] = useState(0);
  const intento = useRef<{ firma: string; id: string } | null>(null);
  const enviando = useRef(false);
  const credito = creditos.find((c) => c.id === Number(indice));
  const distinta = !!credito && credito.moneda_id !== venta.moneda_id;
  const par = resolverParMonedas(credito?.moneda.codigo, venta.moneda?.codigo);
  const conversion = distinta
    ? calcularTasaAlmacenadaPago(credito?.moneda.codigo, venta.moneda?.codigo, Number(tasa))
    : 1;
  const equivalente = Math.round(Number(monto) * conversion * 100) / 100;

  useEffect(() => {
    let vigente = true;
    setError('');
    saldoFavorService.listar({ cliente_id: venta.cliente_id, salto: pagina * 50, limite: 50 })
      .then((lista) => { if (vigente) setCreditos(lista); })
      .catch((fallo: unknown) => { if (vigente) setError(extractErrorMessage(fallo, 'No se pudo consultar el saldo a favor.')); });
    return () => { vigente = false; };
  }, [venta.cliente_id, venta.pagos.length, pagina]);

  const aplicar = async () => {
    if (!credito || enviando.current) return;
    setError('');
    if (!Number.isFinite(equivalente) || equivalente <= 0 || Number(monto) > Number(credito.saldo)) {
      setError('Revisa el monto disponible y digita la tasa manual si cambia la moneda.');
      return;
    }
    if (equivalente > Number(venta.saldo_pendiente)) {
      setError('El equivalente supera lo pendiente. Usa solo una parte; el resto queda a favor.');
      return;
    }
    if (!window.confirm(`¿Aplicar ${formatCurrency(Number(monto), credito.moneda.codigo)} del saldo a favor?\nSe descontarán ${formatCurrency(equivalente, venta.moneda?.codigo)} de esta venta. No entra dinero nuevo a caja.`)) return;
    const firma = JSON.stringify([venta.id, credito.id, monto, conversion]);
    if (intento.current?.firma !== firma) intento.current = { firma, id: crypto.randomUUID() };
    const payload: AplicarSaldo = {
      venta_id: venta.id, saldo_favor_id: credito.id, monto: Number(monto),
      operacion_id: intento.current.id, ...(distinta ? { tasa_cambio: conversion } : {}),
    };
    try {
      enviando.current = true;
      setOcupado(true);
      await saldoFavorService.aplicar(payload);
      setMonto('');
      setTasa('');
      setIndice('');
      await onAplicado();
    } catch (fallo: unknown) {
      setError(extractErrorMessage(fallo, 'No se pudo aplicar el saldo a favor.'));
    } finally {
      enviando.current = false;
      setOcupado(false);
    }
  };

  if (!creditos.length && !error && pagina === 0) return null;
  return (
    <section aria-label="Saldo a favor del cliente" className="space-y-3 rounded-xl border border-emerald-200 bg-emerald-50 p-4">
      <h4 className="font-headline font-black text-emerald-900">Saldo a favor del cliente</h4>
      <ul className="text-xs text-emerald-900">
        {creditos.map((c) => <li key={c.id}>{formatCurrency(Number(c.saldo), c.moneda.codigo)} · {c.referencia}</li>)}
      </ul>
      {venta.saldo_pendiente > 0 && venta.estado !== 'CANCELADA' && (
        <div className="space-y-2">
          <label className="block text-xs font-bold">Crédito que se usará
            <select aria-label="Crédito que se usará" value={indice} disabled={ocupado}
              onChange={(e) => { setIndice(e.target.value); setMonto(''); setTasa(''); }}
              className="mt-1 block w-full rounded-lg border p-2">
              <option value="">Selecciona un saldo a favor</option>
              {creditos.map((c) => <option key={c.id} value={c.id}>#{c.id} · {formatCurrency(Number(c.saldo), c.moneda.codigo)}</option>)}
            </select>
          </label>
          {credito && <>
            <label className="block text-xs font-bold">Monto del saldo a favor ({credito.moneda.codigo})
              <MontoInput aria-label="Monto del saldo a favor" value={monto} onChange={setMonto} disabled={ocupado} className="mt-1 w-full rounded-lg border p-2" />
            </label>
            {distinta && <label className="block text-xs font-bold">Tasa manual: {par.label}
              <input aria-label="Tasa manual del saldo a favor" type="number" min="0" step="any" value={tasa}
                disabled={ocupado} onChange={(e) => setTasa(e.target.value)} placeholder={par.placeholder}
                className="mt-1 w-full rounded-lg border p-2" />
            </label>}
            {equivalente > 0 && <p className="text-xs">Se aplicará {formatCurrency(equivalente, venta.moneda?.codigo)}. Sin entrada de caja.</p>}
            <Button onClick={aplicar} loading={ocupado} disabled={!monto || (distinta && !tasa)}>Aplicar saldo a favor</Button>
          </>}
        </div>
      )}
      {(pagina > 0 || creditos.length === 50) && <div className="flex gap-2 text-xs">
        <button disabled={pagina === 0 || ocupado} onClick={() => setPagina(pagina - 1)}>Anterior</button>
        <button disabled={creditos.length < 50 || ocupado} onClick={() => setPagina(pagina + 1)}>Siguiente</button>
      </div>}
      {error && <p role="alert" className="text-xs text-red-700">{error}</p>}
    </section>
  );
}
