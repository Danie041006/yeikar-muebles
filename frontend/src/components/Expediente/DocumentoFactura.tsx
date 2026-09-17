import type { FacturaExp, ClienteExp } from '../../services/historialService';
import { fmtFechaVE } from '../../utils/fechas';

const fmtBs = (n: number) =>
  n.toLocaleString('es-VE', { minimumFractionDigits: 2, maximumFractionDigits: 2 });

interface DocumentoFacturaProps {
  factura: FacturaExp;
  cliente?: ClienteExp | null;
  className?: string;
}

export default function DocumentoFactura({ factura, cliente, className = '' }: DocumentoFacturaProps) {
  const numero = `00 – ${factura.id.toString().padStart(5, '0')}`;
  const numeroControl = `00 – ${factura.id.toString().padStart(6, '0')}`;
  const fechaEmision = fmtFechaVE(factura.fecha_emision);
  const tasa = factura.tasa_usd_ves || 1;

  const lineas = (factura.detalles || []).map((d, i) => ({
    key: d.descripcion || d.producto_nombre || `linea-${i}`,
    descripcion: d.descripcion ?? d.producto_nombre ?? `Producto`,
    foto: null as string | null,
    cantidad: Number(d.cantidad),
    precioBs: Number(d.precio_usd) * tasa,
    subtotalBs: Number(d.subtotal_bs),
  }));

  const baseImponibleBs = Number(factura.base_imponible_bs) || 0;
  const ivaBs = Number(factura.iva_bs) || 0;
  const totalVentaBs = Number(factura.total_bs) || 0;
  const igtfBs = Number(factura.igtf_bs) || 0;
  const totalAPagarBs = totalVentaBs;

  return (
    <div
      className={`bg-white text-stone-900 font-sans p-8 relative ${className}`}
      style={{ width: '215.9mm', minHeight: '279.4mm', boxSizing: 'border-box' }}
    >
      {/* Filigrana / Logo Marca de Agua */}
      <div className="absolute inset-0 flex items-center justify-center pointer-events-none opacity-[0.03] select-none z-0">
        <img src="/logo-marca-de-agua.PNG" alt="" className="w-[400px] h-auto" />
      </div>

      <div className="relative z-10 flex flex-col justify-between min-h-[255mm]">
        <div>
          {/* Encabezado Oficial */}
          <div className="flex justify-between items-start pb-3 border-b-2 border-stone-800">
            <div className="space-y-1 max-w-[62%]">
              <img src="/Logo-yeikar.png" alt="Yeikar" className="h-10 object-contain mb-1" />
              <h1 className="font-serif font-black text-stone-900 text-sm tracking-widest uppercase">
                Comercializadora Yeikar
              </h1>
              <p className="text-[9px] font-bold text-stone-700">RIF. V-18969838-7 · Lilia Carolina Bautista (Propietaria)</p>
              <p className="text-[8px] text-stone-600 leading-tight">
                Fabricación, Compra, Venta, Importación, Comercialización al Mayor y Detal de todo tipo de Muebles.
              </p>
              <p className="text-[8px] text-stone-600">
                <strong>Dirección:</strong> Av. Intercomunal con Calle 16 Local N° 15-205 B. Simón Bolívar, Ureña, Edo. Táchira
              </p>
              <p className="text-[8px] text-stone-600 font-mono">
                <strong>Tel:</strong> (0276) 7874095 · Cel: 0414-7393699 / 0414-7398817
              </p>
              <p className="text-[8px] text-stone-600 font-mono">
                <strong>Instagram:</strong> @mueblesyeikar.fabricantes &nbsp;·&nbsp; <strong>Facebook:</strong> Muebles Yeikar
              </p>
            </div>

            {/* Recuadro de Control / Número */}
            <div className="text-right border-2 border-stone-800 rounded-lg p-3 bg-stone-50/80 min-w-[170px] shadow-sm">
              <div className="text-[9px] font-black text-stone-800 uppercase tracking-widest">FACTURA DE VENTA</div>
              <div className="text-sm font-black text-amber-800 font-mono tracking-widest mt-1">
                N°: {numero}
              </div>
              <div className="text-[8px] font-mono text-stone-700 font-bold mt-1">
                N° DE CONTROL: {numeroControl}
              </div>
              <div className="text-[8px] font-mono text-stone-700 font-bold mt-0.5">
                FECHA DE EMISIÓN: {fechaEmision}
              </div>
            </div>
          </div>

          {/* Datos del Cliente — Conforme SENIAT */}
          <div className="grid grid-cols-4 gap-x-3 gap-y-2 bg-stone-50/80 border border-stone-300 rounded-xl p-3 my-3 text-[9px] shadow-sm">
            <div className="col-span-4">
              <span className="font-bold text-stone-500 uppercase text-[7.5px] block">Nombre y Apellido o Razón Social</span>
              <span className="font-extrabold text-stone-950 text-xs">{cliente?.nombre ?? '—'}</span>
            </div>
            <div className="col-span-2 border-t border-stone-200 pt-1.5">
              <span className="font-bold text-stone-500 uppercase text-[7.5px] block">Identificación</span>
              <span className="font-bold text-stone-900 font-mono text-[8.5px]">RIF&#160;(&#160;&#160;)&#160;&#160;&#160;C.I.&#160;(&#160;&#160;)</span>
              {cliente?.cedula && (
                <span className="block font-bold text-stone-700 font-mono text-[8px] mt-0.5">
                  {cliente.cedula}
                </span>
              )}
            </div>
            <div className="col-span-2 border-t border-stone-200 pt-1.5">
              <span className="font-bold text-stone-500 uppercase text-[7.5px] block">Teléfono</span>
              <span className="font-extrabold text-stone-900 font-mono">{cliente?.telefono || '—'}</span>
            </div>
            <div className="col-span-4 border-t border-stone-200 pt-1.5">
              <span className="font-bold text-stone-500 uppercase text-[7.5px] block">Domicilio Fiscal</span>
              <span className="font-semibold text-stone-900 italic">{cliente?.direccion || '—'}</span>
            </div>
            <div className="col-span-4 border-t border-stone-200 pt-1.5">
              <span className="font-bold text-stone-500 uppercase text-[7.5px] block">Forma de Pago</span>
              <span className="font-bold text-stone-900 font-mono text-[8px]">
                Efectivo&#160;(&#160;&#160;)&#160;&#160;Tarjeta de Débito&#160;(&#160;&#160;)&#160;&#160;Tarjeta de Crédito&#160;(&#160;&#160;)&#160;&#160;Otros&#160;(&#160;&#160;)
              </span>
            </div>
          </div>

          {/* Tabla de Productos / Concepto o Descripción con montos en Bolívares */}
          <div className="mb-4 border border-stone-300 rounded-lg overflow-hidden shadow-sm">
            <table className="w-full border-collapse text-[9.5px]">
              <thead>
                <tr className="bg-stone-900 text-stone-100 uppercase font-serif text-[8px] tracking-wider">
                  <th className="p-2 text-center w-[8%]">Cant.</th>
                  <th className="p-2 text-left">Concepto o Descripción</th>
                  <th className="p-2 text-right w-[20%]">P. Unitario (Bs.)</th>
                  <th className="p-2 text-right w-[22%]">Monto Total (Bs.)</th>
                </tr>
              </thead>
              <tbody className="divide-y divide-stone-200">
                {lineas.map((l, i) => (
                  <tr key={String(l.key) + i} className={i % 2 === 0 ? 'bg-white' : 'bg-stone-50/60'}>
                    <td className="p-2 text-center font-mono font-bold text-stone-900">{l.cantidad}</td>
                    <td className="p-2 font-serif font-bold text-stone-950">
                      <div className="flex items-center gap-2">
                        {l.foto && (
                          <img
                            src={l.foto}
                            alt={l.descripcion}
                            className="h-16 w-16 rounded-lg object-cover border border-stone-300 shrink-0"
                          />
                        )}
                        <span>{l.descripcion}</span>
                      </div>
                    </td>
                    <td className="p-2 text-right font-mono text-stone-800">Bs. {fmtBs(l.precioBs)}</td>
                    <td className="p-2 text-right font-mono font-black text-stone-950">Bs. {fmtBs(l.subtotalBs)}</td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        </div>

        {/* Sección Inferior: Desglose Fiscal SENIAT Venezuela y Firmas */}
        <div>
          <div className="grid grid-cols-2 gap-4 items-end mb-4">
            {/* Nota Legal izquierda */}
            <div className="text-[8px] text-stone-600 space-y-1.5">
              <p className="font-bold text-stone-800 uppercase tracking-wider">Esta factura va sin enmienda ni tachadura.</p>
            </div>

            {/* Tarjeta de Resumen Fiscal SENIAT Oficial */}
            <div className="border border-stone-400 rounded-xl overflow-hidden shadow-sm font-mono text-[8.5px]">
              <div className="bg-stone-900 text-stone-100 px-3 py-1 font-serif font-bold uppercase tracking-wider text-[7.5px] flex justify-between items-center">
                <span>Resumen Fiscal</span>
              </div>
              <div className="p-2.5 space-y-1 bg-stone-50/90">
                <div className="flex justify-between items-center text-stone-700 border-t border-stone-200 pt-1">
                  <span>Monto Total de la Base Imponible al Valor Agregado Bs:</span>
                  <span className="font-bold text-stone-900">{fmtBs(baseImponibleBs)}</span>
                </div>
                <div className="flex justify-between items-center text-stone-700">
                  <span>Monto Total del Impuesto al Valor Agregado — Alícuota 16% Bs:</span>
                  <span className="font-bold text-stone-900">{fmtBs(ivaBs)}</span>
                </div>
                <div className="flex justify-between items-center text-stone-800 font-bold border-t border-stone-300 pt-1">
                  <span>Monto Total de la Venta de los Bienes o la Prestación del Servicio Bs:</span>
                  <span>{fmtBs(totalVentaBs)}</span>
                </div>
                <div className="flex justify-between items-center text-stone-700">
                  <span>Monto Total de la Base Imponible del IGTF (3%) Bs:</span>
                  <span className="font-bold text-stone-900">{fmtBs(igtfBs)}</span>
                </div>
              </div>

              {/* Destacado de TOTAL A PAGAR Bs. */}
              <div className="bg-amber-100/90 border-t-2 border-stone-800 p-2.5 flex justify-between items-center">
                <div>
                  <span className="font-serif font-black text-stone-950 uppercase text-[9px] tracking-wider block">TOTAL A PAGAR</span>
                </div>
                <div className="text-right">
                  <span className="text-sm font-black text-amber-950 font-mono tracking-tight block">
                    Bs. {fmtBs(totalAPagarBs)}
                  </span>
                </div>
              </div>
            </div>
          </div>
        </div>
      </div>
    </div>
  );
}
