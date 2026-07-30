'use client';

import { useState, useEffect, useCallback } from 'react';
import { useSession } from 'next-auth/react';
import { SECTORES } from '@/lib/constants';
import { authedFetch, AUTH_ENABLED } from '@/lib/authClient';
import { Bell, Plus, Trash2, Power, PowerOff, Tag, Hash, Calendar, Info, Pencil, X } from 'lucide-react';
import FadeIn from '@/components/FadeIn';
import CountUp from '@/components/CountUp';

const INPUT_CLS = 'w-full bg-transparent border-b border-border-light px-1 py-2 text-[13px] text-text-primary placeholder-text-tertiary focus:outline-none focus:border-celeste transition-colors';

// Form reutilizable: alta y edición comparten markup. `initial` pre-carga
// keywords/sectores; `onSubmit` recibe el payload limpio { keywords, sectores }.
function AlertaForm({ initial, onSubmit, onCancel, submitLabel, onPreview }) {
  const [keywords, setKeywords] = useState(initial?.keywords || []);
  const [sectores, setSectores] = useState(initial?.sectores || []);
  const [draft, setDraft] = useState('');
  const [preview, setPreview] = useState(null); // { count_30d } | null

  const addKeyword = (raw) => {
    const kw = raw.trim();
    if (kw && !keywords.includes(kw)) setKeywords((p) => [...p, kw]);
    setDraft('');
  };
  const onKeyDown = (e) => {
    if (e.key === 'Enter' || e.key === ',') { e.preventDefault(); addKeyword(draft); }
    else if (e.key === 'Backspace' && !draft && keywords.length) setKeywords((p) => p.slice(0, -1));
  };
  const toggleSector = (s) =>
    setSectores((p) => (p.includes(s) ? p.filter((x) => x !== s) : [...p, s]));

  // Preview de volumen: "≈ N normas en 30 días" para el criterio actual.
  // Debounced; solo con keywords confirmadas + sectores (ignora el draft a medio
  // tipear). Mata alertas muertas (N=0) y avisa de las ruidosas antes de crearlas.
  useEffect(() => {
    if (!onPreview || (!keywords.length && !sectores.length)) { setPreview(null); return; }
    let cancel = false;
    const t = setTimeout(async () => {
      try {
        const p = await onPreview({ keywords, sectores });
        if (!cancel) setPreview(p);
      } catch { if (!cancel) setPreview(null); }
    }, 400);
    return () => { cancel = true; clearTimeout(t); };
  }, [keywords, sectores, onPreview]);

  const submit = () => {
    // Volcar lo que quede tipeado sin confirmar.
    const kws = draft.trim() && !keywords.includes(draft.trim()) ? [...keywords, draft.trim()] : keywords;
    // Válida con keywords O sectores (alerta por-sector = sin keywords).
    if (!kws.length && !sectores.length) return;
    onSubmit({ keywords: kws, sectores });
  };

  return (
    <div className="animate-slide-up border-l-2 border-celeste pl-5 py-1">
      <div className="mb-4">
        <label className="eyebrow text-[9px] block mb-2">Keywords <span className="text-text-tertiary normal-case font-normal">— Enter o coma para sumar · opcional si elegís sectores</span></label>
        <div className="flex flex-wrap items-center gap-1.5">
          {keywords.map((kw) => (
            <span key={kw} className="flex items-center gap-1 text-[11px] font-mono tint-blue border px-2 py-0.5 rounded-full">
              {kw}
              <button onClick={() => setKeywords((p) => p.filter((x) => x !== kw))} className="hover:text-status-red transition-colors"><X size={11} /></button>
            </span>
          ))}
          <input
            type="text" value={draft} onChange={(e) => setDraft(e.target.value)} onKeyDown={onKeyDown} onBlur={() => addKeyword(draft)}
            placeholder={keywords.length ? 'sumar otra…' : 'litio, ciberseguridad, SMVM…'}
            className="flex-1 min-w-[140px] bg-transparent px-1 py-1 text-[13px] text-text-primary placeholder-text-tertiary focus:outline-none"
            autoFocus
          />
        </div>
        <div className="border-b border-border-light mt-1" />
      </div>

      <div className="mb-4">
        <label className="eyebrow text-[9px] block mb-2">Sectores <span className="text-text-tertiary normal-case font-normal">— opcional, uno o varios (vacío = todos)</span></label>
        <div className="flex flex-wrap gap-1.5">
          {SECTORES.map((s) => {
            const on = sectores.includes(s);
            return (
              <button key={s} onClick={() => toggleSector(s)}
                className={`text-[11px] font-mono px-2.5 py-1 rounded-full border transition-colors ${on ? 'tint-blue' : 'text-text-tertiary border-border-light hover:text-text-secondary hover:border-text-tertiary'}`}>
                {s}
              </button>
            );
          })}
        </div>
      </div>

      {onPreview && preview && (
        <p className="text-[11px] font-mono mb-4 text-text-tertiary">
          {preview.count_30d === 0
            ? '≈ 0 normas en los últimos 30 días — criterio muy angosto, revisá las keywords'
            : `≈ ${preview.count_30d.toLocaleString('es-AR')} normas en los últimos 30 días${preview.count_30d > 200 ? ' · criterio amplio, vas a recibir bastante' : ''}`}
        </p>
      )}

      <div className="flex gap-3">
        <button onClick={submit} className="px-4 py-1.5 btn-celeste rounded-full text-[11px] font-bold">{submitLabel}</button>
        <button onClick={onCancel} className="px-3 py-1.5 text-text-secondary text-[11px] font-medium hover:text-text-primary transition-colors">Cancelar</button>
      </div>
    </div>
  );
}

