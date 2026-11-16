import type { CapturaEntrada, CompraInventarioMultipleCreate } from '../../services/inventarioService';

interface Props {
  anterior: CapturaEntrada;
  corregida: CompraInventarioMultipleCreate;
  nombres: Record<string, string>;
}

const texto = (valor: unknown) => valor == null || valor === '' ? 'Sin indicar' : String(valor);

export default function EntradaCambiosResumen({ anterior, corregida, nombres }: Props) {
  const cambios: string[] = [];
  for (const [campo, etiqueta] of [['fecha', 'Fecha'], ['proveedor_nombre', 'Proveedor'], ['recibido_por', 'Quién lo trajo'], ['observaciones', 'Observaciones']] as const) {
    if (texto(anterior[campo]) !== texto(corregida[campo])) cambios.push(`${etiqueta}: ${texto(anterior[campo])} → ${texto(corregida[campo])}`);
  }
  const previas = new Map(anterior.lineas.map((linea) => [linea.linea_id, linea]));
  for (const linea of corregida.lineas) {
    const previa = previas.get(linea.linea_id);
    previas.delete(linea.linea_id);
    const nombre = nombres[linea.linea_id || ''] || 'Artículo';
    if (!previa) { cambios.push(`Agregar renglón: ${linea.cantidad} × ${nombre}`); continue; }
    if ((previa.material_id || previa.producto_id) !== (linea.material_id || linea.producto_id) || previa.tipo_item !== linea.tipo_item) cambios.push(`Artículo: ${previa.nombre} → ${nombre}`);
    for (const [campo, etiqueta] of [['cantidad', 'Cantidad'], ['precio_unitario', 'Precio unitario'], ['descuento_porcentaje', 'Descuento (%)'], ['llevada_unitaria', 'Pasada por unidad'], ['llevada_total', 'Pasada total'], ['tasa_precio_a_cop', 'Tasa del precio']] as const) {
      if (Number(previa[campo] || 0) !== Number(linea[campo] || 0)) cambios.push(`${nombre} · ${etiqueta}: ${texto(previa[campo])} → ${texto(linea[campo])}`);
    }
    for (const [campo, etiqueta] of [['cliente_nombre', 'Cliente'], ['departamento', 'Departamento'], ['observaciones', 'Observación del renglón']] as const) {
      if (texto(previa[campo]) !== texto(linea[campo])) cambios.push(`${nombre} · ${etiqueta}: ${texto(previa[campo])} → ${texto(linea[campo])}`);
    }
  }
  for (const previa of previas.values()) cambios.push(`Quitar renglón: ${previa.cantidad} × ${previa.nombre}`);
  const pagosPrevios = new Map(anterior.pagos.map((pago) => [pago.pago_id, pago]));
  for (const pago of corregida.pagos) {
    const previo = pagosPrevios.get(pago.pago_id);
    pagosPrevios.delete(pago.pago_id);
    if (!previo) { cambios.push(`Agregar pago: ${pago.monto} en la cuenta seleccionada`); continue; }
    if (Number(previo.monto) !== pago.monto) cambios.push(`Monto del pago (${previo.codigo}): ${previo.monto} → ${pago.monto}`);
    if (previo.metodo_caja_id !== pago.metodo_caja_id) cambios.push(`Cambiar la cuenta del pago de ${pago.monto}. Revisa la cuenta seleccionada arriba.`);
    if (Number(previo.tasa_cambio || 1) !== Number(pago.tasa_cambio || 1)) cambios.push(`Tasa del pago: ${previo.tasa_cambio} → ${pago.tasa_cambio}`);
    if (texto(previo.observacion) !== texto(pago.observacion)) cambios.push(`Concepto del pago: ${texto(previo.observacion)} → ${texto(pago.observacion)}`);
  }
  for (const pago of pagosPrevios.values()) cambios.push(`Quitar pago: ${pago.monto} ${pago.codigo}`);
  return <ul className="mt-3 list-disc space-y-1 pl-5 text-xs">{cambios.length ? cambios.map((cambio, indice) => <li key={indice}>{cambio}</li>) : <li>No hay cambios en los datos mostrados.</li>}</ul>;
}
