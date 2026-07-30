'use client';

// Flag público: ¿está activada la auth? (lo setea el deploy con NEXT_PUBLIC_AUTH_ENABLED).
export const AUTH_ENABLED = process.env.NEXT_PUBLIC_AUTH_ENABLED === 'true';

// Prefijo del BFF: el bearer lo agrega el route handler del server
// (app/api/vigia/[...path]/route.js), así que el token nunca llega al browser.
// Es same-origin, o sea que además no pasa por CORS.
export const BFF_BASE = '/api/vigia';

// Fetch autenticado para endpoints de workspace.
//
// Ya NO recibe el jwt: antes lo sacaban de useSession(), que era justamente el
// problema. La firma cambió de (apiJwt, path, init) a (path, init).
export async function authedFetch(path, init = {}) {
  const headers = new Headers(init.headers || {});
  if (init.body && !headers.has('Content-Type')) headers.set('Content-Type', 'application/json');
  const res = await fetch(`${BFF_BASE}${path}`, { ...init, headers, cache: 'no-store' });
  // Se conserva textual el mensaje de error: las pantallas hacen catch y
  // muestran e.message, así que cambiarlo alteraría lo que ve el usuario.
  if (!res.ok) throw new Error(`API ${res.status} en ${path}`);
  return res.status === 204 ? null : res.json();
}
