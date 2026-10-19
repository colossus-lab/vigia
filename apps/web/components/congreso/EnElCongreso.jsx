'use client';

/* Sección "En el Congreso" del detalle de una norma: lo que le pasó a ese
   proyecto en las cámaras, cruzado por expediente (`norma.congreso`). La API
   manda null si no hay cruce, y entonces esto ni se monta. */

import Link from 'next/link';
import { CalendarDays, Vote, Gavel } from 'lucide-react';
import {
  formatFecha, formatFechaHora, formatHora, marcador, nombrePropio, resultadoColor,
} from '@/lib/congreso';
import { CamaraBadge, ResultadoBadge, VotosBar } from '@/components/congreso/ui';

function Bloque({ icon: Icon, titulo, children }) {
  return (
    <div className="mb-6 last:mb-0">
      <p className="text-[10px] font-mono uppercase tracking-[0.15em] text-text-tertiary mb-2 flex items-center gap-1.5">
        <Icon size={10} /> {titulo}
      </p>
      <div className="border-t border-border-light">{children}</div>
    </div>
  );
}

export default function EnElCongreso({ congreso, ahora = new Date() }) {
  const reuniones = congreso?.reuniones || [];
  const votaciones = congreso?.votaciones || [];
  const asuntos = congreso?.asuntos || [];
  if (!reuniones.length && !votaciones.length && !asuntos.length) return null;

  const proximas = reuniones.filter((r) => new Date(r.fecha_hora) >= ahora);
  const pasadas = reuniones.filter((r) => new Date(r.fecha_hora) < ahora);

  return (
    <div>
      {reuniones.length > 0 && (
        <Bloque icon={CalendarDays} titulo={proximas.length ? 'Próximas reuniones de comisión' : 'Reuniones de comisión'}>
          {[...proximas, ...pasadas].slice(0, 6).map((r) => (
            <div key={r.id} className="flex items-start gap-3 border-b border-border-light py-2.5">
              <div className="shrink-0 w-[4.5rem]">
                <p className={`text-[11px] font-mono font-bold ${proximas.includes(r) ? 'text-celeste' : 'text-text-tertiary'}`}>{formatFecha(r.fecha_hora, { conDia: false })}</p>
                <p className="text-[10px] font-mono text-text-tertiary">{formatHora(r.fecha_hora)}</p>
              </div>
              <div className="flex-1 min-w-0">
                <div className="flex flex-wrap items-center gap-2 mb-0.5">
                  <CamaraBadge camara={r.camara} />
                  {!proximas.includes(r) && <span className="text-[10px] text-text-tertiary">ya pasó</span>}
                </div>
                <p className="text-[12px] font-semibold text-text-primary break-words">{nombrePropio(r.comision)}</p>
                {r.sala && <p className="text-[10px] text-text-tertiary">{r.sala}</p>}
              </div>
            </div>
          ))}
        </Bloque>
      )}

      {votaciones.length > 0 && (
        <Bloque icon={Vote} titulo="Votaciones">
          {votaciones.map((v) => (
            <Link key={v.id} href={`/congreso/votaciones/${v.id}`} className="group block border-b border-border-light py-2.5 transition-all duration-300 hover:bg-celeste/[0.03] hover:pl-2">
              <div className="flex flex-wrap items-center gap-2 mb-1">
                <CamaraBadge camara={v.camara} />
                <ResultadoBadge resultado={v.resultado} />
                <span className="text-[10px] font-mono text-text-tertiary ml-auto">{formatFechaHora(v.fecha)}</span>
              </div>
              <p className="text-[12px] font-semibold text-text-primary group-hover:text-celeste-bright transition-colors break-words mb-1.5">{v.titulo}</p>
              <div className="flex items-center gap-3">
                <div className="flex-1 max-w-[200px]"><VotosBar votacion={v} /></div>
                <span className="text-[11px] font-mono text-text-secondary">{marcador(v)}</span>
              </div>
            </Link>
          ))}
        </Bloque>
      )}

      {asuntos.length > 0 && (
        <Bloque icon={Gavel} titulo="Tratado en sesión">
          {asuntos.map((a) => {
            const contenido = (
              <div className="flex items-start gap-3">
                <div className="w-1 self-stretch rounded-full shrink-0 opacity-80" style={{ backgroundColor: resultadoColor(a.resultado) }} />
                <div className="flex-1 min-w-0">
                  <div className="flex flex-wrap items-center gap-2 mb-1">
                    {a.camara && <CamaraBadge camara={a.camara} />}
                    <ResultadoBadge resultado={a.resultado} />
                    {a.fecha && <span className="text-[10px] font-mono text-text-tertiary ml-auto">sesión del {formatFecha(a.fecha)}</span>}
                  </div>
                  <p className="text-[12px] text-text-secondary group-hover:text-text-primary transition-colors break-words">{a.sumario || a.clave}</p>
                </div>
              </div>
            );
            return a.sesion_id ? (
              <Link key={a.id} href={`/congreso/sesiones/${a.sesion_id}`} className="group block border-b border-border-light py-2.5 transition-colors hover:bg-celeste/[0.03]">
                {contenido}
              </Link>
            ) : (
              <div key={a.id} className="border-b border-border-light py-2.5">{contenido}</div>
            );
          })}
        </Bloque>
      )}
    </div>
  );
}
