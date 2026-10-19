'use client';

import { Suspense, useState } from 'react';
import { useSearchParams } from 'next/navigation';
import { Search, Info } from 'lucide-react';
import { api } from '@/lib/api';
import FadeIn from '@/components/FadeIn';
import { agruparPorDia, tituloDia, sumarDias, hoyKey } from '@/lib/congreso';
import {
  PageHeader, CamaraChips, ReunionRow, Cargando, Vacio, ErrorCarga, Paginado, Nota,
  INPUT_CLS, LABEL_CLS, useLista,
} from '@/components/congreso/ui';

const RANGOS = [
  [7, 'Próximos 7 días'],
  [14, 'Próximos 14 días'],
  [30, 'Próximos 30 días'],
];
const LIMIT = 50;

function Agenda() {
  const sp = useSearchParams();
  const [camara, setCamara] = useState(['S', 'D'].includes(sp.get('camara')) ? sp.get('camara') : '');
  const [dias, setDias] = useState(7);
  const [comision, setComision] = useState('');
  const [q, setQ] = useState('');
  // Lo que se busca: los inputs de texto se aplican al enviar, no por tecla.
  const [aplicado, setAplicado] = useState({ comision: '', q: '' });
  const [offset, setOffset] = useState(0);

  const { page, error, loading } = useLista(api.congresoAgenda, {
    camara: camara || undefined,
    hasta: sumarDias(hoyKey(), dias),
    comision: aplicado.comision || undefined,
    q: aplicado.q || undefined,
    limit: LIMIT,
    offset,
  });

  const cambiar = (set) => (v) => { set(v); setOffset(0); };
  const submit = (e) => {
    e.preventDefault();
    setAplicado({ comision: comision.trim(), q: q.trim() });
    setOffset(0);
  };

  const grupos = agruparPorDia(page?.items);
  const filtrando = aplicado.comision || aplicado.q;

  return (
    <div>
      <FadeIn>
        <PageHeader
          eyebrow="CONGRESO"
          sub="Agenda de comisiones"
          titulo={<>Lo que se viene, <em>día por día.</em></>}
          bajada="citaciones de las comisiones del Senado y de Diputados"
        />
      </FadeIn>

      <FadeIn delay={60}>
        <form onSubmit={submit} className="mb-8 space-y-5">
          <div className="flex flex-wrap items-center justify-between gap-3">
            <CamaraChips value={camara} onChange={cambiar(setCamara)} />
            <select
              value={dias}
              onChange={(e) => cambiar(setDias)(Number(e.target.value))}
              className="bg-transparent border border-border-light rounded-lg px-2 py-1 text-[11px] text-text-secondary focus:outline-none focus:border-celeste"
              aria-label="Rango de días"
            >
              {RANGOS.map(([n, label]) => <option key={n} value={n}>{label}</option>)}
            </select>
          </div>
          <div className="grid grid-cols-1 md:grid-cols-[1fr_1fr_auto] gap-4 items-end">
            <div>
              <label className={LABEL_CLS} htmlFor="ag-comision">Comisión</label>
              <input id="ag-comision" value={comision} onChange={(e) => setComision(e.target.value)} placeholder="p. ej. presupuesto" className={INPUT_CLS} />
            </div>
            <div>
              <label className={LABEL_CLS} htmlFor="ag-q">Tema del temario</label>
              <input id="ag-q" value={q} onChange={(e) => setQ(e.target.value)} placeholder="p. ej. jubilaciones" className={INPUT_CLS} />
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

      {loading && <Cargando />}
      {!loading && error && <ErrorCarga />}
      {!loading && !error && grupos.length === 0 && (
        <Vacio>
          {filtrando
            ? 'Ninguna reunión coincide con la búsqueda en este rango. Probá con otra comisión o ampliá los días.'
            : 'No hay reuniones de comisión cargadas en este rango. Las cámaras publican la agenda semana a semana: lo habitual es que se vea solo la semana en curso.'}
        </Vacio>
      )}
      {!loading && !error && grupos.map((g) => (
        <section key={g.dia} className="mb-6">
          <h3 className="text-[11px] font-mono uppercase tracking-[0.12em] text-sol py-2 border-b-2 border-text-primary/70">
            {tituloDia(g.dia)} <span className="text-text-tertiary ml-1">· {g.items.length}</span>
          </h3>
          {g.items.map((r, i) => <ReunionRow key={r.id} r={r} i={i} conCamara={!camara} />)}
        </section>
      ))}
      {!loading && <Paginado page={page} onOffset={setOffset} unidad="reuniones" />}

      <div className="mt-10">
        <Nota icon={Info}>
          Cuando una reunión se suspende o se reprograma, la cámara la saca de su agenda y acá desaparece
          también. Los proyectos linkeados salen del cruce por número de expediente con el temario.
        </Nota>
      </div>
    </div>
  );
}

export default function AgendaPage() {
  return (
    <Suspense fallback={<Cargando />}>
      <Agenda />
    </Suspense>
  );
}
