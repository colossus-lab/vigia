'use client';

import { createContext, useCallback, useContext, useEffect, useState } from 'react';
import { useSession } from 'next-auth/react';
import { AUTH_ENABLED, authedFetch } from '@/lib/authClient';

/**
 * Saldo de créditos del workspace, compartido por toda la app.
 *
 * No sale de `session.workspace`: eso viaja adentro del JWT y se refresca recién
 * en el próximo /auth/sync, mientras que el saldo lo mueve el worker cada hora.
 * Hay que pedirlo.
 *
 * Vive en un contexto y no en cada componente porque lo consumen la barra de la
 * sidebar y el cartel de agotado; sin esto serían dos fetch idénticos por
 * pantalla. El saldo solo cambia cuando corre el matcher, así que alcanza con
 * pedirlo al montar — `refrescar()` está para cuando haga falta forzarlo.
 */
const Ctx = createContext({ creditos: null, cargando: true, refrescar: () => {} });

export function useCreditos() {
  return useContext(Ctx);
}

export default function CreditosProvider({ children }) {
  const { status } = useSession();
  const [creditos, setCreditos] = useState(null);
  const [cargando, setCargando] = useState(true);

  const refrescar = useCallback(async () => {
    if (!AUTH_ENABLED) {
      setCargando(false);
      return;
    }
    try {
      const ws = await authedFetch('/workspaces/me');
      setCreditos(ws?.creditos ?? null);
    } catch {
      // El medidor es informativo: si no se puede leer, la app sigue andando y
      // no se muestra nada. Nunca romper una pantalla por el saldo.
      setCreditos(null);
    } finally {
      setCargando(false);
    }
  }, []);

  useEffect(() => {
    if (status === 'loading') return;
    if (status !== 'authenticated') {
      setCargando(false);
      return;
    }
    refrescar();
  }, [status, refrescar]);

  return <Ctx.Provider value={{ creditos, cargando, refrescar }}>{children}</Ctx.Provider>;
}
