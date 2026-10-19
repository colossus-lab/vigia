'use client';

import { useEffect, useState } from 'react';
import Link from 'next/link';
import { Info, FileText, ArrowRight, Clock } from 'lucide-react';
import { api } from '@/lib/api';
import FadeIn from '@/components/FadeIn';
import CountUp from '@/components/CountUp';
import {
  CAMARAS, ACTIVIDAD, agruparPorDia, tituloDia, formatFecha, formatFechaHora, hrefActividad,
  resultadoLabel, resultadoColor, nombrePropio, hoyKey,
} from '@/lib/congreso';
import {
  PageHeader, SectionTitle, VerTodo, Badge, CamaraBadge, Cargando, Vacio, ErrorCarga,
  VotacionRow, SesionRow, ReunionRow, H3_STYLE,
} from '@/components/congreso/ui';

/* ── KPIs por cámara ─────────────────────────────────────────── */

function KpisCamara({ camara, r }) {
  const meta = CAMARAS[camara];
  const KPIS = [
    { label: 'Reuniones', sub: 'de comisión, próximos 7 días', value: r?.reuniones_proximas, color: 'text-celeste' },
    {
      label: 'Votaciones', sub: 'últimos 30 días', value: r?.votaciones_30d, color: 'text-sol',
      // null no es 0: Diputados no tiene fuente de voto nominal.
      sinDatos: r && r.votaciones_30d === null,
    },
    { label: 'Sesiones', sub: 'últimos 30 días', value: r?.sesiones_30d, color: 'text-text-primary' },
    { label: 'Proyectos', sub: 'presentados, 30 días', value: r?.proyectos_30d, color: 'text-sol-bright' },
  ];
  return (
    <div>
      <div className="flex items-baseline justify-between gap-3 mb-2">
        <h3 className="text-[15px] font-bold text-text-primary flex items-center gap-2" style={H3_STYLE}>
          <span className="w-2 h-2 rounded-full" style={{ backgroundColor: meta.color }} />
          {meta.largo}
        </h3>
        {r?.ultima_sesion && (
          <span className="text-[10px] font-mono text-text-tertiary">última sesión {formatFecha(r.ultima_sesion)}</span>
        )}
      </div>
      <div className="grid grid-cols-2 sm:grid-cols-4 border-t-2 border-text-primary/70">
        {KPIS.map(({ label, sub, value, color, sinDatos }) => (
          <div key={label} className="pt-4 pb-5 pr-3 sm:border-r last:border-r-0 border-border-light sm:px-3 sm:first:pl-0">
            <p className={`font-mono font-bold tracking-tight text-[clamp(1.6rem,3vw,2.3rem)] leading-none mb-1.5 ${sinDatos ? 'text-text-tertiary' : color}`}>
              {sinDatos ? (
                <span className="text-[13px] font-medium tracking-normal">sin datos*</span>
              ) : value != null ? (
                <CountUp value={value} />
              ) : (
                '—'
              )}
            </p>
            <p className="text-[12px] font-bold text-text-primary" style={H3_STYLE}>{label}</p>
            <p className="text-[10px] text-text-tertiary">{sub}</p>
          </div>
        ))}
      </div>
    </div>
  );
}

function Resumen({ resumen, error }) {
  return (
    <FadeIn delay={60}>
      <section className="mb-12">
        <div className="grid grid-cols-1 lg:grid-cols-2 gap-8">
          <KpisCamara camara="S" r={resumen?.S} />
          <KpisCamara camara="D" r={resumen?.D} />
        </div>
        {error && <ErrorCarga />}
        {resumen?.D && resumen.D.votaciones_30d === null && (
          <p className="text-[10px] text-text-tertiary mt-3 flex items-start gap-1.5 max-w-2xl leading-relaxed">
            <Info size={10} className="shrink-0 mt-0.5" />
            <span>
              * Diputados no publica el voto nominal en datos abiertos (el dataset se cortó en 2020) y su
              sitio de votaciones está detrás de un reCAPTCHA. Lo que sí vemos es el resultado de cada asunto
              tratado, en <Link href="/congreso/sesiones?camara=D" className="text-celeste hover:text-celeste-bright">sus sesiones</Link>.
            </span>
          </p>
        )}
      </section>
    </FadeIn>
  );
}

/* ── Esta semana ─────────────────────────────────────────────── */

