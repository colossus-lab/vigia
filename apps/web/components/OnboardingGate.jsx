'use client';

import { useEffect } from 'react';
import { useSession } from 'next-auth/react';
import { useRouter } from 'next/navigation';
import { AUTH_ENABLED } from '@/lib/authClient';

/**
 * Empuja al onboarding a los usuarios nuevos. El signin manda directo al feed,
 * así que sin esto el 76% nunca pasa por /onboarding (y no llega a crear una
 * alerta, que es el gancho de retención). Redirige a /onboarding si el usuario
 * está autenticado, no onboardeó, y no marcó "saltar por ahora" (localStorage,
 * misma key que OnboardingBanner). Es no-bloqueante: /onboarding ofrece saltar.
 */
const KEY = 'vigia_onboarding_dismissed';

export default function OnboardingGate() {
  const { data: session, status } = useSession();
  const router = useRouter();

  useEffect(() => {
    if (!AUTH_ENABLED || status !== 'authenticated') return;
    const ws = session?.workspace;
    if (!ws || ws.onboarded) return;
    let dismissed = false;
    try { dismissed = localStorage.getItem(KEY) === '1'; } catch { /* noop */ }
    if (!dismissed) router.replace('/onboarding');
  }, [status, session, router]);

  return null;
}
