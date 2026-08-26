import React from 'react';
import { formatCurrency } from '../../utils/format';
import { accionVerbo } from '../../utils/auditoria';
import BadgeEstado from '../BadgeEstado';
import AdjuntoImagen from '../AdjuntoImagen';
import DocumentoCotizacion from './DocumentoCotizacion';
import {
  AuditoriaExp,
  ConsumoExp,
  CotizacionExp,
  EnvioExp,
  EtapaExp,
  Expediente,
  FacturaExp,
  GastoExp,
  PagoExp,
  ProduccionExp,
  VentaExp,
} from '../../services/historialService';

const fmtFecha = (v?: string | null) => (v ? new Date(v).toLocaleDateString('es-CO') : '—');
const fmtFechaHora = (v?: string | null) =>
  v ? new Date(v).toLocaleString('es-CO', { dateStyle: 'short', timeStyle: 'short' }) : '—';
const dinero = (n?: number | null, moneda?: string | null) => formatCurrency(Number(n || 0), moneda || undefined);

// ─────────────────────────────────────────────────────────────────────────
// Estructura: tarjetas por etapa de la cadena
// ─────────────────────────────────────────────────────────────────────────
function CardSeccion({ titulo, icono, children, estado, dominio, acciones }: {
  titulo: string;
  icono: React.ReactNode;
  children: React.ReactNode;
  estado?: string | null;
  dominio?: 'cotizacion' | 'pedido' | 'orden' | 'etapa' | 'venta' | 'envio' | 'factura';
  acciones?: React.ReactNode;
}) {
  return (
    <section className="bg-white border border-yeikar-secondary-light/10 rounded-2xl shadow-sm overflow-hidden">
      <header className="flex items-center justify-between gap-2 bg-gradient-to-r from-yeikar-secondary to-yeikar-secondary-light px-5 py-3">
        <h3 className="flex items-center gap-2 font-headline font-black text-white text-sm uppercase tracking-wider">
          {icono}
          {titulo}
        </h3>
        <div className="flex items-center gap-2">
          {acciones}
          {estado && dominio && <BadgeEstado dominio={dominio} estado={estado} />}
        </div>
      </header>
      <div className="p-5">{children}</div>
    </section>
  );
}

const Fila = ({ k, v, mono = false }: { k: string; v: React.ReactNode; mono?: boolean }) => (
  <div className="flex items-start justify-between gap-3 py-1 text-xs">
    <span className="text-yeikar-neutral/55 shrink-0">{k}</span>
    <span className={`font-semibold text-yeikar-secondary text-right ${mono ? 'font-mono' : ''}`}>{v ?? '—'}</span>
  </div>
);

const tablaTh = 'px-3 py-1.5 text-[10px] font-black uppercase tracking-wider text-yeikar-neutral/45 text-left whitespace-nowrap';
const tablaTd = 'px-3 py-1.5 text-xs font-mono text-yeikar-secondary whitespace-nowrap';

// ─────────────────────────────────────────────────────────────────────────
// Cotización
// ─────────────────────────────────────────────────────────────────────────
function SeccionCotizacion({ cot }: { cot?: CotizacionExp | null }) {
  if (!cot) {
    return (
      <CardSeccion titulo="Cotización" icono={<span>📋</span>}>
        <p className="text-xs text-yeikar-neutral/50 italic">Sin cotización vinculada.</p>
      </CardSeccion>
    );
  }
  return (
    <CardSeccion titulo={`Cotización #${cot.id}`} icono={<span>📋</span>} estado={cot.estado} dominio="cotizacion">
      <div className="grid grid-cols-2 sm:grid-cols-4 gap-3 mb-4">
        <Fila k="Fecha" v={fmtFecha(cot.fecha)} />
        <Fila k="Registrada por" v={cot.creado_por} />
        <Fila k="Total estimado" v={dinero(cot.total_estimado, cot.moneda)} mono />
        <Fila k="Moneda / Tasa" v={`${cot.moneda || '—'} · ${cot.tasa_cambio ?? '—'}`} mono />
      </div>
      <table className="w-full">
        <thead>
          <tr className="border-b border-yeikar-secondary-light/10">
            <th className={tablaTh}>Mueble</th>
            <th className={`${tablaTh} text-right`}>Cant.</th>
            <th className={`${tablaTh} text-right`}>Precio</th>
            <th className={`${tablaTh} text-right`}>Subtotal</th>
            <th className={tablaTh}>Medidas</th>
          </tr>
        </thead>
        <tbody className="divide-y divide-yeikar-secondary-light/5">
          {cot.detalles.map((d, i) => (
            <tr key={i}>
              <td className={`${tablaTd} whitespace-normal font-semibold`}>{d.producto_nombre || `Producto #${d.producto_id}`}</td>
              <td className={`${tablaTd} text-right`}>{d.cantidad}</td>
              <td className={`${tablaTd} text-right`}>{dinero(d.precio, cot.moneda)}</td>
              <td className={`${tablaTd} text-right font-bold`}>{dinero(d.precio * d.cantidad, cot.moneda)}</td>
              <td className={`${tablaTd} whitespace-normal`}>
                {d.dimensiones?.ancho ? `${d.dimensiones.ancho}m × ${d.dimensiones.largo ?? '?'}m` : 'Estándar'}
              </td>
            </tr>
          ))}
        </tbody>
      </table>
      {cot.observaciones && (
        <p className="mt-3 text-[11px] text-yeikar-neutral/55 italic bg-yeikar-tertiary/30 rounded-lg px-3 py-2">{cot.observaciones}</p>
      )}
    </CardSeccion>
  );
}

