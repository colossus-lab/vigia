// BFF: inyecta el bearer de la API del lado del SERVIDOR.
//
// Antes el JWT de la API viajaba al browser (`session.apiJwt` en auth.js) y los
// componentes armaban el header a mano. Como todo lo que devuelve el callback
// `session` se serializa en GET /api/auth/session, cualquier XSS se llevaba un
// token válido por 24h y no revocable. Ahora el token vive solo en la cookie
// cifrada de NextAuth y se descifra acá, en el server.
//
// OJO — esto NO puede ser un proxy genérico. El commit 0876d34 ya removió un
// rewrite `/api-proxy/:path*` justamente porque dejaba un proxy abierto en
// Vercel: cualquiera lo usaba para pegarle a lo que quisiera desde nuestro
// origen. Por eso cada request se valida contra una ALLOWLIST explícita de
// (método, patrón) y la URL base sale de env, nunca del input.
import { getToken } from 'next-auth/jwt';

const API_BASE = (process.env.INTERNAL_API_URL || process.env.NEXT_PUBLIC_API_URL || 'http://localhost:8000').replace(/\/$/, '');
// TIENE que ser el mismo secreto con el que NextAuth cifra la cookie de sesión
// (`secret:` en auth.js, que lee esta misma env var). Si divergen, getToken()
// devuelve null en silencio, el BFF reenvía sin bearer y TODOS los usuarios
// logueados empiezan a comer 401 sin que nada falle de forma visible.
const AUTH_SECRET = process.env.AUTH_SECRET;

// Solo lo que el web realmente usa. Quedan afuera a propósito
// `/workspaces/me/leave` y `/alerts/{id}/matches`: ninguna pantalla los llama.
// Los `\d+` y `[\w-]+` acotan los parámetros dinámicos: sin eso, `/alerts/..%2f..`
// sería un camino para salirse del prefijo.
const ALLOWLIST = [
  ['GET', /^\/alerts$/],
  ['POST', /^\/alerts$/],
  ['POST', /^\/alerts\/preview$/],
  ['PATCH', /^\/alerts\/\d+$/],
  ['DELETE', /^\/alerts\/\d+$/],
  ['GET', /^\/workspaces\/me$/],
  ['POST', /^\/workspaces\/me\/onboarding$/],
  ['GET', /^\/workspaces\/me\/members$/],
  ['GET', /^\/workspaces\/me\/invitations$/],
  ['POST', /^\/workspaces\/me\/invitations$/],
  ['DELETE', /^\/workspaces\/me\/members\/\d+$/],
  // API keys. Solo alta, listado y revocación: el secreto viaja UNA vez, en la
  // respuesta del POST, y no hay endpoint que lo devuelva después ni acá ni en
  // la API.
  ['GET', /^\/api-keys$/],
  ['POST', /^\/api-keys$/],
  ['DELETE', /^\/api-keys\/\d+$/],
  ['GET', /^\/account\/export$/],
  ['DELETE', /^\/account$/],
  ['POST', /^\/invitations\/[\w-]+\/accept$/],
];

function permitido(metodo, ruta) {
  return ALLOWLIST.some(([m, re]) => m === metodo && re.test(ruta));
}

// Headers de la respuesta de la API que sí queremos reenviar. El export de datos
// baja como archivo, así que sin Content-Disposition la descarga pierde el
// nombre. Todo lo demás se descarta (no filtramos el stack del upstream).
const HEADERS_A_REENVIAR = ['content-type', 'content-disposition', 'content-length'];

async function manejar(request, ctx) {
  const { path = [] } = await ctx.params;
  const ruta = '/' + path.join('/');
  const metodo = request.method.toUpperCase();

  if (!permitido(metodo, ruta)) {
    return Response.json({ detail: 'not_allowed' }, { status: 404 });
  }

  const headers = new Headers();
  const ct = request.headers.get('content-type');
  if (ct) headers.set('content-type', ct);

  // El token sale de la cookie cifrada, no de la sesión serializada. Si no hay
  // —modo demo con AUTH_ENABLED=false— se reenvía sin bearer y la API responde
  // con su contexto ficticio, igual que antes.
  //
  // `secureCookie` es OBLIGATORIO acá y su ausencia fue el bug de la v1 de esto.
  // getToken() lo asume `false`, y de ese default salen DOS cosas: el nombre de
  // cookie que busca (`authjs.session-token`) y —porque el salt por defecto ES el
  // nombre de la cookie— la clave con la que la descifra. En HTTPS la cookie se
  // llama `__Secure-authjs.session-token`, así que sin esto no la encuentra, y
  // aunque la encontrara tampoco podría abrirla. Devuelve null EN SILENCIO: el
  // BFF reenviaba sin bearer y todo lo autenticado daba 401 sin un solo error.
  //
  // Se deduce de las cookies que llegan y no del entorno: así vale igual en
  // local (http), en las previews y en producción, sin variables que sincronizar.
  const cookies = request.cookies.getAll();
  const secureCookie = cookies.some((c) => c.name.startsWith('__Secure-authjs.session-token'));
  const hayCookieDeSesion =
    secureCookie || cookies.some((c) => c.name.startsWith('authjs.session-token'));

  const token = AUTH_SECRET
    ? await getToken({ req: request, secret: AUTH_SECRET, secureCookie })
    : null;

  if (token?.apiJwt) {
    headers.set('authorization', `Bearer ${token.apiJwt}`);
  } else if (hayCookieDeSesion) {
    // Había sesión y no pudimos leer el token: es un bug de configuración, no un
    // usuario anónimo. Sin este log el fallo es invisible — la API contesta 401
    // y parece un problema de permisos. Nunca se loguean valores de cookies.
    console.error(
      '[bff] hay cookie de sesión pero getToken() no devolvió apiJwt — ' +
        `secureCookie=${secureCookie}, secretoPresente=${Boolean(AUTH_SECRET)}, ` +
        `cookies=[${cookies.map((c) => c.name).join(', ')}]`,
    );
  }

  const url = new URL(API_BASE + ruta);
  url.search = new URL(request.url).search;

  const body = ['GET', 'HEAD'].includes(metodo) ? undefined : await request.arrayBuffer();

  let upstream;
  try {
    upstream = await fetch(url, { method: metodo, headers, body, cache: 'no-store' });
  } catch {
    return Response.json({ detail: 'upstream_unreachable' }, { status: 502 });
  }

  const salida = new Headers();
  for (const h of HEADERS_A_REENVIAR) {
    const v = upstream.headers.get(h);
    if (v) salida.set(h, v);
  }
  // Se streamea el body en vez de leerlo: /account/export baja un archivo y
  // materializarlo en memoria rompería con exports grandes.
  return new Response(upstream.body, { status: upstream.status, headers: salida });
}

export const GET = manejar;
export const POST = manejar;
export const PATCH = manejar;
export const DELETE = manejar;

export const dynamic = 'force-dynamic';
