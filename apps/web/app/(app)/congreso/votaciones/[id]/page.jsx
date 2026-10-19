'use client';

import { useEffect, useMemo, useState } from 'react';
import Link from 'next/link';
import { useParams } from 'next/navigation';
import { BarChart, Bar, XAxis, YAxis, Tooltip, ResponsiveContainer, CartesianGrid } from 'recharts';
import { ArrowLeft, ExternalLink, FileText, Video, Search, Landmark } from 'lucide-react';
import { api } from '@/lib/api';
import FadeIn from '@/components/FadeIn';
import CountUp from '@/components/CountUp';
import {
  VOTOS, datosPorBloque, filtrarVotos, formatFecha, formatFechaHora, nombrePropio, votoLabel,
} from '@/lib/congreso';
import {
  CamaraBadge, ResultadoBadge, VotoBadge, Badge, VotosBar, ProyectosLinks, SectionTitle,
  Cargando, Vacio, ErrorCarga, INPUT_CLS, H3_STYLE, useAngosto,
} from '@/components/congreso/ui';

function BloqueTooltip({ active, payload, label }) {
  if (!active || !payload?.length) return null;
  const fila = payload[0].payload;
  return (
    <div className="bg-navy-700 border border-border-medium rounded-lg px-3 py-2 shadow-lg">
      <p className="text-[11px] font-bold text-text-primary mb-1">{nombrePropio(fila.bloque) || label}</p>
      {payload.filter((p) => p.value > 0).map((p) => (
        <p key={p.dataKey} className="text-[11px] font-mono flex items-center gap-1.5" style={{ color: VOTOS[p.dataKey].color }}>
          <span className="w-2 h-2 rounded-full" style={{ backgroundColor: VOTOS[p.dataKey].color }} />
          {VOTOS[p.dataKey].label}: {p.value}
        </p>
      ))}
      <p className="text-[10px] font-mono text-text-tertiary mt-1">{fila.total} en total</p>
    </div>
  );
}

function PorBloque({ porBloque }) {
  const angosto = useAngosto();
  const { data, series } = useMemo(
    () => datosPorBloque(porBloque, { top: angosto ? 8 : 12, largo: angosto ? 16 : 28 }),
    [porBloque, angosto]
  );
  if (!data.length) return <Vacio>Esta acta no trae el detalle por bloque.</Vacio>;
  // `contain`: el ResponsiveContainer fija su ancho en px y, sin esto, ese ancho
  // vuelve como ancho intrínseco y la página queda más ancha que el celular.
  return (
    <div className="[contain:inline-size]">
      <ResponsiveContainer width="100%" height={data.length * 30 + 30}>
        <BarChart data={data} layout="vertical" margin={{ left: 0, right: 8, top: 0, bottom: 0 }} barCategoryGap={6}>
          <CartesianGrid strokeDasharray="3 3" stroke="rgba(116, 172, 223, 0.08)" horizontal={false} />
          <XAxis type="number" tick={{ fill: '#636E85', fontSize: 10 }} axisLine={false} tickLine={false} allowDecimals={false} />
          <YAxis type="category" dataKey="nombre" width={angosto ? 104 : 190} tick={{ fill: '#8892A8', fontSize: angosto ? 9 : 11 }} axisLine={false} tickLine={false} interval={0} />
          <Tooltip content={<BloqueTooltip />} cursor={{ fill: 'rgba(116,172,223,0.06)' }} />
          {series.map((k, i) => (
            <Bar
              key={k}
              dataKey={k}
              name={VOTOS[k].label}
              stackId="v"
              fill={VOTOS[k].color}
              radius={i === series.length - 1 ? [0, 3, 3, 0] : 0}
              animationDuration={900}
            />
          ))}
        </BarChart>
      </ResponsiveContainer>
      <div className="flex flex-wrap gap-x-4 gap-y-1 mt-2 text-[10px] font-mono text-text-tertiary">
        {series.map((k) => (
          <span key={k} className="inline-flex items-center gap-1.5">
            <span className="w-2 h-2 rounded-full" style={{ backgroundColor: VOTOS[k].color }} />
            {VOTOS[k].label}
          </span>
        ))}
      </div>
    </div>
  );
}

