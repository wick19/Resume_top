import { createContext, useContext, useEffect, useState, type ReactNode } from "react";
import { clearToken, getToken, logout as apiLogout, me } from "./api";

type User = { id: number; email: string };

type AuthValue = {
  user: User | null;
  ready: boolean;
  refresh: () => Promise<void>;
  logout: () => Promise<void>;
};

const AuthContext = createContext<AuthValue | null>(null);

export function AuthProvider({ children }: { children: ReactNode }) {
  const [user, setUser] = useState<User | null>(null);
  const [ready, setReady] = useState(false);

  async function refresh() {
    if (!getToken()) {
      setUser(null);
      setReady(true);
      return;
    }
    try {
      setUser((await me()).user);
    } catch {
      clearToken();
      setUser(null);
    } finally {
      setReady(true);
    }
  }

  useEffect(() => {
    refresh();
  }, []);

  async function logout() {
    try {
      await apiLogout();
    } catch {
      /* token may already be gone */
    }
    clearToken();
    setUser(null);
  }

  return (
    <AuthContext.Provider value={{ user, ready, refresh, logout }}>
      {children}
    </AuthContext.Provider>
  );
}

export function useAuth() {
  const value = useContext(AuthContext);
  if (!value) throw new Error("AuthProvider missing");
  return value;
}
