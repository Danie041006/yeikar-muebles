import { createContext, useCallback, useContext, useMemo, useRef, useState, type ReactNode } from 'react';
import { AnimatePresence, motion } from 'framer-motion';
import { CheckCircle2, XCircle, Info, AlertTriangle, X } from 'lucide-react';

export type ToastType = 'success' | 'error' | 'info' | 'warning';

export interface ToastAction {
  label: string;
  onClick: () => void;
}

interface ToastItem {
  id: number;
  type: ToastType;
  message: string;
  duration: number;
  action?: ToastAction;
}

interface ToastApi {
  success: (message: string) => void;
  error: (message: string) => void;
  info: (message: string, action?: ToastAction) => void;
  warning: (message: string, action?: ToastAction) => void;
}

const ToastContext = createContext<ToastApi | null>(null);

const STYLES: Record<ToastType, { chip: string; bar: string; icon: ReactNode }> = {
  success: {
    chip: 'bg-green-50 text-green-600 border-green-200',
    bar: 'bg-green-500',
    icon: <CheckCircle2 className="w-4.5 h-4.5" />,
  },
  error: {
    chip: 'bg-rose-50 text-rose-600 border-rose-200',
    bar: 'bg-rose-500',
    icon: <XCircle className="w-4.5 h-4.5" />,
  },
  info: {
    chip: 'bg-yeikar-primary/10 text-yeikar-secondary border-yeikar-primary/20',
    bar: 'bg-yeikar-primary',
    icon: <Info className="w-4.5 h-4.5" />,
  },
  warning: {
    chip: 'bg-amber-50 text-amber-600 border-amber-200',
    bar: 'bg-amber-500',
    icon: <AlertTriangle className="w-4.5 h-4.5" />,
  },
};

const DURATIONS: Record<ToastType, number> = {
  success: 4500,
  error: 6500,
  info: 4500,
  warning: 5000,
};

export function ToastProvider({ children }: { children: ReactNode }) {
  const [toasts, setToasts] = useState<ToastItem[]>([]);
  const nextId = useRef(1);

  const dismiss = useCallback((id: number) => {
    setToasts((prev) => prev.filter((t) => t.id !== id));
  }, []);

  const push = useCallback(
    (type: ToastType, message: string, action?: ToastAction) => {
      const id = nextId.current++;
      const duration = action ? 0 : DURATIONS[type];
      setToasts((prev) => [...prev.slice(-3), { id, type, message, duration, action }]);
      if (!action) window.setTimeout(() => dismiss(id), duration);
    },
    [dismiss],
  );

  const api = useMemo<ToastApi>(
    () => ({
      success: (message) => push('success', message),
      error: (message) => push('error', message),
      info: (message, action) => push('info', message, action),
      warning: (message, action) => push('warning', message, action),
    }),
    [push],
  );

  return (
    <ToastContext.Provider value={api}>
      {children}
      <div
        className="fixed bottom-5 right-5 z-[80] flex w-full max-w-sm flex-col gap-2.5 mb-safe"
        aria-live="polite"
        aria-label="Notificaciones"
      >
        <AnimatePresence initial={false}>
          {toasts.map((toast) => {
            const style = STYLES[toast.type];
            return (
              <motion.div
                key={toast.id}
                layout
                initial={{ opacity: 0, x: 60, scale: 0.95 }}
                animate={{ opacity: 1, x: 0, scale: 1 }}
                exit={{ opacity: 0, x: 60, scale: 0.95 }}
                transition={{ duration: 0.28, ease: [0.16, 1, 0.3, 1] }}
                className="relative overflow-hidden rounded-2xl border border-yeikar-secondary-light/15 bg-white shadow-modal"
                role="status"
              >
                <div className="flex items-start gap-3 px-4 py-3.5">
                  <div className={`mt-0.5 flex h-8 w-8 shrink-0 items-center justify-center rounded-xl border ${style.chip}`}>
                    {style.icon}
                  </div>
                  <div className="flex-1 pt-1">
                    <p className="text-sm font-medium leading-snug text-yeikar-neutral">{toast.message}</p>
                    {toast.action && (
                      <button
                        onClick={toast.action.onClick}
                        className="mt-2 rounded-lg bg-yeikar-primary px-3 py-1.5 text-xs font-bold text-yeikar-neutral shadow-gold transition-transform active:scale-95"
                      >
                        {toast.action.label}
                      </button>
                    )}
                  </div>
                  <button
                    onClick={() => dismiss(toast.id)}
                    className="-mr-1 -mt-1 p-1 text-yeikar-neutral/35 transition-colors hover:text-yeikar-neutral"
                    aria-label="Cerrar notificación"
                  >
                    <X className="h-4 w-4" />
                  </button>
                </div>
                {toast.duration > 0 && (
                  <motion.div
                    initial={{ width: '100%' }}
                    animate={{ width: '0%' }}
                    transition={{ duration: toast.duration / 1000, ease: 'linear' }}
                    className={`h-0.5 ${style.bar}`}
                  />
                )}
              </motion.div>
            );
          })}
        </AnimatePresence>
      </div>
    </ToastContext.Provider>
  );
}

export function useToast(): ToastApi {
  const ctx = useContext(ToastContext);
  if (!ctx) throw new Error('useToast debe usarse dentro de <ToastProvider>');
  return ctx;
}
