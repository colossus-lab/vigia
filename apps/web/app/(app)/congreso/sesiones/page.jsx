'use client';

import { Suspense, useState } from 'react';
import { useSearchParams } from 'next/navigation';
import { api } from '@/lib/api';
import FadeIn from '@/components/FadeIn';
import {
  PageHeader, CamaraChips, SesionRow, Cargando, Vacio, ErrorCarga, Paginado, LABEL_CLS, INPUT_CLS, useLista,
} from '@/components/congreso/ui';

const LIMIT = 20;

function Sesiones() {
  const sp = useSearchParams();
  const [camara, setCamara] = useState(['S', 'D'].includes(sp.get('camara')) ? sp.get('camara') : '');
  const [desde, setDesde] = useState('');
  const [hasta, setHasta] = useState('');
  const [offset, setOffset] = useState(0);

  const { page, error, loading } = useLista(api.congresoSesiones, {
    camara: camara || undefined,
    desde: desde || undefined,
    hasta: hasta || undefined,
    limit: LIMIT,
    offset,
  });
  const cambiar = (set) => (v) => { set(v); setOffset(0); };

  return (
    <div>
      <FadeIn>
        <PageHeader
          eyebrow="CONGRESO"
          sub="Sesiones en el recinto"
          titulo={<>Lo que se trató <em>en el recinto.</em></>}
          bajada="Senado: votaciones de cada sesión · Diputados: asuntos tratados y su resultado"
        />
      </FadeIn>

      <FadeIn delay={60}>
        <div className="flex flex-wrap items-end justify-between gap-4 mb-8">
          <CamaraChips value={camara} onChange={cambiar(setCamara)} />
          <div className="grid grid-cols-2 gap-4 w-full sm:w-auto">
            <div>
              <label className={LABEL_CLS} htmlFor="se-desde">Desde</label>
              <input id="se-desde" type="date" value={desde} onChange={(e) => cambiar(setDesde)(e.target.value)} className={`${INPUT_CLS} [color-scheme:dark]`} />
            </div>
            <div>
              <label className={LABEL_CLS} htmlFor="se-hasta">Hasta</label>
              <input id="se-hasta" type="date" value={hasta} onChange={(e) => cambiar(setHasta)(e.target.value)} className={`${INPUT_CLS} [color-scheme:dark]`} />
            </div>
          </div>
        </div>
      </FadeIn>

      <div className="border-t border-border-light">
        {loading && <Cargando />}
        {!loading && error && <ErrorCarga />}
        {!loading && !error && page?.items?.length === 0 && (
          <Vacio>{desde || hasta ? 'No hubo sesiones en ese rango de fechas.' : 'Todavía no hay sesiones cargadas.'}</Vacio>
        )}
        {!loading && !error && (page?.items || []).map((s, i) => <SesionRow key={s.id} s={s} i={i} />)}
      </div>
      {!loading && <Paginado page={page} onOffset={setOffset} unidad="sesiones" />}
    </div>
  );
}

export default function SesionesPage() {
  return (
    <Suspense fallback={<Cargando />}>
      <Sesiones />
    </Suspense>
  );
}
