import type { EstructuraCostos as EstructuraCostosData, FilaCosto } from '../utils/estructuraCostos';
import { fmtMoneda } from '../utils/format';

// Renderiza la ESTRUCTURA DE COSTOS como documento estilo Excel:
// encabezado formal, bloques por sección con filas (Concepto | Cant | Unidad |
// V/Unit | Precio Total), subtotales, TOTAL PRODUCCIÓN y el bloque final de
// ganancia/IVA/precio de venta.

const FILA_TONE: Record<FilaCosto['tipo'], string> = {
  insumo: '',
  produccion: 'text-amber-800',
  subtotal: 'font-semibold',
  gastos: 'text-slate-600',
  negocio: 'text-slate-600',
  total_seccion: 'font-black text-yeikar-secondary border-t-2 border-yeikar-secondary-light/30',
};

const MONEDA_BASE = 'COP';

export default function EstructuraCostos({ data }: { data: EstructuraCostosData }) {
  const { resumen } = data;
  return (
    <div className="rounded-2xl border border-yeikar-secondary-light/15 bg-white overflow-hidden">
      {/* Encabezado del documento */}
      <div className="bg-gradient-to-r from-yeikar-neutral via-yeikar-secondary to-yeikar-neutral-dark px-6 py-5 text-white">
        <div className="flex flex-wrap items-end justify-between gap-3">
          <div>
            <p className="font-headline text-lg font-black tracking-wide">COMERCIALIZADORA YEIKAR</p>
            <p className="text-sm font-bold tracking-[0.3em] text-yeikar-primary-light">ESTRUCTURA DE COSTOS</p>
            <p className="mt-0.5 text-xs text-white/60">RIF-V-18969838-7</p>
          </div>
          <div className="text-right text-sm">
            <p className="font-bold text-yeikar-primary-light">NOMBRE DEL PRODUCTO</p>
            <p className="font-headline text-lg font-black">{data.producto_nombre}</p>
            {data.dimensiones && (
              <p className="text-xs text-white/60">
                {data.dimensiones.ancho} × {data.dimensiones.largo} m
              </p>
            )}
          </div>
        </div>
      </div>

      <div className="p-6 space-y-5">
        {data.sin_desglose ? (
          <div className="rounded-xl border border-amber-200 bg-amber-50 px-4 py-3 text-sm text-amber-800">
            Este producto no tiene desglose detallado (solo el total del Excel).
            {data.nota ? <span className="block text-xs text-amber-600/80 mt-1">{data.nota}</span> : null}
          </div>
        ) : data.secciones.length === 0 ? (
          <p className="text-sm text-yeikar-neutral/40">Sin secciones de costo.</p>
        ) : (
          data.secciones.map((sec, idx) => (
            <div key={sec.nombre} className="overflow-hidden rounded-xl border border-yeikar-secondary-light/15">
              <div className="bg-yeikar-tertiary/30 px-4 py-2 flex items-center justify-between">
                <h4 className="font-headline font-black text-sm uppercase tracking-wider text-yeikar-secondary">
                  {idx + 1}. {sec.nombre}
                </h4>
                <span className="font-mono text-sm font-bold text-yeikar-secondary">
                  {fmtMoneda(sec.total, MONEDA_BASE)}
                </span>
              </div>
              <div className="overflow-x-auto">
                <table className="w-full text-left border-collapse text-sm">
                  <thead className="bg-yeikar-primary/5 text-yeikar-neutral/50 text-[11px] uppercase tracking-wider">
                    <tr>
                      <th className="px-4 py-1.5">Concepto</th>
                      <th className="px-2 py-1.5 text-right">Cant</th>
                      <th className="px-2 py-1.5">Unidad</th>
                      <th className="px-2 py-1.5 text-right">V/Unit</th>
                      <th className="px-4 py-1.5 text-right">Precio Total</th>
                    </tr>
                  </thead>
                  <tbody className="divide-y divide-yeikar-secondary-light/5">
                    {sec.filas.map((f) => (
                      <tr key={f.id} className={f.tipo === 'total_seccion' ? 'bg-yeikar-tertiary/15' : ''}>
                        <td className={`px-4 py-1.5 ${FILA_TONE[f.tipo]}`}>
                          {f.concepto}
                          {f.nota && <span className="ml-2 text-[11px] text-yeikar-neutral/40 italic">{f.nota}</span>}
                        </td>
                        <td className="px-2 py-1.5 text-right font-mono text-xs">
                          {f.tipo === 'insumo' && f.cantidad ? f.cantidad : ''}
                        </td>
                        <td className="px-2 py-1.5 text-xs text-yeikar-neutral/50">
                          {f.tipo === 'insumo' ? f.unidad : ''}
                        </td>
                        <td className="px-2 py-1.5 text-right font-mono text-xs">
                          {f.tipo === 'insumo' && f.v_unit ? fmtMoneda(f.v_unit, MONEDA_BASE) : ''}
                        </td>
                        <td className={`px-4 py-1.5 text-right font-mono ${FILA_TONE[f.tipo]}`}>
                          {fmtMoneda(f.total, MONEDA_BASE)}
                        </td>
                      </tr>
                    ))}
                  </tbody>
                </table>
              </div>
            </div>
          ))
        )}

        {/* TOTAL PRODUCCIÓN */}
        <div className="flex items-center justify-between rounded-xl bg-yeikar-neutral px-5 py-3 text-white">
          <span className="font-headline text-sm font-black uppercase tracking-widest">Total Producción</span>
          <span className="font-mono text-lg font-black">{fmtMoneda(data.total_produccion, MONEDA_BASE)}</span>
        </div>

        {/* Bloque final: costo / ganancia / precio / IVA */}
        <div className="rounded-xl border border-yeikar-primary/25 bg-yeikar-primary/5 p-5 space-y-2 text-sm">
          <div className="flex justify-between">
            <span className="text-yeikar-neutral/60">Total Costo</span>
            <span className="font-mono font-bold">{fmtMoneda(resumen.costo_total, MONEDA_BASE)}</span>
          </div>
          <div className="flex justify-between">
            <span className="text-yeikar-neutral/60">
              Más Ganancia Máxima de Producto ({resumen.ganancia_porcentaje}%)
            </span>
            <span className="font-mono font-bold text-amber-700">{fmtMoneda(resumen.ganancia_monto, MONEDA_BASE)}</span>
          </div>
          <div className="flex justify-between border-t border-yeikar-primary/15 pt-2">
            <span className="font-bold text-yeikar-secondary">Precio de Venta del Producto</span>
            <span className="font-mono font-black text-yeikar-dark">{fmtMoneda(resumen.precio_venta, MONEDA_BASE)}</span>
          </div>
          {resumen.iva_porcentaje > 0 && (
            <div className="flex justify-between">
              <span className="text-yeikar-neutral/60">IVA {resumen.iva_porcentaje}%</span>
              <span className="font-mono">{fmtMoneda(resumen.precio_con_iva - resumen.precio_venta, MONEDA_BASE)}</span>
            </div>
          )}
          <div className="flex justify-between rounded-lg bg-yeikar-primary px-3 py-2 text-yeikar-neutral">
            <span className="font-headline font-black uppercase tracking-widest">Total a Pagar</span>
            <span className="font-mono text-lg font-black">{fmtMoneda(resumen.precio_con_iva, MONEDA_BASE)}</span>
          </div>
        </div>
      </div>
    </div>
  );
}
