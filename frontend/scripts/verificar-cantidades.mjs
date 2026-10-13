/**
 * Verificación del parser de cantidades "a la humana" (utils/cantidades.ts).
 *
 * El taller dicta "tres cuartos", "medio", "3/4" y un parseFloat los rompía
 * en silencio ("3/4" → 3). Este script compila el parser con esbuild (ya es
 * dependencia del frontend) y comprueba los casos críticos, incluidos los
 * teteros del colbón contra las equivalencias reales del seed.
 *
 * Ejecutar:  cd frontend && node scripts/verificar-cantidades.mjs
 */
import { execSync } from 'node:child_process';
import { fileURLToPath } from 'node:url';
import path from 'node:path';

const dirFrontend = path.resolve(path.dirname(fileURLToPath(import.meta.url)), '..');
const parser = path.join(dirFrontend, 'src/utils/cantidades.ts');
const esbuild = path.join(dirFrontend, 'node_modules/.bin/esbuild');

const js = execSync(`"${esbuild}" "${parser}" --format=esm`, {
  cwd: dirFrontend,
  encoding: 'utf8',
});
const { parseCantidadHumana, fmtCantidadHumana } = await import(
  'data:text/javascript;base64,' + Buffer.from(js).toString('base64')
);

// [entrada dictada, número esperado] — null = el parser DEBE rechazarla.
const CASOS = [
  ['1', 1], ['1,5', 1.5], ['0,75', 0.75], ['2', 2],
  ['3/4', 0.75], ['1/2', 0.5], ['3 / 4', 0.75],
  ['3/4 de litro', 0.75], ['tres cuartos de litro', 0.75], ['2 y 1/2', 2.5],
  ['medio', 0.5], ['media', 0.5], ['un cuarto', 0.25], ['tres cuartos', 0.75],
  ['dos y medio', 2.5], ['un litro y medio', 1.5],
  ['½', 0.5], ['¼', 0.25], ['¾', 0.75],
  ['un tetero', 1], ['medio tetero', 0.5], ['tres', 3], ['diez', 10],
  ['', null], ['abc', null], ['0', null], ['-1', null], ['3/0', null], ['dos tres', null],
];

let fallas = 0;
for (const [entrada, esperado] of CASOS) {
  const v = parseCantidadHumana(entrada);
  const bien = esperado === null ? v === null : v !== null && Math.abs(v - esperado) < 1e-9;
  if (!bien) {
    fallas++;
    console.error(`FALLA: ${JSON.stringify(entrada)} → ${v} (esperado ${esperado})`);
  }
}
console.log(`Parser de cantidades: ${CASOS.length - fallas}/${CASOS.length} OK`);

// Teteros del colbón: mismas equivalencias del seed (base CUÑETE, $267.000).
const FACTOR_LITRO = 1 / (5 * 3.785);
const COSTO_CUNETE = 267000;
console.log('\nSimulación teteros (colbón):');
for (const [texto, desc] of [
  ['1', 'tetero de litro'],
  ['medio', 'tetero de medio litro'],
  ['tres cuartos', '¾ de litro'],
]) {
  const litros = parseCantidadHumana(texto);
  const base = Math.round(litros * FACTOR_LITRO * 10000) / 10000;
  console.log(
    `  ${desc}: "${texto}" = ${fmtCantidadHumana(litros)} L → ${base} cuñete ≈ ` +
    `$${Math.round(base * COSTO_CUNETE).toLocaleString('es-CO')}`,
  );
}

process.exit(fallas > 0 ? 1 : 0);
