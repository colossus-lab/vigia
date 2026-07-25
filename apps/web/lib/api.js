// Cliente del API de Vigía. En el browser usa NEXT_PUBLIC_API_URL.
const BASE = process.env.NEXT_PUBLIC_API_URL || 'http://localhost:8000';

function qs(params) {
  const sp = new URLSearchParams();
  for (const [k, v] of Object.entries(params || {})) {
    if (v !== undefined && v !== null && v !== '') sp.set(k, v);
  }
  const s = sp.toString();
  return s ? `?${s}` : '';
}

// Los datos de Vigía cambian una vez por día (ingesta 03:00/08:00 ART), así que
// no tiene sentido pegarle a la API en cada navegación.
//
// `next.revalidate` solo aplica cuando el fetch corre en el server de Next; casi
// todas las páginas que usan este cliente son 'use client', así que ahí lo
// ignora y manda el `Cache-Control` que devuelve la API (ver main.py).
const REVALIDATE_SECONDS = 120;

async function get(path, { revalidate = REVALIDATE_SECONDS } = {}) {
  const res = await fetch(`${BASE}${path}`, { next: { revalidate } });
  if (!res.ok) throw new Error(`API ${res.status} en ${path}`);
  return res.json();
}

export const api = {
  listNormas: (params) => get(`/normas${qs(params)}`),
  ediciones: (params) => get(`/normas/ediciones${qs(params)}`),
  getNorma: (id) => get(`/normas/${id}`),
  search: (params) => get(`/search${qs(params)}`),
  dashboard: () => get('/stats/dashboard'),
  dnuStats: () => get('/stats/dnu'),
  series: (params) => get(`/stats/series${qs(params)}`),
  organismos: (params) => get(`/stats/organismos${qs(params)}`),
  emisores: () => get('/stats/emisores'),
  listAvisos: (params) => get(`/avisos${qs(params)}`),
  avisosRubros: (params) => get(`/avisos/rubros${qs(params)}`),
  avisosStats: (params) => get(`/avisos/stats${qs(params)}`),
};

export { BASE as API_BASE };
