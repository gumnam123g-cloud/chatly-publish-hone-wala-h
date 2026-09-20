// Combined screen: AI Meeting Mode + AI Negotiation Assistant.
import { useState } from "react";
import { View, ScrollView, Pressable, TextInput, StyleSheet } from "react-native";
import { useRouter, useLocalSearchParams } from "expo-router";
import { useSafeAreaInsets } from "react-native-safe-area-context";
import * as Clipboard from "expo-clipboard";
import { useTheme, spacing, radius, fontSize } from "@/src/theme";
import { AppText, Icon, Button, useToast, Loading } from "@/src/ui";
import { api } from "@/src/api";

export default function MeetingMode() {
  const { colors } = useTheme();
  const insets = useSafeAreaInsets();
  const router = useRouter();
  const toast = useToast();
  const { chat_id, mode: initMode } = useLocalSearchParams<{ chat_id?: string; mode?: string }>();
  const [tab, setTab] = useState<"meeting" | "negotiate">(initMode === "negotiate" ? "negotiate" : "meeting");
  const [meeting, setMeeting] = useState<any | null>(null);
  const [negotiation, setNegotiation] = useState<any | null>(null);
  const [goal, setGoal] = useState("Reach a fair agreement");
  const [busy, setBusy] = useState(false);
  const [hours, setHours] = useState("24");

  const runMeeting = async () => {
    if (!chat_id) return toast.show("Open from a chat's menu.", "info");
    setBusy(true); setMeeting(null);
    try {
      const r = await api.post<any>("/ai/meeting-mode", { chat_id, hours: Number(hours) || 24 });
      setMeeting(r);
    } catch (e: any) { toast.show(e?.message || "Failed", "error"); }
    finally { setBusy(false); }
  };

  const runNegotiate = async () => {
    if (!chat_id) return toast.show("Open from a chat's menu.", "info");
    setBusy(true); setNegotiation(null);
    try {
      const r = await api.post<any>("/ai/negotiate", { chat_id, goal });
      setNegotiation(r);
    } catch (e: any) { toast.show(e?.message || "Failed", "error"); }
    finally { setBusy(false); }
  };

  const Section = ({ title, items, icon }: { title: string; items?: any[]; icon: string }) => {
    if (!items?.length) return null;
    return (
      <View style={{ marginTop: spacing.lg }}>
        <View style={{ flexDirection: "row", alignItems: "center", marginBottom: spacing.sm }}>
          <Icon name={icon as any} size={18} color={colors.brandPrimary} />
          <AppText weight="bold" size="lg" style={{ marginLeft: 8 }}>{title}</AppText>
        </View>
        {items.map((t, i) => (
          <View key={i} style={{ flexDirection: "row", alignItems: "flex-start", paddingVertical: 6 }}>
            <View style={{ width: 6, height: 6, borderRadius: 3, backgroundColor: colors.brandPrimary, marginTop: 8, marginRight: 8 }} />
            <AppText style={{ flex: 1 }}>{typeof t === "string" ? t : (t.title || t.owner || t.name || JSON.stringify(t))}</AppText>
          </View>
        ))}
      </View>
    );
  };

  return (
    <View style={{ flex: 1, backgroundColor: colors.surface }}>
      <View style={{ paddingTop: insets.top + 6, paddingBottom: spacing.sm, paddingHorizontal: spacing.md, flexDirection: "row", alignItems: "center", backgroundColor: colors.card, borderBottomWidth: 1, borderBottomColor: colors.border }}>
        <Pressable onPress={() => router.back()} hitSlop={10}><Icon name="chevron-back" size={26} /></Pressable>
        <AppText weight="heavy" size="xxl" style={{ marginLeft: spacing.sm, flex: 1 }}>Meeting & Negotiate</AppText>
      </View>
      <View style={{ flexDirection: "row", padding: spacing.md, gap: 8 }}>
        {(["meeting", "negotiate"] as const).map((k) => (
          <Pressable key={k} onPress={() => setTab(k)} style={{ flex: 1, height: 40, borderRadius: radius.md, borderWidth: 1, borderColor: tab === k ? colors.brandPrimary : colors.border, backgroundColor: tab === k ? colors.brandTertiary : "transparent", alignItems: "center", justifyContent: "center" }}>
            <AppText weight="semibold" style={{ textTransform: "capitalize" }}>{k === "meeting" ? "Meeting Mode" : "Negotiate"}</AppText>
          </Pressable>
        ))}
      </View>
      <ScrollView contentContainerStyle={{ padding: spacing.md, paddingBottom: spacing.xxl }}>
        {tab === "meeting" ? (
          <>
            <AppText muted size="sm">Chatly analyzes the recent conversation and extracts a meeting brief. It never posts on your behalf.</AppText>
            <TextInput value={hours} onChangeText={setHours} placeholder="Look-back hours" keyboardType="number-pad" placeholderTextColor={colors.onSurfaceMuted}
              style={{ marginTop: spacing.sm, borderWidth: 1, borderColor: colors.border, borderRadius: radius.md, paddingHorizontal: spacing.md, height: 42, color: colors.onSurface, fontSize: fontSize.base }} />
            <Button title="Run Meeting Mode" onPress={runMeeting} loading={busy} />
            {busy && <Loading />}
            {meeting && (
              <View style={{ marginTop: spacing.md, backgroundColor: colors.card, borderColor: colors.border, borderWidth: 1, borderRadius: radius.md, padding: spacing.md }}>
                {meeting.summary && <AppText>{meeting.summary}</AppText>}
                <Section title="Decisions" items={meeting.decisions} icon="checkmark-done" />
                <Section title="Action items" items={meeting.action_items} icon="flash" />
                <Section title="Deadlines" items={meeting.deadlines} icon="time" />
                <Section title="Open questions" items={meeting.open_questions} icon="help-circle" />
              </View>
            )}
          </>
        ) : (
          <>
            <AppText muted size="sm">Get 3 reply approaches. You can copy → edit → send yourself. Nothing is auto-sent.</AppText>
            <TextInput value={goal} onChangeText={setGoal} placeholder="Your goal (e.g. defer the deadline politely)" placeholderTextColor={colors.onSurfaceMuted}
              style={{ marginTop: spacing.sm, borderWidth: 1, borderColor: colors.border, borderRadius: radius.md, paddingHorizontal: spacing.md, height: 46, color: colors.onSurface, fontSize: fontSize.base }} />
            <Button title="Suggest approaches" onPress={runNegotiate} loading={busy} />
            {busy && <Loading />}
            {negotiation && Array.isArray(negotiation.approaches) && negotiation.approaches.map((a: any, i: number) => (
              <View key={i} style={{ marginTop: spacing.md, backgroundColor: colors.card, borderColor: colors.border, borderWidth: 1, borderRadius: radius.md, padding: spacing.md }}>
                <AppText weight="bold" size="lg" style={{ textTransform: "capitalize" }}>{a.name}</AppText>
                <AppText style={{ marginTop: 6 }}>{a.message}</AppText>
                {a.why_it_works && <AppText size="xs" muted style={{ marginTop: 6 }}>Why: {a.why_it_works}</AppText>}
                {a.risks && <AppText size="xs" muted>Risks: {a.risks}</AppText>}
                <Button title="Copy reply" variant="secondary" onPress={async () => { await Clipboard.setStringAsync(a.message || ""); toast.show("Copied", "success"); }} />
              </View>
            ))}
          </>
        )}
      </ScrollView>
    </View>
  );
}

const styles = StyleSheet.create({});
