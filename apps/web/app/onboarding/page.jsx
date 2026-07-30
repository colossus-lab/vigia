'use client';

import { useState } from 'react';
import { useSession } from 'next-auth/react';
import { useRouter } from 'next/navigation';
import { Eye, Check, Bell } from 'lucide-react';
import { SECTORES } from '@/lib/constants';
import { authedFetch } from '@/lib/authClient';

const DISMISS_KEY = 'vigia_onboarding_dismissed';

export default function OnboardingPage() {
  const { data: session } = useSession();
  const router = useRouter();
  const [name, setName] = useState('');
  const [selected, setSelected] = useState([]);
  const [saving, setSaving] = useState(false);
  const [step, setStep] = useState('form'); // 'form' | 'suggest'
  const [preview, setPreview] = useState(null); // { count_30d } | null
  const [creating, setCreating] = useState(false);

  const toggle = (s) => setSelected((prev) => (prev.includes(s) ? prev.filter((x) => x !== s) : [...prev, s]));

  const markDismissed = () => {
    // El flag `onboarded` del JWT queda stale hasta el próximo sync; marcamos el
    // dismiss para que OnboardingBanner/OnboardingGate no reaparezcan/redirijan.
    try { localStorage.setItem(DISMISS_KEY, '1'); } catch { /* noop */ }
  };

  const skip = () => { markDismissed(); router.push('/feed'); };

  const submit = async () => {
    setSaving(true);
    try {
      await authedFetch(session?.apiJwt, '/workspaces/me/onboarding', {
        method: 'POST',
        body: JSON.stringify({ name: name || undefined, sectores_interes: selected }),
      });
      markDismissed();
      // Sin sectores no hay nada que sugerir monitorear → directo al feed.
      if (!selected.length) { router.push('/feed'); return; }
      // Convertir el interés en una alerta: mostramos la sugerencia con el
      // volumen esperado (preview) antes de crearla con un clic.
      setStep('suggest');
      try {
        const p = await authedFetch(session?.apiJwt, '/alerts/preview', {
          method: 'POST',
          body: JSON.stringify({ keywords: [], sectores: selected }),
        });
        setPreview(p);
      } catch { setPreview(null); }
    } catch {
      setSaving(false);
    }
  };

  const createAlerta = async () => {
    setCreating(true);
    try {
      await authedFetch(session?.apiJwt, '/alerts', {
        method: 'POST',
        body: JSON.stringify({ keywords: [], sectores: selected }),
      });
      router.push('/alerts');
    } catch {
      setCreating(false);
    }
  };

  return (
    <div className="min-h-screen flex flex-col items-center justify-center p-4">
      <div className="flag-stripe fixed top-0 inset-x-0 z-[60]" />

      {step === 'form' && (
        <div className="card p-8 max-w-lg w-full">
          <div className="flex items-center gap-2.5 mb-6">
            <div className="w-9 h-9 rounded-lg bg-celeste/10 border border-celeste/30 flex items-center justify-center">
              <Eye size={18} className="text-celeste" />
            </div>
            <div>
              <h1 className="text-base font-bold text-text-primary">Configurá tu workspace</h1>
              <p className="text-[12px] text-text-tertiary">Personalizá Vigía para tu organización</p>
            </div>
          </div>

          <label className="text-[10px] font-semibold text-text-tertiary uppercase tracking-wide mb-1 block">Nombre del workspace</label>
          <input
            value={name}
            onChange={(e) => setName(e.target.value)}
            placeholder={session?.workspace?.name || 'Mi organización'}
            className="w-full bg-bg-primary border border-border-light rounded-lg px-3 py-2 text-[13px] mb-5 focus:outline-none focus:border-inst-accent"
          />

          <label className="text-[10px] font-semibold text-text-tertiary uppercase tracking-wide mb-2 block">Sectores de interés</label>
          <div className="flex flex-wrap gap-2 mb-6">
            {SECTORES.map((s) => (
              <button
                key={s}
                onClick={() => toggle(s)}
                className={`px-2.5 py-1 rounded-full text-[11px] font-medium border transition-colors flex items-center gap-1 ${
                  selected.includes(s)
                    ? 'bg-celeste/10 text-celeste-bright border-celeste/40'
                    : 'bg-bg-primary text-text-secondary border-border-light hover:bg-bg-tertiary'
                }`}
              >
                {selected.includes(s) && <Check size={11} />} {s}
              </button>
            ))}
          </div>

          <button
            onClick={submit}
            disabled={saving}
            className="w-full px-4 py-2.5 btn-celeste rounded-full text-[13px] font-bold disabled:opacity-50"
          >
            {saving ? 'Guardando…' : 'Continuar'}
          </button>
          <button
            onClick={skip}
            disabled={saving}
            className="w-full mt-2 px-4 py-2 text-text-tertiary hover:text-text-secondary text-[12px] font-medium transition-colors disabled:opacity-50"
          >
            Saltar por ahora
          </button>
        </div>
      )}

      {step === 'suggest' && (
        <div className="card p-8 max-w-lg w-full">
          <div className="flex items-center gap-2.5 mb-5">
            <div className="w-9 h-9 rounded-lg bg-celeste/10 border border-celeste/30 flex items-center justify-center">
              <Bell size={18} className="text-celeste" />
            </div>
            <div>
              <h1 className="text-base font-bold text-text-primary">Creá tu primera alerta</h1>
              <p className="text-[12px] text-text-tertiary">Te avisamos por email cuando salga algo nuevo</p>
            </div>
          </div>

          <p className="text-[13px] text-text-secondary leading-relaxed mb-4">
            Monitoreá todo lo que se publique en{' '}
            <span className="text-text-primary font-semibold">{selected.join(', ')}</span>.
          </p>

          <div className="flex flex-wrap gap-2 mb-4">
            {selected.map((s) => (
              <span key={s} className="px-2.5 py-1 rounded-full text-[11px] font-medium border bg-celeste/10 text-celeste-bright border-celeste/40">
                {s}
              </span>
            ))}
          </div>

          {preview && (
            <p className="text-[11px] text-text-tertiary font-mono mb-5">
              ≈ {preview.count_30d.toLocaleString('es-AR')} normas en estos sectores en los últimos 30 días
            </p>
          )}

          <button
            onClick={createAlerta}
            disabled={creating}
            className="w-full px-4 py-2.5 btn-celeste rounded-full text-[13px] font-bold disabled:opacity-50"
          >
            {creating ? 'Creando…' : 'Crear alerta'}
          </button>
          <button
            onClick={() => router.push('/feed')}
            disabled={creating}
            className="w-full mt-2 px-4 py-2 text-text-tertiary hover:text-text-secondary text-[12px] font-medium transition-colors disabled:opacity-50"
          >
            Ahora no
          </button>
        </div>
      )}
    </div>
  );
}
