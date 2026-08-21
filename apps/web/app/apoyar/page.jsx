'use client';

import { useState } from 'react';
import Link from 'next/link';
import { Eye, Copy, Check, ArrowLeft, ExternalLink, Mail } from 'lucide-react';
import FadeIn from '@/components/FadeIn';

const CBU = '0070011520000022781626';
const CBU_PRETTY = '0070 0115 2000 0022 7816 26';
const CONTACTO = 'devops@colossuslab.org';

/* Dos niveles, suscripciones mensuales (débito automático en MP). El monto
   libre lo define el donante en el checkout.

   `efecto` es lo único que el aporte cambia de verdad, y lo que cambia entre
   niveles NO es el tamaño del cupo sino cada cuánto se renueva. Se escribe así
   a propósito: "$5.000 = N créditos" convierte el aporte en una lista de
   precios, que es justo lo que la fundación no hace.

   OJO: el tier Adherente ($3.000, mpago.la/2vLd7UV) se sacó de la página pero
   el link sigue vivo y sus suscriptores siguen pagando. A ellos les corresponde
   `base`, igual que a Colaborador/a — está anotado en infra/DEPLOY.md. */
const TIERS = [
  { k: 'Colaborador/a', amt: '$5.000', url: 'https://mpago.la/258XizR', feat: true, efecto: 'Créditos que se renuevan cada quincena' },
  { k: 'Patrocinador/a', amt: '$20.000', url: 'https://mpago.la/2V9fVHo', efecto: 'Sin cupo: alertas sin contar créditos' },
];
const MONTO_LIBRE_URL = 'https://mpago.la/15TqeBQ';

