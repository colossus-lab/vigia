/* Metadatos para compartir una sección con login.

   Un bot (WhatsApp, X, Slack…) que sigue un link a una sección gateada recibe
   el 307 de proxy.js y termina en /auth/signin?callbackUrl=<sección>. Sin esto
   la preview mostraba el OpenGraph genérico del login. Con esto, el login
   arma sus metadatos según el destino.

   `callbackUrl` viene del usuario: solo se usa para ELEGIR una entrada fija
   de este mapa, nunca se refleja en el HTML. */

const SECCIONES = [
  {
    prefijo: '/congreso',
    title: 'Congreso — Senado y Diputados',
    description:
      'Votaciones, agenda de comisiones, sesiones y legisladores del Senado y Diputados, cruzados con cada proyecto. Inteligencia legislativa por OpenArg.',
    url: 'https://vigia.openarg.org/congreso',
    image: '/og/congreso',
    alt: 'Vigía — Congreso: votaciones, agenda de comisiones y sesiones del Senado y Diputados.',
  },
];

function seccionDe(callbackUrl) {
  if (typeof callbackUrl !== 'string' || !callbackUrl.startsWith('/')) return null;
  const path = callbackUrl.split(/[?#]/)[0];
  return SECCIONES.find((s) => path === s.prefijo || path.startsWith(`${s.prefijo}/`)) || null;
}

/** Metadata de Next para el login según adónde iba el usuario (o {} = la genérica). */
export function metadataDestino(callbackUrl) {
  const s = seccionDe(callbackUrl);
  if (!s) return {};
  const images = [{ url: s.image, width: 1200, height: 630, alt: s.alt }];
  return {
    title: s.title,
    description: s.description,
    openGraph: { title: s.title, description: s.description, url: s.url, type: 'website', images },
    twitter: { card: 'summary_large_image', title: s.title, description: s.description, images },
  };
}
