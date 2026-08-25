import { useEffect, useState } from 'react';
import { descargarAdjunto, type AdjuntoInfo } from '../services/adjuntosService';

interface Props {
  adjunto?: AdjuntoInfo | null;
  alt?: string;
  className?: string;
  /** Llamada cuando el usuario hace clic (p. ej. para ampliar en un modal). */
  onClick?: () => void;
}

/**
 * Muestra una imagen adjunta:
 * - Si trae `url` pública (fotos de PRODUCTO) la usa directo.
 * - Si solo trae `id` (recibos/comprobantes) la descarga con el token y la
 *   muestra como blob — así los comprobantes jamás se exponen públicamente.
 */
export default function AdjuntoImagen({ adjunto, alt, className, onClick }: Props) {
  const [blobUrl, setBlobUrl] = useState<string | null>(null);
  const [error, setError] = useState(false);

  useEffect(() => {
    let activo = true;
    if (!adjunto) return;
    if (adjunto.url) return; // pública, sin descarga
    setError(false);
    descargarAdjunto(adjunto.id)
      .then((blob) => {
        if (!activo) return;
        setBlobUrl(URL.createObjectURL(blob));
      })
      .catch(() => activo && setError(true));
    return () => {
      activo = false;
      if (blobUrl) URL.revokeObjectURL(blobUrl);
    };
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [adjunto?.id, adjunto?.url]);

  const src = adjunto?.url ?? blobUrl;
  if (!adjunto || (!src && error)) {
    return (
      <div className={`flex items-center justify-center rounded-lg bg-stone-200 text-stone-400 ${className ?? ''}`}>
        <svg xmlns="http://www.w3.org/2000/svg" className="h-5 w-5" fill="none" viewBox="0 0 24 24" stroke="currentColor">
          <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M4 16l4.586-4.586a2 2 0 012.828 0L16 16m-2-2l1.586-1.586a2 2 0 012.828 0L20 14m-6-6h.01M6 20h12a2 2 0 002-2V6a2 2 0 00-2-2H6a2 2 0 00-2 2v12a2 2 0 002 2z" />
        </svg>
      </div>
    );
  }
  if (!src) {
    return (
      <div className={`animate-pulse rounded-lg bg-stone-200 ${className ?? ''}`} />
    );
  }
  return (
    <img
      src={src}
      alt={alt ?? 'adjunto'}
      className={`object-cover ${className ?? ''} ${onClick ? 'cursor-pointer' : ''}`}
      onClick={onClick}
      loading="lazy"
    />
  );
}