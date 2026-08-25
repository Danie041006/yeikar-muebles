import React, { useState, useEffect } from 'react';
import { LineaCostoOut, SeccionCostoOut, UnidadMedida } from '../services/iqeService';
import { productosService, Material } from '../services/productosService';
import { useToast } from '../context/ToastContext';
import { SearchSelect } from './ui';

interface EstructuraCostosEditorProps {
  secciones: SeccionCostoOut[];
  onChange: (nuevasSecciones: SeccionCostoOut[]) => void;
  onRecalculate: () => void;
  unidades: UnidadMedida[];
  isLoading: boolean;
}

export default function EstructuraCostosEditor({
  secciones,
  onChange,
  onRecalculate,
  unidades,
  isLoading,
}: EstructuraCostosEditorProps) {
  const toast = useToast();
  // Estados para agregar material
  const [activeSearchSection, setActiveSearchSection] = useState<string | null>(null);
  const [searchTerm, setSearchTerm] = useState('');
  const [searchResults, setSearchResults] = useState<Material[]>([]);
  const [customMaterialName, setCustomMaterialName] = useState('');

  // Estado para modal de creación de material
  const [isModalOpen, setIsModalOpen] = useState(false);
  // Estado para modal de nueva sección
  const [isNewSectionOpen, setIsNewSectionOpen] = useState(false);
  const [newSectionName, setNewSectionName] = useState('');
  const [newMatName, setNewMatName] = useState('');
  const [newMatCost, setNewMatCost] = useState('0');
  const [newMatUnit, setNewMatUnit] = useState('');
  const [modalSection, setModalSection] = useState<string | null>(null);

  // Buscar en inventario al escribir
  useEffect(() => {
    if (!searchTerm.trim()) {
      setSearchResults([]);
      return;
    }
    const delayDebounce = setTimeout(async () => {
      try {
        const results = await productosService.getMateriales(searchTerm);
        setSearchResults(results.slice(0, 5));
      } catch (err) {
        console.error('Error al buscar materiales:', err);
      }
    }, 300);

    return () => clearTimeout(delayDebounce);
  }, [searchTerm]);

  // Modificar cantidad o precio inline
  const handleItemFieldChange = (
    seccionNombre: string,
    tempId: string,
    field: keyof LineaCostoOut,
    value: any
  ) => {
    const updated = secciones.map((sec) => {
      if (sec.seccion === seccionNombre) {
        return {
          ...sec,
          items: sec.items.map((item) => {
            if (item.temp_id === tempId) {
              const updatedItem = { ...item, [field]: value };
              // Recalcular costo total del item
              if (field === 'cantidad' || field === 'costo_unitario') {
                const qty = field === 'cantidad' ? parseFloat(value) || 0 : item.cantidad;
                const price = field === 'costo_unitario' ? parseFloat(value) || 0 : item.costo_unitario;
                updatedItem.costo_total = parseFloat((qty * price).toFixed(2));
              }
              return updatedItem;
            }
            return item;
          }),
        };
      }
      return sec;
    });
    // Recalcular subtotal de la sección
    const finalUpdated = updated.map((sec) => {
      const subtotal = sec.items
        .filter((i) => i.activo)
        .reduce((sum, item) => sum + (item.costo_total || 0), 0);
      return { ...sec, subtotal: parseFloat(subtotal.toFixed(2)) };
    });
    onChange(finalUpdated);
  };

  // Mapear un material sugerido (un clic) para una línea sin precio
  const handleMapSugerencia = (seccionNombre: string, tempId: string, mat: { id: number; nombre: string; costo_base: number; abreviatura?: string | null }) => {
    const updated = secciones.map((sec) => {
      if (sec.seccion === seccionNombre) {
        return {
          ...sec,
          items: sec.items.map((item) => {
            if (item.temp_id === tempId) {
              const costo_unitario = Number(mat.costo_base) || 0;
              const updatedItem: LineaCostoOut = {
                ...item,
                material_id: mat.id,
                costo_unitario,
                costo_total: parseFloat((item.cantidad * costo_unitario).toFixed(2)),
                precio_pendiente: false,
                unidad: mat.abreviatura || item.unidad,
                fuente: 'manual',
                razon: item.razon || `Mapeado a ${mat.nombre}`,
                sugerencias: [],
              };
              return updatedItem;
            }
            return item;
          }),
        };
      }
      return sec;
    });
    const finalUpdated = updated.map((sec) => {
      const subtotal = sec.items
        .filter((i) => i.activo)
        .reduce((sum, item) => sum + (item.costo_total || 0), 0);
      return { ...sec, subtotal: parseFloat(subtotal.toFixed(2)) };
    });
    onChange(finalUpdated);
  };

  // Eliminar línea
  const handleDeleteItem = (seccionNombre: string, tempId: string) => {    const updated = secciones.map((sec) => {
      if (sec.seccion === seccionNombre) {
        const filtered = sec.items.filter((item) => item.temp_id !== tempId);
        const subtotal = filtered
          .filter((i) => i.activo)
          .reduce((sum, item) => sum + (item.costo_total || 0), 0);
        return { ...sec, items: filtered, subtotal: parseFloat(subtotal.toFixed(2)) };
      }
      return sec;
    });
    onChange(updated);
  };

  // Activar buscador para una sección
  const startAddLine = (seccionNombre: string) => {
    setActiveSearchSection(seccionNombre);
    setSearchTerm('');
    setCustomMaterialName('');
    setSearchResults([]);
  };

  // Agregar material existente del inventario
  const handleAddExistingMaterial = (seccionNombre: string, mat: Material) => {
    const nuevoItem: LineaCostoOut = {
      temp_id: Math.random().toString(36).substring(2, 10),
      material_id: mat.id,
      nombre: mat.nombre.toUpperCase(),
      cantidad: 1.0,
      unidad: mat.unidad_medida?.abreviatura || 'UN',
      costo_unitario: Number(mat.costo_base),
      costo_total: Number(mat.costo_base),
      precio_pendiente: false,
      razon: 'Agregado manualmente por el vendedor',
      fuente: 'manual',
      es_opcional: false,
      activo: true,
    };

    insertItemIntoSection(seccionNombre, nuevoItem);
    setActiveSearchSection(null);
  };

  // Agregar línea temporal sin material en inventario
  const handleAddTempLine = (seccionNombre: string) => {
    const name = customMaterialName.trim() || 'NUEVO INSUMO';
    const nuevoItem: LineaCostoOut = {
      temp_id: Math.random().toString(36).substring(2, 10),
      material_id: null,
      nombre: name.toUpperCase(),
      cantidad: 1.0,
      unidad: 'UN',
      costo_unitario: 0.0,
      costo_total: 0.0,
      precio_pendiente: true,
      razon: 'Insumo temporal (precio pendiente)',
      fuente: 'manual',
      es_opcional: false,
      activo: true,
    };

    insertItemIntoSection(seccionNombre, nuevoItem);
    setActiveSearchSection(null);
  };

  // Abrir modal para crear en inventario
  const openCreateMaterialModal = (seccionNombre: string, name?: string) => {
    setNewMatName(name || '');
    setNewMatCost(''); // vacío para que sea opcional
    setNewMatUnit(unidades[0]?.id.toString() || '');
    setModalSection(seccionNombre);
    setIsModalOpen(true);
  };

  // Guardar nuevo material en inventario e insertarlo
  const handleCreateMaterial = async (e: React.FormEvent) => {
    e.preventDefault();
    if (!newMatName.trim() || !modalSection) return;

    try {
      const mat = await productosService.crearMaterial({
        nombre: newMatName.toUpperCase().trim(),
        costo_base: parseFloat(newMatCost) || 0,
        unidad_medida_id: parseInt(newMatUnit),
        activo: true,
      });

      // Obtener la abreviatura de la unidad
      const unitObj = unidades.find((u) => u.id === parseInt(newMatUnit));
      const abr = unitObj ? unitObj.abreviatura : 'UN';

      const nuevoItem: LineaCostoOut = {
        temp_id: Math.random().toString(36).substring(2, 10),
        material_id: mat.id,
        nombre: mat.nombre,
        cantidad: 1.0,
        unidad: abr,
        costo_unitario: Number(mat.costo_base),
        costo_total: Number(mat.costo_base),
        precio_pendiente: false,
        razon: 'Creado en inventario e insertado',
        fuente: 'manual',
        es_opcional: false,
        activo: true,
      };

      insertItemIntoSection(modalSection, nuevoItem);
      setIsModalOpen(false);
      setActiveSearchSection(null);
    } catch (err) {
      toast.error('Error al crear el material en el inventario. Asegúrese de que el nombre sea único.');
    }
  };

  // Insertar item en sección y actualizar subtotales
  const insertItemIntoSection = (seccionNombre: string, item: LineaCostoOut) => {
    const updated = secciones.map((sec) => {
      if (sec.seccion === seccionNombre) {
        const items = [...sec.items, item];
        const subtotal = items
          .filter((i) => i.activo)
          .reduce((sum, it) => sum + (it.costo_total || 0), 0);
        return { ...sec, items, subtotal: parseFloat(subtotal.toFixed(2)) };
      }
      return sec;
    });
    onChange(updated);
  };

  // Agregar una nueva sección vacía
  const handleAddSection = () => {
    setNewSectionName('');
    setIsNewSectionOpen(true);
  };

  const handleConfirmAddSection = () => {
    const nombre = newSectionName;
    if (!nombre || !nombre.trim()) {
      toast.warning('Ingrese el nombre de la sección.');
      return;
    }

    const nombreUpper = nombre.toUpperCase().trim();
    if (secciones.some((s) => s.seccion === nombreUpper)) {
      toast.warning('La sección ya existe.');
      return;
    }

    const nuevaSeccion: SeccionCostoOut = {
      seccion: nombreUpper,
      items: [],
      subtotal: 0.0,
    };

    onChange([...secciones, nuevaSeccion]);
    setIsNewSectionOpen(false);
    setNewSectionName('');
  };

  // Icono por sección de producción
  const getSeccionIcon = (nombre: string) => {
    const n = nombre.toUpperCase();
    if (n.includes('EBAN')) return '';
    if (n.includes('MANO DE OBRA') || n.includes('M.O')) return '';
    if (n.includes('PINTURA')) return '';
    if (n.includes('TAPIC')) return '';
    if (n.includes('HERRAJ')) return '';
    if (n.includes('TERMINACI')) return '';
    if (n.includes('NOCHER')) return '';
    if (n.includes('ILUMINA') || n.includes('LED')) return '';
    return '';
  };

  // Color del header por sección
  const getSeccionColor = (nombre: string) => {
    const n = nombre.toUpperCase();
    if (n.includes('EBAN')) return 'from-amber-800 to-amber-900';
    if (n.includes('MANO DE OBRA')) return 'from-blue-700 to-blue-900';
    if (n.includes('PINTURA')) return 'from-violet-700 to-violet-900';
    if (n.includes('TAPIC')) return 'from-pink-600 to-pink-800';
    if (n.includes('HERRAJ')) return 'from-slate-600 to-slate-800';
    if (n.includes('TERMINACI')) return 'from-teal-600 to-teal-800';
    if (n.includes('NOCHER')) return 'from-indigo-600 to-indigo-800';
    if (n.includes('ILUMINA')) return 'from-yellow-500 to-yellow-700';
    return 'from-gray-600 to-gray-800';
  };

  return (
    <div className="space-y-6">
      {secciones.map((sec) => (
        <div key={sec.seccion} className="bg-white rounded-2xl border border-gray-200 shadow-sm overflow-hidden transition-all hover:border-gray-300">
          {/* Header de la sección */}
          <div className={`bg-gradient-to-r ${getSeccionColor(sec.seccion)} text-white px-6 py-3.5 flex items-center justify-between`}>
            <h3 className="font-headline font-bold tracking-wide text-sm flex items-center gap-2">
              <span className="text-lg">{getSeccionIcon(sec.seccion)}</span>
              {sec.seccion}
            </h3>
            <div className="text-right">
              <span className="text-xs text-white/60 font-medium mr-2">Subtotal:</span>
              <span className="font-mono font-bold text-white text-base">
                ${sec.subtotal.toLocaleString('es-CO', { minimumFractionDigits: 2 })}
              </span>
            </div>
          </div>

          {/* Tabla de ítems */}
          <div className="overflow-x-auto">
            <table className="w-full text-sm">
              <thead>
                <tr className="bg-gray-100/50 text-[10px] text-gray-500 uppercase tracking-wider border-b border-gray-100">
                  <th className="w-10 px-4 py-2.5 text-center">Activo</th>
                  <th className="text-left px-4 py-2.5">Material / Insumo</th>
                  <th className="text-right px-4 py-2.5">Cant.</th>
                  <th className="text-left px-2 py-2.5">Unidad</th>
                  <th className="text-right px-4 py-2.5">Costo Unit.</th>
                  <th className="text-right px-4 py-2.5">Costo Total</th>
                  <th className="w-20 px-4 py-2.5 text-center">Acción</th>
                </tr>
              </thead>
              <tbody className="divide-y divide-gray-100 font-body">
                {sec.items.length === 0 ? (
                  <tr>
                    <td colSpan={7} className="text-center py-6 text-gray-400 text-xs italic">
                      No hay materiales en esta sección. Haz clic en "+ Agregar línea" para añadir uno.
                    </td>
                  </tr>
                ) : (
                  sec.items.map((item) => (
                    <tr
                      key={item.temp_id}
                      className={`hover:bg-gray-50/50 transition-colors ${!item.activo ? 'opacity-30 bg-gray-50/20' : ''}`}
                    >
                      {/* Checkbox de activo */}
                      <td className="px-4 py-3 text-center">
                        <input
                          type="checkbox"
                          checked={item.activo}
                          onChange={(e) =>
                            handleItemFieldChange(sec.seccion, item.temp_id, 'activo', e.target.checked)
                          }
                          className="w-4 h-4 rounded text-yeikar-primary border-gray-300 focus:ring-yeikar-primary/40 accent-yeikar-primary"
                        />
                      </td>

                      {/* Nombre y advertencia */}
                      <td className="px-4 py-3">
                        <div className="flex flex-col">
                          <div className="flex items-center gap-1.5">
                            <span className="font-semibold text-gray-800 text-xs sm:text-sm">{item.nombre}</span>
                            {item.precio_pendiente && item.activo && (
                              <span className="bg-red-50 text-red-600 border border-red-200 text-[9px] px-1 rounded font-bold animate-pulse">
                                 PRECIO PENDIENTE
                              </span>
                            )}
                            {item.fuente === 'politica' && (
                              <span className="bg-blue-50 text-blue-600 border border-blue-200 text-[9px] px-1 rounded font-bold">
                                 MANO DE OBRA
                              </span>
                            )}
                            {item.confianza_cantidad === 'alta' && (
                              <span className="bg-green-50 text-green-600 border border-green-200 text-[9px] px-1 rounded font-bold" title="Cantidad tomada de una receta real o respaldada por varias recetas similares">
                                 confianza alta
                              </span>
                            )}
                            {item.confianza_cantidad === 'media' && (
                              <span className="bg-amber-50 text-amber-600 border border-amber-200 text-[9px] px-1 rounded font-bold" title="Cantidad estimada por mediana de recetas similares (3-4 recetas)">
                                 confianza media
                              </span>
                            )}
                            {item.confianza_cantidad === 'baja' && (
                              <span className="bg-gray-50 text-gray-500 border border-gray-200 text-[9px] px-1 rounded font-bold" title="Cantidad propuesta por la IA sin respaldo histórico">
                                 estimación IA
                              </span>
                            )}
                          </div>
                          {item.razon && (
                            <span className="text-[10px] text-gray-400 italic mt-0.5 line-clamp-1 hover:line-clamp-none" title={item.razon}>
                               {item.razon}
                            </span>
                          )}
                          {item.cantidad_ia_sugerida != null && item.cantidad_referencia != null && Math.abs(item.cantidad_ia_sugerida - item.cantidad_referencia) > 0.001 && (
                            <span className="text-[10px] text-gray-500 mt-0.5 font-mono" title="Cantidad propuesta por la IA vs cantidad real de la receta histórica">
                               IA: {item.cantidad_ia_sugerida} · receta: {item.cantidad_referencia}
                            </span>
                          )}
                          {/* Sugerencias de material del inventario (1 clic para mapear) */}
                          {item.precio_pendiente && item.sugerencias && item.sugerencias.length > 0 && (
                            <div className="flex flex-wrap gap-1 mt-1.5">
                              {item.sugerencias.map((sug) => (
                                <button
                                  key={sug.id}
                                  type="button"
                                  title={`Mapear a "${sug.nombre}" (${sug.costo_base} por ${sug.abreviatura || ''})`}
                                  onClick={() => handleMapSugerencia(sec.seccion, item.temp_id, sug)}
                                  className="text-[10px] font-semibold bg-yeikar-primary/10 text-yeikar-secondary border border-yeikar-primary/30 rounded-full px-2 py-0.5 hover:bg-yeikar-primary/20 hover:border-yeikar-primary transition-all"
                                >
                                  + {sug.nombre}
                                </button>
                              ))}
                            </div>
                          )}
                        </div>
                      </td>

                      {/* Cantidad */}
                      <td className="px-4 py-3 text-right">
                        <input
                          type="number"
                          step="0.001"
                          min="0"
                          disabled={!item.activo}
                          value={item.cantidad}
                          onChange={(e) =>
                            handleItemFieldChange(sec.seccion, item.temp_id, 'cantidad', parseFloat(e.target.value) || 0)
                          }
                          className="w-16 sm:w-20 text-right border border-gray-200 rounded-lg px-2 py-1 text-xs font-mono focus:outline-none focus:ring-2 focus:ring-yeikar-primary/40 disabled:bg-gray-100"
                        />
                      </td>

                      {/* Unidad */}
                      <td className="px-2 py-3 text-left font-semibold text-xs text-gray-500 font-mono">
                        {item.unidad}
                      </td>

                      {/* Costo Unitario */}
                      <td className="px-4 py-3 text-right">
                        {item.precio_pendiente ? (
                          <div className="flex items-center gap-1 justify-end">
                            <span className="text-gray-400 text-xs">$</span>
                            <input
                              type="number"
                              min="0"
                              step="0.01"
                              placeholder="0"
                              value={item.costo_unitario || ''}
                              onChange={(e) =>
                                handleItemFieldChange(sec.seccion, item.temp_id, 'costo_unitario', parseFloat(e.target.value) || 0)
                              }
                              className="w-20 sm:w-24 text-right border border-red-300 bg-red-50/30 rounded-lg px-2 py-1 text-xs font-mono font-bold focus:outline-none focus:ring-2 focus:ring-red-400/40"
                            />
                          </div>
                        ) : (
                          <input
                            type="number"
                            min="0"
                            step="0.01"
                            disabled={!item.activo}
                            value={item.costo_unitario}
                            onChange={(e) =>
                              handleItemFieldChange(sec.seccion, item.temp_id, 'costo_unitario', parseFloat(e.target.value) || 0)
                            }
                            className="w-20 sm:w-24 text-right border border-gray-200 rounded-lg px-2 py-1 text-xs font-mono focus:outline-none focus:ring-2 focus:ring-yeikar-primary/40 disabled:bg-gray-100"
                          />
                        )}
                      </td>

                      {/* Costo Total */}
                      <td className="px-4 py-3 text-right font-mono font-bold text-gray-700 text-xs sm:text-sm">
                        ${(item.activo ? item.costo_total : 0).toLocaleString('es-CO', { minimumFractionDigits: 2 })}
                      </td>

                      {/* Botón eliminar / crear en inventario */}
                      <td className="px-4 py-3 text-center">
                        <div className="flex items-center justify-center gap-2">
                          {item.precio_pendiente && item.activo && (
                            <button
                              type="button"
                              onClick={() => openCreateMaterialModal(sec.seccion, item.nombre)}
                              title="Crear material formalmente en inventario"
                              className="p-1.5 text-emerald-600 bg-emerald-50 border border-emerald-200 rounded-lg hover:bg-emerald-100 hover:text-emerald-700 transition-all"
                            >
                              +
                            </button>
                          )}
                          <button
                            type="button"
                            onClick={() => handleDeleteItem(sec.seccion, item.temp_id)}
                            className="p-1.5 text-red-500 bg-red-50 border border-red-200 rounded-lg hover:bg-red-100 hover:text-red-700 transition-all"
                          >
                            ×
                          </button>
                        </div>
                      </td>
                    </tr>
                  ))
                )}
              </tbody>
            </table>
          </div>

          {/* Acciones de sección */}
          <div className="bg-gray-50/30 px-6 py-3 border-t border-gray-100 flex items-center justify-between">
            {activeSearchSection === sec.seccion ? (
              <div className="w-full space-y-2 py-1">
                <div className="flex gap-2">
                  <div className="relative flex-1">
                    <input
                      type="text"
                      placeholder="Buscar material en el inventario..."
                      value={searchTerm}
                      onChange={(e) => setSearchTerm(e.target.value)}
                      className="w-full border border-gray-200 rounded-xl px-4 py-2 text-xs focus:outline-none focus:ring-2 focus:ring-yeikar-primary/40"
                      autoFocus
                    />
                    {searchResults.length > 0 && (
                      <div className="absolute left-0 right-0 mt-1 bg-white border border-gray-200 rounded-xl shadow-lg z-10 overflow-hidden divide-y divide-gray-100">
                        {searchResults.map((mat) => (
                          <div
                            key={mat.id}
                            onClick={() => handleAddExistingMaterial(sec.seccion, mat)}
                            className="px-4 py-2 hover:bg-yeikar-primary/10 cursor-pointer flex items-center justify-between text-xs transition-all"
                          >
                            <span className="font-semibold text-gray-700">{mat.nombre}</span>
                            <span className="text-gray-400 font-mono">${mat.costo_base}/{mat.unidad_medida?.abreviatura || 'UN'}</span>
                          </div>
                        ))}
                      </div>
                    )}
                  </div>
                  <button
                    type="button"
                    onClick={() => setActiveSearchSection(null)}
                    className="px-3 py-2 text-xs border border-gray-300 text-gray-500 rounded-xl hover:bg-gray-100 transition-all"
                  >
                    Cancelar
                  </button>
                </div>

                <div className="flex items-center gap-2 pt-1">
                  <span className="text-[10px] text-gray-400">¿No lo encontraste? Agrega uno personalizado:</span>
                  <input
                    type="text"
                    placeholder="Nombre del nuevo insumo..."
                    value={customMaterialName}
                    onChange={(e) => setCustomMaterialName(e.target.value)}
                    className="border border-gray-200 rounded-lg px-2 py-1 text-[11px] w-48 focus:outline-none focus:ring-2 focus:ring-yeikar-primary/40"
                  />
                  <button
                    type="button"
                    onClick={() => handleAddTempLine(sec.seccion)}
                    className="bg-yeikar-primary text-yeikar-neutral px-2 py-1 rounded-lg text-[10px] font-bold hover:bg-yeikar-primary-dark transition-all"
                  >
                    Agregar Temporal
                  </button>
                  <span className="text-gray-300">|</span>
                  <button
                    type="button"
                    onClick={() => openCreateMaterialModal(sec.seccion, customMaterialName)}
                    className="bg-emerald-600 text-white px-2 py-1 rounded-lg text-[10px] font-bold hover:bg-emerald-700 transition-all"
                  >
                    Crear en Inventario
                  </button>
                </div>
              </div>
            ) : (
              <button
                type="button"
                onClick={() => startAddLine(sec.seccion)}
                className="text-xs font-semibold text-yeikar-primary hover:text-yeikar-primary-dark flex items-center gap-1 py-1"
              >
                 Agregar línea de costo
              </button>
            )}
          </div>
        </div>
      ))}

      {/* Acción general */}
      <div className="flex flex-col sm:flex-row gap-3 pt-2">
        <button
          type="button"
          onClick={handleAddSection}
          className="flex-1 py-3 border-2 border-dashed border-gray-300 text-gray-500 rounded-2xl hover:bg-gray-50 hover:border-gray-400 font-semibold text-sm transition-all flex items-center justify-center gap-2"
        >
           Agregar nueva sección de producción
        </button>
        <button
          type="button"
          onClick={onRecalculate}
          disabled={isLoading}
          className="flex-1 py-3 bg-yeikar-primary text-yeikar-neutral rounded-2xl font-bold text-sm hover:bg-yeikar-primary-dark transition-all disabled:opacity-50 shadow-md flex items-center justify-center gap-2"
        >
          {isLoading ? (
            <svg className="animate-spin w-4 h-4" fill="none" viewBox="0 0 24 24"><circle className="opacity-25" cx="12" cy="12" r="10" stroke="currentColor" strokeWidth="4" /><path className="opacity-75" fill="currentColor" d="M4 12a8 8 0 018-8V0C5.373 0 0 5.373 0 12h4z" /></svg>
          ) : ''} Recalcular estructura
        </button>
      </div>

      {/* Modal para Crear Material en Caliente */}
      {isModalOpen && (
        <div className="fixed inset-0 bg-black/50 backdrop-blur-sm z-50 flex items-center justify-center p-4">
          <div className="bg-white rounded-2xl shadow-xl max-w-md w-full overflow-hidden border border-gray-200">
            <div className="bg-gradient-to-r from-yeikar-secondary to-yeikar-secondary-dark text-white px-6 py-4">
              <h3 className="font-headline font-bold text-lg">Dar de Alta Material</h3>
              <p className="text-xs text-white/70">Crea el insumo en el inventario real para guardarlo</p>
            </div>
            <form onSubmit={handleCreateMaterial} className="p-6 space-y-4 font-body">
              <div>
                <label className="block text-xs font-semibold text-gray-600 mb-1">Nombre del material *</label>
                <input
                  type="text"
                  required
                  value={newMatName}
                  onChange={(e) => setNewMatName(e.target.value)}
                  className="w-full border border-gray-200 rounded-xl px-4 py-2 text-sm focus:outline-none focus:ring-2 focus:ring-yeikar-primary/40 uppercase"
                />
              </div>

              <div className="grid grid-cols-2 gap-4">
                <div>
                  <label className="block text-xs font-semibold text-gray-600 mb-1">Costo Base ($) <span className="text-gray-400 font-normal">(Opcional)</span></label>
                  <input
                    type="number"
                    min="0"
                    step="0.01"
                    placeholder="0.00"
                    value={newMatCost}
                    onChange={(e) => setNewMatCost(e.target.value)}
                    className="w-full border border-gray-200 rounded-xl px-4 py-2 text-sm font-mono focus:outline-none focus:ring-2 focus:ring-yeikar-primary/40"
                  />
                </div>
                <div>
                  <label className="block text-xs font-semibold text-gray-600 mb-1">Unidad de Medida *</label>
                  <SearchSelect
                    value={newMatUnit}
                    onChange={(v) => setNewMatUnit(String(v))}
                    options={unidades.map((u) => ({ value: u.id, label: `${u.nombre} (${u.abreviatura})` }))}
                    placeholder="Seleccionar..."
                  />
                </div>
              </div>

              <div className="flex gap-3 pt-2">
                <button
                  type="button"
                  onClick={() => setIsModalOpen(false)}
                  className="flex-1 py-2.5 border border-gray-300 text-gray-600 rounded-xl font-medium text-sm hover:bg-gray-50 transition-all"
                >
                  Cancelar
                </button>
                <button
                  type="submit"
                  className="flex-1 py-2.5 bg-emerald-600 text-white rounded-xl font-bold text-sm hover:bg-emerald-700 transition-all shadow-sm"
                >
                  Confirmar y Guardar
                </button>
              </div>
            </form>
          </div>
        </div>
      )}

      {/* Modal: nueva sección */}
      {isNewSectionOpen && (
        <div className="fixed inset-0 z-50 flex items-center justify-center p-4 bg-black/50 backdrop-blur-sm">
          <div className="bg-white rounded-2xl shadow-xl max-w-md w-full overflow-hidden border border-gray-200">
            <div className="bg-gradient-to-r from-yeikar-secondary to-yeikar-secondary-dark text-white px-6 py-4">
              <h3 className="font-headline font-bold text-lg">Nueva Sección</h3>
              <p className="text-xs text-white/70">Agrupa insumos y costos bajo una misma etapa de producción</p>
            </div>
            <form
              onSubmit={(e) => {
                e.preventDefault();
                handleConfirmAddSection();
              }}
              className="p-6 space-y-4 font-body"
            >
              <div>
                <label className="block text-xs font-semibold text-gray-600 mb-1">Nombre de la sección *</label>
                <input
                  type="text"
                  required
                  autoFocus
                  value={newSectionName}
                  onChange={(e) => setNewSectionName(e.target.value)}
                  placeholder="ej. HERRAJES, TAPICERÍA"
                  className="w-full border border-gray-200 rounded-xl px-4 py-2 text-sm focus:outline-none focus:ring-2 focus:ring-yeikar-primary/40 uppercase"
                />
              </div>
              <div className="flex gap-3 pt-2">
                <button
                  type="button"
                  onClick={() => setIsNewSectionOpen(false)}
                  className="flex-1 py-2.5 border border-gray-300 text-gray-600 rounded-xl font-medium text-sm hover:bg-gray-50 transition-all"
                >
                  Cancelar
                </button>
                <button
                  type="submit"
                  className="flex-1 py-2.5 bg-yeikar-primary text-yeikar-neutral rounded-xl font-bold text-sm hover:bg-yeikar-primary/90 transition-all shadow-sm"
                >
                  Crear sección
                </button>
              </div>
            </form>
          </div>
        </div>
      )}
    </div>
  );
}
