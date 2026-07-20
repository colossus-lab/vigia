'use client';

import { useState, useEffect, Suspense } from 'react';
import { useRouter, useSearchParams } from 'next/navigation';
import { BarChart, Bar, XAxis, Tooltip, ResponsiveContainer, Cell } from 'recharts';
import { api } from '@/lib/api';
import { TIPOS_NORMA } from '@/lib/constants';
import {
  Building2,
  Landmark, Receipt, Antenna, Umbrella, Zap, Pill, Flame, Sprout, CandlestickChart, ShieldAlert, Scale,
} from 'lucide-react';
import FadeIn from '@/components/FadeIn';
import CountUp from '@/components/CountUp';
import { Edicion } from '@/components/Edicion';
import SupportBanner from '@/components/SupportBanner';

// Icono por organismo emisor (lucide). Fallback a Building2.
const EMISOR_ICON = {
  BCRA: Landmark, ARCA: Receipt, ENACOM: Antenna, SSN: Umbrella, ENRE: Zap,
  ANMAT: Pill, ENARGAS: Flame, SENASA: Sprout, CNV: CandlestickChart,
  IGJ: Building2, UIF: ShieldAlert, CNDC: Scale,
};

function WeekTooltip({ active, payload, label }) {
  if (!active || !payload?.length) return null;
  return (
    <div className="bg-navy-700 border border-border-medium rounded-lg px-3 py-2 shadow-lg">
      <p className="text-[10px] font-mono text-text-tertiary mb-0.5">semana del {label}</p>
      <p className="text-[12px] font-bold text-text-primary font-mono">{payload[0].value.toLocaleString('es-AR')} normas</p>
    </div>
  );
}

/* Strip de actividad semanal — flotante, sin card */
function ActivityStrip() {
  const [weeks, setWeeks] = useState([]);

  useEffect(() => {
    api.series({ months: 3, granularity: 'week' }).then(setWeeks).catch(() => {});
  }, []);

  if (!weeks.length) return null;
  const data = weeks.map((w) => ({ semana: w.mes.slice(5), total: w.total }));
  const lastFull = weeks.length > 1 ? weeks[weeks.length - 2] : weeks[weeks.length - 1];

  return (
    <FadeIn delay={80}>
      <div className="mb-8 border-t-2 border-text-primary/70 pt-4">
        <div className="flex flex-wrap items-end justify-between gap-6">
          <div className="shrink-0">
            <p className="eyebrow mb-2"><span className="eyebrow-num">ACTIVIDAD</span><span className="ml-2">últimas 12 semanas</span></p>
            <p className="font-mono font-bold text-4xl text-celeste leading-none">
              <CountUp value={lastFull?.total || 0} />
            </p>
            <p className="text-[11px] text-text-tertiary mt-1">normas la semana pasada</p>
          </div>
          <div className="flex-1 min-w-[260px] max-w-xl">
            <ResponsiveContainer width="100%" height={72}>
              <BarChart data={data} margin={{ top: 4, bottom: 0, left: 0, right: 0 }}>
                <XAxis dataKey="semana" tick={{ fill: '#636E85', fontSize: 9 }} axisLine={false} tickLine={false} interval="preserveStartEnd" />
                <Tooltip content={<WeekTooltip />} cursor={{ fill: 'rgba(116,172,223,0.07)' }} />
                <Bar dataKey="total" radius={[2, 2, 0, 0]} animationDuration={900}>
                  {data.map((_, i) => (
                    <Cell key={i} fill={i >= data.length - 1 ? '#F6B40E' : '#74ACDF'} fillOpacity={i >= data.length - 1 ? 0.9 : 0.55} />
                  ))}
                </Bar>
              </BarChart>
            </ResponsiveContainer>
          </div>
        </div>
      </div>
    </FadeIn>
  );
}

