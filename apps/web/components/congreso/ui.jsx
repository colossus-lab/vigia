'use client';

/* Piezas compartidas de la sección Congreso: badges, barra de votos, filas de
   votación/sesión/reunión, filtros y paginado. Colores y formatos salen de
   lib/congreso.js; acá solo hay markup. */

import { useEffect, useState } from 'react';
import Link from 'next/link';
import { useRouter } from 'next/navigation';
import { ArrowRight, ChevronLeft, ChevronRight, Clock, FileText, MapPin } from 'lucide-react';
import {
  CAMARAS, camaraLabel, camaraTint, votoLabel, votoTint, resultadoLabel, resultadoTint,
  nombrePropio, nombreComision, textoLegible, hoyKey, formatFecha, formatFechaHora, formatHora, marcador, proporcionVotos, VOTOS,
} from '@/lib/congreso';

export const INPUT_CLS =
  'w-full bg-transparent border-b border-border-light px-1 py-2 text-[12px] text-text-secondary focus:outline-none focus:border-celeste transition-colors';
export const LABEL_CLS = 'text-[10px] font-mono uppercase tracking-[0.15em] text-text-tertiary';
export const ROW_CLS =
  'group block border-b border-border-light py-3.5 transition-all duration-300 hover:bg-celeste/[0.03] hover:pl-3';
export const H3_STYLE = { fontFamily: 'var(--font-display)' };

/* ── Encabezado ──────────────────────────────────────────────── */

export function PageHeader({ eyebrow, sub, titulo, bajada }) {
  return (
    <div className="mb-7 pt-2">
      <p className="eyebrow mb-1">
        <span className="eyebrow-num">VIGÍA / {eyebrow}</span>
        {sub && <span className="ml-2">{sub}</span>}
      </p>
      <h2 className="display-section text-text-primary mb-1">{titulo}</h2>
      {bajada && <p className="text-[13px] text-text-tertiary font-mono">{bajada}</p>}
    </div>
  );
}

export function SectionTitle({ num, eyebrow, children, accion }) {
  return (
    <div className="flex flex-wrap items-end justify-between gap-x-4 gap-y-1 mb-4">
      <div>
        <p className="eyebrow mb-1">
          <span className="eyebrow-num">{num}</span>
          <span className="ml-2">{eyebrow}</span>
        </p>
        <h3 className="text-[17px] font-bold text-text-primary" style={H3_STYLE}>{children}</h3>
      </div>
      {accion}
    </div>
  );
}

export function VerTodo({ href, children = 'Ver todo' }) {
  return (
    <Link href={href} className="textlink inline-flex items-center gap-1 text-[12px] font-medium">
      {children} <span className="arrow">→</span>
    </Link>
  );
}

/* ── Badges ──────────────────────────────────────────────────── */

export function Badge({ tint = 'tint-gray', children, className = '' }) {
  return (
    <span className={`inline-flex items-center px-2 py-0.5 rounded-full text-[9px] font-medium border uppercase tracking-wide whitespace-nowrap ${tint} ${className}`}>
      {children}
    </span>
  );
}

export const CamaraBadge = ({ camara }) => <Badge tint={camaraTint(camara)}>{camaraLabel(camara)}</Badge>;
export const VotoBadge = ({ voto }) => <Badge tint={votoTint(voto)}>{votoLabel(voto)}</Badge>;
export function ResultadoBadge({ resultado }) {
  return <Badge tint={resultadoTint(resultado)}>{resultadoLabel(resultado)}</Badge>;
}

/* ── Estados ─────────────────────────────────────────────────── */

export function Cargando({ texto = 'Cargando…' }) {
  return <p className="text-[12px] text-text-tertiary py-6 font-mono animate-pulse">{texto}</p>;
}

export function Vacio({ children }) {
  return <p className="text-[12px] text-text-tertiary py-6 leading-relaxed">{children}</p>;
}

export function ErrorCarga() {
  return (
    <p className="text-[12px] text-status-red/90 py-6">
      No pudimos traer los datos del Congreso. Probá de nuevo en un rato.
    </p>
  );
}

/** Nota editorial con borde sol (el idioma de /dnu). */
export function Nota({ icon: Icon, children }) {
  return (
    <div className="flex items-start gap-3 border-l-2 border-sol pl-4 py-1">
      {Icon && <Icon size={14} className="text-sol shrink-0 mt-0.5" />}
      <p className="text-[12px] text-text-secondary leading-relaxed max-w-2xl">{children}</p>
    </div>
  );
}

