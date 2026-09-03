import type { EstructuraCostos as EstructuraCostosData } from '../utils/estructuraCostos';
import { fmtMoneda } from '../utils/format';

// Renderiza la ESTRUCTURA DE COSTOS como documento estilo Excel — la vista que
// el taller prefiere: bandas AMARILLAS para las secciones, rejilla con bordes
// visibles, bandas NARANJAS para los totales y bloque final de ganancia/IVA.

const MONEDA_BASE = 'COP';

const BORDE = 'border border-slate-300';

export default function EstructuraCostos({ data }: { data: EstructuraCostosData }) {
  const { resumen } = data;
  return (
    <div className="rounded-2xl border border-yeikar-secondary-light/15 bg-white overflow-hidden">
      {/* Encabezado del documento (membrete) */}
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
          data.secciones.map((sec) => (
            <div key={sec.nombre} className="overflow-x-auto">
              <table className="w-full border-collapse text-sm">
                <tbody>
                  {/* Banda amarilla de sección, como en el Excel */}
                  <tr>
                    <td colSpan={5} className={`${BORDE} bg-yellow-200 px-3 py-1.5 font-headline font-black uppercase tracking-wide text-yeikar-secondary text-xs`}>
                      SECCION {sec.nombre}
                    </td>
                  </tr>
                  {/* Encabezado de columnas */}
                  <tr className="bg-slate-100 font-bold text-[11px] uppercase text-yeikar-secondary">
                    <td className={`${BORDE} px-3 py-1 text-center`}>MATERIA PRIMA</td>
                    <td className={`${BORDE} px-2 py-1 text-center w-20`}>CANTIDAD</td>
                    <td className={`${BORDE} px-2 py-1 text-center w-32`}>UNIDAD DE MEDIDA</td>
                    <td className={`${BORDE} px-2 py-1 text-center w-28`}>V/UNIT</td>
                    <td className={`${BORDE} px-3 py-1 text-center w-36`}>PRECIO TOTAL</td>
                  </tr>
                  {sec.filas.map((f) => {
                    const esTotal = f.tipo === 'total_seccion';
                    const esSubtotal = f.tipo === 'subtotal' || f.tipo === 'gastos' || f.tipo === 'negocio';
                    return (
                      <tr key={f.id} className={esTotal ? 'bg-orange-200 font-black' : esSubtotal ? 'bg-orange-50' : ''}>
                        <td className={`${BORDE} px-3 py-1 ${f.tipo === 'produccion' ? 'font-semibold' : ''}`}>
                          {f.concepto}
                          {f.nota && <span className="ml-2 text-[11px] text-yeikar-neutral/40 italic">{f.nota}</span>}
                        </td>
                        <td className={`${BORDE} px-2 py-1 text-right font-mono text-xs`}>
                          {f.tipo === 'insumo' && f.cantidad ? f.cantidad : ''}
                        </td>
                        <td className={`${BORDE} px-2 py-1 text-xs text-yeikar-neutral/60`}>
                          {f.tipo === 'insumo' ? f.unidad : ''}
                        </td>
                        <td className={`${BORDE} px-2 py-1 text-right font-mono text-xs`}>
                          {f.tipo === 'insumo' && f.v_unit ? fmtMoneda(f.v_unit, MONEDA_BASE) : ''}
                        </td>
                        <td className={`${BORDE} px-3 py-1 text-right font-mono ${esTotal ? '' : f.tipo === 'produccion' ? 'font-semibold' : ''}`}>
                          {fmtMoneda(f.total, MONEDA_BASE)}
                        </td>
                      </tr>
                    );
                  })}
                </tbody>
              </table>
            </div>
          ))
        )}

        {/* TOTAL PRODUCCIÓN — banda naranja fuerte */}
        {data.secciones.length > 0 && (
          <table className="w-full border-collapse text-sm">
            <tbody>
              <tr className="bg-orange-300 font-black">
                <td className={`${BORDE} px-3 py-2 font-headline uppercase tracking-wide`}>TOTAL PRODUCCIÓN</td>
                <td className={`${BORDE} px-3 py-2 text-right font-mono text-base w-56`}>
                  {fmtMoneda(data.total_produccion, MONEDA_BASE)}
                </td>
              </tr>
            </tbody>
          </table>
        )}

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
