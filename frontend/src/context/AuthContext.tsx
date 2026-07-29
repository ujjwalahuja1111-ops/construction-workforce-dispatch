import { createContext, useContext, useState, useEffect, ReactNode, useCallback } from 'react';
import { storage } from '../utils/storage';
import { api, TOKEN_STORAGE_KEY } from '../api/client';

interface AuthState {
  loading: boolean;
  user: any | null;
  worker: any | null;
  token: string | null;
  profileComplete: boolean;
}

interface AuthCtx extends AuthState {
  setSession(token: string, user: any, profileComplete: boolean): Promise<void>;
  refreshMe(): Promise<void>;
  signOut(): Promise<void>;
}

const Ctx = createContext<AuthCtx | null>(null);

export function AuthProvider({ children }: { children: ReactNode }) {
  const [state, setState] = useState<AuthState>({
    loading: true,
    user: null,
    worker: null,
    token: null,
    profileComplete: false,
  });

  const bootstrap = useCallback(async () => {
    const token = await storage.secureGet(TOKEN_STORAGE_KEY, '');
    if (!token) {
      setState((s) => ({ ...s, loading: false }));
      return;
    }
    try {
      const me = await api.me();
      setState({
        loading: false,
        token: token as string,
        user: me.user,
        worker: me.worker,
        profileComplete: !!me.worker,
      });
    } catch {
      await storage.secureRemove(TOKEN_STORAGE_KEY);
      setState({ loading: false, user: null, worker: null, token: null, profileComplete: false });
    }
  }, []);

  useEffect(() => {
    bootstrap();
  }, [bootstrap]);

  const setSession = useCallback(async (token: string, user: any, profileComplete: boolean) => {
    await storage.secureSet(TOKEN_STORAGE_KEY, token);
    setState({ loading: false, token, user, worker: null, profileComplete });
    // best-effort refresh in background to pull worker profile
    api.me()
      .then((me) => setState((s) => ({ ...s, user: me.user, worker: me.worker, profileComplete: !!me.worker })))
      .catch(() => {});
  }, []);

  const refreshMe = useCallback(async () => {
    try {
      const me = await api.me();
      setState((s) => ({ ...s, user: me.user, worker: me.worker, profileComplete: !!me.worker }));
    } catch {
      /* ignore */
    }
  }, []);

  const signOut = useCallback(async () => {
    await storage.secureRemove(TOKEN_STORAGE_KEY);
    setState({ loading: false, user: null, worker: null, token: null, profileComplete: false });
  }, []);

  return (
    <Ctx.Provider value={{ ...state, setSession, refreshMe, signOut }}>
      {children}
    </Ctx.Provider>
  );
}

export function useAuth(): AuthCtx {
  const c = useContext(Ctx);
  if (!c) throw new Error('useAuth must be used inside <AuthProvider>');
  return c;
}
