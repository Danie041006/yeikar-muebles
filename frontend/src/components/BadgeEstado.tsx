import React from 'react';
import Badge from './ui/Badge';
import { estadoInfo } from '../utils/estados';

interface BadgeEstadoProps {
  dominio: 'cotizacion' | 'pedido' | 'orden' | 'etapa' | 'venta' | 'envio' | 'factura';
  estado?: string | null;
  size?: 'sm' | 'md';
  dot?: boolean;
}

export default function BadgeEstado({ dominio, estado, size = 'sm', dot = true }: BadgeEstadoProps) {
  const { tone, label } = estadoInfo(dominio, estado);
  return (
    <Badge tone={tone} size={size} dot={dot}>
      {label}
    </Badge>
  );
}