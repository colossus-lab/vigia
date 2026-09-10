/**
 * Regresión del plural de los tipos de norma.
 *
 * El header de cada edición en /boletines mostraba "35 resolucións · 7
 * disposicións": la regla era `+ 's'` para todo salvo LEY. Los terminados en
 * -ión hacen -iones y pierden la tilde, y las siglas no se pluralizan.
 *
 * Se testea acá y no en el componente porque el listado se pide client-side y
 * el origen local no está en API_CORS_ORIGINS: la preview nunca renderiza una
 * edición real, así que el bug no se ve en dev.
 *
 *   node apps/web/scripts/test-plural.mjs
 */
import { pluralizarTipo } from '../lib/plural.js';
import { TIPOS_NORMA } from '../lib/constants.js';

let fallos = 0;
function afirmar(condicion, descripcion) {
  console.log(`  ${condicion ? 'ok  ' : 'FALLA'} ${descripcion}`);
  if (!condicion) fallos++;
}

const plural = (tipo, n) =>
  pluralizarTipo(tipo, (TIPOS_NORMA[tipo]?.label || tipo).toLowerCase(), n);

// --- el bug reportado ------------------------------------------------------
afirmar(plural('RESOLUCION', 35) === 'resoluciones', 'resolución -> resoluciones (no "resolucións")');
afirmar(plural('DISPOSICION', 7) === 'disposiciones', 'disposición -> disposiciones');
afirmar(plural('COMUNICACION', 4) === 'comunicaciones', 'comunicación -> comunicaciones');

// --- lo que ya andaba, que no se rompa -------------------------------------
afirmar(plural('DECRETO', 6) === 'decretos', 'decreto -> decretos');
afirmar(plural('LEY', 3) === 'leyes', 'ley -> leyes');
afirmar(plural('PROYECTO', 2) === 'proyectos', 'proyecto -> proyectos');
afirmar(plural('CONSULTA', 9) === 'consultas', 'consulta -> consultas');

// --- siglas: invariables ---------------------------------------------------
afirmar(plural('DNU', 3) === 'dnu', 'DNU no se pluraliza ("3 dnu")');

// --- singular: nunca se toca ----------------------------------------------
for (const tipo of Object.keys(TIPOS_NORMA)) {
  const esperado = TIPOS_NORMA[tipo].label.toLowerCase();
  if (plural(tipo, 1) !== esperado) {
    afirmar(false, `singular intacto para ${tipo}`);
  }
}
afirmar(true, 'en singular ningún tipo se pluraliza');

// --- tipo desconocido: no explota -----------------------------------------
afirmar(pluralizarTipo('NUEVO', 'nuevo', 2) === 'nuevos', 'un tipo que la API sume todavía pluraliza');

console.log(fallos ? `\n${fallos} fallo(s)` : '\ntodo ok');
process.exit(fallos ? 1 : 0);
