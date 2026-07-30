'use client';

import { useState, useEffect, useCallback } from 'react';
import { useSession, signOut } from 'next-auth/react';
import { Users, Plus, Trash2, Copy, Building2, Info, MessageCircle, Check, Mail, Download, ShieldAlert, AlertTriangle } from 'lucide-react';
import { authedFetch, AUTH_ENABLED } from '@/lib/authClient';
import { API_BASE } from '@/lib/api';

function inviteMessage(wsName, token) {
  const link = `${location.origin}/auth/invite?token=${token}`;
  return `Te invito a "${wsName}" en Vigía, la plataforma de inteligencia legislativa argentina. Aceptá acá: ${link}`;
}

export default function WorkspaceSettings() {
  const { data: session, status } = useSession();
  const jwt = session?.apiJwt;
  const [ws, setWs] = useState(null);
  const [members, setMembers] = useState([]);
  const [invites, setInvites] = useState([]);
  const [email, setEmail] = useState('');
  const [role, setRole] = useState('viewer');
  const [err, setErr] = useState('');
  const [lastInvite, setLastInvite] = useState(null); // feedback del email automático
  const [copied, setCopied] = useState(null); // token recién copiado
  const [showDelete, setShowDelete] = useState(false); // modal de borrado de cuenta
  const [confirmEmail, setConfirmEmail] = useState(''); // email tipeado para confirmar
  const [busy, setBusy] = useState(false); // export/delete en curso

  const userEmail = session?.user?.email || '';

  const load = useCallback(async () => {
    if (!jwt) return;
    try {
      const [w, m, i] = await Promise.all([
        authedFetch(jwt, '/workspaces/me'),
        authedFetch(jwt, '/workspaces/me/members'),
        authedFetch(jwt, '/workspaces/me/invitations'),
      ]);
      setWs(w); setMembers(m); setInvites(i);
    } catch (e) { setErr(String(e.message || e)); }
  }, [jwt]);

  useEffect(() => { load(); }, [load]);

  const invite = async () => {
    setErr('');
    try {
      const inv = await authedFetch(jwt, '/workspaces/me/invitations', {
        method: 'POST', body: JSON.stringify({ email, role }),
      });
      setLastInvite(inv);
      setEmail('');
      load();
    } catch (e) { setErr(String(e.message || e)); }
  };

  const copyMessage = (token) => {
    navigator.clipboard?.writeText(inviteMessage(ws?.name || 'mi workspace', token));
    setCopied(token);
    setTimeout(() => setCopied(null), 2000);
  };

  const whatsappHref = (token) =>
    `https://wa.me/?text=${encodeURIComponent(inviteMessage(ws?.name || 'mi workspace', token))}`;

  const removeMember = async (userId) => {
    try { await authedFetch(jwt, `/workspaces/me/members/${userId}`, { method: 'DELETE' }); load(); }
    catch (e) { setErr(String(e.message || e)); }
  };

  const exportData = async () => {
    setErr(''); setBusy(true);
    try {
      const res = await fetch(`${API_BASE}/account/export`, {
        headers: { Authorization: `Bearer ${jwt}` }, cache: 'no-store',
      });
      if (!res.ok) throw new Error(`API ${res.status} en /account/export`);
      const blob = await res.blob();
      const url = URL.createObjectURL(blob);
      const a = document.createElement('a');
      a.href = url; a.download = 'vigia-mis-datos.json';
      document.body.appendChild(a); a.click(); a.remove();
      URL.revokeObjectURL(url);
    } catch (e) { setErr(String(e.message || e)); }
    finally { setBusy(false); }
  };

  const deleteAccount = async () => {
    setErr(''); setBusy(true);
    try {
      await authedFetch(jwt, '/account', { method: 'DELETE' });
      await signOut({ callbackUrl: '/' });
    } catch (e) { setErr(String(e.message || e)); setBusy(false); }
  };

  if (!AUTH_ENABLED) {
    return (
      <div className="max-w-2xl mx-auto">
        <div className="card p-5 border-l-4 border-l-inst-accent flex items-start gap-2">
          <Info size={16} className="text-inst-accent shrink-0 mt-0.5" />
          <p className="text-[13px] text-text-secondary leading-relaxed">
            La gestión de workspace requiere autenticación activa. Configurá Google OAuth
            (<code className="font-mono">AUTH_GOOGLE_ID/SECRET</code> + <code className="font-mono">AUTH_SECRET</code>)
            para habilitar login, miembros e invitaciones.
          </p>
        </div>
      </div>
    );
  }

  if (status === 'loading') return <div className="text-text-tertiary text-sm">Cargando…</div>;
  if (!session) return <div className="text-text-tertiary text-sm">Iniciá sesión para gestionar tu workspace.</div>;

  return (
    <div className="max-w-2xl mx-auto animate-fade-in">
      <div className="mb-6">
        <h2 className="text-xl font-bold text-text-primary tracking-tight mb-0.5">Workspace</h2>
        <p className="text-sm text-text-tertiary">Miembros e invitaciones</p>
      </div>

      {err && <div className="card p-3 mb-4 border-l-4 border-l-status-red text-[12px] text-status-red">{err}</div>}

      {ws && (
        <div className="card p-5 mb-5">
          <div className="flex items-center gap-3">
            <div className="w-10 h-10 rounded-lg bg-celeste/10 border border-celeste/30 flex items-center justify-center"><Building2 size={18} className="text-celeste" /></div>
            <div>
              <h3 className="text-sm font-semibold text-text-primary">{ws.name}</h3>
              <p className="text-[11px] text-text-tertiary">{ws.seats_used}/{ws.seat_limit} asientos · plan {ws.plan} · tu rol: {ws.role}</p>
            </div>
          </div>
        </div>
      )}

      <div className="card p-5 mb-5">
        <h3 className="text-sm font-semibold text-text-primary mb-3 flex items-center gap-2"><Plus size={14} /> Invitar miembro</h3>
        <div className="flex flex-col md:flex-row gap-2">
          <input value={email} onChange={(e) => setEmail(e.target.value)} placeholder="email@empresa.com" className="flex-1 bg-bg-primary border border-border-light rounded-lg px-3 py-2 text-[13px] focus:outline-none focus:border-inst-accent" />
          <select value={role} onChange={(e) => setRole(e.target.value)} className="bg-bg-primary border border-border-light rounded-lg px-3 py-2 text-[13px] text-text-secondary focus:outline-none focus:border-inst-accent">
            <option value="viewer">Viewer</option>
            <option value="admin">Admin</option>
          </select>
          <button onClick={invite} className="px-3 py-2 btn-celeste rounded-full text-[12px] font-bold">Invitar</button>
        </div>
        {lastInvite && (
          <div className="mt-3 flex items-start gap-2 text-[12px] text-text-secondary border-l-2 border-celeste/40 pl-3 py-1">
            <Mail size={13} className="shrink-0 mt-0.5 text-celeste" />
            <p>
              Invitación creada para <strong className="text-text-primary">{lastInvite.email}</strong>
              {lastInvite.email_sent
                ? ' — le mandamos el email con el link.'
                : ' — compartile el link por WhatsApp o copialo desde "Invitaciones pendientes".'}
            </p>
          </div>
        )}
      </div>

      <div className="card p-5 mb-5">
        <h3 className="text-sm font-semibold text-text-primary mb-3 flex items-center gap-2"><Users size={14} /> Miembros ({members.length})</h3>
        <div className="space-y-2">
          {members.map((m) => (
            <div key={m.user_id} className="flex items-center justify-between py-1.5 border-b border-border-light last:border-0">
              <div>
                <p className="text-[13px] font-medium text-text-primary">{m.name || m.email}</p>
                <p className="text-[11px] text-text-tertiary">{m.email} · {m.role}</p>
              </div>
              {m.role !== 'owner' && (
                <button onClick={() => removeMember(m.user_id)} className="p-1.5 rounded text-text-tertiary hover:text-status-red hover:bg-status-red/10 transition-colors"><Trash2 size={14} /></button>
              )}
            </div>
          ))}
        </div>
      </div>

      {invites.filter((i) => !i.accepted).length > 0 && (
        <div className="card p-5">
          <h3 className="text-sm font-semibold text-text-primary mb-3">Invitaciones pendientes</h3>
          <div className="space-y-2">
            {invites.filter((i) => !i.accepted).map((i) => (
              <div key={i.token} className="flex items-center justify-between gap-3 py-2 border-b border-border-light last:border-0">
                <div className="min-w-0">
                  <p className="text-[13px] text-text-primary truncate">{i.email} · {i.role}</p>
                  <p className="text-[10px] text-text-tertiary font-mono truncate">/auth/invite?token={i.token}</p>
                </div>
                <div className="flex items-center gap-1 shrink-0">
                  <a
                    href={whatsappHref(i.token)}
                    target="_blank"
                    rel="noreferrer"
                    className="flex items-center gap-1.5 px-2.5 py-1.5 rounded-full border border-status-green/30 text-status-green text-[11px] font-medium hover:bg-status-green/10 transition-colors"
                    title="Compartir invitación por WhatsApp"
                  >
                    <MessageCircle size={13} /> WhatsApp
                  </a>
                  <button
                    onClick={() => copyMessage(i.token)}
                    className="flex items-center gap-1.5 px-2.5 py-1.5 rounded-full border border-border-light text-text-secondary text-[11px] font-medium hover:border-celeste/40 hover:text-celeste transition-colors"
                    title="Copiar mensaje con el link de invitación"
                  >
                    {copied === i.token ? <Check size={13} className="text-status-green" /> : <Copy size={13} />}
                    {copied === i.token ? 'Copiado' : 'Copiar'}
                  </button>
                </div>
              </div>
            ))}
          </div>
        </div>
      )}

      <div className="card p-5 mt-5">
        <h3 className="text-sm font-semibold text-text-primary mb-1 flex items-center gap-2"><ShieldAlert size={14} /> Tu cuenta y tus datos</h3>
        <p className="text-[12px] text-text-tertiary leading-relaxed mb-4">
          Ejercé tus derechos sobre tus datos personales (Ley 25.326): descargá todo lo que guardamos
          de vos o eliminá tu cuenta por completo. El borrado es inmediato e irreversible.
        </p>
        <div className="flex flex-col md:flex-row gap-2">
          <button
            onClick={exportData}
            disabled={busy}
            className="flex items-center justify-center gap-2 px-3 py-2 rounded-full border border-border-light text-[12px] font-medium text-text-secondary hover:border-celeste/40 hover:text-celeste transition-colors disabled:opacity-40 disabled:cursor-not-allowed"
          >
            <Download size={14} /> Descargar mis datos
          </button>
          <button
            onClick={() => { setConfirmEmail(''); setShowDelete(true); }}
            className="flex items-center justify-center gap-2 px-3 py-2 rounded-full border border-status-red/30 text-[12px] font-medium text-status-red hover:bg-status-red/10 transition-colors"
          >
            <Trash2 size={14} /> Eliminar mi cuenta
          </button>
        </div>
      </div>

      {showDelete && (
        <div className="fixed inset-0 z-[80] flex items-center justify-center p-4 bg-black/60 backdrop-blur-sm" onClick={() => !busy && setShowDelete(false)}>
          <div className="card p-6 max-w-sm w-full" onClick={(e) => e.stopPropagation()}>
            <div className="flex items-center gap-2.5 mb-3">
              <div className="w-9 h-9 rounded-lg bg-status-red/10 border border-status-red/30 flex items-center justify-center"><AlertTriangle size={18} className="text-status-red" /></div>
              <h3 className="text-sm font-bold text-text-primary">Eliminar tu cuenta</h3>
            </div>
            <p className="text-[12px] text-text-secondary leading-relaxed mb-4">
              Esto borra tu cuenta, tus workspaces personales, alertas y todo tu registro de actividad.
              <strong className="text-text-primary"> No se puede deshacer.</strong> Para confirmar, escribí tu email
              <span className="font-mono text-text-primary"> {userEmail}</span>.
            </p>
            <input
              value={confirmEmail}
              onChange={(e) => setConfirmEmail(e.target.value)}
              placeholder={userEmail}
              className="w-full bg-bg-primary border border-border-light rounded-lg px-3 py-2 text-[13px] mb-4 focus:outline-none focus:border-status-red"
            />
            <div className="flex gap-2 justify-end">
              <button onClick={() => setShowDelete(false)} disabled={busy} className="px-3 py-2 rounded-full border border-border-light text-[12px] text-text-secondary hover:text-text-primary transition-colors disabled:opacity-40">Cancelar</button>
              <button
                onClick={deleteAccount}
                disabled={busy || confirmEmail.trim().toLowerCase() !== userEmail.toLowerCase()}
                className="px-3 py-2 rounded-full bg-status-red text-white text-[12px] font-bold hover:bg-status-red/90 transition-colors disabled:opacity-40 disabled:cursor-not-allowed"
              >
                {busy ? 'Eliminando…' : 'Eliminar definitivamente'}
              </button>
            </div>
          </div>
        </div>
      )}
    </div>
  );
}
