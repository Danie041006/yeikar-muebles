import React from 'react';

interface BadgeProps {
  tone?: 'neutral' | 'gold' | 'green' | 'red' | 'blue' | 'amber' | 'purple';
  children: React.ReactNode;
  dot?: boolean;
  pulse?: boolean;
  className?: string;
  size?: 'sm' | 'md';
}

const tones: Record<NonNullable<BadgeProps['tone']>, string> = {
  neutral: 'bg-yeikar-tertiary text-yeikar-secondary border-yeikar-secondary-light/15',
  gold: 'bg-amber-500/10 text-amber-800 border-amber-500/20',
  green: 'bg-emerald-50 text-emerald-700 border-emerald-200/60',
  red: 'bg-rose-50 text-rose-700 border-rose-200/60',
  blue: 'bg-sky-50 text-sky-700 border-sky-200/60',
  amber: 'bg-amber-50 text-amber-800 border-amber-200/60',
  purple: 'bg-purple-50 text-purple-700 border-purple-200/60',
};

const dots: Record<NonNullable<BadgeProps['tone']>, string> = {
  neutral: 'bg-slate-400',
  gold: 'bg-amber-500',
  green: 'bg-emerald-500',
  red: 'bg-rose-500',
  blue: 'bg-sky-500',
  amber: 'bg-amber-500',
  purple: 'bg-purple-500',
};

export default function Badge({
  tone = 'neutral',
  dot = false,
  pulse = false,
  size = 'md',
  className = '',
  children,
}: BadgeProps) {
  const sizeClasses = size === 'sm' ? 'px-2 py-0.5 text-[11px]' : 'px-2.5 py-1 text-xs';

  return (
    <span
      className={`inline-flex items-center gap-1.5 rounded-full font-headline font-semibold border tracking-tight transition-all duration-150 whitespace-nowrap ${sizeClasses} ${tones[tone]} ${className}`}
    >
      {dot && (
        <span className="relative flex h-1.5 w-1.5">
          {pulse && (
            <span
              className={`animate-ping absolute inline-flex h-full w-full rounded-full ${dots[tone]} opacity-75`}
            />
          )}
          <span className={`relative inline-flex rounded-full h-1.5 w-1.5 ${dots[tone]}`} />
        </span>
      )}
      {children}
    </span>
  );
}
