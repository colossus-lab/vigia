import NextAuth from 'next-auth';
import Google from 'next-auth/providers/google';

/**
 * NextAuth v5 + Google OAuth + sync server-to-server contra la API de Vigía.
 *
 * Flujo: signIn('google') → callback jwt hace POST {API}/auth/sync con AUTH_SECRET
 * → la API upserta app_user, garantiza workspace default y devuelve un JWT propio
 * → guardamos apiJwt + workspace en el token y lo exponemos en la session.
 *
 * Si no hay credenciales Google, AUTH_ENABLED=false y la app corre en modo demo
 * (datos públicos sin login).
 */
export const AUTH_ENABLED = Boolean(process.env.AUTH_GOOGLE_ID || process.env.GOOGLE_CLIENT_ID);

const INTERNAL_API_URL =
  process.env.INTERNAL_API_URL ?? process.env.NEXT_PUBLIC_API_URL ?? 'http://localhost:8000';
const AUTH_SECRET = process.env.AUTH_SECRET ?? '';

async function syncUserWithApi(profile) {
  if (!AUTH_SECRET) {
    console.warn('[auth] AUTH_SECRET not set; skipping API sync');
    return null;
  }
  try {
    const res = await fetch(`${INTERNAL_API_URL}/auth/sync`, {
      method: 'POST',
      headers: { 'Content-Type': 'application/json', Authorization: `Bearer ${AUTH_SECRET}` },
      body: JSON.stringify({
        email: profile.email,
        name: profile.name ?? undefined,
        image_url: profile.picture ?? undefined,
        provider: 'google',
        provider_id: profile.sub ?? undefined,
      }),
    });
    if (!res.ok) {
      console.error(`[auth] /auth/sync failed: ${res.status} ${await res.text()}`);
      return null;
    }
    return await res.json();
  } catch (e) {
    console.error('[auth] /auth/sync threw:', e);
    return null;
  }
}

const NEXTAUTH_SECRET =
  process.env.AUTH_SECRET ?? (AUTH_ENABLED ? undefined : 'demo-mode-placeholder-not-used');

// El apiJwt que firma la API dura 24h, pero la sesión NextAuth vive 30 días: sin
// renovarlo, pasadas 24h del login todos los endpoints gateados devuelven 401
// aunque el usuario siga "logueado". Decodificamos el exp para re-sincronizar
// antes de que venza (margen de 1h). atob existe tanto en runtime node como edge.
function apiJwtExp(jwt) {
  try {
    const part = jwt.split('.')[1].replace(/-/g, '+').replace(/_/g, '/');
    return JSON.parse(atob(part)).exp ?? 0;
  } catch {
    return 0;
  }
}
const API_JWT_REFRESH_MARGIN_S = 3600;

export const { handlers, auth, signIn, signOut } = NextAuth({
  trustHost: true,
  secret: NEXTAUTH_SECRET,
  session: { strategy: 'jwt' },
  providers: AUTH_ENABLED
    ? [
        Google({
          clientId: process.env.AUTH_GOOGLE_ID ?? process.env.GOOGLE_CLIENT_ID,
          clientSecret: process.env.AUTH_GOOGLE_SECRET ?? process.env.GOOGLE_CLIENT_SECRET,
        }),
      ]
    : [],
  pages: { signIn: '/auth/signin' },
  callbacks: {
    async jwt({ token, account, profile }) {
      // En el login guardamos la identidad para poder re-sincronizar después.
      if (account && profile && profile.email) {
        token.email = profile.email;
        token.name = profile.name;
        token.picture = profile.picture;
        token.providerId = profile.sub;
      }
      // Mintea el apiJwt al login y lo renueva cuando está por vencer (o ya
      // venció). Sin esto, el token muere a las 24h y la sesión queda "viva"
      // pero sin acceso a los endpoints gateados (401).
      const now = Math.floor(Date.now() / 1000);
      const exp = token.apiJwt ? apiJwtExp(token.apiJwt) : 0;
      if (token.email && exp - now < API_JWT_REFRESH_MARGIN_S) {
        const sync = await syncUserWithApi({
          email: token.email,
          name: token.name,
          picture: token.picture,
          sub: token.providerId,
        });
        if (sync) {
          token.apiJwt = sync.jwt;
          token.userId = sync.user_id;
          token.workspaceId = sync.workspace_id;
          token.workspaceSlug = sync.workspace_slug;
          token.workspaceName = sync.workspace_name;
          token.role = sync.role;
          token.plan = sync.plan;
          token.trialEndsAt = sync.trial_ends_at;
          token.onboarded = sync.onboarded;
        }
      }
      return token;
    },
    async session({ session, token }) {
      session.apiJwt = token.apiJwt;
      if (token.workspaceId) {
        session.workspace = {
          id: token.workspaceId,
          slug: token.workspaceSlug ?? '',
          name: token.workspaceName ?? '',
          role: token.role ?? 'viewer',
          plan: token.plan ?? 'free',
          trialEndsAt: token.trialEndsAt ?? null,
          onboarded: Boolean(token.onboarded),
        };
      }
      return session;
    },
  },
});
