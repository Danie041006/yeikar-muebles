import type { ReactNode } from 'react';
import { PackageOpen } from 'lucide-react';

interface EmptyStateProps {
  icon?: ReactNode;
  title: string;
  description?: string;
  action?: ReactNode;
  compact?: boolean;
}

export default function EmptyState({
  icon,
  title,
  description,
  action,
  compact = false,
}: EmptyStateProps) {
  return (
    <div
        className={`flex flex-col items-center justify-center text-center border border-dashed border-yeikar-secondary-light/20 rounded-2xl bg-white/60 backdrop-blur-sm ${
        compact ? 'p-8' : 'p-14'
      }`}
    >
      <div className="w-14 h-14 rounded-2xl bg-amber-500/10 border border-amber-500/20 text-amber-800 flex items-center justify-center mb-4 shadow-subtle">
        {icon || <PackageOpen className="w-7 h-7" />}
      </div>
      <h4 className="text-base font-bold font-headline text-yeikar-neutral tracking-tight">
        {title}
      </h4>
      {description && (
        <p className="text-sm text-yeikar-neutral/55 mt-1 max-w-sm leading-relaxed">{description}</p>
      )}
      {action && <div className="mt-5">{action}</div>}
    </div>
  );
}
