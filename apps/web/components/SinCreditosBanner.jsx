'use client';

import { useEffect, useState } from 'react';
import Link from 'next/link';
import { BellOff, X } from 'lucide-react';
import { AUTH_ENABLED } from '@/lib/authClient';
import { useCreditos } from '@/components/CreditosProvider';

/**
 * Cartel de "te quedaste sin créditos", arriba de cualquier pantalla de la app.
 *
 * Vive en el layout y no en /alerts a propósito: la persona se entera de que
 * dejó de recibir mails justamente porque NO le llegan, así que el aviso tiene
 * que estar donde entre, no en la pantalla que quizás no visita.
 *
 * El orden del texto es deliberado: primero lo que NO se pierde, después cómo
 * se sigue. Al revés se lee como un cobro.
 *
 * El descarte se guarda por período (`vigia_sincreditos_dismissed:<renueva>`) y
 * no con una clave fija como los otros banners: quien lo cierra este mes tiene
 * que volver a verlo el que viene si vuelve a quedarse sin créditos.
 */
const PREFIJO = 'vigia_sincreditos_dismissed';

function fecha(iso) {
  if (!iso) return '';
  const [y, m, d] = iso.split('-');
  return `${d}/${m}`;
}

export default function SinCreditosBanner() {
  const { creditos } = useCreditos();
  const [oculto, setOculto] = useState(true); // oculto hasta leer localStorage (evita flash)

  const clave = creditos?.renueva ? `${PREFIJO}:${creditos.renueva}` : null;

  useEffect(() => {
    if (!clave) return;
    try {
      setOculto(localStorage.getItem(clave) === '1');
    } catch {
      setOculto(false);
    }
  }, [clave]);

  // `disponibles === null` es el nivel pleno: no tiene cupo, nunca ve esto.
  if (!AUTH_ENABLED || !creditos?.agotados || creditos.disponibles === null || oculto) {
    return null;
  }

  const descartar = () => {
    try {
      if (clave) localStorage.setItem(clave, '1');
    } catch {
      /* noop */
    }
    setOculto(true);
  };

  return (
    <div className="mb-5 card border-l-4 border-l-sol p-4 flex items-start gap-3">
      <div className="w-8 h-8 rounded-lg bg-sol/10 border border-sol/25 flex items-center justify-center shrink-0">
        <BellOff size={15} className="text-sol" />
      </div>
      <div className="flex-1 min-w-0">
        <p className="text-[13px] font-semibold text-text-primary">
          Te quedaste sin créditos este mes
        </p>
        <p className="text-[12px] text-text-secondary leading-relaxed mt-0.5">
          No perdiste nada: tus alertas siguen registrando cada coincidencia y está todo acá. Lo
          único que se pausó son los mails, y se reanudan solos el{' '}
          <span className="text-text-primary font-semibold">{fecha(creditos.renueva)}</span>. Si
          querés seguir recibiéndolos ahora, podés apoyar el proyecto.
        </p>
        <div className="flex flex-wrap items-center gap-2 mt-2.5">
          <Link
            href="/alerts"
            className="px-3 py-1.5 rounded-full text-[12px] font-bold border border-border-light text-text-primary hover:border-celeste hover:bg-celeste/5 transition-colors"
          >
            Ver lo que se detectó
          </Link>
          <Link
            href="/apoyar"
            className="px-3 py-1.5 rounded-full text-[12px] font-bold bg-sol/15 text-sol border border-sol/30 hover:bg-sol/25 transition-colors"
          >
            Apoyar a Vigía
          </Link>
        </div>
      </div>
      <button
        onClick={descartar}
        aria-label="Descartar"
        className="shrink-0 p-1 text-text-tertiary hover:text-text-primary transition-colors"
      >
        <X size={15} />
      </button>
    </div>
  );
}
