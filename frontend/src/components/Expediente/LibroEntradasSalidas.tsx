import { Fragment, useEffect, useMemo, useRef, useState } from 'react';
import { FileDown } from 'lucide-react';
import { EmptyState, Spinner, Tabs } from '../ui';
import { useDebouncedValue } from '../../hooks/useDebouncedValue';
import { useAuth } from '../../context/AuthContext';
import { inventarioService } from '../../services/inventarioService';
import { productosService } from '../../services/productosService';
import type { LibroEntradasSalidas, LibroFila } from '../../services/inventarioService';
import { reportesService } from '../../services/reportesService';
import type { MovimientoCaja } from '../../services/reportesService';
import { extractErrorMessage, formatCurrency } from '../../utils/format';
import { fmtFechaVE } from '../../utils/fechas';

type Lado = 'ENTRADAS' | 'SALIDAS';
type Dominio = 'INVENTARIO' | 'DINERO';
type Periodo = 'dia' | 'semana' | 'mes';
type Agrupar = 'dia' | 'semana' | 'mes';
type GrupoInv = 'INSUMOS' | 'PLASTICOS' | 'REVENTA' | 'CRUDO';

interface BookDef {
  key: string;
  label: string;
  lado: Lado;
  dominio: Dominio;
}

// Los 4 libros: entradas/salidas de inventario y de dinero.
const BOOKS: BookDef[] = [
  { key: 'entradas-inventario', label: 'Entradas de Inventario', lado: 'ENTRADAS', dominio: 'INVENTARIO' },
  { key: 'salidas-inventario', label: 'Salidas de Inventario', lado: 'SALIDAS', dominio: 'INVENTARIO' },
  { key: 'entradas-dinero', label: 'Entradas de Dinero', lado: 'ENTRADAS', dominio: 'DINERO' },
  { key: 'salidas-dinero', label: 'Salidas de Dinero', lado: 'SALIDAS', dominio: 'DINERO' },
];

const ZONAS = [
  { valor: '', label: 'Todas las zonas' },
  { valor: 'EBANISTERIA', label: 'Ebanistería' },
  { valor: 'PREPARACION', label: 'Preparación' },
  { valor: 'PINTURA', label: 'Pintura' },
  { valor: 'TAPICERIA', label: 'Tapicería' },
  { valor: 'VIDRIERIA', label: 'Vidriería' },
  { valor: 'TERMINACION', label: 'Terminación' },
  { valor: 'OFICINA', label: 'Oficina' },
  { valor: 'GENERAL', label: 'General (sin zona)' },
];

const TIPO_MOV_LABEL: Record<string, string> = {
  ENTRADA: 'Entrada',
  SALIDA: 'Salida',
  DEVOLUCION: 'Devolución',
  DANO: 'Daño',
};

// Los "tres inventarios" del libro (más crudo): Insumos — con la zona del
// taller como filtro opcional — y los productos separados por su categoría
// (Plásticos) o su tipo (Reventa: electrodomésticos y colchones).
const GRUPOS_INV: { valor: GrupoInv; label: string }[] = [
  { valor: 'INSUMOS', label: 'Insumos' },
  { valor: 'PLASTICOS', label: 'Plásticos' },
  { valor: 'REVENTA', label: 'Reventa (electrodomésticos y colchones)' },
  { valor: 'CRUDO', label: 'Crudo' },
];

// "PLÁSTICOS" → "PLASTICOS": compara nombres de catálogo sin tildes.
const normNombre = (valor: string) =>
  valor.toUpperCase().normalize('NFD').replace(/[\u0300-\u036f]/g, '');

const TIPO_MOV_ESTILO: Record<string, string> = {
  ENTRADA: 'bg-emerald-50 text-emerald-700 border-emerald-200',
  SALIDA: 'bg-amber-50 text-amber-700 border-amber-200',
  DEVOLUCION: 'bg-sky-50 text-sky-700 border-sky-200',
  DANO: 'bg-red-50 text-red-700 border-red-200',
};

const ITEM_TIPO_LABEL: Record<string, string> = {
  MATERIAL: 'Insumo',
  PRODUCTO: 'Producto',
  CRUDO: 'Crudo',
};

const MESES = [
  'enero', 'febrero', 'marzo', 'abril', 'mayo', 'junio',
  'julio', 'agosto', 'septiembre', 'octubre', 'noviembre', 'diciembre',
];

const inputCls =
  'border border-yeikar-secondary-light/20 rounded-xl px-3 py-2 text-xs text-yeikar-secondary bg-white focus:outline-none focus:border-yeikar-primary/50';