/* ── Barra afirmativo/negativo ───────────────────────────────── */

export function VotosBar({ votacion, alto = 'h-1.5', leyenda = false }) {
  const p = proporcionVotos(votacion);
  if (!p) return null;
  const tramos = [
    ['afirmativo', p.afirmativo],
    ['abstencion', p.abstencion],
    ['negativo', p.negativo],
  ].filter(([, x]) => x > 0);
  return (
    <div>
      <div className={`flex w-full ${alto} rounded-full overflow-hidden bg-border-light`} role="img"
        aria-label={`${votacion.afirmativos} afirmativos, ${votacion.negativos} negativos, ${votacion.abstenciones || 0} abstenciones`}>
        {tramos.map(([k, x]) => (
          <span key={k} style={{ width: `${x * 100}%`, backgroundColor: VOTOS[k].color }} className="h-full" />
        ))}
      </div>
      {leyenda && (
        <div className="flex flex-wrap gap-x-4 gap-y-1 mt-2 text-[10px] font-mono text-text-tertiary">
          {tramos.map(([k, x]) => (
            <span key={k} className="inline-flex items-center gap-1.5">
              <span className="w-2 h-2 rounded-full" style={{ backgroundColor: VOTOS[k].color }} />
              {VOTOS[k].label} {Math.round(x * 100)}%
            </span>
          ))}
        </div>
      )}
    </div>
  );
}

/* ── Proyectos cruzados ──────────────────────────────────────── */

export function ProyectosLinks({ proyectos, compacto = false }) {
  if (!proyectos?.length) return null;
  return (
    <ul className={compacto ? 'mt-1.5 space-y-1' : 'mt-2 space-y-1.5'}>
      {proyectos.map((p) => (
        <li key={p.id} className="min-w-0">
          <Link
            href={`/norma/${p.id}`}
            className="group/p inline-flex items-start gap-1.5 text-[11px] text-celeste hover:text-celeste-bright transition-colors max-w-full"
          >
            <FileText size={10} className="shrink-0 mt-[3px]" />
            <span className="min-w-0">
              <span className="font-mono">{p.numero}</span>
              {p.titulo && <span className="text-text-secondary group-hover/p:text-text-primary"> · {sentenceTitulo(p.titulo)}</span>}
              {p.estado && <span className="text-text-tertiary"> · {p.estado}</span>}
            </span>
          </Link>
        </li>
      ))}
    </ul>
  );
}

// Los títulos de HCDN vienen en mayúsculas con punto final.
const sentenceTitulo = (t) => {
  const s = t.replace(/\.\s*$/, '');
  return s === s.toUpperCase() ? s.charAt(0) + s.slice(1).toLowerCase() : s;
};

/* ── Filas ───────────────────────────────────────────────────── */

/* Las filas son un div clickeable y no un <Link>: adentro van los links a los
   proyectos, y un <a> dentro de otro rompe la hidratación. El título sí es un
   <Link>, para el teclado y el clic del medio. */
function FilaLink({ href, i, children }) {
  const router = useRouter();
  return (
    <div
      onClick={(e) => {
        if (e.target.closest('a, button')) return;
        router.push(href);
      }}
      className={`${ROW_CLS} cursor-pointer animate-fade-in`}
      style={{ animationDelay: `${Math.min(i * 30, 300)}ms`, animationFillMode: 'both' }}
    >
      {children}
    </div>
  );
}

export function VotacionRow({ v, i = 0, conCamara = true }) {
  const href = `/congreso/votaciones/${v.id}`;
  return (
    <FilaLink href={href} i={i}>
      <div className="flex items-start gap-3">
        <div className="flex-1 min-w-0">
          <div className="flex flex-wrap items-center gap-2 mb-1">
            {conCamara && <CamaraBadge camara={v.camara} />}
            <ResultadoBadge resultado={v.resultado} />
            {v.etapa && <span className="text-[10px] text-text-tertiary font-mono">en {v.etapa}</span>}
            <span className="text-[10px] text-text-tertiary font-mono ml-auto flex items-center gap-1">
              <Clock size={9} /> {formatFechaHora(v.fecha)}
            </span>
          </div>
          <h4 className="text-[13px] font-semibold text-text-primary group-hover:text-celeste-bright transition-colors mb-2" style={H3_STYLE}>
            <Link href={href}>{v.titulo || `Acta ${v.numero_acta}`}</Link>
          </h4>
          <div className="flex items-center gap-3">
            <div className="flex-1 max-w-xs"><VotosBar votacion={v} /></div>
            <span className="text-[11px] font-mono text-text-secondary tabular-nums shrink-0">{marcador(v)}</span>
          </div>
          <ProyectosLinks proyectos={v.proyectos} compacto />
        </div>
        <ArrowRight size={12} className="text-text-tertiary group-hover:text-celeste group-hover:translate-x-0.5 shrink-0 mt-2 transition-all" />
      </div>
    </FilaLink>
  );
}

