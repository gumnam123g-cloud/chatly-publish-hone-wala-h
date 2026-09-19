import React, { createContext, useContext, useEffect, useState, useCallback, useRef } from "react";
import { Platform } from "react-native";
import * as WebBrowser from "expo-web-browser";
import * as Linking from "expo-linking";
import { storage } from "@/src/utils/storage";
import { api, TOKEN_KEY } from "@/src/api";
import { signInFirebaseWithCustomToken, signOutFirebase } from "@/src/firebase";
import { registerPushToken, unregisterPushToken } from "@/src/notifications";

WebBrowser.maybeCompleteAuthSession();

export type User = {
  user_id: string;
  name: string;
  email: string;
  username?: string;
  bio?: string;
  avatar?: string | null;
  email_verified?: boolean;
};

type AuthCtx = {
  user: User | null;
  token: string | null;
  loading: boolean;
  login: (email: string, password: string) => Promise<void>;
  signup: (name: string, email: string, password: string) => Promise<void>;
  verifyOtp: (email: string, code: string) => Promise<void>;
  resendOtp: (email: string) => Promise<void>;
  forgot: (email: string) => Promise<void>;
  reset: (email: string, code: string, newPassword: string) => Promise<void>;
  loginWithGoogle: () => Promise<void>;
  logout: () => Promise<void>;
  setUser: (u: User) => void;
};

const Ctx = createContext<AuthCtx>({} as AuthCtx);
const USER_KEY = "chatly_user";
const sentSessions = new Set<string>();