const fmtCosto = (n: number) => `$ ${Number(n).toLocaleString('es-ES', { maximumFractionDigits: 2 })}`;

const isoLocal = (d: Date) =>
  `${d.getFullYear()}-${String(d.getMonth() + 1).padStart(2, '0')}-${String(d.getDate()).padStart(2, '0')}`;

function rangoDePeriodo(periodo: Periodo): { desde: string; hasta: string } {
  const hoy = new Date();
  if (periodo === 'dia') return { desde: isoLocal(hoy), hasta: isoLocal(hoy) };
  if (periodo === 'semana') {
    const lunes = new Date(hoy);
    lunes.setDate(hoy.getDate() - ((hoy.getDay() + 6) % 7));
    const domingo = new Date(lunes);
    domingo.setDate(lunes.getDate() + 6);
    return { desde: isoLocal(lunes), hasta: isoLocal(domingo) };
  }
  const primero = new Date(hoy.getFullYear(), hoy.getMonth(), 1);
  const ultimo = new Date(hoy.getFullYear(), hoy.getMonth() + 1, 0);
  return { desde: isoLocal(primero), hasta: isoLocal(ultimo) };
}

function grupoDeFecha(fecha: string, agrupar: Agrupar): { clave: string; label: string } {
  const d = new Date(`${fecha.slice(0, 10)}T12:00:00`);
  if (agrupar === 'mes') {
    return {
      clave: `${d.getFullYear()}-${String(d.getMonth() + 1).padStart(2, '0')}`,
      label: `${MESES[d.getMonth()]} ${d.getFullYear()}`,
    };
  }
  if (agrupar === 'semana') {
    const lunes = new Date(d);
    lunes.setDate(d.getDate() - ((d.getDay() + 6) % 7));
    const domingo = new Date(lunes);
    domingo.setDate(lunes.getDate() + 6);
    return { clave: isoLocal(lunes), label: `Semana del ${fmtFechaVE(lunes)} al ${fmtFechaVE(domingo)}` };
  }
  return { clave: fecha.slice(0, 10), label: fmtFechaVE(fecha) };
}

function agruparPor<T extends { fecha: string }>(
  filas: T[],
  agrupar: Agrupar,
): { clave: string; label: string; filas: T[] }[] {
  const mapa = new Map<string, { clave: string; label: string; filas: T[] }>();
  for (const fila of filas) {
    const { clave, label } = grupoDeFecha(fila.fecha, agrupar);
    const grupo = mapa.get(clave) ?? { clave, label, filas: [] };
    grupo.filas.push(fila);
    mapa.set(clave, grupo);
  }
  return [...mapa.values()].sort((a, b) => (a.clave < b.clave ? 1 : -1));
}

function BadgeTipo({ tipo }: { tipo: string }) {
  const estilo = TIPO_MOV_ESTILO[tipo] ?? 'bg-slate-50 text-slate-600 border-slate-200';
  return (
    <span className={`inline-block px-1.5 py-0.5 rounded-full border text-[10px] font-bold whitespace-nowrap ${estilo}`}>
      {TIPO_MOV_LABEL[tipo] ?? tipo}
    </span>
  );
}

function ChipResumen({ label, tono = 'normal' }: { label: string; tono?: 'normal' | 'suave' | 'alerta' }) {
  const cls =
    tono === 'alerta'
      ? 'border-amber-300 text-amber-800 bg-amber-50'
      : tono === 'suave'
        ? 'border-yeikar-secondary-light/10 text-yeikar-neutral/50 bg-white'
        : 'border-yeikar-secondary-light/15 text-yeikar-secondary bg-yeikar-tertiary/40';
  return <span className={`px-2.5 py-1 rounded-full border text-[11px] font-mono font-bold ${cls}`}>{label}</span>;
}

// Guion para las celdas donde la entrada no trajo ese dato.
function Guion() {
  return <span className="text-yeikar-neutral/30">—</span>;
}

// Texto libre en una celda del libro: se corta con "…" y el valor completo
// queda disponible en el tooltip (title).
function CeldaTexto({ valor, ancho = 120 }: { valor?: string | null; ancho?: number }) {
  if (!valor) return <Guion />;
  return (
    <span className="block truncate" style={{ maxWidth: ancho }} title={valor}>
      {valor}
    </span>
  );
}

// "Fiar" en el libro: Sí (pend.) / Sí (pag.) según el estado de la deuda.
function EtiquetaFiar({ fila }: { fila: LibroFila }) {
  if (!fila.fiado) return <Guion />;
  const estado =
    fila.fiado_estado === 'PENDIENTE' ? ' (pend.)' : fila.fiado_estado === 'PAGADA' ? ' (pag.)' : '';
  return <span className="whitespace-nowrap text-[11px]">{`Sí${estado}`}</span>;
}

