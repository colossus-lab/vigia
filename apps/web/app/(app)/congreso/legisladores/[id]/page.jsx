'use client';

import { useEffect, useState } from 'react';
import Link from 'next/link';
import { useParams } from 'next/navigation';
import { ArrowLeft, ArrowRight, Info, Clock } from 'lucide-react';
import { api } from '@/lib/api';
import FadeIn from '@/components/FadeIn';
import CountUp from '@/components/CountUp';
import { CAMARAS, nombrePropio, mandato, porcentaje, formatFecha, formatFechaHora } from '@/lib/congreso';
import {
  CamaraBadge, VotoBadge, ResultadoBadge, Badge, SectionTitle, Nota, Cargando, Vacio, ErrorCarga, ROW_CLS, H3_STYLE,
} from '@/components/congreso/ui';

function Estadisticas({ e }) {
  const KPIS = [
    { label: 'Presentismo', sub: `${e.presentes} de ${e.votaciones} votaciones`, texto: porcentaje(e.presentismo), color: 'text-celeste' },
    { label: 'Alineamiento', sub: 'votó como la mayoría de su bloque', texto: porcentaje(e.alineamiento_bloque), color: 'text-sol' },
    { label: 'Votaciones', sub: 'últimos 365 días', valor: e.votaciones, color: 'text-text-primary' },
    { label: 'Presente', sub: 'no figuró como ausente', valor: e.presentes, color: 'text-status-green' },
  ];
  return (
    <div className="grid grid-cols-2 sm:grid-cols-4 border-t-2 border-text-primary/70">
      {KPIS.map(({ label, sub, texto, valor, color }) => (
        <div key={label} className="pt-4 pb-5 pr-3 sm:border-r last:border-r-0 border-border-light sm:px-4 sm:first:pl-0">
          <p className={`font-mono font-bold tracking-tight text-[clamp(1.6rem,3vw,2.3rem)] leading-none mb-1.5 ${color}`}>
            {texto !== undefined ? (texto ?? '—') : valor != null ? <CountUp value={valor} /> : '—'}
          </p>
          <p className="text-[12px] font-bold text-text-primary" style={H3_STYLE}>{label}</p>
          <p className="text-[10px] text-text-tertiary">{sub}</p>
        </div>
      ))}
    </div>
  );
}

export default function LegisladorDetalle() {
  const { id } = useParams();
  const [l, setL] = useState(undefined);

  useEffect(() => {
    setL(undefined);
    api.congresoLegislador(id).then(setL).catch((e) => setL(String(e.message).includes('404') ? null : 'error'));
  }, [id]);

  const volver = (
    <Link href="/congreso/legisladores" className="group inline-flex items-center gap-1.5 text-text-tertiary hover:text-text-primary text-[12px] mb-6 pt-2 transition-colors">
      <ArrowLeft size={13} className="group-hover:-translate-x-0.5 transition-transform" /> Legisladores
    </Link>
  );

  if (l === undefined) return <div>{volver}<Cargando /></div>;
  if (l === 'error') return <div>{volver}<ErrorCarga /></div>;
  if (l === null) return <div>{volver}<Vacio>No encontramos a ese legislador.</Vacio></div>;

  const META = [
    { label: 'Bloque', value: nombrePropio(l.bloque) },
    { label: 'Distrito', value: nombrePropio(l.distrito) },
    { label: 'Mandato', value: mandato(l) },
    { label: 'Hasta', value: l.mandato_hasta ? formatFecha(l.mandato_hasta, { conDia: false }) : null },
  ].filter((m) => m.value);
  const votos = l.votos_recientes || [];

  return (
    <div>
      <FadeIn>{volver}</FadeIn>

      <FadeIn delay={40}>
        <div className="mb-10">
          <div className="flex flex-wrap items-center gap-2 mb-3">
            <CamaraBadge camara={l.camara} />
            {!l.activo && <Badge>mandato cumplido</Badge>}
          </div>
          <p className="eyebrow mb-1">
            <span className="eyebrow-num">{(CAMARAS[l.camara]?.legislador || 'legislador/a').toUpperCase()}</span>
          </p>
          <h1 className="display-section text-text-primary leading-tight mb-6 break-words">{nombrePropio(l.nombre)}</h1>
          <div className="grid grid-cols-2 md:grid-cols-4 gap-y-4 border-t border-border-light pt-4">
            {META.map(({ label, value }) => (
              <div key={label} className="pr-4 min-w-0">
                <p className="eyebrow text-[9px] mb-1">{label}</p>
                <p className="text-[12px] font-medium text-text-primary leading-snug break-words">{value}</p>
              </div>
            ))}
          </div>
        </div>
      </FadeIn>

      <FadeIn delay={80}>
        <section className="mb-12">
          <SectionTitle num="I." eyebrow="Últimos 365 días">En el <em className="text-sol italic">recinto.</em></SectionTitle>
          {l.estadisticas ? (
            <Estadisticas e={l.estadisticas} />
          ) : (
            <Nota icon={Info}>
              {l.camara === 'D'
                ? 'Sin presentismo ni alineamiento para Diputados: la cámara no publica el voto nominal en datos abiertos (el dataset se cortó en 2020) y su sitio de votaciones está detrás de un reCAPTCHA. Sin el voto de cada diputado no hay forma honesta de calcularlos.'
                : 'Sin votaciones registradas en los últimos 365 días.'}
            </Nota>
          )}
        </section>
      </FadeIn>

      {(votos.length > 0 || l.estadisticas) && (
        <section className="mb-10">
          <FadeIn>
            <SectionTitle num="II." eyebrow="Votos recientes">Cómo <em className="text-sol italic">votó.</em></SectionTitle>
          </FadeIn>
          <div className="border-t border-border-light">
            {votos.length === 0 && <Vacio>Sin votos recientes.</Vacio>}
            {votos.map((v, i) => (
              <Link
                key={v.votacion_id}
                href={`/congreso/votaciones/${v.votacion_id}`}
                className={`${ROW_CLS} animate-fade-in`}
                style={{ animationDelay: `${Math.min(i * 30, 300)}ms`, animationFillMode: 'both' }}
              >
                <div className="flex items-start gap-3">
                  <div className="flex-1 min-w-0">
                    <div className="flex flex-wrap items-center gap-2 mb-1">
                      <VotoBadge voto={v.voto} />
                      <span className="text-[10px] text-text-tertiary">la cámara:</span>
                      <ResultadoBadge resultado={v.resultado} />
                      <span className="text-[10px] text-text-tertiary font-mono ml-auto flex items-center gap-1">
                        <Clock size={9} /> {formatFechaHora(v.fecha)}
                      </span>
                    </div>
                    <h4 className="text-[13px] font-semibold text-text-primary group-hover:text-celeste-bright transition-colors break-words" style={H3_STYLE}>
                      {v.titulo}
                    </h4>
                  </div>
                  <ArrowRight size={12} className="text-text-tertiary group-hover:text-celeste group-hover:translate-x-0.5 shrink-0 mt-2 transition-all" />
                </div>
              </Link>
            ))}
          </div>
        </section>
      )}
    </div>
  );
}
