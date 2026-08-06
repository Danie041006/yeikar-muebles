import type { ReactNode } from 'react';

interface PageHeaderProps {
  eyebrow?: string;
  title: string;
  subtitle?: ReactNode;
  actions?: ReactNode;
  icon?: ReactNode;
}

export default function PageHeader({ eyebrow, title, subtitle, actions, icon }: PageHeaderProps) {
  return (
    <div className="flex flex-wrap items-center justify-between gap-4 pb-3 border-b border-yeikar-secondary-light/10">
      <div className="flex items-center gap-3.5">
        {icon && (
          <div className="p-3 bg-amber-500/10 border border-amber-500/20 text-amber-800 rounded-2xl shrink-0 shadow-subtle">
            {icon}
          </div>
        )}
        <div>
          {eyebrow && (
            <p className="eyebrow mb-1">
              {eyebrow}
            </p>
          )}
          <h1 className="text-2xl sm:text-3xl font-black font-headline text-yeikar-neutral tracking-tight leading-tight">
            {title}
          </h1>
          {subtitle && <p className="text-yeikar-neutral/55 text-sm mt-1">{subtitle}</p>}
        </div>
      </div>
      {actions && <div className="flex items-center gap-3 flex-wrap">{actions}</div>}
    </div>
  );
}
