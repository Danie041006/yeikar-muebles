import { useEffect, useMemo, useRef, useState } from 'react';
import { Check, ChevronDown, Search } from 'lucide-react';

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
  options: SearchSelectOption[];
  placeholder?: string;
  searchPlaceholder?: string;
  emptyText?: string;
  disabled?: boolean;
  className?: string;
}

export default function SearchSelect({
  value,
  onChange,
  options,
  placeholder = 'Seleccionar...',
  searchPlaceholder = 'Buscar...',
  emptyText = 'Sin resultados',
  disabled = false,
  className = '',
}: SearchSelectProps) {
  const [open, setOpen] = useState(false);
  const [query, setQuery] = useState('');
  const [highlighted, setHighlighted] = useState(0);
  const [coords, setCoords] = useState<{ top: number; left: number; width: number } | null>(null);
  const triggerRef = useRef<HTMLButtonElement>(null);
  const dropdownRef = useRef<HTMLDivElement>(null);
  const searchRef = useRef<HTMLInputElement>(null);
  const itemRefs = useRef<(HTMLButtonElement | null)[]>([]);
  const isCoarse = useCoarsePointer();

  const selected = useMemo(
    () => options.find((o) => String(o.value) === String(value)),
    [options, value]
  );

  const filtered = useMemo(() => {
    const q = query.trim().toLowerCase();
    if (!q) return options;
    return options.filter((o) => o.label.toLowerCase().includes(q));
  }, [options, query]);

  // Agrupa las opciones filtradas conservando el orden de aparición. Los
  // índices originales en `filtered` se preservan para la navegación con
  // teclado (highlighted apunta a posiciones del array plano).
  const clusters = useMemo(() => {
    if (!filtered.some((o) => o.group)) return null;
    const map = new Map<string, { group: string; items: { opt: SearchSelectOption; index: number }[] }>();
    filtered.forEach((opt, index) => {
      const group = opt.group ?? '';
      if (!map.has(group)) map.set(group, { group, items: [] });
      map.get(group)!.items.push({ opt, index });
    });
    return Array.from(map.values());
  }, [filtered]);

  const openDropdown = () => {
    if (disabled) return;
    const rect = triggerRef.current?.getBoundingClientRect();
    if (!rect) return;
    const height = Math.min(288, options.length * 40 + 64);
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
  }, [highlighted, filtered.length]);

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

  if (isCoarse) {
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
      setHighlighted((h) => Math.min(h + 1, filtered.length - 1));
    } else if (e.key === 'ArrowUp') {
      e.preventDefault();
      setHighlighted((h) => Math.max(h - 1, 0));
    } else if (e.key === 'Enter') {
      e.preventDefault();
      const opt = filtered[highlighted];
      if (opt) selectOption(opt);
    } else if (e.key === 'Escape') {
      setOpen(false);
    }
  };

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
        <span className="truncate">{selected ? selected.label : placeholder}</span>
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

          {filtered.length === 0 && (
            <div className="px-4 py-6 text-center text-sm text-yeikar-neutral/40">{emptyText}</div>
          )}

          {(() => {
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
                  <span className="truncate">{opt.label}</span>
                  {isSelected && <Check className="h-4 w-4 shrink-0" />}
                </button>
              );
            };
            if (!clusters) return filtered.map((opt, i) => renderItem(opt, i, false));
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
