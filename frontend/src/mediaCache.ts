/**
 * File-system based cache for chat media (images, videos, PDFs). Downloads once
 * per storage_path and reuses on offline reopen.
 *
 * On native we use FileSystem (SAF-safe cacheDirectory). On web we simply fall
 * back to the streaming URL since there is no persistent FS in the browser
 * runtime; the browser's HTTP cache handles reopens.
 */
import { Platform } from "react-native";
import * as FileSystem from "expo-file-system/legacy";

const DIR = (FileSystem.cacheDirectory || "") + "chatly-media/";
let ensured = false;

async function ensureDir() {
  if (ensured || Platform.OS === "web") return;
  try {
    const info = await FileSystem.getInfoAsync(DIR);
    if (!info.exists) await FileSystem.makeDirectoryAsync(DIR, { intermediates: true });
  } catch {}
  ensured = true;
}

function safeName(key: string, ext: string) {
  const hash = key.replace(/[^a-zA-Z0-9]/g, "_").slice(-80);
  return `${hash}${ext.startsWith(".") ? ext : "." + ext}`;
}

/**
 * Returns a local file URI for the given (storage_path, ext) if already cached
 * or if the download succeeds; otherwise returns the original remote URL as a
 * best-effort fallback (streaming from network).
 */
export async function ensureCached(remoteUrl: string, cacheKey: string, ext: string): Promise<string> {
  if (Platform.OS === "web") return remoteUrl;
  await ensureDir();
  const target = DIR + safeName(cacheKey, ext);
  try {
    const info = await FileSystem.getInfoAsync(target);
    if (info.exists && (info as any).size > 0) return target;
    const r = await FileSystem.downloadAsync(remoteUrl, target);
    if (r.status >= 200 && r.status < 300) return r.uri;
    return remoteUrl;
  } catch {
    return remoteUrl;
  }
}

/** Best-effort synchronous cache-path (used when we only need a hint URL). */
export function cachedPath(cacheKey: string, ext: string): string | null {
  if (Platform.OS === "web") return null;
  return DIR + safeName(cacheKey, ext);
}
