import { motion } from 'framer-motion';

interface Tab {
  key: string;
  label: string;
  count?: number;
  icon?: React.ReactNode;
}

interface TabsProps {
  tabs: Tab[];
  active: string;
  onChange: (key: string) => void;
  variant?: 'underline' | 'pills';
  className?: string;
}

export default function Tabs({
  tabs,
  active,
  onChange,
  variant = 'underline',
  className = '',
}: TabsProps) {
  if (variant === 'pills') {
    return (
      <div role="tablist" className={`inline-flex items-center gap-1 p-1.5 bg-white/70 backdrop-blur border border-yeikar-secondary-light/10 rounded-2xl ${className}`}>
        {tabs.map((tab) => {
          const isActive = tab.key === active;
          return (
            <button
              key={tab.key}
              type="button"
              role="tab"
              aria-selected={isActive}
              onClick={() => onChange(tab.key)}
              className={`relative px-4 py-2 text-xs font-bold font-headline rounded-xl transition-colors select-none flex items-center gap-2 ${
                isActive ? 'text-yeikar-neutral' : 'text-slate-500 hover:text-slate-800'
              }`}
            >
              {isActive && (
                <motion.div
                  layoutId="activeTabPill"
                  className="absolute inset-0 bg-white rounded-xl shadow-subtle border border-slate-200/60"
                  transition={{ type: 'spring', stiffness: 400, damping: 30 }}
                />
              )}
              <span className="relative z-10 flex items-center gap-1.5">
                {tab.icon}
                {tab.label}
              </span>
              {typeof tab.count === 'number' && (
                <span
                  className={`relative z-10 px-1.5 py-0.5 rounded-full text-[11px] font-mono font-bold ${
                    isActive
                      ? 'bg-amber-500/10 text-amber-800'
                      : 'bg-slate-200/70 text-slate-600'
                  }`}
                >
                  {tab.count}
                </span>
              )}
            </button>
          );
        })}
      </div>
    );
  }

  return (
    <div role="tablist" className={`flex flex-wrap items-center gap-2 border-b border-yeikar-secondary-light/10 ${className}`}>
      {tabs.map((tab) => {
        const isActive = tab.key === active;
        return (
          <button
            key={tab.key}
            type="button"
            role="tab"
            aria-selected={isActive}
            onClick={() => onChange(tab.key)}
            className={`relative px-4 py-3 text-sm font-bold font-headline transition-colors select-none flex items-center gap-2 ${
              isActive
                ? 'text-amber-800'
                : 'text-slate-500 hover:text-slate-800'
            }`}
          >
            {tab.icon}
            {tab.label}
            {typeof tab.count === 'number' && (
              <span
                className={`px-2 py-0.5 rounded-full text-xs font-mono font-bold ${
                  isActive
                    ? 'bg-amber-500/10 text-amber-800 border border-amber-500/20'
                    : 'bg-slate-100 text-slate-600'
                }`}
              >
                {tab.count}
              </span>
            )}
            {isActive && (
              <motion.div
                layoutId="activeTabUnderline"
                className="absolute bottom-0 left-0 right-0 h-0.5 bg-yeikar-primary rounded-t-full"
                transition={{ type: 'spring', stiffness: 500, damping: 35 }}
              />
            )}
          </button>
        );
      })}
    </div>
  );
}
