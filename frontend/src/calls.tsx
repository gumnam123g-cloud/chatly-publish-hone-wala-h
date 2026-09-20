import React, { createContext, useContext, useEffect, useRef, useState, useCallback } from "react";
import { View, Modal, Pressable, StyleSheet, Platform } from "react-native";
import { useRouter } from "expo-router";
import { LinearGradient } from "expo-linear-gradient";
import * as Haptics from "expo-haptics";
import { useSafeAreaInsets } from "react-native-safe-area-context";
import { useTheme, spacing, radius } from "@/src/theme";
import { AppText, Avatar, Icon } from "@/src/ui";
import { api, TOKEN_KEY } from "@/src/api";
import { useWs } from "@/src/ws";
import { useAuth } from "@/src/auth";
import { storage } from "@/src/utils/storage";
import {
  rtcAvailable, unavailableReason, getUserMedia, createPeerConnection, switchCamera, canSwitchCamera,
  RTCVideoView, RemoteAudio,
} from "@/src/rtc";
import { startChunkedCapture, CaptureChunk } from "@/src/callCapture";
import { useCallRecorder, setCallAudioMode, ensureMicPermission } from "@/src/useCallRecorder";
import { startRingtone, stopRingtone } from "@/src/ringtone";

type Call = any;
type Segment = { id: string; speaker_id: string; speaker: string; text: string; at: string };
type Phase = "incoming" | "outgoing" | "connected" | "ended";
type CallCtx = { startCall: (chatId: string, name: string, type: "voice" | "video") => Promise<void> };
const Ctx = createContext<CallCtx>({ startCall: async () => {} });

const BASE = (process.env.EXPO_PUBLIC_BACKEND_URL || "") + "/api";
const CHUNK_MS = 8000;

