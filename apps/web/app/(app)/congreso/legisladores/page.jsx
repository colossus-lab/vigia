'use client';

import { Suspense, useMemo, useState } from 'react';
import Link from 'next/link';
import { useSearchParams } from 'next/navigation';
import { ArrowRight, Search } from 'lucide-react';
import { api } from '@/lib/api';
import FadeIn from '@/components/FadeIn';
import { CAMARAS, nombrePropio, mandato, composicionPorBloque, filtrarLegisladores } from '@/lib/congreso';
import {
  PageHeader, CamaraChips, Cargando, Vacio, ErrorCarga, SectionTitle, INPUT_CLS, LABEL_CLS, ROW_CLS, H3_STYLE, useLista,
} from '@/components/congreso/ui';

const SELECT_CLS = INPUT_CLS;

function Composicion({ items, camara, bloque, onBloque }) {
  const filas = composicionPorBloque(items, 10);
  const max = filas[0]?.cantidad || 1;
  return (
    <div className="space-y-1.5">
      {filas.map((f) => {
        const activo = bloque === f.bloque;
        const clickeable = !f.resto;
        return (
          <button
            key={f.bloque}
            type="button"
            disabled={!clickeable}
            onClick={() => onBloque(activo ? '' : f.bloque)}
            className={`w-full grid grid-cols-[minmax(0,1fr)_minmax(0,1.3fr)_2rem] items-center gap-3 text-left group ${clickeable ? '' : 'cursor-default'}`}
          >
            <span className={`text-[11px] truncate transition-colors ${activo ? 'text-celeste-bright font-semibold' : 'text-text-secondary group-hover:text-text-primary'}`}>
              {nombrePropio(f.bloque)}
            </span>
            <span className="h-2 rounded-full bg-border-light overflow-hidden">
              <span className="block h-full rounded-full transition-all" style={{ width: `${(f.cantidad / max) * 100}%`, backgroundColor: activo ? '#93C5F8' : CAMARAS[camara].color, opacity: f.resto ? 0.4 : 0.85 }} />
            </span>
            <span className="text-[11px] font-mono text-text-tertiary text-right tabular-nums">{f.cantidad}</span>
          </button>
        );
      })}
    </div>
  );
}

function Legisladores() {
  const sp = useSearchParams();
  const [camara, setCamara] = useState(sp.get('camara') === 'D' ? 'D' : 'S');
  const [bloque, setBloque] = useState('');
  const [distrito, setDistrito] = useState('');
  const [q, setQ] = useState('');

  // Una cámara entera entra en una página (contrato: limit hasta 300), así que
  // los filtros corren en el browser y responden al tipear.
  const { page, error, loading } = useLista(api.congresoLegisladores, { camara, limit: 300 });
  const items = page?.items || [];

  const bloques = useMemo(() => [...new Set(items.map((l) => l.bloque).filter(Boolean))].sort(), [items]);
  const distritos = useMemo(() => [...new Set(items.map((l) => l.distrito).filter(Boolean))].sort(), [items]);
  const filas = filtrarLegisladores(items, { q, bloque, distrito });

  const cambiarCamara = (c) => { setCamara(c); setBloque(''); setDistrito(''); };

  return (
    <div>
      <FadeIn>
        <PageHeader
          eyebrow="CONGRESO"
          sub="Senadores y diputados en funciones"
          titulo={<>Las bancas, <em>una por una.</em></>}
          bajada="bloque · distrito · mandato · presentismo y alineamiento (Senado)"
        />
      </FadeIn>

      <FadeIn delay={60}>
        <div className="mb-8">
          <CamaraChips value={camara} onChange={cambiarCamara} conTodas={false} />
        </div>
      </FadeIn>

      {loading && <Cargando />}
      {!loading && error && <ErrorCarga />}
      {!loading && !error && items.length === 0 && <Vacio>Todavía no hay legisladores cargados para esta cámara.</Vacio>}

      {!loading && !error && items.length > 0 && (
        <div className="grid grid-cols-1 lg:grid-cols-[1fr_1.5fr] gap-x-10 gap-y-10">
          <section className="min-w-0">
            <SectionTitle num="I." eyebrow={`${items.length} bancas`}>
              La <em className="text-sol italic">composición.</em>
            </SectionTitle>
            <Composicion items={items} camara={camara} bloque={bloque} onBloque={setBloque} />
            <p className="text-[10px] text-text-tertiary mt-3">Tocá un bloque para filtrar la lista.</p>
          </section>

          <section className="min-w-0">
            <div className="grid grid-cols-1 sm:grid-cols-3 gap-4 mb-4">
              <div className="relative">
                <label className={LABEL_CLS} htmlFor="le-q">Nombre</label>
                <Search size={12} className="absolute left-1 bottom-2.5 text-text-tertiary" />
                <input id="le-q" value={q} onChange={(e) => setQ(e.target.value)} placeholder="Buscar" className={`${INPUT_CLS} pl-5`} />
              </div>
              <div>
                <label className={LABEL_CLS} htmlFor="le-bloque">Bloque</label>
                <select id="le-bloque" value={bloque} onChange={(e) => setBloque(e.target.value)} className={SELECT_CLS}>
                  <option value="">Todos</option>
                  {bloques.map((b) => <option key={b} value={b}>{nombrePropio(b)}</option>)}
                </select>
              </div>
              <div>
                <label className={LABEL_CLS} htmlFor="le-distrito">Distrito</label>
                <select id="le-distrito" value={distrito} onChange={(e) => setDistrito(e.target.value)} className={SELECT_CLS}>
                  <option value="">Todos</option>
                  {distritos.map((d) => <option key={d} value={d}>{nombrePropio(d)}</option>)}
                </select>
              </div>
            </div>
            <div className="border-t border-border-light">
              {filas.length === 0 && <Vacio>Nadie coincide con esos filtros.</Vacio>}
              {filas.map((l) => (
                <Link key={l.id} href={`/congreso/legisladores/${l.id}`} className={ROW_CLS}>
                  <div className="flex items-center gap-3">
                    <div className="flex-1 min-w-0">
                      <h4 className="text-[13px] font-semibold text-text-primary group-hover:text-celeste-bright transition-colors break-words" style={H3_STYLE}>
                        {nombrePropio(l.nombre)}
                      </h4>
                      <p className="text-[10px] text-text-tertiary break-words">
                        {[nombrePropio(l.bloque), nombrePropio(l.distrito)].filter(Boolean).join(' · ')}
                      </p>
                    </div>
                    {mandato(l) && <span className="text-[10px] font-mono text-text-tertiary shrink-0 hidden sm:inline">{mandato(l)}</span>}
                    <ArrowRight size={12} className="text-text-tertiary group-hover:text-celeste group-hover:translate-x-0.5 shrink-0 transition-all" />
                  </div>
                </Link>
              ))}
            </div>
            <p className="text-[11px] text-text-tertiary font-mono mt-3">{filas.length} de {items.length} {CAMARAS[camara].legisladores}</p>
          </section>
        </div>
      )}
    </div>
  );
}

export default function LegisladoresPage() {
  return (
    <Suspense fallback={<Cargando />}>
      <Legisladores />
    </Suspense>
  );
}
