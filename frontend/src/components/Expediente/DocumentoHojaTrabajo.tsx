import React from 'react';
import type { ReferenciaReceta } from '../../services/produccionService';

interface Props {
  hoja: ReferenciaReceta;
  containerId?: string;
  className?: string;
}

const fmt = (n: number) =>
  Number(n).toLocaleString('es-ES', { maximumFractionDigits: 2 });

const fmtFecha = (iso?: string | null) => {
  if (!iso) return null;
  const d = new Date(`${iso}T12:00:00`);
  return isNaN(d.getTime()) ? iso : d.toLocaleDateString('es-ES', { day: '2-digit', month: 'long', year: 'numeric' });
};

/**
 * Documento HOJA DE TRABAJO YEIKAR — Guía técnica imprimible para operarios de taller.
 *
 * Principios de UX y diseño:
 * - Identidad Yeikar 100%: Dorado (#D4AF37), Ébano artesanal (#2D1B10), Marfil (#F9F7F2) y Neutros carbón.
 * - Sin montos comerciales: exclusivo para fabricación y control de planta.
 * - Hero equilibrado: Especificaciones críticas (dimensiones en mono de gran legibilidad,
 *   color, acabado, cantidad) junto a la foto de referencia proporcionada para que todo
 *   el paquete principal quepa de manera armónica en 1 sola página tamaño carta.
 * - Observaciones críticas destacadas para evitar errores de corte y confección.
 * - Checklist de materiales de la sección con casillas para tilde manual y desglose de corte.
 * - Bloque de notas de taller y control de calidad con doble firma.
 * - Cortes de página inteligentes mediante data-pdf-item="true" (ver utils/pdfCaptura.ts).
 */
