'use client';

import { Suspense, useState, useEffect } from 'react';
import Link from 'next/link';
import { useSession, signIn } from 'next-auth/react';
import { useSearchParams, useRouter } from 'next/navigation';
import { Eye } from 'lucide-react';
import { authedFetch, AUTH_ENABLED } from '@/lib/authClient';

function InviteInner() {
  const { data: session, status } = useSession();
  const params = useSearchParams();
  const router = useRouter();
  const token = params.get('token');
  const [state, setState] = useState('idle'); // idle | accepting | ok | error
  const [msg, setMsg] = useState('');
  const [accepted, setAccepted] = useState(false);

  useEffect(() => {
    if (!AUTH_ENABLED || !token) return;
    if (status === 'authenticated' && session?.apiJwt && state === 'idle') {
      setState('accepting');
      authedFetch(session.apiJwt, `/invitations/${token}/accept`, { method: 'POST' })
        .then(() => { setState('ok'); setTimeout(() => router.push('/feed'), 1200); })
        .catch((e) => { setState('error'); setMsg(String(e.message || e)); });
    }
  }, [status, session, token, state, router]);

  return (
    <div className="min-h-screen flex flex-col items-center justify-center p-4">
      <div className="flag-stripe fixed top-0 inset-x-0 z-[60]" />
      <div className="card p-8 max-w-sm w-full text-center">
        <div className="w-12 h-12 rounded-lg bg-celeste/10 border border-celeste/30 flex items-center justify-center mx-auto mb-4"><Eye size={24} className="text-celeste" /></div>
        <h1 className="text-lg font-bold text-text-primary mb-3">Invitación a Vigía</h1>
        {!token && <p className="text-[13px] text-status-red">Falta el token de invitación.</p>}
        {token && !AUTH_ENABLED && <p className="text-[13px] text-text-secondary">Auth deshabilitada en este entorno.</p>}
        {token && AUTH_ENABLED && status === 'unauthenticated' && (
          <>
            <label className="flex items-start gap-2.5 mb-4 cursor-pointer select-none text-left">
              <input
                type="checkbox"
                checked={accepted}
                onChange={(e) => setAccepted(e.target.checked)}
                className="mt-0.5 w-4 h-4 shrink-0 accent-celeste cursor-pointer"
              />
              <span className="text-[11px] text-text-tertiary leading-relaxed">
                Leí y acepto los{' '}
                <Link href="/legal" className="text-celeste hover:text-celeste-bright transition-colors">términos y la política de privacidad</Link>, y presto mi consentimiento al tratamiento de mis datos personales conforme a la Ley N° 25.326.
              </span>
            </label>
            <button onClick={() => signIn('google')} disabled={!accepted} className="w-full px-4 py-2.5 btn-celeste rounded-full text-[13px] font-bold disabled:opacity-40 disabled:cursor-not-allowed">Iniciá sesión para aceptar</button>
          </>
        )}
        {state === 'accepting' && <p className="text-[13px] text-text-secondary">Aceptando…</p>}
        {state === 'ok' && <p className="text-[13px] text-status-green">¡Listo! Redirigiendo…</p>}
        {state === 'error' && <p className="text-[13px] text-status-red">{msg}</p>}
      </div>
    </div>
  );
}

export default function InvitePage() {
  return (
    <Suspense fallback={null}>
      <InviteInner />
    </Suspense>
  );
}
