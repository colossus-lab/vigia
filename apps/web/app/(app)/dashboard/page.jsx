'use client';

import { useState, useEffect } from 'react';
import {
  BarChart, Bar, XAxis, YAxis, Tooltip, ResponsiveContainer,
  PieChart, Pie, Cell, AreaChart, Area, CartesianGrid,
} from 'recharts';
import { api } from '@/lib/api';
import { TIPOS_NORMA } from '@/lib/constants';
import { TrendingUp, TrendingDown, Minus } from 'lucide-react';
import FadeIn from '@/components/FadeIn';
import CountUp from '@/components/CountUp';

const COLORS = ['#74ACDF', '#F6B40E', '#34D399', '#A78BFA', '#F87171', '#93C5F8', '#FFD04A', '#8892A8'];

// Orden y color editorial por tipo (paleta Argentina).
const SERIE_TIPOS = [
  { key: 'RESOLUCION', color: '#74ACDF' },
  { key: 'PROYECTO', color: '#22D3EE' },
  { key: 'DISPOSICION', color: '#A78BFA' },
  { key: 'DECRETO', color: '#F6B40E' },
  { key: 'LEY', color: '#34D399' },
  { key: 'DNU', color: '#F87171' },
  { key: 'COMUNICACION', color: '#F472B6' },
  { key: 'CONSULTA', color: '#FB923C' },
  { key: 'OTRA', color: '#8892A8' },
];

function Delta({ actual, anterior }) {
  if (!anterior) return null;
  const pct = Math.round(((actual - anterior) / anterior) * 100);
  const up = pct > 0;
  const Icon = pct === 0 ? Minus : up ? TrendingUp : TrendingDown;
  const cls = pct === 0 ? 'text-text-tertiary' : up ? 'text-status-green' : 'text-status-red';
  return (
    <span className={`inline-flex items-center gap-1 text-[11px] font-semibold font-mono ${cls}`}>
      <Icon size={11} /> {up ? '+' : ''}{pct}%
    </span>
  );
}

function ChartTooltip({ active, payload, label }) {
  if (!active || !payload?.length) return null;
  return (
    <div className="bg-navy-700 border border-border-medium rounded-lg p-3 shadow-lg">
      <p className="text-xs font-semibold text-text-primary mb-1 font-mono">{label}</p>
      {payload.filter((e) => e.value > 0).map((entry, i) => (
        <p key={i} className="text-[11px] text-text-secondary">
          <span className="inline-block w-2 h-2 rounded-full mr-1.5" style={{ backgroundColor: entry.color || entry.fill }} />
          {entry.name}: <span className="font-semibold text-text-primary font-mono">{entry.value.toLocaleString('es-AR')}</span>
        </p>
      ))}
    </div>
  );
}

function Eyebrow({ num, children }) {
  return (
    <p className="eyebrow mb-1">
      <span className="eyebrow-num">{num}</span>
      <span className="ml-2">{children}</span>
    </p>
  );
}

const fmtMes = (ym) => {
  const [y, m] = ym.split('-');
  const meses = ['Ene', 'Feb', 'Mar', 'Abr', 'May', 'Jun', 'Jul', 'Ago', 'Sep', 'Oct', 'Nov', 'Dic'];
  return `${meses[parseInt(m, 10) - 1]} ${y.slice(2)}`;
};

