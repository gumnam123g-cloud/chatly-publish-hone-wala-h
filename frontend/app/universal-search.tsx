/**
 * Universal Search (feature #44). Debounced query hits /search/universal and
 * groups results by kind (chats, messages, tasks, reminders, files).
 */
import React, { useCallback, useEffect, useRef, useState } from "react";
import { View, ScrollView, Pressable, StyleSheet, TextInput, ActivityIndicator } from "react-native";
import { Stack, router } from "expo-router";
import { SafeAreaView } from "react-native-safe-area-context";
import { useTheme, spacing, radius, fontSize } from "@/src/theme";
import { AppText, Card, Icon, useToast } from "@/src/ui";
import { api } from "@/src/api";
import dayjs from "dayjs";

interface Res { chats: any[]; messages: any[]; tasks: any[]; reminders: any[]; files: any[] }

export default function UniversalSearchScreen() {
  const { colors } = useTheme();
  const toast = useToast();
  const [q, setQ] = useState("");
  const [res, setRes] = useState<Res | null>(null);
  const [loading, setLoading] = useState(false);
  const timer = useRef<ReturnType<typeof setTimeout> | null>(null);

  const run = useCallback(async (query: string) => {
    if (!query.trim()) { setRes(null); return; }
    setLoading(true);
    try {
      const r = await api.get<Res>(`/search/universal?q=${encodeURIComponent(query.trim())}`);
      setRes(r);
    } catch (e: any) { toast.show(e?.message || "Search failed.", "error"); setRes(null); }
    finally { setLoading(false); }
  }, []);

  useEffect(() => {
    if (timer.current) clearTimeout(timer.current);
    timer.current = setTimeout(() => run(q), 350);
    return () => { if (timer.current) clearTimeout(timer.current); };
  }, [q, run]);

  const openChat = (chatId: string) => router.push({ pathname: "/chat/[id]", params: { id: chatId } });

  return (
    <SafeAreaView style={{ flex: 1, backgroundColor: colors.background }} edges={["top", "bottom"]}>
      <Stack.Screen options={{ headerShown: false }} />
      <View style={styles.header}>
        <Pressable testID="search-back" onPress={() => router.back()} hitSlop={12} style={styles.iconBtn}>
          <Icon name="chevron-back" size={26} />
        </Pressable>
        <View style={{ flex: 1, flexDirection: "row", alignItems: "center", backgroundColor: colors.surfaceTertiary, borderRadius: radius.pill, paddingHorizontal: 12, height: 40, marginLeft: 4 }}>
          <Icon name="search" size={18} color={colors.onSurfaceMuted} />
          <TextInput testID="universal-search-input" autoFocus value={q} onChangeText={setQ} placeholder="Search chats, messages, tasks, files" placeholderTextColor={colors.onSurfaceMuted}
            style={{ flex: 1, marginLeft: 8, color: colors.onSurface, fontSize: fontSize.base }} />
          {q ? <Pressable onPress={() => setQ("")}><Icon name="close" size={18} color={colors.onSurfaceMuted} /></Pressable> : null}
        </View>
      </View>
      <ScrollView contentContainerStyle={{ padding: spacing.lg, paddingBottom: 40 }}>
        {loading ? <ActivityIndicator color={colors.brandPrimary} style={{ marginTop: spacing.xl }} /> : null}
        {res ? (
          <>
            {res.chats.length ? <Section title="Chats">
              {res.chats.map((c: any) => (
                <Pressable key={c.chat_id} onPress={() => openChat(c.chat_id)} style={{ paddingVertical: 10 }}>
                  <AppText weight="semibold">{c.name || c.title || "Chat"}</AppText>
                  {c.last_message ? <AppText muted numberOfLines={1}>{c.last_message}</AppText> : null}
                </Pressable>
              ))}
            </Section> : null}
            {res.messages.length ? <Section title={`Messages (${res.messages.length})`}>
              {res.messages.map((m: any) => (
                <Pressable key={m.message_id} onPress={() => openChat(m.chat_id)} style={{ paddingVertical: 10 }}>
                  <AppText numberOfLines={2}>{m.text}</AppText>
                  <AppText size="xs" muted style={{ marginTop: 2 }}>{dayjs(m.created_at).format("D MMM · h:mm A")}</AppText>
                </Pressable>
              ))}
            </Section> : null}
            {res.tasks.length ? <Section title={`Tasks (${res.tasks.length})`}>
              {res.tasks.map((t: any, i: number) => (
                <Pressable key={i} onPress={() => router.push("/tasks")} style={{ paddingVertical: 10 }}>
                  <AppText weight="semibold">{t.title}</AppText>
                  {t.notes ? <AppText muted numberOfLines={1}>{t.notes}</AppText> : null}
                </Pressable>
              ))}
            </Section> : null}
            {res.reminders.length ? <Section title={`Reminders (${res.reminders.length})`}>
              {res.reminders.map((r: any, i: number) => (
                <Pressable key={i} onPress={() => router.push("/reminders")} style={{ paddingVertical: 10 }}>
                  <AppText>{r.text}</AppText>
                  {r.remind_at ? <AppText size="xs" muted>{dayjs(r.remind_at).format("D MMM · h:mm A")}</AppText> : null}
                </Pressable>
              ))}
            </Section> : null}
            {res.files.length ? <Section title={`Files (${res.files.length})`}>
              {res.files.map((m: any) => (
                <Pressable key={m.message_id} onPress={() => openChat(m.chat_id)} style={{ paddingVertical: 10, flexDirection: "row", alignItems: "center" }}>
                  <Icon name="document-outline" size={20} color={colors.brandPrimary} />
                  <View style={{ flex: 1, marginLeft: 10 }}>
                    <AppText weight="semibold" numberOfLines={1}>{m.attachment?.filename || "File"}</AppText>
                    <AppText size="xs" muted>{dayjs(m.created_at).format("D MMM · h:mm A")}</AppText>
                  </View>
                </Pressable>
              ))}
            </Section> : null}
            {(!res.chats.length && !res.messages.length && !res.tasks.length && !res.reminders.length && !res.files.length) ? (
              <View style={{ alignItems: "center", paddingVertical: spacing.xxl }}>
                <Icon name="search-outline" size={64} color={colors.onSurfaceMuted} />
                <AppText muted style={{ marginTop: spacing.md }}>No results for “{q}”.</AppText>
              </View>
            ) : null}
          </>
        ) : q ? null : (
          <View style={{ alignItems: "center", paddingVertical: spacing.xxl }}>
            <Icon name="search-outline" size={64} color={colors.onSurfaceMuted} />
            <AppText muted style={{ marginTop: spacing.md }}>Search across chats, messages, tasks, reminders, files.</AppText>
          </View>
        )}
      </ScrollView>
    </SafeAreaView>
  );
}

function Section({ title, children }: { title: string; children: React.ReactNode }) {
  return (
    <Card style={{ marginBottom: spacing.md }}>
      <AppText size="sm" weight="bold" muted style={{ marginBottom: 6, textTransform: "uppercase", letterSpacing: 0.5 }}>{title}</AppText>
      {children}
    </Card>
  );
}

const styles = StyleSheet.create({
  header: { flexDirection: "row", alignItems: "center", paddingHorizontal: spacing.md, height: 56 },
  iconBtn: { width: 40, height: 40, alignItems: "center", justifyContent: "center" },
});