export function CallProvider({ children }: { children: React.ReactNode }) {
  const { colors } = useTheme();
  const router = useRouter();
  const insets = useSafeAreaInsets();
  const { subscribe, send } = useWs();
  const { user } = useAuth();
  const recorder = useCallRecorder();

  // ---- UI state ----
  const [call, setCall] = useState<Call | null>(null);
  const [phase, setPhase] = useState<Phase>("outgoing");
  const [muted, setMuted] = useState(false);
  const [speaker, setSpeaker] = useState(true);
  const [camOff, setCamOff] = useState(false);
  const [seconds, setSeconds] = useState(0);
  const [localStream, setLocalStream] = useState<any>(null);
  const [remoteStream, setRemoteStream] = useState<any>(null);
  const [connState, setConnState] = useState<string>("new");
  const [mediaError, setMediaError] = useState<string | null>(null);
  const [captions, setCaptions] = useState<Segment[]>([]);
  const [ccOn, setCcOn] = useState(true);
  const [ccState, setCcState] = useState<"idle" | "live" | "unavailable" | "off">("idle");
  const [showAllCaptions, setShowAllCaptions] = useState(false);

  // ---- mutable refs (used inside async/WS handlers) ----
  const callRef = useRef<Call | null>(null);
  const phaseRef = useRef<Phase>("outgoing");
  const meRef = useRef<string | null>(null);
  const roleRef = useRef<"caller" | "callee">("caller");
  const pc = useRef<any>(null);
  const localRef = useRef<any>(null);
  const pendingIce = useRef<any[]>([]);
  const pendingOffer = useRef<any>(null);
  const mediaReady = useRef(false);
  const iceServersRef = useRef<any[] | null>(null);
  const stopCapture = useRef<null | (() => void)>(null);
  const ccOnRef = useRef(true);
  const speakerRef = useRef(true);
  const timer = useRef<any>(null);

  useEffect(() => { meRef.current = user?.user_id || null; }, [user]);
  useEffect(() => { callRef.current = call; }, [call]);
  useEffect(() => { phaseRef.current = phase; }, [phase]);
  useEffect(() => { ccOnRef.current = ccOn; }, [ccOn]);
  useEffect(() => { speakerRef.current = speaker; }, [speaker]);

  const clearTimer = () => { if (timer.current) { clearInterval(timer.current); timer.current = null; } };
  const startTimer = () => { clearTimer(); setSeconds(0); timer.current = setInterval(() => setSeconds((s) => s + 1), 1000); };

  const peerIdOf = (c: Call | null) => {
    const me = meRef.current;
    const others = (c?.participants || []).filter((p: string) => p !== me);
    return others[0] || c?.caller_id || null;
  };
  const isDm = (c: Call | null) => (c?.mode || "dm") === "dm";

  // ---------------------------------------------------------------- media ----
  const getIceServers = async () => {
    if (iceServersRef.current) return iceServersRef.current;
    try {
      const r = await api.get<{ iceServers: any[] }>("/calls/ice-servers");
      iceServersRef.current = r.iceServers || [];
    } catch {
      iceServersRef.current = [{ urls: ["stun:stun.l.google.com:19302"] }];
    }
    return iceServersRef.current!;
  };

  const acquireMedia = async (type: "voice" | "video") => {
    if (!rtcAvailable) { setMediaError(unavailableReason); mediaReady.current = true; return null; }
    try {
      if (Platform.OS !== "web") await ensureMicPermission();
      const constraints: any = {
        audio: { echoCancellation: true, noiseSuppression: true, autoGainControl: true },
        video: type === "video" ? { facingMode: "user", width: { ideal: 640 }, height: { ideal: 480 }, frameRate: { ideal: 24 } } : false,
      };
      const stream = await getUserMedia(constraints);
      localRef.current = stream;
      setLocalStream(stream);
      setMediaError(null);
      return stream;
    } catch (e: any) {
      setMediaError(type === "video" ? "Camera/microphone access was denied. Enable it in Settings to use calls." : "Microphone access was denied. Enable it in Settings to use calls.");
      return null;
    } finally {
      mediaReady.current = true;
    }
  };

  const flushIce = async () => {
    const p = pc.current;
    if (!p || !p.remoteDescription) return;
    const queued = pendingIce.current; pendingIce.current = [];
    for (const c of queued) { try { await p.addIceCandidate(c); } catch {} }
  };

  const createPeer = async (stream: any) => {
    if (pc.current) return pc.current;
    const iceServers = await getIceServers();
    const p = createPeerConnection({ iceServers, iceCandidatePoolSize: 2 });
    if (stream) stream.getTracks().forEach((t: any) => p.addTrack(t, stream));
    p.onicecandidate = (ev: any) => {
      const c = callRef.current;
      if (ev.candidate && c) {
        const cand = typeof ev.candidate.toJSON === "function" ? ev.candidate.toJSON() : ev.candidate;
        send({ type: "call_ice", to: peerIdOf(c), call_id: c.call_id, candidate: cand });
      }
    };
    p.ontrack = (ev: any) => {
      const s = ev.streams && ev.streams[0];
      if (s) setRemoteStream(s);
    };
    p.onconnectionstatechange = () => {
      const st = p.connectionState;
      setConnState(st);
      if (st === "failed") setMediaError("Connection failed. Check your network and try again.");
    };
    pc.current = p;
    return p;
  };

  const sendOffer = async () => {
    const c = callRef.current; if (!c) return;
    const p = await createPeer(localRef.current);
    const offer = await p.createOffer({ offerToReceiveAudio: true, offerToReceiveVideo: c.type === "video" });
    await p.setLocalDescription(offer);
    const d = p.localDescription || offer;
    send({ type: "call_offer", to: peerIdOf(c), call_id: c.call_id, sdp: { type: d.type, sdp: d.sdp } });
  };

  const handleOffer = async (sdp: any) => {
    const c = callRef.current; if (!c) return;
    const p = await createPeer(localRef.current);
    await p.setRemoteDescription(sdp);
    await flushIce();
    const answer = await p.createAnswer();
    await p.setLocalDescription(answer);
    const d = p.localDescription || answer;
    send({ type: "call_answer", to: peerIdOf(c), call_id: c.call_id, sdp: { type: d.type, sdp: d.sdp } });
  };

  const handleAnswer = async (sdp: any) => {
    const p = pc.current; if (!p) return;
    try { await p.setRemoteDescription(sdp); await flushIce(); } catch {}
  };

  const handleIce = async (candidate: any) => {
    const p = pc.current;
    if (p && p.remoteDescription) { try { await p.addIceCandidate(candidate); } catch {} }
    else pendingIce.current.push(candidate);
  };

  // --------------------------------------------------------- transcription ----
  const uploadChunk = async (callId: string, chunk: CaptureChunk, seq: number) => {
    const form = new FormData();
    if (chunk.blob) form.append("file", chunk.blob, chunk.name);
    else form.append("file", { uri: chunk.uri, name: chunk.name, type: chunk.type } as any);
    form.append("seq", String(seq));
    form.append("at", chunk.startedAt);
    form.append("language", "auto");
    const token = await storage.secureGet<string>(TOKEN_KEY, "");
    const res = await fetch(`${BASE}/calls/${callId}/transcript-chunk`, {
      method: "POST", headers: { Authorization: `Bearer ${token}` }, body: form,
    });
    if (res.status === 403) throw new Error("privacy");
  };

  const startTranscription = async () => {
    const c = callRef.current;
    if (!c || stopCapture.current || !ccOnRef.current) return;
    if (!rtcAvailable && Platform.OS !== "web") { setCcState("unavailable"); return; }
    try {
      const r = await api.get<{ privacy: any }>("/ai/privacy");
      if (r.privacy?.call_intelligence === false || r.privacy?.call_transcription === false) { setCcState("off"); return; }
    } catch {}
    const callId = c.call_id;
    const stop = await startChunkedCapture({
      recorder,
      intervalMs: CHUNK_MS,
      onChunk: (chunk, seq) => {
        uploadChunk(callId, chunk, seq).catch((e) => {
          if (e?.message === "privacy") { setCcState("off"); stopCapture.current?.(); stopCapture.current = null; }
        });
      },
      onUnavailable: () => { setCcState("unavailable"); stopCapture.current = null; },
    });
    stopCapture.current = stop;
    setCcState((s) => (s === "unavailable" || s === "off" ? s : "live"));
  };

  const stopTranscription = () => {
    if (stopCapture.current) { try { stopCapture.current(); } catch {} stopCapture.current = null; }
  };

  const toggleCc = () => {
    setCcOn((on) => {
      const next = !on; ccOnRef.current = next;
      if (!next) { stopTranscription(); setCcState("idle"); }
      else if (phaseRef.current === "connected") { setTimeout(() => startTranscription(), 0); }
      return next;
    });
  };

  // ------------------------------------------------------------ lifecycle ----
  const cleanupMedia = useCallback(() => {
    stopTranscription();
    try { pc.current?.close(); } catch {}
    pc.current = null;
    try { localRef.current?.getTracks?.().forEach((t: any) => t.stop()); } catch {}
    localRef.current = null;
    pendingIce.current = []; pendingOffer.current = null; mediaReady.current = false;
    setLocalStream(null); setRemoteStream(null); setConnState("new");
    if (Platform.OS !== "web") setCallAudioMode(false, true);
  }, []);

  const reset = useCallback((goIntel?: string) => {
    clearTimer(); cleanupMedia();
    setCall(null); callRef.current = null; setPhase("outgoing"); setMuted(false); setCamOff(false);
    setMediaError(null); setCaptions([]); setCcState("idle"); setShowAllCaptions(false);
    if (goIntel) router.push({ pathname: "/call-intelligence/[id]", params: { id: goIntel } });
  }, [router, cleanupMedia]);

  const onConnected = useCallback(async () => {
    setPhase("connected"); phaseRef.current = "connected"; startTimer();
    if (Platform.OS !== "web") await setCallAudioMode(true, speakerRef.current);
    startTranscription();
  }, []); // eslint-disable-line react-hooks/exhaustive-deps

  useEffect(() => subscribe(async (ev) => {
    const c = callRef.current;
    if (ev.type === "incoming_call") {
      if (c) return; // already in a call; let the caller time out
      roleRef.current = "callee";
      setCall(ev.call); callRef.current = ev.call; setPhase("incoming"); phaseRef.current = "incoming";
      setSpeaker(ev.call?.type === "video"); speakerRef.current = ev.call?.type === "video";
      setCamOff(ev.call?.type !== "video");
      Haptics.notificationAsync(Haptics.NotificationFeedbackType.Warning).catch(() => {});
      startRingtone().catch(() => {});
      return;
    }
    if (!c || (ev.call_id && ev.call_id !== c.call_id)) return;
    if (ev.type === "call_accepted") {
      stopRingtone().catch(() => {});
      await onConnected();
      if (roleRef.current === "caller" && isDm(c) && rtcAvailable) {
        if (!mediaReady.current) await acquireMedia(c.type);
        try { await sendOffer(); } catch { setMediaError("Could not start media."); }
      }
    } else if (ev.type === "call_offer") {
      if (!rtcAvailable) return;
      if (!mediaReady.current) { pendingOffer.current = ev.sdp; return; }
      try { await handleOffer(ev.sdp); } catch { setMediaError("Could not start media."); }
    } else if (ev.type === "call_answer") {
      await handleAnswer(ev.sdp);
    } else if (ev.type === "call_ice") {
      await handleIce(ev.candidate);
    } else if (ev.type === "call_transcript") {
      const seg: Segment = ev.segment;
      if (seg) setCaptions((prev) => (prev.some((s) => s.id === seg.id) ? prev : [...prev, seg]));
    } else if (ev.type === "call_rejected") {
      stopRingtone().catch(() => {});
      setPhase("ended"); setTimeout(() => reset(), 1200);
    } else if (ev.type === "call_ended") {
      stopRingtone().catch(() => {});
      setPhase("ended"); cleanupMedia();
      const cid = c?.call_id || ev.call_id;
      setTimeout(() => reset(ev.duration > 0 ? cid : undefined), 1200);
    }
  }), [subscribe, reset, cleanupMedia, onConnected]); // eslint-disable-line react-hooks/exhaustive-deps

  const startCall = useCallback(async (chatId: string, name: string, type: "voice" | "video") => {
    try {
      roleRef.current = "caller";
      const res = await api.post<{ call: Call }>("/calls", { chat_id: chatId, type });
      const c = { ...res.call, caller_name: "You", peerName: name };
      setCall(c); callRef.current = c;
      setPhase("outgoing"); phaseRef.current = "outgoing";
      setCamOff(type === "voice"); setSpeaker(type === "video"); speakerRef.current = type === "video";
      // Grab mic/camera now so the permission prompt and self-preview happen while ringing.
      if (isDm(c)) acquireMedia(type);
    } catch { /* toast handled by api layer */ }
  }, []); // eslint-disable-line react-hooks/exhaustive-deps

  const accept = async () => {
    const c = callRef.current; if (!c) return;
    stopRingtone().catch(() => {});
    try {
      await api.post(`/calls/${c.call_id}/accept`);
      await onConnected();
      if (isDm(c)) {
        await acquireMedia(c.type);
        if (pendingOffer.current) { const o = pendingOffer.current; pendingOffer.current = null; try { await handleOffer(o); } catch {} }
      }
    } catch {}
  };
  const reject = async () => {
    const c = callRef.current; if (!c) return;
    stopRingtone().catch(() => {});
    try { await api.post(`/calls/${c.call_id}/reject`); } catch {}
    reset();
  };
  const end = async () => {
    const c = callRef.current; if (!c) return;
    stopRingtone().catch(() => {});
    cleanupMedia();
    try { const r = await api.post<{ duration: number }>(`/calls/${c.call_id}/end`); reset(r.duration > 0 ? c.call_id : undefined); }
    catch { reset(); }
  };

  const toggleMute = () => {
    setMuted((m) => {
      const next = !m;
      try { localRef.current?.getAudioTracks?.().forEach((t: any) => { t.enabled = !next; }); } catch {}
      return next;
    });
  };
  const toggleCam = () => {
    setCamOff((off) => {
      const next = !off;
      try { localRef.current?.getVideoTracks?.().forEach((t: any) => { t.enabled = !next; }); } catch {}
      return next;
    });
  };
  const toggleSpeaker = () => {
    setSpeaker((s) => {
      const next = !s; speakerRef.current = next;
      if (Platform.OS !== "web") setCallAudioMode(true, next);
      return next;
    });
  };
  const flipCamera = () => switchCamera(localRef.current);

  // ------------------------------------------------------------------ view ----
  const visible = !!call;
  const isVideo = call?.type === "video";
  const peerName = call?.peerName || call?.caller_name || call?.peer?.name || "Call";
  const peerAvatar = call?.caller_avatar || call?.peer?.avatar;
  const fmt = (s: number) => `${String(Math.floor(s / 60)).padStart(2, "0")}:${String(s % 60).padStart(2, "0")}`;
  const connecting = phase === "connected" && rtcAvailable && isDm(call) && connState !== "connected" && connState !== "completed";
  const statusLabel = phase === "incoming" ? `Incoming ${isVideo ? "video" : "voice"} call`
    : phase === "outgoing" ? "Calling…" : phase === "ended" ? "Call ended"
    : connecting ? `Connecting… ${fmt(seconds)}` : fmt(seconds);
  const showRemoteVideo = isVideo && phase === "connected" && !!remoteStream;
  const showLocalVideo = isVideo && !!localStream && !camOff && phase !== "ended";
  const recent = showAllCaptions ? captions : captions.slice(-3);
  const banner = mediaError || (!rtcAvailable && Platform.OS !== "web" && phase !== "ended" ? unavailableReason : null)
    || (call && !isDm(call) && phase === "connected" ? "Group call audio/video is coming soon — this is a signaling-only session." : null);

  return (
    <Ctx.Provider value={{ startCall }}>
      {children}
      <Modal visible={visible} animationType="slide" onRequestClose={() => {}} statusBarTranslucent>
        <View style={[styles.fill, { backgroundColor: isVideo ? "#0B0B0E" : colors.brandPrimary }]}>
          {/* Remote video (full-screen) */}
          {showRemoteVideo ? (
            <RTCVideoView stream={remoteStream} style={styles.remoteVideo} zOrder={0} />
          ) : (
            <LinearGradient colors={isVideo ? ["#101014", "#1C1C1E"] : [colors.brandPrimary, "#B33F00"]} style={styles.remoteVideo} />
          )}
          <RemoteAudio stream={remoteStream} />

          {/* Top: name + status */}
          <View style={[styles.top, { paddingTop: insets.top + spacing.lg }]} pointerEvents="box-none">
            {!showRemoteVideo && (
              <View style={{ alignItems: "center", marginTop: spacing.xxl }}>
                <Avatar name={peerName} uri={peerAvatar} size={112} />
              </View>
            )}
            <AppText size="xxl" weight="heavy" color="#fff" style={{ marginTop: spacing.lg, textAlign: "center" }}>{peerName}</AppText>
            <View testID="call-status" style={{ flexDirection: "row", alignItems: "center", justifyContent: "center", marginTop: 6 }}>
              {phase === "connected" && <View style={[styles.dot, { backgroundColor: connecting ? "#FFD60A" : "#34C759" }]} />}
              <AppText size="lg" color="rgba(255,255,255,0.9)">{statusLabel}</AppText>
            </View>
            {phase === "connected" && ccState === "live" && (
              <View style={styles.pill}>
                <View style={[styles.dot, { backgroundColor: "#FF453A" }]} />
                <AppText size="xs" color="#fff">Live transcript</AppText>
              </View>
            )}
            {!!banner && (
              <View style={styles.banner}>
                <Icon name="information-circle" size={16} color="#fff" />
                <AppText size="sm" color="#fff" style={{ marginLeft: 6, flex: 1 }}>{banner}</AppText>
              </View>
            )}
          </View>

          {/* Local preview (PiP) */}
          {showLocalVideo && (
            <View style={[styles.pip, { top: insets.top + spacing.lg, right: spacing.lg }]}>
              <RTCVideoView stream={localStream} style={styles.pipVideo} mirror zOrder={1} />
            </View>
          )}

          {/* Bottom: captions + controls */}
          <View style={[styles.bottom, { paddingBottom: insets.bottom + spacing.xl }]}>
            {phase === "connected" && captions.length > 0 && (
              <Pressable testID="captions" onPress={() => setShowAllCaptions((v) => !v)} style={[styles.captions, showAllCaptions && { maxHeight: 260 }]}>
                {recent.map((s) => (
                  <AppText key={s.id} size="sm" color="#fff" style={{ marginBottom: 4 }}>
                    <AppText size="sm" weight="bold" color="rgba(255,255,255,0.75)">{s.speaker_id === meRef.current ? "You" : s.speaker}: </AppText>
                    {s.text}
                  </AppText>
                ))}
              </Pressable>
            )}

            {phase === "incoming" ? (
              <View style={{ flexDirection: "row", justifyContent: "space-around" }}>
                <CallBtn testID="reject-call" icon="close" bg={colors.error} label="Decline" onPress={reject} />
                <CallBtn testID="accept-call" icon="call" bg={colors.success} label="Accept" onPress={accept} />
              </View>
            ) : (
              <>
                {phase !== "ended" && (
                  <View style={styles.controlsRow}>
                    <CallBtn testID="toggle-mute" icon={muted ? "mic-off" : "mic"} bg={muted ? "#fff" : "rgba(255,255,255,0.2)"} fg={muted ? "#111" : "#fff"} label={muted ? "Unmute" : "Mute"} small onPress={toggleMute} />
                    {Platform.OS !== "web" && (
                      <CallBtn testID="toggle-speaker" icon={speaker ? "volume-high" : "volume-mute"} bg={speaker ? "#fff" : "rgba(255,255,255,0.2)"} fg={speaker ? "#111" : "#fff"} label="Speaker" small onPress={toggleSpeaker} />
                    )}
                    {isVideo && <CallBtn testID="toggle-cam" icon={camOff ? "videocam-off" : "videocam"} bg={camOff ? "#fff" : "rgba(255,255,255,0.2)"} fg={camOff ? "#111" : "#fff"} label="Camera" small onPress={toggleCam} />}
                    {isVideo && canSwitchCamera && !camOff && <CallBtn testID="flip-cam" icon="camera-reverse" bg="rgba(255,255,255,0.2)" label="Flip" small onPress={flipCamera} />}
                    {phase === "connected" && (
                      <CallBtn testID="toggle-cc" icon={ccOn ? "chatbox-ellipses" : "chatbox-ellipses-outline"} bg={ccOn ? "#fff" : "rgba(255,255,255,0.2)"} fg={ccOn ? "#111" : "#fff"} label={ccState === "off" ? "CC off" : ccState === "unavailable" ? "No CC" : "Transcript"} small onPress={toggleCc} />
                    )}
                  </View>
                )}
                <View style={{ alignItems: "center" }}>
                  <CallBtn testID="end-call" icon="call" bg={colors.error} label="End" rotate onPress={end} />
                </View>
              </>
            )}
          </View>
        </View>
      </Modal>
    </Ctx.Provider>
  );
}

