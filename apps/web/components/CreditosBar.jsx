'use client';

import Link from 'next/link';
import { useCreditos } from '@/components/CreditosProvider';

/**
 * Barra de saldo del período, en la sidebar.
 *
 * Muestra créditos, nunca dólares ni tokens: nadie sabe qué es un token, y un
 * contador que baja de forma impredecible solo genera ansiedad. Un crédito es
 * un mail de alerta, y eso se puede explicar en una línea.
 *
 * `disponibles === null` es "sin cupo" (nivel pleno) y NO es lo mismo que 0.
 *
 * Los niveles se nombran como en /apoyar (Colaborador/a, Patrocinador/a) y no
 * con los internos (`base`, `pleno`): quien lo lee acá tiene que reconocer lo
 * que contrató allá.
 */

/** Coma decimal argentina, y sin ",0" cuando el número es entero. */
function fmt(n) {
  const v = Math.max(0, n ?? 0);
  return Number.isInteger(v) ? String(v) : v.toFixed(1).replace('.', ',');
}

function fecha(iso) {
  if (!iso) return '';
  const [y, m, d] = iso.split('-');
  return `${d}/${m}`;
}

export default function CreditosBar() {
  const { creditos } = useCreditos();
  if (!creditos) return null;

  if (creditos.disponibles === null) {
    return (
      <div className="px-3 py-2.5 rounded-lg border border-sol/25 bg-sol/[0.07]">
        <p className="text-[11px] text-sol font-bold leading-tight">Patrocinador/a</p>
        <p className="text-[10px] text-text-tertiary mt-0.5 leading-snug">
          Sin cupo mensual. Gracias por bancar Vigía.
        </p>
      </div>
    );
  }

  const { cupo, disponibles, agotados } = creditos;
  const fraccion = cupo ? Math.min(1, Math.max(0, disponibles / cupo)) : 0;
  const pocos = !agotados && fraccion <= 0.2;
  const color = agotados ? 'bg-status-red' : pocos ? 'bg-sol' : 'bg-celeste';
  const texto = agotados ? 'text-status-red' : pocos ? 'text-sol' : 'text-text-secondary';

  return (
    <div className="px-3 py-2.5 rounded-lg border border-border-light bg-bg-tertiary/40">
      <div className="flex items-baseline justify-between gap-2 mb-1.5">
        <span className="text-[9px] font-mono uppercase tracking-[0.14em] text-text-tertiary">
          Créditos
        </span>
        <span className={`text-[11px] font-mono ${texto}`}>
          {fmt(disponibles)} <span className="text-text-tertiary">de {cupo}</span>
        </span>
      </div>
      <div className="h-1 rounded-full bg-bg-primary overflow-hidden" role="presentation">
        <div className={`h-full rounded-full ${color}`} style={{ width: `${fraccion * 100}%` }} />
      </div>
      <p className="text-[10px] text-text-tertiary mt-1.5 leading-snug">
        {agotados
          ? `Se renuevan el ${fecha(creditos.renueva)}.`
          : pocos
            ? `Queda poco — se renuevan el ${fecha(creditos.renueva)}.`
            : `1 crédito = 1 mail de alerta. Renuevan el ${fecha(creditos.renueva)}.`}{' '}
        <Link href="/apoyar" className="text-celeste hover:text-celeste-bright transition-colors">
          {agotados || pocos ? 'Apoyar' : '¿Qué son?'}
        </Link>
      </p>
    </div>
  );
}
