import { useState, useRef, useCallback, useEffect } from 'react';
import {
  iqeService,
  type SeccionCostoOut,
  type ResumenCostosOut,
  type UnidadMedida,
  type TipoProducto,
  type ContextoExportarOut,
  type GenerateStructureOut,
} from '../services/iqeService';
import { clienteService, type Client } from '../services/clienteService';
import { productosService } from '../services/productosService';
import EstructuraCostosEditor from '../components/EstructuraCostosEditor';
import EstructuraCostos from '../components/EstructuraCostos';
import { normalizarEstructuraIQE } from '../utils/estructuraCostos';
import { Modal } from '../components/ui';
import { SearchSelect } from '../components/ui';

// ─── Tipos de estado local ────────────────────────────────────────────────────

type Paso = 'manual' | 'borrador' | 'finalizar';

interface ParametrosForm {
  ancho: string;
  largo: string;
  alto: string;
  fondo: string;
  ganancia: string;
  iva: string;
  impuesto: string;
  pct_mano_obra: string;
  pct_gastos: string;
}

const PASOS = [
  { id: 'manual', num: 1, label: 'Contexto + IA' },
  { id: 'borrador', num: 2, label: 'Estructura de Costos' },
  { id: 'finalizar', num: 3, label: 'Guardar' },
] as const;

const TIPOS_MUEBLE = [
  { value: 'otro', label: 'Otro / genérico' },
  { value: 'cama', label: 'Cama' },
  { value: 'nochero', label: 'Nochero / mesa de noche' },
  { value: 'closet', label: 'Closet' },
  { value: 'armario', label: 'Armario' },
  { value: 'tocador', label: 'Tocador' },
  { value: 'sala', label: 'Sala' },
  { value: 'comedor', label: 'Comedor' },
  { value: 'escritorio', label: 'Escritorio' },
  { value: 'rack_tv', label: 'Rack / TV' },
  { value: 'libreria', label: 'Librería' },
  { value: 'mueble_bano', label: 'Mueble de baño' },
];

// ─── Constantes de la UI ──────────────────────────────────────────────────────

// Ejemplo de lo que devuelve la IA en FORMATO EXCEL (para "Probar con un ejemplo")
const EJEMPLO_EXCEL = `SECCION EBANISTERIA
MATERIAL | CANTIDAD | UNIDAD | V/UNIT | PRECIO TOTAL
LAMINA DE 9 | 1 | LAMINA | 140000 | 140000
COLBON | 0.7 | LITRO | 14000 | 9800
TORNILLOS DE 2" | 100 | UN | 100 | 10000
HECHURA | 1 | PAR |  | 
SECCION PINTURA
PREPARADO | 1 | PISTOLADA |  | 
PINTURA ALEX | 1 | CON EL 5% |  | 
SECCION TAPICERIA
TELA PRANNA NEGRA | 6 | M | 34899 | 209394
ESPUMA 2 ROSADA | 2 | LAMINA | 48000 | 96000`;

const CONSEJOS_IA = [
  { nombre: 'Las 3 IAs', texto: 'Todas deben hacerte las preguntas del costeador ANTES de cotizar (lo exige el prompt [1]). Si alguna salta directo a la tabla, respóndele: "Hazme TODAS las preguntas que necesites antes de cotizar, una por una".' },
  { nombre: 'Claude', texto: 'Activa "extended thinking" para mejores cantidades.' },
  { nombre: 'ChatGPT', texto: 'Usa un modelo con razonamiento y adjunta la foto en el primer mensaje.' },
  { nombre: 'Gemini', texto: 'Activa "Deep Think" (modelo 2.5 Pro) para analizar la foto.' },
];

const PASOS_GUIA = [
  { n: '1', t: 'Entender el mueble', d: 'Copia el prompt [1], adjunta la FOTO (o pega el mensaje de WhatsApp) y responde las preguntas que te haga la IA.' },
  { n: '2', t: 'Estructura de costos', d: 'En la MISMA conversación, copia el prompt [2]. La IA te devuelve la tabla estilo Excel.' },
  { n: '3', t: 'Pega la respuesta', d: 'Copia la tabla que devolvió la IA, pégala abajo e importa la estructura.' },
];