// ─────────────────────────────────────────────────────────────────────────
// Pedido
// ─────────────────────────────────────────────────────────────────────────
function SeccionPedido({ exp }: { exp: Expediente }) {
  const ped = exp.pedido;
  if (!ped) return null;
  return (
    <CardSeccion titulo={`Pedido #${ped.id}`} icono={<span>🛒</span>} estado={ped.estado} dominio="pedido">
      <div className="grid grid-cols-2 sm:grid-cols-4 gap-3 mb-4">
        <Fila k="Fecha" v={fmtFecha(ped.fecha)} />
        <Fila k="Entregado por" v={ped.creado_por} />
        <Fila k="Entrega estimada" v={fmtFecha(ped.fecha_entrega_estimada)} />
        <Fila k="Cotización origen" v={`#${ped.cotizacion_id ?? '—'}`} />
      </div>
      <table className="w-full">
        <thead>
          <tr className="border-b border-yeikar-secondary-light/10">
            <th className={tablaTh}>Mueble</th>
            <th className={`${tablaTh} text-right`}>Cant.</th>
            <th className={`${tablaTh} text-right`}>Precio</th>
            <th className={`${tablaTh} text-right`}>Costo unit.</th>
            <th className={tablaTh}>Detalles</th>
          </tr>
        </thead>
        <tbody className="divide-y divide-yeikar-secondary-light/5">
          {exp.detalles_pedido.map((d) => (
            <tr key={d.id}>
              <td className={`${tablaTd} whitespace-normal font-semibold`}>{d.producto_nombre || `Producto #${d.producto_id}`}</td>
              <td className={`${tablaTd} text-right`}>{d.cantidad}</td>
              <td className={`${tablaTd} text-right`}>{dinero(d.precio)}</td>
              <td className={`${tablaTd} text-right`}>{dinero(d.costo_unitario)}</td>
              <td className={`${tablaTd} whitespace-normal max-w-[220px]`}>
                {[d.color && `Color: ${d.color}`, d.acabado && `Acabado: ${d.acabado}`, d.descripcion_especifica]
                  .filter(Boolean)
                  .join(' · ') || '—'}
              </td>
            </tr>
          ))}
        </tbody>
      </table>
      {ped.observaciones && (
        <p className="mt-3 text-[11px] text-yeikar-neutral/55 italic bg-yeikar-tertiary/30 rounded-lg px-3 py-2">{ped.observaciones}</p>
      )}
    </CardSeccion>
  );
}