function FeedView() {
  const router = useRouter();
  const searchParams = useSearchParams();
  // Deep-link desde el Universo: /feed?tipo=LEY&sector=Energía
  const tipoParam = searchParams.get('tipo');
  const sectorParam = searchParams.get('sector');
  const emisorParam = searchParams.get('emisor');
  const [filterTipo, setFilterTipo] = useState(
    tipoParam && TIPOS_NORMA[tipoParam] ? tipoParam : 'TODOS'
  );
  const [filterSector, setFilterSector] = useState(sectorParam || null);
  const [filterEmisor, setFilterEmisor] = useState(emisorParam || '');
  const [emisores, setEmisores] = useState([]);
  const [ediciones, setEdiciones] = useState([]);
  const [hasMore, setHasMore] = useState(false);
  const [offsetDias, setOffsetDias] = useState(0);
  const [loading, setLoading] = useState(true);

  // Catálogo de emisores (organismos canónicos) para el facet — una sola vez.
  useEffect(() => {
    api.emisores().then((e) => setEmisores(e || [])).catch(() => setEmisores([]));
  }, []);

  // El feed son ediciones diarias (como un diario): cambiar el filtro
  // resetea la paginación; "cargar más días" appendea.
  useEffect(() => {
    setLoading(true);
    api
      .ediciones({
        dias: 5,
        offset_dias: offsetDias,
        tipo: filterTipo !== 'TODOS' ? filterTipo : undefined,
        sector: filterSector || undefined,
        emisor: filterEmisor || undefined,
      })
      .then((d) => {
        setEdiciones((prev) => (offsetDias === 0 ? d.ediciones : [...prev, ...d.ediciones]));
        setHasMore(d.has_more);
      })
      .catch(() => { setEdiciones([]); setHasMore(false); })
      .finally(() => setLoading(false));
  }, [filterTipo, filterSector, filterEmisor, offsetDias]);

  const changeFilter = (setter) => (value) => { setOffsetDias(0); setter(value); };

  return (
    <div className="max-w-4xl mx-auto">
      <SupportBanner />
      <FadeIn>
        <div className="mb-7 pt-2">
          <p className="eyebrow mb-1"><span className="eyebrow-num">VIGÍA / FEED</span><span className="ml-2">Lo último publicado</span></p>
          <h2 className="display-section text-text-primary mb-1">Feed <em>normativo.</em></h2>
          <p className="text-[13px] text-text-tertiary font-mono">Boletín Oficial · Congreso · actualización diaria</p>
        </div>
      </FadeIn>

      <ActivityStrip />

      {/* Filtros flotantes */}
      <FadeIn delay={140}>
        <div className="mb-2 pb-4 border-b border-border-light">
          <div className="flex flex-wrap items-center gap-2">
            {['TODOS', ...Object.keys(TIPOS_NORMA)].map((tipo) => (
              <button
                key={tipo}
                onClick={() => changeFilter(setFilterTipo)(tipo)}
                className={`px-3 py-1 rounded-full text-[11px] font-medium transition-all duration-200 border ${
                  filterTipo === tipo
                    ? 'bg-celeste/10 text-celeste-bright border-celeste/40 scale-105'
                    : 'bg-transparent text-text-secondary border-border-light hover:border-celeste/30 hover:text-text-primary'
                }`}
              >
                {tipo === 'TODOS' ? 'Todos' : TIPOS_NORMA[tipo].label}
              </button>
            ))}
            {filterSector && (
              <button
                onClick={() => changeFilter(setFilterSector)(null)}
                className="px-3 py-1 rounded-full text-[11px] font-medium border bg-sol/10 text-sol border-sol/40 hover:border-sol transition-all"
                title="Quitar filtro de sector"
              >
                {filterSector} ×
              </button>
            )}
          </div>
          {emisores.length > 0 && (
            <div className="flex flex-wrap items-center gap-1.5 mt-3">
              <span className="text-[9px] uppercase tracking-wider text-text-tertiary font-mono mr-1 shrink-0">Organismo</span>
              {emisores.map((e) => {
                const Icon = EMISOR_ICON[e.emisor] || Building2;
                const on = filterEmisor === e.emisor;
                return (
                  <button
                    key={e.emisor}
                    onClick={() => changeFilter(setFilterEmisor)(on ? '' : e.emisor)}
                    className={`flex items-center gap-1.5 px-2.5 py-1 rounded-full text-[10px] font-mono transition-all border ${
                      on ? 'tint-blue' : 'border-border-light text-text-tertiary hover:text-text-secondary hover:border-celeste/30'
                    }`}
                  >
                    <Icon size={12} />
                    <span className="font-bold tracking-wide">{e.emisor}</span>
                    <span className="opacity-50">{e.cantidad.toLocaleString('es-AR')}</span>
                  </button>
                );
              })}
            </div>
          )}
        </div>
      </FadeIn>

      {loading && ediciones.length === 0 ? (
        <div className="py-20 text-center">
          <p className="text-text-tertiary text-sm font-mono animate-pulse">Cargando el Boletín…</p>
        </div>
      ) : (
        <div>
          {ediciones.map((ed) => (
            <Edicion key={ed.fecha} edicion={ed} onOpen={(id) => router.push(`/norma/${id}`)} />
          ))}
        </div>
      )}

      {!loading && ediciones.length === 0 && (
        <div className="text-center py-16">
          <p className="text-text-tertiary text-sm">No hay normas que coincidan con el filtro.</p>
        </div>
      )}

      {hasMore && !loading && (
        <div className="text-center py-8">
          <button
            onClick={() => setOffsetDias((o) => o + 5)}
            className="px-5 py-2 rounded-full text-[12px] font-medium border border-border-light text-text-secondary hover:border-celeste/40 hover:text-celeste transition-colors"
          >
            Cargar ediciones anteriores ↓
          </button>
        </div>
      )}
      {loading && ediciones.length > 0 && (
        <p className="text-center py-6 text-[11px] font-mono text-text-tertiary animate-pulse">Cargando…</p>
      )}
    </div>
  );
}

export default function FeedPage() {
  return (
    <Suspense fallback={<div className="max-w-4xl mx-auto text-text-tertiary text-sm pt-6">Cargando…</div>}>
      <FeedView />
    </Suspense>
  );
}
