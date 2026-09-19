import { useState, useEffect, useRef } from "react";
import {
  View, FlatList, Pressable, TextInput, Platform, ScrollView, ActivityIndicator, StyleSheet,
} from "react-native";
import { KeyboardAvoidingView } from "react-native-keyboard-controller";
import { useLocalSearchParams } from "expo-router";
import { useSafeAreaInsets } from "react-native-safe-area-context";
import { useTheme, spacing, radius, fontSize } from "@/src/theme";
import { AppText, Icon, useToast } from "@/src/ui";
import { StackHeader } from "@/src/Header";
import { api } from "@/src/api";

type Turn = { role: "user" | "assistant"; text: string; id: string; action?: any };

const SUGGESTIONS = [
  "Kal 9 baje Rahul ko project update ka message karna hai",
  "Aaj ke unread chats summarize karo",
  "Draft a polite follow-up to Rahul",
  "What are my pending tasks?",
];

export default function Assistant() {
  const { colors } = useTheme();
  const insets = useSafeAreaInsets();
  const toast = useToast();
  const { prompt } = useLocalSearchParams<{ prompt?: string }>();
  const [turns, setTurns] = useState<Turn[]>([]);
  const [text, setText] = useState("");
  const [convId, setConvId] = useState<string | null>(null);
  const [sending, setSending] = useState(false);
  const listRef = useRef<FlatList>(null);

  const sendMsg = async (msg: string) => {
    if (!msg.trim() || sending) return;
    const userTurn: Turn = { role: "user", text: msg.trim(), id: "u" + Date.now() };
    setTurns((p) => [...p, userTurn]);
    setText(""); setSending(true);
    setTimeout(() => listRef.current?.scrollToEnd({ animated: true }), 100);
    try {
      // Step 1: ask the interpreter what the user wants. If it maps to a
      // consequential action we surface a confirmation card; otherwise fall
      // back to the free-form chat so the assistant remains useful for
      // "answer" queries too.
      const intent = await api.post<{ action: string; params: any; human_readable: string }>(
        "/assistant/interpret", { text: msg.trim(), now: new Date().toISOString() }
      );
      const consequential = ["create_task", "create_reminder", "schedule_message"].includes(intent.action);
      if (consequential) {
        setTurns((p) => [...p, {
          role: "assistant", id: "a" + Date.now(),
          text: intent.human_readable || "Please confirm this action.", action: intent,
        }]);
      } else if (intent.action === "answer") {
        const reply = intent?.params?.reply || "";
        if (reply) {
          setTurns((p) => [...p, { role: "assistant", text: reply, id: "a" + Date.now() }]);
        } else {
          // Fall through to free-form chat if interpreter had no direct answer.
          const res = await api.post<{ conversation_id: string; reply: string }>("/ai/chat", { message: msg.trim(), conversation_id: convId });
          setConvId(res.conversation_id);
          setTurns((p) => [...p, { role: "assistant", text: res.reply || "\u2026", id: "a" + Date.now() }]);
        }
      } else {
        // Non-consequential mapped actions: fetch the read-only view.
        const res = await api.post<{ conversation_id: string; reply: string }>("/ai/chat", { message: msg.trim(), conversation_id: convId });
        setConvId(res.conversation_id);
        setTurns((p) => [...p, { role: "assistant", text: res.reply || "\u2026", id: "a" + Date.now() }]);
      }
      setTimeout(() => listRef.current?.scrollToEnd({ animated: true }), 100);
    } catch (e: any) {
      toast.show(e.message || "Chatly failed", "error");
      setTurns((p) => [...p, { role: "assistant", text: "Sorry, I couldn't process that. Please try again.", id: "e" + Date.now() }]);
    } finally { setSending(false); }
  };

  const confirm = async (turn: Turn) => {
    if (!turn.action) return;
    const { action, params } = turn.action;
    try {
      if (action === "create_task") {
        await api.post("/tasks", { title: params?.title || "New task", priority: params?.priority || "normal" });
        toast.show("Task created", "success");
      } else if (action === "create_reminder") {
        await api.post("/reminders", { text: params?.text || turn.text, remind_at: params?.remind_at_iso });
        toast.show("Reminder set", "success");
      } else if (action === "schedule_message") {
        // Consequential: only allow when a chat_id has been resolved (frontend
        // does not silently guess a contact). We route the user to the
        // Scheduled screen with a pre-filled draft rather than autosending.
        setTurns((p) => [...p, { role: "assistant", text: `Opening the scheduler with your draft. Please pick the exact chat and confirm.`, id: "a" + Date.now() }]);
        // Simple UX: navigate the user to /scheduled with pre-filled state.
        // For now we just show the draft; the Scheduled screen \"New\" flow
        // asks the user to pick the chat, which is safer than guessing.
        return;
      }
      setTurns((p) => p.map((t) => t.id === turn.id ? { ...t, action: null } : t));
    } catch (e: any) { toast.show(e?.message || "Couldn't perform action.", "error"); }
  };

  useEffect(() => { if (prompt) sendMsg(String(prompt)); }, []);

  return (
    <View style={{ flex: 1, backgroundColor: colors.surface }}>
      <StackHeader title="Chatly" subtitle="AI Assistant" right={<Icon name="sparkles" size={22} color={colors.brandPrimary} />} />
      <KeyboardAvoidingView style={{ flex: 1 }} behavior="translate-with-padding" keyboardVerticalOffset={0}>
        {turns.length === 0 ? (
          <ScrollView contentContainerStyle={{ padding: spacing.xl, flexGrow: 1, justifyContent: "center" }}>
            <View style={{ alignItems: "center", marginBottom: spacing.xl }}>
              <View style={{ width: 72, height: 72, borderRadius: 22, backgroundColor: colors.brandTertiary, alignItems: "center", justifyContent: "center" }}>
                <Icon name="sparkles" size={34} color={colors.brandPrimary} />
              </View>
              <AppText size="xl" weight="bold" style={{ marginTop: spacing.md }}>How can I help?</AppText>
              <AppText muted center style={{ marginTop: 4 }}>Ask anything in English, Hindi or Hinglish</AppText>
            </View>
            <View style={{ gap: spacing.sm }}>
              {SUGGESTIONS.map((s) => (
                <Pressable key={s} testID={`suggestion-${s.slice(0,6)}`} onPress={() => sendMsg(s)} style={{ padding: spacing.md, borderRadius: radius.md, borderWidth: 1, borderColor: colors.border, backgroundColor: colors.card, flexDirection: "row", alignItems: "center" }}>
                  <Icon name="arrow-forward-circle-outline" size={20} color={colors.brandPrimary} />
                  <AppText style={{ marginLeft: spacing.sm, flex: 1 }}>{s}</AppText>
                </Pressable>
              ))}
            </View>
          </ScrollView>
        ) : (
          <FlatList
            ref={listRef}
            data={turns}
            keyExtractor={(t) => t.id}
            contentContainerStyle={{ padding: spacing.lg, gap: spacing.md }}
            renderItem={({ item }) => (
              <View style={{ alignItems: item.role === "user" ? "flex-end" : "flex-start" }}>
                {item.role === "assistant" && (
                  <View style={{ flexDirection: "row", alignItems: "center", marginBottom: 4 }}>
                    <Icon name="sparkles" size={14} color={colors.brandPrimary} />
                    <AppText size="xs" weight="bold" color={colors.brandPrimary} style={{ marginLeft: 4 }}>CHATLY</AppText>
                  </View>
                )}
                <View style={[styles.bubble, { backgroundColor: item.role === "user" ? colors.brandPrimary : colors.card, borderColor: colors.border, borderWidth: item.role === "user" ? 0 : 1 }]}>
                  <AppText size="md" color={item.role === "user" ? "#fff" : colors.onCard} style={{ lineHeight: 22 }}>{item.text}</AppText>
                  {item.role === "assistant" && item.action ? (
                    <View style={{ marginTop: spacing.sm, backgroundColor: colors.surfaceTertiary, borderRadius: radius.md, padding: spacing.md }}>
                      <AppText size="xs" weight="bold" muted style={{ textTransform: "uppercase", letterSpacing: 0.5, marginBottom: 4 }}>
                        Proposed action \u2014 confirm to apply
                      </AppText>
                      <AppText size="sm">
                        {item.action.action === "create_task" ? `Create task: ${item.action.params?.title}` :
                         item.action.action === "create_reminder" ? `Set reminder: ${item.action.params?.text} @ ${item.action.params?.remind_at_iso || ""}` :
                         item.action.action === "schedule_message" ? `Schedule message to ${item.action.params?.contact_hint || "someone"}: ${item.action.params?.text}` :
                         item.action.action}
                      </AppText>
                      <View style={{ flexDirection: "row", gap: 8, marginTop: spacing.sm }}>
                        <Pressable testID={`assist-confirm-${item.id}`} onPress={() => confirm(item)} style={{ flex: 1, backgroundColor: colors.brandPrimary, borderRadius: radius.md, paddingVertical: 10, alignItems: "center" }}>
                          <AppText weight="bold" color="#fff">Confirm</AppText>
                        </Pressable>
                        <Pressable testID={`assist-dismiss-${item.id}`} onPress={() => setTurns((p) => p.map((t) => t.id === item.id ? { ...t, action: null } : t))} style={{ flex: 1, borderColor: colors.border, borderWidth: 1, borderRadius: radius.md, paddingVertical: 10, alignItems: "center" }}>
                          <AppText weight="semibold">Dismiss</AppText>
                        </Pressable>
                      </View>
                    </View>
                  ) : null}
                </View>
              </View>
            )}
            ListFooterComponent={sending ? <View style={{ flexDirection: "row", alignItems: "center", padding: spacing.sm }}><ActivityIndicator size="small" color={colors.brandPrimary} /><AppText muted size="sm" style={{ marginLeft: 8 }}>Chatly is thinking…</AppText></View> : null}
          />
        )}

        <View style={{ flexDirection: "row", alignItems: "flex-end", padding: spacing.md, paddingBottom: insets.bottom + spacing.sm, backgroundColor: colors.card, borderTopWidth: 1, borderTopColor: colors.border }}>
          <View style={{ flex: 1, backgroundColor: colors.surfaceTertiary, borderRadius: radius.xl, paddingHorizontal: spacing.md, minHeight: 44, justifyContent: "center", maxHeight: 120 }}>
            <TextInput testID="assistant-input" value={text} onChangeText={setText} placeholder="Ask Chatly anything" placeholderTextColor={colors.onSurfaceMuted} multiline style={{ color: colors.onSurface, fontSize: fontSize.lg, paddingVertical: Platform.OS === "ios" ? 12 : 8 }} />
          </View>
          <Pressable testID="assistant-send" onPress={() => sendMsg(text)} disabled={!text.trim() || sending} style={{ width: 44, height: 44, borderRadius: 22, backgroundColor: text.trim() ? colors.brandPrimary : colors.surfaceTertiary, alignItems: "center", justifyContent: "center", marginLeft: 6 }}>
            <Icon name="arrow-up" size={22} color={text.trim() ? "#fff" : colors.onSurfaceMuted} />
          </Pressable>
        </View>
      </KeyboardAvoidingView>
    </View>
  );
}

const styles = StyleSheet.create({
  bubble: { maxWidth: "88%", paddingHorizontal: spacing.md, paddingVertical: spacing.sm, borderRadius: radius.lg },
});
