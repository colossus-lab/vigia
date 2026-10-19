// Metadatos del login según el destino (lib/ogDestino.js).
// Correr: pnpm test:og
import assert from 'node:assert/strict';
import { metadataDestino } from '../lib/ogDestino.js';

const casos = [];
const caso = (nombre, fn) => casos.push([nombre, fn]);

caso('/congreso usa el OpenGraph de la sección', () => {
  const m = metadataDestino('/congreso');
  assert.equal(m.openGraph.images[0].url, '/og/congreso');
  assert.equal(m.twitter.card, 'summary_large_image');
  assert.equal(m.openGraph.url, 'https://vigia.openarg.org/congreso');
});

caso('subpáginas y query string también', () => {
  for (const u of ['/congreso/votaciones/5', '/congreso/agenda?camara=S', '/congreso#x']) {
    assert.equal(metadataDestino(u).openGraph.images[0].url, '/og/congreso', u);
  }
});

caso('lo que no es una sección conocida cae en la genérica', () => {
  for (const u of [undefined, null, '', '/feed', '/congresoX', '/avisos', 'https://evil.example/congreso', '//evil.example/congreso']) {
    assert.deepEqual(metadataDestino(u), {}, String(u));
  }
});

caso('el callbackUrl nunca se refleja en los metadatos', () => {
  const m = metadataDestino('/congreso/<script>alert(1)</script>');
  assert.ok(!JSON.stringify(m).includes('<script>'));
});

let fallas = 0;
for (const [nombre, fn] of casos) {
  try { fn(); console.log(`  ok   ${nombre}`); }
  catch (e) { fallas++; console.log(`  FAIL ${nombre}\n       ${e.message}`); }
}
if (fallas) { console.log(`\n${fallas} fallaron`); process.exit(1); }
console.log('\ntodo ok');
