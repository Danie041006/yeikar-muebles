import { useEffect, useRef, useState } from 'react';
import {
  cuentasService, type ResumenCuenta,
} from '../../services/cuentasService';
import { CLASIFICACIONES_GASTO } from '../../services/gastoService';
import {
  Button, Field, Input, Label, Modal, SearchSelect, Select, Spinner,
} from '../ui';
import { fmtFechaHoraVE } from '../../utils/fechas';
import {
  construirReporteCuentas, etiquetaFiltroReporte, type FiltroReporteCuentas,
} from '../../utils/reporteCuentas';
import { imprimirReporteCuentas } from '../../utils/reporteCuentasHtml';
import { exportarReporteCuentasExcel } from '../../utils/reporteCuentasExcel';

interface Props {
  open: boolean;
  onClose: () => void;
  cuentas: ResumenCuenta[];
  cuentaInicialId?: number | null;
  desdeInicial?: string | null;
  hastaInicial?: string | null;
}

type Formato = 'PDF' | 'EXCEL';

const iso = (d: Date) =>
  `${d.getFullYear()}-${String(d.getMonth() + 1).padStart(2, '0')}-${String(d.getDate()).padStart(2, '0')}`;

const primerDiaMes = () => {
  const hoy = new Date();
  return iso(new Date(hoy.getFullYear(), hoy.getMonth(), 1));
};

const ultimoDiaMes = () => {
  const hoy = new Date();
  return iso(new Date(hoy.getFullYear(), hoy.getMonth() + 1, 0));
};

function Casilla({
  checked, onChange, title, description,
}: {
  checked: boolean;
  onChange: (v: boolean) => void;
  title: string;
  description?: string;
}) {
  return (
    <label className="flex items-start gap-2 rounded-xl border border-yeikar-secondary-light/15 bg-yeikar-tertiary/10 px-3 py-2 cursor-pointer hover:border-yeikar-primary/40 transition-colors">
      <input
        type="checkbox"
        checked={checked}
        onChange={(e) => onChange(e.target.checked)}
        className="mt-0.5 rounded border-yeikar-secondary-light/30 text-yeikar-primary focus:ring-yeikar-primary h-4 w-4"
      />
      <span>
        <span className="block text-xs font-bold font-headline text-yeikar-secondary">{title}</span>
        {description && <span className="block text-[11px] text-yeikar-neutral/50">{description}</span>}
      </span>
    </label>
  );
}

