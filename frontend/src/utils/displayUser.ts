/** Nombre real para auditoría/UI, con fallback al login.
 *
 * Fuente única en frontend: todo "quién registró" debe usar esto,
 * nunca `nombre_usuario` directo.
 */
interface ConNombre {
  nombre?: string | null;
  nombre_usuario?: string | null;
  creador_nombre?: string | null;
}

export function nombreVisible(u: ConNombre | null | undefined): string | null {
  if (!u) return null;
  return u.nombre || u.nombre_usuario || u.creador_nombre || null;
}

/** Variante con fallback para render directo. */
export function nombreVisibleO(
  u: ConNombre | null | undefined,
  fallback = '—',
): string {
  return nombreVisible(u) ?? fallback;
}
