/**
 * Lightweight analytics client.
 *
 * Emits product-event names to the backend (feedback_routes.py -> /analytics/event).
 * Events are batched (flushed every 5s or when the buffer hits 20) so a burst of
 * message-sent events on a slow network never blocks the UI.
 *
 * NEVER send raw message contents, credentials, passwords, or call audio/video.
 * Keep props to small labels (counts, kinds, durations, boolean flags).
 */
import { api } from "@/src/api";
import { Platform } from "react-native";
import Constants from "expo-constants";

type Props = Record<string, string | number | boolean | null | undefined>;
interface QueuedEvent { event: string; props?: Props; at: string }

const QUEUE: QueuedEvent[] = [];
let flushTimer: ReturnType<typeof setTimeout> | null = null;
let inFlight = false;

const BATCH_SIZE = 20;
const FLUSH_MS = 5000;

function scheduleFlush() {
  if (flushTimer || inFlight) return;
  flushTimer = setTimeout(() => { flushTimer = null; flush(); }, FLUSH_MS);
}

async function flush() {
  if (inFlight || QUEUE.length === 0) return;
  const batch = QUEUE.splice(0, Math.min(QUEUE.length, 50));
  inFlight = true;
  try {
    await api.post("/analytics/event", { events: batch });
  } catch {
    // Requeue at most 200 events so an offline period doesn't grow the queue forever.
    for (const ev of batch) {
      if (QUEUE.length < 200) QUEUE.unshift(ev);
    }
  } finally {
    inFlight = false;
    if (QUEUE.length > 0) scheduleFlush();
  }
}

/** Fire and forget. Safe to call from any component (no await needed). */
export function track(event: string, props?: Props): void {
  QUEUE.push({ event, props, at: new Date().toISOString() });
  if (QUEUE.length >= BATCH_SIZE) {
    if (flushTimer) { clearTimeout(flushTimer); flushTimer = null; }
    flush();
  } else {
    scheduleFlush();
  }
}

/** Common shared props attached to every event via the caller if useful. */
export function baseProps(): Props {
  return {
    platform: Platform.OS,
    app_version: (Constants.expoConfig?.version as string) || "dev",
  };
}

/** Force flush (e.g. on logout). */
export function flushAnalytics(): Promise<void> {
  if (flushTimer) { clearTimeout(flushTimer); flushTimer = null; }
  return flush();
}
