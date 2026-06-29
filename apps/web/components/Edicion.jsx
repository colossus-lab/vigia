'use client';

import { useState } from 'react';
import { Clock, ArrowRight, Building2, Tag } from 'lucide-react';
import { TIPOS_NORMA } from '@/lib/constants';

export const TIPO_TINT = {
  DNU: 'tint-red', DECRETO: 'tint-amber', LEY: 'tint-green', RESOLUCION: 'tint-blue',
  DISPOSICION: 'tint-purple', PROYECTO: 'tint-cyan', COMUNICACION: 'tint-pink',
  CONSULTA: 'tint-orange', OTRA: 'tint-gray',
};

export const TIPO_DOT = {
  DNU: '#F87171', DECRETO: '#F6B40E', LEY: '#34D399', RESOLUCION: '#74ACDF',
  DISPOSICION: '#A78BFA', PROYECTO: '#22D3EE', COMUNICACION: '#F472B6',
  CONSULTA: '#FB923C', OTRA: '#8892A8',
};

const IMPACTO_TINT = { alto: 'tint-red', medio: 'tint-amber', bajo: 'tint-gray' };

export function NormRow({ norma, onClick, index }) {
  const tipoMeta = TIPOS_NORMA[norma.tipo] || TIPOS_NORMA.OTRA;
  return (
    <div
      onClick={onClick}
      className="group cursor-pointer border-b border-border-light py-4 transition-all duration-300 hover:bg-celeste/[0.03] hover:pl-3"
      style={{ animationDelay: `${Math.min(index * 35, 400)}ms` }}
    >
      <div className="flex items-start gap-3">
        <div className="w-1 self-stretch rounded-full shrink-0 opacity-70 group-hover:opacity-100 transition-opacity" style={{ backgroundColor: TIPO_DOT[norma.tipo] || TIPO_DOT.OTRA }} />
        <div className="flex-1 min-w-0">
          <div className="flex flex-wrap items-center gap-2 mb-1.5">
            <span className={`px-2 py-0.5 rounded-full text-[9px] font-semibold uppercase tracking-wide border ${TIPO_TINT[norma.tipo] || TIPO_TINT.OTRA}`}>
              {tipoMeta.label}{norma.numero ? ` ${norma.numero}` : ''}
            </span>
            {norma.emisor && (
              <span className="px-2 py-0.5 rounded-full text-[9px] font-bold tracking-wide border tint-blue font-mono">
                {norma.emisor}
              </span>
            )}
            {norma.impacto && (
              <span className={`px-2 py-0.5 rounded-full text-[9px] font-medium border ${IMPACTO_TINT[norma.impacto]}`}>
                impacto {norma.impacto}
              </span>
            )}
            {norma.fecha_publicacion && (
              <span className="text-[10px] text-text-tertiary ml-auto flex items-center gap-1 font-mono shrink-0">
                <Clock size={9} /> {norma.fecha_publicacion}
              </span>
            )}
          </div>

          <h3 className="text-[14px] font-semibold text-text-primary leading-snug mb-1 group-hover:text-celeste-bright transition-colors" style={{ fontFamily: 'var(--font-display)' }}>
            {norma.titulo}
          </h3>

          {(norma.resumen_ia || norma.resumen) && (
            <p className="text-[12px] text-text-secondary leading-relaxed line-clamp-2 mb-1.5">{norma.resumen_ia || norma.resumen}</p>
          )}

          <div className="flex flex-wrap items-center gap-3 text-[10px] text-text-tertiary">
            {norma.organismo && <span className="flex items-center gap-1 truncate max-w-[280px]"><Building2 size={10} /> {norma.organismo}</span>}
            {norma.sector && <span className="flex items-center gap-1"><Tag size={10} /> {norma.sector}</span>}
            <span className="ml-auto flex items-center gap-1 text-celeste font-medium opacity-0 group-hover:opacity-100 transition-all shrink-0">
              Ver detalle <ArrowRight size={10} className="group-hover:translate-x-0.5 transition-transform" />
            </span>
          </div>
        </div>
      </div>
    </div>
  );
}

