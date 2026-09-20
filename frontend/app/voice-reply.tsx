// AI Voice Reply — record → transcribe → polish → user edits → send.
import { useRef, useState } from "react";
import { View, ScrollView, Pressable, TextInput, StyleSheet } from "react-native";
import { useRouter, useLocalSearchParams } from "expo-router";
import { useSafeAreaInsets } from "react-native-safe-area-context";
import { useTheme, spacing, radius, fontSize } from "@/src/theme";
import { AppText, Icon, Button, useToast, Loading } from "@/src/ui";
import { API_ORIGIN, api } from "@/src/api";
import { useAuth } from "@/src/auth";
import { useCallRecorder, ensureMicPermission } from "@/src/useCallRecorder";

export default function VoiceReply() {
  const { colors } = useTheme();
  const insets = useSafeAreaInsets();
  const router = useRouter();
  const toast = useToast();
  const { chat_id, chat_name } = useLocalSearchParams<{ chat_id?: string; chat_name?: string }>();
  const { token } = useAuth();
  const rec = useCallRecorder();
  const [busy, setBusy] = useState(false);
  const [transcript, setTranscript] = useState("");
  const [draft, setDraft] = useState("");
  const [tone, setTone] = useState<"friendly" | "professional" | "firm" | "casual">("friendly");

  const startRecord = async () => {
    if (!(await ensureMicPermission())) { toast.show("Mic permission needed.", "info"); return; }
    await rec.start();
  };

  const stopAndPolish = async () => {
    const uri = await rec.stop();
    if (!uri) return;
    setBusy(true);
    try {
      const form = new FormData();
      form.append("file", { uri, name: "voice.m4a", type: "audio/m4a" } as any);
      form.append("tone", tone);
      const res = await fetch(`${API_ORIGIN}/api/ai/voice-reply`, {
        method: "POST", headers: { Authorization: `Bearer ${token}` }, body: form,
      });
      if (!res.ok) throw new Error(`HTTP ${res.status}`);
      const j = await res.json();
      setTranscript(j.transcript || ""); setDraft(j.draft || j.transcript || "");
    } catch (e: any) { toast.show(e?.message || "Failed to transcribe", "error"); }
    finally { setBusy(false); }
  };

  const send = async () => {
    if (!chat_id) { toast.show("Open this from a chat.", "info"); return; }
    if (!draft.trim()) return;
    try {
      await api.post(`/chats/${chat_id}/messages`, { text: draft.trim() });
      toast.show("Sent", "success"); router.back();
    } catch (e: any) { toast.show(e?.message || "Failed", "error"); }
  };

  return (
    <View style={{ flex: 1, backgroundColor: colors.surface }}>
      <View style={{ paddingTop: insets.top + 6, paddingBottom: spacing.sm, paddingHorizontal: spacing.md, flexDirection: "row", alignItems: "center", backgroundColor: colors.card, borderBottomWidth: 1, borderBottomColor: colors.border }}>
        <Pressable onPress={() => router.back()} hitSlop={10}><Icon name="chevron-back" size={26} /></Pressable>
        <AppText weight="heavy" size="xl" style={{ marginLeft: spacing.sm, flex: 1 }} numberOfLines={1}>{chat_name ? `Voice Reply → ${chat_name}` : "Voice Reply"}</AppText>
      </View>
      <ScrollView contentContainerStyle={{ padding: spacing.md, paddingBottom: spacing.xxl }}>
        <AppText muted size="sm">Speak naturally in English, Hindi or Hinglish. Chatly transcribes with Sarvam AI and polishes it — you decide what to send.</AppText>
        <View style={{ flexDirection: "row", flexWrap: "wrap", gap: 6, marginTop: spacing.md }}>
          {(["friendly", "professional", "firm", "casual"] as const).map((t) => (
            <Pressable key={t} onPress={() => setTone(t)} style={{ paddingHorizontal: 10, paddingVertical: 6, borderRadius: radius.pill, borderWidth: 1, borderColor: tone === t ? colors.brandPrimary : colors.border, backgroundColor: tone === t ? colors.brandTertiary : "transparent" }}>
              <AppText size="xs" weight="semibold" style={{ textTransform: "capitalize" }}>{t}</AppText>
            </Pressable>
          ))}
        </View>

        <View style={{ alignItems: "center", marginTop: spacing.xl }}>
          <Pressable onPress={rec.isRecording ? stopAndPolish : startRecord}
            style={{ width: 120, height: 120, borderRadius: 60, alignItems: "center", justifyContent: "center", backgroundColor: rec.isRecording ? colors.error : colors.brandPrimary }}>
            <Icon name={rec.isRecording ? "square" : "mic"} size={48} color="#fff" />
          </Pressable>
          <AppText muted size="sm" style={{ marginTop: spacing.sm }}>{rec.isRecording ? "Recording… tap to stop" : "Tap to record"}</AppText>
        </View>

        {busy && <Loading />}

        {transcript !== "" && (
          <View style={{ marginTop: spacing.lg, backgroundColor: colors.card, borderColor: colors.border, borderWidth: 1, borderRadius: radius.md, padding: spacing.md }}>
            <AppText size="xs" muted>Transcript</AppText>
            <AppText style={{ marginTop: 4 }}>{transcript}</AppText>
          </View>
        )}
        {draft !== "" && (
          <View style={{ marginTop: spacing.md, backgroundColor: colors.card, borderColor: colors.border, borderWidth: 1, borderRadius: radius.md, padding: spacing.md }}>
            <AppText size="xs" muted>Polished draft (editable)</AppText>
            <TextInput multiline value={draft} onChangeText={setDraft}
              style={{ marginTop: 4, minHeight: 90, color: colors.onSurface, fontSize: fontSize.base, textAlignVertical: "top" }} />
            <Button title="Send message" onPress={send} />
          </View>
        )}
      </ScrollView>
    </View>
  );
}
