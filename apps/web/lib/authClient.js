'use client';

// Flag público: ¿está activada la auth? (lo setea el deploy con NEXT_PUBLIC_AUTH_ENABLED).
export const AUTH_ENABLED = process.env.NEXT_PUBLIC_AUTH_ENABLED === 'true';

import { API_BASE } from '@/lib/api';

// Fetch autenticado para endpoints de workspace (usa el apiJwt de la sesión NextAuth).
export async function authedFetch(apiJwt, path, init = {}) {
  const headers = new Headers(init.headers || {});
  if (apiJwt) headers.set('Authorization', `Bearer ${apiJwt}`);
  if (init.body && !headers.has('Content-Type')) headers.set('Content-Type', 'application/json');
  const res = await fetch(`${API_BASE}${path}`, { ...init, headers, cache: 'no-store' });
  if (!res.ok) throw new Error(`API ${res.status} en ${path}`);
  return res.status === 204 ? null : res.json();
}
