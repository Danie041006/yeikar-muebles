import { Loader2 } from 'lucide-react';

interface SpinnerProps {
  label?: string;
  size?: 'sm' | 'md' | 'lg';
  className?: string;
}

const sizes = {
  sm: 'w-5 h-5',
  md: 'w-8 h-8',
  lg: 'w-12 h-12',
};

export default function Spinner({ label, size = 'md', className = '' }: SpinnerProps) {
  return (
    <div className={`flex flex-col items-center justify-center gap-3 p-4 ${className}`}>
      <Loader2 className={`${sizes[size]} text-yeikar-primary animate-spin`} />
       {label && <p className="text-xs font-mono font-semibold text-yeikar-neutral/50">{label}</p>}
    </div>
  );
}