interface GrupoInventario {
  clave: string;
  label: string;
  filas: LibroFila[];
  costo: number;
  sinCosto: number;
}

interface GrupoDinero {
  clave: string;
  label: string;
  filas: MovimientoCaja[];
  porMoneda: Record<string, number>;
}

// ── Tabla del libro de inventario (con subtotales por período y zona) ──
function ContenidoInventario({
  libro,
  grupos,
  lado,
}: {
  libro: LibroEntradasSalidas;
  grupos: GrupoInventario[];
  lado: Lado;
}) {
  // El libro de ENTRADAS muestra como columnas los campos que se llenan al
  // registrar una entrada (precio unitario, llevada, proveedor, cliente, zona,
  // quién trajo, descuento, cuenta de pago, fiar y observaciones). En el libro
  // de salidas solo aplican zona, origen, observaciones y costo.
  const esEntradas = lado === 'ENTRADAS';
  const numColumnas = esEntradas ? 16 : 9;
  if (libro.resumen.movimientos === 0) {
    return (
      <EmptyState
        compact
        title="Sin movimientos"
        description="No hay entradas ni salidas de inventario en el período con los filtros actuales."
      />
    );
  }
  return (
    <>
      <div data-pdf-item="true" className="flex flex-wrap items-center gap-2">
        <ChipResumen label={`${libro.resumen.movimientos} movimientos`} />
        <ChipResumen label={`Costo total: ${fmtCosto(libro.resumen.costo_total)}`} />
        {libro.resumen.movimientos_sin_costo > 0 && (
          <ChipResumen label={`${libro.resumen.movimientos_sin_costo} sin costo`} tono="suave" />
        )}
        {libro.resumen.por_zona.map((z) => (
          <ChipResumen
            key={z.zona}
            label={`${z.label}: ${z.movimientos} mov · ${z.costo > 0 ? fmtCosto(z.costo) : '—'}`}
          />
        ))}
        {libro.truncado && <ChipResumen label="Listado truncado" tono="alerta" />}
      </div>

      <div className="overflow-x-auto">
        <table className="w-full text-left border-collapse text-xs">
          <thead>
            <tr className="text-[10px] uppercase tracking-wider text-yeikar-neutral/45 border-b border-yeikar-secondary-light/10">
              <th className="py-2 pr-1.5 font-bold">Fecha</th>
              <th className="py-2 pr-1.5 font-bold">Tipo</th>
              <th className="py-2 pr-1.5 font-bold">Ítem</th>
              <th className="py-2 pr-1.5 font-bold text-right">Cant.</th>
              {esEntradas && (
                <>
                  <th className="py-2 pr-1.5 font-bold text-right">Precio unit.</th>
                  <th className="py-2 pr-1.5 font-bold text-right">Llevada</th>
                  <th className="py-2 pr-1.5 font-bold">Proveedor</th>
                  <th className="py-2 pr-1.5 font-bold">Cliente</th>
                </>
              )}
              <th className="py-2 pr-1.5 font-bold">Zona</th>
              {esEntradas ? (
                <>
                  <th className="py-2 pr-1.5 font-bold">Recibió</th>
                  <th className="py-2 pr-1.5 font-bold text-right">Desc. %</th>
                  <th className="py-2 pr-1.5 font-bold">Pagó</th>
                  <th className="py-2 pr-1.5 font-bold">Fiar</th>
                </>
              ) : (
                <th className="py-2 pr-1.5 font-bold">Consumió</th>
              )}
              <th className="py-2 pr-1.5 font-bold">Origen</th>
              <th className="py-2 pr-1.5 font-bold">Obs.</th>
              <th className="py-2 font-bold text-right">Costo total</th>
            </tr>
          </thead>
          <tbody>
            {grupos.map((grupo) => (
              <Fragment key={grupo.clave}>
                <tr data-pdf-item="true" className="bg-yeikar-secondary/5">
                  <td colSpan={numColumnas} className="px-2 py-1.5 font-headline font-bold text-yeikar-secondary">
                    {grupo.label}
                    <span className="ml-2 font-mono text-[10px] font-normal text-yeikar-neutral/45">
                      {grupo.filas.length} mov
                      {grupo.costo > 0 ? ` · ${fmtCosto(grupo.costo)}` : ''}
                      {grupo.sinCosto > 0 ? ` · ${grupo.sinCosto} sin costo` : ''}
                    </span>
                  </td>
                </tr>
                {grupo.filas.map((fila) => (
                  <tr key={`${fila.item_tipo}-${fila.id}`} data-pdf-item="true" className="border-b border-yeikar-secondary-light/5">
                    <td className="py-1.5 pr-1.5 font-mono text-[11px] text-yeikar-neutral/60 whitespace-nowrap">
                      {fmtFechaVE(fila.fecha)}
                    </td>
                    <td className="py-1.5 pr-1.5"><BadgeTipo tipo={fila.tipo} /></td>
                    <td className="py-1.5 pr-1.5">
                      <span className="block truncate font-semibold text-yeikar-secondary" style={{ maxWidth: 105 }} title={fila.item_nombre}>
                        {fila.item_nombre}
                      </span>
                      <span className="block text-[10px] text-yeikar-neutral/40">
                        ({[ITEM_TIPO_LABEL[fila.item_tipo] ?? fila.item_tipo, fila.categoria]
                          .filter(Boolean)
                          .join(' · ')})
                      </span>
                    </td>
                    <td className="py-1.5 pr-1.5 text-right font-mono text-[11px]">
                      {Number(fila.cantidad).toLocaleString('es-ES', { maximumFractionDigits: 4 })}
                      {fila.unidad ? ` ${fila.unidad}` : ''}
                    </td>
                    {esEntradas && (
                      <>
                        <td className="py-1.5 pr-1.5 text-right font-mono text-[11px] whitespace-nowrap">
                          {fila.costo_unitario != null ? fmtCosto(fila.costo_unitario) : <Guion />}
                        </td>
                        <td className="py-1.5 pr-1.5 text-right font-mono text-[11px] whitespace-nowrap">
                          {fila.llevada != null ? fmtCosto(fila.llevada) : <Guion />}
                        </td>
                        <td className="py-1.5 pr-1.5"><CeldaTexto valor={fila.proveedor} ancho={80} /></td>
                        <td className="py-1.5 pr-1.5"><CeldaTexto valor={fila.cliente} ancho={80} /></td>
                      </>
                    )}
                    <td className="py-1.5 pr-1.5">
                      <CeldaTexto valor={ZONAS.find((z) => z.valor === fila.zona)?.label ?? fila.zona} ancho={56} />
                    </td>
                    {esEntradas && (
                      <>
                        <td className="py-1.5 pr-1.5"><CeldaTexto valor={fila.recibido_por} ancho={58} /></td>
                        <td className="py-1.5 pr-1.5 text-right font-mono text-[11px] whitespace-nowrap">
                          {fila.descuento != null && fila.descuento > 0 ? `${fila.descuento}%` : <Guion />}
                        </td>
                        <td className="py-1.5 pr-1.5"><CeldaTexto valor={fila.pagado_desde} ancho={68} /></td>
                        <td className="py-1.5 pr-1.5"><EtiquetaFiar fila={fila} /></td>
                      </>
                    )}
                    {!esEntradas && (
                      <td className="py-1.5 pr-1.5"><CeldaTexto valor={fila.consumido_por} ancho={68} /></td>
                    )}
                    <td className="py-1.5 pr-1.5"><CeldaTexto valor={fila.origen} ancho={52} /></td>
                    <td className="py-1.5 pr-1.5">
                      {fila.observaciones ? (
                        <span className="block max-w-[95px] whitespace-normal break-words text-yeikar-neutral/70">
                          {fila.observaciones}
                        </span>
                      ) : (
                        <Guion />
                      )}
                    </td>
                    <td className="py-1.5 text-right font-mono text-[11px] whitespace-nowrap">
                      {fila.costo_total != null ? fmtCosto(fila.costo_total) : <Guion />}
                    </td>
                  </tr>
                ))}
              </Fragment>
            ))}
          </tbody>
        </table>
      </div>

      <p data-pdf-item="true" className="text-[10px] text-yeikar-neutral/45">
        Los ajustes de stock no forman parte del libro (no son entradas ni salidas): se ven en el
        historial de cada insumo en Inventario.
      </p>
    </>
  );
}

