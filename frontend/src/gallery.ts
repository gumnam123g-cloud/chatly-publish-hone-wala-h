/**
 * Gallery auto-save for received/sent media (images + videos only).
 * Native-only (expo-media-library). Respects the user's "Auto-Save Media" setting.
 * Voice messages and generic files are intentionally never saved to the gallery.
 */
import { Platform } from "react-native";
import { storage } from "@/src/utils/storage";

let MediaLibrary: any = null;
try { MediaLibrary = require("expo-media-library"); } catch {}

const KEY = "chatly_autosave_media";

export async function getAutoSave(): Promise<boolean> {
  return (await storage.getItem<boolean>(KEY, false)) as boolean;
}
export async function setAutoSave(v: boolean) {
  await storage.setItem(KEY, v as any);
}

/** Save a local/remote media URI to the device gallery (images/videos only). */
export async function saveMediaToGallery(uri: string, kind: "image" | "video"): Promise<boolean> {
  if (Platform.OS === "web" || !MediaLibrary || !uri) return false;
  if (kind !== "image" && kind !== "video") return false;
  try {
    const perm = await MediaLibrary.requestPermissionsAsync();
    if (!perm.granted) return false;
    await MediaLibrary.saveToLibraryAsync(uri);
    return true;
  } catch {
    return false;
  }
}

/** Save only if the user enabled auto-save. No-op for voice/files. */
export async function maybeAutoSave(uri: string, kind: "image" | "video" | "voice" | "file"): Promise<void> {
  if (kind !== "image" && kind !== "video") return;
  if (!(await getAutoSave())) return;
  await saveMediaToGallery(uri, kind);
}