function AgendaColumna({ camara, data }) {
  const meta = CAMARAS[camara];
  const grupos = agruparPorDia(data?.items);
  return (
    <div className="min-w-0">
      <div className="flex items-center justify-between gap-2 pb-2 border-b-2" style={{ borderColor: meta.color }}>
        <h4 className="text-[13px] font-bold text-text-primary" style={H3_STYLE}>{meta.label}</h4>
        {data && <span className="text-[10px] font-mono text-text-tertiary">{data.total} {data.total === 1 ? 'reunión' : 'reuniones'}</span>}
      </div>
      {!data && <Cargando />}
      {data && grupos.length === 0 && (
        <Vacio>Sin reuniones de comisión cargadas para los próximos 7 días.</Vacio>
      )}
      {grupos.map((g) => (
        <div key={g.dia}>
          <p className="text-[10px] font-mono uppercase tracking-[0.12em] text-sol pt-4 pb-1">{tituloDia(g.dia)}</p>
          {g.items.map((r) => <ReunionRow key={r.id} r={r} conCamara={false} />)}
        </div>
      ))}
      {data?.total > data?.items?.length && (
        <Link href={`/congreso/agenda?camara=${camara}`} className="textlink inline-flex text-[11px] mt-3">
          y {data.total - data.items.length} más <span className="arrow">→</span>
        </Link>
      )}
    </div>
  );
}

/* ── Últimas sesiones, con lo tratado ────────────────────────── */

function LoTratado({ detalle }) {
  if (!detalle) return null;
  const items = detalle.camara === 'S' || detalle.votaciones?.length
    ? (detalle.votaciones || []).map((v) => ({ id: `v${v.id}`, texto: v.titulo, resultado: v.resultado }))
    : (detalle.asuntos || []).map((a) => ({ id: `a${a.id}`, texto: a.sumario || a.clave, resultado: a.resultado }));
  if (!items.length) return null;
  return (
    <ul className="mt-2 space-y-1">
      {items.slice(0, 3).map((it) => (
        <li key={it.id} className="flex items-start gap-2 text-[11px] text-text-secondary min-w-0">
          <span className="mt-[5px] w-1.5 h-1.5 rounded-full shrink-0" style={{ backgroundColor: resultadoColor(it.resultado) }} title={resultadoLabel(it.resultado)} />
          <span className="min-w-0 line-clamp-2">{it.texto}</span>
        </li>
      ))}
      {items.length > 3 && <li className="text-[10px] font-mono text-text-tertiary pl-3.5">+ {items.length - 3} más</li>}
    </ul>
  );
}

/* ── Actividad ───────────────────────────────────────────────── */

function Actividad({ data, error }) {
  if (error) return <ErrorCarga />;
  if (!data) return <Cargando />;
  if (!data.items?.length) return <Vacio>Sin actividad en las últimas dos semanas.</Vacio>;
  return (
    <div className="border-l border-border-light ml-1">
      {data.items.map((it, i) => {
        const meta = ACTIVIDAD[it.tipo] || ACTIVIDAD.reunion;
        return (
          <Link
            key={`${it.tipo}-${it.id}`}
            href={hrefActividad(it)}
            className="group relative block pl-5 pb-4 last:pb-0 animate-fade-in"
            style={{ animationDelay: `${Math.min(i * 30, 300)}ms`, animationFillMode: 'both' }}
          >
            <span className="absolute -left-[3.5px] top-1.5 w-1.5 h-1.5 rounded-full" style={{ backgroundColor: CAMARAS[it.camara]?.color }} />
            <div className="flex flex-wrap items-center gap-2 mb-0.5">
              <Badge tint={meta.tint}>{meta.label}</Badge>
              <CamaraBadge camara={it.camara} />
              <span className="text-[10px] text-text-tertiary font-mono">{formatFechaHora(it.fecha)}</span>
            </div>
            <p className="text-[12px] text-text-primary group-hover:text-celeste-bright transition-colors break-words">
              {nombrePropio(it.titulo)}
              {it.detalle && <span className="text-text-tertiary font-mono text-[11px]"> · {it.detalle}</span>}
            </p>
          </Link>
        );
      })}
    </div>
  );
}

/* ── Página ──────────────────────────────────────────────────── */

