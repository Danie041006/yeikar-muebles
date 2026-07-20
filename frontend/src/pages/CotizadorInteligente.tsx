import { useState, useRef, useCallback, useEffect } from 'react';
import {
  iqeService,
  type FurnitureAttributesOut,
  type SeccionCostoOut,
  type ResumenCostosOut,
  type UnidadMedida,
  type TipoProducto,
} from '../services/iqeService';
import { clienteService, type Client } from '../services/clienteService';
import EstructuraCostosEditor from '../components/EstructuraCostosEditor';

// ─── Tipos de estado local ────────────────────────────────────────────────────

type Paso = 'upload' | 'validar' | 'borrador' | 'finalizar';

interface AtributosEditables extends FurnitureAttributesOut {}

interface ParametrosForm {
  ancho: string;
  largo: string;
  ganancia: string;
  iva: string;
  pct_mano_obra: string;
  pct_gastos: string;
}

// ─── Constantes de la UI ──────────────────────────────────────────────────────

const TIPOS_MUEBLE = [
  'cama', 'nochero', 'closet', 'tocador', 'armario',
  'sala', 'comedor', 'escritorio', 'rack_tv', 'libreria', 'mueble_bano', 'otro',
];

const FAMILIAS = ['tapizada', 'melamina', 'madera_solida', 'mdf_laqueado', 'metalica', 'mixta'];
const ESTILOS = ['moderno', 'clasico', 'rustico', 'minimalista', 'industrial'];
const PATAS = ['metal', 'madera', 'sin_patas', 'ruedas'];

const PASOS: { id: Paso; label: string; num: number }[] = [
  { id: 'upload', label: 'Foto', num: 1 },
  { id: 'validar', label: 'Validar IA', num: 2 },
  { id: 'borrador', label: 'Estructura', num: 3 },
  { id: 'finalizar', label: 'Finalizar', num: 4 },
];

const CONFIANZA_COLOR = (c: number) => {
  if (c >= 0.85) return 'text-emerald-600 bg-emerald-50';
  if (c >= 0.70) return 'text-amber-600 bg-amber-50';
  return 'text-red-600 bg-red-50';
};

