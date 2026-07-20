import Link from 'next/link';
import { Heart, ArrowLeft } from 'lucide-react';
import FadeIn from '@/components/FadeIn';

export const metadata = {
  title: 'Gracias por tu aporte — Vigía',
  description: 'Tu aporte a Vigía se procesó con éxito.',
};

/**
 * Página de retorno (back URL) tras un pago/suscripción en MercadoPago.
 * MP redirige acá al donante cuando el pago fue exitoso. Es pública (el donante
 * puede no estar logueado) y no depende de la API — contenido estático.
 */
export default function GraciasPage() {
  return (
    <div className="min-h-screen flex flex-col items-center justify-center p-4">
      <div className="flag-stripe fixed top-0 inset-x-0 z-[60]" />

      <FadeIn className="w-full max-w-md">
        <div className="card p-8 text-center relative overflow-hidden">
          <div className="absolute inset-0 pointer-events-none" style={{ background: 'radial-gradient(ellipse 80% 60% at 50% -10%, rgba(116,172,223,0.12), transparent 60%)' }} />

          <div className="relative">
            <div className="w-12 h-12 rounded-xl bg-celeste/10 border border-celeste/30 flex items-center justify-center mx-auto mb-6">
              <Heart size={22} className="text-celeste" />
            </div>

            <p className="eyebrow mb-2 flex justify-center"><span className="eyebrow-num">APORTE CONFIRMADO</span></p>
            <h1 className="display-section text-text-primary mb-4">¡Gracias por bancar <em>lo público!</em></h1>

            <p className="text-[13px] text-text-secondary leading-relaxed mb-2">
              Tu aporte se procesó con éxito. Con eso mantenemos Vigía en marcha: servidores,
              ingesta diaria de datos y, sobre todo, su independencia.
            </p>
            <p className="text-[12px] text-text-tertiary leading-relaxed">
              Vigía es y seguirá siendo gratis para todos.
            </p>

            <div className="mt-7 pt-5 border-t border-border-light">
              <Link
                href="/feed"
                className="inline-flex items-center justify-center gap-2 px-5 py-2.5 btn-celeste rounded-full text-[13px] font-bold"
              >
                Volver a Vigía
              </Link>
              <div className="mt-4">
                <Link href="/" className="inline-flex items-center gap-1 text-[11px] text-text-tertiary hover:text-text-primary transition-colors">
                  <ArrowLeft size={11} /> Ir al inicio
                </Link>
              </div>
            </div>
          </div>
        </div>
      </FadeIn>

      <p className="text-[10px] text-text-tertiary font-mono mt-6">Datos públicos verificables · Colossus Lab · BA</p>
    </div>
  );
}
