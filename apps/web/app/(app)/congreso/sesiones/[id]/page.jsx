'use client';

import { useEffect, useState } from 'react';
import Link from 'next/link';
import { useParams } from 'next/navigation';
import { ArrowLeft, ExternalLink, FileText, BookOpen } from 'lucide-react';
import { api } from '@/lib/api';
import FadeIn from '@/components/FadeIn';
import { formatFecha, nombrePropio, resultadoColor } from '@/lib/congreso';
import {
  CamaraBadge, ResultadoBadge, Badge, VotacionRow, ProyectosLinks, SectionTitle,
  Cargando, Vacio, ErrorCarga, sesionNumeros,
} from '@/components/congreso/ui';

function Asunto({ a, i }) {
  return (
    <div
      className="border-b border-border-light py-3.5 hover:bg-celeste/[0.03] transition-colors animate-fade-in"
      style={{ animationDelay: `${Math.min(i * 30, 300)}ms`, animationFillMode: 'both' }}
    >
      <div className="flex items-start gap-3">
        <div className="w-1 self-stretch rounded-full shrink-0 opacity-80" style={{ backgroundColor: resultadoColor(a.resultado) }} />
        <div className="flex-1 min-w-0">
          <div className="flex flex-wrap items-center gap-2 mb-1">
            <ResultadoBadge resultado={a.resultado} />
            {a.tipo && <Badge>{a.tipo}</Badge>}
            {a.orden_del_dia && <span className="text-[10px] font-mono text-text-tertiary">O.D. {a.orden_del_dia}</span>}
            {a.clave && !a.clave.startsWith('#') && !a.clave.startsWith('OD-') && (
              <span className="text-[10px] font-mono text-text-tertiary">{a.clave}</span>
            )}
          </div>
          <p className="text-[13px] text-text-primary leading-relaxed break-words">{a.sumario || a.clave}</p>
          <ProyectosLinks proyectos={a.proyectos} compacto />
        </div>
      </div>
    </div>
  );
}

export default function SesionDetalle() {
  const { id } = useParams();
  const [s, setS] = useState(undefined);

  useEffect(() => {
    setS(undefined);
    api.congresoSesion(id).then(setS).catch((e) => setS(String(e.message).includes('404') ? null : 'error'));
  }, [id]);

  const volver = (
    <Link href="/congreso/sesiones" className="group inline-flex items-center gap-1.5 text-text-tertiary hover:text-text-primary text-[12px] mb-6 pt-2 transition-colors">
      <ArrowLeft size={13} className="group-hover:-translate-x-0.5 transition-transform" /> Sesiones
    </Link>
  );

  if (s === undefined) return <div>{volver}<Cargando /></div>;
  if (s === 'error') return <div>{volver}<ErrorCarga /></div>;
  if (s === null) return <div>{volver}<Vacio>No encontramos esa sesión.</Vacio></div>;

  const LINKS = [
    s.url_taquigrafica && { href: s.url_taquigrafica, label: 'Versión taquigráfica', icon: BookOpen },
    s.url_diario && { href: s.url_diario, label: 'Diario de sesiones', icon: FileText },
    s.url && { href: s.url, label: 'La sesión en el sitio', icon: ExternalLink },
  ].filter(Boolean);
  const votaciones = s.votaciones || [];
  const asuntos = s.asuntos || [];

  return (
    <div>
      <FadeIn>{volver}</FadeIn>

      <FadeIn delay={40}>
        <div className="mb-10">
          <div className="flex flex-wrap items-center gap-2 mb-3">
            <CamaraBadge camara={s.camara} />
            {sesionNumeros(s) && <span className="text-[10px] font-mono text-text-tertiary">{sesionNumeros(s)}</span>}
          </div>
          <p className="eyebrow mb-1"><span className="eyebrow-num">SESIÓN</span><span className="ml-2">{formatFecha(s.fecha)}</span></p>
          <h1 className="display-section text-text-primary leading-tight mb-5 break-words">{nombrePropio(s.tipo) || 'Sesión'}</h1>
          <div className="flex flex-wrap gap-x-5 gap-y-2 border-t-2 border-text-primary/70 pt-4">
            {LINKS.map(({ href, label, icon: Icon }) => (
              <a key={href} href={href} target="_blank" rel="noreferrer" className="textlink inline-flex items-center gap-1.5 text-[12px] font-medium">
                <Icon size={11} /> {label} <span className="arrow">→</span>
              </a>
            ))}
            {!s.url_taquigrafica && (
              <span className="text-[11px] text-text-tertiary">
                {s.camara === 'D'
                  ? 'Diputados todavía no tiene una fuente de versiones taquigráficas en Vigía.'
                  : 'Sin versión taquigráfica publicada.'}
              </span>
            )}
          </div>
        </div>
      </FadeIn>

      {(votaciones.length > 0 || s.camara === 'S') && (
        <section className="mb-10">
          <FadeIn>
            <SectionTitle num="I." eyebrow={`${votaciones.length} ${votaciones.length === 1 ? 'votación' : 'votaciones'}`}>
              Lo que se <em className="text-sol italic">votó.</em>
            </SectionTitle>
          </FadeIn>
          <div className="border-t border-border-light">
            {votaciones.length === 0 && <Vacio>Esta sesión no tiene votaciones nominales registradas.</Vacio>}
            {votaciones.map((v, i) => <VotacionRow key={v.id} v={v} i={i} conCamara={false} />)}
          </div>
        </section>
      )}

      {(asuntos.length > 0 || s.camara === 'D') && (
        <section className="mb-10">
          <FadeIn>
            <SectionTitle num={votaciones.length ? 'II.' : 'I.'} eyebrow={`${asuntos.length} ${asuntos.length === 1 ? 'asunto' : 'asuntos'} · Boletín de Asuntos Tratados`}>
              Lo que se <em className="text-sol italic">trató.</em>
            </SectionTitle>
          </FadeIn>
          <div className="border-t border-border-light">
            {asuntos.length === 0 && (
              <Vacio>
                Esta sesión no tiene Boletín de Asuntos Tratados. Pasa con las asambleas, las sesiones en minoría
                y las preparatorias, o si la cámara todavía no lo publicó.
              </Vacio>
            )}
            {asuntos.map((a, i) => <Asunto key={a.id} a={a} i={i} />)}
          </div>
          {s.camara === 'D' && asuntos.length > 0 && (
            <p className="text-[10px] text-text-tertiary mt-3">
              Diputados publica el resultado de cada asunto, no el voto de cada diputado.
            </p>
          )}
        </section>
      )}
    </div>
  );
}