// ─────────────────────────────────────────────────────────────────────────
// Producción: timeline de áreas por orden
// ─────────────────────────────────────────────────────────────────────────
function TimelineAreas({ produccion }: { produccion: ProduccionExp }) {
  const etapas = produccion.etapas || [];
  if (etapas.length === 0) {
    return <p className="text-xs text-yeikar-neutral/50 italic">La orden aún no tiene etapas asignadas.</p>;
  }
  return (
    <ol className="space-y-0">
      {etapas.map((et, i) => (
        <li key={et.id} className="relative flex gap-3 pb-4 last:pb-0">
          {i < etapas.length - 1 && <span className="absolute left-[9px] top-5 bottom-0 w-px bg-yeikar-secondary-light/20" />}
          <span className={`mt-1 h-[18px] w-[18px] rounded-full border-2 shrink-0 ${
            et.estado === 'COMPLETADA'
              ? 'bg-emerald-500 border-emerald-500'
              : et.estado === 'EN_PROCESO'
                ? 'bg-yeikar-primary border-yeikar-primary animate-pulse'
                : 'bg-white border-yeikar-secondary-light/40'
          }`} />
          <div className="flex-1 min-w-0">
            <div className="flex flex-wrap items-center gap-2">
              <span className="font-headline font-bold text-xs text-yeikar-secondary">{et.area_nombre || `Área #${et.area_id}`}</span>
              {et.es_retrabajo && (
                <span className="text-[9px] font-black uppercase tracking-wider text-rose-600 bg-rose-50 px-1.5 py-0.5 rounded">Retrabajo</span>
              )}
              <BadgeEstado dominio="etapa" estado={et.estado} />
            </div>
            <p className="text-[11px] text-yeikar-neutral/55 font-mono mt-0.5">
              {et.empleado_responsable || 'Sin responsable'}
              {et.empleados_adicionales?.length ? ` + ${et.empleados_adicionales.join(', ')}` : ''}
              {et.fecha_inicio && ` · ${fmtFechaHora(et.fecha_inicio)} → ${et.fecha_fin ? fmtFechaHora(et.fecha_fin) : 'en curso'}`}
            </p>
            {et.consumos.length > 0 && (
              <div className="mt-2 rounded-xl border border-yeikar-secondary-light/10 bg-yeikar-tertiary/25 p-3">
                <p className="text-[10px] font-black uppercase tracking-wider text-yeikar-neutral/45 mb-1.5">Materiales usados ({et.consumos.length})</p>
                <table className="w-full">
                  <thead>
                    <tr>
                      <th className={tablaTh}>Material</th>
                      <th className={`${tablaTh} text-right`}>Cant.</th>
                      <th className={`${tablaTh} text-right`}>Costo unit.</th>
                      <th className={`${tablaTh} text-right`}>Total</th>
                      <th className={tablaTh}>Por</th>
                    </tr>
                  </thead>
                  <tbody className="divide-y divide-yeikar-secondary-light/5">
                    {et.consumos.map((c) => (
                      <tr key={c.id}>
                        <td className={`${tablaTd} whitespace-normal font-semibold`}>{c.material_nombre || `Material #${c.material_id}`}</td>
                        <td className={`${tablaTd} text-right`}>{c.cantidad}</td>
                        <td className={`${tablaTd} text-right`}>{dinero(c.costo_unitario)}</td>
                        <td className={`${tablaTd} text-right font-bold`}>{dinero((c.cantidad || 0) * (c.costo_unitario || 0))}</td>
                        <td className={`${tablaTd} whitespace-normal`}>{c.creado_por || '—'}</td>
                      </tr>
                    ))}
                  </tbody>
                </table>
              </div>
            )}
            {et.mano_obra.length > 0 && (
              <div className="mt-2 flex flex-wrap gap-2">
                {et.mano_obra.map((m) => (
                  <span key={m.id} className="text-[11px] font-mono bg-emerald-50 text-emerald-700 border border-emerald-200/60 rounded-lg px-2 py-1">
                    {m.empleado_nombre}: {dinero(m.monto)}
                    {m.porcentaje_recargo ? ` (+${m.porcentaje_recargo}%)` : ''}
                    {m.pagado ? ' ✓' : ' · pendiente'}
                  </span>
                ))}
              </div>
            )}
          </div>
        </li>
      ))}
    </ol>
  );
}

