import { useCallback, useState } from "react";
import { View, ScrollView, Pressable, TextInput, StyleSheet, ActivityIndicator, Modal } from "react-native";
import { useRouter, useLocalSearchParams } from "expo-router";
import { useFocusEffect } from "expo-router";
import { useSafeAreaInsets } from "react-native-safe-area-context";
import { useTheme, spacing, radius, fontSize } from "@/src/theme";
import { AppText, Icon, EmptyState, Loading, useToast, Button } from "@/src/ui";
import { api } from "@/src/api";
import { useAuth } from "@/src/auth";

type Poll = {
  id: string; chat_id: string; question: string; status: string; created_at: string;
  final_decision?: any;
  options: { id: string; label: string; votes: string[] }[];
};

export default function GroupAssistant() {
  const { colors } = useTheme();
  const insets = useSafeAreaInsets();
  const router = useRouter();
  const toast = useToast();
  const { user } = useAuth();
  const { id, name } = useLocalSearchParams<{ id: string; name?: string }>();
  const [assistant, setAssistant] = useState<any | null>(null);
  const [loading, setLoading] = useState(true);
  const [polls, setPolls] = useState<Poll[]>([]);
  const [analysis, setAnalysis] = useState<any | null>(null);
  const [analyzing, setAnalyzing] = useState(false);
  const [showPoll, setShowPoll] = useState(false);
  const [question, setQuestion] = useState("");
  const [optionsText, setOptionsText] = useState("");
  const [creating, setCreating] = useState(false);

  const load = useCallback(async () => {
    setLoading(true);
    try {
      const a = await api.get<{ assistant: any }>(`/groups/${id}/assistant`);
      setAssistant(a.assistant || {});
      const p = await api.get<{ polls: Poll[] }>(`/groups/${id}/decision-maker/polls`);
      setPolls(p.polls || []);
    } catch (e: any) { toast.show(e?.message || "Failed", "error"); }
    finally { setLoading(false); }
  }, [id, toast]);
  useFocusEffect(useCallback(() => { load(); }, [load]));

  const analyzeDecision = async () => {
    setAnalyzing(true); setAnalysis(null);
    try {
      const r = await api.post<{ analysis: any }>(`/groups/${id}/decision-maker/analyze`);
      setAnalysis(r.analysis || {});
      if (r.analysis?.question) setQuestion(r.analysis.question);
      if (Array.isArray(r.analysis?.options)) setOptionsText(r.analysis.options.map((o: any) => o.label).join("\n"));
    } catch (e: any) { toast.show(e?.message || "Failed", "error"); }
    finally { setAnalyzing(false); }
  };

  const createPoll = async () => {
    const opts = optionsText.split("\n").map((s) => s.trim()).filter(Boolean);
    if (!question.trim() || opts.length < 2) { toast.show("Enter a question and at least 2 options.", "info"); return; }
    setCreating(true);
    try {
      await api.post(`/groups/${id}/decision-maker/polls`, { question: question.trim(), options: opts });
      toast.show("Poll created", "success");
      setShowPoll(false); setQuestion(""); setOptionsText(""); load();
    } catch (e: any) { toast.show(e?.message || "Failed", "error"); }
    finally { setCreating(false); }
  };

  const vote = async (p: Poll, optionId: string) => {
    try {
      await api.post(`/groups/${id}/decision-maker/polls/${p.id}/vote`, { option_id: optionId });
      load();
    } catch (e: any) { toast.show(e?.message || "Failed", "error"); }
  };

  const closePoll = async (p: Poll) => {
    try {
      await api.post(`/groups/${id}/decision-maker/polls/${p.id}/close`);
      load();
    } catch (e: any) { toast.show(e?.message || "Failed", "error"); }
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
            <AppText style={{ flex: 1 }}>{typeof t === "string" ? t : t.text || JSON.stringify(t)}</AppText>
          </View>
        ))}
      </View>
    );
  };

  return (
    <View style={{ flex: 1, backgroundColor: colors.surface }}>
      <View style={{ paddingTop: insets.top + 6, paddingBottom: spacing.sm, paddingHorizontal: spacing.md, flexDirection: "row", alignItems: "center", backgroundColor: colors.card, borderBottomWidth: 1, borderBottomColor: colors.border }}>
        <Pressable onPress={() => router.back()} hitSlop={10}><Icon name="chevron-back" size={26} /></Pressable>
        <AppText weight="heavy" size="xl" style={{ marginLeft: spacing.sm, flex: 1 }} numberOfLines={1}>{name || "Group AI"}</AppText>
        <Pressable onPress={() => setShowPoll(true)} style={{ paddingHorizontal: 12, height: 36, borderRadius: 18, backgroundColor: colors.brandTertiary, alignItems: "center", justifyContent: "center", flexDirection: "row" }}>
          <Icon name="checkmark-done" size={16} color={colors.brandPrimary} />
          <AppText size="sm" weight="bold" color={colors.brandPrimary} style={{ marginLeft: 6 }}>New Poll</AppText>
        </Pressable>
      </View>
      <ScrollView contentContainerStyle={{ padding: spacing.md, paddingBottom: spacing.xxl }}>
        {loading ? <Loading /> : (
          <>
            <View style={{ backgroundColor: colors.card, borderColor: colors.border, borderWidth: 1, borderRadius: radius.md, padding: spacing.md }}>
              <View style={{ flexDirection: "row", alignItems: "center" }}>
                <Icon name="people" size={18} color={colors.brandPrimary} />
                <AppText weight="bold" size="lg" style={{ marginLeft: 8 }}>Group Summary</AppText>
              </View>
              {assistant?.summary ? <AppText style={{ marginTop: 6 }}>{assistant.summary}</AppText> :
                <AppText muted style={{ marginTop: 6 }}>Not enough conversation yet.</AppText>}
            </View>
            <Section title="Decisions" items={assistant?.decisions} icon="checkmark-done" />
            <Section title="Action items" items={assistant?.action_items} icon="flash" />
            <Section title="Open questions" items={assistant?.questions} icon="help-circle" />

            <View style={{ marginTop: spacing.lg }}>
              <Pressable onPress={analyzeDecision} style={{ backgroundColor: colors.brandTertiary, borderRadius: radius.md, padding: spacing.md, flexDirection: "row", alignItems: "center" }}>
                <Icon name="sparkles" size={18} color={colors.brandPrimary} />
                <AppText weight="bold" color={colors.brandPrimary} style={{ marginLeft: 8, flex: 1 }}>Detect a decision to vote on</AppText>
                {analyzing ? <ActivityIndicator size="small" color={colors.brandPrimary} /> : <Icon name="chevron-forward" size={18} color={colors.brandPrimary} />}
              </Pressable>
              {analysis?.question ? (
                <View style={{ backgroundColor: colors.card, borderColor: colors.border, borderWidth: 1, borderRadius: radius.md, padding: spacing.md, marginTop: spacing.sm }}>
                  <AppText weight="bold">{analysis.question}</AppText>
                  {Array.isArray(analysis.options) && analysis.options.map((o: any, i: number) => (
                    <AppText key={i} style={{ marginTop: 4 }}>• {o.label}</AppText>
                  ))}
                  <Button title="Turn into a poll" onPress={() => setShowPoll(true)} />
                </View>
              ) : null}
            </View>

            <AppText weight="bold" size="sm" muted style={{ marginTop: spacing.lg, marginBottom: spacing.sm }}>POLLS</AppText>
            {polls.length === 0 ? (
              <EmptyState icon="checkmark-done-outline" title="No polls yet" subtitle="Turn a chat decision into a quick vote." />
            ) : polls.map((p) => {
              const total = p.options.reduce((s, o) => s + (o.votes?.length || 0), 0) || 1;
              const closed = p.status === "closed";
              return (
                <View key={p.id} style={{ borderWidth: 1, borderColor: colors.border, borderRadius: radius.md, padding: spacing.md, backgroundColor: colors.card, marginBottom: spacing.sm }}>
                  <AppText weight="bold" size="lg">{p.question}</AppText>
                  {p.options.map((o) => {
                    const pct = Math.round(((o.votes?.length || 0) / total) * 100);
                    const voted = !!user && (o.votes || []).includes(user.user_id);
                    return (
                      <Pressable key={o.id} disabled={closed} onPress={() => vote(p, o.id)} style={{ marginTop: 8 }}>
                        <View style={{ height: 40, borderRadius: radius.md, overflow: "hidden", backgroundColor: colors.surfaceTertiary }}>
                          <View style={{ position: "absolute", left: 0, top: 0, bottom: 0, width: `${pct}%`, backgroundColor: voted ? colors.brandPrimary + "44" : colors.brandTertiary }} />
                          <View style={{ flex: 1, flexDirection: "row", alignItems: "center", paddingHorizontal: 12 }}>
                            <Icon name={voted ? "radio-button-on" : "radio-button-off"} size={16} color={voted ? colors.brandPrimary : colors.onSurfaceMuted} />
                            <AppText weight="semibold" style={{ marginLeft: 8, flex: 1 }}>{o.label}</AppText>
                            <AppText size="sm" muted>{pct}%</AppText>
                          </View>
                        </View>
                      </Pressable>
                    );
                  })}
                  <View style={{ flexDirection: "row", alignItems: "center", marginTop: spacing.sm }}>
                    <AppText size="xs" muted style={{ flex: 1 }}>{total} votes · {closed ? `Closed — winner: ${p.final_decision?.label || "—"}` : "Open"}</AppText>
                    {!closed && (
                      <Pressable onPress={() => closePoll(p)}>
                        <AppText size="sm" weight="bold" color={colors.brandPrimary}>Close poll</AppText>
                      </Pressable>
                    )}
                  </View>
                </View>
              );
            })}
          </>
        )}
      </ScrollView>

      <Modal visible={showPoll} transparent animationType="slide" onRequestClose={() => setShowPoll(false)}>
        <Pressable style={{ flex: 1, backgroundColor: colors.overlay }} onPress={() => setShowPoll(false)} />
        <View style={[styles.sheet, { backgroundColor: colors.card, paddingBottom: insets.bottom + spacing.lg }]}>
          <AppText weight="bold" size="lg" style={{ marginBottom: spacing.sm }}>New Poll</AppText>
          <TextInput value={question} onChangeText={setQuestion} placeholder="Question" placeholderTextColor={colors.onSurfaceMuted}
            style={{ borderWidth: 1, borderColor: colors.border, borderRadius: radius.md, paddingHorizontal: spacing.md, height: 46, color: colors.onSurface, fontSize: fontSize.base, marginBottom: spacing.sm }} />
          <TextInput value={optionsText} onChangeText={setOptionsText} placeholder="One option per line" placeholderTextColor={colors.onSurfaceMuted} multiline
            style={{ borderWidth: 1, borderColor: colors.border, borderRadius: radius.md, paddingHorizontal: spacing.md, minHeight: 100, color: colors.onSurface, fontSize: fontSize.base, marginBottom: spacing.md, textAlignVertical: "top", paddingVertical: 10 }} />
          <Button title="Create Poll" onPress={createPoll} loading={creating} />
        </View>
      </Modal>
    </View>
  );
}

const styles = StyleSheet.create({
  sheet: { position: "absolute", bottom: 0, left: 0, right: 0, borderTopLeftRadius: radius.xl, borderTopRightRadius: radius.xl, padding: spacing.lg },
});
