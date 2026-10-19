'use client';

import { Suspense, useState } from 'react';
import Link from 'next/link';
import { useSearchParams } from 'next/navigation';
import { Search, Info } from 'lucide-react';
import { api } from '@/lib/api';
import FadeIn from '@/components/FadeIn';
import {
  PageHeader, CamaraChips, VotacionRow, Cargando, Vacio, ErrorCarga, Paginado, Nota,
  INPUT_CLS, LABEL_CLS, useLista,
} from '@/components/congreso/ui';

const LIMIT = 20;

function Votaciones() {
  const sp = useSearchParams();
  const [camara, setCamara] = useState(['S', 'D'].includes(sp.get('camara')) ? sp.get('camara') : '');
  const [resultado, setResultado] = useState('');
  const [q, setQ] = useState(sp.get('q') || '');
  const [expediente, setExpediente] = useState(sp.get('expediente') || '');
  const [aplicado, setAplicado] = useState({ q: sp.get('q') || '', expediente: sp.get('expediente') || '' });
  const [offset, setOffset] = useState(0);

  const { page, error, loading } = useLista(api.congresoVotaciones, {
    camara: camara || undefined,
    resultado: resultado || undefined,
    q: aplicado.q || undefined,
    expediente: aplicado.expediente || undefined,
    limit: LIMIT,
    offset,
  });

  const cambiar = (set) => (v) => { set(v); setOffset(0); };
  const submit = (e) => {
    e.preventDefault();
    setAplicado({ q: q.trim(), expediente: expediente.trim() });
    setOffset(0);
  };
  const filtrando = aplicado.q || aplicado.expediente || resultado;

  return (
    <div>
      <FadeIn>
        <PageHeader
          eyebrow="CONGRESO"
          sub="Votaciones nominales"
          titulo={<>Quién votó <em>qué.</em></>}
          bajada="actas del Senado desde 2008 · resultado, totales y voto por bloque"
        />
      </FadeIn>

      <FadeIn delay={60}>
        <form onSubmit={submit} className="mb-8 space-y-5">
          <div className="flex flex-wrap items-center justify-between gap-3">
            <CamaraChips value={camara} onChange={cambiar(setCamara)} />
            <select
              value={resultado}
              onChange={(e) => cambiar(setResultado)(e.target.value)}
              className="bg-transparent border border-border-light rounded-lg px-2 py-1 text-[11px] text-text-secondary focus:outline-none focus:border-celeste"
              aria-label="Resultado"
            >
              <option value="">Cualquier resultado</option>
              <option value="afirmativo">Afirmativo</option>
              <option value="negativo">Negativo</option>
            </select>
          </div>
          <div className="grid grid-cols-1 md:grid-cols-[1fr_220px_auto] gap-4 items-end">
            <div>
              <label className={LABEL_CLS} htmlFor="vo-q">Tema</label>
              <input id="vo-q" value={q} onChange={(e) => setQ(e.target.value)} placeholder="p. ej. presupuesto, ganancias" className={INPUT_CLS} />
            </div>
            <div>
              <label className={LABEL_CLS} htmlFor="vo-exp">Expediente</label>
              <input id="vo-exp" value={expediente} onChange={(e) => setExpediente(e.target.value)} placeholder="0010-PE-2026 o CD-12/26" className={`${INPUT_CLS} font-mono`} />
            </div>
            <button
              type="submit"
              className="flex items-center justify-center gap-1.5 text-[12px] font-medium text-celeste border border-celeste/30 rounded-lg px-4 py-2 hover:bg-celeste/10 transition-colors"
            >
              <Search size={12} /> Buscar
            </button>
          </div>
        </form>
      </FadeIn>

      {camara === 'D' && (
        <div className="mb-6">
          <Nota icon={Info}>
            Diputados no publica el voto nominal en datos abiertos (el dataset se cortó en 2020) y su sitio de
            votaciones está detrás de un reCAPTCHA. De Diputados mostramos el resultado de cada asunto tratado,
            en <Link href="/congreso/sesiones?camara=D" className="text-celeste hover:text-celeste-bright">sus sesiones</Link>.
          </Nota>
        </div>
      )}

      <div className="border-t border-border-light">
        {loading && <Cargando />}
        {!loading && error && <ErrorCarga />}
        {!loading && !error && page?.items?.length === 0 && (
          <Vacio>
            {filtrando
              ? 'Ninguna votación coincide con la búsqueda. Probá con otras palabras o con el expediente en otra forma.'
              : 'Todavía no hay votaciones cargadas para esta cámara.'}
          </Vacio>
        )}
        {!loading && !error && (page?.items || []).map((v, i) => <VotacionRow key={v.id} v={v} i={i} conCamara={!camara} />)}
      </div>
      {!loading && <Paginado page={page} onOffset={setOffset} unidad="votaciones" />}
    </div>
  );
}

export default function VotacionesPage() {
  return (
    <Suspense fallback={<Cargando />}>
      <Votaciones />
    </Suspense>
  );
}
