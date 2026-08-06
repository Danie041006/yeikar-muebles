import type { ReactNode } from 'react';

interface CardProps {
  title?: ReactNode;
  subtitle?: string;
  action?: ReactNode;
  className?: string;
  bodyClassName?: string;
  headerClassName?: string;
  children: ReactNode;
  hoverable?: boolean;
}

export default function Card({
  title,
  subtitle,
  action,
  className = '',
  bodyClassName = '',
  headerClassName = '',
  children,
  hoverable = false,
}: CardProps) {
  return (
    <div
      className={`bg-white border border-yeikar-secondary-light/10 rounded-2xl shadow-card transition-all duration-200 overflow-hidden ${
        hoverable ? 'hover:shadow-lift hover:-translate-y-0.5 border-yeikar-secondary-light/20' : ''
      } ${className}`}
    >
      {(title || action || subtitle) && (
        <div
          className={`flex items-center justify-between px-6 pt-5 pb-4 border-b border-yeikar-secondary-light/10 ${headerClassName}`}
        >
          <div>
            {typeof title === 'string' ? (
              <h3 className="text-[15px] font-bold font-headline text-yeikar-neutral tracking-tight">
                {title}
              </h3>
            ) : (
              title
            )}
            {subtitle && <p className="text-xs text-yeikar-neutral/55 mt-1">{subtitle}</p>}
          </div>
          {action && <div className="flex items-center gap-2">{action}</div>}
        </div>
      )}
      <div className={`p-6 ${bodyClassName}`}>{children}</div>
    </div>
  );
}