export default function AlertsView() {
  const { data: session } = useSession();
  const jwt = session?.apiJwt;
  const connected = AUTH_ENABLED && Boolean(jwt);

  const [alertas, setAlertas] = useState([]);
  const [showForm, setShowForm] = useState(false);
  const [editingId, setEditingId] = useState(null);
  const [err, setErr] = useState('');

  const load = useCallback(async () => {
    if (!connected) return;
    try {
      setAlertas(await authedFetch(jwt, '/alerts'));
    } catch (e) { setErr(String(e.message || e)); }
  }, [connected, jwt]);

  // Preview de volumen para el form (solo con sesión: el endpoint pide auth).
  const previewAlerta = useCallback(
    (payload) => authedFetch(jwt, '/alerts/preview', { method: 'POST', body: JSON.stringify(payload) }),
    [jwt],
  );
  const onPreview = connected ? previewAlerta : null;

  useEffect(() => { load(); }, [load]);

  const addAlerta = async ({ keywords, sectores }) => {
    if (connected) {
      try {
        await authedFetch(jwt, '/alerts', { method: 'POST', body: JSON.stringify({ keywords, sectores }) });
        await load();
      } catch (e) { setErr(String(e.message || e)); }
    } else {
      setAlertas((prev) => [
        { id: `local-${Date.now()}`, keywords, sectores, activa: true, matches: 0, last_match_at: null },
        ...prev,
      ]);
    }
    setShowForm(false);
  };

  const saveEdit = async (a, { keywords, sectores }) => {
    if (connected) {
      try {
        await authedFetch(jwt, `/alerts/${a.id}`, { method: 'PATCH', body: JSON.stringify({ keywords, sectores }) });
        await load();
      } catch (e) { setErr(String(e.message || e)); }
    } else {
      setAlertas((prev) => prev.map((x) => (x.id === a.id ? { ...x, keywords, sectores } : x)));
    }
    setEditingId(null);
  };

  const toggleAlerta = async (a) => {
    if (connected) {
      await authedFetch(jwt, `/alerts/${a.id}`, { method: 'PATCH', body: JSON.stringify({ activa: !a.activa }) });
      load();
    } else {
      setAlertas((prev) => prev.map((x) => (x.id === a.id ? { ...x, activa: !x.activa } : x)));
    }
  };

  const deleteAlerta = async (a) => {
    if (connected) {
      await authedFetch(jwt, `/alerts/${a.id}`, { method: 'DELETE' });
      load();
    } else {
      setAlertas((prev) => prev.filter((x) => x.id !== a.id));
    }
  };

  const activas = alertas.filter((a) => a.activa).length;
  const totalMatches = alertas.reduce((s, a) => s + (a.matches || 0), 0);

  const KPIS = [
    { label: 'Alertas', value: alertas.length, color: 'text-text-primary' },
    { label: 'Activas', value: activas, color: 'text-status-green' },
    { label: 'Matches', value: totalMatches, color: 'text-celeste' },
  ];

  return (
    <div className="max-w-3xl mx-auto">
      <FadeIn>
        <div className="flex items-end justify-between gap-4 mb-7 pt-2">
          <div>
            <p className="eyebrow mb-1"><span className="eyebrow-num">VIGÍA / ALERTAS</span><span className="ml-2">Monitoreo automático</span></p>
            <h2 className="display-section text-text-primary mb-1">Que la norma <em>te encuentre.</em></h2>
            <p className="text-[13px] text-text-tertiary font-mono">keywords + sectores · matching horario · digest por email</p>
          </div>
          <button onClick={() => { setShowForm((v) => !v); setEditingId(null); }} className="flex items-center gap-1.5 px-4 py-2 btn-celeste rounded-full text-[11px] font-bold shrink-0">
            <Plus size={13} /> Nueva
          </button>
        </div>
      </FadeIn>

      {!connected && (
        <FadeIn delay={60}>
          <div className="flex items-start gap-2 border-l-2 border-celeste pl-4 py-1 mb-8">
            <Info size={13} className="text-celeste shrink-0 mt-0.5" />
            <p className="text-[12px] text-text-secondary leading-relaxed">
              {AUTH_ENABLED ? 'Iniciá sesión para que tus alertas se guarden y lleguen por email.' : 'Vista demo: las alertas viven solo en esta sesión.'}
            </p>
          </div>
        </FadeIn>
      )}

      {err && <p className="text-[12px] text-status-red mb-4 font-mono">{err}</p>}

      {/* KPIs flotantes */}
      <div className="grid grid-cols-3 border-t-2 border-text-primary/70 mb-10">
        {KPIS.map(({ label, value, color }, i) => (
          <FadeIn key={label} delay={i * 80}>
            <div className="pt-4 pb-5 lg:border-r border-border-light lg:px-5 first:pl-0 transition-colors duration-300 hover:bg-celeste/[0.03]">
              <p className={`font-mono font-bold text-3xl leading-none mb-1.5 ${color}`}><CountUp value={value} /></p>
              <p className="eyebrow text-[9px]">{label}</p>
            </div>
          </FadeIn>
        ))}
      </div>

      {/* Form de alta */}
      {showForm && (
        <div className="mb-10">
          <p className="eyebrow mb-4"><span className="eyebrow-num">+</span><span className="ml-2">Nueva alerta</span></p>
          <AlertaForm initial={{ keywords: [], sectores: [] }} onSubmit={addAlerta} onCancel={() => setShowForm(false)} submitLabel="Crear" onPreview={onPreview} />
        </div>
      )}

      {/* Lista editorial */}
      <div className="border-t border-border-light">
        {alertas.map((alerta, i) => (
          <FadeIn key={alerta.id} delay={Math.min(i * 50, 300)}>
            {editingId === alerta.id ? (
              <div className="border-b border-border-light py-5">
                <p className="eyebrow mb-4"><span className="eyebrow-num">✎</span><span className="ml-2">Editar alerta</span></p>
                <AlertaForm
                  initial={{ keywords: alerta.keywords || [], sectores: alerta.sectores || [] }}
                  onSubmit={(payload) => saveEdit(alerta, payload)}
                  onCancel={() => setEditingId(null)}
                  submitLabel="Guardar"
                  onPreview={onPreview}
                />
                <p className="text-[10px] text-text-tertiary font-mono mt-3 pl-5">Cambiar el criterio reinicia los matches: la alerta solo notifica normas nuevas desde la edición.</p>
              </div>
            ) : (
              <div className={`group flex items-center justify-between gap-3 border-b border-border-light py-4 transition-all duration-300 hover:bg-celeste/[0.03] hover:pl-2 ${!alerta.activa ? 'opacity-40' : ''}`}>
                <div className="flex items-center gap-3 min-w-0">
                  <Bell size={15} className={alerta.activa ? 'text-celeste' : 'text-text-tertiary'} />
                  <div className="min-w-0">
                    <div className="flex items-center gap-2 mb-1">
                      <h4 className="text-[14px] font-semibold text-text-primary truncate" style={{ fontFamily: 'var(--font-display)' }}>
                        {(alerta.keywords || []).length
                          ? `“${alerta.keywords.join('”, “')}”`
                          : (alerta.sectores || []).length
                            ? `Sectores: ${alerta.sectores.join(' · ')}`
                            : 'Todas las normas'}
                      </h4>
                      {alerta.activa && <span className="text-[9px] font-medium tint-green border px-1.5 py-0.5 rounded-full shrink-0">activa</span>}
                    </div>
                    <div className="flex items-center gap-3 text-[10px] text-text-tertiary font-mono">
                      <span className="flex items-center gap-1"><Tag size={9} /> {(alerta.sectores || []).length ? alerta.sectores.join(' · ') : 'todos'}</span>
                      <span className="flex items-center gap-1"><Hash size={9} /> {(alerta.matches || 0).toLocaleString('es-AR')} matches</span>
                      {alerta.last_match_at && <span className="flex items-center gap-1"><Calendar size={9} /> {alerta.last_match_at.slice(0, 10)}</span>}
                    </div>
                  </div>
                </div>
                <div className="flex items-center gap-1 shrink-0">
                  <button onClick={() => { setEditingId(alerta.id); setShowForm(false); }} className="p-1.5 rounded-lg text-text-tertiary hover:text-celeste hover:bg-celeste/10 transition-colors">
                    <Pencil size={14} />
                  </button>
                  <button onClick={() => toggleAlerta(alerta)} className={`p-1.5 rounded-lg transition-colors ${alerta.activa ? 'text-status-green hover:bg-status-green/10' : 'text-text-tertiary hover:bg-bg-tertiary'}`}>
                    {alerta.activa ? <Power size={14} /> : <PowerOff size={14} />}
                  </button>
                  <button onClick={() => deleteAlerta(alerta)} className="p-1.5 rounded-lg text-text-tertiary hover:text-status-red hover:bg-status-red/10 transition-colors">
                    <Trash2 size={14} />
                  </button>
                </div>
              </div>
            )}
          </FadeIn>
        ))}
      </div>

      {alertas.length === 0 && (
        <div className="text-center py-16">
          <Bell size={28} className="text-text-tertiary/40 mx-auto mb-3" />
          <p className="text-text-tertiary text-sm">Sin alertas todavía — creá la primera.</p>
        </div>
      )}
    </div>
  );
}