export function fmtEdicionFecha(iso) {
  const d = new Date(`${iso}T12:00:00`);
  const s = d.toLocaleDateString('es-AR', { weekday: 'long', day: 'numeric', month: 'long' });
  return s.charAt(0).toUpperCase() + s.slice(1);
}

export function resumenEdicion(ed) {
  const partes = Object.entries(ed.resumen || {})
    .filter(([t]) => t !== 'OTRA')
    .sort((a, b) => b[1] - a[1])
    .slice(0, 4)
    .map(([t, c]) => `${c} ${(TIPOS_NORMA[t]?.label || t).toLowerCase()}${c !== 1 ? (t === 'LEY' ? 'es' : 's') : ''}`);
  return partes.join(' · ');
}

/* Una edición del diario: header del día + destacados + trámite colapsado */
export function Edicion({ edicion, onOpen }) {
  const [verTramite, setVerTramite] = useState(false);
  const tramiteCount = edicion.tramite_total || 0;

  return (
    <section className="mb-10">
      <div className="flex flex-wrap items-baseline justify-between gap-2 border-t-2 border-text-primary/70 pt-3 mb-1">
        <h3 className="text-[16px] font-bold text-text-primary" style={{ fontFamily: 'var(--font-display)' }}>
          {fmtEdicionFecha(edicion.fecha)}
        </h3>
        <p className="text-[10px] text-text-tertiary font-mono">{resumenEdicion(edicion)}</p>
      </div>

      {edicion.destacados.map((norma, i) => (
        <div key={norma.id} className="animate-fade-in" style={{ animationDelay: `${Math.min(i * 30, 300)}ms`, animationFillMode: 'both' }}>
          <NormRow norma={norma} index={i} onClick={() => onOpen(norma.id)} />
        </div>
      ))}
      {edicion.destacados.length === 0 && tramiteCount === 0 && (
        <p className="text-[12px] text-text-tertiary py-4">Sin publicaciones.</p>
      )}
      {edicion.destacados_total > edicion.destacados.length && (
        <p className="text-[11px] text-text-tertiary font-mono py-2">
          +{edicion.destacados_total - edicion.destacados.length} destacados más en el Buscador
        </p>
      )}

      {tramiteCount > 0 && (
        <div className="mt-1">
          <button
            onClick={() => setVerTramite((v) => !v)}
            className="group w-full flex items-center gap-2 py-2.5 text-left text-[12px] text-text-tertiary hover:text-text-secondary transition-colors"
          >
            <span className={`inline-block transition-transform duration-200 ${verTramite ? 'rotate-90' : ''}`}>▸</span>
            <span className="font-mono">{tramiteCount} de trámite</span>
            <span className="hidden sm:inline">— edictos, designaciones y ceremoniales</span>
            <span className="flex-1 border-b border-dashed border-border-light group-hover:border-border-medium transition-colors" />
          </button>
          {verTramite && (
            <div className="border-l border-border-light ml-1 mb-2">
              {edicion.tramite.map((n) => (
                <div
                  key={n.id}
                  onClick={() => onOpen(n.id)}
                  className="flex items-center gap-2 pl-4 py-1.5 cursor-pointer text-[12px] text-text-secondary hover:text-text-primary hover:bg-celeste/[0.03] transition-colors"
                >
                  <span className="w-1.5 h-1.5 rounded-full shrink-0" style={{ backgroundColor: TIPO_DOT[n.tipo] || TIPO_DOT.OTRA, opacity: 0.6 }} />
                  <span className="truncate">{n.titulo}</span>
                  {n.organismo && <span className="text-[10px] text-text-tertiary shrink-0 hidden md:inline truncate max-w-[180px]">{n.organismo}</span>}
                </div>
              ))}
              {edicion.tramite_total > edicion.tramite.length && (
                <p className="pl-4 py-1.5 text-[10px] text-text-tertiary font-mono">
                  +{edicion.tramite_total - edicion.tramite.length} más
                </p>
              )}
            </div>
          )}
        </div>
      )}
    </section>
  );
}