function SeccionProduccion({ detalles }: { detalles: Expediente['detalles_pedido'] }) {
  const conProduccion = detalles.filter((d) => d.produccion);
  if (conProduccion.length === 0) {
    return (
      <CardSeccion titulo="Producción" icono={<span>🔨</span>}>
        <p className="text-xs text-yeikar-neutral/50 italic">Sin órdenes de producción para este pedido.</p>
      </CardSeccion>
    );
  }
  return (
    <CardSeccion titulo="Producción" icono={<span>🔨</span>}>
      <div className="space-y-6">
        {conProduccion.map((d) => {
          const p = d.produccion!;
          return (
            <div key={d.id} className="rounded-2xl border border-yeikar-secondary-light/15 p-4">
              <div className="flex flex-wrap items-center justify-between gap-2 mb-3">
                <div>
                  <p className="font-headline font-bold text-sm text-yeikar-secondary">
                    {d.producto_nombre || `Producto #${d.producto_id}`}
                    <span className="text-yeikar-neutral/45 font-mono text-xs ml-2">x{d.cantidad}</span>
                  </p>
                  <p className="text-[11px] text-yeikar-neutral/55 font-mono">
                    Orden #{p.orden.id} · creada por {p.orden.creado_por || '—'} · {fmtFecha(p.orden.fecha_inicio)}
                  </p>
                </div>
                <BadgeEstado dominio="orden" estado={p.orden.estado} />
              </div>
              <TimelineAreas produccion={p} />
              {p.costo && (
                <div className="mt-3 grid grid-cols-2 sm:grid-cols-4 gap-2 rounded-xl bg-yeikar-secondary/5 border border-yeikar-secondary-light/10 p-3">
                  <Fila k="Materiales" v={dinero(p.costo.costo_material)} mono />
                  <Fila k="Mano de obra" v={dinero(p.costo.costo_mano_obra)} mono />
                  <Fila k="Gastos" v={dinero(p.costo.costo_gastos)} mono />
                  <Fila k="Costo total" v={dinero(p.costo.costo_total)} mono />
                  <Fila k="Precio calculado" v={dinero(p.costo.precio_venta_calculado)} mono />
                  <Fila k="Ganancia" v={`${p.costo.ganancia_porcentaje ?? '—'}%`} mono />
                  <Fila k="Impuestos base" v={dinero(p.costo.precio_impuestos_base)} mono />
                </div>
              )}
            </div>
          );
        })}
      </div>
    </CardSeccion>
  );
}

// ─────────────────────────────────────────────────────────────────────────
// Venta y cobros (ingresos)
// ─────────────────────────────────────────────────────────────────────────
function PagoRow({ pago }: { pago: PagoExp }) {
  return (
    <div className="rounded-xl border border-yeikar-secondary-light/15 p-3">
      <div className="flex flex-wrap items-center justify-between gap-2">
        <div className="flex items-center gap-2 flex-wrap">
          <span className="font-mono font-bold text-sm text-emerald-700">+ {dinero(pago.monto, pago.moneda)}</span>
          <span className="text-[11px] text-yeikar-neutral/55 font-mono">
            {pago.metodo_pago || '—'} · {fmtFechaHora(pago.fecha)}
          </span>
          {pago.moneda && pago.moneda !== 'COP' && (
            <span className="text-[10px] font-mono bg-amber-50 text-amber-700 border border-amber-200 rounded px-1.5 py-0.5">
              ≈ {dinero(pago.monto_en_moneda_base)} COP
            </span>
          )}
        </div>
        <BadgeEstado dominio="venta" estado="PAGADA" />
      </div>
      {(pago.referencia || pago.observaciones) && (
        <p className="text-[11px] text-yeikar-neutral/55 mt-1">
          {pago.referencia}
          {pago.observaciones ? ` · ${pago.observaciones}` : ''}
        </p>
      )}
      <div className="flex flex-wrap items-center gap-2 mt-1.5">
        {pago.caja && (
          <span className="text-[10px] font-mono bg-yeikar-tertiary/40 text-yeikar-secondary rounded px-1.5 py-0.5">
            Caja: {pago.caja.cuenta} · {pago.caja.responsable || 'sin responsable'}
          </span>
        )}
        {pago.recibos.map((r) => (
          <AdjuntoImagen key={r.id} adjunto={r} alt={r.nombre} className="h-9 w-9 rounded-lg border border-yeikar-secondary-light/15" />
        ))}
      </div>
    </div>
  );
}

