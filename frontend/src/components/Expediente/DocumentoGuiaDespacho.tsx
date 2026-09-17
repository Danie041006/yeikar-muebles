import type { EnvioExp, VentaExp, ClienteExp, DetallePedidoExp } from '../../services/historialService';
import { fmtFechaVE } from '../../utils/fechas';

interface DocumentoGuiaDespachoProps {
  envio: EnvioExp;
  cliente?: ClienteExp | null;
  detalles_pedido?: DetallePedidoExp[];
  venta?: VentaExp | null;
  className?: string;
}

export default function DocumentoGuiaDespacho({
  envio,
  cliente,
  detalles_pedido = [],
  venta,
  className = '',
}: DocumentoGuiaDespachoProps) {
  const guiaNum = (envio.guia_despacho || envio.id.toString()).padStart(6, '0');
  const fechaEmision = envio.fecha_salida
    ? fmtFechaVE(envio.fecha_salida)
    : fmtFechaVE(new Date());

  const totalBs = venta ? Number(venta.total) : 0;
  const baseImponibleBs = totalBs / 1.16;
  const iva16Bs = totalBs - baseImponibleBs;
  const totalVentaBs = totalBs;
  const igtf3Bs = totalVentaBs * 0.03;
  const totalAPagarBs = totalVentaBs + igtf3Bs;

  return (
    <div
      className={`bg-white text-stone-900 font-sans p-7 relative ${className}`}
      style={{ width: '215.9mm', minHeight: '279.4mm', boxSizing: 'border-box' }}
    >
      {/* Marca de agua */}
      <div className="absolute inset-0 flex items-center justify-center pointer-events-none opacity-[0.03] select-none z-0">
        <img src="/logo-marca-de-agua.PNG" alt="" className="w-[400px] h-auto" />
      </div>

      <div className="relative z-10 flex flex-col justify-between min-h-[255mm]">
        <div>
          {/* Encabezado */}
          <div className="flex justify-between items-start pb-3 border-b-2 border-stone-800">
            <div className="space-y-0.5 max-w-[60%]">
              <img src="/Logo-yeikar.png" alt="Yeikar" className="h-10 object-contain mb-1" />
              <h1 className="font-serif font-black text-stone-900 text-sm tracking-widest uppercase">Comercializadora Yeikar</h1>
              <p className="text-[9px] font-bold text-stone-700">RIF. V-18969838-7 · Lilia Carolina Bautista (Propietaria)</p>
              <p className="text-[8px] text-stone-600 leading-tight">Fabricación, Compra, Venta, Importación, Comercialización al Mayor y Detal de todo tipo de Muebles.</p>
              <p className="text-[8px] text-stone-600"><strong>Dirección:</strong> Av. Intercomunal con Calle 16 Local N° 15-205 B. Simón Bolívar, Ureña, Edo. Táchira</p>
              <p className="text-[8px] text-stone-600 font-mono"><strong>Tel:</strong> (0276) 7874095 · Cel: 0414-7393699 / 0414-7398817</p>
              <p className="text-[8px] text-stone-600 font-mono"><strong>Instagram:</strong> @mueblesyeikar.fabricantes · <strong>Facebook:</strong> Muebles Yeikar</p>
            </div>
            {/* Recuadro Guía de Despacho */}
            <div className="text-right border-2 border-stone-800 rounded-lg p-3 bg-stone-50/80 min-w-[175px] shadow-sm">
              <div className="text-[8px] font-black text-red-700 uppercase tracking-widest">Guía de Despacho</div>
              <div className="text-sm font-black text-red-800 font-mono tracking-widest mt-0.5">
                N° {guiaNum}
              </div>
              <div className="text-[8px] font-mono text-stone-700 font-bold mt-1">FECHA DE EMISIÓN: {fechaEmision}</div>
              <div className="text-[8px] font-mono text-stone-700 font-bold mt-0.5">N° DE CONTROL: 00 – {envio.id.toString().padStart(6, '0')}</div>
            </div>
          </div>

          {/* Datos del Destinatario */}
          <div className="border border-stone-300 rounded-sm mt-2 mb-1 text-[9px]">
            <div className="grid grid-cols-3 border-b border-stone-200">
              <div className="col-span-2 px-2 py-1 border-r border-stone-200">
                <span className="font-bold text-stone-500 uppercase text-[7px] block">Nombre y Apellido o Razón Social</span>
                <span className="font-extrabold text-stone-950">{cliente?.nombre ?? '—'}</span>
              </div>
              <div className="px-2 py-1">
                <span className="font-bold text-stone-500 uppercase text-[7px] block">Teléfono</span>
                <span className="font-bold text-stone-900 font-mono">{cliente?.telefono || '—'}</span>
              </div>
            </div>
            <div className="grid grid-cols-2 border-b border-stone-200">
              <div className="px-2 py-1 border-r border-stone-200">
                <span className="font-bold text-stone-500 uppercase text-[7px] block">N° de Registro Único de Información Fiscal (RIF) / C.I.</span>
                <span className="font-bold text-stone-900 font-mono">{cliente?.cedula || '—'}</span>
              </div>
              <div className="px-2 py-1">
                <span className="font-bold text-stone-500 uppercase text-[7px] block">Domicilio Fiscal</span>
                <span className="font-semibold text-stone-900 italic">{cliente?.direccion || '—'}</span>
              </div>
            </div>
            <div className="grid grid-cols-3 border-b border-stone-200">
              <div className="px-2 py-1 border-r border-stone-200">
                <span className="font-bold text-stone-500 uppercase text-[7px] block">FACTURA N°</span>
                <span className="font-black text-red-700 font-mono text-sm">{venta ? venta.id.toString().padStart(6, '0') : '—'}</span>
              </div>
              <div className="px-2 py-1 border-r border-stone-200">
                <span className="font-bold text-stone-500 uppercase text-[7px] block">Forma de Pago</span>
                <span className="font-bold text-stone-900">{venta?.pagos?.[0]?.metodo_pago || '—'}</span>
              </div>
              <div className="px-2 py-1">
                <span className="font-bold text-stone-500 uppercase text-[7px] block">Domicilio / Dirección de Entrega</span>
                <span className="font-semibold text-stone-900 italic text-[8px]">{envio.direccion_entrega || cliente?.direccion || '—'}</span>
              </div>
            </div>
          </div>

          {/* Tabla de Productos con Precio Unitario y Monto */}
          <div className="mb-2 border border-stone-300 overflow-hidden">
            <table className="w-full border-collapse text-[9px]">
              <thead>
                <tr className="bg-stone-800 text-stone-100 uppercase text-[7.5px] tracking-wider">
                  <th className="px-2 py-1.5 text-center w-[10%] border-r border-stone-600">Cant.</th>
                  <th className="px-2 py-1.5 text-left border-r border-stone-600">Concepto o Descripción</th>
                  <th className="px-2 py-1.5 text-right w-[20%] border-r border-stone-600">Precio Unitario</th>
                  <th className="px-2 py-1.5 text-right w-[20%]">Monto</th>
                </tr>
              </thead>
              <tbody className="divide-y divide-stone-200">
                {detalles_pedido.map((det, i) => {
                  // Emparejar el precio con la venta: INSUMO por material_id;
                  // producto por producto_id (nunca null === null).
                  const detVenta = venta?.detalles?.find(dv =>
                    det.tipo_item === 'INSUMO'
                      ? dv.material_id != null && dv.material_id === det.material_id
                      : dv.producto_id != null && dv.producto_id === det.producto_id
                  );
                  const precio = detVenta ? Number(detVenta.precio) : Number(det.precio);
                  const monto = precio * Number(det.cantidad);
                  const simbolo = venta?.moneda === 'VES' ? 'Bs' : venta?.moneda === 'EUR' ? '€' : '$';
                  return (
                    <tr key={det.id || i} className={i % 2 === 0 ? 'bg-white' : 'bg-stone-50/60'}>
                      <td className="px-2 py-1.5 text-center font-mono font-bold border-r border-stone-200">{det.cantidad}</td>
                      <td className="px-2 py-1.5 font-bold border-r border-stone-200">
                        <span>
                          {det.producto_nombre || (det.material_id ? 'Insumo' : 'Mueble Yeikar')}
                          {det.tipo_item !== 'INSUMO' && det.dimensiones?.ancho ? <span className="font-normal text-stone-500"> ({det.dimensiones.ancho}×{det.dimensiones.largo}m)</span> : ''}
                        </span>
                        {det.descripcion_especifica && <span className="block text-[7.5px] text-stone-400 font-normal italic">{det.descripcion_especifica}</span>}
                      </td>
                      <td className="px-2 py-1.5 text-right font-mono border-r border-stone-200">
                        {simbolo}{precio.toLocaleString('es-VE', { minimumFractionDigits: 2 })}
                      </td>
                      <td className="px-2 py-1.5 text-right font-mono font-bold">
                        {simbolo}{monto.toLocaleString('es-VE', { minimumFractionDigits: 2 })}
                      </td>
                    </tr>
                  );
                })}
                {/* Filas vacías para dar aspecto de formulario */}
                {Array.from({ length: Math.max(0, 5 - detalles_pedido.length) }).map((_, i) => (
                  <tr key={`empty-${i}`} className={(detalles_pedido.length + i) % 2 === 0 ? 'bg-white' : 'bg-stone-50/30'}>
                    <td className="px-2 py-2.5 border-r border-stone-200">&nbsp;</td>
                    <td className="px-2 py-2.5 border-r border-stone-200">&nbsp;</td>
                    <td className="px-2 py-2.5 border-r border-stone-200">&nbsp;</td>
                    <td className="px-2 py-2.5">&nbsp;</td>
                  </tr>
                ))}
              </tbody>
              {/* Fila TOTAL */}
              <tfoot>
                <tr className="bg-stone-100 border-t-2 border-stone-800">
                  <td colSpan={3} className="px-2 py-1.5 text-right font-serif font-black text-stone-900 uppercase tracking-widest text-[8.5px] border-r border-stone-300">TOTAL</td>
                  <td className="px-2 py-1.5 text-right font-mono font-black text-stone-950">
                    {venta ? `${venta.moneda === 'VES' ? 'Bs' : '$'}${Number(venta.total).toLocaleString('es-VE', { minimumFractionDigits: 2 })}` : '—'}
                  </td>
                </tr>
              </tfoot>
            </table>
          </div>
        </div>

        {/* Sección Inferior: Transporte + Desglose Fiscal + Firmas */}
        <div>
          {/* Transporte */}
          <div className="border border-stone-300 text-[8.5px] font-mono mb-2">
            <div className="grid grid-cols-3 border-b border-stone-200">
              <div className="px-2 py-1 border-r border-stone-200">
                <span className="font-bold text-stone-500 uppercase text-[7px] block">Transportado en:</span>
                <span className="font-bold text-stone-900">Camión / Suburban Yeikar</span>
              </div>
              <div className="px-2 py-1 border-r border-stone-200">
                <span className="font-bold text-stone-500 uppercase text-[7px] block">Conductor:</span>
                <span className="font-bold text-stone-900">{envio.chofer || 'Por Asignar'}</span>
              </div>
              <div className="px-2 py-1">
                <span className="font-bold text-stone-500 uppercase text-[7px] block">C.I.:</span>
                <span className="font-bold text-stone-900">—</span>
              </div>
            </div>
            <div className="px-2 py-1">
              <span className="font-bold text-stone-500 uppercase text-[7px]">Placas N°: </span>
              <span className="font-bold text-stone-900">S/N</span>
            </div>
          </div>

          {/* Pie: Leyenda Legal + Desglose Fiscal SENIAT + Firmas */}
          <div className="grid grid-cols-2 gap-3 mb-3">
            <div className="text-[7.5px] text-stone-600 space-y-0.5">
              <p className="font-bold text-stone-800 uppercase tracking-wider">Esta Guía de Despacho va sin enmienda ni tachadura.</p>
              <p className="italic">ORIGINAL · Documento legal habilitado para amparar el traslado de bienes y mercancías Comercializadora Yeikar.</p>
            </div>

            {/* Bloque Fiscal SENIAT */}
            <div className="border border-stone-400 rounded-sm overflow-hidden font-mono text-[8px]">
              <div className="bg-stone-900 text-stone-100 px-2 py-0.5 font-serif font-bold uppercase tracking-wider text-[7px] flex justify-between">
                <span>Resumen Fiscal</span>
                <span className="text-[6.5px] text-amber-300">Valores en Bs.</span>
              </div>
              <div className="p-2 space-y-0.5 bg-stone-50">
                <div className="flex justify-between text-stone-700">
                  <span>Monto Total Base Imponible al Valor Agregado % Bs:</span>
                  <span className="font-bold">{baseImponibleBs > 0 ? baseImponibleBs.toLocaleString('es-VE', { minimumFractionDigits: 2, maximumFractionDigits: 2 }) : '—'}</span>
                </div>
                <div className="flex justify-between text-stone-700">
                  <span>Monto Total Impuesto al Valor Agregado — Alícuota 16% Bs:</span>
                  <span className="font-bold">{iva16Bs > 0 ? iva16Bs.toLocaleString('es-VE', { minimumFractionDigits: 2, maximumFractionDigits: 2 }) : '—'}</span>
                </div>
                <div className="flex justify-between text-stone-800 font-bold border-t border-stone-300 pt-0.5">
                  <span>Monto Total Venta Bienes / Servicios Bs:</span>
                  <span>{totalVentaBs > 0 ? totalVentaBs.toLocaleString('es-VE', { minimumFractionDigits: 2, maximumFractionDigits: 2 }) : '—'}</span>
                </div>
                <div className="flex justify-between text-stone-700">
                  <span>Monto Total Base Imponible IGTF / IGTF 3% Bs:</span>
                  <span className="font-bold">{igtf3Bs > 0 ? igtf3Bs.toLocaleString('es-VE', { minimumFractionDigits: 2, maximumFractionDigits: 2 }) : '—'}</span>
                </div>
              </div>
              <div className="bg-amber-100 border-t-2 border-stone-800 px-2 py-1 flex justify-between items-center">
                <span className="font-serif font-black text-stone-950 uppercase text-[7.5px] tracking-wider">TOTAL A PAGAR</span>
                <span className="font-black text-amber-950 font-mono">
                  Bs. {totalAPagarBs > 0 ? totalAPagarBs.toLocaleString('es-VE', { minimumFractionDigits: 2, maximumFractionDigits: 2 }) : '—'}
                </span>
              </div>
            </div>
          </div>

          {/* Firmas */}
          <div className="grid grid-cols-3 gap-6 pt-2 border-t border-stone-300">
            <div className="text-center">
              <div className="w-28 border-t border-stone-400 mx-auto mb-1" />
              <div className="text-[7.5px] font-serif font-bold uppercase tracking-wider text-stone-800">FIRMA DEL CONDUCTOR</div>
              <div className="text-[7px] text-stone-500">Transportista</div>
            </div>
            <div className="text-center">
              <div className="w-28 border-t border-stone-400 mx-auto mb-1" />
              <div className="text-[7.5px] font-serif font-bold uppercase tracking-wider text-stone-800">CLIENTE / CONFORME</div>
              <div className="text-[7px] text-stone-500">Recibido Conforme</div>
            </div>
            <div className="text-center">
              <div className="w-28 border-t border-stone-400 mx-auto mb-1" />
              <div className="text-[7.5px] font-serif font-bold uppercase tracking-wider text-stone-800">COMERCIALIZADORA YEIKAR</div>
              <div className="text-[7px] text-stone-500">Firma del Emisor</div>
            </div>
          </div>

          {/* Sello Original */}
          <div className="text-right mt-1">
            <span className="text-[9px] font-black text-red-700 border border-red-400 px-2 py-0.5 rounded font-serif uppercase tracking-widest">Original</span>
          </div>
        </div>
      </div>
    </div>
  );
}