export default function CotizadorInteligente() {
  // ── Parámetros de dimensiones y costos ──
  const [parametros, setParametros] = useState<ParametrosForm>({
    ancho: '1.60',
    largo: '1.90',
    alto: '0.50',
    fondo: '',
    ganancia: '40',
    iva: '0',
    impuesto: '7',
    pct_mano_obra: '15',
    pct_gastos: '10',
  });

  // ── Paso 2: Estructura de Costos ──
  const [secciones, setSecciones] = useState<SeccionCostoOut[]>([]);
  const [resumen, setResumen] = useState<ResumenCostosOut | null>(null);
  const [showEstructura, setShowEstructura] = useState(false);
  const [materialesSinPrecio, setMaterialesSinPrecio] = useState(0);
  const [productoBaseId, setProductoBaseId] = useState<number | null>(null);
  const [productoBaseNombre, setProductoBaseNombre] = useState<string | null>(null);
  const [scoreSimilitud, setScoreSimilitud] = useState(0);
  const [generandoEstructura, setGenerandoEstructura] = useState(false);

  // Catálogos auxiliares
  const [unidades, setUnidades] = useState<UnidadMedida[]>([]);
  const [tiposProducto, setTiposProducto] = useState<TipoProducto[]>([]);

  // ── Paso 1 (Manual): contexto + JSON de la IA de navegador ──
  const [productos, setProductos] = useState<{ id: number; nombre: string }[]>([]);
  const [productoBaseSel, setProductoBaseSel] = useState('');
  const [tipoMueble, setTipoMueble] = useState('otro');
  const [conFoto, setConFoto] = useState(true);
  const [descripcionMueble, setDescripcionMueble] = useState('');
  const [contexto, setContexto] = useState<ContextoExportarOut | null>(null);
  const [promptActivoId, setPromptActivoId] = useState('entender_mueble');
  const [generandoContexto, setGenerandoContexto] = useState(false);
  const [jsonIA, setJsonIA] = useState('');
  const [importandoEstructura, setImportandoEstructura] = useState(false);
  const [copiado, setCopiado] = useState(false);
  const [advertenciaImport, setAdvertenciaImport] = useState<string | null>(null);
  const [seccionesFaltantes, setSeccionesFaltantes] = useState<string[]>([]);
  const jsonFileRef = useRef<HTMLInputElement>(null);

  const promptActivo =
    contexto?.prompts.find((p) => p.id === promptActivoId) ?? contexto?.prompts[0] ?? null;

  const handleCargarArchivoJson = (file: File) => {
    const reader = new FileReader();
    reader.onload = (e) => {
      setJsonIA(String(e.target?.result || ''));
      setErrorAnalisis('');
    };
    reader.readAsText(file);
  };

  // ── Paso 3: Finalizar y guardar ──
  const [paso, setPaso] = useState<Paso>('manual');
  const [guardarComo, setGuardarComo] = useState<'cotizacion' | 'producto'>('cotizacion');
  const [clientes, setClientes] = useState<Client[]>([]);
  const [clienteId, setClienteId] = useState('');
  const [observacionesFinal, setObservacionesFinal] = useState('');
  const [nombreProducto, setNombreProducto] = useState('');
  const [tipoProductoId, setTipoProductoId] = useState('');

  const [guardando, setGuardando] = useState(false);
  const [cotizacionCreada, setCotizacionCreada] = useState<{
    id: number;
    total: number;
    mensaje: string;
    pdfUrl: string;
    isProduct: boolean;
  } | null>(null);
  const [errorAnalisis, setErrorAnalisis] = useState('');
  const [errorFinal, setErrorFinal] = useState('');

  // Cargar catálogos iniciales
  useEffect(() => {
    const loadCatalogs = async () => {
      try {
        const [unds, tps] = await Promise.all([
          iqeService.getUnidadesMedida(),
          iqeService.getTiposProducto(),
        ]);
        setUnidades(unds);
        setTiposProducto(tps);
      } catch (err) {
        console.error('Error al cargar catálogos:', err);
      }
    };
    loadCatalogs();
  }, []);

  /** Cargar productos para la receta de referencia */
  const cargarProductos = useCallback(async () => {
    try {
      const list = await productosService.getProductos();
      setProductos(list.map((p) => ({ id: p.id, nombre: p.nombre })));
    } catch (err) {
      console.error('Error al cargar productos:', err);
    }
  }, []);

  useEffect(() => {
    cargarProductos();
  }, [cargarProductos]);

  // ── Paso 1: generar el paquete de contexto para la IA de navegador ──
  const handleGenerarContexto = async () => {
    setGenerandoContexto(true);
    setErrorAnalisis('');
    try {
      const res = await iqeService.exportarContexto({
        producto_base_id: productoBaseSel ? Number(productoBaseSel) : null,
        ancho: parseFloat(parametros.ancho) || 1.6,
        largo: parseFloat(parametros.largo) || 1.9,
        alto: parseFloat(parametros.alto) || null,
        con_foto: conFoto,
        descripcion: conFoto ? undefined : descripcionMueble,
        tipo_mueble: tipoMueble,
      });
      setContexto(res);
      setPromptActivoId(res.prompts?.[0]?.id ?? 'desde_cero');
      setCopiado(false);
    } catch (err: any) {
      setErrorAnalisis(err?.response?.data?.detail || 'Error al generar el contexto.');
    } finally {
      setGenerandoContexto(false);
    }
  };

  const handleCopiarContexto = async () => {
    const texto = promptActivo?.instrucciones ?? contexto?.instrucciones;
    if (!texto) return;
    try {
      await navigator.clipboard.writeText(texto);
      setCopiado(true);
      setTimeout(() => setCopiado(false), 2500);
    } catch {
      setErrorAnalisis('No se pudo copiar: copia el texto manualmente.');
    }
  };

  const handleDescargarContexto = () => {
    if (!contexto) return;
    const blob = new Blob([contexto.texto], { type: 'text/markdown;charset=utf-8' });
    const url = URL.createObjectURL(blob);
    const a = document.createElement('a');
    a.href = url;
    a.download = 'contexto-yeikar.md';
    a.click();
    URL.revokeObjectURL(url);
  };

  const handleDescargarInventarioJson = () => {
    if (!contexto) return;
    const blob = new Blob(
      [JSON.stringify({ inventario: contexto.inventario, receta_similar: contexto.receta_similar }, null, 2)],
      { type: 'application/json;charset=utf-8' },
    );
    const url = URL.createObjectURL(blob);
    const a = document.createElement('a');
    a.href = url;
    a.download = 'inventario-yeikar.json';
    a.click();
    URL.revokeObjectURL(url);
  };

  /** ¿La respuesta pegada parece JSON (objeto/array) o texto estilo Excel? */
  const esRespuestaJson = (texto: string): boolean => {
    const t = texto.trim();
    return t.startsWith('{') || t.startsWith('[');
  };

  /** Aplicar la estructura importada → saltar al editor */
  const aplicarRespuestaImportada = (resp: GenerateStructureOut) => {
    setSecciones(resp.secciones);
    setResumen(resp.resumen);
    setMaterialesSinPrecio(resp.materiales_sin_precio);
    setProductoBaseId(resp.producto_base_id);
    setProductoBaseNombre(resp.producto_base_nombre);
    setScoreSimilitud(Math.round(resp.score_similitud * 100));
    setAdvertenciaImport(resp.advertencia ?? null);
    setSeccionesFaltantes(resp.secciones_faltantes ?? []);
    setPaso('borrador');
  };

  /** Normalizar el JSON pegado (objeto con estructura_propuesta o array directo) */
  const parsearJsonIA = (): { estructura: any[]; tipo: string; dims: Record<string, any> } | null => {
    try {
      const parsed = JSON.parse(jsonIA);
      if (Array.isArray(parsed)) {
        return { estructura: parsed, tipo: 'otro', dims: {} };
      }
      if (parsed && typeof parsed === 'object' && Array.isArray(parsed.estructura_propuesta)) {
        return {
          estructura: parsed.estructura_propuesta,
          tipo: parsed.tipo_mueble || 'otro',
          dims: parsed.dimensiones_referencia || {},
        };
      }
      setErrorAnalisis('El JSON no contiene una estructura válida (falta "estructura_propuesta").');
      return null;
    } catch {
      setErrorAnalisis('JSON inválido. Revisa que la IA devolvió un JSON válido y pégalo completo.');
      return null;
    }
  };

  /** Importar la respuesta de la IA (formato Excel o JSON) → salta al editor */
  const handleImportarEstructura = async () => {
    if (!jsonIA.trim()) return;
    setImportandoEstructura(true);
    setErrorAnalisis('');
    try {
      const base = {
        producto_base_id: productoBaseSel ? Number(productoBaseSel) : null,
        tipo_mueble: tipoMueble,
        nuevo_ancho: parseFloat(parametros.ancho) || 1.6,
        nuevo_largo: parseFloat(parametros.largo) || 1.9,
        nuevo_alto: parseFloat(parametros.alto) || null,
        nuevo_fondo: parseFloat(parametros.fondo) || null,
        ganancia_porcentaje: parseFloat(parametros.ganancia) || 40,
        iva_porcentaje: parseFloat(parametros.iva) || 0,
        impuesto_porcentaje: parseFloat(parametros.impuesto) || 7,
        pct_mano_obra: parseFloat(parametros.pct_mano_obra) || 15,
        pct_gastos: parseFloat(parametros.pct_gastos) || 10,
      };
      if (esRespuestaJson(jsonIA)) {
        const parsed = parsearJsonIA();
        if (!parsed) return;
        const resp = await iqeService.importarEstructura({
          ...base,
          estructura_propuesta: parsed.estructura,
          tipo_mueble: parsed.tipo,
          dimensiones_referencia: parsed.dims,
        });
        aplicarRespuestaImportada(resp);
      } else {
        const resp = await iqeService.importarTexto({
          ...base,
          texto: jsonIA,
        });
        aplicarRespuestaImportada(resp);
      }
    } catch (err: any) {
      setErrorAnalisis(
        err?.response?.data?.detail ||
          'No se pudo importar la respuesta. Si la IA no la devolvió en formato Excel, usa el prompt "Reparar respuesta".',
      );
    } finally {
      setImportandoEstructura(false);
    }
  };

  /** Paso 2: Recalcular la estructura de costos */
  const handleRecalcular = async () => {
    setGenerandoEstructura(true);
    try {
      const resp = await iqeService.recalculateStructure({
        secciones,
        ganancia_porcentaje: parseFloat(parametros.ganancia) || 40,
        iva_porcentaje: parseFloat(parametros.iva) || 0,
        impuesto_porcentaje: parseFloat(parametros.impuesto) || 7,
        pct_mano_obra: parseFloat(parametros.pct_mano_obra) || 15,
        pct_gastos: parseFloat(parametros.pct_gastos) || 10,
      });

      setSecciones(resp.secciones);
      setResumen(resp.resumen);
      setMaterialesSinPrecio(resp.materiales_sin_precio);
    } catch (err: any) {
      setErrorAnalisis(err?.response?.data?.detail || 'Error al recalcular la estructura.');
    } finally {
      setGenerandoEstructura(false);
    }
  };

  /** Ir al paso final cargando clientes */
  const irAPasoFinal = async () => {
    try {
      const list = await clienteService.getAll();
      setClientes(list);
    } catch (e) {
      console.error('Error al cargar clientes:', e);
    }
    setPaso('finalizar');
  };

  /** Paso 3: Guardar cotización o nuevo producto */
  const handleGuardarFinal = async () => {
    setGuardando(true);
    setErrorFinal('');
    try {
      const resp = await iqeService.finalizeStructure({
        guardar_como: guardarComo,
        cliente_id: guardarComo === 'cotizacion' ? Number(clienteId) : undefined,
        nombre_producto: guardarComo === 'producto' ? nombreProducto : undefined,
        tipo_producto_id: guardarComo === 'producto' ? Number(tipoProductoId) : undefined,
        producto_base_id: productoBaseId,
        secciones,
        nuevo_ancho: parseFloat(parametros.ancho) || 1.6,
        nuevo_largo: parseFloat(parametros.largo) || 1.9,
        nuevo_alto: parseFloat(parametros.alto) || null,
        ganancia_porcentaje: parseFloat(parametros.ganancia) || 40,
        iva_porcentaje: parseFloat(parametros.iva) || 0,
        impuesto_porcentaje: parseFloat(parametros.impuesto) || 7,
        pct_mano_obra: parseFloat(parametros.pct_mano_obra) || 15,
        pct_gastos: parseFloat(parametros.pct_gastos) || 10,
        observaciones: observacionesFinal || null,
      });
      setCotizacionCreada({
        id: resp.cotizacion_id,
        total: resp.total_estimado,
        mensaje: resp.mensaje,
        pdfUrl: resp.pdf_url,
        isProduct: guardarComo === 'producto',
      });
    } catch (err: any) {
      setErrorFinal(err?.response?.data?.detail || 'Error al guardar.');
    } finally {
      setGuardando(false);
    }
  };

    /** Reiniciar el flujo completo */
  const handleNuevaCotizacion = () => {    setPaso('manual');
    setProductoBaseSel('');
    setContexto(null);
    setJsonIA('');
    setDescripcionMueble('');
    setSecciones([]);
    setResumen(null);
    setCotizacionCreada(null);
    setClienteId('');
    setObservacionesFinal('');
    setNombreProducto('');
    setTipoProductoId('');
    setErrorAnalisis('');
    setErrorFinal('');
    setProductoBaseId(null);
    setProductoBaseNombre(null);
    setScoreSimilitud(0);
  };

  const pasoActualNum = PASOS.find((p) => p.id === paso)?.num ?? 1;

  return (
    <div className="min-h-screen bg-yeikar-tertiary font-body">
      {/* Header */}
      <div className="bg-gradient-to-r from-yeikar-secondary to-yeikar-secondary-dark text-white px-6 py-5 shadow-lg">
        <div className="max-w-5xl mx-auto flex items-center gap-4">
          <div className="p-2.5 bg-yeikar-primary/20 rounded-xl border border-yeikar-primary/30">
            <svg className="w-7 h-7 text-yeikar-primary" fill="none" stroke="currentColor" viewBox="0 0 24 24">
              <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M9.663 17h4.673M12 3v1m6.364 1.636l-.707.707M21 12h-1M4 12H3m3.343-5.657l-.707-.707m2.828 9.9a5 5 0 117.072 0l-.548.547A3.374 3.374 0 0014 18.469V19a2 2 0 11-4 0v-.531c0-.895-.356-1.754-.988-2.386l-.548-.547z" />
            </svg>
          </div>
          <div>
            <h1 className="text-xl sm:text-2xl font-headline font-bold tracking-tight">Cotizador Inteligente</h1>
            <p className="text-xs text-white/70">100% manual · sin APIs de pago · guiado por IA de navegador y datos reales</p>
          </div>
        </div>
      </div>

      {/* Stepper */}
      <div className="bg-white border-b border-yeikar-tertiary-dark shadow-sm">
        <div className="max-w-5xl mx-auto px-6 py-3">
          <div className="flex items-center justify-between gap-2">
            {PASOS.map((p, i) => {
              const activo = p.id === paso;
              const completado = p.num < pasoActualNum;
              return (
                <div key={p.id} className="flex items-center gap-2 flex-1">
                  <div
                    className={`flex items-center gap-2 ${completado ? 'cursor-pointer' : ''}`}
                    onClick={() => (completado ? setPaso(p.id) : undefined)}
                  >
                    <div
                      className={`w-7 h-7 rounded-full flex items-center justify-center text-xs font-bold transition-all
                      ${activo ? 'bg-yeikar-primary text-yeikar-neutral shadow-md scale-110' :
                        completado ? 'bg-yeikar-primary/25 text-yeikar-primary-dark shadow' :
                        'bg-yeikar-secondary-light/10 text-yeikar-neutral/40'}`}
                    >
                      {completado ? '' : p.num}
                    </div>
                    <span
                      className={`text-xs font-bold hidden sm:block
                      ${activo ? 'text-yeikar-secondary' :
                        completado ? 'text-yeikar-primary-dark' : 'text-yeikar-neutral/40'}`}
                    >
                      {p.label}
                    </span>
                  </div>
                  {i < PASOS.length - 1 && (
                    <div className={`flex-1 h-0.5 mx-2 rounded ${p.num < pasoActualNum ? 'bg-yeikar-primary' : 'bg-yeikar-secondary-light/10'}`} />
                  )}
                </div>
              );
            })}
          </div>
        </div>
      </div>

      <div className="max-w-5xl mx-auto px-4 py-8">
        {/* ── PASO 1: Modo Manual (contexto + IA de navegador) ── */}
        {paso === 'manual' && (
          <div className="space-y-6">
            {/* Guía paso a paso */}
            <div className="grid grid-cols-1 sm:grid-cols-3 gap-3">
              {PASOS_GUIA.map((s) => (
                <div key={s.n} className="bg-white rounded-2xl border border-yeikar-secondary-light/10 p-4 shadow-card">
                  <div className="flex items-center gap-2 mb-1.5">
                    <span className="w-6 h-6 rounded-full bg-yeikar-primary text-yeikar-neutral font-black font-headline text-sm flex items-center justify-center">{s.n}</span>
                    <h3 className="font-headline font-bold text-sm text-yeikar-secondary">{s.t}</h3>
                  </div>
                  <p className="text-xs text-yeikar-neutral/60 leading-relaxed">{s.d}</p>
                </div>
              ))}
            </div>

            {/* Consejos según la IA */}
            <div className="bg-white rounded-2xl border border-yeikar-secondary-light/10 p-4 shadow-card">
              <h3 className="text-xs font-bold text-yeikar-neutral/70 uppercase tracking-wider mb-2"> Consejos según tu IA (para mejores resultados)</h3>
              <div className="grid grid-cols-1 sm:grid-cols-3 gap-2">
                {CONSEJOS_IA.map((c) => (
                  <div key={c.nombre} className="rounded-xl bg-yeikar-tertiary/50 border border-yeikar-secondary-light/10 px-3 py-2">
                    <span className="text-xs font-black text-yeikar-secondary">{c.nombre}</span>
                    <p className="text-[11px] text-yeikar-neutral/60 mt-0.5">{c.texto}</p>
                  </div>
                ))}
              </div>
              <p className="text-[11px] text-yeikar-neutral/50 mt-2">
                No cambies de chat entre el paso 1 y el 2: la IA necesita recordar lo que entendió del mueble.
              </p>
            </div>

            {/* Entrada: foto o descripción */}
            <div className="bg-white rounded-2xl border border-yeikar-secondary-light/10 p-5 shadow-card space-y-4">
              <div className="flex flex-col sm:flex-row sm:items-center sm:justify-between gap-3">
                <h3 className="text-sm font-bold text-yeikar-neutral uppercase tracking-wider">¿Cómo analizará la IA el mueble?</h3>
                <div className="flex gap-1.5 bg-yeikar-tertiary/60 rounded-xl p-1">
                  <button
                    onClick={() => setConFoto(true)}
                    className={`px-4 py-2 rounded-lg text-sm font-bold font-headline transition-all ${
                      conFoto ? 'bg-yeikar-primary text-yeikar-neutral shadow-sm' : 'text-yeikar-neutral/60 hover:bg-white'
                    }`}
                  >
                     Con foto
                  </button>
                  <button
                    onClick={() => setConFoto(false)}
                    className={`px-4 py-2 rounded-lg text-sm font-bold font-headline transition-all ${
                      !conFoto ? 'bg-yeikar-primary text-yeikar-neutral shadow-sm' : 'text-yeikar-neutral/60 hover:bg-white'
                    }`}
                  >
                     Sin foto (descripción)
                  </button>
                </div>
              </div>

              {!conFoto && (
                <div>
                  <label className="block text-xs font-semibold text-yeikar-neutral/60 mb-1">
                    Describe el mueble (o pega el mensaje del cliente) *
                  </label>
                  <textarea
                    value={descripcionMueble}
                    onChange={(e) => setDescripcionMueble(e.target.value)}
                    rows={3}
                    placeholder='Ej: "Cama matrimonial 1.60x1.90 en madera sólida, espaldar tapizado en tela lino beige, dos noches con 1 cajón cada uno, acabado laqueado mate"'
                    className="w-full border border-yeikar-secondary-light/15 rounded-xl px-4 py-3 text-sm focus:outline-none focus:ring-2 focus:ring-yeikar-primary/40 resize-none"
                  />
                  <p className="text-[11px] text-yeikar-neutral/50 mt-1">
                     Si tienes el mensaje de WhatsApp del cliente, pégalo tal cual — la IA entiende lenguaje cotidiano.
                  </p>
                </div>
              )}
            </div>

            {/* Producto de referencia + medidas */}
            <div className="bg-white rounded-2xl border border-yeikar-secondary-light/10 p-5 shadow-card space-y-4">
              <div className="flex items-center gap-2">
                <h3 className="text-sm font-bold text-yeikar-neutral uppercase tracking-wider">Referencia y medidas</h3>
                <span className="text-[10px] bg-yeikar-primary/15 text-yeikar-primary-dark font-bold px-2 py-0.5 rounded-full">OPCIONAL</span>
              </div>
              <div>
                <label className="block text-xs font-semibold text-yeikar-neutral/60 mb-1">
                  Tipo de mueble
                </label>
                <select
                  value={tipoMueble}
                  onChange={(e) => setTipoMueble(e.target.value)}
                  className="w-full border border-yeikar-secondary-light/15 rounded-lg px-3 py-2 text-sm bg-white focus:outline-none focus:ring-2 focus:ring-yeikar-primary/40"
                >
                  {TIPOS_MUEBLE.map((t) => (
                    <option key={t.value} value={t.value}>{t.label}</option>
                  ))}
                </select>
                <p className="text-[11px] text-yeikar-neutral/50 mt-1">
                  Afina la anatomía (secciones típicas) y el catálogo que recibe la IA. Con "Otro" usa el catálogo completo.
                </p>
              </div>
              <div className="grid grid-cols-1 sm:grid-cols-2 gap-3">
                <div>
                  <label className="block text-xs font-semibold text-yeikar-neutral/60 mb-1">
                    Producto similar (receta de referencia)
                  </label>
                  <SearchSelect
                    value={productoBaseSel}
                    onChange={(v) => setProductoBaseSel(String(v))}
                    options={[
                      { value: '', label: 'Ninguno — estructura desde cero' },
                      ...productos.map((p) => ({ value: p.id, label: p.nombre })),
                    ]}
                    placeholder="Ninguno — estructura desde cero"
                  />
                  <p className="text-[11px] text-yeikar-neutral/50 mt-1">
                    Si eliges uno, la IA recibirá su receta como guía de materiales y proporciones.
                  </p>
                </div>
                <div className="grid grid-cols-3 gap-2">
                  <div>
                    <label className="block text-xs font-semibold text-yeikar-neutral/60 mb-1">Ancho (m)</label>
                    <input type="number" step="0.01" min="0" value={parametros.ancho}
                      onChange={(e) => setParametros({ ...parametros, ancho: e.target.value })}
                      className="w-full border border-yeikar-secondary-light/15 rounded-lg px-2 py-2 text-sm font-mono focus:outline-none focus:ring-2 focus:ring-yeikar-primary/40" />
                  </div>
                  <div>
                    <label className="block text-xs font-semibold text-yeikar-neutral/60 mb-1">Largo (m)</label>
                    <input type="number" step="0.01" min="0" value={parametros.largo}
                      onChange={(e) => setParametros({ ...parametros, largo: e.target.value })}
                      className="w-full border border-yeikar-secondary-light/15 rounded-lg px-2 py-2 text-sm font-mono focus:outline-none focus:ring-2 focus:ring-yeikar-primary/40" />
                  </div>
                  <div>
                    <label className="block text-xs font-semibold text-yeikar-neutral/60 mb-1">Alto (m)</label>
                    <input type="number" step="0.01" min="0" value={parametros.alto}
                      onChange={(e) => setParametros({ ...parametros, alto: e.target.value })}
                      className="w-full border border-yeikar-secondary-light/15 rounded-lg px-2 py-2 text-sm font-mono focus:outline-none focus:ring-2 focus:ring-yeikar-primary/40" />
                  </div>
                </div>
              </div>
              <button
                onClick={handleGenerarContexto}
                disabled={generandoContexto || (!conFoto && !descripcionMueble.trim())}
                className="w-full py-3 bg-yeikar-primary text-yeikar-neutral rounded-xl font-bold font-headline hover:bg-yeikar-primary/90 transition-all disabled:opacity-40 text-sm flex items-center justify-center gap-2"
              >
                {generandoContexto ? (
                  <>
                    <svg className="animate-spin w-4 h-4" fill="none" viewBox="0 0 24 24">
                      <circle className="opacity-25" cx="12" cy="12" r="10" stroke="currentColor" strokeWidth="4" />
                      <path className="opacity-75" fill="currentColor" d="M4 12a8 8 0 018-8V0C5.373 0 0 5.373 0 12h4z" />
                    </svg>
                    Generando contexto del negocio...
                  </>
                ) : (
                  ' Generar contexto para la IA'
                )}
              </button>
            </div>

            {/* Paquete de contexto generado */}
            {contexto && (
              <div className="bg-white rounded-2xl border border-yeikar-secondary-light/10 p-5 shadow-card space-y-3">
                <div className="flex flex-wrap items-center justify-between gap-2">
                  <h3 className="text-sm font-bold text-yeikar-neutral uppercase tracking-wider">
                    Instrucciones para la IA
                    {contexto.producto_base_id && (
                      <span className="ml-2 text-[11px] font-mono text-yeikar-neutral/50 normal-case">
                        · Ref: {contexto.producto_base_nombre}
                      </span>
                    )}
                  </h3>
                  <div className="flex gap-2">
                    <button
                      onClick={handleCopiarContexto}
                      className="px-3 py-1.5 bg-yeikar-secondary text-white rounded-lg text-xs font-bold hover:bg-yeikar-secondary-light transition-all"
                    >
                      {copiado ? '¡Copiado!' : 'Copiar prompt'}
                    </button>
                    <button
                      onClick={handleDescargarContexto}
                      className="px-3 py-1.5 border border-yeikar-secondary-light/25 text-yeikar-secondary rounded-lg text-xs font-bold hover:bg-yeikar-tertiary transition-all"
                    >
                       Descargar .md
                    </button>
                    <button
                      onClick={handleDescargarInventarioJson}
                      title="Inventario estructurado (JSON) para IA que aceptan archivos"
                      className="px-3 py-1.5 border border-yeikar-secondary-light/25 text-yeikar-secondary rounded-lg text-xs font-bold hover:bg-yeikar-tertiary transition-all"
                    >
                       inventario.json
                    </button>
                  </div>
                </div>

                {/* Librería de prompts */}
                {contexto.prompts.length > 0 && (
                  <>
                    <div className="grid grid-cols-1 sm:grid-cols-2 lg:grid-cols-3 gap-2">
                      {contexto.prompts.map((p) => (
                        <button
                          key={p.id}
                          onClick={() => setPromptActivoId(p.id)}
                          title={p.descripcion}
                          className={`text-left px-3 py-2 rounded-xl border text-xs font-bold transition-all ${
                            promptActivo?.id === p.id
                              ? 'bg-yeikar-primary/15 border-yeikar-primary/50 text-yeikar-secondary'
                              : 'border-yeikar-secondary-light/15 text-yeikar-neutral/60 hover:bg-yeikar-tertiary'
                          }`}
                        >
                          {p.titulo}
                        </button>
                      ))}
                    </div>
                    {promptActivo && (
                      <p className="text-[11px] text-yeikar-neutral/50">
                         {promptActivo.descripcion}
                      </p>
                    )}
                  </>
                )}

                <textarea
                  readOnly
                  value={promptActivo?.instrucciones ?? contexto.instrucciones}
                  rows={16}
                  className="w-full border border-yeikar-secondary-light/15 rounded-xl px-4 py-3 text-xs font-mono bg-yeikar-tertiary/40 focus:outline-none resize-y"
                />
                <p className="text-[11px] text-yeikar-neutral/50">
                  Inventario con <strong>{contexto.inventario.length}</strong> materiales · Copia el prompt seleccionado,{' '}
                  {conFoto ? 'adjunta la foto del mueble' : 'incluye la descripción'} en tu IA y pégalo.
                </p>
              </div>
            )}

            {/* Pegar la respuesta de la IA */}
            <div className="bg-white rounded-2xl border border-yeikar-secondary-light/10 p-5 shadow-card space-y-3">
              <div className="flex flex-wrap items-center justify-between gap-2">
                <h3 className="text-sm font-bold text-yeikar-neutral uppercase tracking-wider">Respuesta de la IA</h3>
                <div className="flex gap-2">
                  <button
                    onClick={() => { setJsonIA(EJEMPLO_EXCEL); setErrorAnalisis(''); }}
                    className="px-3 py-1.5 border border-yeikar-primary/40 text-yeikar-secondary rounded-lg text-xs font-bold hover:bg-yeikar-primary/10 transition-all"
                  >
                     Probar con un ejemplo
                  </button>
                  <button
                    onClick={() => jsonFileRef.current?.click()}
                    className="px-3 py-1.5 border border-yeikar-secondary-light/25 text-yeikar-secondary rounded-lg text-xs font-bold hover:bg-yeikar-tertiary transition-all"
                  >
                     Cargar .txt / .json
                  </button>
                  <input
                    ref={jsonFileRef}
                    type="file"
                    accept=".txt,.md,.json,text/plain,application/json"
                    className="hidden"
                    onChange={(e) => {
                      const f = e.target.files?.[0];
                      if (f) handleCargarArchivoJson(f);
                      e.target.value = '';
                    }}
                  />
                </div>
              </div>
              <textarea
                value={jsonIA}
                onChange={(e) => setJsonIA(e.target.value)}
                rows={10}
                placeholder='Pega aquí la tabla que devolvió la IA (secciones + MATERIAL | CANTIDAD | UNIDAD | V/UNIT | PRECIO TOTAL)...'
                className="w-full border border-yeikar-secondary-light/15 rounded-xl px-4 py-3 text-xs font-mono focus:outline-none focus:ring-2 focus:ring-yeikar-primary/40 resize-y"
              />
              <button
                onClick={handleImportarEstructura}
                disabled={!jsonIA.trim() || importandoEstructura}
                className="w-full py-3 bg-yeikar-secondary text-white rounded-xl font-bold hover:bg-yeikar-secondary-light transition-all disabled:opacity-40 text-sm flex items-center justify-center gap-2"
              >
                {importandoEstructura ? (
                  <>
                    <svg className="animate-spin w-4 h-4" fill="none" viewBox="0 0 24 24">
                      <circle className="opacity-25" cx="12" cy="12" r="10" stroke="currentColor" strokeWidth="4" />
                      <path className="opacity-75" fill="currentColor" d="M4 12a8 8 0 018-8V0C5.373 0 0 5.373 0 12h4z" />
                    </svg>
                    Importando y matcheando con el inventario...
                  </>
                ) : (
                  ' Importar estructura y continuar →'
                )}
              </button>
              <p className="text-[11px] text-yeikar-neutral/50">
                 Si la IA no devolvió la tabla bien formada, pídele con el prompt "Reparar respuesta" y pega el resultado aquí.
              </p>
            </div>

            {errorAnalisis && (
              <div className="bg-red-50 border border-red-200 rounded-xl p-4 text-sm text-red-700 font-semibold">
                 {errorAnalisis}
              </div>
            )}
          </div>
        )}

        {/* ── PASO 2: Estructura de Costos del Borrador ── */}
        {paso === 'borrador' && (
          <div className="space-y-6">
            <div className="flex flex-col sm:flex-row sm:items-center sm:justify-between gap-4">
              <div>
                <h2 className="text-xl sm:text-2xl font-headline font-bold text-yeikar-secondary">
                  Estructura de Costos del Borrador
                </h2>
                {productoBaseNombre && (
                  <p className="text-xs text-yeikar-neutral/50 mt-1">
                    Fusión guiada por plantilla: <strong>{productoBaseNombre}</strong> ({scoreSimilitud}% similitud)
                  </p>
                )}
              </div>
              <div className="flex items-center gap-3">
                <span className="text-xs font-semibold text-yeikar-neutral/60">Medidas:</span>
                <span className="bg-yeikar-primary/10 border border-yeikar-primary/30 text-yeikar-secondary text-xs font-bold font-mono px-3 py-1 rounded-lg">
                  {parametros.ancho}m × {parametros.largo}m{parametros.alto ? ` × ${parametros.alto}m` : ''}
                </span>
              </div>
            </div>

            {/* Panel de dimensiones y desgloses de costos */}
            <div className="grid grid-cols-1 lg:grid-cols-3 gap-6 items-start">
              <div className="lg:col-span-2 space-y-6">
                {/* Advertencias de validación post-import */}
                {advertenciaImport && (
                  <div className="bg-amber-50 border border-amber-300 rounded-xl p-4 text-sm text-amber-800">
                     {advertenciaImport}
                    {seccionesFaltantes.length > 0 && (
                      <span className="block mt-1 text-xs">
                        Secciones pendientes: {seccionesFaltantes.join(', ')}
                      </span>
                    )}
                  </div>
                )}
                {/* Resumen del import */}
                {(() => {
                  const totalItems = secciones.reduce((n, s) => n + s.items.length, 0);
                  const mapeados = secciones.reduce((n, s) => n + s.items.filter((i) => i.material_id).length, 0);
                  if (totalItems === 0) return null;
                  return (
                    <div className="grid grid-cols-3 gap-3">
                      <div className="bg-green-50 border border-green-200 rounded-xl p-3 text-center">
                        <p className="text-xs font-mono text-green-600 mb-0.5"> Matcheados con inventario</p>
                        <p className="font-headline font-bold text-green-700 text-xl">{mapeados}</p>
                      </div>
                      <div className="bg-amber-50 border border-amber-200 rounded-xl p-3 text-center">
                        <p className="text-xs font-mono text-amber-600 mb-0.5"> Pendientes</p>
                        <p className="font-headline font-bold text-amber-700 text-xl">{materialesSinPrecio}</p>
                      </div>
                      <div className="bg-yeikar-tertiary/60 border border-yeikar-secondary-light/10 rounded-xl p-3 text-center">
                        <p className="text-xs font-mono text-yeikar-neutral/50 mb-0.5">Líneas totales</p>
                        <p className="font-headline font-bold text-yeikar-neutral text-xl">{totalItems}</p>
                      </div>
                    </div>
                  );
                })()}

                {materialesSinPrecio > 0 && (
                  <div className="bg-red-50 border border-red-200 text-red-800 rounded-xl px-5 py-3 text-xs sm:text-sm font-semibold flex items-center gap-2">
                    <span> Tienes {materialesSinPrecio} material(es) sin precio asignado. Ingrese un costo unitario temporal o registre el material formalmente.</span>
                  </div>
                )}

                <EstructuraCostosEditor
                  secciones={secciones}
                  onChange={(sec) => setSecciones(sec)}
                  onRecalculate={handleRecalcular}
                  unidades={unidades}
                  isLoading={generandoEstructura}
                />
              </div>

              {/* ERP Summary sidebar */}
              <div className="space-y-6">
                {/* Parámetros Rápidos */}
                <div className="bg-white rounded-2xl border border-yeikar-secondary-light/10 p-5 shadow-card space-y-3">
                  <h4 className="text-xs font-bold text-yeikar-neutral/60 uppercase tracking-wider mb-2">Parámetros Financieros</h4>
                  <div className="grid grid-cols-2 gap-2 text-xs">
                    <div>
                      <label className="block text-yeikar-neutral/50 font-medium mb-1">Mano de Obra %</label>
                      <input
                        type="number"
                        value={parametros.pct_mano_obra}
                        onChange={(e) => setParametros({ ...parametros, pct_mano_obra: e.target.value })}
                        className="w-full border border-yeikar-secondary-light/15 rounded-lg px-2.5 py-1.5 font-mono focus:outline-none focus:ring-1 focus:ring-yeikar-primary"
                      />
                    </div>
                    <div>
                      <label className="block text-yeikar-neutral/50 font-medium mb-1">Gastos %</label>
                      <input
                        type="number"
                        value={parametros.pct_gastos}
                        onChange={(e) => setParametros({ ...parametros, pct_gastos: e.target.value })}
                        className="w-full border border-yeikar-secondary-light/15 rounded-lg px-2.5 py-1.5 font-mono focus:outline-none focus:ring-1 focus:ring-yeikar-primary"
                      />
                    </div>
                    <div>
                      <label className="block text-yeikar-neutral/50 font-medium mb-1">Ganancia %</label>
                      <input
                        type="number"
                        value={parametros.ganancia}
                        onChange={(e) => setParametros({ ...parametros, ganancia: e.target.value })}
                        className="w-full border border-yeikar-secondary-light/15 rounded-lg px-2.5 py-1.5 font-mono focus:outline-none focus:ring-1 focus:ring-yeikar-primary"
                      />
                    </div>
                    <div>
                      <label className="block text-yeikar-neutral/50 font-medium mb-1">IVA %</label>
                      <input
                        type="number"
                        value={parametros.iva}
                        onChange={(e) => setParametros({ ...parametros, iva: e.target.value })}
                        className="w-full border border-yeikar-secondary-light/15 rounded-lg px-2.5 py-1.5 font-mono focus:outline-none focus:ring-1 focus:ring-yeikar-primary"
                      />
                    </div>
                    <div>
                      <label className="block text-yeikar-neutral/50 font-medium mb-1" title="Impuestos adicionales sobre el costo de producción">Impuestos %</label>
                      <input
                        type="number"
                        value={parametros.impuesto}
                        onChange={(e) => setParametros({ ...parametros, impuesto: e.target.value })}
                        className="w-full border border-yeikar-secondary-light/15 rounded-lg px-2.5 py-1.5 font-mono focus:outline-none focus:ring-1 focus:ring-yeikar-primary"
                      />
                    </div>
                  </div>
                </div>

                {/* Resumen de totales */}
                {resumen && (
                  <div className="bg-yeikar-secondary text-white rounded-2xl p-6 shadow-lift space-y-4">
                    <h3 className="font-headline font-bold text-base border-b border-white/10 pb-2">
                      Resumen del ERP
                    </h3>
                    <button
                      onClick={() => setShowEstructura(true)}
                      className="w-full text-xs font-bold text-yeikar-primary-light hover:text-white uppercase tracking-wider underline underline-offset-4"
                    >
                      Ver estructura de costos (Excel)
                    </button>
                    <div className="space-y-2 text-xs sm:text-sm">
                      <div className="flex justify-between">
                        <span className="text-white/60">Costo Materiales</span>
                        <span className="font-mono">${resumen.costo_materiales.toLocaleString('es-CO', { minimumFractionDigits: 2 })}</span>
                      </div>
                      <div className="flex justify-between">
                        <span className="text-white/60">Mano de Obra ({parametros.pct_mano_obra}%)</span>
                        <span className="font-mono">${resumen.costo_mano_obra.toLocaleString('es-CO', { minimumFractionDigits: 2 })}</span>
                      </div>
                      <div className="flex justify-between">
                        <span className="text-white/60">Gastos Generales ({parametros.pct_gastos}%)</span>
                        <span className="font-mono">${resumen.costo_gastos.toLocaleString('es-CO', { minimumFractionDigits: 2 })}</span>
                      </div>
                      <div className="flex justify-between border-t border-white/10 pt-2 font-semibold">
                        <span>Costo de Producción</span>
                        <span className="font-mono">${resumen.costo_produccion.toLocaleString('es-CO', { minimumFractionDigits: 2 })}</span>
                      </div>
                      {Number(resumen.impuestos) > 0 && (
                        <div className="flex justify-between text-white/80">
                          <span>Impuestos ({Number(resumen.impuesto_porcentaje) || parametros.impuesto}%)</span>
                          <span className="font-mono">${Number(resumen.impuestos).toLocaleString('es-CO', { minimumFractionDigits: 2 })}</span>
                        </div>
                      )}
                      <div className="flex justify-between text-white/80">
                        <span>Ganancia ({parametros.ganancia}%)</span>
                        <span className="font-mono">${(resumen.precio_sin_iva - (resumen.base_con_impuestos || resumen.costo_produccion)).toLocaleString('es-CO', { minimumFractionDigits: 2 })}</span>
                      </div>
                    </div>

                    <div className="border-t border-white/20 pt-4 space-y-1 text-right">
                      <p className="text-xs text-white/50">Precio Final sugerido</p>
                      <p className="text-2xl font-bold font-mono text-yeikar-primary">
                        ${resumen.precio_con_iva.toLocaleString('es-CO', { minimumFractionDigits: 2 })}
                      </p>
                      {parseFloat(parametros.iva) > 0 && (
                        <p className="text-[10px] text-white/40">Con IVA ({parametros.iva}%) incluido</p>
                      )}
                    </div>
                  </div>
                )}
              </div>
            </div>

            {errorAnalisis && (
              <div className="bg-red-50 border border-red-200 rounded-xl p-4 text-sm text-red-700 font-semibold">
                 {errorAnalisis}
              </div>
            )}

            <div className="flex gap-3">
              <button
                type="button"
                onClick={() => setPaso('manual')}
                className="flex-1 py-3 border border-yeikar-secondary-light/15 text-yeikar-neutral/70 rounded-xl font-semibold hover:bg-yeikar-tertiary transition-all"
              >
                ← Volver al Paso 1
              </button>
              <button
                type="button"
                onClick={irAPasoFinal}
                disabled={materialesSinPrecio > 0}
                className="flex-2 flex-grow-[2] py-3 bg-yeikar-secondary text-white rounded-xl font-bold hover:bg-yeikar-secondary-light transition-all shadow-md flex items-center justify-center gap-2 disabled:opacity-40"
              >
                Finalizar y Guardar →
              </button>
            </div>
          </div>
        )}

        {/* ── PASO 3: Guardar y Persistir ── */}
        {paso === 'finalizar' && !cotizacionCreada && resumen && (
          <div className="space-y-6">
            <div>
              <h2 className="text-xl sm:text-2xl font-headline font-bold text-yeikar-secondary">Confirmar Guardado</h2>
              <p className="text-sm text-yeikar-neutral/60 mt-1">
                Elige si deseas registrar la estructura como una Cotización formal de venta o como una nueva Plantilla de Producto.
              </p>
            </div>

            {/* Resumen compacto de precio */}
            <div className="bg-yeikar-primary/10 border border-yeikar-primary/30 rounded-2xl p-5 flex flex-col sm:flex-row sm:items-center sm:justify-between gap-4">
              <div className="space-y-1">
                <span className="text-[10px] text-yeikar-secondary font-bold uppercase tracking-wider">Monto Final</span>
                <p className="text-3xl font-bold font-mono text-yeikar-secondary">
                  ${resumen.precio_con_iva.toLocaleString('es-CO', { minimumFractionDigits: 2 })}
                </p>
              </div>
              <div className="grid grid-cols-2 gap-x-6 gap-y-1 text-xs">
                <span className="text-yeikar-neutral/50">Ancho/Largo:</span>
                <span className="font-semibold text-yeikar-neutral">{parametros.ancho}m × {parametros.largo}m{parametros.alto ? ` × ${parametros.alto}m` : ''}</span>
                <span className="text-yeikar-neutral/50">Costo Prod:</span>
                <span className="font-semibold font-mono text-yeikar-neutral">${resumen.costo_produccion.toLocaleString('es-CO', { minimumFractionDigits: 2 })}</span>
              </div>
            </div>

            {/* Toggle tipo guardado */}
            <div className="bg-white rounded-2xl border border-yeikar-secondary-light/10 shadow-card overflow-hidden">
              <div className="grid grid-cols-2 divide-x divide-yeikar-secondary-light/10 border-b border-yeikar-secondary-light/10">
                <button
                  type="button"
                  onClick={() => setGuardarComo('cotizacion')}
                  className={`py-4 text-center font-semibold text-sm transition-all flex items-center justify-center gap-2
                    ${guardarComo === 'cotizacion' ? 'bg-yeikar-primary/10 text-yeikar-secondary font-bold' : 'text-yeikar-neutral/50 hover:bg-yeikar-tertiary'}`}
                >
                   Guardar como Cotización
                </button>
                <button
                  type="button"
                  onClick={() => setGuardarComo('producto')}
                  className={`py-4 text-center font-semibold text-sm transition-all flex items-center justify-center gap-2
                    ${guardarComo === 'producto' ? 'bg-yeikar-primary/10 text-yeikar-secondary font-bold' : 'text-yeikar-neutral/50 hover:bg-yeikar-tertiary'}`}
                >
                   Guardar como Nuevo Producto
                </button>
              </div>

              <div className="p-6 space-y-4">
                {guardarComo === 'cotizacion' ? (
                  <div className="space-y-4">
                    <div>
                      <label className="block text-sm font-semibold text-yeikar-neutral mb-2">Cliente *</label>
                      <SearchSelect
                        value={clienteId}
                        onChange={(v) => setClienteId(String(v))}
                        options={clientes.map((c) => ({ value: c.id, label: c.nombre }))}
                        placeholder="Seleccione un cliente..."
                      />
                    </div>
                    <div>
                      <label className="block text-sm font-semibold text-yeikar-neutral mb-2">Observaciones</label>
                      <textarea
                        value={observacionesFinal}
                        onChange={(e) => setObservacionesFinal(e.target.value)}
                        placeholder="Observaciones de venta o requerimientos específicos del cliente..."
                        rows={3}
                        className="w-full border border-yeikar-secondary-light/15 rounded-xl px-4 py-3 text-sm focus:outline-none focus:ring-2 focus:ring-yeikar-primary/40 resize-none"
                      />
                    </div>
                  </div>
                ) : (
                  <div className="space-y-4">
                    <div>
                      <label className="block text-sm font-semibold text-yeikar-neutral mb-2">Nombre de la Plantilla / Producto *</label>
                      <input
                        type="text"
                        required
                        placeholder="Ej. CAMA FLOTANTE NÓRDICA V2"
                        value={nombreProducto}
                        onChange={(e) => setNombreProducto(e.target.value)}
                        className="w-full border border-yeikar-secondary-light/15 rounded-xl px-4 py-3 text-sm focus:outline-none focus:ring-2 focus:ring-yeikar-primary/40 uppercase"
                      />
                    </div>
                    <div className="grid grid-cols-1 sm:grid-cols-2 gap-4">
                      <div>
                        <label className="block text-sm font-semibold text-yeikar-neutral mb-2">Categoría de Producto *</label>
                        <SearchSelect
                          value={tipoProductoId}
                          onChange={(v) => setTipoProductoId(String(v))}
                          options={tiposProducto.map((tp) => ({ value: tp.id, label: tp.nombre }))}
                          placeholder="Seleccione categoría..."
                        />
                      </div>
                      <div>
                        <label className="block text-sm font-semibold text-yeikar-neutral mb-2">Descripción del Producto</label>
                        <input
                          type="text"
                          placeholder="Notas o especificaciones para catálogo..."
                          value={observacionesFinal}
                          onChange={(e) => setObservacionesFinal(e.target.value)}
                          className="w-full border border-yeikar-secondary-light/15 rounded-xl px-4 py-3 text-sm focus:outline-none focus:ring-2 focus:ring-yeikar-primary/40"
                        />
                      </div>
                    </div>
                    <p className="text-xs text-yeikar-primary-dark bg-yeikar-primary/10 border border-yeikar-primary/30 rounded-lg p-3 font-semibold">
                       Al guardar como Producto, la receta detallada se almacenará como receta paramétrica base. Esto te permitirá usar este producto como plantilla idéntica para cotizaciones futuras.
                    </p>
                  </div>
                )}
              </div>
            </div>

            {errorFinal && (
              <div className="bg-red-50 border border-red-200 rounded-xl p-4 text-sm text-red-700 font-semibold">
                 {errorFinal}
              </div>
            )}

            <div className="flex gap-3">
              <button
                type="button"
                onClick={() => setPaso('borrador')}
                className="flex-1 py-3 border border-yeikar-secondary-light/15 text-yeikar-neutral/70 rounded-xl font-semibold hover:bg-yeikar-tertiary transition-all"
              >
                ← Volver a Estructura
              </button>
              <button
                type="button"
                onClick={handleGuardarFinal}
                disabled={guardando}
                className="flex-2 flex-grow-[2] py-4 bg-yeikar-primary text-yeikar-neutral rounded-xl font-bold hover:bg-yeikar-primary-dark transition-all shadow-md flex items-center justify-center gap-2"
              >
                {guardando ? (
                  <><svg className="animate-spin w-5 h-5" fill="none" viewBox="0 0 24 24"><circle className="opacity-25" cx="12" cy="12" r="10" stroke="currentColor" strokeWidth="4" /><path className="opacity-75" fill="currentColor" d="M4 12a8 8 0 018-8V0C5.373 0 0 5.373 0 12h4z" /></svg> Guardando...</>
                ) : (
                  'Confirmar y Registrar'
                )}
              </button>
            </div>
          </div>
        )}

        {/* ── Cotización / Producto creado exitosamente ── */}
        {paso === 'finalizar' && cotizacionCreada && (
          <div className="text-center space-y-6 py-10 bg-white border border-yeikar-secondary-light/10 rounded-2xl shadow-card max-w-2xl mx-auto p-8">
            <div className="w-20 h-20 bg-yeikar-primary/15 rounded-full flex items-center justify-center mx-auto shadow-inner">
              <svg className="w-10 h-10 text-yeikar-primary-dark" fill="none" stroke="currentColor" viewBox="0 0 24 24">
                <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M9 12l2 2 4-4m6 2a9 9 0 11-18 0 9 9 0 0118 0z" />
              </svg>
            </div>
            <div className="space-y-2">
              <h2 className="text-2xl font-headline font-bold text-yeikar-primary-dark">¡Registro exitoso!</h2>
              <p className="text-sm text-yeikar-neutral/60">{cotizacionCreada.mensaje}</p>
              {cotizacionCreada.id > 0 ? (
                <p className="text-xs text-yeikar-neutral/50 font-mono">
                  Cotización #{cotizacionCreada.id} registrada con un monto final de{' '}
                  <strong className="text-yeikar-secondary">${cotizacionCreada.total.toLocaleString('es-CO', { minimumFractionDigits: 2 })}</strong>
                </p>
              ) : (
                <p className="text-xs text-yeikar-neutral/50 font-mono">
                  Producto de catálogo guardado con un costo sugerido de{' '}
                  <strong className="text-yeikar-secondary">${cotizacionCreada.total.toLocaleString('es-CO', { minimumFractionDigits: 2 })}</strong>
                </p>
              )}
            </div>
            <div className="flex gap-3 justify-center pt-2">
              {cotizacionCreada.isProduct ? (
                <a
                  href="/productos"
                  className="px-6 py-3 bg-yeikar-secondary text-white rounded-xl font-bold hover:bg-yeikar-secondary-light transition-all shadow"
                >
                  Ver Productos
                </a>
              ) : (
                <a
                  href="/cotizaciones"
                  className="px-6 py-3 bg-yeikar-secondary text-white rounded-xl font-bold hover:bg-yeikar-secondary-light transition-all shadow"
                >
                  Ver Cotizaciones
                </a>
              )}
              <button
                type="button"
                onClick={handleNuevaCotizacion}
                className="px-6 py-3 border border-yeikar-secondary-light/15 text-yeikar-neutral/70 rounded-xl font-semibold hover:bg-yeikar-tertiary transition-all"
              >
                Nueva Cotización
              </button>
            </div>
          </div>
        )}
      </div>

      {/* Modal: estructura de costos estilo Excel */}
      <Modal
        open={showEstructura}
        onClose={() => setShowEstructura(false)}
        title="Estructura de Costos"
        subtitle="Cotizador IA"
        size="4xl"
        footer={<button onClick={() => setShowEstructura(false)} className="btn btn-outline">Cerrar</button>}
      >
        <EstructuraCostos data={normalizarEstructuraIQE({ secciones, resumen })} />
      </Modal>
    </div>
  );
}