function CallBtn({ icon, bg, fg = "#fff", label, onPress, small, rotate, testID }: any) {
  const size = small ? 56 : 68;
  return (
    <Pressable testID={testID} onPress={onPress} style={{ alignItems: "center", minWidth: 64 }}>
      <View style={{ width: size, height: size, borderRadius: size / 2, backgroundColor: bg, alignItems: "center", justifyContent: "center", transform: rotate ? [{ rotate: "135deg" }] : undefined }}>
        <Icon name={icon} size={small ? 24 : 30} color={fg} />
      </View>
      <AppText size="sm" color="rgba(255,255,255,0.9)" style={{ marginTop: 8 }}>{label}</AppText>
    </Pressable>
  );
}

const styles = StyleSheet.create({
  fill: { flex: 1 },
  remoteVideo: { position: "absolute", top: 0, left: 0, right: 0, bottom: 0 },
  top: { paddingHorizontal: spacing.xl },
  bottom: { position: "absolute", left: 0, right: 0, bottom: 0, paddingHorizontal: spacing.xl },
  controlsRow: { flexDirection: "row", justifyContent: "center", alignItems: "flex-start", flexWrap: "wrap", gap: spacing.md, marginBottom: spacing.xl },
  pip: { position: "absolute", width: 108, height: 152, borderRadius: radius.lg, overflow: "hidden", backgroundColor: "#222", borderWidth: 1.5, borderColor: "rgba(255,255,255,0.35)" },
  pipVideo: { width: "100%", height: "100%" },
  captions: { backgroundColor: "rgba(0,0,0,0.55)", borderRadius: radius.lg, paddingHorizontal: spacing.md, paddingVertical: spacing.sm, marginBottom: spacing.lg, overflow: "hidden" },
  dot: { width: 8, height: 8, borderRadius: 4, marginRight: 6 },
  pill: { alignSelf: "center", flexDirection: "row", alignItems: "center", backgroundColor: "rgba(0,0,0,0.35)", paddingHorizontal: spacing.md, paddingVertical: 4, borderRadius: radius.pill, marginTop: spacing.sm },
  banner: { flexDirection: "row", alignItems: "center", backgroundColor: "rgba(0,0,0,0.4)", borderRadius: radius.md, padding: spacing.md, marginTop: spacing.lg },
});

export const useCall = () => useContext(Ctx);