export default function DashboardView() {
  const [dash, setDash] = useState(null);
  const [dnu, setDnu] = useState(null);
  const [serie, setSerie] = useState([]);
  const [organismos, setOrganismos] = useState([]);

  useEffect(() => {
    api.dashboard().then(setDash).catch(() => {});
    api.dnuStats().then(setDnu).catch(() => {});
    api.series({ months: 24 }).then(setSerie).catch(() => {});
    api.organismos({ days: 90, limit: 10 }).then(setOrganismos).catch(() => {});
  }, []);

  const rec = dash?.recientes;
  const sectorData = (dash?.por_sector || []).slice(0, 8).map((s) => ({ name: s.sector, value: s.cantidad }));
  const totalSerie = serie.map((p) => ({ mes: fmtMes(p.mes), total: p.total }));
  const maxOrg = organismos[0]?.cantidad || 1;
  const dnuHist = (dnu?.historico || []).filter((d) => d.anio >= 1994);

  const KPIS = [
    { label: 'Normas esta semana', value: rec?.semana, sub: 'vs. semana anterior', color: 'text-celeste', delta: rec && <Delta actual={rec.semana} anterior={rec.semana_anterior} /> },
    { label: 'Últimos 30 días', value: rec?.mes, sub: 'vs. 30 días previos', color: 'text-sol', delta: rec && <Delta actual={rec.mes} anterior={rec.mes_anterior} /> },
    { label: 'Proyectos presentados', value: rec?.proyectos_30d, sub: 'últimos 30 días · Congreso', color: 'text-sol-bright', delta: null },
    { label: `DNU en ${new Date().getFullYear()}`, value: rec?.dnu_anio, sub: `${(dnu?.total ?? 0).toLocaleString('es-AR')} históricos`, color: 'text-status-red', delta: null },
  ];

  return (
    <div className="max-w-6xl mx-auto">
      {/* Header editorial */}
      <FadeIn>
        <div className="mb-10 pt-2">
          <Eyebrow num="VIGÍA / DATA">Inteligencia regulatoria</Eyebrow>
          <h2 className="display-section text-text-primary mb-1">
            El pulso de la <em>normativa.</em>
          </h2>
          <p className="text-[13px] text-text-tertiary font-mono">
            {dash ? <CountUp value={dash.total_normas} /> : '…'} normas · InfoLEG / BORA / HCDN · actualización diaria
          </p>
        </div>
      </FadeIn>

      {/* I. Ahora — KPIs monumentales sin card */}
      <section className="mb-14">
        <FadeIn><Eyebrow num="I.">Ahora</Eyebrow></FadeIn>
        <div className="grid grid-cols-2 lg:grid-cols-4 border-t-2 border-text-primary/70 mt-3">
          {KPIS.map(({ label, value, sub, color, delta }, i) => (
            <FadeIn key={label} delay={i * 90} className="h-full">
              <div className="group pt-5 pb-6 pr-4 lg:border-r border-border-light lg:px-5 first:pl-0 h-full transition-colors duration-300 hover:bg-celeste/[0.03]">
                <p className={`font-mono font-bold tracking-tight text-[clamp(2.2rem,4vw,3.4rem)] leading-none mb-2 ${color}`}>
                  {value != null ? <CountUp value={value} /> : '—'}
                </p>
                <div className="flex items-center gap-2 mb-0.5">
                  <p className="text-[13px] font-bold text-text-primary" style={{ fontFamily: 'var(--font-display)' }}>{label}</p>
                  {delta}
                </div>
                <p className="text-[11px] text-text-tertiary">{sub}</p>
              </div>
            </FadeIn>
          ))}
        </div>
      </section>

      {/* II. Pulso — total + small multiples por tipo */}
      <section className="mb-14">
        <FadeIn>
          <Eyebrow num="II.">Pulso regulatorio · 24 meses</Eyebrow>
          <h3 className="text-[17px] font-bold text-text-primary mb-6" style={{ fontFamily: 'var(--font-display)' }}>
            Producción total, <em className="text-sol italic">y cada tipo en su propia escala.</em>
          </h3>
        </FadeIn>

        <FadeIn delay={100}>
          <ResponsiveContainer width="100%" height={240}>
            <AreaChart data={totalSerie} margin={{ left: -10, right: 4 }}>
              <defs>
                <linearGradient id="fillTotal" x1="0" y1="0" x2="0" y2="1">
                  <stop offset="0%" stopColor="#74ACDF" stopOpacity={0.35} />
                  <stop offset="100%" stopColor="#74ACDF" stopOpacity={0.02} />
                </linearGradient>
              </defs>
              <CartesianGrid strokeDasharray="3 3" stroke="rgba(116, 172, 223, 0.08)" vertical={false} />
              <XAxis dataKey="mes" tick={{ fill: '#636E85', fontSize: 10 }} axisLine={false} tickLine={false} interval="preserveStartEnd" />
              <YAxis tick={{ fill: '#636E85', fontSize: 10 }} axisLine={false} tickLine={false} />
              <Tooltip content={<ChartTooltip />} />
              <Area type="monotone" dataKey="total" name="Total" stroke="#74ACDF" strokeWidth={2} fill="url(#fillTotal)" animationDuration={1200} />
            </AreaChart>
          </ResponsiveContainer>
        </FadeIn>

        {/* Small multiples: cada tipo con su escala propia */}
        <div className="grid grid-cols-2 md:grid-cols-4 lg:grid-cols-7 gap-x-5 gap-y-6 mt-8">
          {SERIE_TIPOS.map(({ key, color }, i) => {
            const data = serie.map((p) => ({ mes: fmtMes(p.mes), v: p.por_tipo[key] || 0 }));
            const total = data.reduce((s, d) => s + d.v, 0);
            if (!total) return null;
            return (
              <FadeIn key={key} delay={i * 70}>
                <div className="group cursor-default transition-transform duration-300 hover:-translate-y-1">
                  <div className="flex items-baseline justify-between mb-1.5">
                    <span className="text-[10px] font-semibold uppercase tracking-[0.1em]" style={{ color }}>
                      {(TIPOS_NORMA[key] || { label: key }).label}
                    </span>
                    <span className="text-[11px] font-mono text-text-secondary">
                      <CountUp value={total} />
                    </span>
                  </div>
                  <ResponsiveContainer width="100%" height={48}>
                    <AreaChart data={data} margin={{ top: 2, bottom: 0, left: 0, right: 0 }}>
                      <Area type="monotone" dataKey="v" stroke={color} strokeWidth={1.5} fill={color} fillOpacity={0.18} animationDuration={1000} animationBegin={i * 120} />
                    </AreaChart>
                  </ResponsiveContainer>
                  <div className="h-px bg-border-light group-hover:bg-celeste/40 transition-colors duration-300" />
                </div>
              </FadeIn>
            );
          })}
        </div>
        <p className="text-[10px] text-text-tertiary font-mono mt-3">* Cada mini-serie usa su propia escala — el conteo es el total de 24 meses.</p>
      </section>

      {/* III. Quién regula */}
      <section className="mb-14">
        <FadeIn>
          <Eyebrow num="III.">Quién regula · últimos 90 días</Eyebrow>
          <h3 className="text-[17px] font-bold text-text-primary mb-6" style={{ fontFamily: 'var(--font-display)' }}>
            Los organismos que <em className="text-sol italic">más publican.</em>
          </h3>
        </FadeIn>
        <div className="border-t border-border-light">
          {organismos.map((o, i) => (
            <FadeIn key={`${o.jurisdiccion || ''}|${o.organismo}`} delay={i * 60}>
              <div className="group grid grid-cols-[2.2rem_1fr_auto] items-center gap-3 py-3 border-b border-border-light transition-all duration-300 hover:pl-2 hover:bg-celeste/[0.03]">
                <span className="font-mono text-[11px] text-celeste">{String(i + 1).padStart(2, '0')}</span>
                <div className="min-w-0">
                  {/* La jurisdicción es parte del nombre: hay un Ministerio de
                      Salud nacional, uno de CABA y uno de PBA, y son distintos. */}
                  <p className="text-[13px] text-text-primary truncate mb-1.5" title={`${o.organismo}${o.jurisdiccion ? ` · ${o.jurisdiccion}` : ''}`}>
                    {o.organismo}
                    {o.jurisdiccion && (
                      <span className="text-text-tertiary font-mono text-[10px] ml-1.5">{o.jurisdiccion}</span>
                    )}
                  </p>
                  <div className="w-full bg-bg-tertiary/60 rounded-full h-[3px] overflow-hidden">
                    <div
                      className="h-full rounded-full transition-all duration-1000 ease-out"
                      style={{ width: `${(o.cantidad / maxOrg) * 100}%`, backgroundColor: COLORS[i % COLORS.length] }}
                    />
                  </div>
                </div>
                <span className="font-mono font-bold text-[15px] text-text-primary tabular-nums">
                  <CountUp value={o.cantidad} />
                </span>
              </div>
            </FadeIn>
          ))}
          {organismos.length === 0 && <p className="text-[12px] text-text-tertiary py-4">Sin datos del período.</p>}
        </div>
      </section>

      {/* IV + V: DNU histórico y sectores */}
      <div className="grid grid-cols-1 lg:grid-cols-2 gap-x-12 gap-y-14 mb-16">
        <section>
          <FadeIn>
            <Eyebrow num="IV.">DNU desde 1994</Eyebrow>
            <h3 className="text-[17px] font-bold text-text-primary mb-6" style={{ fontFamily: 'var(--font-display)' }}>
              Cada gestión, <em className="text-sol italic">a simple vista.</em>
            </h3>
          </FadeIn>
          <FadeIn delay={120}>
            <ResponsiveContainer width="100%" height={240}>
              <BarChart data={dnuHist} margin={{ left: -14, right: 0 }}>
                <CartesianGrid strokeDasharray="3 3" stroke="rgba(116, 172, 223, 0.08)" vertical={false} />
                <XAxis dataKey="anio" tick={{ fill: '#636E85', fontSize: 9 }} axisLine={false} tickLine={false} interval={3} />
                <YAxis tick={{ fill: '#636E85', fontSize: 10 }} axisLine={false} tickLine={false} />
                <Tooltip content={<ChartTooltip />} cursor={{ fill: 'rgba(116,172,223,0.06)' }} />
                <Bar dataKey="cantidad" name="DNU" fill="#F87171" radius={[3, 3, 0, 0]} animationDuration={1100} />
              </BarChart>
            </ResponsiveContainer>
          </FadeIn>
        </section>

        <section>
          <FadeIn>
            <Eyebrow num="V.">Sectores</Eyebrow>
            <h3 className="text-[17px] font-bold text-text-primary mb-6" style={{ fontFamily: 'var(--font-display)' }}>
              Dónde golpea <em className="text-sol italic">la regulación.</em>
            </h3>
          </FadeIn>
          <FadeIn delay={120}>
            <div className="flex items-center gap-6">
              <ResponsiveContainer width="50%" height={220}>
                <PieChart>
                  <Pie data={sectorData} cx="50%" cy="50%" innerRadius={52} outerRadius={84} paddingAngle={1.5} dataKey="value" animationDuration={1100} stroke="none">
                    {sectorData.map((_, index) => (
                      <Cell key={index} fill={COLORS[index % COLORS.length]} />
                    ))}
                  </Pie>
                  <Tooltip content={<ChartTooltip />} />
                </PieChart>
              </ResponsiveContainer>
              <div className="flex-1 space-y-2">
                {sectorData.map((s, i) => (
                  <div key={s.name} className="flex items-center gap-2 group transition-transform duration-200 hover:translate-x-1">
                    <div className="w-2 h-2 rounded-full shrink-0" style={{ backgroundColor: COLORS[i % COLORS.length] }} />
                    <span className="text-[11px] text-text-secondary truncate">{s.name}</span>
                    <span className="text-[11px] font-mono text-text-primary ml-auto tabular-nums">{s.value.toLocaleString('es-AR')}</span>
                  </div>
                ))}
              </div>
            </div>
          </FadeIn>
        </section>
      </div>

      <FadeIn>
        <p className="text-[10px] text-text-tertiary font-mono pb-10 border-t border-border-light pt-4">
          Fuentes: InfoLEG (Min. Justicia) · Boletín Oficial · datos.hcdn.gob.ar — datos públicos verificables.
        </p>
      </FadeIn>
    </div>
  );
}
