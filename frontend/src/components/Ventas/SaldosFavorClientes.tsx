import { useEffect, useState } from 'react';
import { saldoFavorService, type SaldoFavor } from '../../services/saldoFavorService';
import { extractErrorMessage, formatCurrency } from '../../utils/format';
import { fmtFechaVE } from '../../utils/fechas';

export default function SaldosFavorClientes({ revision = 0 }: { revision?: number }) {
  const [abierto, setAbierto] = useState(false);
  const [creditos, setCreditos] = useState<SaldoFavor[]>([]);
  const [pagina, setPagina] = useState(0);
  const [error, setError] = useState('');
  const [cargando, setCargando] = useState(false);
  useEffect(() => {
    if (!abierto) return;
    let vigente = true;
    setCargando(true);
    setError('');
    saldoFavorService.listar({ salto: pagina * 50, limite: 50 })
      .then((lista) => { if (vigente) setCreditos(lista); })
      .catch((fallo: unknown) => { if (vigente) setError(extractErrorMessage(fallo, 'No se pudieron consultar los saldos.')); })
      .finally(() => { if (vigente) setCargando(false); });
    return () => { vigente = false; };
  }, [abierto, pagina, revision]);
  return (
    <section className="rounded-xl border border-emerald-200 bg-white p-4">
      <button onClick={() => setAbierto(!abierto)} aria-expanded={abierto} className="font-headline font-bold text-emerald-800">
        Saldos a favor de clientes {abierto ? '−' : '+'}
      </button>
      {abierto && <div className="mt-3 space-y-2 text-sm">
        {cargando ? <p>Cargando saldos…</p> : creditos.map((c) => (
          <div key={c.id} className="flex flex-wrap justify-between gap-2 border-b py-2">
            <div><strong>{c.cliente_nombre}</strong><p className="text-xs text-yeikar-neutral/60">{c.referencia} · {fmtFechaVE(c.created_at)} · {c.creador_nombre}</p></div>
            <strong className="font-mono text-emerald-800">{formatCurrency(Number(c.saldo), c.moneda.codigo)}</strong>
          </div>
        ))}
        {!cargando && !error && !creditos.length && <p>No hay saldos disponibles en esta página.</p>}
        {error && <p role="alert" className="text-red-700">{error}</p>}
        <div className="flex gap-3 text-xs">
          <button disabled={!pagina || cargando} onClick={() => setPagina(pagina - 1)}>Anterior</button>
          <button disabled={creditos.length < 50 || cargando} onClick={() => setPagina(pagina + 1)}>Siguiente</button>
        </div>
      </div>}
    </section>
  );
}