// ── Tabla del libro de dinero (con subtotales por período y moneda) ──
function ContenidoDinero({
  movimientos,
  grupos,
  totalesMoneda,
}: {
  movimientos: MovimientoCaja[];
  grupos: GrupoDinero[];
  totalesMoneda: Record<string, number>;
}) {
  if (movimientos.length === 0) {
    return (
      <EmptyState
        compact
        title="Sin movimientos"
        description="No hay movimientos de dinero en el período con los filtros actuales."
      />
    );
  }
  return (
    <>
      <div data-pdf-item="true" className="flex flex-wrap items-center gap-2">
        <ChipResumen label={`${movimientos.length} movimientos`} />
        {Object.entries(totalesMoneda).map(([cod, total]) => (
          <ChipResumen key={cod} label={`${cod}: ${formatCurrency(total, cod)}`} />
        ))}
      </div>

      <div className="overflow-x-auto">
        <table className="w-full text-left border-collapse text-xs">
          <thead>
            <tr className="text-[10px] uppercase tracking-wider text-yeikar-neutral/45 border-b border-yeikar-secondary-light/10">
              <th className="py-2 pr-2 font-bold">Fecha</th>
              <th className="py-2 pr-2 font-bold">Cuenta</th>
              <th className="py-2 pr-2 font-bold">Movimiento</th>
              <th className="py-2 pr-2 font-bold text-right">Monto</th>
              <th className="py-2 pr-2 font-bold">Persona o entidad / Concepto</th>
              <th className="py-2 font-bold">Quién</th>
            </tr>
          </thead>
          <tbody>
            {grupos.map((grupo) => (
              <Fragment key={grupo.clave}>
                <tr data-pdf-item="true" className="bg-yeikar-secondary/5">
                  <td colSpan={6} className="px-2 py-1.5 font-headline font-bold text-yeikar-secondary">
                    {grupo.label}
                    <span className="ml-2 font-mono text-[10px] font-normal text-yeikar-neutral/45">
                      {grupo.filas.length} mov
                      {Object.entries(grupo.porMoneda)
                        .map(([cod, total]) => ` · ${cod}: ${formatCurrency(total, cod)}`)
                        .join('')}
                    </span>
                  </td>
                </tr>
                {grupo.filas.map((movimiento) => (
                  <tr key={movimiento.id} data-pdf-item="true" className="border-b border-yeikar-secondary-light/5">
                    <td className="py-1.5 pr-2 font-mono text-[11px] text-yeikar-neutral/60 whitespace-nowrap">
                      {fmtFechaVE(movimiento.fecha)}
                    </td>
                    <td className="py-1.5 pr-2 font-semibold text-yeikar-secondary">
                      {movimiento.metodo_caja?.nombre || `Cuenta #${movimiento.metodo_caja_id}`}
                    </td>
                    <td className="py-1.5 pr-2">
                      <BadgeTipo tipo={movimiento.tipo} />
                    </td>
                    <td className="py-1.5 pr-2 text-right font-mono whitespace-nowrap">
                      {formatCurrency(Number(movimiento.monto), movimiento.moneda?.codigo || 'COP')}
                    </td>
                    <td className="py-1.5 pr-2">
                      <span className="font-semibold text-yeikar-secondary">
                        {movimiento.persona_entidad || '—'}
                      </span>
                      {movimiento.concepto && (
                        <span className="block text-[10px] text-yeikar-neutral/40 max-w-[260px] truncate">
                          {movimiento.concepto}
                        </span>
                      )}
                    </td>
                    <td className="py-1.5 text-yeikar-neutral/60">
                      {movimiento.usuario?.nombre || movimiento.usuario?.nombre_usuario || '—'}
                    </td>
                  </tr>
                ))}
              </Fragment>
            ))}
          </tbody>
        </table>
      </div>

      <p data-pdf-item="true" className="text-[10px] text-yeikar-neutral/45">
        No incluye aperturas ni ajustes de caja (no son entradas ni salidas de operación): se ven
        en Cuentas y en Estado del Día.
      </p>
    </>
  );
}

