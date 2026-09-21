import { useEffect } from 'react';
import { useToast } from '../context/ToastContext';
import { aplicarActualizacionSW, suscribirActualizacion, suscribirListoOffline } from '../utils/pwa';

export default function ActualizacionSW() {
  const toast = useToast();

  useEffect(() => {
    return suscribirActualizacion(() => {
      toast.info('Hay una versión nueva de YEIKAR', {
        label: 'Recargar',
        onClick: () => {
          void aplicarActualizacionSW();
        },
      });
    });
  }, [toast]);

  useEffect(() => {
    return suscribirListoOffline(() => {
      toast.success('YEIKAR quedó listo para usarse sin conexión');
    });
  }, [toast]);

  return null;
}
