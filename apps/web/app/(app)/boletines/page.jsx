'use client';

import { useState, useEffect } from 'react';
import { useRouter } from 'next/navigation';
import { api } from '@/lib/api';
import { Landmark } from 'lucide-react';
import FadeIn from '@/components/FadeIn';
import { Edicion } from '@/components/Edicion';

// Cada jurisdicción = el/los código(s) de fuente de su Boletín Oficial.
const JURIS = [
  {
    key: 'Nacional',
    label: 'Nacional',
    source: 'bora_primera,infoleg',
    desc: 'Boletín Oficial de la República Argentina',
  },
  {
    key: 'PBA',
    label: 'PBA',
    source: 'bopba',
    desc: 'Boletín Oficial de la Provincia de Buenos Aires',
  },
  {
    key: 'CABA',
    label: 'CABA',
    source: 'bocaba',
    desc: 'Boletín Oficial de la Ciudad de Buenos Aires',
  },
];

export default function BoletinesPage() {
  const router = useRouter();
  const [activo, setActivo] = useState('Nacional');
  const [ediciones, setEdiciones] = useState([]);
  const [hasMore, setHasMore] = useState(false);
  const [offsetDias, setOffsetDias] = useState(0);
  const [loading, setLoading] = useState(true);

  const jur = JURIS.find((j) => j.key === activo);

  useEffect(() => {
    if (jur.soon) {
      setEdiciones([]);
      setHasMore(false);
      setLoading(false);
      return;
    }
    setLoading(true);
    api
      .ediciones({ dias: 5, offset_dias: offsetDias, source: jur.source })
      .then((d) => {
        setEdiciones((prev) => (offsetDias === 0 ? d.ediciones : [...prev, ...d.ediciones]));
        setHasMore(d.has_more);
      })
      .catch(() => { setEdiciones([]); setHasMore(false); })
      .finally(() => setLoading(false));
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [activo, offsetDias]);

  const cambiar = (key) => {
    setOffsetDias(0);
    setEdiciones([]);
    setLoading(true);
    setActivo(key);
  };

  return (
    <div className="max-w-4xl mx-auto">
      <FadeIn>
        <div className="mb-7 pt-2">
          <p className="eyebrow mb-1">
            <span className="eyebrow-num">VIGÍA / BOLETINES</span>
            <span className="ml-2">Oficiales por jurisdicción</span>
          </p>
          <h2 className="display-section text-text-primary mb-1">Boletines <em>oficiales.</em></h2>
          <p className="text-[13px] text-text-tertiary font-mono">{jur.desc} · actualización diaria</p>
        </div>
      </FadeIn>

      {/* Selector de jurisdicción */}
      <FadeIn delay={80}>
        <div className="mb-6 border-t-2 border-text-primary/70 pt-4">
          <p className="eyebrow mb-2"><span className="eyebrow-num">JURISDICCIÓN</span></p>
          <div className="flex flex-wrap gap-2">
            {JURIS.map((j) => (
              <button
                key={j.key}
                onClick={() => !j.soon && cambiar(j.key)}
                disabled={j.soon}
                className={`px-4 py-2 rounded-lg text-[13px] font-semibold border transition-all duration-200 ${
                  activo === j.key
                    ? 'bg-celeste/10 text-celeste-bright border-celeste/40'
                    : j.soon
                      ? 'text-text-tertiary/50 border-border-light cursor-not-allowed'
                      : 'text-text-secondary border-border-light hover:border-celeste/30 hover:text-text-primary'
                }`}
              >
                {j.label}
                {j.soon && (
                  <span className="ml-1.5 text-[9px] uppercase tracking-wider text-sol/80 font-mono">pronto</span>
                )}
              </button>
            ))}
          </div>
        </div>
      </FadeIn>

      {jur.soon ? (
        <div className="text-center py-20 border-t border-border-light">
          <Landmark size={28} className="mx-auto text-text-tertiary/40 mb-3" />
          <p className="text-[14px] text-text-secondary font-semibold mb-1">
            {jur.desc} — próximamente
          </p>
          <p className="text-[12px] text-text-tertiary max-w-md mx-auto">
            Estamos sumando la ingesta de esta jurisdicción. Pronto vas a poder seguir sus ediciones acá.
          </p>
        </div>
      ) : loading && ediciones.length === 0 ? (
        <div className="py-20 text-center">
          <p className="text-text-tertiary text-sm font-mono animate-pulse">Cargando el Boletín…</p>
        </div>
      ) : ediciones.length === 0 ? (
        <div className="text-center py-16">
          <p className="text-text-tertiary text-sm">Sin ediciones recientes en esta jurisdicción.</p>
        </div>
      ) : (
        <div>
          {ediciones.map((ed) => (
            <Edicion key={ed.fecha} edicion={ed} onOpen={(id) => router.push(`/norma/${id}`)} />
          ))}
        </div>
      )}

      {hasMore && !loading && !jur.soon && (
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
