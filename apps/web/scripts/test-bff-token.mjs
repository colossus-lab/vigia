/**
 * Regresión del bug que rompió el BFF en producción (commit 40e1071).
 *
 * `getToken()` asume `secureCookie: false`, y de ese default salen DOS cosas: el
 * nombre de cookie que busca y —porque el salt por defecto ES el nombre de la
 * cookie— la clave con la que la descifra. En HTTPS la cookie se llama
 * `__Secure-authjs.session-token`, así que sin `secureCookie: true` devuelve
 * null EN SILENCIO y el BFF reenvía sin bearer: todo lo autenticado da 401.
 *
 * Esto cifra una cookie igual que NextAuth y verifica que se pueda abrir. Usa la
 * criptografía real de @auth/core, así que no depende de un browser ni de una
 * sesión de Google — que es exactamente lo que faltaba cuando el bug pasó.
 *
 *   node apps/web/scripts/test-bff-token.mjs
 */
// Vía next-auth/jwt y no @auth/core: es el mismo módulo reexportado, pero
// next-auth sí es dependencia directa (@auth/core es transitiva y pnpm no la
// expone). Es además exactamente el import que usa el handler.
import { encode, getToken } from 'next-auth/jwt';

const SECRET = 'x'.repeat(64);
const SEGURA = '__Secure-authjs.session-token';
const LLANA = 'authjs.session-token';

const pedido = (nombre, valor) =>
  new Request('https://ejemplo.test/api/vigia/alerts', {
    headers: { cookie: `${nombre}=${valor}` },
  });

let fallos = 0;
function afirmar(condicion, descripcion) {
  console.log(`  ${condicion ? 'ok  ' : 'FALLA'} ${descripcion}`);
  if (!condicion) fallos++;
}

// --- HTTPS: el escenario de producción y de las previews -------------------
const cookieSegura = await encode({
  token: { apiJwt: 'JWT-API', workspaceId: 42 },
  secret: SECRET,
  salt: SEGURA,
});

const conFix = await getToken({
  req: pedido(SEGURA, cookieSegura),
  secret: SECRET,
  secureCookie: true,
});
afirmar(conFix?.apiJwt === 'JWT-API', 'con secureCookie:true se recupera el apiJwt');

const sinFix = await getToken({ req: pedido(SEGURA, cookieSegura), secret: SECRET });
afirmar(
  sinFix?.apiJwt === undefined,
  'sin secureCookie devuelve null (el bug, documentado acá para que se note si vuelve)',
);

// --- HTTP: dev local -------------------------------------------------------
const cookieLlana = await encode({
  token: { apiJwt: 'JWT-LOCAL' },
  secret: SECRET,
  salt: LLANA,
});
const enDev = await getToken({
  req: pedido(LLANA, cookieLlana),
  secret: SECRET,
  secureCookie: false,
});
afirmar(enDev?.apiJwt === 'JWT-LOCAL', 'en dev local (http, sin prefijo) sigue funcionando');

// --- secreto equivocado ----------------------------------------------------
const otroSecreto = await getToken({
  req: pedido(SEGURA, cookieSegura),
  secret: 'y'.repeat(64),
  secureCookie: true,
});
afirmar(otroSecreto === null, 'con otro secreto no abre la cookie');

console.log(fallos ? `\n${fallos} fallo(s)` : '\ntodo ok');
process.exit(fallos ? 1 : 0);
