'use client';

import { useEffect, useState } from 'react';
import Link from 'next/link';
import { Heart, X } from 'lucide-react';

/**
 * Invitación descartable a apoyar el proyecto, arriba del feed. Vigía es gratis
 * y se sostiene con aportes; esto lo hace visible sin molestar. Se oculta al
 * cerrarlo (persistido en localStorage para no insistir).
 */
const KEY = 'vigia_support_dismissed';

export default function SupportBanner() {
  const [hidden, setHidden] = useState(true); // oculto hasta leer localStorage (evita flash)

  useEffect(() => {
    try {
      setHidden(localStorage.getItem(KEY) === '1');
    } catch {
      setHidden(false);
    }
  }, []);

  if (hidden) return null;

  const dismiss = () => {
    try {
      localStorage.setItem(KEY, '1');
    } catch {
      /* noop */
    }
    setHidden(true);
  };

  return (
    <div className="mb-5 card border-l-4 border-l-sol p-3.5 flex items-center gap-3">
      <div className="w-8 h-8 rounded-lg bg-sol/10 border border-sol/25 flex items-center justify-center shrink-0">
        <Heart size={15} className="text-sol" />
      </div>
      <p className="flex-1 min-w-0 text-[12px] text-text-secondary leading-relaxed">
        <span className="text-text-primary font-semibold">Vigía es y seguirá siendo gratis.</span>{' '}
        Lo sostenemos con aportes de quienes lo usan — si te sirve, bancá el proyecto.
      </p>
      <Link
        href="/apoyar"
        className="shrink-0 px-3 py-1.5 rounded-full text-[12px] font-bold whitespace-nowrap bg-sol/15 text-sol border border-sol/30 hover:bg-sol/25 transition-colors"
      >
        Apoyar
      </Link>
      <button
        onClick={dismiss}
        aria-label="Descartar"
        className="shrink-0 p-1 text-text-tertiary hover:text-text-primary transition-colors"
      >
        <X size={15} />
      </button>
    </div>
  );
}
