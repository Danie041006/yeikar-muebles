import React from 'react';
import type { Nomina, NominaDetalle } from '../../services/nominaService';

const fmtCOP = (n: number) => `$ ${(Number(n) || 0).toLocaleString('es-CO')}`;

interface Props {
  nomina: Nomina;
  containerId?: string;
  className?: string;
}

interface BloqueEmpleadoProps {
  d: NominaDetalle;
  nomina: Nomina;
}

function BloqueEmpleado({ d, nomina }: BloqueEmpleadoProps) {
  return (
    <div data-pdf-item="true" className="border border-stone-300 rounded-lg overflow-hidden shadow-sm mb-6 break-inside-avoid">

      {/* ── Cabecero del ticket ── */}
      <div className="flex justify-between items-start px-4 py-3 border-b-2 border-stone-900 bg-white">
        <div className="space-y-0.5">
          <img src="/Logo-yeikar.png" alt="Yeikar" className="h-10 object-contain" />
          <div className="font-serif font-bold text-stone-950 text-[10px] tracking-widest uppercase mt-1">
            Comercializadora Yeikar
          </div>
          <div className="text-[7px] text-stone-500 font-mono font-semibold leading-tight">
            AV. INTERCOMUNAL CON CALLE 16 LOCAL Nro 15-205, BARRIO SIMÓN BOLÍVAR, UREÑA, TÁCHIRA
          </div>
        </div>

      </div>

      {/* ── Header del empleado ── */}
      <div className="bg-stone-50/60 px-4 py-2.5 border-b border-stone-200 flex flex-wrap items-center justify-between gap-2">
        <div className="flex items-center gap-2">
          <span className="font-serif font-bold text-stone-950 text-[11px]">{d.empleado_nombre}</span>
          {d.cargo_nombre && (
            <span className="text-[8px] text-stone-500 font-medium uppercase tracking-wider">{d.cargo_nombre}</span>
          )}
        </div>
        <span className={`text-[8px] font-bold uppercase tracking-[0.12em] px-2 py-0.5 rounded-full
          ${d.tipo_pago === 'DESTAJO'
            ? 'bg-purple-100 text-purple-800 border border-purple-200'
            : 'bg-stone-100 text-stone-700 border border-stone-300'
          }`}>
          {d.tipo_pago === 'DESTAJO' ? 'Producción' : d.tipo_pago}
        </span>
      </div>

      {/* ── Tabla de líneas ── */}
      {d.lineas.length > 0 && (
        <div className="border-b border-stone-200">
          <table className="w-full border-collapse text-[9px]">
            <thead>
              <tr className="bg-stone-900 text-stone-100">
                <th className="px-3 py-1.5 text-left font-serif font-bold uppercase tracking-[0.12em] text-[7.5px] w-[8%]">Cant.</th>
                <th className="px-3 py-1.5 text-left font-serif font-bold uppercase tracking-[0.12em] text-[7.5px]">Descripción</th>
                <th className="px-3 py-1.5 text-left font-serif font-bold uppercase tracking-[0.12em] text-[7.5px] w-[20%]">Cliente</th>
                <th className="px-3 py-1.5 text-right font-serif font-bold uppercase tracking-[0.12em] text-[7.5px] w-[14%]">P. Unitario</th>
                <th className="px-3 py-1.5 text-right font-serif font-bold uppercase tracking-[0.12em] text-[7.5px] w-[14%]">Total</th>
              </tr>
            </thead>
            <tbody className="divide-y divide-stone-200">
              {d.lineas.map((l, idx) => (
                <tr key={l.id} className={idx % 2 === 0 ? 'bg-white' : 'bg-stone-50/60'}>
                  <td className="px-3 py-1.5 text-center font-mono font-extrabold text-stone-900">{l.cantidad}</td>
                  <td className="px-3 py-1.5 font-medium text-stone-800">
                    {l.descripcion}
                    {l.origen === 'ETAPA' && <span className="ml-1 text-[7px] text-amber-700 font-bold">auto</span>}
                  </td>
                  <td className="px-3 py-1.5 text-stone-600 italic">{l.cliente_nombre || '—'}</td>
                  <td className="px-3 py-1.5 text-right font-mono text-stone-800 font-medium">{fmtCOP(Number(l.precio_unitario))}</td>
                  <td className="px-3 py-1.5 text-right font-mono font-extrabold text-stone-950">{fmtCOP(Number(l.total))}</td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      )}

      {/* ── Totales ── */}
      <div className="px-4 py-2.5 space-y-1">
        <div className="flex justify-between items-center text-[9px]">
          <span className="text-stone-600 font-bold uppercase tracking-wider text-[7.5px]">Total Producción</span>
          <span className="font-mono font-extrabold text-stone-900">{fmtCOP(Number(d.total_produccion))}</span>
        </div>
        {Number(d.bono_aguinaldo) > 0 && (
          <div className="flex justify-between items-center text-[9px]">
            <span className="text-amber-700 font-bold uppercase tracking-wider text-[7.5px]">Bono Aguinaldo Acumulado</span>
            <span className="font-mono font-extrabold text-amber-800">+{fmtCOP(Number(d.bono_aguinaldo))}</span>
          </div>
        )}
        <div className="flex justify-between items-center border-t border-stone-300 pt-1.5 mt-1">
          <span className="text-[9px] font-serif font-bold uppercase tracking-wider text-stone-800">Nómina a Pagar</span>
          <span className="text-sm font-black text-amber-900 font-mono">{fmtCOP(Number(d.monto_a_pagar))}</span>
        </div>
      </div>

      {/* ── Sección de firma ── */}
      <div className="border-t border-stone-300 bg-stone-50/40 px-4 py-3">
        <div className="grid grid-cols-2 gap-6">
          <div className="flex flex-col justify-between">
            <div className="text-[8px] font-serif font-bold uppercase tracking-wider text-stone-800">
              Firma del Trabajador
            </div>
            <div className="mt-8">
              <div className="w-full border-t border-stone-400 mb-1" />
              <div className="text-[7px] text-stone-500 font-medium">Firma y cédula del trabajador</div>
            </div>
          </div>
          <div className="flex flex-col justify-between">
            <div>
              <div className="text-[8px] font-serif font-bold uppercase tracking-wider text-stone-800 mb-1">
                Recibí el Monto Indicado
              </div>
              <div className="flex items-center gap-2 mb-2">
                <div className="w-4 h-4 border border-stone-400 rounded" />
                <span className="text-[8px] text-stone-700 font-bold">FIRMADO</span>
              </div>
            </div>
            <div className="grid grid-cols-2 gap-3 mt-4">
              <div>
                <div className="text-[7px] text-stone-500 font-bold uppercase tracking-wider mb-0.5">Fecha</div>
                <div className="border-t border-stone-400 w-full" />
              </div>
              <div>
                <div className="text-[7px] text-stone-500 font-bold uppercase tracking-wider mb-0.5">Cédula</div>
                <div className="border-t border-stone-400 w-full" />
              </div>
            </div>
          </div>
        </div>
      </div>
    </div>
  );
}

/**
 * Documento de Nómina YEIKAR — plantilla visual para generar PDF
 * con html2canvas + jsPDF, igual que las cotizaciones.
 */
export default function DocumentoNomina({
  nomina,
  containerId,
  className = '',
}: Props) {
  return (
    <div
      id={containerId}
      className={`bg-white shadow-2xl relative text-stone-800 font-sans mx-auto ${className}`}
      style={{
        width: '215.9mm',
        minHeight: '279.4mm',
        padding: '14mm 15mm',
        boxSizing: 'border-box',
        display: 'flex',
        flexDirection: 'column',
      }}
    >
      {/* Watermark */}
      <div className="absolute inset-0 flex items-center justify-center pointer-events-none opacity-[0.06] z-0 select-none">
        <img src="/logo-marca-de-agua.PNG" alt="" className="w-[420px] h-auto" />
      </div>

      {/* ── All content above watermark ── */}
      <div className="relative z-10 flex flex-col gap-4 flex-1">
        <div className="flex flex-col gap-4">

          {/* ── Bloques de empleados (Tickets individuales) ── */}
          {nomina.detalles.map((d) => (
            <BloqueEmpleado key={d.id} d={d} nomina={nomina} />
          ))}

          {/* ── Conceptos varios ── */}
          {nomina.conceptos_varios.length > 0 && (
            <div data-pdf-item="true" className="border border-stone-300 rounded-lg overflow-hidden shadow-sm">
              <div className="bg-stone-900 text-stone-100 px-4 py-2">
                <span className="text-[8.5px] font-serif font-bold uppercase tracking-[0.12em]">Varios</span>
              </div>
              <div className="divide-y divide-stone-200">
                {nomina.conceptos_varios.map((c) => (
                  <div key={c.id} className="flex justify-between items-center px-4 py-2 text-[9px]">
                    <span className="text-stone-800 font-medium">{c.descripcion}</span>
                    <span className="font-mono font-extrabold text-stone-950">{fmtCOP(Number(c.monto))}</span>
                  </div>
                ))}
              </div>
            </div>
          )}

          {/* ── Resumen trabajador y totales ── */}
          <div data-pdf-item="true" className="space-y-4">
            <div className="border border-stone-300 rounded-lg overflow-hidden shadow-sm">
              <div className="bg-stone-900 text-stone-100 px-4 py-2">
                <span className="text-[8.5px] font-serif font-bold uppercase tracking-[0.12em]">Resumen Trabajador</span>
              </div>
              <table className="w-full border-collapse text-[9px]">
                <thead>
                  <tr className="bg-stone-100 text-stone-800 border-b border-stone-300">
                    <th className="px-3 py-1.5 text-left font-serif font-bold uppercase tracking-wider text-[7.5px]">Cargo</th>
                    <th className="px-3 py-1.5 text-left font-serif font-bold uppercase tracking-wider text-[7.5px]">Trabajador</th>
                    <th className="px-3 py-1.5 text-right font-serif font-bold uppercase tracking-wider text-[7.5px]">Monto</th>
                  </tr>
                </thead>
                <tbody className="divide-y divide-stone-200">
                  {nomina.detalles.map((d, idx) => (
                    <tr key={d.id} className={idx % 2 === 0 ? 'bg-white' : 'bg-stone-50/60'}>
                      <td className="px-3 py-1.5 text-stone-700 font-medium">{d.cargo_nombre || '—'}</td>
                      <td className="px-3 py-1.5 font-serif font-bold text-stone-950">{d.empleado_nombre}</td>
                      <td className="px-3 py-1.5 text-right font-mono font-extrabold text-stone-950">{fmtCOP(Number(d.monto_a_pagar))}</td>
                    </tr>
                  ))}
                </tbody>
                <tfoot>
                  <tr className="bg-amber-50/60 border-t-2 border-stone-900">
                    <td colSpan={2} className="px-3 py-2">
                      <span className="text-[9px] font-serif font-black uppercase tracking-wider text-stone-900">Total Nómina</span>
                    </td>
                    <td className="px-3 py-2 text-right">
                      <span className="text-sm font-black text-amber-900 font-mono">{fmtCOP(Number(nomina.total_nomina))}</span>
                    </td>
                  </tr>
                </tfoot>
              </table>
            </div>

            {/* ── Firma empleador ── */}
            <div className="grid grid-cols-2 gap-10 pt-4">
              <div className="text-center">
                <div className="w-40 border-t border-stone-400 mx-auto mb-1" />
                <div className="text-[8px] font-serif font-bold uppercase tracking-wider text-stone-800">Firma del Empleador</div>
                <div className="text-[7px] text-stone-500 font-medium mt-0.5">Autorizado</div>
              </div>
              <div className="text-center">
                <div className="w-40 border-t border-stone-400 mx-auto mb-1" />
                <div className="text-[8px] font-serif font-bold uppercase tracking-wider text-stone-800">Fecha de Pago</div>
                <div className="text-[7px] text-stone-500 font-medium mt-0.5">___/___/______</div>
              </div>
            </div>
          </div>
        </div>
      </div>{/* end z-10 */}
    </div>
  );
}
