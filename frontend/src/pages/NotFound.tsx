import { Link } from 'react-router-dom';
import { Compass } from 'lucide-react';
import SEO from '../components/SEO';

export default function NotFound() {
  return (
    <div className="premium-grid flex min-h-screen items-center justify-center bg-yeikar-tertiary p-6">
      <SEO
        title="Página no encontrada"
        description="La página que buscas no existe o fue movida."
      />
      <div className="w-full max-w-md rounded-2xl border border-yeikar-secondary-light/10 bg-white/75 p-10 text-center shadow-card backdrop-blur-xl">
        <div className="mx-auto mb-6 flex h-16 w-16 items-center justify-center rounded-2xl bg-yeikar-primary font-headline text-3xl font-black text-yeikar-neutral shadow-gold">
          Y
        </div>
        <p className="eyebrow mb-2">Error 404</p>
        <h1 className="font-headline text-3xl font-black tracking-tight text-yeikar-neutral">
          Página no encontrada
        </h1>
        <p className="mt-3 text-sm leading-relaxed text-yeikar-neutral/55">
          La dirección que intentas abrir no existe o fue movida dentro del sistema.
        </p>
        <div className="mt-8 flex items-center justify-center gap-3">
          <Link
            to="/dashboard"
            className="inline-flex items-center gap-2 rounded-xl bg-yeikar-primary px-5 py-2.5 font-headline text-sm font-bold text-yeikar-neutral shadow-gold transition-colors hover:bg-yeikar-primary-light"
          >
            <Compass className="h-4 w-4" strokeWidth={2} />
            Volver al inicio
          </Link>
        </div>
      </div>
    </div>
  );
}