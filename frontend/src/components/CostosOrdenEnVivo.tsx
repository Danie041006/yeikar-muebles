import type { CostosEnVivoOrden } from '../services/produccionService';
import { fmtMoneda } from '../utils/format';

// Desglose de costos EN VIVO de una orden de producción, con la misma
// estructura visual que la ESTRUCTURA DE COSTOS de productos (estilo Excel):
// bandas AMARILLAS por sección, rejilla con bordes, bandas NARANJAS para
// totales. Se actualiza en plena producción conforme se registran consumos
// y mano de obra.

const MONEDA_BASE = 'COP';
const BORDE = 'border border-slate-300';

export default function CostosOrdenEnVivo({ data, loading, compacto = false }: { data: CostosEnVivoOrden | null; loading?: boolean; compacto?: boolean }) {
  if (loading && !data) {
    return (
      <div className="rounded-2xl border border-yeikar-secondary-light/15 bg-white p-6 text-center text-sm text-yeikar-neutral/40">
        Calculando costos en vivo...
      </div>
    );
  }
  if (!data) return null;

  const vacio = data.secciones.length === 0;
  const estimado = data.costo_estimado ?? data.estimado;
  const delta = estimado != null ? data.total_produccion - estimado : null;
  const pctDelta = estimado != null && estimado > 0 ? (delta! / estimado) * 100 : null;

  return (
    <div className="rounded-2xl border border-yeikar-secondary-light/15 bg-white overflow-hidden">
      {/* Encabezado estilo documento (el membrete completo se usa fuera del modal de etapa) */}
      {compacto ? (
        <div className="flex flex-wrap items-center justify-between gap-2 px-4 py-2.5 bg-yeikar-tertiary/40 border-b border-yeikar-secondary-light/10">
          <p className="text-[10px] font-bold font-headline uppercase tracking-wider text-yeikar-neutral/50">
            Estructura de costos de la orden
          </p>
          <p className="font-mono text-xs font-bold text-yeikar-secondary">
            ORDEN #{data.orden_id} · {data.estado.replace('_', ' ')}
          </p>
        </div>
      ) : (
        <div className="bg-gradient-to-r from-yeikar-neutral via-yeikar-secondary to-yeikar-neutral-dark px-5 py-4 text-white">
          <div className="flex flex-wrap items-end justify-between gap-2">
            <div>
              <p className="font-headline text-base font-black tracking-wide">COMERCIALIZADORA YEIKAR</p>
              <p className="text-xs font-bold tracking-[0.3em] text-yeikar-primary-light">ESTRUCTURA DE COSTOS EN VIVO</p>
            </div>
            <div className="text-right text-sm">
              <p className="font-mono font-bold text-yeikar-primary-light">ORDEN #{data.orden_id} · {data.estado.replace('_', ' ')}</p>
              {data.producto_nombre && <p className="font-headline text-base font-black">{data.producto_nombre}</p>}
              {(data.dimensiones?.ancho != null || data.dimensiones?.largo != null) && (
                <p className="text-xs text-white/60">
                  {data.dimensiones.ancho ?? '?'} × {data.dimensiones.largo ?? '?'} m
                  {data.unidades > 1 ? ` · ${data.unidades} und` : ''}
                </p>
              )}
            </div>
          </div>
        </div>
      )}

      <div className="p-5 space-y-4">
        {vacio ? (
          compacto ? (
            <p className="text-xs text-yeikar-neutral/50 italic text-center py-2">
              Sin consumos ni mano de obra en la orden todavía — el desglose por sección aparecerá aquí al registrar el primer movimiento.
            </p>
          ) : (
            <div className="rounded-xl border border-amber-200 bg-amber-50 px-4 py-3 text-sm text-amber-800">
              Sin consumos ni mano de obra registrados aún. Al registrar materiales y mano de obra, aquí verás el
              desglose por sección como en el Excel.
            </div>
          )
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

                  {sec.insumos.map((ins, i) => (
                    <tr key={`${sec.nombre}-ins-${i}`} className={ins.es_excedente || ins.es_retrabajo ? 'bg-red-50' : ''}>
                      <td className={`${BORDE} px-3 py-1`}>
                        {ins.nombre}
                        {ins.captura && (
                          <span className="block text-[10px] font-mono text-yeikar-neutral/50">
                            {ins.captura}
                          </span>
                        )}
                        {ins.es_pendiente && (
                          <span className="ml-2 text-[10px] font-bold text-amber-600 uppercase">
                            PEDIDO · PROVISIONAL
                          </span>
                        )}
                        {ins.es_excedente && (
                          <span className="ml-2 text-[10px] font-bold text-red-500 uppercase">
                            EXCEDENTE{ins.motivo ? ` · ${ins.motivo}` : ''}
                          </span>
                        )}
                        {ins.es_retrabajo && (
                          <span className="ml-2 text-[10px] font-bold text-amber-600 uppercase">RETRABAJO</span>
                        )}
                      </td>
                      <td className={`${BORDE} px-2 py-1 text-right font-mono text-xs`}>{ins.cantidad}</td>
                      <td className={`${BORDE} px-2 py-1 text-xs text-yeikar-neutral/60`}>{ins.unidad}</td>
                      <td className={`${BORDE} px-2 py-1 text-right font-mono text-xs`}>{fmtMoneda(ins.v_unit, MONEDA_BASE)}</td>
                      <td className={`${BORDE} px-3 py-1 text-right font-mono text-xs`}>{fmtMoneda(ins.total, MONEDA_BASE)}</td>
                    </tr>
                  ))}

                  {sec.produccion.map((p, i) => (
                    <tr key={`${sec.nombre}-prod-${i}`} className={p.es_retrabajo ? 'bg-amber-50' : ''}>
                      <td className={`${BORDE} px-3 py-1 font-semibold`}>
                        FABRICACIÓN {p.nombre} ({p.porcentaje}%)
                        {p.es_retrabajo && (
                          <span className="ml-2 text-[10px] font-bold text-amber-600 uppercase">RETRABAJO</span>
                        )}
                      </td>
                      <td className={`${BORDE} px-2 py-1`} />
                      <td className={`${BORDE} px-2 py-1`} />
                      <td className={`${BORDE} px-2 py-1 text-right font-mono text-xs`}>{fmtMoneda(p.base, MONEDA_BASE)}</td>
                      <td className={`${BORDE} px-3 py-1 text-right font-mono font-semibold`}>{fmtMoneda(p.total, MONEDA_BASE)}</td>
                    </tr>
                  ))}

                  <tr className="bg-orange-50">
                    <td className={`${BORDE} px-3 py-1`}>Sub total</td>
                    <td className={`${BORDE} px-2 py-1`} />
                    <td className={`${BORDE} px-2 py-1`} />
                    <td className={`${BORDE} px-2 py-1`} />
                    <td className={`${BORDE} px-3 py-1 text-right font-mono text-xs`}>{fmtMoneda(sec.subtotal, MONEDA_BASE)}</td>
                  </tr>
                  {sec.pct_gastos > 0 && (
                    <tr className="bg-orange-50">
                      <td className={`${BORDE} px-3 py-1`}>Gastos de sección ({sec.pct_gastos}%)</td>
                      <td className={`${BORDE} px-2 py-1`} />
                      <td className={`${BORDE} px-2 py-1`} />
                      <td className={`${BORDE} px-2 py-1`} />
                      <td className={`${BORDE} px-3 py-1 text-right font-mono text-xs`}>{fmtMoneda(sec.gastos, MONEDA_BASE)}</td>
                    </tr>
                  )}
                  <tr className="bg-orange-200 font-black">
                    <td className={`${BORDE} px-3 py-1`}>Total sección</td>
                    <td className={`${BORDE} px-2 py-1`} />
                    <td className={`${BORDE} px-2 py-1`} />
                    <td className={`${BORDE} px-2 py-1`} />
                    <td className={`${BORDE} px-3 py-1 text-right font-mono`}>{fmtMoneda(sec.total, MONEDA_BASE)}</td>
                  </tr>
                </tbody>
              </table>
            </div>
          ))
        )}

        {/* TOTAL PRODUCCIÓN — banda naranja fuerte */}
        {!vacio && (
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

        {/* Resumen: materiales / mano de obra / gastos */}
        {!vacio && (
          <div className="grid grid-cols-3 gap-2 text-center">
            <div className="bg-white rounded-xl border border-yeikar-secondary-light/10 p-2">
              <span className="text-[9px] font-bold text-yeikar-neutral/50 block uppercase">Materiales</span>
              <span className="font-mono font-bold text-sm text-yeikar-secondary">{fmtMoneda(data.totales.materiales, MONEDA_BASE)}</span>
            </div>
            <div className="bg-white rounded-xl border border-yeikar-secondary-light/10 p-2">
              <span className="text-[9px] font-bold text-yeikar-neutral/50 block uppercase">Mano de obra</span>
              <span className="font-mono font-bold text-sm text-yeikar-secondary">{fmtMoneda(data.totales.mano_obra, MONEDA_BASE)}</span>
            </div>
            <div className="bg-white rounded-xl border border-yeikar-secondary-light/10 p-2">
              <span className="text-[9px] font-bold text-yeikar-neutral/50 block uppercase">Gastos</span>
              <span className="font-mono font-bold text-sm text-yeikar-secondary">{fmtMoneda(data.totales.gastos, MONEDA_BASE)}</span>
            </div>
          </div>
        )}

        {/* Estimado vs en vivo + notas */}
        <div className="space-y-1.5 text-xs">
          {estimado != null && delta != null && (
            <div className={`flex justify-between items-center rounded-lg px-3 py-2 font-mono ${
              delta >= 0 ? 'bg-red-50 text-red-700 border border-red-200' : 'bg-emerald-50 text-emerald-700 border border-emerald-200'
            }`}>
              <span className="font-bold uppercase tracking-wider">Estimado vs en vivo</span>
              <span className="font-bold">
                {fmtMoneda(estimado, MONEDA_BASE)} → {fmtMoneda(data.total_produccion, MONEDA_BASE)} · {delta >= 0 ? '+' : ''}{delta.toLocaleString('es-CO')} ({pctDelta?.toFixed(1)}%)
              </span>
            </div>
          )}
          {data.costo_real_total != null && (
            <div className="flex justify-between items-center rounded-lg bg-stone-50 border border-stone-200 px-3 py-2 text-yeikar-neutral/70">
              <span className="font-bold uppercase tracking-wider">Costo real (orden finalizada)</span>
              <span className="font-mono font-bold">
                {fmtMoneda(data.costo_real_total, MONEDA_BASE)}
                {data.costo_real_precio_venta != null && (
                  <span className="ml-2 text-yeikar-secondary">· Venta ({data.costo_real_ganancia ?? 0}%): {fmtMoneda(data.costo_real_precio_venta, MONEDA_BASE)}</span>
                )}
              </span>
            </div>
          )}
          {data.totales.excedentes > 0 && (
            <p className="text-[10px] text-yeikar-neutral/40 italic">
              Excedentes y retrabajo ({fmtMoneda(data.totales.excedentes, MONEDA_BASE)} en excedentes) no entran a la
              estructura generada, pero sí al costo real de la orden.
            </p>
          )}
          {!vacio && data.unidades > 1 && (
            <p className="text-[10px] text-yeikar-neutral/40 italic">
              Costo acumulado de toda la orden ({data.unidades} unidades). La estructura generada al finalizar divide
              las cantidades por unidad.
            </p>
          )}
        </div>
      </div>
    </div>
  );
}