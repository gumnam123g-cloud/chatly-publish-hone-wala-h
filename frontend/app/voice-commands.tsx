// Voice Commands — record → interpret → confirm before acting.
import { useState } from "react";
import { View, ScrollView, Pressable, StyleSheet } from "react-native";
import { useRouter } from "expo-router";
import { useSafeAreaInsets } from "react-native-safe-area-context";
import { useTheme, spacing, radius, fontSize } from "@/src/theme";
import { AppText, Icon, Button, useToast, Loading } from "@/src/ui";
import { api, API_ORIGIN } from "@/src/api";
import { useAuth } from "@/src/auth";
import { useCallRecorder, ensureMicPermission } from "@/src/useCallRecorder";

export default function VoiceCommands() {
  const { colors } = useTheme();
  const insets = useSafeAreaInsets();
  const router = useRouter();
  const toast = useToast();
  const { token } = useAuth();
  const rec = useCallRecorder();
  const [busy, setBusy] = useState(false);
  const [transcript, setTranscript] = useState("");
  const [result, setResult] = useState<any | null>(null);

  const record = async () => {
    if (!(await ensureMicPermission())) return toast.show("Mic permission needed.", "info");
    if (rec.isRecording) {
      const uri = await rec.stop(); if (!uri) return;
      setBusy(true); setTranscript(""); setResult(null);
      try {
        // Transcribe using /ai/voice-reply endpoint (returns transcript + draft) — we only use transcript.
        const form = new FormData();
        form.append("file", { uri, name: "cmd.m4a", type: "audio/m4a" } as any);
        form.append("tone", "friendly");
        const res = await fetch(`${API_ORIGIN}/api/ai/voice-reply`, {
          method: "POST", headers: { Authorization: `Bearer ${token}` }, body: form,
        });
        const j = await res.json();
        const t = j?.transcript || "";
        setTranscript(t);
        if (!t.trim()) { toast.show("Couldn't hear you clearly.", "info"); return; }
        const r = await api.post<any>("/ai/interpret-command", { text: t });
        setResult(r);
      } catch (e: any) { toast.show(e?.message || "Failed", "error"); }
      finally { setBusy(false); }
    } else {
      await rec.start();
    }
  };

  const confirm = async () => {
    if (!result) return;
    const { intent, params } = result;
    try {
      if (intent === "reminder") {
        await api.post("/reminders", { title: params.title || transcript, remind_at: params.when || null });
        toast.show("Reminder created", "success");
      } else if (intent === "task") {
        await api.post("/tasks", { title: params.title || transcript, priority: "normal" });
        toast.show("Task created", "success");
      } else if (intent === "unread_summary") {
        router.push("/catchup");
      } else if (intent === "message_draft") {
        toast.show("Open the chat and use Voice Reply to send a draft.", "info");
      } else if (intent === "search") {
        router.push({ pathname: "/universal-search", params: { q: params.text || transcript } as any });
      } else {
        toast.show("Nothing to apply for this intent.", "info");
      }
      setResult(null); setTranscript("");
    } catch (e: any) { toast.show(e?.message || "Failed", "error"); }
  };

  return (
    <View style={{ flex: 1, backgroundColor: colors.surface }}>
      <View style={{ paddingTop: insets.top + 6, paddingBottom: spacing.sm, paddingHorizontal: spacing.md, flexDirection: "row", alignItems: "center", backgroundColor: colors.card, borderBottomWidth: 1, borderBottomColor: colors.border }}>
        <Pressable onPress={() => router.back()} hitSlop={10}><Icon name="chevron-back" size={26} /></Pressable>
        <AppText weight="heavy" size="xxl" style={{ marginLeft: spacing.sm, flex: 1 }}>Voice Commands</AppText>
      </View>
      <ScrollView contentContainerStyle={{ padding: spacing.md }}>
        <AppText muted size="sm">Examples: "Remind me to call mom tomorrow at 6", "What did I miss?", "Draft a message to Priya".</AppText>
        <View style={{ alignItems: "center", marginTop: spacing.xl }}>
          <Pressable onPress={record} style={{ width: 120, height: 120, borderRadius: 60, alignItems: "center", justifyContent: "center", backgroundColor: rec.isRecording ? colors.error : colors.brandPrimary }}>
            <Icon name={rec.isRecording ? "square" : "mic"} size={48} color="#fff" />
          </Pressable>
          <AppText muted size="sm" style={{ marginTop: spacing.sm }}>{rec.isRecording ? "Recording…" : "Tap to speak"}</AppText>
        </View>
        {busy && <Loading />}
        {transcript !== "" && <View style={{ marginTop: spacing.lg, borderColor: colors.border, borderWidth: 1, borderRadius: radius.md, padding: spacing.md, backgroundColor: colors.card }}>
          <AppText size="xs" muted>Heard</AppText>
          <AppText style={{ marginTop: 4 }}>{transcript}</AppText>
        </View>}
        {result && (
          <View style={{ marginTop: spacing.md, borderColor: colors.border, borderWidth: 1, borderRadius: radius.md, padding: spacing.md, backgroundColor: colors.card }}>
            <AppText weight="bold">Intent: {result.intent}</AppText>
            {result.confirmation && <AppText style={{ marginTop: 4 }}>{result.confirmation}</AppText>}
            <Button title="Confirm & apply" onPress={confirm} />
          </View>
        )}
      </ScrollView>
    </View>
  );
}

const styles = StyleSheet.create({});