const PASOS = [
  'Suscribite por Mercado Pago acá arriba, o transferí al CBU de abajo.',
  <>Escribinos a <a href={`mailto:${CONTACTO}`} className="text-celeste hover:text-celeste-bright transition-colors">{CONTACTO}</a> con el mail con el que entrás a Vigía — que no siempre es el de Mercado Pago.</>,
  'En el día te lo activamos.',
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

        {/* Qué es un crédito. Va antes de las tarjetas: sin esto, "más créditos"
            no significa nada y el aporte se lee como un peaje. */}
        <FadeIn delay={90}>
          <div className="card p-6 mb-9">
            <h2 className="text-[17px] font-bold text-text-primary mb-3" style={{ fontFamily: 'var(--font-display)' }}>
              ¿Qué es un crédito?
            </h2>
            <p className="text-[13px] text-text-secondary leading-relaxed mb-3">
              El corpus no se mide. Buscar, leer una norma, seguir el tracker de DNU, mirar las
              estadísticas: todo eso es libre, no lleva cuenta y no necesita ni que tengas cuenta.
            </p>
            <p className="text-[13px] text-text-secondary leading-relaxed mb-3">
              Lo único que se cuenta son <strong className="text-text-primary">los mails que te
              mandamos a vos</strong> cuando una de tus alertas encuentra algo. Un crédito es un
              mail. Todos arrancan con <strong className="text-text-primary">100 por mes</strong>,
              que alcanzan para unos tres avisos por día — bastante más de lo que usa casi
              cualquiera.
            </p>
            <p className="text-[12px] text-text-tertiary leading-relaxed">
              Si se te acaban, tus alertas siguen registrando todo igual y lo ves en Vigía cuando
              entrás; lo que se pausa hasta el mes siguiente son los mails.
            </p>
          </div>
        </FadeIn>

        <FadeIn delay={120}>
          <div className="grid grid-cols-1 sm:grid-cols-2 gap-3 mb-4">
            {TIERS.map((t) => (
              <div
                key={t.k}
                className={`rounded-2xl p-5 flex flex-col gap-1 border ${t.feat ? 'border-celeste/40 bg-bg-tertiary' : 'border-border-light bg-bg-secondary'}`}
              >
                <span className="font-mono text-[10px] uppercase tracking-[0.14em] text-text-tertiary">{t.k}</span>
                <span className="font-mono text-[1.9rem] font-medium text-text-primary leading-tight">
                  {t.amt}<span className="text-[0.85rem] text-text-tertiary"> / mes</span>
                </span>
                <span className="text-[12px] text-text-secondary mb-1">{t.efecto}</span>
                <span className="text-[11px] text-text-tertiary mb-3">Débito automático mensual</span>
                <a
                  href={t.url}
                  target="_blank"
                  rel="noopener noreferrer"
                  className={`mt-auto inline-flex items-center justify-center gap-1.5 px-3 py-2 rounded-full text-[12px] font-bold transition-colors ${
                    t.feat
                      ? 'btn-celeste'
                      : 'border border-border-light text-text-primary hover:border-celeste hover:bg-celeste/5'
                  }`}
                >
                  Suscribirme <ExternalLink size={12} />
                </a>
              </div>
            ))}
          </div>
          {/* Monto libre — misma suscripción mensual, pero el importe lo elige el donante */}
          <a
            href={MONTO_LIBRE_URL}
            target="_blank"
            rel="noopener noreferrer"
            className="flex flex-wrap items-center justify-between gap-3 rounded-2xl border border-dashed border-celeste/40 bg-celeste/[0.04] px-5 py-4 mb-4 hover:bg-celeste/[0.09] hover:border-celeste/60 transition-colors"
          >
            <span className="min-w-0">
              <span className="block font-mono text-[10px] uppercase tracking-[0.14em] text-text-tertiary mb-0.5">El monto que quieras</span>
              <span className="block text-[13px] text-text-secondary">Elegís vos cuánto aportar por mes.</span>
            </span>
            <span className="inline-flex items-center gap-1.5 px-4 py-2 rounded-full text-[12px] font-bold border border-celeste/40 text-celeste-bright whitespace-nowrap">
              Elegir monto <ExternalLink size={12} />
            </span>
          </a>

          <p className="text-[11px] text-text-tertiary font-mono mb-9">
            Se debita automáticamente todos los meses con tu tarjeta. Podés cancelarla cuando quieras desde Mercado Pago.
          </p>
        </FadeIn>

        {/* Activación manual: no hay webhook de Mercado Pago, y el mail de MP
            casi nunca es el mail con el que la persona entra a Vigía. */}
        <FadeIn delay={150}>
          <div className="card p-6 mb-8 border-l-4 border-l-celeste">
            <div className="flex items-center gap-2 mb-3">
              <Mail size={15} className="text-celeste shrink-0" />
              <h2 className="text-[17px] font-bold text-text-primary" style={{ fontFamily: 'var(--font-display)' }}>Después de aportar, avisanos</h2>
            </div>
            <ol className="space-y-2.5">
              {PASOS.map((paso, i) => (
                <li key={i} className="flex items-start gap-3">
                  <span className="shrink-0 w-5 h-5 rounded-full bg-celeste/10 border border-celeste/30 text-celeste font-mono text-[10px] flex items-center justify-center mt-0.5">
                    {i + 1}
                  </span>
                  <span className="text-[13px] text-text-secondary leading-relaxed">{paso}</span>
                </li>
              ))}
            </ol>
          </div>
        </FadeIn>

        <FadeIn delay={180}>
          <div className="card p-6 mb-8">
            <h2 className="text-[17px] font-bold text-text-primary mb-1" style={{ fontFamily: 'var(--font-display)' }}>¿Preferís un aporte único?</h2>
            <p className="text-[13px] text-text-secondary mb-1">Transferí el monto que quieras, una sola vez o cuando puedas, desde cualquier banco o billetera.</p>

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

        <FadeIn delay={210}>
          <div className="flex items-start gap-2.5 border-l-2 border-celeste pl-4 py-1 mb-6">
            <p className="text-[13px] text-text-secondary leading-relaxed">
              <span className="text-text-primary font-semibold">El aporte no compra funciones.</span> Todo
              Vigía —el Boletín, el Congreso, el buscador, cada norma— es y seguirá siendo gratis para
              todos, sin medidor y sin cuenta. Lo único que el aporte cambia es cuánto aire tenés en los
              mails que te mandamos a vos, porque son lo único que cuesta por persona. El que aporta
              banca lo público; el resto no pierde nada.
            </p>
          </div>
          <div className="flex items-start gap-2.5 border-l-2 border-sol pl-4 py-1 mb-10">
            <p className="text-[13px] text-text-secondary leading-relaxed">
              <span className="text-text-primary font-semibold">Y si no podés aportar, escribinos igual.</span>{' '}
              Si te quedaste sin créditos y los necesitás, mandanos un mail a{' '}
              <a href={`mailto:${CONTACTO}`} className="text-celeste hover:text-celeste-bright transition-colors">{CONTACTO}</a>{' '}
              y lo resolvemos: el acceso no depende de poder pagar.
            </p>
          </div>
          <p className="text-[10px] text-text-tertiary font-mono">Datos públicos verificables · Colossus Lab · BA</p>
        </FadeIn>
      </div>
    </div>
  );
}
