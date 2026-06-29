/** @type {import('next').NextConfig} */

// API pública que consume el cliente (whitelist de connect-src del CSP).
// trim() es load-bearing: un \n colado en la env var (p.ej. cargada por CLI)
// invalida el header y tira 500 en TODAS las rutas dinámicas (Node no
// serializa headers con newlines) — pasó en prod el 2026-06-11.
const API_ORIGIN = (process.env.NEXT_PUBLIC_API_URL || 'https://vigia-api.openarg.org').trim();

// CSP en Report-Only primero: no rompe nada (solo reporta), permite endurecer
// script-src con nonces más adelante sin romper la hidratación de Next.
const csp = [
  "default-src 'self'",
  "base-uri 'self'",
  "frame-ancestors 'none'",
  "form-action 'self'",
  "object-src 'none'",
  "img-src 'self' data: https:",
  "style-src 'self' 'unsafe-inline' https://fonts.googleapis.com",
  "font-src 'self' https://fonts.gstatic.com",
  "script-src 'self' 'unsafe-inline'",
  `connect-src 'self' ${API_ORIGIN}`,
].join('; ');

const securityHeaders = [
  { key: 'X-Content-Type-Options', value: 'nosniff' },
  { key: 'X-Frame-Options', value: 'DENY' },
  { key: 'Referrer-Policy', value: 'strict-origin-when-cross-origin' },
  {
    key: 'Permissions-Policy',
    value: 'camera=(), microphone=(), geolocation=(), browsing-topics=()',
  },
  { key: 'Content-Security-Policy-Report-Only', value: csp },
];

const nextConfig = {
  reactStrictMode: true,
  poweredByHeader: false,
  async headers() {
    return [{ source: '/:path*', headers: securityHeaders }];
  },
};

export default nextConfig;
