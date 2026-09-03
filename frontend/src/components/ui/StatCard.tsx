import type { ReactNode } from 'react';

interface StatCardProps {
  label: string;
  value: ReactNode;
  icon?: ReactNode;
  accent?: string;
  iconBg?: string;
  iconText?: string;
  hint?: ReactNode;
  trend?: {
    value: string;
    positive?: boolean;
  };
  className?: string;
}

export default function StatCard({
  label,
  value,
  icon,
  accent = 'from-yeikar-primary to-amber-300',
  iconBg = 'bg-amber-500/10 border border-amber-500/20',
  iconText = 'text-amber-800',
  hint,
  trend,
  className = '',
}: StatCardProps) {
  return (
    <div
      className={`relative bg-white border border-yeikar-secondary-light/10 rounded-2xl p-4 sm:p-6 shadow-card hover:shadow-lift transition-all duration-200 overflow-hidden ${className}`}
    >
      {/* Top golden accent ribbon */}
      <div className={`absolute top-0 left-0 right-0 h-1 bg-gradient-to-r ${accent}`} />

      <div className="flex items-start justify-between gap-3 sm:gap-4">
        <div className="space-y-1 min-w-0">
           <p className="text-[11px] font-mono font-bold uppercase tracking-[0.1em] text-yeikar-neutral/55">
            {label}
          </p>
          <div className="flex items-baseline gap-2 flex-wrap">
            <h3 className="text-xl sm:text-2xl font-black font-headline tracking-tight text-yeikar-neutral leading-none break-words">
              {value}
            </h3>
            {trend && (
              <span
                className={`inline-flex items-center text-xs font-bold font-headline px-1.5 py-0.5 rounded-full ${
                  trend.positive
                    ? 'bg-emerald-50 text-emerald-700'
                    : 'bg-rose-50 text-rose-700'
                }`}
              >
                {trend.positive ? '↑' : '↓'} {trend.value}
              </span>
            )}
          </div>
           {hint && <div className="text-xs text-yeikar-neutral/55 pt-0.5">{hint}</div>}
        </div>

        {icon && (
          <div
            className={`p-3 rounded-2xl shrink-0 flex items-center justify-center ${iconBg} ${iconText}`}
          >
            {icon}
          </div>
        )}
      </div>
    </div>
  );
}
