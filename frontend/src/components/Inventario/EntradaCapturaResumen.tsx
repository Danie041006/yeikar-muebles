import type { CapturaEntrada } from '../../services/inventarioService';
import type { CuentaPagoEntrada } from './PagosEntradaEditor';

export default function EntradaCapturaResumen({ captura, cuentas }: { captura: CapturaEntrada; cuentas: CuentaPagoEntrada[] }) {
  return <div className="mt-3 space-y-3 rounded-xl bg-yeikar-tertiary/40 p-3 text-xs text-yeikar-neutral">
    <p>{captura.fecha} · Proveedor: {captura.proveedor_nombre || 'Sin indicar'} · Lo trajo: {captura.recibido_por || 'Sin indicar'}</p>
    {captura.lineas.map((linea, indice) => <div key={linea.linea_id || indice} className="border-t border-yeikar-secondary/10 pt-2">
      <p className="font-bold">{linea.cantidad} {linea.unidad || 'Ud'} · {linea.nombre}</p>
      <p>Precio unitario: {linea.precio_unitario} · Moneda registrada: {linea.moneda_precio_id} · Tasa: {linea.tasa_precio_a_cop || 1}</p>
      <p>Descuento: {linea.descuento_porcentaje}% · Llevada {linea.llevada_total != null ? 'total' : 'por unidad'}: {linea.llevada_total ?? linea.llevada_unitaria}</p>
      <p>Cliente: {linea.cliente_nombre || 'Sin indicar'} · Departamento: {linea.departamento || 'General'}</p>
      {linea.observaciones && <p>{linea.observaciones}</p>}
    </div>)}
    <p className="font-bold">Pagos originales</p>
    {captura.pagos.length === 0 && <p>Sin pagos registrados; entrada fiada.</p>}
    {captura.pagos.map((pago, indice) => <p key={pago.pago_id || indice}>
      {pago.observacion ? `${pago.observacion} · ` : ''}{cuentas.find((cuenta) => cuenta.cuentaId === pago.metodo_caja_id)?.nombre || 'Cuenta registrada'} · {pago.monto} {pago.codigo} · Tasa: {pago.tasa_cambio || 1}
    </p>)}
    {captura.observaciones && <p>Observaciones: {captura.observaciones}</p>}
  </div>;
}
