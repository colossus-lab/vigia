/* Plural castellano de los labels de tipo de norma.

   Módulo aparte (y no una función suelta en el componente) para que se pueda
   testear sin browser: `pnpm test:plural`, igual que el BFF. */

/* Siglas: invariables en plural ("3 dnu", no "3 dnus"). */
const TIPOS_INVARIABLES = new Set(['DNU']);

/**
 * Plural del label ya en minúscula de un tipo.
 *
 * La regla anterior era `+ 's'` salvo LEY, y escupía "35 resolucións · 7
 * disposicións" en el header de cada edición de /boletines. Los terminados en
 * -ión hacen -iones y pierden la tilde.
 */
export function pluralizarTipo(tipo, label, n) {
  if (n === 1 || TIPOS_INVARIABLES.has(tipo)) return label;
  if (/ión$/.test(label)) return label.replace(/ión$/, 'iones');
  // Vocal átona -> +s (decreto, proyecto, consulta); consonante o -y -> +es (ley).
  return /[aeiou]$/.test(label) ? `${label}s` : `${label}es`;
}
