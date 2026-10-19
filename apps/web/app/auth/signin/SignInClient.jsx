'use client';

import { Suspense, useState } from 'react';
import Link from 'next/link';
import { signIn } from 'next-auth/react';
import { useSearchParams } from 'next/navigation';
import { Eye, Bell, Users, History, ArrowLeft } from 'lucide-react';
import { AUTH_ENABLED } from '@/lib/authClient';
import FadeIn from '@/components/FadeIn';

const BENEFITS = [
  { icon: Bell, text: 'Alertas por keyword y sector, con digest por email' },
  { icon: Users, text: 'Un workspace para tu equipo — invitá miembros' },
  { icon: History, text: 'Monitoreo persistente: nada se pierde entre sesiones' },
];

function GoogleMark() {
  return (
    <svg width="15" height="15" viewBox="0 0 24 24" aria-hidden>
      <path fill="#4285F4" d="M22.56 12.25c0-.78-.07-1.53-.2-2.25H12v4.26h5.92a5.06 5.06 0 0 1-2.2 3.32v2.77h3.57c2.08-1.92 3.27-4.74 3.27-8.1z" />
      <path fill="#34A853" d="M12 23c2.97 0 5.46-.98 7.28-2.66l-3.57-2.77c-.98.66-2.23 1.06-3.71 1.06-2.86 0-5.29-1.93-6.16-4.53H2.18v2.84A11 11 0 0 0 12 23z" />
      <path fill="#FBBC05" d="M5.84 14.1A6.6 6.6 0 0 1 5.5 12c0-.73.13-1.44.34-2.1V7.06H2.18a11 11 0 0 0 0 9.88l3.66-2.84z" />
      <path fill="#EA4335" d="M12 5.38c1.62 0 3.06.56 4.21 1.64l3.15-3.15A11 11 0 0 0 2.18 7.06l3.66 2.84c.87-2.6 3.3-4.52 6.16-4.52z" />
    </svg>
  );
}

function SignInInner() {
  const params = useSearchParams();
  const callbackUrl = params.get('callbackUrl') || '/feed';
  const [accepted, setAccepted] = useState(false);

  return (
    <div className="min-h-screen flex flex-col items-center justify-center p-4">
      <div className="flag-stripe fixed top-0 inset-x-0 z-[60]" />

      <FadeIn className="w-full max-w-sm">
        <div className="card p-8 relative overflow-hidden">
          <div className="absolute inset-0 pointer-events-none" style={{ background: 'radial-gradient(ellipse 80% 60% at 50% -10%, rgba(116,172,223,0.10), transparent 60%)' }} />

          <div className="relative">
            <div className="flex items-center gap-2.5 mb-7">
              <div className="w-10 h-10 rounded-lg bg-celeste/10 border border-celeste/30 flex items-center justify-center">
                <Eye size={20} className="text-celeste" />
              </div>
              <div>
                <p className="text-[14px] font-bold text-text-primary leading-none" style={{ fontFamily: 'var(--font-display)' }}>VIGÍA</p>
                <p className="text-[8px] text-text-tertiary uppercase tracking-[0.18em] font-mono mt-0.5">por OpenArg</p>
              </div>
            </div>

            <p className="eyebrow mb-2"><span className="eyebrow-num">ACCESO</span></p>
            <h1 className="display-section text-text-primary mb-6">Entrá a <em>Vigía.</em></h1>

            <ul className="space-y-3 mb-7">
              {BENEFITS.map(({ icon: Icon, text }) => (
                <li key={text} className="flex items-start gap-2.5 text-[12px] text-text-secondary leading-relaxed">
                  <Icon size={13} className="text-celeste shrink-0 mt-0.5" />
                  {text}
                </li>
              ))}
            </ul>

            {AUTH_ENABLED ? (
              <>
                <label className="flex items-start gap-2.5 mb-4 cursor-pointer select-none">
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
                <button
                  onClick={() => signIn('google', { callbackUrl })}
                  disabled={!accepted}
                  className="w-full flex items-center justify-center gap-2.5 px-4 py-2.5 bg-text-primary text-navy-950 rounded-full text-[13px] font-bold hover:bg-white transition-colors disabled:opacity-40 disabled:cursor-not-allowed disabled:hover:bg-text-primary"
                >
                  <GoogleMark /> Continuar con Google
                </button>
              </>
            ) : (
              <div className="text-[12px] text-text-secondary bg-bg-secondary border border-border-light rounded-lg p-3 leading-relaxed">
                <span className="tint-amber border rounded-full px-2 py-0.5 text-[10px] font-semibold mr-1.5">demo</span>
                El login se activa configurando Google OAuth
                (<code className="font-mono text-[11px]">AUTH_GOOGLE_ID/SECRET</code> + <code className="font-mono text-[11px]">AUTH_SECRET</code>).
              </div>
            )}

            <div className="flex items-center justify-between mt-6 pt-5 border-t border-border-light">
              <Link href="/" className="flex items-center gap-1 text-[11px] text-text-tertiary hover:text-text-primary transition-colors">
                <ArrowLeft size={11} /> Volver al inicio
              </Link>
              <span className="text-[11px] text-text-tertiary">Cuenta gratuita</span>
            </div>
          </div>
        </div>
      </FadeIn>

      <p className="text-[10px] text-text-tertiary font-mono mt-6">Datos públicos verificables · Colossus Lab · BA</p>
    </div>
  );
}

export default function SignInClient() {
  return (
    <Suspense fallback={null}>
      <SignInInner />
    </Suspense>
  );
}
