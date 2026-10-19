'use client';

import { useState, useEffect } from 'react';
import Link from 'next/link';
import { useParams, useRouter } from 'next/navigation';
import { api } from '@/lib/api';
import { TIPOS_NORMA } from '@/lib/constants';
import { ArrowLeft, Clock, Building2, MapPin, Tag, ExternalLink, Database } from 'lucide-react';
import FadeIn from '@/components/FadeIn';
import EnElCongreso from '@/components/congreso/EnElCongreso';

const TIPO_TINT = {
  DNU: 'tint-red', DECRETO: 'tint-amber', LEY: 'tint-green', RESOLUCION: 'tint-blue',
  DISPOSICION: 'tint-purple', PROYECTO: 'tint-cyan', COMUNICACION: 'tint-pink',
  CONSULTA: 'tint-orange', OTRA: 'tint-gray',
};

export default function NormDetailView() {
  const { id } = useParams();
  const router = useRouter();
  const [norma, setNorma] = useState(undefined);

  useEffect(() => {
    api.getNorma(id).then(setNorma).catch(() => setNorma(null));
  }, [id]);

  if (norma === undefined) {
    return <div className="max-w-3xl mx-auto text-center py-20 text-text-tertiary font-mono animate-pulse">Cargando…</div>;
  }

  if (norma === null) {
    return (
      <div className="max-w-3xl mx-auto text-center py-20">
        <p className="text-text-tertiary">Norma no encontrada</p>
        <button onClick={() => router.push('/feed')} className="textlink text-sm mt-3">Volver al feed <span className="arrow">→</span></button>
      </div>
    );
  }

  const tipoMeta = TIPOS_NORMA[norma.tipo] || TIPOS_NORMA.OTRA;
  const estado = norma.estado || '';
  const META = [
    { icon: Clock, label: 'Publicación', value: norma.fecha_publicacion },
    { icon: Building2, label: 'Organismo', value: norma.organismo },
    { icon: MapPin, label: 'Jurisdicción', value: norma.jurisdiccion },
    { icon: Tag, label: 'Sector', value: norma.sector },
    { icon: Database, label: 'Fuente', value: norma.fuente },
  ].filter((f) => f.value);

  return (
    <div className="max-w-3xl mx-auto">
      <FadeIn>
        <button onClick={() => router.back()} className="group flex items-center gap-1.5 text-text-tertiary hover:text-text-primary text-[12px] mb-7 pt-2 transition-colors">
          <ArrowLeft size={13} className="group-hover:-translate-x-0.5 transition-transform" /> Volver
        </button>
      </FadeIn>

      {/* Header editorial */}
      <FadeIn delay={60}>
        <div className="mb-8">
          <div className="flex flex-wrap items-center gap-2 mb-4">
            <span className={`px-2.5 py-0.5 rounded-full text-[10px] font-semibold uppercase tracking-wide border ${TIPO_TINT[norma.tipo] || TIPO_TINT.OTRA}`}>
              {tipoMeta.label} {norma.numero || ''}
            </span>
            {estado && (
              <span className="px-2.5 py-0.5 rounded-full text-[10px] font-medium border tint-gray">{estado}</span>
            )}
          </div>
          <h1 className="display-section text-text-primary leading-tight mb-6">{norma.titulo}</h1>

          {/* Meta como fila hairline */}
          <div className="grid grid-cols-2 md:grid-cols-4 gap-y-4 border-t-2 border-text-primary/70 pt-4">
            {META.map(({ icon: Icon, label, value }) => (
              <div key={label} className="pr-4">
                <p className="eyebrow text-[9px] mb-1 flex items-center gap-1"><Icon size={9} /> {label}</p>
                <p className="text-[12px] font-medium text-text-primary leading-snug">{value}</p>
              </div>
            ))}
          </div>
        </div>
      </FadeIn>

      {/* Análisis IA — solo cuando exista (Fase 5) */}
      {norma.resumen_ia && (
        <FadeIn delay={100}>
          <section className="mb-10">
            <p className="eyebrow mb-3"><span className="eyebrow-num">IA</span><span className="ml-2">Análisis automático</span></p>
            <div className="border-l-2 border-celeste pl-5 py-1">
              <p className="text-[13px] text-text-secondary leading-relaxed">{norma.resumen_ia}</p>
            </div>
          </section>
        </FadeIn>
      )}

      {norma.resumen && (
        <FadeIn delay={130}>
          <section className="mb-10">
            <p className="eyebrow mb-3"><span className="eyebrow-num">I.</span><span className="ml-2">Texto resumido</span></p>
            <p className="text-[14px] text-text-secondary leading-relaxed max-w-2xl">{norma.resumen}</p>
            {(norma.url || norma.bora_seccion) && (
              <a
                href={norma.url || '#'}
                target={norma.url ? '_blank' : undefined}
                rel="noreferrer"
                className="textlink inline-flex items-center gap-1.5 text-[12px] font-medium mt-4"
              >
                <ExternalLink size={11} />
                Texto completo{norma.bora_seccion ? ` — Boletín Oficial, ${norma.bora_seccion}` : ' en la fuente'}
                <span className="arrow">→</span>
              </a>
            )}
          </section>
        </FadeIn>
      )}

      {norma.movimientos && norma.movimientos.length > 0 && (
        <FadeIn delay={150}>
          <section className="mb-10">
            <p className="eyebrow mb-3"><span className="eyebrow-num">I·b</span><span className="ml-2">Tramitación</span></p>
            <div className="border-l border-border-light ml-1">
              {norma.movimientos.map((m, i) => (
                <div key={i} className="relative pl-5 pb-4 last:pb-0">
                  <span className="absolute -left-[3.5px] top-1.5 w-1.5 h-1.5 rounded-full bg-celeste/70" />
                  <p className="text-[12px] text-text-secondary leading-relaxed">{m.movimiento}</p>
                  {m.fecha && <p className="text-[10px] text-text-tertiary font-mono mt-0.5">{m.fecha}</p>}
                </div>
              ))}
            </div>
          </section>
        </FadeIn>
      )}

      {/* Cruce por expediente con lo que pasó en las cámaras: null si no hay. */}
      {norma.congreso && (
        <FadeIn delay={155}>
          <section className="mb-10">
            <p className="eyebrow mb-3"><span className="eyebrow-num">I·c</span><span className="ml-2">En el Congreso</span></p>
            <EnElCongreso congreso={norma.congreso} />
            <Link href="/congreso" className="textlink inline-flex items-center gap-1 text-[11px] mt-3">
              Todo lo que pasa en el Congreso <span className="arrow">→</span>
            </Link>
          </section>
        </FadeIn>
      )}

      {norma.entidades && norma.entidades.length > 0 && (
        <FadeIn delay={160}>
          <section className="mb-10">
            <p className="eyebrow mb-3"><span className="eyebrow-num">II.</span><span className="ml-2">{norma.tipo === 'PROYECTO' ? 'Autoría' : 'Entidades'}</span></p>
            <div className="flex flex-wrap gap-2">
              {norma.entidades.map((ent) => (
                <span key={ent} className="px-3 py-1 border border-border-light rounded-full text-[12px] text-text-secondary transition-colors hover:border-celeste/40 hover:text-text-primary">
                  {ent}
                </span>
              ))}
            </div>
          </section>
        </FadeIn>
      )}

      {norma.tags && norma.tags.length > 0 && (
        <FadeIn delay={190}>
          <section className="mb-10">
            <p className="eyebrow mb-3"><span className="eyebrow-num">III.</span><span className="ml-2">Tags</span></p>
            <div className="flex flex-wrap gap-2">
              {norma.tags.map((tag) => (
                <span key={tag} className="px-2.5 py-1 bg-celeste/10 text-celeste-bright border border-celeste/30 rounded-full text-[10px] font-medium">
                  #{tag}
                </span>
              ))}
            </div>
          </section>
        </FadeIn>
      )}

      <FadeIn delay={210}>
        <p className="text-[10px] text-text-tertiary font-mono border-t border-border-light pt-4 pb-10">
          Fuente: {norma.tipo === 'PROYECTO' ? 'datos.hcdn.gob.ar' : 'InfoLEG / Boletín Oficial'} · dato público verificable
        </p>
      </FadeIn>
    </div>
  );
}
