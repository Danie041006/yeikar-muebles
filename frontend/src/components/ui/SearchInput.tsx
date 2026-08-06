import React, { type InputHTMLAttributes } from 'react';
import { Search, X } from 'lucide-react';

interface SearchInputProps extends InputHTMLAttributes<HTMLInputElement> {
  value: string;
  onChange: (e: React.ChangeEvent<HTMLInputElement>) => void;
  onClear?: () => void;
  placeholder?: string;
  className?: string;
}

export default function SearchInput({
  value,
  onChange,
  onClear,
  placeholder = 'Buscar...',
  className = '',
  ...rest
}: SearchInputProps) {
  return (
    <div className={`relative flex items-center ${className}`}>
      <Search className="absolute left-3.5 h-4 w-4 pointer-events-none text-yeikar-neutral/40" />
      <input
        type="text"
        value={value}
        onChange={onChange}
        placeholder={placeholder}
         className="input bg-white pl-10 pr-9 text-sm placeholder:text-yeikar-neutral/40"
        {...rest}
      />
      {value && (
        <button
          type="button"
          onClick={() => {
            if (onClear) {
              onClear();
            } else {
              const event = { target: { value: '' } } as React.ChangeEvent<HTMLInputElement>;
              onChange(event);
            }
          }}
           className="absolute right-3 rounded-lg p-1 text-yeikar-neutral/35 transition-all hover:bg-yeikar-tertiary hover:text-yeikar-secondary"
        >
          <X className="w-3.5 h-3.5" />
        </button>
      )}
    </div>
  );
}