function TablaVotos({ votos }) {
  const [q, setQ] = useState('');
  const [voto, setVoto] = useState('');
  const conteo = useMemo(() => {
    const c = {};
    for (const v of votos || []) c[v.voto] = (c[v.voto] || 0) + 1;
    return c;
  }, [votos]);
  const filas = filtrarVotos(votos, { q, voto });
  const opciones = Object.keys(VOTOS).filter((k) => conteo[k]);

  if (!votos?.length) return <Vacio>Esta acta no trae el voto de cada legislador.</Vacio>;
  return (
    <div>
      <div className="grid grid-cols-1 md:grid-cols-[1fr_auto] gap-4 items-end mb-4">
        <div className="relative">
          <Search size={12} className="absolute left-1 top-1/2 -translate-y-1/2 text-text-tertiary" />
          <input value={q} onChange={(e) => setQ(e.target.value)} placeholder="Buscar por nombre, bloque o provincia" className={`${INPUT_CLS} pl-5`} aria-label="Buscar en los votos" />
        </div>
        <div className="flex flex-wrap gap-1.5" role="group" aria-label="Filtrar por voto">
          {[['', 'Todos', votos.length], ...opciones.map((k) => [k, votoLabel(k), conteo[k]])].map(([k, label, n]) => (
            <button
              key={k || 'todos'}
              type="button"
              onClick={() => setVoto(k)}
              aria-pressed={voto === k}
              className={`px-2.5 py-1 rounded-full text-[11px] font-medium border transition-colors ${
                voto === k ? 'bg-celeste/10 text-celeste-bright border-celeste/40' : 'text-text-secondary border-border-light hover:border-celeste/30'
              }`}
            >
              {label} <span className="font-mono text-text-tertiary">{n}</span>
            </button>
          ))}
        </div>
      </div>
      <div className="border-t border-border-light">
        {filas.length === 0 && <Vacio>Nadie coincide con ese filtro.</Vacio>}
        {filas.map((v, i) => {
          const nombre = nombrePropio(v.nombre);
          return (
            <div key={`${v.legislador_id ?? v.nombre}-${i}`} className="flex items-center gap-3 border-b border-border-light py-2.5 hover:bg-celeste/[0.03] transition-colors">
              <div className="flex-1 min-w-0">
                {v.legislador_id ? (
                  <Link href={`/congreso/legisladores/${v.legislador_id}`} className="text-[12px] font-semibold text-text-primary hover:text-celeste-bright transition-colors break-words">
                    {nombre}
                  </Link>
                ) : (
                  <span className="text-[12px] font-semibold text-text-primary break-words">{nombre}</span>
                )}
                <p className="text-[10px] text-text-tertiary break-words">
                  {[nombrePropio(v.bloque), nombrePropio(v.distrito)].filter(Boolean).join(' · ')}
                </p>
              </div>
              <VotoBadge voto={v.voto} />
            </div>
          );
        })}
      </div>
      {filas.length > 0 && <p className="text-[11px] text-text-tertiary font-mono mt-3">{filas.length} de {votos.length} legisladores</p>}
    </div>
  );
}

