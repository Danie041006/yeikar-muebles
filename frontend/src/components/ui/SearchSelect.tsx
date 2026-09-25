import { useEffect, useMemo, useRef, useState } from 'react';
import { Check, ChevronDown, Loader2, Search } from 'lucide-react';
import { useDebouncedValue } from '../../hooks/useDebouncedValue';

export interface SearchSelectOption {
  value: string | number;
  label: string;
  /** Grupo opcional (se renderiza como encabezado de sección / optgroup). */
  group?: string;
}

function useCoarsePointer(): boolean {
  const [coarse, setCoarse] = useState(() => {
    if (typeof window === 'undefined' || !window.matchMedia) return false;
    return window.matchMedia('(pointer: coarse)').matches;
  });

  useEffect(() => {
    if (typeof window === 'undefined' || !window.matchMedia) return;
    const mql = window.matchMedia('(pointer: coarse)');
    const onChange = (e: MediaQueryListEvent) => setCoarse(e.matches);
    mql.addEventListener('change', onChange);
    return () => mql.removeEventListener('change', onChange);
  }, []);

  return coarse;
}

interface SearchSelectProps {
  value: string | number | null | undefined;
  onChange: (value: string | number) => void;
  /**
   * Modo estático: opciones ya cargadas que se filtran en memoria.
   * En modo async (`loadOptions`) se usan como semilla del valor actual.
   */
  options?: SearchSelectOption[];
  /**
   * Modo async (autocomplete server-side): se llama al escribir, con debounce.
   * Cuando está presente, el dropdown consulta el backend en vez de filtrar
   * `options` en memoria (patrón Instagram/Facebook: pocos resultados, según
   * lo que tecleas). Opcional para conservar compatibilidad con los callers
   * actuales que pasan `options` estáticas.
   */
  loadOptions?: (query: string) => Promise<SearchSelectOption[]>;
  /** Async: caracteres mínimos para disparar la búsqueda (0 = cargar al abrir). */
  minChars?: number;
  /** Async: milisegundos de debounce entre keystrokes. */
  debounceMs?: number;
  placeholder?: string;
  searchPlaceholder?: string;
  emptyText?: string;
  disabled?: boolean;
  className?: string;
  /** Renderizado custom del label de cada opción (dropdown + trigger). */
  renderLabel?: (option: SearchSelectOption) => React.ReactNode;
  /**
   * Label del valor actual. Necesario en modo async cuando el valor ya está
   * seleccionado (p.ej. responsable de etapa precargado) y `options` no
   * contiene todavía esa fila: sin esto el trigger mostraría el placeholder.
   */
  selectedOption?: SearchSelectOption;
}

