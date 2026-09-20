import React, { createContext, useContext, useEffect, useRef, useCallback, useState } from "react";
import { wsUrl } from "@/src/api";
import { useAuth } from "@/src/auth";
import { drainOutbox, pullSince } from "@/src/offlineChat";

type Listener = (event: any) => void;

type WsCtx = {
  subscribe: (fn: Listener) => () => void;
  send: (data: any) => void;
  online: boolean;
};

const Ctx = createContext<WsCtx>({ subscribe: () => () => {}, send: () => {}, online: false });

export function WsProvider({ children }: { children: React.ReactNode }) {
  const { token } = useAuth();
  const wsRef = useRef<WebSocket | null>(null);
  const listeners = useRef<Set<Listener>>(new Set());
  const reconnectTimer = useRef<any>(null);
  const shouldConnect = useRef(false);
  const [online, setOnline] = useState(false);

  const runReconnectSync = useCallback(async () => {
    try {
      const pulled = await pullSince();
      pulled.forEach((m) => listeners.current.forEach((fn) => fn({ type: "message", chat_id: m.chat_id, message: m })));
    } catch {}
    try { await drainOutbox(); } catch {}
  }, []);

  const connect = useCallback(() => {
    if (!token) return;
    try {
      const ws = new WebSocket(wsUrl(token));
      wsRef.current = ws;
      ws.onopen = () => {
        setOnline(true);
        runReconnectSync();
      };
      ws.onmessage = (e) => {
        try {
          const data = JSON.parse(e.data);
          listeners.current.forEach((fn) => fn(data));
        } catch {}
      };
      ws.onclose = () => {
        setOnline(false);
        if (shouldConnect.current) {
          reconnectTimer.current = setTimeout(connect, 2500);
        }
      };
      ws.onerror = () => {
        try { ws.close(); } catch {}
      };
    } catch {}
  }, [token, runReconnectSync]);

  useEffect(() => {
    if (token) {
      shouldConnect.current = true;
      connect();
    }
    return () => {
      shouldConnect.current = false;
      if (reconnectTimer.current) clearTimeout(reconnectTimer.current);
      try { wsRef.current?.close(); } catch {}
      wsRef.current = null;
      setOnline(false);
    };
  }, [token, connect]);

  const subscribe = useCallback((fn: Listener) => {
    listeners.current.add(fn);
    return () => listeners.current.delete(fn);
  }, []);

  const send = useCallback((data: any) => {
    try {
      if (wsRef.current?.readyState === WebSocket.OPEN) {
        wsRef.current.send(JSON.stringify(data));
      }
    } catch {}
  }, []);

  return <Ctx.Provider value={{ subscribe, send, online }}>{children}</Ctx.Provider>;
}

export const useWs = () => useContext(Ctx);
