import { useCallback, useState } from "react";
import { View, ScrollView, Pressable, TextInput, StyleSheet, Modal, Switch, ActivityIndicator } from "react-native";
import { useRouter } from "expo-router";
import { useFocusEffect } from "expo-router";
import { useSafeAreaInsets } from "react-native-safe-area-context";
import { useTheme, spacing, radius, fontSize } from "@/src/theme";
import { AppText, Icon, EmptyState, Loading, useToast, Button } from "@/src/ui";
import { api } from "@/src/api";

type Rule = {
  id: string; name: string; enabled: boolean;
  summary: boolean; suggest_priority: boolean; suggest_reminder: boolean; suggest_follow_up: boolean;
  chat_ids: string[];
};

type Suggestion = {
  type: string; message_id?: string; title: string; reason?: string;
  params?: any; priority?: string; remind_at?: string;
};

export default function Autopilot() {
  const { colors } = useTheme();
  const insets = useSafeAreaInsets();
  const router = useRouter();
  const toast = useToast();
  const [rules, setRules] = useState<Rule[]>([]);
  const [loading, setLoading] = useState(true);
  const [editOpen, setEditOpen] = useState(false);
  const [editing, setEditing] = useState<Rule | null>(null);
  const [saving, setSaving] = useState(false);
  const [chats, setChats] = useState<any[]>([]);
  const [analyzeChat, setAnalyzeChat] = useState<string | null>(null);
  const [suggestions, setSuggestions] = useState<Suggestion[]>([]);
  const [analyzing, setAnalyzing] = useState(false);

  const load = useCallback(async () => {
    try {
      const r = await api.get<{ rules: Rule[] }>("/ai/autopilot/rules");
      setRules(r.rules || []);
      const c = await api.get<{ chats: any[] }>("/chats");
      setChats(c.chats || []);
    } catch (e: any) { toast.show(e?.message || "Failed to load", "error"); }
    finally { setLoading(false); }
  }, [toast]);
  useFocusEffect(useCallback(() => { load(); }, [load]));

  const newRule = (): Rule => ({
    id: "", name: "New Rule", enabled: true,
    summary: true, suggest_priority: true, suggest_reminder: true, suggest_follow_up: true, chat_ids: [],
  });

  const openNew = () => { setEditing(newRule()); setEditOpen(true); };
  const openEdit = (r: Rule) => { setEditing({ ...r }); setEditOpen(true); };

  const save = async () => {
    if (!editing) return;
    setSaving(true);
    try {
      if (editing.id) await api.patch(`/ai/autopilot/rules/${editing.id}`, editing);
      else await api.post("/ai/autopilot/rules", editing);
      toast.show("Saved", "success");
      setEditOpen(false); load();
    } catch (e: any) { toast.show(e?.message || "Failed", "error"); }
    finally { setSaving(false); }
  };

  const remove = async (r: Rule) => {
    try { await api.del(`/ai/autopilot/rules/${r.id}`); load(); }
    catch (e: any) { toast.show(e?.message || "Failed", "error"); }
  };

  const analyze = async (chat_id: string) => {
    setAnalyzeChat(chat_id); setSuggestions([]); setAnalyzing(true);
    try {
      const r = await api.post<{ suggestions: Suggestion[] }>("/ai/autopilot/analyze", { chat_id });
      setSuggestions(r.suggestions || []);
    } catch (e: any) { toast.show(e?.message || "Failed", "error"); }
    finally { setAnalyzing(false); }
  };

  const confirmAction = async (s: Suggestion) => {
    try {
      await api.post("/ai/autopilot/confirm", {
        suggestion_type: s.type, message_id: s.message_id, title: s.title,
        priority: s.priority, remind_at: s.remind_at,
      });
      toast.show("Action applied", "success");
      setSuggestions((p) => p.filter((x) => x !== s));
    } catch (e: any) { toast.show(e?.message || "Failed", "error"); }
  };

  return (
    <View style={{ flex: 1, backgroundColor: colors.surface }}>
      <View style={{ paddingTop: insets.top + 6, paddingBottom: spacing.sm, paddingHorizontal: spacing.md, flexDirection: "row", alignItems: "center", backgroundColor: colors.card, borderBottomWidth: 1, borderBottomColor: colors.border }}>
        <Pressable onPress={() => router.back()} hitSlop={10}><Icon name="chevron-back" size={26} /></Pressable>
        <AppText weight="heavy" size="xxl" style={{ marginLeft: spacing.sm, flex: 1 }}>AI Autopilot</AppText>
        <Pressable onPress={openNew} style={{ width: 40, height: 40, borderRadius: 20, backgroundColor: colors.brandTertiary, alignItems: "center", justifyContent: "center" }}>
          <Icon name="add" size={24} color={colors.brandPrimary} />
        </Pressable>
      </View>
      <ScrollView contentContainerStyle={{ padding: spacing.md, paddingBottom: spacing.xxl }}>
        <AppText muted size="sm" style={{ marginBottom: spacing.sm }}>
          Autopilot never sends messages or edits your data on its own. It ONLY suggests actions — you approve each one.
        </AppText>
        <AppText weight="bold" size="sm" muted style={{ marginTop: spacing.md, marginBottom: spacing.sm }}>YOUR RULES</AppText>
        {loading ? <Loading /> : rules.length === 0 ? (
          <EmptyState icon="settings-outline" title="No rules yet" subtitle="Add a rule so Chatly can watch selected chats and surface priorities, reminders, and follow-ups for you to confirm." />
        ) : rules.map((r) => (
          <Pressable key={r.id} onPress={() => openEdit(r)} style={{ borderWidth: 1, borderColor: colors.border, borderRadius: radius.md, padding: spacing.md, backgroundColor: colors.card, marginBottom: spacing.sm }}>
            <View style={{ flexDirection: "row", alignItems: "center" }}>
              <Icon name={r.enabled ? "flash" : "flash-off-outline"} size={18} color={r.enabled ? colors.brandPrimary : colors.onSurfaceMuted} />
              <AppText weight="bold" size="lg" style={{ marginLeft: 8, flex: 1 }}>{r.name}</AppText>
              <Pressable onPress={() => remove(r)}><Icon name="trash-outline" size={20} color={colors.error} /></Pressable>
            </View>
            <AppText size="sm" muted style={{ marginTop: 6 }}>
              {[r.suggest_priority && "priority", r.suggest_reminder && "reminders", r.suggest_follow_up && "follow-ups", r.summary && "summaries"].filter(Boolean).join(" · ")}
            </AppText>
            <AppText size="xs" muted>{r.chat_ids.length ? `${r.chat_ids.length} chats` : "All conversations"}</AppText>
          </Pressable>
        ))}

        <AppText weight="bold" size="sm" muted style={{ marginTop: spacing.lg, marginBottom: spacing.sm }}>ANALYZE A CHAT</AppText>
        {chats.slice(0, 8).map((c) => (
          <Pressable key={c.chat_id} onPress={() => analyze(c.chat_id)} style={{ borderWidth: 1, borderColor: colors.border, borderRadius: radius.md, padding: spacing.md, backgroundColor: colors.card, marginBottom: spacing.sm, flexDirection: "row", alignItems: "center" }}>
            <Icon name="sparkles" size={18} color={colors.brandPrimary} />
            <AppText style={{ marginLeft: 10, flex: 1 }} numberOfLines={1}>{c.other?.name || "Chat"}</AppText>
            <Icon name="chevron-forward" size={18} color={colors.onSurfaceMuted} />
          </Pressable>
        ))}

        {analyzing && <ActivityIndicator color={colors.brandPrimary} style={{ marginTop: spacing.lg }} />}
        {suggestions.map((s, i) => (
          <View key={i} style={{ borderWidth: 1, borderColor: colors.border, borderRadius: radius.md, padding: spacing.md, backgroundColor: colors.card, marginTop: spacing.sm }}>
            <View style={{ flexDirection: "row", alignItems: "center" }}>
              <Icon name={s.type === "priority" ? "flag" : s.type === "reminder" ? "alarm" : s.type === "follow_up" ? "return-up-forward" : "document-text"} size={16} color={colors.brandPrimary} />
              <AppText weight="bold" style={{ marginLeft: 8, flex: 1 }} numberOfLines={2}>{s.title}</AppText>
            </View>
            {s.reason ? <AppText muted size="sm" style={{ marginTop: 4 }}>{s.reason}</AppText> : null}
            <Pressable onPress={() => confirmAction(s)} style={{ marginTop: spacing.sm, backgroundColor: colors.brandPrimary, alignSelf: "flex-start", paddingHorizontal: 14, paddingVertical: 8, borderRadius: radius.pill }}>
              <AppText size="sm" weight="bold" color="#fff">Confirm & apply</AppText>
            </Pressable>
          </View>
        ))}
      </ScrollView>

      <Modal visible={editOpen} transparent animationType="slide" onRequestClose={() => setEditOpen(false)}>
        <Pressable style={{ flex: 1, backgroundColor: colors.overlay }} onPress={() => setEditOpen(false)} />
        <View style={[styles.sheet, { backgroundColor: colors.card, paddingBottom: insets.bottom + spacing.lg }]}>
          <AppText weight="bold" size="lg" style={{ marginBottom: spacing.sm }}>{editing?.id ? "Edit Rule" : "New Rule"}</AppText>
          <TextInput value={editing?.name || ""} onChangeText={(v) => setEditing((e) => e ? { ...e, name: v } : e)} placeholder="Rule name" placeholderTextColor={colors.onSurfaceMuted}
            style={{ borderWidth: 1, borderColor: colors.border, borderRadius: radius.md, paddingHorizontal: spacing.md, height: 44, color: colors.onSurface, fontSize: fontSize.base, marginBottom: spacing.md }} />
          {[
            ["enabled", "Enabled"], ["summary", "Suggest summaries"], ["suggest_priority", "Suggest priority"],
            ["suggest_reminder", "Suggest reminders"], ["suggest_follow_up", "Suggest follow-ups"],
          ].map(([k, l]) => (
            <View key={k} style={{ flexDirection: "row", alignItems: "center", paddingVertical: spacing.sm }}>
              <AppText style={{ flex: 1 }}>{l}</AppText>
              <Switch value={(editing as any)?.[k]} onValueChange={(v) => setEditing((e) => e ? { ...e, [k]: v } as any : e)} />
            </View>
          ))}
          <Button title="Save Rule" onPress={save} loading={saving} />
        </View>
      </Modal>
    </View>
  );
}

const styles = StyleSheet.create({
  sheet: { position: "absolute", bottom: 0, left: 0, right: 0, borderTopLeftRadius: radius.xl, borderTopRightRadius: radius.xl, padding: spacing.lg },
});