export default function VotacionDetalle() {
  const { id } = useParams();
  const [v, setV] = useState(undefined);

  useEffect(() => {
    setV(undefined);
    api.congresoVotacion(id).then(setV).catch((e) => setV(String(e.message).includes('404') ? null : 'error'));
  }, [id]);

  const volver = (
    <Link href="/congreso/votaciones" className="group inline-flex items-center gap-1.5 text-text-tertiary hover:text-text-primary text-[12px] mb-6 pt-2 transition-colors">
      <ArrowLeft size={13} className="group-hover:-translate-x-0.5 transition-transform" /> Votaciones
    </Link>
  );

  if (v === undefined) return <div>{volver}<Cargando /></div>;
  if (v === 'error') return <div>{volver}<ErrorCarga /></div>;
  if (v === null) return <div>{volver}<Vacio>No encontramos esa votación.</Vacio></div>;

  const TOTALES = [
    { k: 'afirmativo', label: 'Afirmativos', value: v.afirmativos },
    { k: 'negativo', label: 'Negativos', value: v.negativos },
    { k: 'abstencion', label: 'Abstenciones', value: v.abstenciones },
    { k: 'ausente', label: 'Ausentes', value: v.ausentes },
  ];
  const LINKS = [
    v.url && { href: v.url, label: 'Acta en el sitio', icon: ExternalLink },
    v.url_pdf && { href: v.url_pdf, label: 'Acta en PDF', icon: FileText },
    v.video_url && { href: v.video_url, label: 'Video', icon: Video },
  ].filter(Boolean);

  return (
    <div>
      <FadeIn>{volver}</FadeIn>

      <FadeIn delay={40}>
        <div className="mb-8">
          <div className="flex flex-wrap items-center gap-2 mb-3">
            <CamaraBadge camara={v.camara} />
            <ResultadoBadge resultado={v.resultado} />
            {v.etapa && <Badge>en {v.etapa}</Badge>}
            {v.mayoria && <Badge>mayoría {v.mayoria.toLowerCase()}</Badge>}
          </div>
          <p className="eyebrow mb-1">
            <span className="eyebrow-num">ACTA {v.numero_acta || '—'}</span>
            <span className="ml-2">{formatFechaHora(v.fecha)}</span>
          </p>
          <h1 className="display-section text-text-primary leading-tight mb-6 break-words">{v.titulo || `Acta ${v.numero_acta}`}</h1>

          <div className="grid grid-cols-2 sm:grid-cols-4 border-t-2 border-text-primary/70">
            {TOTALES.map(({ k, label, value }) => (
              <div key={k} className="pt-4 pb-5 pr-3 sm:border-r last:border-r-0 border-border-light sm:px-4 sm:first:pl-0">
                <p className="font-mono font-bold tracking-tight text-[clamp(1.8rem,3.4vw,2.6rem)] leading-none mb-1.5" style={{ color: k === 'ausente' ? '#8892A8' : VOTOS[k].color }}>
                  {value != null ? <CountUp value={value} /> : '—'}
                </p>
                <p className="text-[12px] font-bold text-text-primary" style={H3_STYLE}>{label}</p>
              </div>
            ))}
          </div>
          <div className="mt-4"><VotosBar votacion={v} alto="h-2.5" leyenda /></div>

          <div className="flex flex-wrap gap-x-5 gap-y-2 mt-6">
            {v.sesion && (
              <Link href={`/congreso/sesiones/${v.sesion.id}`} className="textlink inline-flex items-center gap-1.5 text-[12px] font-medium">
                <Landmark size={11} /> Sesión {nombrePropio(v.sesion.tipo)?.toLowerCase()} del {formatFecha(v.sesion.fecha)} <span className="arrow">→</span>
              </Link>
            )}
            {LINKS.map(({ href, label, icon: Icon }) => (
              <a key={href} href={href} target="_blank" rel="noreferrer" className="textlink inline-flex items-center gap-1.5 text-[12px] font-medium">
                <Icon size={11} /> {label} <span className="arrow">→</span>
              </a>
            ))}
          </div>
        </div>
      </FadeIn>

      {(v.proyectos?.length > 0 || v.expedientes?.length > 0 || v.ordenes_del_dia?.length > 0) && (
        <FadeIn delay={80}>
          <section className="mb-10">
            <SectionTitle num="I." eyebrow="Qué se votó">Los <em className="text-sol italic">proyectos.</em></SectionTitle>
            {v.proyectos?.length > 0 ? (
              <ProyectosLinks proyectos={v.proyectos} />
            ) : (
              <Vacio>
                Esta votación no cruza con ningún proyecto cargado en Vigía. Pasa con los acuerdos (pliegos de
                ascensos, jueces, embajadores), que no son proyectos de ley.
              </Vacio>
            )}
            {(v.expedientes?.length > 0 || v.ordenes_del_dia?.length > 0) && (
              <p className="text-[10px] font-mono text-text-tertiary mt-3 break-words">
                {v.expedientes?.length > 0 && <>expedientes: {v.expedientes.join(', ')}</>}
                {v.expedientes?.length > 0 && v.ordenes_del_dia?.length > 0 && ' · '}
                {v.ordenes_del_dia?.length > 0 && <>órdenes del día: {v.ordenes_del_dia.join(', ')}</>}
              </p>
            )}
          </section>
        </FadeIn>
      )}

      <FadeIn delay={100}>
        <section className="mb-10">
          <SectionTitle num="II." eyebrow="Voto por bloque">Cómo votó <em className="text-sol italic">cada bancada.</em></SectionTitle>
          <PorBloque porBloque={v.por_bloque} />
        </section>
      </FadeIn>

      <section className="mb-10">
        <FadeIn>
          <SectionTitle num="III." eyebrow="Voto nominal">Uno <em className="text-sol italic">por uno.</em></SectionTitle>
        </FadeIn>
        <TablaVotos votos={v.votos} />
      </section>
    </div>
  );
}
