import { useEffect, useState } from 'react';
import { ChevronLeft, ChevronRight, Pencil, X } from 'lucide-react';
import { inventarioService, type EntradaInventarioDetalle, type EntradaInventarioResumen } from '../../services/inventarioService';
import { extractErrorMessage } from '../../utils/format';
import { useDebouncedValue } from '../../hooks/useDebouncedValue';
import { importeCOP } from './PagosEntradaEditor';

interface Props {
  onClose: () => void;
  onEditar: (entrada: EntradaInventarioDetalle) => void;
}

export default function EntradasRegistradas({ onClose, onEditar }: Props) {
  const [buscar, setBuscar] = useState('');
  const filtro = useDebouncedValue(buscar, 300);
  const [offset, setOffset] = useState(0);
  const [entradas, setEntradas] = useState<EntradaInventarioResumen[]>([]);
  const [total, setTotal] = useState(0);
  const [cargando, setCargando] = useState(false);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => { setOffset(0); }, [filtro]);
  useEffect(() => {
    const alPresionarEscape = (evento: KeyboardEvent) => {
      if (evento.key === 'Escape') onClose();
    };
    window.addEventListener('keydown', alPresionarEscape);
    return () => window.removeEventListener('keydown', alPresionarEscape);
  }, [onClose]);
  useEffect(() => {
    let vigente = true;
    setCargando(true);
    inventarioService.getEntradas(filtro, offset).then((respuesta) => {
      if (vigente) { setEntradas(respuesta.entradas); setTotal(respuesta.total); setError(null); }
    }).catch((fallo: unknown) => {
      if (vigente) setError(extractErrorMessage(fallo, 'No se pudieron consultar las entradas.'));
    }).finally(() => { if (vigente) setCargando(false); });
    return () => { vigente = false; };
  }, [filtro, offset]);

  const abrirCorreccion = async (id: number) => {
    setError(null);
    setCargando(true);
    try { onEditar(await inventarioService.getEntrada(id)); }
    catch (fallo: unknown) { setError(extractErrorMessage(fallo, 'No se pudo recuperar la entrada.')); }
    finally { setCargando(false); }
  };

  return <div className="fixed inset-0 z-[90] flex items-center justify-center bg-yeikar-neutral/60 p-3 backdrop-blur-sm" role="dialog" aria-modal="true" aria-labelledby="entradas-registradas-titulo">
    <section className="flex max-h-[92dvh] w-full max-w-5xl flex-col overflow-hidden rounded-3xl bg-[#fbf8f0] shadow-2xl">
      <header className="flex shrink-0 items-start justify-between gap-3 border-b bg-white p-5">
        <div><h2 id="entradas-registradas-titulo" className="font-headline text-xl font-black text-yeikar-secondary">Entradas registradas</h2><p className="mt-1 text-xs text-yeikar-neutral/60">Corrige errores de captura. Para abonar las deudas, usa Gastos → Por Pagar.</p></div>
        <button type="button" onClick={onClose} aria-label="Cerrar entradas registradas" className="rounded-lg p-2"><X size={20} /></button>
      </header>
      <div className="min-h-0 space-y-3 overflow-y-auto p-5">
        <label className="block text-xs font-bold text-yeikar-secondary">Buscar por proveedor u observaciones
          <input className="mt-1 w-full rounded-xl border bg-white p-3 text-sm font-normal" value={buscar} onChange={(evento) => setBuscar(evento.target.value)} />
        </label>
        {error && <p role="alert" className="rounded-xl bg-red-50 p-3 text-sm text-red-800">{error}</p>}
        {cargando && <p role="status" className="text-sm">Consultando entrada…</p>}
        {!cargando && entradas.length === 0 && <p className="p-5 text-center text-sm text-yeikar-neutral/60">No hay entradas para mostrar.</p>}
        {entradas.map((entrada) => <article key={entrada.compra_id} className="space-y-2 rounded-2xl border border-yeikar-secondary/10 bg-white p-4">
          <div className="flex items-start justify-between gap-3"><div><p className="font-headline font-bold text-yeikar-secondary">{entrada.proveedor_nombre || 'Sin proveedor indicado'}</p><p className="text-xs text-yeikar-neutral/60">{entrada.fecha.slice(0, 10).split('-').reverse().join('/')} · versión {entrada.version}</p>
            {entrada.historica && <p className="mt-1 text-[11px] text-amber-800">Entrada anterior al enlace de pagos: al abrirla se verifica si puede corregirse sin adivinar.</p>}</div>
            <button type="button" disabled={cargando} onClick={() => void abrirCorreccion(entrada.compra_id)} className="inline-flex items-center gap-2 rounded-xl bg-yeikar-secondary px-3 py-2 text-xs font-bold text-white disabled:opacity-50"><Pencil size={14} /> Corregir entrada</button>
          </div>
          <p className="text-sm">{entrada.articulos}</p>
          <div className="flex flex-wrap gap-x-5 gap-y-1 font-mono text-xs"><span>Total: {importeCOP(Number(entrada.total_en_moneda_base))}</span><span>Pagado al registrar: {importeCOP(Number(entrada.pagado_en_moneda_base))}</span><strong className="text-yeikar-secondary">Pendiente: {importeCOP(Number(entrada.saldo_actual))}</strong></div>
        </article>)}
      </div>
      <footer className="flex shrink-0 items-center justify-between border-t bg-white px-5 py-3 text-xs">
        <span>{total} entradas</span><div className="flex gap-2"><button type="button" aria-label="Entradas anteriores" disabled={offset === 0 || cargando} onClick={() => setOffset(Math.max(0, offset - 25))} className="rounded-lg border p-2 disabled:opacity-40"><ChevronLeft size={16} /></button><button type="button" aria-label="Más entradas" disabled={offset + 25 >= total || cargando} onClick={() => setOffset(offset + 25)} className="rounded-lg border p-2 disabled:opacity-40"><ChevronRight size={16} /></button></div>
      </footer>
    </section>
  </div>;
}