function SeccionVenta({ venta }: { venta?: VentaExp | null }) {
  if (!venta) {
    return (
      <CardSeccion titulo="Venta y cobros" icono={<span>💰</span>}>
        <p className="text-xs text-yeikar-neutral/50 italic">Este pedido aún no tiene venta/factura de cobro.</p>
      </CardSeccion>
    );
  }
  const pct = venta.total > 0 ? Math.min(100, (venta.total_pagado / venta.total) * 100) : 0;
  return (
    <CardSeccion titulo={`Venta #${venta.id} y cobros`} icono={<span>💰</span>} estado={venta.estado} dominio="venta">
      <div className="grid grid-cols-2 sm:grid-cols-4 gap-3 mb-4">
        <Fila k="Total" v={dinero(venta.total, venta.moneda)} mono />
        <Fila k="Pagado" v={dinero(venta.total_pagado, venta.moneda)} mono />
        <Fila k="Saldo pendiente" v={dinero(venta.saldo_pendiente, venta.moneda)} mono />
        <Fila k="Equiv. COP" v={dinero(venta.total_en_moneda_base)} mono />
      </div>
      <div className="h-2 rounded-full bg-yeikar-tertiary overflow-hidden mb-4">
        <div className="h-full rounded-full bg-gradient-to-r from-emerald-500 to-emerald-600 transition-all" style={{ width: `${pct}%` }} />
      </div>
      <div className="space-y-2">
        {venta.pagos.length === 0 && (
          <p className="text-xs text-yeikar-neutral/50 italic">Sin pagos registrados.</p>
        )}
        {venta.pagos.map((p) => <PagoRow key={p.id} pago={p} />)}
      </div>
      {venta.observaciones && (
        <p className="mt-3 text-[11px] text-yeikar-neutral/55 italic bg-yeikar-tertiary/30 rounded-lg px-3 py-2">{venta.observaciones}</p>
      )}
    </CardSeccion>
  );
}

// ─────────────────────────────────────────────────────────────────────────
// Egresos
// ─────────────────────────────────────────────────────────────────────────
function SeccionGastos({ gastos }: { gastos: GastoExp[] }) {
  const total = gastos.reduce((acc, g) => acc + Number(g.monto_en_moneda_base || 0), 0);
  return (
    <CardSeccion titulo={`Egresos del pedido (${gastos.length})`} icono={<span>📤</span>}>
      {gastos.length === 0 ? (
        <p className="text-xs text-yeikar-neutral/50 italic">Sin egresos registrados para este pedido.</p>
      ) : (
        <>
          <div className="grid grid-cols-2 sm:grid-cols-4 gap-3 mb-4">
            <Fila k="Total egresos" v={dinero(total)} mono />
          </div>
          <table className="w-full">
            <thead>
              <tr className="border-b border-yeikar-secondary-light/10">
                <th className={tablaTh}>Fecha</th>
                <th className={tablaTh}>Descripción</th>
                <th className={tablaTh}>Área</th>
                <th className={`${tablaTh} text-right`}>Monto</th>
                <th className={tablaTh}>Registró</th>
              </tr>
            </thead>
            <tbody className="divide-y divide-yeikar-secondary-light/5">
              {gastos.map((g) => (
                <tr key={g.id}>
                  <td className={tablaTd}>{fmtFecha(g.fecha)}</td>
                  <td className={`${tablaTd} whitespace-normal`}>{g.descripcion || '—'}</td>
                  <td className={tablaTd}>{g.area || '—'}</td>
                  <td className={`${tablaTd} text-right font-bold text-rose-600`}>{dinero(g.monto, g.moneda)}</td>
                  <td className={tablaTd}>{g.creado_por || '—'}</td>
                </tr>
              ))}
            </tbody>
          </table>
        </>
      )}
    </CardSeccion>
  );
}

// ─────────────────────────────────────────────────────────────────────────
// Facturas fiscales
// ─────────────────────────────────────────────────────────────────────────
function SeccionFacturas({ facturas, entrada }: { facturas: FacturaExp[]; entrada?: Expediente['factura_entrada'] }) {
  const lista = entrada ? facturas.filter((f) => f.id === entrada.id) : facturas;
  return (
    <CardSeccion titulo={`Facturas fiscales (${facturas.length})`} icono={<span>🧾</span>}>
      {facturas.length === 0 ? (
        <p className="text-xs text-yeikar-neutral/50 italic">Sin facturas fiscales emitidas.</p>
      ) : (
        <div className="space-y-2">
          {(lista.length ? lista : facturas).map((f) => (
            <div key={f.id} className="rounded-xl border border-yeikar-secondary-light/15 p-3 flex flex-wrap items-center justify-between gap-2">
              <div>
                <p className="font-headline font-bold text-sm text-yeikar-secondary">Factura #{f.id}</p>
                <p className="text-[11px] text-yeikar-neutral/55 font-mono">
                  {fmtFecha(f.fecha_emision)} · ${f.total_usd} USD · {f.total_bs.toLocaleString('es-VE')} Bs
                  {f.tasa_usd_ves ? ` · 1 USD = ${f.tasa_usd_ves} Bs` : ''} · emitida por {f.creado_por || '—'}
                </p>
              </div>
              <BadgeEstado dominio="factura" estado={f.estado} />
            </div>
          ))}
        </div>
      )}
    </CardSeccion>
  );
}

