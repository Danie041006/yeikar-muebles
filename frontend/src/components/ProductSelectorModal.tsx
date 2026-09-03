import { useState, useMemo, useEffect } from 'react';
import { Search, X, Check, LayoutGrid, List, Package, Ruler, Sparkles, Tag, ArrowRight } from 'lucide-react';
import Modal from './ui/Modal';
import AdjuntoImagen from './AdjuntoImagen';
import { Product } from '../services/cotizacionService';
import { formatCurrency } from '../utils/format';

interface ProductSelectorModalProps {
  open: boolean;
  onClose: () => void;
  products: Product[];
  selectedProductId?: number | string | null;
  onSelectProduct: (product: Product) => void;
  currencyCode?: string;
  tasaCambio?: number;
  selectedMonedaId?: number;
  title?: string;
}

export default function ProductSelectorModal({
  open,
  onClose,
  products,
  selectedProductId,
  onSelectProduct,
  currencyCode = 'COP',
  tasaCambio = 1,
  selectedMonedaId = 1,
  title = 'Catálogo de Modelos y Muebles',
}: ProductSelectorModalProps) {
  const [searchTerm, setSearchTerm] = useState('');
  const [selectedCategory, setSelectedCategory] = useState<string>('TODOS');
  const [viewMode, setViewMode] = useState<'grid' | 'list'>('grid');

  // Reset search and category when opened
  useEffect(() => {
    if (open) {
      setSearchTerm('');
    }
  }, [open]);

  // Extract unique categories from products
  const { categories, totalFabricados, totalReventa } = useMemo(() => {
    const catsMap = new Map<string, number>();
    let fabCount = 0;
    let revCount = 0;

    products.forEach((p) => {
      if (p.es_reventa) {
        revCount++;
      } else {
        fabCount++;
      }

      const cat = p.tipo_producto?.nombre || p.categoria || 'Sin clasificar';
      catsMap.set(cat, (catsMap.get(cat) || 0) + 1);
    });

    const sortedCats = Array.from(catsMap.entries())
      .map(([name, count]) => ({ name, count }))
      .sort((a, b) => b.count - a.count);

    return {
      categories: sortedCats,
      totalFabricados: fabCount,
      totalReventa: revCount,
    };
  }, [products]);

  // Format reference base price for display (incluye el código de moneda para
  // que el usuario sepa en qué moneda está el precio mostrado).
  const getProductDisplayPrice = (p: Product): { text: string; code: string } | null => {
    const basePrecio = Number(p.precio_venta_base ?? p.precio_costo_base ?? 0);
    if (!isFinite(basePrecio) || basePrecio <= 0) return null;

    const monedaExtranjera = p.moneda && p.moneda.codigo !== 'COP' ? p.moneda.codigo : null;
    if (monedaExtranjera) {
      return { text: formatCurrency(basePrecio, monedaExtranjera), code: monedaExtranjera };
    }
    const divisor = selectedMonedaId === 1 ? 1 : (tasaCambio > 0 ? tasaCambio : 1);
    return { text: formatCurrency(basePrecio / divisor, currencyCode), code: currencyCode };
  };

  // Filter products based on search and category
  const filteredProducts = useMemo(() => {
    const query = searchTerm.toLowerCase().trim();

    return products.filter((p) => {
      // Category filter
      if (selectedCategory === 'FABRICADOS' && p.es_reventa) return false;
      if (selectedCategory === 'REVENTA' && !p.es_reventa) return false;
      if (
        selectedCategory !== 'TODOS' &&
        selectedCategory !== 'FABRICADOS' &&
        selectedCategory !== 'REVENTA'
      ) {
        const cat = p.tipo_producto?.nombre || p.categoria || 'Sin clasificar';
        if (cat !== selectedCategory) return false;
      }

      // Text search filter
      if (!query) return true;

      const matchName = p.nombre?.toLowerCase().includes(query);
      const matchCode = p.codigo?.toLowerCase().includes(query);
      const matchDesc = p.descripcion?.toLowerCase().includes(query);
      const matchCat = (p.tipo_producto?.nombre || p.categoria || '').toLowerCase().includes(query);

      return matchName || matchCode || matchDesc || matchCat;
    });
  }, [products, searchTerm, selectedCategory]);

  const handleSelect = (product: Product) => {
    onSelectProduct(product);
    onClose();
  };

  const currentSelectedIdNum = selectedProductId ? Number(selectedProductId) : null;

  return (
    <Modal
      open={open}
      onClose={onClose}
      size="5xl"
      title={
        <div className="flex items-center justify-between gap-3 w-full pr-4 sm:pr-6">
          <div className="flex items-center gap-2.5">
            <div className="w-9 h-9 rounded-xl bg-yeikar-primary/20 text-yeikar-neutral flex items-center justify-center border border-yeikar-primary/30">
              <Package className="w-5 h-5 text-yeikar-secondary" />
            </div>
            <div>
              <h3 className="text-lg font-black font-headline text-yeikar-secondary tracking-tight">
                {title}
              </h3>
              <p className="text-xs text-stone-500 font-body">
                Haga clic sobre un mueble o presione &ldquo;Seleccionar&rdquo; para agregarlo al presupuesto
              </p>
            </div>
          </div>
        </div>
      }
    >
      <div className="flex flex-col h-full -m-4 sm:-m-6">
        {/* Top Control Bar: Search + Category Filters + View Mode */}
        <div className="p-5 bg-gradient-to-b from-yeikar-tertiary/60 to-white border-b border-yeikar-secondary-light/15 space-y-3.5">
          {/* Search bar & View switch */}
          <div className="flex items-center gap-3">
            <div className="relative flex-1">
              <Search className="w-4 h-4 text-stone-400 absolute left-3.5 top-1/2 -translate-y-1/2" />
              <input
                type="text"
                value={searchTerm}
                onChange={(e) => setSearchTerm(e.target.value)}
                placeholder="Buscar por nombre de mueble, código, tipo o características..."
                autoFocus
                className="w-full pl-10 pr-9 py-2.5 bg-white border border-yeikar-secondary-light/25 rounded-xl text-sm font-body text-yeikar-neutral placeholder:text-stone-400 focus:outline-none focus:ring-2 focus:ring-yeikar-primary/60 focus:border-yeikar-primary transition-all shadow-sm"
              />
              {searchTerm && (
                <button
                  onClick={() => setSearchTerm('')}
                  className="absolute right-3 top-1/2 -translate-y-1/2 text-stone-400 hover:text-stone-600 p-0.5 rounded-full hover:bg-stone-100 transition-colors"
                  title="Borrar búsqueda"
                >
                  <X className="w-4 h-4" />
                </button>
              )}
            </div>

            {/* View Mode Toggle */}
            <div className="flex items-center bg-stone-100 p-1 rounded-xl border border-stone-200/80 shrink-0">
              <button
                type="button"
                onClick={() => setViewMode('grid')}
                className={`flex items-center gap-1.5 px-3 py-1.5 rounded-lg text-xs font-bold transition-all ${
                  viewMode === 'grid'
                    ? 'bg-white text-yeikar-secondary shadow-sm'
                    : 'text-stone-500 hover:text-stone-800'
                }`}
                title="Vista Cuadrícula / Tarjetas"
              >
                <LayoutGrid className="w-3.5 h-3.5" />
                <span className="hidden sm:inline">Tarjetas</span>
              </button>
              <button
                type="button"
                onClick={() => setViewMode('list')}
                className={`flex items-center gap-1.5 px-3 py-1.5 rounded-lg text-xs font-bold transition-all ${
                  viewMode === 'list'
                    ? 'bg-white text-yeikar-secondary shadow-sm'
                    : 'text-stone-500 hover:text-stone-800'
                }`}
                title="Vista Lista / Índice Detallado"
              >
                <List className="w-3.5 h-3.5" />
                <span className="hidden sm:inline">Índice</span>
              </button>
            </div>
          </div>

          {/* Indices / Categories Horizontal Bar */}
          <div className="flex items-center gap-2 overflow-x-auto pb-1">
            <span className="text-[11px] font-bold uppercase tracking-wider text-stone-400 flex items-center gap-1 shrink-0 font-headline">
              <Tag className="w-3 h-3 text-yeikar-primary" /> Filtro:
            </span>

            <button
              type="button"
              onClick={() => setSelectedCategory('TODOS')}
              className={`px-3 py-1 rounded-full text-xs font-bold transition-all shrink-0 border ${
                selectedCategory === 'TODOS'
                  ? 'bg-yeikar-secondary text-yeikar-tertiary border-yeikar-secondary shadow-sm'
                  : 'bg-white text-stone-600 border-stone-200 hover:border-yeikar-primary/50 hover:bg-stone-50'
              }`}
            >
              Todos ({products.length})
            </button>

            <button
              type="button"
              onClick={() => setSelectedCategory('FABRICADOS')}
              className={`px-3 py-1 rounded-full text-xs font-bold transition-all shrink-0 border flex items-center gap-1.5 ${
                selectedCategory === 'FABRICADOS'
                  ? 'bg-amber-600 text-white border-amber-600 shadow-sm'
                  : 'bg-amber-50 text-amber-900 border-amber-200 hover:bg-amber-100/70'
              }`}
            >
              <Sparkles className="w-3 h-3 text-amber-500" />
              Fabricados ({totalFabricados})
            </button>

            <button
              type="button"
              onClick={() => setSelectedCategory('REVENTA')}
              className={`px-3 py-1 rounded-full text-xs font-bold transition-all shrink-0 border ${
                selectedCategory === 'REVENTA'
                  ? 'bg-sky-700 text-white border-sky-700 shadow-sm'
                  : 'bg-sky-50 text-sky-900 border-sky-200 hover:bg-sky-100/70'
              }`}
            >
              Reventa ({totalReventa})
            </button>

            <div className="h-4 w-[1px] bg-stone-300 mx-1 shrink-0" />

            {categories.map((cat) => (
              <button
                key={cat.name}
                type="button"
                onClick={() => setSelectedCategory(cat.name)}
                className={`px-3 py-1 rounded-full text-xs font-bold transition-all shrink-0 border ${
                  selectedCategory === cat.name
                    ? 'bg-yeikar-primary text-yeikar-neutral border-yeikar-primary shadow-sm'
                    : 'bg-white text-stone-600 border-stone-200 hover:border-yeikar-primary/50 hover:bg-stone-50'
                }`}
              >
                {cat.name} ({cat.count})
              </button>
            ))}
          </div>
        </div>

        {/* Content Area: Products Grid or Index List */}
        <div className="flex-1 overflow-y-auto p-5 bg-stone-50/50">
          {filteredProducts.length === 0 ? (
            <div className="py-16 text-center">
              <div className="w-14 h-14 rounded-2xl bg-stone-100 text-stone-400 mx-auto flex items-center justify-center mb-3">
                <Package className="w-7 h-7" />
              </div>
              <h4 className="text-base font-bold font-headline text-stone-700">
                No se encontraron modelos
              </h4>
              <p className="text-xs text-stone-500 max-w-sm mx-auto mt-1">
                No hay productos que coincidan con &ldquo;{searchTerm}&rdquo; en la categoría seleccionada.
              </p>
              <div className="flex items-center justify-center gap-2 mt-4">
                {(searchTerm || selectedCategory !== 'TODOS') && (
                  <button
                    type="button"
                    onClick={() => {
                      setSearchTerm('');
                      setSelectedCategory('TODOS');
                    }}
                    className="px-4 py-2 bg-white border border-stone-200 rounded-xl text-xs font-bold text-yeikar-secondary hover:bg-stone-50 transition-colors shadow-sm focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-yeikar-primary/60"
                  >
                    Limpiar filtros
                  </button>
                )}
              </div>
            </div>
          ) : viewMode === 'grid' ? (
            /* Cuadrícula Visual */
            <div className="grid grid-cols-1 sm:grid-cols-2 lg:grid-cols-3 gap-3.5">
              {filteredProducts.map((p) => {
                const isSelected = currentSelectedIdNum === p.id;
                const priceInfo = getProductDisplayPrice(p);
                const firstPhoto = p.fotos && p.fotos.length > 0 ? p.fotos[0] : null;
                const catName = p.tipo_producto?.nombre || p.categoria || 'Sin categoría';

                return (
                  <div
                    key={p.id}
                    onClick={() => handleSelect(p)}
                    className={`group relative bg-white rounded-2xl border p-4 flex flex-col justify-between cursor-pointer transition-all duration-200 hover:shadow-md hover:-translate-y-0.5 ${
                      isSelected
                        ? 'border-yeikar-primary ring-2 ring-yeikar-primary/40 bg-amber-50/20'
                        : 'border-yeikar-secondary-light/15 hover:border-yeikar-primary/60'
                    }`}
                  >
                    {/* Header Tags */}
                    <div>
                      <div className="flex items-center justify-between gap-2 mb-2">
                        <div className="flex items-center gap-1.5 flex-wrap">
                          <span
                            className={`text-[10px] font-black uppercase px-2 py-0.5 rounded-md tracking-wider ${
                              p.es_reventa
                                ? 'bg-sky-100 text-sky-800 border border-sky-200'
                                : 'bg-amber-100 text-amber-900 border border-amber-200/60'
                            }`}
                          >
                            {p.es_reventa ? 'Reventa' : 'Fabricado'}
                          </span>
                          <span className="text-[10px] font-semibold text-stone-600 bg-stone-100 px-2 py-0.5 rounded-md">
                            {catName}
                          </span>
                        </div>

                        {p.codigo && (
                          <span className="text-[10px] font-mono font-bold text-stone-400 group-hover:text-yeikar-secondary transition-colors">
                            {p.codigo}
                          </span>
                        )}
                      </div>

                      {/* Photo / Thumbnail & Title */}
                      <div className="flex items-start gap-3 my-2">
                        {firstPhoto ? (
                          <div className="w-14 h-14 rounded-xl overflow-hidden bg-stone-100 border border-stone-200/60 shrink-0">
                            <AdjuntoImagen
                              adjunto={firstPhoto}
                              alt={p.nombre}
                              className="w-full h-full object-cover"
                            />
                          </div>
                        ) : (
                          <div className="w-14 h-14 rounded-xl bg-gradient-to-br from-yeikar-tertiary to-stone-100 border border-yeikar-secondary-light/10 flex items-center justify-center text-yeikar-secondary/40 shrink-0 group-hover:text-yeikar-primary transition-colors">
                            <Package className="w-6 h-6" />
                          </div>
                        )}

                        <div className="flex-1 min-w-0">
                          <h4 className="font-headline font-black text-sm text-yeikar-neutral leading-snug group-hover:text-yeikar-secondary transition-colors line-clamp-2">
                            {p.nombre}
                          </h4>
                          {p.descripcion && (
                            <p className="text-[11px] text-stone-500 line-clamp-2 mt-0.5">
                              {p.descripcion}
                            </p>
                          )}
                        </div>
                      </div>

                      {/* Dimensions info if fabricated */}
                      {!p.es_reventa && (p.ancho_base || p.largo_base) && (
                        <div className="flex items-center gap-1 text-[11px] text-stone-500 font-mono bg-stone-50 px-2 py-1 rounded-lg border border-stone-100 my-2">
                          <Ruler className="w-3.5 h-3.5 text-yeikar-primary shrink-0" />
                          <span>
                            Base: {Number(p.ancho_base || 1).toFixed(2)}m × {Number(p.largo_base || 1).toFixed(2)}m
                            {p.alto_base ? ` × ${Number(p.alto_base).toFixed(2)}m` : ''}
                          </span>
                        </div>
                      )}
                    </div>

                    {/* Bottom: Base Price & Action Button */}
                    <div className="pt-3 mt-1 border-t border-stone-100 flex items-center justify-between gap-2">
                      <div>
                        <span className="block text-[9px] uppercase font-bold text-stone-400">
                          {p.es_reventa ? 'Precio Ref.' : 'Precio Base'}
                          {priceInfo?.code ? ` · ${priceInfo.code}` : ''}
                        </span>
                        <span className="font-mono text-xs font-black text-yeikar-secondary">
                          {priceInfo?.text || '—'}
                        </span>
                      </div>

                      <button
                        type="button"
                        onClick={(e) => {
                          e.stopPropagation();
                          handleSelect(p);
                        }}
                        className={`flex items-center gap-1 px-3 py-1.5 rounded-xl text-xs font-bold font-headline transition-all ${
                          isSelected
                            ? 'bg-emerald-600 text-white shadow-sm'
                            : 'bg-yeikar-secondary text-yeikar-tertiary group-hover:bg-yeikar-primary group-hover:text-yeikar-neutral shadow-sm'
                        }`}
                      >
                        {isSelected ? (
                          <>
                            <Check className="w-3.5 h-3.5" />
                            <span>Seleccionado</span>
                          </>
                        ) : (
                          <>
                            <span>Elegir</span>
                            <ArrowRight className="w-3 h-3" />
                          </>
                        )}
                      </button>
                    </div>
                  </div>
                );
              })}
            </div>
          ) : (
            /* Vista Lista / Índice Detallado */
            <div className="bg-white rounded-2xl border border-yeikar-secondary-light/15 overflow-hidden shadow-sm">
              <table className="w-full text-left text-xs border-collapse">
                <thead>
                  <tr className="bg-yeikar-neutral text-yeikar-tertiary uppercase text-[10px] tracking-wider font-headline">
                    <th className="py-3 px-4">Mueble / Modelo</th>
                    <th className="py-3 px-4">Tipo / Categoría</th>
                    <th className="py-3 px-4">Medidas Base</th>
                    <th className="py-3 px-4 text-right">Precio Ref.</th>
                    <th className="py-3 px-4 text-center">Acción</th>
                  </tr>
                </thead>
                <tbody className="divide-y divide-stone-100">
                  {filteredProducts.map((p) => {
                    const isSelected = currentSelectedIdNum === p.id;
                    const priceInfo = getProductDisplayPrice(p);
                    const catName = p.tipo_producto?.nombre || p.categoria || 'Sin clasificar';

                    return (
                      <tr
                        key={p.id}
                        onClick={() => handleSelect(p)}
                        className={`cursor-pointer hover:bg-amber-50/40 transition-colors ${
                          isSelected ? 'bg-amber-50/70 font-semibold' : ''
                        }`}
                      >
                        <td className="py-3 px-4">
                          <div className="font-headline font-bold text-yeikar-neutral text-xs sm:text-sm">
                            {p.nombre}
                          </div>
                          {p.codigo && (
                            <span className="text-[10px] font-mono text-stone-400">
                              Código: {p.codigo}
                            </span>
                          )}
                        </td>
                        <td className="py-3 px-4">
                          <div className="flex items-center gap-1.5 flex-wrap">
                            <span
                              className={`text-[9px] font-bold uppercase px-1.5 py-0.5 rounded ${
                                p.es_reventa
                                  ? 'bg-sky-100 text-sky-800'
                                  : 'bg-amber-100 text-amber-900'
                              }`}
                            >
                              {p.es_reventa ? 'Reventa' : 'Fabricado'}
                            </span>
                            <span className="text-stone-600">{catName}</span>
                          </div>
                        </td>
                        <td className="py-3 px-4 font-mono text-stone-600">
                          {!p.es_reventa && (p.ancho_base || p.largo_base) ? (
                            <span>
                              {Number(p.ancho_base || 1).toFixed(2)}m × {Number(p.largo_base || 1).toFixed(2)}m
                            </span>
                          ) : (
                            <span className="text-stone-400 italic">No aplica</span>
                          )}
                        </td>
                        <td className="py-3 px-4 text-right font-mono font-bold text-yeikar-secondary">
                          {priceInfo ? (
                            <>
                              {priceInfo.text}
                              <span className="block text-[9px] font-bold text-stone-400 uppercase">
                                {priceInfo.code}
                              </span>
                            </>
                          ) : (
                            '—'
                          )}
                        </td>
                        <td className="py-3 px-4 text-center">
                          <button
                            type="button"
                            onClick={(e) => {
                              e.stopPropagation();
                              handleSelect(p);
                            }}
                            className={`px-3 py-1 rounded-lg text-xs font-bold font-headline transition-all ${
                              isSelected
                                ? 'bg-emerald-600 text-white'
                                : 'bg-yeikar-secondary text-yeikar-tertiary hover:bg-yeikar-primary hover:text-yeikar-neutral'
                            }`}
                          >
                            {isSelected ? '✓ Seleccionado' : 'Seleccionar'}
                          </button>
                        </td>
                      </tr>
                    );
                  })}
                </tbody>
              </table>
            </div>
          )}
        </div>

        {/* Footer info & Dismiss */}
        <div className="p-4 bg-white border-t border-yeikar-secondary-light/15 flex items-center justify-between text-xs text-stone-500">
          <div className="flex items-center gap-3">
            <span className="font-medium">
              Mostrando <span className="font-bold text-yeikar-neutral">{filteredProducts.length}</span> de{' '}
              <span className="font-bold text-yeikar-neutral">{products.length}</span> muebles en catálogo
            </span>
          </div>
          <button
            type="button"
            onClick={onClose}
            className="px-4 py-1.5 border border-stone-300 hover:bg-stone-100 rounded-xl text-stone-700 font-bold transition-all"
          >
            Cerrar
          </button>
        </div>
      </div>
    </Modal>
  );
}