export default function SearchSelect({
  value,
  onChange,
  options = [],
  loadOptions,
  minChars = 0,
  debounceMs = 300,
  placeholder = 'Seleccionar...',
  searchPlaceholder = 'Buscar...',
  emptyText = 'Sin resultados',
  disabled = false,
  className = '',
  renderLabel,
  selectedOption,
}: SearchSelectProps) {
  const [open, setOpen] = useState(false);
  const [query, setQuery] = useState('');
  const [highlighted, setHighlighted] = useState(0);
  const [coords, setCoords] = useState<{ top: number; left: number; width: number } | null>(null);
  const [asyncOptions, setAsyncOptions] = useState<SearchSelectOption[]>([]);
  const [loadingAsync, setLoadingAsync] = useState(false);
  const triggerRef = useRef<HTMLButtonElement>(null);
  const dropdownRef = useRef<HTMLDivElement>(null);
  const searchRef = useRef<HTMLInputElement>(null);
  const itemRefs = useRef<(HTMLButtonElement | null)[]>([]);
  const isCoarse = useCoarsePointer();

  const isAsync = typeof loadOptions === 'function';
  const debouncedQuery = useDebouncedValue(query, isAsync ? debounceMs : 0);

  const selected = useMemo(() => {
    // Prioridad: lo que ya está en options (estático) o vino de la búsqueda
    // async. selectedOption es solo un fallback para valores precargados que
    // aún no están en ninguna lista (p.ej. responsable de etapa).
    return (
      options.find((o) => String(o.value) === String(value)) ??
      asyncOptions.find((o) => String(o.value) === String(value)) ??
      selectedOption ??
      undefined
    );
  }, [options, asyncOptions, value, selectedOption]);

  const filtered = useMemo(() => {
    const q = query.trim().toLowerCase();
    if (!q) return options;
    return options.filter((o) => o.label.toLowerCase().includes(q));
  }, [options, query]);

  // ── Async: buscar en el backend con debounce ──
  useEffect(() => {
    if (!isAsync || !open) return;
    const q = debouncedQuery.trim();
    if (q.length < minChars) {
      setAsyncOptions([]);
      setLoadingAsync(false);
      return;
    }
    let active = true;
    setLoadingAsync(true);
    loadOptions!(q)
      .then((res) => { if (active) setAsyncOptions(res); })
      .catch(() => { if (active) setAsyncOptions([]); })
      .finally(() => { if (active) setLoadingAsync(false); });
    return () => { active = false; };
  }, [isAsync, open, debouncedQuery, minChars, loadOptions]);

  const items = isAsync ? asyncOptions : filtered;

  // Agrupa las opciones (estáticas o async) conservando el orden de aparición.
  const clusters = useMemo(() => {
    if (!items.some((o) => o.group)) return null;
    const map = new Map<string, { group: string; items: { opt: SearchSelectOption; index: number }[] }>();
    items.forEach((opt, index) => {
      const group = opt.group ?? '';
      if (!map.has(group)) map.set(group, { group, items: [] });
      map.get(group)!.items.push({ opt, index });
    });
    return Array.from(map.values());
  }, [items]);

  const openDropdown = () => {
    if (disabled) return;
    const rect = triggerRef.current?.getBoundingClientRect();
    if (!rect) return;
    const height = Math.min(288, items.length * 40 + 64);
    const placeUp = window.innerHeight - rect.bottom < height + 12;
    setCoords({
      top: placeUp ? Math.max(8, rect.top - height - 6) : rect.bottom + 6,
      left: rect.left,
      width: rect.width,
    });
    setQuery('');
    setHighlighted(0);
    setOpen(true);
  };

  useEffect(() => {
    if (open) searchRef.current?.focus();
  }, [open]);

  useEffect(() => {
    itemRefs.current[highlighted]?.scrollIntoView({ block: 'nearest' });
  }, [highlighted, items.length]);

  useEffect(() => {
    if (!open) return;
    const onPointerDown = (e: MouseEvent | TouchEvent) => {
      const target = e.target as Node;
      if (triggerRef.current?.contains(target) || dropdownRef.current?.contains(target)) return;
      setOpen(false);
    };
    const onScroll = (e: Event) => {
      if (dropdownRef.current?.contains(e.target as Node)) return;
      setOpen(false);
    };
    const onResize = () => setOpen(false);
    document.addEventListener('mousedown', onPointerDown);
    document.addEventListener('touchstart', onPointerDown);
    window.addEventListener('scroll', onScroll, true);
    window.addEventListener('resize', onResize);
    return () => {
      document.removeEventListener('mousedown', onPointerDown);
      document.removeEventListener('touchstart', onPointerDown);
      window.removeEventListener('scroll', onScroll, true);
      window.removeEventListener('resize', onResize);
    };
  }, [open]);

  const selectOption = (opt: SearchSelectOption) => {
    onChange(opt.value);
    setOpen(false);
  };

  // En móvil (pointer coarse) se renderiza un <select> nativo. En modo async
  // no aplica (no hay forma de buscar en server con un select nativo), así
  // que en ese caso usamos el autocomplete custom.
  if (isCoarse && !isAsync) {
    return (
      <div className={`relative ${className}`}>
        <select
          value={value ?? ''}
          disabled={disabled}
          onChange={(e) => {
            const v = e.target.value;
            const opt = options.find((o) => String(o.value) === v);
            onChange(opt ? opt.value : v);
          }}
          aria-label={placeholder}
          className="input min-h-11 cursor-pointer appearance-none pr-9"
        >
          <option value="" disabled>{placeholder}</option>
          {clusters ? (
            clusters.map((cluster) => (
              <optgroup key={cluster.group || 'sin-grupo'} label={cluster.group}>
                {cluster.items.map(({ opt }) => (
                  <option key={String(opt.value)} value={String(opt.value)}>{opt.label}</option>
                ))}
              </optgroup>
            ))
          ) : (
            options.map((opt) => (
              <option key={String(opt.value)} value={String(opt.value)}>{opt.label}</option>
            ))
          )}
        </select>
        <ChevronDown className="pointer-events-none absolute right-3 top-1/2 h-4 w-4 -translate-y-1/2 text-yeikar-primary-dark/60" />
      </div>
    );
  }

  const onSearchKeyDown = (e: React.KeyboardEvent<HTMLInputElement>) => {
    if (e.key === 'ArrowDown') {
      e.preventDefault();
      setHighlighted((h) => Math.min(h + 1, items.length - 1));
    } else if (e.key === 'ArrowUp') {
      e.preventDefault();
      setHighlighted((h) => Math.max(h - 1, 0));
    } else if (e.key === 'Enter') {
      e.preventDefault();
      const opt = items[highlighted];
      if (opt) selectOption(opt);
    } else if (e.key === 'Escape') {
      setOpen(false);
    }
  };

  const queryLength = debouncedQuery.trim().length;
  const canSearch = !isAsync || queryLength >= minChars;

  return (
    <div className={`relative ${className}`}>
      <button
        ref={triggerRef}
        type="button"
        disabled={disabled}
        onClick={() => (open ? setOpen(false) : openDropdown())}
        aria-haspopup="listbox"
        aria-expanded={open}
        className={`input flex items-center justify-between gap-2 text-left pr-9 disabled:opacity-50 disabled:cursor-not-allowed ${selected ? '' : 'text-yeikar-neutral/40'}`}
      >
        <span className="truncate">{selected ? (renderLabel ? renderLabel(selected) : selected.label) : placeholder}</span>
        <Search className="h-4 w-4 shrink-0 pointer-events-none text-yeikar-primary-dark/60" />
      </button>

      {open && coords && (
        <div
          ref={dropdownRef}
          role="listbox"
          style={{ position: 'fixed', top: coords.top, left: coords.left, width: coords.width }}
          className="z-[100] max-h-72 overflow-y-auto rounded-xl border border-yeikar-secondary-light/15 bg-white shadow-lift"
        >
          <div className="sticky top-0 z-10 border-b border-yeikar-secondary-light/10 bg-white p-2">
            <div className="relative">
              <Search className="absolute left-3 top-1/2 -translate-y-1/2 h-4 w-4 pointer-events-none text-yeikar-neutral/40" />
              <input
                ref={searchRef}
                type="text"
                value={query}
                onChange={(e) => {
                  setQuery(e.target.value);
                  setHighlighted(0);
                }}
                onKeyDown={onSearchKeyDown}
                placeholder={searchPlaceholder}
                className="w-full rounded-lg border border-yeikar-secondary-light/15 py-2 pl-9 pr-3 text-sm placeholder:text-yeikar-neutral/40 focus:outline-none focus:border-yeikar-primary focus:ring-2 focus:ring-yeikar-primary/20"
              />
            </div>
          </div>

          {loadingAsync && (
            <div className="flex items-center gap-2 px-4 py-3 text-sm text-yeikar-neutral/50">
              <Loader2 className="h-4 w-4 animate-spin" />
              Buscando…
            </div>
          )}

          {!loadingAsync && !canSearch && (
            <div className="px-4 py-6 text-center text-sm text-yeikar-neutral/40">
              Escribe al menos {minChars} caracteres para buscar
            </div>
          )}

          {!loadingAsync && canSearch && items.length === 0 && (
            <div className="px-4 py-6 text-center text-sm text-yeikar-neutral/40">{emptyText}</div>
          )}

          {canSearch && (() => {
            const renderItem = (opt: SearchSelectOption, i: number, indented: boolean) => {
              const isSelected = String(opt.value) === String(value);
              const isHighlighted = i === highlighted;
              return (
                <button
                  key={String(opt.value)}
                  ref={(el) => {
                    itemRefs.current[i] = el;
                  }}
                  type="button"
                  role="option"
                  aria-selected={isSelected}
                  onMouseEnter={() => setHighlighted(i)}
                  onClick={() => selectOption(opt)}
                  className={`flex w-full items-center justify-between gap-2 py-2.5 pr-4 text-left text-sm transition-colors ${
                    indented ? 'pl-6' : 'px-4'
                  } ${isHighlighted ? 'bg-yeikar-tertiary' : ''} ${
                    isSelected ? 'font-bold text-yeikar-primary-dark' : 'text-yeikar-neutral/90'
                  }`}
                >
                  <span className="truncate">{renderLabel ? renderLabel(opt) : opt.label}</span>
                  {isSelected && <Check className="h-4 w-4 shrink-0" />}
                </button>
              );
            };
            if (!clusters) return items.map((opt, i) => renderItem(opt, i, false));
            return clusters.map((cluster) => (
              <div key={cluster.group || '__sin_grupo'}>
                {cluster.group && (
                  <div className="border-b border-yeikar-secondary-light/10 bg-yeikar-tertiary/60 px-4 py-1.5 font-mono text-[10px] font-bold uppercase tracking-wider text-yeikar-neutral/50">
                    {cluster.group}
                  </div>
                )}
                {cluster.items.map(({ opt, index }) => renderItem(opt, index, true))}
              </div>
            ));
          })()}
        </div>
      )}
    </div>
  );
}