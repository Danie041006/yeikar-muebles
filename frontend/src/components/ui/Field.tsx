import type { InputHTMLAttributes, ReactNode, SelectHTMLAttributes, TextareaHTMLAttributes } from 'react';

export function Label({ children }: { children: ReactNode }) {
  return <label className="block text-[11px] font-headline font-bold tracking-[0.08em] text-yeikar-secondary/80 mb-1.5">{children}</label>;
}

interface FieldProps {
  label: string;
  children: ReactNode;
  className?: string;
  required?: boolean;
  hint?: string;
  error?: string;
}

export function Field({ label, children, className = '', required = false, hint, error }: FieldProps) {
  return (
    <div className={className}>
      <Label>
        {label}
        {required && <span className="text-amber-600 ml-1 font-mono">*</span>}
      </Label>
      {children}
      {hint && !error && <p className="text-xs text-yeikar-neutral/50 mt-1">{hint}</p>}
      {error && <p className="text-xs text-rose-600 font-semibold mt-1">{error}</p>}
    </div>
  );
}

export function Input({ className = '', ...rest }: InputHTMLAttributes<HTMLInputElement>) {
  return (
    <input
      className={`input ${className}`}
      {...rest}
    />
  );
}

export function Select({ className = '', ...rest }: SelectHTMLAttributes<HTMLSelectElement>) {
  return (
    <select
      className={`input appearance-none pr-10 cursor-pointer ${className}`}
      {...rest}
    />
  );
}

export function Textarea({ className = '', ...rest }: TextareaHTMLAttributes<HTMLTextAreaElement>) {
  return (
    <textarea
      className={`input min-h-[96px] resize-y ${className}`}
      {...rest}
    />
  );
}