export default function DocumentoHojaTrabajo({ hoja, containerId, className = '' }: Props) {
  const seccion = hoja.seccion_actual || hoja.area_nombre || null;
  const deSeccion = seccion ? hoja.materiales.filter((m) => m.seccion === seccion) : [];
  const mats = deSeccion.length ? deSeccion : hoja.materiales;
  const tituloMateriales = seccion
    ? `Materiales e Insumos — ${seccion}`
    : 'Materiales e Insumos del Mueble';

  const fotos = (hoja.producto_fotos || []).filter((f) => f.url);

  const observaciones = [
    { tipo: 'PEDIDO', etiqueta: 'Del pedido', texto: hoja.observaciones_pedido },
    { tipo: 'MUEBLE', etiqueta: 'Del mueble / diseño', texto: hoja.descripcion_especifica || hoja.observaciones_detalle },
    { tipo: 'ETAPA', etiqueta: `De esta etapa (${seccion || 'taller'})`, texto: hoja.etapa_observaciones },
  ].filter((o) => o.texto && o.texto.trim());

  const ancho = hoja.dimensiones?.ancho;
  const largo = hoja.dimensiones?.largo;
  const fechaHoy = new Date().toLocaleDateString('es-ES', { day: '2-digit', month: '2-digit', year: 'numeric' });
  const horaHoy = new Date().toLocaleTimeString('es-ES', { hour: '2-digit', minute: '2-digit' });

  return (
    <div
      id={containerId}
      className={`bg-white shadow-2xl relative text-stone-800 font-sans mx-auto ${className}`}
      style={{
        width: '215.9mm',
        minHeight: '279.4mm',
        padding: '11mm 13mm',
        boxSizing: 'border-box',
        display: 'flex',
        flexDirection: 'column',
      }}
    >
      {/* Marca de agua institucional Yeikar */}
      <div className="absolute inset-0 flex items-center justify-center pointer-events-none opacity-[0.035] z-0 select-none">
        <img src="/logo-marca-de-agua.PNG" alt="" className="w-[440px] h-auto" />
      </div>

      <div className="relative z-10 flex flex-col gap-2.5 flex-1">
        {/* ── 1. ENCABEZADO INSTITUCIONAL UNIFICADO ── */}
        <div className="flex justify-between items-start pb-2.5 border-b border-stone-300">
          <div className="flex items-center gap-3">
            <img src="/Logo-yeikar.png" alt="Yeikar" className="h-11 object-contain" />
            <div className="space-y-0.5">
              <div className="font-serif font-black text-stone-900 text-[11.5px] tracking-widest uppercase">
                Comercializadora Yeikar
              </div>
              <div className="text-[7.5px] text-[#A58421] font-mono font-bold uppercase tracking-wider">
                Control de Producción · Hoja Técnica de Taller
              </div>
              <div className="text-[7px] text-stone-400 font-mono">
                Documento técnico interno — prohibida su alteración o uso comercial
              </div>
            </div>
          </div>

          {/* Tarjeta de Orden y Control */}
          <div className="text-right border border-stone-300 rounded-xl px-3 py-2 bg-stone-50/90 shadow-xs min-w-[195px]">
            <div className="text-[7.5px] font-black text-stone-500 uppercase tracking-[0.2em]">
              Hoja de Trabajo
            </div>
            <div className="text-sm font-black text-[#8C6D1F] font-mono tracking-wider mt-0.5">
              ORDEN N° 00 – {String(hoja.orden_id ?? 0).padStart(5, '0')}
            </div>
            <div className="flex items-center justify-end gap-1.5 mt-0.5">
              {hoja.pedido_id != null ? (
                <span className="text-[8.5px] text-stone-700 font-mono font-bold">
                  Pedido N° {String(hoja.pedido_id).padStart(5, '0')}
                </span>
              ) : (
                <span className="text-[7.5px] font-mono font-bold uppercase px-1.5 py-0.2 rounded bg-stone-200 text-stone-700">
                  Exhibición / Stock
                </span>
              )}
            </div>
            <div className="text-[7px] text-stone-400 font-mono mt-0.5 uppercase tracking-wider">
              Emitida: {fechaHoy} {horaHoy}
            </div>
          </div>
        </div>

        {/* ── 2. BANDA DE SECCIÓN Y COMPROMISO DE ENTREGA ── */}
        <div className="bg-[#2D1B10] text-[#F9F7F2] rounded-xl px-4 py-2 flex items-center justify-between border-b-2 border-[#D4AF37] shadow-xs">
          <div className="flex items-center gap-2.5">
            <div className="w-2 h-2 rounded-full bg-[#D4AF37] animate-pulse" />
            <div>
              <div className="text-[7px] uppercase tracking-[0.22em] text-[#D4AF37] font-mono font-bold">
                Área / Sección de Trabajo
              </div>
              <div className="text-base font-black font-headline tracking-wide uppercase text-white leading-tight">
                {seccion || 'Taller General'}
              </div>
            </div>
            {hoja.etapa_id && (
              <span className="ml-2 text-[7.5px] font-mono font-bold px-2 py-0.5 rounded bg-white/10 text-stone-200 border border-white/15">
                Etapa #{hoja.etapa_id}
              </span>
            )}
          </div>
          <div className="text-right">
            <div className="text-[7px] uppercase tracking-[0.16em] text-stone-300 font-mono font-bold">
              Fecha Compromiso de Entrega
            </div>
            <div className="font-mono font-black text-[#E5C560] text-[12px] leading-tight mt-0.5">
              {fmtFecha(hoja.fecha_entrega_estimada) || 'POR DEFINIR'}
            </div>
          </div>
        </div>

        {/* ── 3. HERO EQUILIBRADO: FICHA TÉCNICA + FOTO DE REFERENCIA ── */}
        <div className="grid grid-cols-12 gap-3 items-stretch">
          {/* Columna Izquierda: Ficha de Fabricación (7 cols) */}
          <div className="col-span-7 border border-stone-300 rounded-xl p-3 bg-stone-50/50 flex flex-col justify-between">
            <div>
              <div className="flex items-center justify-between">
                <span className="text-[7.5px] font-mono font-bold uppercase tracking-widest text-stone-400">
                  Producto a Fabricar
                </span>
                <span className="text-[8px] font-mono font-black px-2 py-0.5 rounded-full bg-[#2D1B10] text-[#F9F7F2]">
                  {fmt(hoja.cantidad ?? 1)} {(hoja.cantidad ?? 1) === 1 ? 'UNIDAD' : 'UNIDADES'}
                </span>
              </div>
              <h3 className="font-headline font-black text-stone-900 text-[15px] leading-tight mt-1">
                {hoja.producto_nombre}
              </h3>

              {/* Dimensiones de Fabricación — Números grandes y nítidos para taller */}
              <div className="bg-white border-2 border-stone-800 rounded-lg p-2.5 my-2.5 shadow-xs">
                <div className="flex items-center justify-between text-[7px] font-mono font-black tracking-wider text-stone-500 uppercase mb-1">
                  <span>Dimensiones de Fabricación (Ancho × Largo)</span>
                  <span className="text-[#8C6D1F]">Corte Estructural</span>
                </div>
                <div className="flex items-baseline gap-2">
                  {ancho != null && largo != null ? (
                    <>
                      <span className="font-mono font-black text-stone-950 text-[17px] tracking-tight">
                        {fmt(ancho)} × {fmt(largo)} m
                      </span>
                      <span className="font-mono font-bold text-[#8C6D1F] text-[10.5px] bg-[#D4AF37]/10 px-1.5 py-0.5 rounded border border-[#D4AF37]/30">
                        {Math.round(ancho * 100)} × {Math.round(largo * 100)} cm
                      </span>
                    </>
                  ) : (
                    <span className="text-[10px] text-stone-500 italic font-medium">
                      Dimensiones estándar según plano de catálogo
                    </span>
                  )}
                </div>
              </div>
            </div>

            {/* Grid de Especificaciones Auxiliares */}
            <div className="grid grid-cols-2 gap-2 pt-1 border-t border-stone-200 text-[8.5px]">
              <div>
                <span className="text-[7px] font-mono uppercase font-bold text-stone-400 block">Cliente / Destino</span>
                <span className="font-bold text-stone-900 truncate block" title={hoja.cliente_nombre || 'Exhibición'}>
                  {hoja.cliente_nombre || 'Exhibición / Showroom'}
                </span>
                {hoja.cliente_telefono && (
                  <span className="text-[7.5px] font-mono text-stone-500 block">Tel. {hoja.cliente_telefono}</span>
                )}
              </div>
              <div>
                <span className="text-[7px] font-mono uppercase font-bold text-stone-400 block">Color / Tapizado</span>
                <span className="font-bold text-stone-900 block truncate" title={hoja.color || 'Estándar'}>
                  {hoja.color || 'Estándar de fábrica'}
                </span>
              </div>
              <div>
                <span className="text-[7px] font-mono uppercase font-bold text-stone-400 block">Acabado / Brillo</span>
                <span className="font-bold text-stone-900 block truncate" title={hoja.acabado || 'Estándar'}>
                  {hoja.acabado || 'Estándar de catálogo'}
                </span>
              </div>
              <div>
                <span className="text-[7px] font-mono uppercase font-bold text-stone-400 block">Control de Calidad</span>
                <span className="font-mono font-semibold text-stone-600 block">Verificar tolerancias ±2mm</span>
              </div>
            </div>
          </div>

          {/* Columna Derecha: Foto de Referencia (5 cols) */}
          <div className="col-span-5 border border-stone-300 rounded-xl overflow-hidden bg-white shadow-xs flex flex-col justify-between">
            <div className="bg-[#2D1B10] text-[#F9F7F2] text-[7.5px] font-mono font-bold uppercase tracking-[0.18em] px-2.5 py-1 flex items-center justify-between">
              <span>Foto de Referencia</span>
              <span className="text-[#D4AF37]">Guía Visual</span>
            </div>
            {fotos[0] ? (
              <div
                className="flex-1 flex items-center justify-center p-1.5 bg-white overflow-hidden"
                style={{ minHeight: '62mm', maxHeight: '68mm' }}
              >
                <img
                  src={fotos[0].url}
                  alt={hoja.producto_nombre}
                  className="w-full h-full object-contain rounded-md"
                  style={{ maxHeight: '66mm' }}
                />
              </div>
            ) : (
              <div
                className="flex-1 flex flex-col items-center justify-center p-4 bg-stone-50 text-center"
                style={{ minHeight: '62mm', maxHeight: '68mm' }}
              >
                <svg className="w-8 h-8 text-stone-300 mb-1" fill="none" stroke="currentColor" viewBox="0 0 24 24">
                  <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={1.5} d="M4 16l4.586-4.586a2 2 0 012.828 0L16 16m-2-2l1.586-1.586a2 2 0 012.828 0L20 14m-6-6h.01M6 20h12a2 2 0 002-2V6a2 2 0 00-2-2H6a2 2 0 00-2 2v12a2 2 0 002 2z" />
                </svg>
                <span className="text-[8.5px] font-mono font-bold uppercase text-stone-400 tracking-wider">
                  Sin foto adjunta
                </span>
                <span className="text-[7.5px] text-stone-400 mt-0.5">
                  Fabricar según dimensiones y receta técnica
                </span>
              </div>
            )}
            <div className="bg-stone-50 border-t border-stone-200 px-2.5 py-0.5 text-[6.5px] text-stone-400 font-mono text-center uppercase tracking-wider">
              Referencia estética de acabados y forma
            </div>
          </div>
        </div>

        {/* ── 4. OBSERVACIONES Y ESPECIFICACIONES CRÍTICAS ── */}
        <div data-pdf-item="true">
          {observaciones.length > 0 ? (
            <div className="border-l-4 border-[#D4AF37] border-y border-r border-stone-200 rounded-r-xl p-2.5 bg-[#FDFBF7] shadow-xs">
              <div className="text-[8px] font-black uppercase tracking-[0.16em] text-[#8C6D1F] mb-1.5 flex items-center gap-1.5">
                <svg className="w-3 h-3 text-[#D4AF37]" fill="none" stroke="currentColor" viewBox="0 0 24 24">
                  <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2.2} d="M12 9v2m0 4h.01M5 19h14a2 2 0 001.84-2.75L13.74 4a2 2 0 00-3.5 0l-7.1 12.25A2 2 0 005 19z" />
                </svg>
                <span>Especificaciones y Observaciones Críticas de Producción (Leer antes de iniciar)</span>
              </div>
              <div className="space-y-1">
                {observaciones.map((o) => (
                  <div key={o.etiqueta} className="text-[9.5px] leading-snug text-stone-800 flex items-baseline gap-2">
                    <span className="text-[7px] font-mono font-black uppercase px-1.5 py-0.2 rounded bg-[#D4AF37]/15 text-[#8C6D1F] border border-[#D4AF37]/30 shrink-0">
                      {o.etiqueta}
                    </span>
                    <span className="font-semibold text-stone-900 whitespace-pre-line">{o.texto}</span>
                  </div>
                ))}
              </div>
            </div>
          ) : (
            <div className="border border-stone-200 rounded-lg px-3 py-1 bg-stone-50/50 flex items-center justify-between text-[7.5px] font-mono text-stone-500">
              <div className="flex items-center gap-1.5">
                <span className="w-1.5 h-1.5 rounded-full bg-emerald-600" />
                <span>Sin notas u observaciones especiales registradas para esta orden (fabricación estándar).</span>
              </div>
              <span className="text-stone-400">Verificar tolerancias con supervisor</span>
            </div>
          )}
        </div>

        {/* ── 5. LISTA DE MATERIALES E INSUMOS (CHECKLIST DE TALLER) ── */}
        <div data-pdf-item="true">
          <div className="flex items-center justify-between mb-1">
            <div className="flex items-center gap-2">
              <h4 className="text-[9px] font-black uppercase tracking-[0.16em] text-stone-900">
                {tituloMateriales}
              </h4>
              <span className="text-[7.5px] font-mono font-bold text-stone-600 bg-stone-100 px-1.5 py-0.2 rounded border border-stone-200">
                {mats.length} {mats.length === 1 ? 'ítem' : 'ítems'}
              </span>
            </div>
            <span className="text-[7px] font-mono text-stone-400 italic">
              Casilla [✓] para control de almacén y taller
            </span>
          </div>

          {mats.length > 0 ? (
            <div className="border border-stone-300 rounded-lg overflow-hidden shadow-xs">
              <table className="w-full text-[9px] border-collapse">
                <thead>
                  <tr className="bg-[#2D1B10] text-[#F9F7F2] text-[7.5px] font-mono font-bold uppercase tracking-wider">
                    <th className="px-2 py-1.5 text-center border-r border-stone-700 w-8">✓</th>
                    <th className="px-2 py-1.5 text-left border-r border-stone-700">Material / Insumo</th>
                    <th className="px-2 py-1.5 text-center border-r border-stone-700 w-12">Unid.</th>
                    <th className="px-2 py-1.5 text-center border-r border-stone-700 w-24">Cant. Esperada</th>
                    <th className="px-2 py-1.5 text-left">Detalle de Corte / Especificación</th>
                  </tr>
                </thead>
                <tbody>
                  {mats.map((m, idx) => (
                    <tr
                      key={m.material_id}
                      data-pdf-item="true"
                      className={`border-b border-stone-200 ${
                        idx % 2 === 0 ? 'bg-white' : 'bg-stone-50/60'
                      } ${m.condicion_cumplida ? '' : 'opacity-50'}`}
                    >
                      {/* Casilla de verificación amplia */}
                      <td className="px-2 py-1 text-center border-r border-stone-200">
                        <div className="w-3.5 h-3.5 border-2 border-stone-400 rounded-sm inline-block bg-white shadow-xs" />
                      </td>

                      {/* Nombre del material */}
                      <td className="px-2 py-1 font-bold text-stone-900 border-r border-stone-200">
                        <span>{m.nombre}</span>
                        {!m.condicion_cumplida && (
                          <span className="ml-1.5 text-[6.5px] font-mono font-black uppercase text-stone-400 bg-stone-100 px-1 py-0.2 rounded border border-stone-200">
                            (Si aplica)
                          </span>
                        )}
                      </td>

                      {/* Unidad */}
                      <td className="px-2 py-1 text-center font-mono font-semibold text-stone-600 border-r border-stone-200">
                        {m.unidad || '—'}
                      </td>

                      {/* Cantidad esperada */}
                      <td className="px-2 py-1 text-center font-mono font-black text-stone-950 text-[10.5px] border-r border-stone-200">
                        {fmt(m.cantidad_esperada)}
                        {m.cantidad_esperada !== m.cantidad_base && (
                          <span className="block text-[6.5px] font-normal text-stone-400 font-mono leading-none">
                            base {fmt(m.cantidad_base)}
                          </span>
                        )}
                      </td>

                      {/* Detalle de corte o escala */}
                      <td className="px-2 py-1 text-stone-700 text-[8.5px]">
                        {m.es_corte ? (
                          <span className="inline-flex items-center gap-1 font-mono font-semibold text-stone-900 bg-amber-50 px-1.5 py-0.5 rounded border border-amber-200/80">
                            <span>✂</span>
                            <span>
                              {m.cortes_por_lamina ?? '—'} corte(s) de {fmt(m.ancho_corte_cm ?? 0)} × {fmt(m.largo_corte_cm ?? 0)} cm
                            </span>
                            <span className="text-stone-500 font-normal">
                              ≈ {m.laminas_equivalentes ? fmt(m.laminas_equivalentes) : '—'} lám.
                            </span>
                          </span>
                        ) : m.tipo_escala !== 'FIJO' ? (
                          <span className="font-mono text-stone-600">
                            Escala paramétrica {m.tipo_escala.toLowerCase()}
                          </span>
                        ) : (
                          <span className="text-stone-400 font-mono text-[7.5px]">Consumo fijo estándar</span>
                        )}
                      </td>
                    </tr>
                  ))}
                </tbody>
              </table>
            </div>
          ) : (
            <div className="border border-dashed border-stone-300 rounded-lg p-3 text-center bg-stone-50/50">
              <span className="text-[8.5px] text-stone-500 font-mono">
                Esta sección no tiene materiales directos registrados en receta (etapa de ensamble, mano de obra o ajuste).
              </span>
            </div>
          )}
        </div>

        {/* ── 6. FOTOS ADICIONALES (SI EXISTEN) ── */}
        {fotos.slice(1).map((f, i) => (
          <div key={i} data-pdf-item="true" className="border border-stone-300 rounded-xl overflow-hidden bg-white shadow-xs mt-1">
            <div className="bg-[#2D1B10] text-[#F9F7F2] text-[7.5px] font-mono font-bold uppercase tracking-[0.18em] px-3 py-1 flex items-center justify-between">
              <span>Vista Adicional {i + 2}</span>
              <span className="text-[#D4AF37]">{f.nombre || hoja.producto_nombre}</span>
            </div>
            <div className="flex items-center justify-center bg-white p-2" style={{ maxHeight: '80mm' }}>
              <img
                src={f.url}
                alt={`${hoja.producto_nombre} vista ${i + 2}`}
                className="w-full object-contain"
                style={{ maxHeight: '76mm' }}
              />
            </div>
          </div>
        ))}

        {/* ── 7. CONTROL Y NOTAS DEL OPERARIO EN TALLER ── */}
        <div data-pdf-item="true" className="mt-1 pt-1">
          <div className="flex items-center justify-between mb-1">
            <span className="text-[7.5px] font-mono font-black uppercase tracking-[0.16em] text-stone-500">
              Anotaciones de Taller / Incidencias del Operario
            </span>
            <span className="text-[6.5px] font-mono text-stone-400 uppercase">
              Registrar variaciones o ajustes realizados
            </span>
          </div>
          <div className="space-y-2">
            <div className="border-b border-dotted border-stone-300 h-4" />
            <div className="border-b border-dotted border-stone-300 h-4" />
          </div>
        </div>

        {/* ── 8. PROTOCOLO DE FIRMAS Y CONTROL DE CALIDAD ── */}
        <div data-pdf-item="true" className="mt-auto pt-3 grid grid-cols-2 gap-8">
          {/* Operario Responsable */}
          <div className="border-t-2 border-stone-800 pt-1.5 flex flex-col justify-between min-h-[14mm]">
            <div className="flex items-center justify-between text-[7.5px] font-mono font-black text-stone-800 uppercase">
              <span>Fabricado por — Operario Responsable</span>
              <span className="text-stone-400 font-normal">Firma</span>
            </div>
            <div className="text-[7px] text-stone-500 font-mono flex items-center justify-between mt-3">
              <span>Nombre y C.I.: __________________________</span>
              <span>Fecha: _____/_____/202___</span>
            </div>
          </div>

          {/* Supervisor / Control de Calidad */}
          <div className="border-t-2 border-stone-800 pt-1.5 flex flex-col justify-between min-h-[14mm]">
            <div className="flex items-center justify-between text-[7.5px] font-mono font-black text-stone-800 uppercase">
              <span>Supervisor / Control de Calidad</span>
              <div className="flex items-center gap-2 font-mono font-bold text-[7px] text-stone-600">
                <span>[ ] Conforme</span>
                <span>[ ] Con Ajuste</span>
              </div>
            </div>
            <div className="text-[7px] text-stone-500 font-mono flex items-center justify-between mt-3">
              <span>Firma y Sello de Validación</span>
              <span>Fecha Aprobación: _____/_____/202___</span>
            </div>
          </div>
        </div>

        {/* ── 9. PIE DE PÁGINA TÉCNICO ── */}
        <div className="pt-1 flex justify-between items-center text-[6.5px] font-mono text-stone-400 border-t border-stone-200 mt-1">
          <span>COMERCIALIZADORA YEIKAR · SISTEMA DE GESTIÓN DE PRODUCCIÓN</span>
          <span>ORDEN #{hoja.orden_id ?? '—'} · ETAPA #{hoja.etapa_id ?? '—'}</span>
          <span>EXPEDIENTE TÉCNICO DE PLANTA</span>
        </div>
      </div>
    </div>
  );
}