export default function LibroEntradasSalidas() {
  const { esAdmin, hasModulo } = useAuth();
  const libros = useMemo(
    () =>
      BOOKS.filter((b) =>
        b.dominio === 'INVENTARIO' ? hasModulo('inventario') : esAdmin,
      ),
    [esAdmin, hasModulo],
  );

  const [bookKey, setBookKey] = useState<string>('entradas-inventario');
  const book = libros.find((b) => b.key === bookKey) ?? libros[0];

  const [periodo, setPeriodo] = useState<Periodo | null>('dia');
  const [rango, setRango] = useState(() => rangoDePeriodo('dia'));
  const [agrupar, setAgrupar] = useState<Agrupar>('dia');

  // Filtros del libro de inventario: grupo del inventario + zona + buscar
  const [grupoInv, setGrupoInv] = useState<GrupoInv>('INSUMOS');
  const [categoriaPlasticosId, setCategoriaPlasticosId] = useState<number | null>(null);
  const [tipoRevendidoId, setTipoRevendidoId] = useState<number | null>(null);
  const [zona, setZona] = useState('');
  const [buscar, setBuscar] = useState('');
  const buscarDeb = useDebouncedValue(buscar, 400);

  // Filtros del libro de dinero (client-side)
  const [cuenta, setCuenta] = useState('');
  const [buscarDinero, setBuscarDinero] = useState('');

  const [libro, setLibro] = useState<LibroEntradasSalidas | null>(null);
  const [cajaMovs, setCajaMovs] = useState<MovimientoCaja[]>([]);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);
  const [exportando, setExportando] = useState(false);
  const refImprimible = useRef<HTMLDivElement>(null);

  // IDs de catálogo que separan los grupos de productos (Plásticos por
  // categoría, Reventa por tipo). Si el catálogo no responde, el grupo sigue
  // funcionando sin ese filtro.
  useEffect(() => {
    let cancelado = false;
    (async () => {
      try {
        const categorias = await inventarioService.getCategorias('PRODUCTO');
        const plasticos = categorias.find((c) => normNombre(c.nombre).includes('PLASTICO'));
        if (!cancelado && plasticos) setCategoriaPlasticosId(plasticos.id);
      } catch {
        // sin acceso al catálogo de categorías: Plásticos queda sin filtro
      }
      try {
        const tipos = await productosService.getTiposProducto('Revendido');
        const revendido = tipos.find((t) => normNombre(t.nombre).includes('REVENDIDO')) ?? tipos[0];
        if (!cancelado && revendido) setTipoRevendidoId(revendido.id);
      } catch {
        // sin acceso al catálogo de tipos: Reventa queda sin filtro
      }
    })();
    return () => {
      cancelado = true;
    };
  }, []);

  const cambiarPeriodo = (p: Periodo) => {
    setPeriodo(p);
    setRango(rangoDePeriodo(p));
    setAgrupar(p === 'mes' ? 'semana' : 'dia');
  };

  useEffect(() => {
    if (!book) return;
    let cancelado = false;
    setLoading(true);
    setError(null);
    (async () => {
      try {
        if (book.dominio === 'INVENTARIO') {
          const tipoItem = grupoInv === 'INSUMOS' ? 'MATERIAL'
            : grupoInv === 'CRUDO' ? 'CRUDO'
            : 'PRODUCTO';
          const data = await inventarioService.getLibro({
            desde: rango.desde,
            hasta: rango.hasta,
            lado: book.lado,
            tipo_item: tipoItem,
            categoria_id: grupoInv === 'PLASTICOS' ? categoriaPlasticosId ?? undefined : undefined,
            tipo_producto_id: grupoInv === 'REVENTA' ? tipoRevendidoId ?? undefined : undefined,
            zona: zona || undefined,
            buscar: buscarDeb || undefined,
          });
          if (!cancelado) setLibro(data);
        } else {
          const movs = await reportesService.getMovimientosCaja({
            fecha_desde: rango.desde,
            fecha_hasta: rango.hasta,
          });
          if (!cancelado) setCajaMovs(movs);
        }
      } catch (e) {
        if (!cancelado) setError(extractErrorMessage(e, 'No se pudo cargar el libro.'));
      } finally {
        if (!cancelado) setLoading(false);
      }
    })();
    return () => {
      cancelado = true;
    };
  }, [book, rango, grupoInv, categoriaPlasticosId, tipoRevendidoId, zona, buscarDeb]);

  // ── Libro de inventario: orden descendente y subtotales por grupo ──────
  const filasInventario = useMemo(
    () =>
      [...(libro?.filas ?? [])].sort((a, b) =>
        a.fecha < b.fecha ? 1 : a.fecha > b.fecha ? -1 : b.id - a.id,
      ),
    [libro],
  );

  const gruposInventario = useMemo(
    () =>
      agruparPor(filasInventario, agrupar).map((g) => ({
        ...g,
        costo: g.filas.reduce((acc, fila) => acc + (fila.costo_total ?? 0), 0),
        sinCosto: g.filas.filter((fila) => fila.costo_total == null).length,
      })),
    [filasInventario, agrupar],
  );

  // ── Libro de dinero: filtro por lado + cuenta + texto ──────────────────
  const movsDinero = useMemo(() => {
    if (!book) return [];
    const tipoBuscado = book.lado === 'ENTRADAS' ? 'ENTRADA' : 'SALIDA';
    let filas = cajaMovs.filter((m) => m.tipo === tipoBuscado);
    if (cuenta) filas = filas.filter((m) => String(m.metodo_caja_id) === cuenta);
    const q = buscarDinero.trim().toLowerCase();
    if (q) {
      filas = filas.filter((m) =>
        [m.metodo_caja?.nombre, m.persona_entidad, m.concepto, m.referencia]
          .filter(Boolean)
          .some((v) => String(v).toLowerCase().includes(q)),
      );
    }
    return [...filas].sort((a, b) =>
      a.fecha < b.fecha ? 1 : a.fecha > b.fecha ? -1 : b.id - a.id,
    );
  }, [cajaMovs, book, cuenta, buscarDinero]);

  const gruposDinero = useMemo(
    () =>
      agruparPor(movsDinero, agrupar).map((g) => {
        const porMoneda: Record<string, number> = {};
        for (const m of g.filas) {
          const cod = m.moneda?.codigo || 'COP';
          porMoneda[cod] = (porMoneda[cod] || 0) + Number(m.monto || 0);
        }
        return { ...g, porMoneda };
      }),
    [movsDinero, agrupar],
  );

  const totalesMoneda = useMemo(() => {
    const totales: Record<string, number> = {};
    for (const m of movsDinero) {
      const cod = m.moneda?.codigo || 'COP';
      totales[cod] = (totales[cod] || 0) + Number(m.monto || 0);
    }
    return totales;
  }, [movsDinero]);

  const cuentasDisponibles = useMemo(() => {
    const vistos = new Map<string, string>();
    for (const m of cajaMovs) {
      vistos.set(String(m.metodo_caja_id), m.metodo_caja?.nombre || `Cuenta #${m.metodo_caja_id}`);
    }
    return [...vistos.entries()].sort((a, b) => a[1].localeCompare(b[1]));
  }, [cajaMovs]);

  if (!book) {
    return (
      <EmptyState
        title="Sin acceso a estos libros"
        description="Tu usuario no tiene los módulos necesarios para verlos."
      />
    );
  }

  const exportarPdf = async () => {
    if (!refImprimible.current) return;
    setExportando(true);
    try {
      const { capturarElementoAPdf } = await import('../../utils/pdfCaptura');
      await capturarElementoAPdf(refImprimible.current, {
        nombreArchivo: `Libro_${book.label.replace(/\s+/g, '_')}_${rango.desde}_${rango.hasta}.pdf`,
      });
    } finally {
      setExportando(false);
    }
  };

  const cambiarRangoManual = (campo: 'desde' | 'hasta', valor: string) => {
    setPeriodo(null);
    setRango((r) => ({ ...r, [campo]: valor }));
  };

  return (
    <div className="space-y-5">
      <Tabs
        variant="pills"
        tabs={libros.map((b) => ({ key: b.key, label: b.label }))}
        active={book.key}
        onChange={setBookKey}
      />

      {/* ── Controles ── */}
      <div className="bg-white border border-yeikar-secondary-light/10 rounded-2xl p-4 flex flex-wrap items-end gap-x-5 gap-y-3 shadow-sm">
        <div>
          <p className="text-[10px] font-bold uppercase tracking-wider text-yeikar-neutral/50 mb-1.5">Período</p>
          <div className="flex items-center gap-1 bg-yeikar-secondary/5 border border-yeikar-secondary-light/10 rounded-xl p-1">
            {(['dia', 'semana', 'mes'] as Periodo[]).map((p) => (
              <button
                key={p}
                onClick={() => cambiarPeriodo(p)}
                className={`px-3 py-1.5 rounded-lg text-xs font-bold font-headline transition-all ${
                  periodo === p
                    ? 'bg-yeikar-primary text-yeikar-neutral shadow-gold'
                    : 'text-yeikar-secondary/70 hover:bg-yeikar-tertiary/40'
                }`}
              >
                {p === 'dia' ? 'Día' : p === 'semana' ? 'Semana' : 'Mes'}
              </button>
            ))}
          </div>
        </div>

        <div>
          <p className="text-[10px] font-bold uppercase tracking-wider text-yeikar-neutral/50 mb-1.5">Del</p>
          <input type="date" value={rango.desde} onChange={(e) => cambiarRangoManual('desde', e.target.value)} className={inputCls} />
        </div>
        <div>
          <p className="text-[10px] font-bold uppercase tracking-wider text-yeikar-neutral/50 mb-1.5">Al</p>
          <input type="date" value={rango.hasta} onChange={(e) => cambiarRangoManual('hasta', e.target.value)} className={inputCls} />
        </div>

        <div>
          <p className="text-[10px] font-bold uppercase tracking-wider text-yeikar-neutral/50 mb-1.5">Agrupar</p>
          <div className="flex items-center gap-1 bg-yeikar-secondary/5 border border-yeikar-secondary-light/10 rounded-xl p-1">
            {(['dia', 'semana', 'mes'] as Agrupar[]).map((a) => (
              <button
                key={a}
                onClick={() => setAgrupar(a)}
                className={`px-3 py-1.5 rounded-lg text-xs font-bold font-headline transition-all ${
                  agrupar === a
                    ? 'bg-yeikar-primary text-yeikar-neutral shadow-gold'
                    : 'text-yeikar-secondary/70 hover:bg-yeikar-tertiary/40'
                }`}
              >
                {a === 'dia' ? 'Por día' : a === 'semana' ? 'Por semana' : 'Por mes'}
              </button>
            ))}
          </div>
        </div>

        {book.dominio === 'INVENTARIO' ? (
          <>
            <div>
              <p className="text-[10px] font-bold uppercase tracking-wider text-yeikar-neutral/50 mb-1.5">Inventario</p>
              <select value={grupoInv} onChange={(e) => setGrupoInv(e.target.value as GrupoInv)} className={inputCls}>
                {GRUPOS_INV.map((g) => (
                  <option key={g.valor} value={g.valor}>{g.label}</option>
                ))}
              </select>
            </div>
            <div>
              <p className="text-[10px] font-bold uppercase tracking-wider text-yeikar-neutral/50 mb-1.5">Zona</p>
              <select value={zona} onChange={(e) => setZona(e.target.value)} className={inputCls}>
                {ZONAS.map((z) => (
                  <option key={z.valor} value={z.valor}>{z.label}</option>
                ))}
              </select>
            </div>
            <div className="grow min-w-[160px]">
              <p className="text-[10px] font-bold uppercase tracking-wider text-yeikar-neutral/50 mb-1.5">Buscar</p>
              <input
                value={buscar}
                onChange={(e) => setBuscar(e.target.value)}
                placeholder="Nombre del ítem..."
                className={`${inputCls} w-full`}
              />
            </div>
          </>
        ) : (
          <>
            <div>
              <p className="text-[10px] font-bold uppercase tracking-wider text-yeikar-neutral/50 mb-1.5">Cuenta</p>
              <select value={cuenta} onChange={(e) => setCuenta(e.target.value)} className={inputCls}>
                <option value="">Todas las cuentas</option>
                {cuentasDisponibles.map(([id, nombre]) => (
                  <option key={id} value={id}>{nombre}</option>
                ))}
              </select>
            </div>
            <div className="grow min-w-[160px]">
              <p className="text-[10px] font-bold uppercase tracking-wider text-yeikar-neutral/50 mb-1.5">Buscar</p>
              <input
                value={buscarDinero}
                onChange={(e) => setBuscarDinero(e.target.value)}
                placeholder="Referencia o nota..."
                className={`${inputCls} w-full`}
              />
            </div>
          </>
        )}

        <button
          onClick={exportarPdf}
          disabled={exportando || loading}
          className="ml-auto px-4 py-2 bg-yeikar-secondary text-yeikar-primary hover:bg-yeikar-secondary-light disabled:opacity-50 rounded-xl text-xs font-bold font-headline transition-all flex items-center gap-2 shadow-sm"
        >
          <FileDown className="w-4 h-4" />
          {exportando ? 'Generando...' : 'Descargar PDF'}
        </button>
      </div>

      {error && <p className="text-sm text-red-600">{error}</p>}

      {/* ── Área imprimible ── */}
      <div
        ref={refImprimible}
        className="bg-white border border-yeikar-secondary-light/10 rounded-2xl shadow-sm p-5 space-y-4"
      >
        <div data-pdf-item="true" className="flex flex-wrap items-end justify-between gap-2 border-b border-yeikar-secondary-light/10 pb-3">
          <div>
            <p className="font-mono text-[10px] uppercase tracking-widest text-yeikar-neutral/45">YEIKAR · Libro de control</p>
            <h2 className="font-headline font-black text-lg text-yeikar-neutral">{book.label}</h2>
            <p className="text-xs text-yeikar-neutral/55">
              Del {fmtFechaVE(rango.desde)} al {fmtFechaVE(rango.hasta)}
              {' · '}
              {agrupar === 'dia' ? 'agrupado por día' : agrupar === 'semana' ? 'agrupado por semana' : 'agrupado por mes'}
            </p>
          </div>
          <p className="text-[11px] text-yeikar-neutral/40 font-mono">Generado: {fmtFechaVE(new Date())}</p>
        </div>

        {loading ? (
          <div className="flex justify-center py-16"><Spinner /></div>
        ) : book.dominio === 'INVENTARIO' ? (
          libro ? <ContenidoInventario libro={libro} grupos={gruposInventario} lado={book.lado} /> : null
        ) : (
          <ContenidoDinero movimientos={movsDinero} grupos={gruposDinero} totalesMoneda={totalesMoneda} />
        )}
      </div>
    </div>
  );
}
