// Cross-platform ringtone for incoming calls.
//
// Uses expo-audio's AudioPlayer with a remote URL so we don't need to ship a
// binary asset. Loops with `setIsLoopingAsync` on native. On web we use the
// built-in HTMLAudioElement (also loops). Vibration is coordinated so the
// phone rings + vibrates until answered / rejected.
import { Platform, Vibration } from "react-native";

const RING_URL = "https://cdn.jsdelivr.net/gh/anars/blank-audio@1.0.0/1-second-of-silence.mp3";
// A tone-y ring; the file above is only used as a silent fallback if the
// primary URL fails. The primary is a permissively licensed public ringtone.
const PRIMARY_RING_URL =
  "https://upload.wikimedia.org/wikipedia/commons/8/85/Old_phone_ring.ogg";

let stopper: (() => Promise<void>) | null = null;

async function playNative(): Promise<() => Promise<void>> {
  const audio = require("expo-audio");
  const player = audio.createAudioPlayer({ uri: PRIMARY_RING_URL });
  try {
    await audio.setAudioModeAsync?.({
      playsInSilentMode: true,
      shouldPlayInBackground: true,
      interruptionMode: "duckOthers",
    });
  } catch {}
  try { player.loop = true; } catch {}
  try { player.play(); } catch {}
  // Vibrate 1s on / 1s off until stopped.
  try { Vibration.vibrate([0, 1000, 1000], true); } catch {}
  return async () => {
    try { player.pause(); } catch {}
    try { player.remove(); } catch {}
    try { Vibration.cancel(); } catch {}
  };
}

async function playWeb(): Promise<() => Promise<void>> {
  if (typeof window === "undefined") return async () => {};
  const el: any = new (window as any).Audio(PRIMARY_RING_URL);
  el.loop = true;
  el.volume = 1.0;
  try { await el.play(); } catch {
    // Autoplay blocked — try silent fallback (some browsers only block audible autoplay
    // after user interaction).
    try { el.src = RING_URL; await el.play(); } catch {}
  }
  return async () => {
    try { el.pause(); el.src = ""; } catch {}
  };
}

export async function startRingtone(): Promise<void> {
  await stopRingtone();
  try {
    stopper = Platform.OS === "web" ? await playWeb() : await playNative();
  } catch {
    stopper = null;
  }
}

export async function stopRingtone(): Promise<void> {
  const s = stopper;
  stopper = null;
  if (s) { try { await s(); } catch {} }
}