export function sesionNumeros(s) {
  return [
    s.reunion != null && `${s.reunion}ª reunión`,
    s.numero_sesion != null && `${s.numero_sesion}ª sesión`,
    s.periodo != null && `período ${s.periodo}`,
  ].filter(Boolean).join(' · ');
}

export function sesionConteo(s) {
  if (s.camara === 'S' || s.votaciones) return `${s.votaciones} ${s.votaciones === 1 ? 'votación' : 'votaciones'}`;
  return `${s.asuntos} ${s.asuntos === 1 ? 'asunto tratado' : 'asuntos tratados'}`;
}

export function SesionRow({ s, i = 0, children }) {
  const href = `/congreso/sesiones/${s.id}`;
  return (
    <FilaLink href={href} i={i}>
      <div className="flex items-start gap-3">
        <div className="w-1 self-stretch rounded-full shrink-0 opacity-70 group-hover:opacity-100 transition-opacity" style={{ backgroundColor: CAMARAS[s.camara]?.color }} />
        <div className="flex-1 min-w-0">
          <div className="flex flex-wrap items-center gap-2 mb-0.5">
            <CamaraBadge camara={s.camara} />
            {/* La agenda de recinto ya trae sesiones convocadas: "0 asuntos
                tratados" de algo que todavía no pasó confunde. */}
            {s.fecha > hoyKey()
              ? <Badge tint="tint-purple">convocada</Badge>
              : <span className="text-[10px] text-text-tertiary font-mono">{sesionConteo(s)}</span>}
            <span className="text-[10px] text-text-tertiary font-mono ml-auto flex items-center gap-1">
              <Clock size={9} /> {formatFecha(s.fecha)}
            </span>
          </div>
          <h4 className="text-[13px] font-semibold text-text-primary group-hover:text-celeste-bright transition-colors" style={H3_STYLE}>
            <Link href={href}>{nombrePropio(s.tipo) || 'Sesión'}</Link>
          </h4>
          {sesionNumeros(s) && <p className="text-[10px] text-text-tertiary font-mono mt-0.5">{sesionNumeros(s)}</p>}
          {children}
        </div>
        <ArrowRight size={12} className="text-text-tertiary group-hover:text-celeste group-hover:translate-x-0.5 shrink-0 mt-2 transition-all" />
      </div>
    </FilaLink>
  );
}

export function ReunionRow({ r, conCamara = true, conFecha = false, i = 0 }) {
  const [abierto, setAbierto] = useState(false);
  const temario = textoLegible(r.temario?.trim());
  const largo = temario && temario.length > 220;
  return (
    <div
      className="border-b border-border-light py-3.5 transition-colors duration-300 hover:bg-celeste/[0.03] animate-fade-in"
      style={{ animationDelay: `${Math.min(i * 30, 300)}ms`, animationFillMode: 'both' }}
    >
      <div className="flex items-start gap-3">
        <span className="font-mono text-[12px] font-bold text-celeste tabular-nums shrink-0 w-11 pt-px">
          {formatHora(r.fecha_hora) || '—'}
        </span>
        <div className="flex-1 min-w-0">
          <div className="flex flex-wrap items-center gap-2 mb-0.5">
            {conCamara && <CamaraBadge camara={r.camara} />}
            {r.tipo && <Badge>{r.tipo}</Badge>}
            {conFecha && <span className="text-[10px] text-text-tertiary font-mono">{formatFecha(r.fecha_hora)}</span>}
          </div>
          <h4 className="text-[13px] font-semibold text-text-primary break-words" style={H3_STYLE}>
            {nombreComision(r.comision) || 'Reunión de comisión'}
          </h4>
          {r.sala && (
            <p className="text-[10px] text-text-tertiary flex items-center gap-1 mt-0.5"><MapPin size={9} /> {nombrePropio(r.sala)}</p>
          )}
          {temario && (
            <p className="text-[12px] text-text-secondary leading-relaxed mt-1.5 break-words">
              {largo && !abierto ? `${temario.slice(0, 220).trimEnd()}…` : temario}
              {largo && (
                <button onClick={() => setAbierto(!abierto)} className="ml-1.5 text-[11px] text-celeste hover:text-celeste-bright">
                  {abierto ? 'ver menos' : 'ver más'}
                </button>
              )}
            </p>
          )}
          <ProyectosLinks proyectos={r.proyectos} compacto />
          {r.url_citacion && (
            <a href={r.url_citacion} target="_blank" rel="noreferrer" className="textlink inline-flex items-center gap-1 text-[11px] mt-1.5">
              <FileText size={10} /> Citación <span className="arrow">→</span>
            </a>
          )}
        </div>
      </div>
    </div>
  );
}

