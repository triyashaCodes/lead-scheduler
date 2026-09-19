"use client";

import { createContext, useContext, useSyncExternalStore, type ReactNode } from "react";

import { clearToken, emailFromToken, getNotice, getToken, subscribe } from "@/lib/auth";

interface AuthState {
  // False until the browser has read sessionStorage, to avoid flashing the
  // sign-in panel at someone who is already signed in.
  ready: boolean;
  token: string | null;
  email: string | null;
  notice: string | null;
  signOut: () => void;
}

const AuthContext = createContext<AuthState | null>(null);

const noopSubscribe = () => () => {};

export function AuthProvider({ children }: { children: ReactNode }) {
  const token = useSyncExternalStore(subscribe, getToken, () => null);
  const notice = useSyncExternalStore(subscribe, getNotice, () => null);
  const ready = useSyncExternalStore(noopSubscribe, () => true, () => false);

  const value: AuthState = {
    ready,
    token,
    email: token ? emailFromToken(token) : null,
    notice,
    signOut: () => {
      window.google?.accounts.id.disableAutoSelect();
      clearToken();
    },
  };
  return <AuthContext.Provider value={value}>{children}</AuthContext.Provider>;
}

export function useAuth(): AuthState {
  const context = useContext(AuthContext);
  if (!context) throw new Error("useAuth must be used inside AuthProvider");
  return context;
}