export default function CotizadorInteligente() {
  // ── Estado de navegación ──
  const [paso, setPaso] = useState<Paso>('upload');

  // ── Paso 1: Subida de imagen ──
  const [imagenFile, setImagenFile] = useState<File | null>(null);
  const [imagenPreview, setImagenPreview] = useState<string | null>(null);
  const [contextoAdicional, setContextoAdicional] = useState('');
  const [analizando, setAnalizando] = useState(false);
  const [errorAnalisis, setErrorAnalisis] = useState('');
  const fileInputRef = useRef<HTMLInputElement>(null);

  // ── Paso 2: Atributos de la IA (editables) ──
  const [atributos, setAtributos] = useState<AtributosEditables | null>(null);

  // ── Parámetros de dimensiones y costos ──
  const [parametros, setParametros] = useState<ParametrosForm>({
    ancho: '1.60',
    largo: '1.90',
    ganancia: '40',
    iva: '0',
    pct_mano_obra: '15',
    pct_gastos: '10',
  });

  // ── Paso 3: Estructura de Costos ──
  const [secciones, setSecciones] = useState<SeccionCostoOut[]>([]);
  const [resumen, setResumen] = useState<ResumenCostosOut | null>(null);
  const [materialesSinPrecio, setMaterialesSinPrecio] = useState(0);
  const [productoBaseId, setProductoBaseId] = useState<number | null>(null);
  const [productoBaseNombre, setProductoBaseNombre] = useState<string | null>(null);
  const [scoreSimilitud, setScoreSimilitud] = useState(0);
  const [generandoEstructura, setGenerandoEstructura] = useState(false);

  // Catálogos auxiliares
  const [unidades, setUnidades] = useState<UnidadMedida[]>([]);
  const [tiposProducto, setTiposProducto] = useState<TipoProducto[]>([]);

  // ── Paso 4: Finalizar y guardar ──
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

  const handleImagenSelect = useCallback((file: File) => {
    if (!['image/jpeg', 'image/jpg', 'image/png', 'image/webp'].includes(file.type)) {
      setErrorAnalisis('Solo se aceptan imágenes JPEG, PNG o WEBP.');
      return;
    }
    if (file.size > 10 * 1024 * 1024) {
      setErrorAnalisis('La imagen no puede superar 10 MB.');
      return;
    }
    setImagenFile(file);
    setErrorAnalisis('');
    const reader = new FileReader();
    reader.onload = (e) => setImagenPreview(e.target?.result as string);
    reader.readAsDataURL(file);
  }, []);

  const handleDrop = useCallback((e: React.DragEvent) => {
    e.preventDefault();
    const file = e.dataTransfer.files[0];
    if (file) handleImagenSelect(file);
  }, [handleImagenSelect]);

  /** Paso 1 → Paso 2: Analizar imagen con IA */
  const handleAnalizar = async () => {
    if (!imagenFile) return;
    setAnalizando(true);
    setErrorAnalisis('');
    try {
      const resultado = await iqeService.analyzeImage(imagenFile, contextoAdicional);
      setAtributos(resultado);
      // Prellenado de nombre si se crea producto después
      setNombreProducto(`NUEVO MUEBLE ${resultado.tipo_mueble.toUpperCase()}`);
      setPaso('validar');
    } catch (err: any) {
      setErrorAnalisis(
        err?.response?.data?.detail ||
          'Error al analizar la imagen. Verifica la API de OpenAI y las credenciales.'
      );
    } finally {
      setAnalizando(false);
    }
  };

  /** Paso 2 → Paso 3: Generar la estructura de costos inteligente */
  const handleGenerarEstructura = async () => {
    if (!atributos) return;
    setGenerandoEstructura(true);
    setErrorAnalisis('');
    try {
      const resp = await iqeService.generateStructure({
        tipo_mueble: atributos.tipo_mueble,
        atributos: {
          familia_probable: atributos.familia_probable,
          estilo_general: atributos.estilo_general,
          tipo_patas: atributos.tipo_patas,
          tiene_tapiceria: atributos.tiene_tapiceria,
          tiene_luces: atributos.tiene_luces,
          observaciones: atributos.observaciones,
          atributos_extra: atributos.atributos_extra,
        },
        estructura_propuesta: atributos.estructura_propuesta,
        nuevo_ancho: parseFloat(parametros.ancho) || 1.60,
        nuevo_largo: parseFloat(parametros.largo) || 1.90,
        ganancia_porcentaje: parseFloat(parametros.ganancia) || 40,
        iva_porcentaje: parseFloat(parametros.iva) || 0,
        pct_mano_obra: parseFloat(parametros.pct_mano_obra) || 15,
        pct_gastos: parseFloat(parametros.pct_gastos) || 10,
      });

      setSecciones(resp.secciones);
      setResumen(resp.resumen);
      setMaterialesSinPrecio(resp.materiales_sin_precio);
      setProductoBaseId(resp.producto_base_id);
      setProductoBaseNombre(resp.producto_base_nombre);
      setScoreSimilitud(Math.round(resp.score_similitud * 100));

      setPaso('borrador');
    } catch (err: any) {
      setErrorAnalisis(err?.response?.data?.detail || 'Error al generar la estructura de costos.');
    } finally {
      setGenerandoEstructura(false);
    }
  };

  /** Paso 3: Recalcular la estructura de costos */
  const handleRecalcular = async () => {
    setGenerandoEstructura(true);
    try {
      const resp = await iqeService.recalculateStructure({
        secciones,
        ganancia_porcentaje: parseFloat(parametros.ganancia) || 40,
        iva_porcentaje: parseFloat(parametros.iva) || 0,
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

  /** Paso 4: Guardar cotización o nuevo producto */
  const handleGuardarFinal = async () => {
    setErrorFinal('');
    if (guardarComo === 'cotizacion' && !clienteId) {
      setErrorFinal('Debe seleccionar un cliente.');
      return;
    }
    if (guardarComo === 'producto') {
      if (!nombreProducto.trim()) {
        setErrorFinal('Debe ingresar el nombre del producto.');
        return;
      }
      if (!tipoProductoId) {
        setErrorFinal('Debe seleccionar la categoría de producto.');
        return;
      }
    }

    setGuardando(true);
    try {
      const resp = await iqeService.finalizeStructure({
        guardar_como: guardarComo,
        cliente_id: guardarComo === 'cotizacion' ? parseInt(clienteId) : null,
        nombre_producto: guardarComo === 'producto' ? nombreProducto.trim() : null,
        tipo_producto_id: guardarComo === 'producto' ? parseInt(tipoProductoId) : null,
        producto_base_id: productoBaseId,
        secciones,
        nuevo_ancho: parseFloat(parametros.ancho) || 1.60,
        nuevo_largo: parseFloat(parametros.largo) || 1.90,
        ganancia_porcentaje: parseFloat(parametros.ganancia) || 40,
        iva_porcentaje: parseFloat(parametros.iva) || 0,
        pct_mano_obra: parseFloat(parametros.pct_mano_obra) || 15,
        pct_gastos: parseFloat(parametros.pct_gastos) || 10,
        observaciones: observacionesFinal,
        analisis_id: atributos?.analisis_id,
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
            <h1 className="text-xl sm:text-2xl font-headline font-bold tracking-tight">Cotizador Inteligente v2</h1>
            <p className="text-xs text-white/70">Estructura de costos editable guiada por IA y datos reales</p>
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
                      ${activo ? 'bg-yeikar-primary text-white shadow-md scale-110' :
                        completado ? 'bg-emerald-500 text-white shadow' :
                        'bg-gray-200 text-gray-400'}`}
                    >
                      {completado ? '✓' : p.num}
                    </div>
                    <span
                      className={`text-xs font-bold hidden sm:block
                      ${activo ? 'text-yeikar-secondary' :
                        completado ? 'text-emerald-600' : 'text-gray-400'}`}
                    >
                      {p.label}
                    </span>
                  </div>
                  {i < PASOS.length - 1 && (
                    <div className={`flex-1 h-0.5 mx-2 rounded ${p.num < pasoActualNum ? 'bg-emerald-400' : 'bg-gray-200'}`} />
                  )}
                </div>
              );
            })}
          </div>
        </div>
      </div>

      <div className="max-w-5xl mx-auto px-4 py-8">
        {/* ── PASO 1: Carga de Imagen ── */}
        {paso === 'upload' && (
          <div className="space-y-6">
            <div>
              <h2 className="text-xl sm:text-2xl font-headline font-bold text-yeikar-secondary">Analizar Mueble</h2>
              <p className="text-sm text-gray-500 mt-1">Sube la foto del mueble para que la IA proponga los materiales y fases de producción.</p>
            </div>

            <div
              onDrop={handleDrop}
              onDragOver={(e) => e.preventDefault()}
              onClick={() => fileInputRef.current?.click()}
              className={`relative border-2 border-dashed rounded-2xl p-10 text-center cursor-pointer transition-all duration-200
                ${imagenPreview ? 'border-yeikar-primary bg-yeikar-primary/5 shadow-inner' : 'border-gray-300 bg-white hover:border-yeikar-primary hover:bg-yeikar-primary/5'}`}
            >
              <input
                ref={fileInputRef}
                type="file"
                accept="image/jpeg,image/jpg,image/png,image/webp"
                className="hidden"
                onChange={(e) => e.target.files?.[0] && handleImagenSelect(e.target.files[0])}
              />
              {imagenPreview ? (
                <div className="flex flex-col items-center gap-4">
                  <img src={imagenPreview} alt="Preview del mueble" className="max-h-72 max-w-full rounded-xl shadow-md object-contain border border-gray-100" />
                  <p className="text-xs text-gray-400 font-mono">{imagenFile?.name} · {((imagenFile?.size || 0) / 1024).toFixed(0)} KB</p>
                  <button
                    onClick={(e) => {
                      e.stopPropagation();
                      setImagenFile(null);
                      setImagenPreview(null);
                    }}
                    className="text-xs text-red-500 hover:text-red-700 underline font-semibold"
                  >
                    Cambiar Imagen
                  </button>
                </div>
              ) : (
                <div className="flex flex-col items-center gap-3 text-gray-400">
                  <svg className="w-16 h-16 text-gray-300" fill="none" stroke="currentColor" viewBox="0 0 24 24">
                    <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={1.5} d="M4 16l4.586-4.586a2 2 0 012.828 0L16 16m-2-2l1.586-1.586a2 2 0 012.828 0L20 14m-6-6h.01M6 20h12a2 2 0 002-2V6a2 2 0 00-2-2H6a2 2 0 00-2 2v12a2 2 0 002 2z" />
                  </svg>
                  <div>
                    <p className="font-semibold text-gray-600 text-sm">Arrastra la imagen aquí</p>
                    <p className="text-xs mt-1">o haz clic para explorar · JPEG, PNG, WEBP · Max 10 MB</p>
                  </div>
                </div>
              )}
            </div>

            <div className="bg-white rounded-2xl border border-gray-200 p-5 shadow-sm">
              <label className="block text-sm font-semibold text-gray-700 mb-2">Contexto o mensaje adicional</label>
              <textarea
                value={contextoAdicional}
                onChange={(e) => setContextoAdicional(e.target.value)}
                placeholder='Ej: "Cama King Size tapizada en lino con patas ocultas" o "Closet modular de melamina Rovere"'
                rows={3}
                className="w-full border border-gray-200 rounded-xl px-4 py-3 text-sm focus:outline-none focus:ring-2 focus:ring-yeikar-primary/40 resize-none font-body"
              />
              <p className="text-xs text-gray-400 mt-2">💡 Indique dimensiones solicitadas o materiales preferidos para guiar mejor a la IA.</p>
            </div>

            {errorAnalisis && (
              <div className="bg-red-50 border border-red-200 rounded-xl p-4 text-sm text-red-700 font-semibold">
                ⚠️ {errorAnalisis}
              </div>
            )}

            <button
              onClick={handleAnalizar}
              disabled={!imagenFile || analizando}
              className="w-full py-4 bg-yeikar-secondary text-white rounded-xl font-bold hover:bg-yeikar-secondary-light transition-all disabled:opacity-40 disabled:cursor-not-allowed flex items-center justify-center gap-3 shadow-md text-base"
            >
              {analizando ? (
                <>
                  <svg className="animate-spin w-5 h-5" fill="none" viewBox="0 0 24 24">
                    <circle className="opacity-25" cx="12" cy="12" r="10" stroke="currentColor" strokeWidth="4" />
                    <path className="opacity-75" fill="currentColor" d="M4 12a8 8 0 018-8V0C5.373 0 0 5.373 0 12h4z" />
                  </svg>
                  Analizando y sugiriendo estructura de costos...
                </>
              ) : (
                'Analizar con IA →'
              )}
            </button>
          </div>
        )}

        {/* ── PASO 2: Validar Atributos y Configurar Medidas ── */}
        {paso === 'validar' && atributos && (
          <div className="space-y-6">
            <div className="flex items-center justify-between">
              <div>
                <h2 className="text-xl sm:text-2xl font-headline font-bold text-yeikar-secondary">Configuración del Producto</h2>
                <p className="text-sm text-gray-500 mt-1">Revisa los atributos detectados por la IA y define las medidas finales de costeo.</p>
              </div>
              {imagenPreview && (
                <img src={imagenPreview} alt="Miniatura" className="w-16 h-16 rounded-xl object-cover border border-gray-200 shadow" />
              )}
            </div>

            <div className={`rounded-xl px-4 py-3 flex items-center gap-2 text-xs sm:text-sm font-semibold ${CONFIANZA_COLOR(atributos.nivel_confianza)}`}>
              <span>Confianza de la IA: <strong>{Math.round(atributos.nivel_confianza * 100)}%</strong></span>
              {atributos.requiere_revision_humana && <span className="bg-red-200 text-red-800 text-[10px] px-1.5 py-0.5 rounded font-bold">REVISIÓN RECOMENDADA</span>}
            </div>

            {/* Atributos generales */}
            <div className="bg-white rounded-2xl border border-gray-200 p-6 shadow-sm space-y-4">
              <h3 className="text-sm font-bold text-gray-700 uppercase tracking-wider mb-2">Atributos generales</h3>
              <div className="grid grid-cols-1 sm:grid-cols-2 gap-4">
                <div>
                  <label className="block text-xs font-semibold text-gray-500 mb-1">Tipo de Mueble</label>
                  <select
                    value={atributos.tipo_mueble}
                    onChange={(e) => setAtributos({ ...atributos, tipo_mueble: e.target.value })}
                    className="w-full border border-gray-200 rounded-lg px-3 py-2 text-sm focus:outline-none focus:ring-2 focus:ring-yeikar-primary/40 bg-white"
                  >
                    {TIPOS_MUEBLE.map(t => <option key={t} value={t}>{t}</option>)}
                  </select>
                </div>

                <div>
                  <label className="block text-xs font-semibold text-gray-500 mb-1">Familia de Material</label>
                  <select
                    value={atributos.familia_probable || ''}
                    onChange={(e) => setAtributos({ ...atributos, familia_probable: e.target.value || null })}
                    className="w-full border border-gray-200 rounded-lg px-3 py-2 text-sm focus:outline-none focus:ring-2 focus:ring-yeikar-primary/40 bg-white"
                  >
                    <option value="">Sin definir</option>
                    {FAMILIAS.map(f => <option key={f} value={f}>{f}</option>)}
                  </select>
                </div>

                <div>
                  <label className="block text-xs font-semibold text-gray-500 mb-1">Estilo General</label>
                  <select
                    value={atributos.estilo_general || ''}
                    onChange={(e) => setAtributos({ ...atributos, estilo_general: e.target.value || null })}
                    className="w-full border border-gray-200 rounded-lg px-3 py-2 text-sm focus:outline-none focus:ring-2 focus:ring-yeikar-primary/40 bg-white"
                  >
                    <option value="">Sin definir</option>
                    {ESTILOS.map(e => <option key={e} value={e}>{e}</option>)}
                  </select>
                </div>

                <div>
                  <label className="block text-xs font-semibold text-gray-500 mb-1">Tipo de Patas</label>
                  <select
                    value={atributos.tipo_patas || ''}
                    onChange={(e) => setAtributos({ ...atributos, tipo_patas: e.target.value || null })}
                    className="w-full border border-gray-200 rounded-lg px-3 py-2 text-sm focus:outline-none focus:ring-2 focus:ring-yeikar-primary/40 bg-white"
                  >
                    <option value="">Sin definir</option>
                    {PATAS.map(p => <option key={p} value={p}>{p}</option>)}
                  </select>
                </div>
              </div>

              <div className="flex gap-6 pt-2">
                <label className="flex items-center gap-2 cursor-pointer font-semibold text-sm text-gray-700">
                  <input
                    type="checkbox"
                    checked={atributos.tiene_tapiceria}
                    onChange={(e) => setAtributos({ ...atributos, tiene_tapiceria: e.target.checked })}
                    className="w-4 h-4 rounded border-gray-300 text-yeikar-primary focus:ring-yeikar-primary/40 accent-yeikar-primary"
                  />
                  Tiene Tapicería
                </label>
                <label className="flex items-center gap-2 cursor-pointer font-semibold text-sm text-gray-700">
                  <input
                    type="checkbox"
                    checked={atributos.tiene_luces}
                    onChange={(e) => setAtributos({ ...atributos, tiene_luces: e.target.checked })}
                    className="w-4 h-4 rounded border-gray-300 text-yeikar-primary focus:ring-yeikar-primary/40 accent-yeikar-primary"
                  />
                  Tiene Iluminación LED
                </label>
              </div>
            </div>

            {/* Medidas y Parámetros Iniciales */}
            <div className="bg-white rounded-2xl border border-gray-200 p-6 shadow-sm space-y-4">
              <h3 className="text-sm font-bold text-gray-700 uppercase tracking-wider mb-2">Medidas y Parámetros del Proyecto</h3>
              <div className="grid grid-cols-2 sm:grid-cols-3 gap-4">
                <div>
                  <label className="block text-xs font-semibold text-gray-500 mb-1">Ancho (metros) *</label>
                  <input
                    type="number"
                    step="0.01"
                    value={parametros.ancho}
                    onChange={(e) => setParametros({ ...parametros, ancho: e.target.value })}
                    className="w-full border border-gray-200 rounded-lg px-3 py-2 text-sm font-mono focus:outline-none focus:ring-2 focus:ring-yeikar-primary/40"
                  />
                </div>
                <div>
                  <label className="block text-xs font-semibold text-gray-500 mb-1">Largo (metros) *</label>
                  <input
                    type="number"
                    step="0.01"
                    value={parametros.largo}
                    onChange={(e) => setParametros({ ...parametros, largo: e.target.value })}
                    className="w-full border border-gray-200 rounded-lg px-3 py-2 text-sm font-mono focus:outline-none focus:ring-2 focus:ring-yeikar-primary/40"
                  />
                </div>
                <div className="col-span-2 sm:col-span-1">
                  <label className="block text-xs font-semibold text-gray-500 mb-1">Ganancia / Margen (%)</label>
                  <input
                    type="number"
                    value={parametros.ganancia}
                    onChange={(e) => setParametros({ ...parametros, ganancia: e.target.value })}
                    className="w-full border border-gray-200 rounded-lg px-3 py-2 text-sm font-mono focus:outline-none focus:ring-2 focus:ring-yeikar-primary/40"
                  />
                </div>
              </div>
            </div>

            <div className="flex gap-3">
              <button
                type="button"
                onClick={() => setPaso('upload')}
                className="flex-1 py-3 border border-gray-300 text-gray-600 rounded-xl font-semibold hover:bg-gray-50 transition-all"
              >
                ← Volver a Foto
              </button>
              <button
                type="button"
                onClick={handleGenerarEstructura}
                disabled={generandoEstructura}
                className="flex-2 flex-grow-[2] py-3 bg-yeikar-secondary text-white rounded-xl font-bold hover:bg-yeikar-secondary-light transition-all shadow-md flex items-center justify-center gap-2"
              >
                {generandoEstructura ? (
                  <><svg className="animate-spin w-4 h-4" fill="none" viewBox="0 0 24 24"><circle className="opacity-25" cx="12" cy="12" r="10" stroke="currentColor" strokeWidth="4" /><path className="opacity-75" fill="currentColor" d="M4 12a8 8 0 018-8V0C5.373 0 0 5.373 0 12h4z" /></svg> Generando Estructura...</>
                ) : (
                  'Generar estructura de costos →'
                )}
              </button>
            </div>
          </div>
        )}

        {/* ── PASO 3: Estructura de Costos Editable (Borrador) ── */}
        {paso === 'borrador' && (
          <div className="space-y-6">
            <div className="flex flex-col sm:flex-row sm:items-center sm:justify-between gap-4">
              <div>
                <h2 className="text-xl sm:text-2xl font-headline font-bold text-yeikar-secondary">
                  Estructura de Costos del Borrador
                </h2>
                {productoBaseNombre && (
                  <p className="text-xs text-gray-400 mt-1">
                    Fusión inteligente guiada por plantilla: <strong>{productoBaseNombre}</strong> ({scoreSimilitud}% similitud)
                  </p>
                )}
              </div>
              <div className="flex items-center gap-3">
                <span className="text-xs font-semibold text-gray-500">Medidas:</span>
                <span className="bg-yeikar-primary/10 border border-yeikar-primary/30 text-yeikar-secondary text-xs font-bold font-mono px-3 py-1 rounded-lg">
                  {parametros.ancho}m × {parametros.largo}m
                </span>
              </div>
            </div>

            {/* Panel de dimensiones y desgloses de costos */}
            <div className="grid grid-cols-1 lg:grid-cols-3 gap-6 items-start">
              {/* Editor de la Tabla */}
              <div className="lg:col-span-2 space-y-6">
                {materialesSinPrecio > 0 && (
                  <div className="bg-red-50 border border-red-200 text-red-800 rounded-xl px-5 py-3 text-xs sm:text-sm font-semibold flex items-center gap-2">
                    <span>⚠️ Tienes {materialesSinPrecio} material(es) sin precio asignado. Ingrese un costo unitario temporal o registre el material formalmente.</span>
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
                <div className="bg-white rounded-2xl border border-gray-200 p-5 shadow-sm space-y-3">
                  <h4 className="text-xs font-bold text-gray-500 uppercase tracking-wider mb-2">Parámetros Financieros</h4>
                  <div className="grid grid-cols-2 gap-2 text-xs">
                    <div>
                      <label className="block text-gray-400 font-medium mb-1">Mano de Obra %</label>
                      <input
                        type="number"
                        value={parametros.pct_mano_obra}
                        onChange={(e) => setParametros({ ...parametros, pct_mano_obra: e.target.value })}
                        className="w-full border border-gray-200 rounded-lg px-2.5 py-1.5 font-mono focus:outline-none focus:ring-1 focus:ring-yeikar-primary"
                      />
                    </div>
                    <div>
                      <label className="block text-gray-400 font-medium mb-1">Gastos %</label>
                      <input
                        type="number"
                        value={parametros.pct_gastos}
                        onChange={(e) => setParametros({ ...parametros, pct_gastos: e.target.value })}
                        className="w-full border border-gray-200 rounded-lg px-2.5 py-1.5 font-mono focus:outline-none focus:ring-1 focus:ring-yeikar-primary"
                      />
                    </div>
                    <div>
                      <label className="block text-gray-400 font-medium mb-1">Ganancia %</label>
                      <input
                        type="number"
                        value={parametros.ganancia}
                        onChange={(e) => setParametros({ ...parametros, ganancia: e.target.value })}
                        className="w-full border border-gray-200 rounded-lg px-2.5 py-1.5 font-mono focus:outline-none focus:ring-1 focus:ring-yeikar-primary"
                      />
                    </div>
                    <div>
                      <label className="block text-gray-400 font-medium mb-1">IVA %</label>
                      <input
                        type="number"
                        value={parametros.iva}
                        onChange={(e) => setParametros({ ...parametros, iva: e.target.value })}
                        className="w-full border border-gray-200 rounded-lg px-2.5 py-1.5 font-mono focus:outline-none focus:ring-1 focus:ring-yeikar-primary"
                      />
                    </div>
                  </div>
                </div>

                {/* Resumen de totales */}
                {resumen && (
                  <div className="bg-yeikar-secondary text-white rounded-2xl p-6 shadow-md space-y-4">
                    <h3 className="font-headline font-bold text-base border-b border-white/10 pb-2">
                      Resumen del ERP
                    </h3>
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
                      <div className="flex justify-between text-white/80">
                        <span>Ganancia ({parametros.ganancia}%)</span>
                        <span className="font-mono">${(resumen.precio_sin_iva - resumen.costo_produccion).toLocaleString('es-CO', { minimumFractionDigits: 2 })}</span>
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
                ⚠️ {errorAnalisis}
              </div>
            )}

            <div className="flex gap-3">
              <button
                type="button"
                onClick={() => setPaso('validar')}
                className="flex-1 py-3 border border-gray-300 text-gray-600 rounded-xl font-semibold hover:bg-gray-50 transition-all"
              >
                ← Configurar Atributos
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

        {/* ── PASO 4: Guardar y Persistir ── */}
        {paso === 'finalizar' && !cotizacionCreada && resumen && (
          <div className="space-y-6">
            <div>
              <h2 className="text-xl sm:text-2xl font-headline font-bold text-yeikar-secondary">Confirmar Guardado</h2>
              <p className="text-sm text-gray-500 mt-1">
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
                <span className="text-gray-400">Ancho/Largo:</span>
                <span className="font-semibold text-gray-800">{parametros.ancho}m × {parametros.largo}m</span>
                <span className="text-gray-400">Costo Prod:</span>
                <span className="font-semibold font-mono text-gray-800">${resumen.costo_produccion.toLocaleString('es-CO', { minimumFractionDigits: 2 })}</span>
              </div>
            </div>

            {/* Toggle tipo guardado */}
            <div className="bg-white rounded-2xl border border-gray-200 shadow-sm overflow-hidden">
              <div className="grid grid-cols-2 divide-x divide-gray-100 border-b border-gray-100">
                <button
                  type="button"
                  onClick={() => setGuardarComo('cotizacion')}
                  className={`py-4 text-center font-semibold text-sm transition-all flex items-center justify-center gap-2
                    ${guardarComo === 'cotizacion' ? 'bg-yeikar-primary/10 text-yeikar-secondary font-bold' : 'text-gray-400 hover:bg-gray-50'}`}
                >
                  📄 Guardar como Cotización
                </button>
                <button
                  type="button"
                  onClick={() => setGuardarComo('producto')}
                  className={`py-4 text-center font-semibold text-sm transition-all flex items-center justify-center gap-2
                    ${guardarComo === 'producto' ? 'bg-yeikar-primary/10 text-yeikar-secondary font-bold' : 'text-gray-400 hover:bg-gray-50'}`}
                >
                  📦 Guardar como Nuevo Producto
                </button>
              </div>

              <div className="p-6 space-y-4">
                {guardarComo === 'cotizacion' ? (
                  <div className="space-y-4">
                    <div>
                      <label className="block text-sm font-semibold text-gray-700 mb-2">Cliente *</label>
                      <select
                        required
                        value={clienteId}
                        onChange={(e) => setClienteId(e.target.value)}
                        className="w-full border border-gray-200 rounded-xl px-4 py-3 text-sm focus:outline-none focus:ring-2 focus:ring-yeikar-primary/40 bg-white"
                      >
                        <option value="">Seleccione un cliente...</option>
                        {clientes.map(c => <option key={c.id} value={c.id}>{c.nombre}</option>)}
                      </select>
                    </div>
                    <div>
                      <label className="block text-sm font-semibold text-gray-700 mb-2">Observaciones</label>
                      <textarea
                        value={observacionesFinal}
                        onChange={(e) => setObservacionesFinal(e.target.value)}
                        placeholder="Observaciones de venta o requerimientos específicos del cliente..."
                        rows={3}
                        className="w-full border border-gray-200 rounded-xl px-4 py-3 text-sm focus:outline-none focus:ring-2 focus:ring-yeikar-primary/40 resize-none"
                      />
                    </div>
                  </div>
                ) : (
                  <div className="space-y-4">
                    <div>
                      <label className="block text-sm font-semibold text-gray-700 mb-2">Nombre de la Plantilla / Producto *</label>
                      <input
                        type="text"
                        required
                        placeholder="Ej. CAMA FLOTANTE NÓRDICA V2"
                        value={nombreProducto}
                        onChange={(e) => setNombreProducto(e.target.value)}
                        className="w-full border border-gray-200 rounded-xl px-4 py-3 text-sm focus:outline-none focus:ring-2 focus:ring-yeikar-primary/40 uppercase"
                      />
                    </div>
                    <div className="grid grid-cols-1 sm:grid-cols-2 gap-4">
                      <div>
                        <label className="block text-sm font-semibold text-gray-700 mb-2">Categoría de Producto *</label>
                        <select
                          required
                          value={tipoProductoId}
                          onChange={(e) => setTipoProductoId(e.target.value)}
                          className="w-full border border-gray-200 rounded-xl px-4 py-3 text-sm focus:outline-none focus:ring-2 focus:ring-yeikar-primary/40 bg-white"
                        >
                          <option value="">Seleccione categoría...</option>
                          {tiposProducto.map(tp => <option key={tp.id} value={tp.id}>{tp.nombre}</option>)}
                        </select>
                      </div>
                      <div>
                        <label className="block text-sm font-semibold text-gray-700 mb-2">Descripción del Producto</label>
                        <input
                          type="text"
                          placeholder="Notas o especificaciones para catálogo..."
                          value={observacionesFinal}
                          onChange={(e) => setObservacionesFinal(e.target.value)}
                          className="w-full border border-gray-200 rounded-xl px-4 py-3 text-sm focus:outline-none focus:ring-2 focus:ring-yeikar-primary/40"
                        />
                      </div>
                    </div>
                    <p className="text-xs text-amber-600 bg-amber-50 border border-amber-200 rounded-lg p-3 font-semibold">
                      💡 Al guardar como Producto, la receta detallada se almacenará como receta paramétrica base. Esto te permitirá usar este producto como plantilla idéntica para cotizaciones futuras.
                    </p>
                  </div>
                )}
              </div>
            </div>

            {errorFinal && (
              <div className="bg-red-50 border border-red-200 rounded-xl p-4 text-sm text-red-700 font-semibold">
                ⚠️ {errorFinal}
              </div>
            )}

            <div className="flex gap-3">
              <button
                type="button"
                onClick={() => setPaso('borrador')}
                className="flex-1 py-3 border border-gray-300 text-gray-600 rounded-xl font-semibold hover:bg-gray-50 transition-all"
              >
                ← Volver a Estructura
              </button>
              <button
                type="button"
                onClick={handleGuardarFinal}
                disabled={guardando}
                className="flex-2 flex-grow-[2] py-4 bg-emerald-600 text-white rounded-xl font-bold hover:bg-emerald-700 transition-all shadow-md flex items-center justify-center gap-2"
              >
                {guardando ? (
                  <><svg className="animate-spin w-5 h-5" fill="none" viewBox="0 0 24 24"><circle className="opacity-25" cx="12" cy="12" r="10" stroke="currentColor" strokeWidth="4" /><path className="opacity-75" fill="currentColor" d="M4 12a8 8 0 018-8V0C5.373 0 0 5.373 0 12h4z" /></svg> Guardando...</>
                ) : (
                  '✓ Confirmar y Registrar'
                )}
              </button>
            </div>
          </div>
        )}

        {/* ── Cotización / Producto creado exitosamente ── */}
        {paso === 'finalizar' && cotizacionCreada && (
          <div className="text-center space-y-6 py-10 bg-white border border-gray-200 rounded-2xl shadow-sm max-w-2xl mx-auto p-8">
            <div className="w-20 h-20 bg-emerald-100 rounded-full flex items-center justify-center mx-auto shadow-inner">
              <svg className="w-10 h-10 text-emerald-600" fill="none" stroke="currentColor" viewBox="0 0 24 24">
                <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M9 12l2 2 4-4m6 2a9 9 0 11-18 0 9 9 0 0118 0z" />
              </svg>
            </div>
            <div className="space-y-2">
              <h2 className="text-2xl font-headline font-bold text-emerald-700">¡Registro exitoso!</h2>
              <p className="text-sm text-gray-500">{cotizacionCreada.mensaje}</p>
              {cotizacionCreada.id > 0 ? (
                <p className="text-xs text-gray-400 font-mono">
                  Cotización #{cotizacionCreada.id} registrada con un monto final de{' '}
                  <strong className="text-yeikar-secondary">${cotizacionCreada.total.toLocaleString('es-CO', { minimumFractionDigits: 2 })}</strong>
                </p>
              ) : (
                <p className="text-xs text-gray-400 font-mono">
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
                onClick={() => {
                  setPaso('upload');
                  setImagenFile(null);
                  setImagenPreview(null);
                  setContextoAdicional('');
                  setAtributos(null);
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
                }}
                className="px-6 py-3 border border-gray-300 text-gray-600 rounded-xl font-semibold hover:bg-gray-50 transition-all"
              >
                Nueva Cotización
              </button>
            </div>
          </div>
        )}
      </div>
    </div>
  );
}
