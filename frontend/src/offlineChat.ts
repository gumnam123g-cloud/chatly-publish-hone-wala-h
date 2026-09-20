// Offline chat cache + outbox.
//
// Two pieces:
// 1. Message cache — the last ~200 messages per chat are stored in AsyncStorage
//    so the chat opens instantly (with real content) even before the network
//    responds, and stays readable while offline.
// 2. Outbox — messages that failed to send are queued locally with a stable
//    `client_message_id`. On every network-good sync we replay the outbox via
//    /api/sync/messages which is idempotent on the same id.
import { storage } from "@/src/utils/storage";
import { api, ApiError } from "@/src/api";

const CHAT_PREFIX = "chatly_msgs_";
const OUTBOX_KEY = "chatly_outbox";
const LAST_SYNC_KEY = "chatly_last_sync";
const CACHE_LIMIT = 200;

export type ChatMsg = {
  message_id: string;
  chat_id: string;
  sender_id: string;
  text: string;
  status?: string;
  reactions?: Record<string, string>;
  starred_by?: string[];
  edited?: boolean;
  deleted?: boolean;
  created_at: string;
  client_message_id?: string | null;
  attachment?: any;
  reply_to?: string | null;
  type?: string;
};

export type OutboxItem = {
  chat_id: string;
  client_message_id: string;
  text: string;
  type?: string;
  reply_to?: string | null;
  priority?: string | null;
  created_at: string;
  attempts: number;
};

const chatKey = (chatId: string) => CHAT_PREFIX + chatId;

export async function loadCachedMessages(chatId: string): Promise<ChatMsg[]> {
  const raw = await storage.getItem<ChatMsg[] | null>(chatKey(chatId), null);
  return Array.isArray(raw) ? (raw as ChatMsg[]) : [];
}

export async function saveCachedMessages(chatId: string, messages: ChatMsg[]): Promise<void> {
  const trimmed = messages.slice(-CACHE_LIMIT);
  await storage.setItem(chatKey(chatId), trimmed as any);
}

export async function upsertCachedMessage(chatId: string, msg: ChatMsg): Promise<void> {
  const prev = await loadCachedMessages(chatId);
  const withoutTmp = prev.filter(
    (m) => m.message_id !== msg.message_id &&
      !(m.client_message_id && msg.client_message_id && m.client_message_id === msg.client_message_id)
  );
  await saveCachedMessages(chatId, [...withoutTmp, msg]);
}

export async function removeCachedMessage(chatId: string, messageId: string): Promise<void> {
  const prev = await loadCachedMessages(chatId);
  await saveCachedMessages(chatId, prev.filter((m) => m.message_id !== messageId));
}

export async function clearChatCache(chatId: string): Promise<void> {
  await storage.removeItem(chatKey(chatId));
}

// -------- Outbox --------
export async function loadOutbox(): Promise<OutboxItem[]> {
  const raw = await storage.getItem<OutboxItem[] | null>(OUTBOX_KEY, null);
  return Array.isArray(raw) ? (raw as OutboxItem[]) : [];
}

async function saveOutbox(items: OutboxItem[]): Promise<void> {
  await storage.setItem(OUTBOX_KEY, items as any);
}

export async function enqueueOutbox(item: OutboxItem): Promise<void> {
  const items = await loadOutbox();
  const withoutSame = items.filter((i) => i.client_message_id !== item.client_message_id);
  withoutSame.push(item);
  await saveOutbox(withoutSame);
}

export async function removeOutbox(clientMessageId: string): Promise<void> {
  const items = await loadOutbox();
  await saveOutbox(items.filter((i) => i.client_message_id !== clientMessageId));
}

export function generateClientMessageId(): string {
  const rand = Math.random().toString(36).slice(2, 10);
  return `cmsg_${Date.now().toString(36)}_${rand}`;
}

// -------- Sync --------
export async function getLastSyncAt(): Promise<string | null> {
  return (await storage.getItem<string | null>(LAST_SYNC_KEY, null)) as any;
}

export async function setLastSyncAt(ts: string): Promise<void> {
  await storage.setItem(LAST_SYNC_KEY, ts as any);
}

/** Replay any queued messages. Idempotent on client_message_id, so it's safe to call whenever we come online. */
export async function drainOutbox(): Promise<{ sent: number; failed: number }> {
  const items = await loadOutbox();
  let sent = 0;
  let failed = 0;
  for (const item of items) {
    try {
      const res = await api.post<{ message: ChatMsg }>(`/sync/messages?chat_id=${encodeURIComponent(item.chat_id)}`, {
        text: item.text,
        type: item.type || "text",
        reply_to: item.reply_to,
        client_message_id: item.client_message_id,
        priority: item.priority || undefined,
      });
      if (res?.message) {
        await upsertCachedMessage(item.chat_id, res.message);
        await removeOutbox(item.client_message_id);
        sent++;
      }
    } catch (e) {
      const err = e as ApiError;
      // Only give up on permanent errors — keep transient ones for the next drain.
      if (err?.status && err.status >= 400 && err.status < 500 && err.status !== 429 && err.status !== 408) {
        await removeOutbox(item.client_message_id);
        failed++;
      } else {
        item.attempts += 1;
        await enqueueOutbox(item);
        failed++;
      }
    }
  }
  return { sent, failed };
}

/** Pull any messages the client missed while offline. Called on WS reconnect / focus. */
export async function pullSince(): Promise<ChatMsg[]> {
  const since = await getLastSyncAt();
  const q = since ? `?since=${encodeURIComponent(since)}` : "";
  try {
    const res = await api.get<{ messages: ChatMsg[]; server_time: string }>(`/sync/pull${q}`);
    if (res.server_time) await setLastSyncAt(res.server_time);
    for (const m of res.messages || []) {
      await upsertCachedMessage(m.chat_id, m);
    }
    return res.messages || [];
  } catch {
    return [];
  }
}
