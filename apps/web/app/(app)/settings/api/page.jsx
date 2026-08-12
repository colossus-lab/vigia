'use client';

import { useState, useEffect, useCallback } from 'react';
import { useSession } from 'next-auth/react';
import { KeyRound, Plus, Trash2, Copy, Check, Info, AlertTriangle, Terminal } from 'lucide-react';
import { authedFetch, AUTH_ENABLED } from '@/lib/authClient';
import { API_BASE } from '@/lib/api';
import SettingsNav from '@/components/SettingsNav';

// `authedFetch` levanta Error("API 409 en /api-keys"): el status queda dentro
// del mensaje. Se traduce acá porque "API 409" no le dice nada a nadie.
const MENSAJES = {
  403: 'Necesitás ser owner o admin del workspace para gestionar keys.',
  409: 'Llegaste al máximo de keys activas. Revocá alguna para crear otra.',
  422: 'El nombre no puede estar vacío.',
  429: 'Demasiadas keys creadas en poco tiempo. Probá de nuevo en un rato.',
};

function traducir(e) {
  const status = Number(String(e?.message || '').match(/API (\d+)/)?.[1]);
  return MENSAJES[status] || String(e?.message || e);
}

function fecha(iso) {
  if (!iso) return '—';
  return new Date(iso).toLocaleDateString('es-AR', { day: '2-digit', month: 'short', year: 'numeric' });
}

