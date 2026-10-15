// Cifrado local del modo offline (AES-GCM + PBKDF2 con WebCrypto).
//
// Diseño de llaves:
//   - `claveDispositivo` (AES-256 aleatoria): cifra TODO lo que se guarda en
//     IndexedDB (espejo, outbox y sesión cacheada).
//   - Si el usuario configura un PIN, la claveDispositivo se guarda
//     "envuelta" (cifrada con una llave derivada del PIN); el texto plano de
//     la clave se borra. Desbloquear = derivar del PIN y desenvolver.
//   - Sin PIN configurado la clave vive clara en IndexedDB: los datos siguen
//     cifrados (no son legibles a simple vista) y el PIN es la recomendación
//     para proteger equipos compartidos.
//
// La clave activa vive SOLO en memoria: al recargar la app protegida hay que
// desbloquear con el PIN para leer o escribir datos locales.

const TEXTO = new TextEncoder();
const TEXTO_DEC = new TextDecoder();

export const PBKDF2_ITERACIONES = 300_000;

export interface BlobCifrado {
  v: 1;
  iv: string;
  dato: string;
}

export interface CredencialPin {
  salt: string;
  verificador: string;
  iteraciones: number;
}

let claveActiva: CryptoKey | null = null;

export function cifradoDisponible(): boolean {
  return typeof crypto !== 'undefined' && !!crypto.subtle;
}

export function hayClave(): boolean {
  return claveActiva !== null;
}

export function activarClave(clave: CryptoKey): void {
  claveActiva = clave;
}

export function bloquearClave(): void {
  claveActiva = null;
}

export function claveActual(): CryptoKey {
  if (!claveActiva) throw new Error('La clave local está bloqueada.');
  return claveActiva;
}

export function uuid(): string {
  if (typeof crypto.randomUUID === 'function') return crypto.randomUUID();
  const bytes = crypto.getRandomValues(new Uint8Array(16));
  bytes[6] = (bytes[6] & 0x0f) | 0x40;
  bytes[8] = (bytes[8] & 0x3f) | 0x80;
  const hex = Array.from(bytes, (b) => b.toString(16).padStart(2, '0')).join('');
  return `${hex.slice(0, 8)}-${hex.slice(8, 12)}-${hex.slice(12, 16)}-${hex.slice(16, 20)}-${hex.slice(20)}`;
}

function bytesAB64(bytes: Uint8Array<ArrayBuffer> | ArrayBuffer): string {
  const vista = bytes instanceof Uint8Array ? bytes : new Uint8Array(bytes as ArrayBuffer);
  let binario = '';
  const bloque = 0x8000;
  for (let i = 0; i < vista.length; i += bloque) {
    binario += String.fromCharCode(...vista.subarray(i, i + bloque));
  }
  return btoa(binario);
}

function b64ABytes(texto: string): Uint8Array<ArrayBuffer> {
  const binario = atob(texto);
  const bytes = new Uint8Array(binario.length);
  for (let i = 0; i < binario.length; i += 1) bytes[i] = binario.charCodeAt(i);
  return bytes;
}

async function derivarDesdePin(pin: string, salt: Uint8Array<ArrayBuffer>, iteraciones: number) {
  const material = await crypto.subtle.importKey('raw', TEXTO.encode(pin), 'PBKDF2', false, ['deriveBits']);
  const bits = await crypto.subtle.deriveBits(
    { name: 'PBKDF2', salt, iterations: iteraciones, hash: 'SHA-256' },
    material,
    512,
  );
  const bytes = new Uint8Array(bits);
  const clave = await crypto.subtle.importKey(
    'raw',
    bytes.slice(32),
    { name: 'AES-GCM' },
    false,
    ['encrypt', 'decrypt'],
  );
  return { verificador: bytesAB64(bytes.slice(0, 32)), clave };
}

export async function crearCredencialPin(pin: string) {
  const salt = crypto.getRandomValues(new Uint8Array(16));
  const { verificador, clave } = await derivarDesdePin(pin, salt, PBKDF2_ITERACIONES);
  const credencial: CredencialPin = { salt: bytesAB64(salt), verificador, iteraciones: PBKDF2_ITERACIONES };
  return { credencial, clave };
}

export async function verificarPin(pin: string, credencial: CredencialPin): Promise<CryptoKey | null> {
  const { verificador, clave } = await derivarDesdePin(pin, b64ABytes(credencial.salt), credencial.iteraciones);
  if (verificador !== credencial.verificador) return null;
  return clave;
}

export async function generarClaveDispositivo(): Promise<CryptoKey> {
  return crypto.subtle.generateKey({ name: 'AES-GCM', length: 256 }, true, ['encrypt', 'decrypt']);
}

export async function exportarClave(clave: CryptoKey): Promise<string> {
  return bytesAB64(await crypto.subtle.exportKey('raw', clave));
}

export async function importarClave(claveB64: string): Promise<CryptoKey> {
  return crypto.subtle.importKey('raw', b64ABytes(claveB64), { name: 'AES-GCM' }, true, ['encrypt', 'decrypt']);
}

export async function cifrarJson(dato: unknown, clave?: CryptoKey): Promise<BlobCifrado> {
  const iv = crypto.getRandomValues(new Uint8Array(12));
  const plano = TEXTO.encode(JSON.stringify(dato));
  const cifrado = await crypto.subtle.encrypt({ name: 'AES-GCM', iv }, clave ?? claveActual(), plano);
  return { v: 1, iv: bytesAB64(iv), dato: bytesAB64(cifrado) };
}

export async function descifrarJson<T>(blob: BlobCifrado | null | undefined, clave?: CryptoKey): Promise<T | null> {
  if (!blob) return null;
  try {
    const plano = await crypto.subtle.decrypt(
      { name: 'AES-GCM', iv: b64ABytes(blob.iv) },
      clave ?? claveActual(),
      b64ABytes(blob.dato),
    );
    return JSON.parse(TEXTO_DEC.decode(plano)) as T;
  } catch {
    return null;
  }
}