export default function CongresoHub() {
  const [resumen, setResumen] = useState(null);
  const [errResumen, setErrResumen] = useState(false);
  const [agendaS, setAgendaS] = useState(null);
  const [agendaD, setAgendaD] = useState(null);
  const [votaciones, setVotaciones] = useState(null);
  const [sesiones, setSesiones] = useState(null);
  const [detalles, setDetalles] = useState({});
  const [actividad, setActividad] = useState(null);
  const [errActividad, setErrActividad] = useState(false);

  useEffect(() => {
    const vacia = { items: [], total: 0 };
    api.congresoResumen().then(setResumen).catch(() => setErrResumen(true));
    api.congresoAgenda({ camara: 'S', limit: 30 }).then(setAgendaS).catch(() => setAgendaS(vacia));
    api.congresoAgenda({ camara: 'D', limit: 30 }).then(setAgendaD).catch(() => setAgendaD(vacia));
    api.congresoVotaciones({ limit: 5 }).then(setVotaciones).catch(() => setVotaciones(vacia));
    api.congresoActividad({ limit: 12 }).then(setActividad).catch(() => setErrActividad(true));
    // "Últimas": hasta hoy. La lista trae también las convocadas a futuro.
    api.congresoSesiones({ limit: 4, hasta: hoyKey() })
      .then((d) => {
        setSesiones(d);
        // "Con lo tratado": el listado trae solo conteos, así que pedimos el
        // detalle de las cuatro que se muestran. Si alguno falla, la fila queda
        // con el conteo y nada más.
        (d.items || []).forEach((s) =>
          api.congresoSesion(s.id).then((det) => setDetalles((prev) => ({ ...prev, [s.id]: det }))).catch(() => {})
        );
      })
      .catch(() => setSesiones(vacia));
  }, []);

  const proyectos30 = (resumen?.S?.proyectos_30d || 0) + (resumen?.D?.proyectos_30d || 0);

  return (
    <div>
      <FadeIn>
        <PageHeader
          eyebrow="CONGRESO"
          sub="Senado y Diputados"
          titulo={<>El Congreso, <em>en sesión.</em></>}
          bajada="agenda de comisiones · votaciones · sesiones — actualización diaria"
        />
      </FadeIn>

      <Resumen resumen={resumen} error={errResumen} />

      {/* I. Esta semana */}
      <section className="mb-12">
        <FadeIn>
          <SectionTitle num="I." eyebrow="Agenda de comisiones" accion={<VerTodo href="/congreso/agenda">Agenda completa</VerTodo>}>
            Esta semana <em className="text-sol italic">en el Congreso.</em>
          </SectionTitle>
        </FadeIn>
        <FadeIn delay={80}>
          <div className="grid grid-cols-1 md:grid-cols-2 gap-8">
            <AgendaColumna camara="S" data={agendaS} />
            <AgendaColumna camara="D" data={agendaD} />
          </div>
        </FadeIn>
      </section>

      <div className="grid grid-cols-1 lg:grid-cols-2 gap-x-10 gap-y-12 mb-12">
        {/* II. Votaciones */}
        <section className="min-w-0">
          <FadeIn>
            <SectionTitle num="II." eyebrow="Voto nominal · Senado" accion={<VerTodo href="/congreso/votaciones" />}>
              Últimas <em className="text-sol italic">votaciones.</em>
            </SectionTitle>
          </FadeIn>
          <div className="border-t border-border-light">
            {!votaciones && <Cargando />}
            {votaciones?.items?.length === 0 && <Vacio>Todavía no hay votaciones cargadas.</Vacio>}
            {(votaciones?.items || []).map((v, i) => <VotacionRow key={v.id} v={v} i={i} />)}
          </div>
        </section>

        {/* III. Sesiones */}
        <section className="min-w-0">
          <FadeIn>
            <SectionTitle num="III." eyebrow="Recinto" accion={<VerTodo href="/congreso/sesiones" />}>
              Últimas <em className="text-sol italic">sesiones.</em>
            </SectionTitle>
          </FadeIn>
          <div className="border-t border-border-light">
            {!sesiones && <Cargando />}
            {sesiones?.items?.length === 0 && <Vacio>Todavía no hay sesiones cargadas.</Vacio>}
            {(sesiones?.items || []).map((s, i) => (
              <SesionRow key={s.id} s={s} i={i}>
                <LoTratado detalle={detalles[s.id]} />
              </SesionRow>
            ))}
          </div>
        </section>
      </div>

      <div className="grid grid-cols-1 lg:grid-cols-[1.5fr_1fr] gap-x-10 gap-y-12 mb-10">
        {/* IV. Actividad */}
        <section className="min-w-0">
          <FadeIn>
            <SectionTitle num="IV." eyebrow="Últimos 14 días">
              Lo que <em className="text-sol italic">pasó.</em>
            </SectionTitle>
          </FadeIn>
          <Actividad data={actividad} error={errActividad} />
        </section>

        {/* V. Proyectos */}
        <section className="min-w-0">
          <FadeIn>
            <SectionTitle num="V." eyebrow="Mesa de entradas">
              Proyectos <em className="text-sol italic">recientes.</em>
            </SectionTitle>
          </FadeIn>
          <Link
            href="/feed?tipo=PROYECTO"
            className="group block border-t-2 border-text-primary/70 pt-4 transition-colors hover:bg-celeste/[0.03]"
          >
            <p className="font-mono font-bold tracking-tight text-[clamp(1.9rem,3.4vw,2.6rem)] leading-none mb-1.5 text-sol-bright">
              {resumen ? <CountUp value={proyectos30} /> : '—'}
            </p>
            <p className="text-[12px] font-bold text-text-primary" style={H3_STYLE}>proyectos presentados en 30 días</p>
            <p className="text-[11px] text-text-tertiary mb-3">en las dos cámaras, con su tramitación y su cruce con lo votado</p>
            <span className="inline-flex items-center gap-1.5 text-[12px] font-medium text-celeste group-hover:text-celeste-bright">
              <FileText size={12} /> Ver en el feed <ArrowRight size={12} className="group-hover:translate-x-0.5 transition-transform" />
            </span>
          </Link>
          {resumen?.actualizado && (
            <p className="text-[10px] text-text-tertiary font-mono mt-6 flex items-center gap-1">
              <Clock size={9} /> datos al {formatFechaHora(resumen.actualizado)}
            </p>
          )}
        </section>
      </div>
    </div>
  );
}