export default function ApiSettings() {
  const { data: session, status } = useSession();
  const [keys, setKeys] = useState([]);
  const [nombre, setNombre] = useState('');
  const [rol, setRol] = useState(null);
  const [err, setErr] = useState('');
  const [creando, setCreando] = useState(false);
  // El secreto recién emitido. Vive SOLO en este estado: no se persiste, no se
  // vuelve a pedir y se pierde al navegar. Es la única vez que existe del lado
  // del cliente.
  const [reciente, setReciente] = useState(null);
  const [copiado, setCopiado] = useState(false);
  const [porRevocar, setPorRevocar] = useState(null);

  const load = useCallback(async () => {
    if (!session?.workspace?.id) return;
    try {
      const [k, ws] = await Promise.all([authedFetch('/api-keys'), authedFetch('/workspaces/me')]);
      setKeys(k);
      setRol(ws?.role || null);
    } catch (e) {
      setErr(traducir(e));
    }
  }, [session?.workspace?.id]);

  useEffect(() => { load(); }, [load]);

  const crear = async () => {
    setErr(''); setCreando(true);
    try {
      const k = await authedFetch('/api-keys', {
        method: 'POST', body: JSON.stringify({ name: nombre.trim() }),
      });
      setReciente(k);
      setNombre('');
      setCopiado(false);
      load();
    } catch (e) { setErr(traducir(e)); }
    finally { setCreando(false); }
  };

  const revocar = async (id) => {
    setErr('');
    try {
      await authedFetch(`/api-keys/${id}`, { method: 'DELETE' });
      // Si la que se revoca es la que se acaba de emitir, el panel del secreto
      // deja de tener sentido.
      if (reciente?.id === id) setReciente(null);
      setPorRevocar(null);
      load();
    } catch (e) { setErr(traducir(e)); setPorRevocar(null); }
  };

  const copiar = (texto) => {
    navigator.clipboard?.writeText(texto);
    setCopiado(true);
    setTimeout(() => setCopiado(false), 2500);
  };

  if (!AUTH_ENABLED) {
    return (
      <div className="max-w-2xl mx-auto">
        <SettingsNav />
        <div className="card p-5 border-l-4 border-l-inst-accent flex items-start gap-2">
          <Info size={16} className="text-inst-accent shrink-0 mt-0.5" />
          <p className="text-[13px] text-text-secondary leading-relaxed">
            Las API keys requieren autenticación activa. En modo demo la API pública
            responde sin credencial.
          </p>
        </div>
      </div>
    );
  }

  if (status === 'loading') return <div className="text-text-tertiary text-sm">Cargando…</div>;
  if (!session) return <div className="text-text-tertiary text-sm">Iniciá sesión para gestionar tus API keys.</div>;

  const puedeEscribir = rol === 'owner' || rol === 'admin';
  const activas = keys.filter((k) => !k.revoked_at);
  const revocadas = keys.filter((k) => k.revoked_at);

  return (
    <div className="max-w-2xl mx-auto animate-fade-in">
      <SettingsNav />

      <div className="mb-6">
        <h2 className="text-xl font-bold text-text-primary tracking-tight mb-0.5">API</h2>
        <p className="text-sm text-text-tertiary">Credenciales para conectar tus sistemas a Vigía</p>
      </div>

      {err && <div className="card p-3 mb-4 border-l-4 border-l-status-red text-[12px] text-status-red">{err}</div>}

      {reciente && (
        <div className="card p-5 mb-5 border-l-4 border-l-sol">
          <h3 className="text-sm font-semibold text-text-primary mb-1 flex items-center gap-2">
            <AlertTriangle size={14} className="text-sol" /> Copiá tu key ahora
          </h3>
          <p className="text-[12px] text-text-tertiary leading-relaxed mb-3">
            Guardamos solo un hash: <strong className="text-text-primary">esta es la única vez que vas a ver el
            secreto</strong>. Si lo perdés, revocá esta key y creá otra.
          </p>
          <div className="flex items-center gap-2 bg-bg-primary border border-border-light rounded-lg p-3 mb-3">
            <code className="font-mono text-[12px] text-text-primary break-all flex-1">{reciente.secret}</code>
            <button
              onClick={() => copiar(reciente.secret)}
              className="shrink-0 flex items-center gap-1.5 px-2.5 py-1.5 rounded-full border border-border-light text-text-secondary text-[11px] font-medium hover:border-celeste/40 hover:text-celeste transition-colors"
            >
              {copiado ? <Check size={13} className="text-status-green" /> : <Copy size={13} />}
              {copiado ? 'Copiado' : 'Copiar'}
            </button>
          </div>
          <p className="text-[11px] text-text-tertiary mb-1.5 flex items-center gap-1.5">
            <Terminal size={12} /> Probala:
          </p>
          <pre className="bg-bg-primary border border-border-light rounded-lg p-3 text-[11px] font-mono text-text-secondary overflow-x-auto">
{`curl -H "Authorization: Bearer ${reciente.secret}" \\
  "${API_BASE}/v1/normas?limit=5"`}
          </pre>
        </div>
      )}

      {puedeEscribir && (
        <div className="card p-5 mb-5">
          <h3 className="text-sm font-semibold text-text-primary mb-3 flex items-center gap-2"><Plus size={14} /> Nueva key</h3>
          <div className="flex flex-col md:flex-row gap-2">
            <input
              value={nombre}
              onChange={(e) => setNombre(e.target.value)}
              onKeyDown={(e) => { if (e.key === 'Enter' && nombre.trim()) crear(); }}
              placeholder="Para qué es (ej: ETL interno)"
              maxLength={120}
              className="flex-1 bg-bg-primary border border-border-light rounded-lg px-3 py-2 text-[13px] focus:outline-none focus:border-inst-accent"
            />
            <button
              onClick={crear}
              disabled={creando || !nombre.trim()}
              className="px-3 py-2 btn-celeste rounded-full text-[12px] font-bold disabled:opacity-40 disabled:cursor-not-allowed"
            >
              {creando ? 'Creando…' : 'Crear key'}
            </button>
          </div>
        </div>
      )}

      <div className="card p-5 mb-5">
        <h3 className="text-sm font-semibold text-text-primary mb-3 flex items-center gap-2">
          <KeyRound size={14} /> Keys activas ({activas.length})
        </h3>
        {activas.length === 0 ? (
          <p className="text-[12px] text-text-tertiary">
            Todavía no tenés ninguna. {puedeEscribir ? 'Creá una arriba para empezar a consumir la API.' : 'Pedile a un owner o admin del workspace que te cree una.'}
          </p>
        ) : (
          <div className="space-y-2">
            {activas.map((k) => (
              <div key={k.id} className="flex items-center justify-between gap-3 py-2 border-b border-border-light last:border-0">
                <div className="min-w-0">
                  <p className="text-[13px] font-medium text-text-primary truncate">{k.name}</p>
                  <p className="text-[11px] text-text-tertiary font-mono truncate">
                    {k.prefix}… · creada {fecha(k.created_at)} · último uso {fecha(k.last_used_at)}
                  </p>
                </div>
                {puedeEscribir && (
                  <button
                    onClick={() => setPorRevocar(k)}
                    className="shrink-0 p-1.5 rounded text-text-tertiary hover:text-status-red hover:bg-status-red/10 transition-colors"
                    title="Revocar"
                  >
                    <Trash2 size={14} />
                  </button>
                )}
              </div>
            ))}
          </div>
        )}
      </div>

      {revocadas.length > 0 && (
        <div className="card p-5 mb-5">
          <h3 className="text-sm font-semibold text-text-primary mb-3">Revocadas ({revocadas.length})</h3>
          <div className="space-y-2">
            {revocadas.map((k) => (
              <div key={k.id} className="py-1.5 border-b border-border-light last:border-0 opacity-60">
                <p className="text-[13px] text-text-secondary truncate line-through">{k.name}</p>
                <p className="text-[11px] text-text-tertiary font-mono truncate">
                  {k.prefix}… · revocada {fecha(k.revoked_at)}
                </p>
              </div>
            ))}
          </div>
        </div>
      )}

      <div className="card p-5">
        <h3 className="text-sm font-semibold text-text-primary mb-2">Cómo se usa</h3>
        <p className="text-[12px] text-text-tertiary leading-relaxed mb-3">
          Mandá la key en el header <code className="font-mono text-text-secondary">Authorization: Bearer …</code> a
          los endpoints bajo <code className="font-mono text-text-secondary">/v1</code>. Para sincronizar solo lo que
          cambió, usá <code className="font-mono text-text-secondary">updated_since</code> y seguí el{' '}
          <code className="font-mono text-text-secondary">next_cursor</code> hasta que{' '}
          <code className="font-mono text-text-secondary">has_more</code> sea <code className="font-mono text-text-secondary">false</code>.
        </p>
        <pre className="bg-bg-primary border border-border-light rounded-lg p-3 text-[11px] font-mono text-text-secondary overflow-x-auto mb-3">
{`curl -H "Authorization: Bearer vg_live_…" \\
  "${API_BASE}/v1/normas?updated_since=2026-08-01T00:00:00Z&limit=200"`}
        </pre>
        <p className="text-[11px] text-text-tertiary leading-relaxed">
          Cada respuesta trae tu cuota en los headers <code className="font-mono">X-RateLimit-Remaining</code> y{' '}
          <code className="font-mono">X-RateLimit-Reset</code> (se reinicia a las 00:00 UTC). Es gratis: si necesitás
          más volumen, escribinos.
        </p>
      </div>

      {porRevocar && (
        <div className="fixed inset-0 z-[80] flex items-center justify-center p-4 bg-black/60 backdrop-blur-sm" onClick={() => setPorRevocar(null)}>
          <div className="card p-6 max-w-sm w-full" onClick={(e) => e.stopPropagation()}>
            <div className="flex items-center gap-2.5 mb-3">
              <div className="w-9 h-9 rounded-lg bg-status-red/10 border border-status-red/30 flex items-center justify-center">
                <AlertTriangle size={18} className="text-status-red" />
              </div>
              <h3 className="text-sm font-bold text-text-primary">Revocar «{porRevocar.name}»</h3>
            </div>
            <p className="text-[12px] text-text-secondary leading-relaxed mb-4">
              Todo lo que use esta key va a empezar a recibir <span className="font-mono">401</span> de inmediato.
              <strong className="text-text-primary"> No se puede deshacer</strong>: si la necesitás de nuevo, hay que
              crear otra.
            </p>
            <div className="flex gap-2 justify-end">
              <button onClick={() => setPorRevocar(null)} className="px-3 py-2 rounded-full border border-border-light text-[12px] text-text-secondary hover:text-text-primary transition-colors">Cancelar</button>
              <button
                onClick={() => revocar(porRevocar.id)}
                className="px-3 py-2 rounded-full bg-status-red text-white text-[12px] font-bold hover:bg-status-red/90 transition-colors"
              >
                Revocar
              </button>
            </div>
          </div>
        </div>
      )}
    </div>
  );
}