// ─────────────────────────────────────────────────────────────────────────
// Despacho
// ─────────────────────────────────────────────────────────────────────────
function SeccionEnvio({ envio, entrada }: { envio?: EnvioExp | null; entrada?: Expediente['envio_entrada'] }) {
  const e = envio || (entrada ? { ...entrada, id: entrada.id, estado: entrada.estado } : null);
  if (!e) {
    return (
      <CardSeccion titulo="Despacho" icono={<span>🚚</span>}>
        <p className="text-xs text-yeikar-neutral/50 italic">Este pedido aún no tiene despacho asignado.</p>
      </CardSeccion>
    );
  }
  return (
    <CardSeccion titulo={`Despacho${e.guia_despacho ? ` · Guía ${e.guia_despacho}` : ''}`} icono={<span>🚚</span>} estado={e.estado} dominio="envio">
      <div className="grid grid-cols-2 sm:grid-cols-4 gap-3">
        <Fila k="Chofer" v={e.chofer} />
        <Fila k="Asignado por" v={e.asignado_por} />
        <Fila k="Salida" v={fmtFechaHora(e.fecha_salida)} />
        <Fila k="Entrega" v={fmtFechaHora(e.fecha_entrega)} />
      </div>
      {e.direccion_entrega && (
        <p className="mt-2 text-xs text-yeikar-neutral/60 bg-yeikar-tertiary/30 rounded-lg px-3 py-2">
          📍 {e.direccion_entrega}
        </p>
      )}
      {e.ubicaciones && e.ubicaciones.length > 0 && (
        <p className="mt-2 text-[11px] text-yeikar-neutral/50 font-mono">
          🛰 {e.ubicaciones.length} actualizaciones de ubicación registradas durante el recorrido.
        </p>
      )}
      {e.observaciones && (
        <p className="mt-2 text-[11px] text-yeikar-neutral/55 italic">{e.observaciones}</p>
      )}
    </CardSeccion>
  );
}

// ─────────────────────────────────────────────────────────────────────────
// Auditoría (admin)
// ─────────────────────────────────────────────────────────────────────────
function SeccionAuditoria({ eventos }: { eventos: AuditoriaExp[] }) {
  if (eventos.length === 0) return null;
  const entidadLabel: Record<string, string> = {
    cotizacion: 'Cotización',
    pedido: 'Pedido',
    orden_produccion: 'Orden de producción',
    consumo_material: 'Consumo',
    mano_obra: 'Mano de obra',
    venta: 'Venta',
    pago: 'Pago',
    envio: 'Envío',
    factura: 'Factura',
  };
  return (
    <CardSeccion titulo={`Auditoría (${eventos.length} eventos)`} icono={<span>🕵️</span>}>
      <ol className="space-y-2">
        {eventos.map((ev, i) => (
          <li key={i} className="flex gap-2 text-[11px]">
            <span className="font-mono text-yeikar-neutral/40 shrink-0 w-[92px]">{fmtFechaHora(ev.fecha)}</span>
            <span className="text-yeikar-neutral/80">
              <span className="font-mono font-bold text-yeikar-secondary">{ev.actor || 'el sistema'}</span>
              {' '}
              <span className="text-yeikar-neutral/60">{accionVerbo(ev.accion)}</span>
              {' '}
              <span className="font-semibold text-yeikar-secondary">
                {entidadLabel[ev.entidad] || ev.entidad} #{ev.entidad_id}
              </span>
            </span>
          </li>
        ))}
      </ol>
    </CardSeccion>
  );
}

