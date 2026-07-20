'use client';

import { useState } from 'react';
import Link from 'next/link';
import { Eye, Copy, Check, ArrowLeft, Clock } from 'lucide-react';
import FadeIn from '@/components/FadeIn';

const CBU = '0070011520000022781626';
const CBU_PRETTY = '0070 0115 2000 0022 7816 26';

const TIERS = [
  { k: 'Adherente', amt: '$3.000', cad: 'Aporte único' },
  { k: 'Colaborador/a', amt: '$5.000', sub: '/ mes', cad: 'Aporte mensual', feat: true },
  { k: 'Patrocinador/a', amt: '$20.000', cad: 'Aporte único mayor' },
];

export default function ApoyarPage() {
  const [copied, setCopied] = useState(false);

  const copyCbu = async () => {
    try {
      await navigator.clipboard.writeText(CBU);
      setCopied(true);
      setTimeout(() => setCopied(false), 2200);
    } catch { /* noop */ }
  };

  return (
    <div className="min-h-screen">
      <div className="flag-stripe fixed top-0 inset-x-0 z-[60]" />

      <div className="max-w-2xl mx-auto px-5 py-14">
        <FadeIn>
          <div className="flex items-center justify-between mb-10">
            <div className="flex items-center gap-2.5">
              <div className="w-9 h-9 rounded-lg bg-celeste/10 border border-celeste/30 flex items-center justify-center">
                <Eye size={18} className="text-celeste" />
              </div>
              <div>
                <p className="text-[13px] font-bold text-text-primary leading-none" style={{ fontFamily: 'var(--font-display)' }}>VIGÍA</p>
                <p className="text-[8px] text-text-tertiary uppercase tracking-[0.18em] font-mono mt-0.5">por OpenArg</p>
              </div>
            </div>
            <Link href="/feed" className="flex items-center gap-1 text-[11px] text-text-tertiary hover:text-text-primary transition-colors">
              <ArrowLeft size={11} /> Volver
            </Link>
          </div>
        </FadeIn>

        <FadeIn delay={60}>
          <p className="eyebrow mb-3"><span className="eyebrow-num">VIGÍA / APOYAR</span></p>
          <h1 className="display-section text-text-primary mb-5">Vigía es y seguirá siendo <em>gratis.</em></h1>
          <p className="text-[15px] text-text-secondary leading-relaxed mb-4">
            Monitoreamos el Boletín Oficial, ambas cámaras del Congreso, el BCRA y las consultas públicas —
            lo indexamos, lo resumimos con IA y te avisamos cuando cambia algo que te importa. Datos públicos,
            para cualquiera, sin muro de pago ni venta de tus datos.
          </p>
          <p className="text-[13px] text-text-tertiary leading-relaxed mb-9">
            Sostenemos Vigía con los aportes de quienes lo usan. Si te sirve y podés, bancá el proyecto:
            cada aporte va a los servidores, la ingesta diaria de datos y a mantenerlo independiente.
          </p>
        </FadeIn>

        <FadeIn delay={120}>
          <div className="grid grid-cols-1 sm:grid-cols-3 gap-3 mb-4">
            {TIERS.map((t) => (
              <div
                key={t.k}
                className={`rounded-2xl p-5 flex flex-col gap-1 border ${t.feat ? 'border-celeste/40 bg-bg-tertiary' : 'border-border-light bg-bg-secondary'}`}
              >
                <span className="font-mono text-[10px] uppercase tracking-[0.14em] text-text-tertiary">{t.k}</span>
                <span className="font-mono text-[1.9rem] font-medium text-text-primary leading-tight">
                  {t.amt}{t.sub && <span className="text-[0.85rem] text-text-tertiary"> {t.sub}</span>}
                </span>
                <span className="text-[12px] text-text-secondary mb-3">{t.cad}</span>
                <span className="mt-auto inline-flex items-center justify-center gap-1.5 px-3 py-2 rounded-full text-[11px] font-medium border border-border-light text-text-tertiary cursor-default">
                  <Clock size={12} /> MercadoPago · próximamente
                </span>
              </div>
            ))}
          </div>
          <p className="text-[11px] text-text-tertiary font-mono mb-9">
            Los aportes por MercadoPago (único y suscripción mensual) se habilitan pronto. Por ahora, aportá por transferencia 👇
          </p>
        </FadeIn>

        <FadeIn delay={160}>
          <div className="card p-6 mb-8">
            <div className="flex items-center gap-2 mb-1">
              <span className="text-[9px] font-semibold uppercase tracking-wide tint-green border px-1.5 py-0.5 rounded-full">Disponible ahora</span>
            </div>
            <h2 className="text-[17px] font-bold text-text-primary mb-1 mt-2" style={{ fontFamily: 'var(--font-display)' }}>Aportá por transferencia</h2>
            <p className="text-[13px] text-text-secondary mb-1">Transferí el monto que quieras desde cualquier banco o billetera.</p>

            <div className="mt-4 mb-4">
              <p className="text-[14px] font-semibold text-text-primary" style={{ fontFamily: 'var(--font-display)' }}>Fundación Colossus Lab</p>
              <p className="text-[12px] font-mono text-text-tertiary mt-0.5">Banco Galicia · Cuenta en pesos</p>
            </div>

            <div className="flex items-center justify-between gap-3 border border-border-light rounded-xl px-4 py-3 bg-bg-primary">
              <div className="min-w-0">
                <p className="text-[9px] font-mono uppercase tracking-[0.14em] text-text-tertiary mb-0.5">CBU</p>
                <p className="text-[14px] font-mono text-celeste-bright tracking-wide break-all">{CBU_PRETTY}</p>
              </div>
              <button
                onClick={copyCbu}
                className={`shrink-0 inline-flex items-center gap-1.5 px-3 py-2 rounded-lg text-[12px] font-medium border transition-colors ${copied ? 'border-status-green/50 text-status-green' : 'border-border-light text-text-secondary hover:border-celeste hover:text-text-primary'}`}
              >
                {copied ? <><Check size={13} /> Copiado</> : <><Copy size={13} /> Copiar</>}
              </button>
            </div>
          </div>
        </FadeIn>

        <FadeIn delay={200}>
          <div className="flex items-start gap-2.5 border-l-2 border-celeste pl-4 py-1 mb-10">
            <p className="text-[13px] text-text-secondary leading-relaxed">
              <span className="text-text-primary font-semibold">Ningún aporte destraba funciones.</span> Todo Vigía es y
              seguirá siendo gratis para todos — el que aporta banca lo público, no compra un privilegio. Gracias.
            </p>
          </div>
          <p className="text-[10px] text-text-tertiary font-mono">Datos públicos verificables · Colossus Lab · BA</p>
        </FadeIn>
      </div>
    </div>
  );
}