export default function ReporteCuentasModal({
  open, onClose, cuentas, cuentaInicialId, desdeInicial, hastaInicial,
}: Props) {
  const [cuentaId, setCuentaId] = useState<number | ''>('');
  const [desde, setDesde] = useState(primerDiaMes());
  const [hasta, setHasta] = useState(ultimoDiaMes());
  const [formato, setFormato] = useState<Formato>('PDF');
  const [incluirResumen, setIncluirResumen] = useState(true);
  const [incluirDetalle, setIncluirDetalle] = useState(true);
  const [incluirClasificaciones, setIncluirClasificaciones] = useState(false);
  const [filtro, setFiltro] = useState('TODOS');
  const [colPersona, setColPersona] = useState(true);
  const [colRegistrado, setColRegistrado] = useState(true);
  const [colReferencia, setColReferencia] = useState(false);
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState('');
  const abiertoAntes = useRef(false);

  // Al abrir, reinicia las opciones (la cuenta se elige cuando ya hay datos).
  useEffect(() => {
    if (!open) {
      abiertoAntes.current = false;
      return;
    }
    if (abiertoAntes.current) return;
    abiertoAntes.current = true;

    setCuentaId('');
    setDesde(desdeInicial || primerDiaMes());
    setHasta(hastaInicial || ultimoDiaMes());
    setFormato('PDF');
    setIncluirResumen(true);
    setIncluirDetalle(true);
    setIncluirClasificaciones(false);
    setFiltro('TODOS');
    setColPersona(true);
    setColRegistrado(true);
    setColReferencia(false);
    setError('');
    setLoading(false);
  }, [open, desdeInicial, hastaInicial]);

  // La cuenta inicial se resuelve apenas estén disponibles (la carga del
  // listado puede terminar después de abrir el modal).
  useEffect(() => {
    if (!open || cuentaId) return;
    const inicial = (cuentaInicialId
      ? cuentas.find((c) => c.metodo_caja.id === cuentaInicialId)
      : null)
      || cuentas.find((c) => c.metodo_caja.codigo === 'EFECTIVO_COP')
      || cuentas.find((c) => c.metodo_caja.moneda_codigo === 'COP')
      || cuentas[0];
    if (inicial) setCuentaId(inicial.metodo_caja.id);
  }, [open, cuentaId, cuentaInicialId, cuentas]);

  const filtroSeleccionado = (): FiltroReporteCuentas => {
    if (filtro === 'INGRESOS') return { tipo: 'INGRESOS' };
    if (filtro === 'EGRESOS') return { tipo: 'EGRESOS' };
    if (filtro.startsWith('CLASIFICACION:')) {
      const codigo = filtro.slice('CLASIFICACION:'.length);
      const meta = CLASIFICACIONES_GASTO.find((c) => c.value === codigo);
      return {
        tipo: 'CLASIFICACION',
        clasificacion: codigo,
        label: meta?.label ?? codigo,
      };
    }
    return { tipo: 'TODOS' };
  };

  const generar = async () => {
    if (!cuentaId) {
      setError('Elige la cuenta del reporte.');
      return;
    }
    if (!desde || !hasta) {
      setError('Indica el rango de fechas.');
      return;
    }
    if (desde > hasta) {
      setError('La fecha "desde" no puede ser mayor que la fecha "hasta".');
      return;
    }
    if (!incluirResumen && !incluirDetalle && !incluirClasificaciones) {
      setError('Marca al menos una sección para incluir en el reporte.');
      return;
    }

    setLoading(true);
    setError('');
    try {
      const libro = await cuentasService.getLibro({
        metodo_caja_id: Number(cuentaId),
        fecha_desde: desde,
        fecha_hasta: hasta,
      });

      const data = construirReporteCuentas(libro, {
        filtro: filtroSeleccionado(),
        incluirResumen,
        incluirDetalle,
        incluirClasificaciones,
        columnas: {
          persona: colPersona,
          registrado: colRegistrado,
          referencia: colReferencia,
        },
        generadoEn: fmtFechaHoraVE(new Date()),
      });

      if (formato === 'PDF') {
        if (!imprimirReporteCuentas(data)) {
          setError('El navegador bloqueó la ventana del reporte. Permite las ventanas emergentes e intenta de nuevo.');
          return;
        }
      } else {
        await exportarReporteCuentasExcel(data);
      }
      onClose();
    } catch (e: any) {
      console.error('Error generando el reporte de cuentas:', e);
      setError(e?.response?.data?.detail ?? 'No se pudo generar el reporte.');
    } finally {
      setLoading(false);
    }
  };

  return (
    <Modal
      open={open}
      onClose={onClose}
      title="Reporte de libro de caja"
      subtitle="Elige la cuenta, el rango y qué incluir · PDF o Excel"
      size="xl"
      footer={
        <>
          <Button variant="outline" onClick={onClose} disabled={loading}>Cancelar</Button>
          <Button onClick={generar} disabled={loading}>
            {loading
              ? <><Spinner size="sm" /> Generando...</>
              : `Generar ${formato === 'PDF' ? 'PDF' : 'Excel'}`}
          </Button>
        </>
      }
    >
      <div className="space-y-4">
        <div className="grid grid-cols-1 sm:grid-cols-2 gap-4">
          <Field label="Cuenta" required hint="El reporte cubre una cuenta a la vez.">
            <SearchSelect
              value={cuentaId}
              onChange={(v) => setCuentaId(v === '' ? '' : Number(v))}
              options={cuentas.map((c) => ({
                value: c.metodo_caja.id,
                label: `${c.metodo_caja.nombre} · ${c.metodo_caja.moneda_codigo || '?'}`,
              }))}
              placeholder="Seleccione la cuenta..."
            />
          </Field>

          <Field label="Formato" required>
            <div className="grid grid-cols-2 gap-2">
              {([
                ['PDF', 'Listo para imprimir', 'Se abre el diálogo para guardar como PDF.'],
                ['EXCEL', 'Archivo .xlsx', 'Con formato, totales y hoja de clasificaciones.'],
              ] as const).map(([valor, titulo, detalle]) => (
                <button
                  key={valor}
                  type="button"
                  onClick={() => setFormato(valor)}
                  className={`text-left rounded-xl border px-3 py-2 transition-colors ${
                    formato === valor
                      ? 'border-yeikar-primary bg-yeikar-primary/10'
                      : 'border-yeikar-secondary-light/15 bg-white hover:border-yeikar-primary/40'
                  }`}
                >
                  <span className="block text-xs font-black font-headline text-yeikar-secondary">{titulo}</span>
                  <span className="block text-[10px] text-yeikar-neutral/50 leading-snug">{detalle}</span>
                </button>
              ))}
            </div>
          </Field>
        </div>

        <div className="grid grid-cols-1 sm:grid-cols-2 gap-4">
          <Field label="Desde" required>
            <Input type="date" value={desde} onChange={(e) => setDesde(e.target.value)} />
          </Field>
          <Field label="Hasta" required>
            <Input type="date" value={hasta} onChange={(e) => setHasta(e.target.value)} />
          </Field>
        </div>

        <div>
          <Label>Incluir en el reporte</Label>
          <div className="grid grid-cols-1 sm:grid-cols-3 gap-2">
            <Casilla
              checked={incluirResumen}
              onChange={setIncluirResumen}
              title="Resumen"
              description="Saldo inicial, ingresos, egresos y saldo final."
            />
            <Casilla
              checked={incluirDetalle}
              onChange={setIncluirDetalle}
              title="Movimientos"
              description="Detalle del libro con su saldo corrido."
            />
            <Casilla
              checked={incluirClasificaciones}
              onChange={setIncluirClasificaciones}
              title="Clasificaciones"
              description="Totales de gastos por clasificación."
            />
          </div>
        </div>

        <div className="grid grid-cols-1 sm:grid-cols-2 gap-4">
          <Field
            label="Filtrar el detalle"
            hint={filtro === 'TODOS'
              ? 'El saldo corrido se incluye porque el libro está completo.'
              : 'Al filtrar se oculta el saldo corrido y se muestra el total del filtro.'}
          >
            <Select value={filtro} onChange={(e) => setFiltro(e.target.value)}>
              <option value="TODOS">Todos los movimientos</option>
              <option value="INGRESOS">Solo ingresos</option>
              <option value="EGRESOS">Solo egresos</option>
              {CLASIFICACIONES_GASTO.map((c) => (
                <option key={c.value} value={`CLASIFICACION:${c.value}`}>
                  Solo {c.label.toLowerCase()}
                </option>
              ))}
            </Select>
          </Field>

          <div>
            <Label>Columnas del detalle</Label>
            <div className="flex flex-wrap gap-2">
              <Casilla checked={colPersona} onChange={setColPersona} title="Persona o entidad" />
              <Casilla checked={colRegistrado} onChange={setColRegistrado} title="Registrado por" />
              <Casilla checked={colReferencia} onChange={setColReferencia} title="Referencia" />
            </div>
          </div>
        </div>

        {filtro !== 'TODOS' && (
          <p className="text-[11px] text-yeikar-neutral/50 bg-yeikar-tertiary/20 rounded-lg px-3 py-2">
            Detalle: <strong>{etiquetaFiltroReporte(filtroSeleccionado())}</strong>.
            {' '}El resumen de la cuenta siempre cubre todos los movimientos del rango.
          </p>
        )}

        {error && (
          <div className="bg-red-50 border border-red-200 text-red-700 px-4 py-3 rounded-xl text-sm">
            {error}
          </div>
        )}
      </div>
    </Modal>
  );
}