// ─────────────────────────────────────────────────────────────────────────
// Ficha completa
// ─────────────────────────────────────────────────────────────────────────
export default function ExpedienteFicha({ ficha }: { ficha: Expediente }) {
  const cliente = ficha.cliente;

  const rif = localStorage.getItem('print_company_rif') || 'J-50146039-3';
  const direccion = localStorage.getItem('print_company_address') || 'AV. INTERCOMUNAL CON CALLE 16 LOCAL Nro 15-205, BARRIO SIMÓN BOLÍVAR, UREÑA, TÁCHIRA';
  const telefono = localStorage.getItem('print_company_phone') || '+58 412-1234567';

  return (
    <div className="space-y-4">
      {/* Encabezado del cliente */}
      <div className="bg-gradient-to-r from-yeikar-secondary to-yeikar-secondary-light rounded-2xl p-5 text-white shadow-sm">
        <p className="font-mono text-[10px] uppercase tracking-widest text-white/50">Expediente</p>
        <h2 className="font-headline font-black text-xl mt-0.5">{cliente?.nombre || 'Cliente'}</h2>
        <div className="flex flex-wrap gap-x-4 gap-y-1 mt-2 text-xs text-white/70 font-mono">
          {cliente?.cedula && <span>C.I.: {cliente.cedula}</span>}
          {cliente?.telefono && <span>📞 {cliente.telefono}</span>}
          {cliente?.ciudad && <span>📍 {cliente.ciudad}</span>}
          {ficha.cotizacion && <span>Cotización #{ficha.cotizacion.id}</span>}
          {ficha.pedido && <span>Pedido #{ficha.pedido.id}</span>}
          {ficha.venta && <span>Venta #{ficha.venta.id}</span>}
          {ficha.envio && <span>Envío #{ficha.envio.id}</span>}
        </div>
      </div>

      {ficha.cotizacion && (
        <SeccionCotizacion cot={ficha.cotizacion} />
      )}

      {/* Documento de la cotización visible de una (solo lectura, sin descarga) */}
      {ficha.cotizacion && (
        <div className="bg-stone-100 border border-yeikar-secondary-light/10 rounded-2xl p-4 overflow-x-auto">
          <p className="font-mono text-[10px] font-bold uppercase tracking-widest text-yeikar-neutral/45 mb-3 flex items-center gap-2">
            <svg className="w-4 h-4" fill="none" stroke="currentColor" viewBox="0 0 24 24">
              <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M15 12a3 3 0 11-6 0 3 3 0 016 0z" />
              <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M2.458 12C3.732 7.943 7.523 5 12 5c4.478 0 8.268 2.943 9.542 7-1.274 4.057-5.064 7-9.542 7-4.477 0-8.268-2.943-9.542-7z" />
            </svg>
            Documento tal como se imprime
            <span className="text-yeikar-neutral/35 font-normal">· solo lectura</span>
          </p>
          <DocumentoCotizacion
            className="min-w-[816px]"
            cotizacion={{
              id: ficha.cotizacion.id,
              fecha: ficha.cotizacion.fecha,
              moneda_codigo: ficha.cotizacion.moneda,
              tasa_cambio: ficha.cotizacion.tasa_cambio,
              total_estimado: ficha.cotizacion.total_estimado,
              cliente,
              detalles: ficha.cotizacion.detalles.map((d) => ({
                producto_id: d.producto_id,
                producto_nombre: d.producto_nombre,
                cantidad: d.cantidad,
                precio: d.precio,
                ancho: d.dimensiones?.ancho,
                largo: d.dimensiones?.largo,
                observaciones: d.observaciones,
                foto: d.fotos?.[0]?.url ?? null,
              })),
            }}
            rif={rif}
            direccion={direccion}
            telefono={telefono}
            venta={ficha.venta ? {
              total_pagado: ficha.venta.total_pagado,
              saldo_pendiente: ficha.venta.saldo_pendiente,
              pagos: ficha.venta.pagos.map((p) => ({
                id: p.id,
                fecha: p.fecha,
                metodo_pago: p.metodo_pago,
                referencia: p.referencia,
                monto: p.monto,
                moneda: { codigo: p.moneda, simbolo: p.moneda === 'VES' ? 'Bs' : p.moneda === 'EUR' ? '€' : '$' },
                monto_en_moneda_base: p.monto_en_moneda_base,
                tasa_cambio: p.tasa_cambio,
              })),
            } : undefined}
          />
        </div>
      )}
      <SeccionPedido exp={ficha} />
      <SeccionProduccion detalles={ficha.detalles_pedido} />
      <SeccionVenta venta={ficha.venta} />
      <SeccionGastos gastos={ficha.gastos} />
      <SeccionFacturas facturas={ficha.facturas} entrada={ficha.factura_entrada} />
      <SeccionEnvio envio={ficha.envio} entrada={ficha.envio_entrada} />
      <SeccionAuditoria eventos={ficha.auditoria} />
    </div>
  );
}