/* ── Filtros y paginado ──────────────────────────────────────── */

export function CamaraChips({ value, onChange, conTodas = true }) {
  const opciones = [...(conTodas ? [['', 'Las dos']] : []), ['S', 'Senado'], ['D', 'Diputados']];
  return (
    <div className="flex flex-wrap gap-1.5" role="group" aria-label="Cámara">
      {opciones.map(([k, label]) => (
        <button
          key={k || 'todas'}
          type="button"
          onClick={() => onChange(k)}
          aria-pressed={value === k}
          className={`px-3 py-1 rounded-full text-[11px] font-medium border transition-colors ${
            value === k
              ? 'bg-celeste/10 text-celeste-bright border-celeste/40'
              : 'text-text-secondary border-border-light hover:border-celeste/30 hover:text-text-primary'
          }`}
        >
          {label}
        </button>
      ))}
    </div>
  );
}

export function Paginado({ page, onOffset, unidad = 'resultados' }) {
  if (!page || !page.total) return null;
  const { total, limit, offset } = page;
  const desde = offset + 1;
  const hasta = Math.min(offset + (page.items?.length || 0), total);
  return (
    <div className="flex items-center justify-between gap-3 mt-4">
      <p className="text-[11px] text-text-tertiary font-mono">
        {desde.toLocaleString('es-AR')}–{hasta.toLocaleString('es-AR')} de {total.toLocaleString('es-AR')} {unidad}
      </p>
      {total > limit && (
        <div className="flex gap-1.5">
          <button
            type="button"
            disabled={offset === 0}
            onClick={() => onOffset(Math.max(0, offset - limit))}
            className="p-1.5 rounded-lg border border-border-light text-text-secondary hover:text-celeste hover:border-celeste/30 disabled:opacity-30 disabled:pointer-events-none transition-colors"
            aria-label="Página anterior"
          >
            <ChevronLeft size={14} />
          </button>
          <button
            type="button"
            disabled={offset + limit >= total}
            onClick={() => onOffset(offset + limit)}
            className="p-1.5 rounded-lg border border-border-light text-text-secondary hover:text-celeste hover:border-celeste/30 disabled:opacity-30 disabled:pointer-events-none transition-colors"
            aria-label="Página siguiente"
          >
            <ChevronRight size={14} />
          </button>
        </div>
      )}
    </div>
  );
}

/** true en pantallas angostas: el gráfico por bloque achica el eje y los nombres. */
export function useAngosto(px = 640) {
  const [angosto, setAngosto] = useState(false);
  useEffect(() => {
    const mq = window.matchMedia(`(max-width: ${px - 1}px)`);
    const upd = () => setAngosto(mq.matches);
    upd();
    mq.addEventListener('change', upd);
    return () => mq.removeEventListener('change', upd);
  }, [px]);
  return angosto;
}

/**
 * Carga una lista paginada de la API. `params` se serializa para el efecto:
 * cambiar un filtro vuelve a pedir desde el offset que venga en params.
 */
export function useLista(fetcher, params) {
  const [page, setPage] = useState(null);
  const [error, setError] = useState(false);
  const [loading, setLoading] = useState(true);
  const key = JSON.stringify(params);
  useEffect(() => {
    let vivo = true;
    setLoading(true);
    setError(false);
    fetcher(JSON.parse(key))
      .then((d) => vivo && setPage(d))
      .catch(() => vivo && (setError(true), setPage(null)))
      .finally(() => vivo && setLoading(false));
    return () => { vivo = false; };
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [key]);
  return { page, error, loading };
}