function extractSessionId(url: string): string | null {
  const m = url.match(/[?#&]session_id=([^&#]+)/);
  return m ? decodeURIComponent(m[1]) : null;
}

export function AuthProvider({ children }: { children: React.ReactNode }) {
  const [user, setUserState] = useState<User | null>(null);
  const [token, setToken] = useState<string | null>(null);
  const [loading, setLoading] = useState(true);
  const pushTokenRef = useRef<string | null>(null);

  // When authenticated, bring up the real Firebase session (custom token) and register
  // this device for FCM push. Both fail-soft so they never block the app.
  useEffect(() => {
    if (!token) return;
    let cancelled = false;
    (async () => {
      try {
        const r = await api.get<{ firebase_token: string }>("/auth/firebase-token");
        if (!cancelled && r?.firebase_token) await signInFirebaseWithCustomToken(r.firebase_token);
      } catch { /* Firebase optional; app still works on JWT */ }
      try {
        const tok = await registerPushToken();
        if (tok) pushTokenRef.current = tok;
      } catch { /* push optional (native only) */ }
    })();
    return () => { cancelled = true; };
  }, [token]);

  const persistSession = async (t: string, u: User) => {
    await storage.secureSet(TOKEN_KEY, t);
    await storage.setItem(USER_KEY, u as any);
    setToken(t);
    setUserState(u);
  };

  const exchangeSession = useCallback(async (sessionId: string) => {
    if (sentSessions.has(sessionId)) return;
    sentSessions.add(sessionId);
    const res = await api.post<{ token: string; user: User }>("/auth/session", { session_id: sessionId }, false);
    await persistSession(res.token, res.user);
  }, []);

  useEffect(() => {
    (async () => {
      // 1) Web: process a Google session_id in the URL first
      if (Platform.OS === "web" && typeof window !== "undefined") {
        const raw = window.location.href;
        const sid = extractSessionId(raw);
        if (sid) {
          try {
            await exchangeSession(sid);
            try {
              const clean = window.location.origin + window.location.pathname;
              window.history.replaceState(window.history.state, "", clean);
            } catch {}
            setLoading(false);
            return;
          } catch { /* fall through to token check */ }
        }
      }
      // 2) Mobile: cold-start deep link
      if (Platform.OS !== "web") {
        try {
          const initial = await Linking.getInitialURL();
          if (initial) {
            const sid = extractSessionId(initial);
            if (sid) {
              try { await exchangeSession(sid); setLoading(false); return; } catch {}
            }
          }
        } catch {}
      }
      // 3) Existing token — instant startup: hydrate the cached user immediately,
      //    then revalidate against the server in the background.
      const t = await storage.secureGet<string>(TOKEN_KEY, "");
      if (t) {
        setToken(t);
        const cached = await storage.getItem<User | null>(USER_KEY, null);
        if (cached) setUserState(cached as User);
        setLoading(false);
        api.get<{ user: User }>("/auth/me")
          .then((res) => { setUserState(res.user); storage.setItem(USER_KEY, res.user as any); })
          .catch(async (e: any) => {
            // Only drop the session on a real auth failure (401/403). Keep it on
            // transient/offline/server errors so users aren't logged out for no reason.
            const isAuthError =
              e?.status === 401 || e?.status === 403 || e?.category === "auth";
            if (isAuthError) {
              await storage.secureRemove(TOKEN_KEY);
              await storage.removeItem(USER_KEY);
              setToken(null);
              setUserState(null);
            }
          });
        return;
      }
      setLoading(false);
    })();
  }, [exchangeSession]);

  const loginWithGoogle = useCallback(async () => {
    const redirectUrl = Platform.OS === "web" && typeof window !== "undefined"
      ? window.location.origin + "/"
      : Linking.createURL("");
    const authUrl = `https://auth.emergentagent.com/?redirect=${encodeURIComponent(redirectUrl)}`;
    if (Platform.OS === "web") {
      window.location.href = authUrl;
      return;
    }
    let captured: string | null = null;
    const sub = Linking.addEventListener("url", (e) => { if (e.url) captured = e.url; });
    try {
      const result = await WebBrowser.openAuthSessionAsync(authUrl, redirectUrl);
      let url: string | null = (result as any)?.url || captured;
      if (!url) url = await Linking.getInitialURL();
      const sid = url ? extractSessionId(url) : null;
      if (sid) await exchangeSession(sid);
      else throw new Error("Google sign-in was cancelled");
    } finally {
      sub.remove();
    }
  }, [exchangeSession]);

  const login = useCallback(async (email: string, password: string) => {
    const res = await api.post<{ token: string; user: User }>("/auth/login", { email, password }, false);
    await persistSession(res.token, res.user);
  }, []);

  const signup = useCallback(async (name: string, email: string, password: string) => {
    await api.post("/auth/signup", { name, email, password }, false);
  }, []);

  const verifyOtp = useCallback(async (email: string, code: string) => {
    const res = await api.post<{ token: string; user: User }>("/auth/verify-otp", { email, code }, false);
    await persistSession(res.token, res.user);
  }, []);

  const resendOtp = useCallback(async (email: string) => {
    await api.post("/auth/resend-otp", { email }, false);
  }, []);

  const forgot = useCallback(async (email: string) => {
    await api.post("/auth/forgot-password", { email }, false);
  }, []);

  const reset = useCallback(async (email: string, code: string, newPassword: string) => {
    await api.post("/auth/reset-password", { email, code, new_password: newPassword }, false);
  }, []);

  const logout = useCallback(async () => {
    try { await unregisterPushToken(pushTokenRef.current); } catch {}
    try { await signOutFirebase(); } catch {}
    pushTokenRef.current = null;
    await storage.secureRemove(TOKEN_KEY);
    await storage.removeItem(USER_KEY);
    setToken(null);
    setUserState(null);
  }, []);

  const setUser = useCallback((u: User) => {
    setUserState(u);
    storage.setItem(USER_KEY, u as any);
  }, []);

  return (
    <Ctx.Provider value={{ user, token, loading, login, signup, verifyOtp, resendOtp, forgot, reset, loginWithGoogle, logout, setUser }}>
      {children}
    </Ctx.Provider>
  );
}

export const useAuth = () => useContext(Ctx);
