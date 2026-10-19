/**
 * Next 16 proxy (ex middleware). Con AUTH_ENABLED=true protege TODA la
 * plataforma: solo la landing (/) y /auth/* son públicas; cualquier vista de
 * datos requiere sesión. En modo demo (sin credenciales OAuth), passthrough.
 */
import { NextResponse } from 'next/server';
import { AUTH_ENABLED, auth } from '@/auth';

const PROTECTED_PREFIXES = [
  '/feed',
  '/dashboard',
  '/search',
  '/alerts',
  '/dnu',
  '/norma',
  '/avisos',
  '/congreso',
  '/onboarding',
  '/settings',
];

const passthrough = () => NextResponse.next();

const gated = auth((req) => {
  const path = req.nextUrl.pathname;
  const isLoggedIn = !!req.auth;
  const isProtected = PROTECTED_PREFIXES.some((p) => path === p || path.startsWith(`${p}/`));
  if (isProtected && !isLoggedIn) {
    const signin = new URL('/auth/signin', req.url);
    signin.searchParams.set('callbackUrl', path);
    return NextResponse.redirect(signin);
  }
  return NextResponse.next();
});

export default AUTH_ENABLED ? gated : passthrough;

export const config = {
  matcher: ['/((?!api|_next/static|_next/image|favicon.ico|.*\\..*).*)'],
};
