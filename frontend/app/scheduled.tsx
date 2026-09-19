/**
 * Scheduled Messages screen (features #9, #10).
 *
 * Lists user's scheduled messages, allows editing text/time, pause/resume,
 * cancel, and creating a new one. The New button opens a bottom sheet with a
 * chat picker, a plain multi-line input, an ISO datetime picker (native on
 * mobile) and a recurrence chooser (off / daily / weekly / custom N days).
 */
import React, { useEffect, useState, useCallback } from "react";
import { View, ScrollView, Pressable, StyleSheet, Modal, Platform, TextInput, RefreshControl } from "react-native";
import { Stack, router } from "expo-router";
import { SafeAreaView } from "react-native-safe-area-context";
import { useTheme, spacing, radius, fontSize } from "@/src/theme";
import { AppText, Button, Card, Icon, useToast } from "@/src/ui";
import { api } from "@/src/api";
import dayjs from "dayjs";

type Schedule = {
  id: string; chat_id: string; text: string; send_at: string;
  recurrence: string | null; interval_days: number | null;
  paused: boolean; status: string; last_error: string | null;
};

type Chat = { chat_id: string; other?: { name?: string; is_group?: boolean } | null };

export default function ScheduledScreen() {
  const { colors } = useTheme();
  const toast = useToast();
  const [items, setItems] = useState<Schedule[]>([]);
  const [chats, setChats] = useState<Chat[]>([]);
  const [tab, setTab] = useState<"active" | "past">("active");
  const [refreshing, setRefreshing] = useState(false);
  const [sheetOpen, setSheetOpen] = useState<Schedule | "new" | null>(null);

  const load = useCallback(async () => {
    setRefreshing(true);
    try {
      const [sched, chatsRes] = await Promise.all([
        api.get<{ items: Schedule[] }>(`/messages/schedule?status=${tab}`),
        api.get<{ chats: any[] }>("/chats"),
      ]);
      setItems(sched.items || []);
      setChats(chatsRes.chats || []);
    } catch (e: any) {
      toast.show(e?.message || "Couldn't load schedules.", "error");
    } finally { setRefreshing(false); }
  }, [tab]);

  useEffect(() => { load(); }, [load]);

  const chatName = (chatId: string) => {
    const c = chats.find((x) => x.chat_id === chatId);
    return c?.other?.name || (c?.other?.is_group ? "Group" : "Contact");
  };

  const cancel = async (s: Schedule) => {
    try {
      await api.del(`/messages/schedule/${s.id}`);
      toast.show("Cancelled", "success");
      load();
    } catch (e: any) { toast.show(e?.message || "Couldn't cancel.", "error"); }
  };
  const togglePause = async (s: Schedule) => {
    try {
      await api.patch(`/messages/schedule/${s.id}`, { paused: !s.paused });
      load();
    } catch (e: any) { toast.show(e?.message || "Couldn't update.", "error"); }
  };

  return (
    <SafeAreaView style={{ flex: 1, backgroundColor: colors.background }} edges={["top", "bottom"]}>
      <Stack.Screen options={{ headerShown: false }} />
      <View style={styles.header}>
        <Pressable testID="sched-back" onPress={() => router.back()} hitSlop={12} style={styles.iconBtn}>
          <Icon name="chevron-back" size={26} />
        </Pressable>
        <AppText size="xl" weight="bold" style={{ flex: 1, marginLeft: 8 }}>Scheduled</AppText>
        <Pressable testID="sched-new" onPress={() => setSheetOpen("new")} hitSlop={12} style={styles.iconBtn}>
          <Icon name="add" size={26} color={colors.brandPrimary} />
        </Pressable>
      </View>
      <View style={{ flexDirection: "row", marginHorizontal: spacing.lg, marginBottom: spacing.md, backgroundColor: colors.surfaceTertiary, borderRadius: radius.pill, padding: 4 }}>
        {(["active", "past"] as const).map((t) => (
          <Pressable key={t} testID={`sched-tab-${t}`} onPress={() => setTab(t)} style={{ flex: 1, paddingVertical: 10, borderRadius: radius.pill, backgroundColor: tab === t ? colors.brandPrimary : "transparent", alignItems: "center" }}>
            <AppText weight="semibold" color={tab === t ? "#fff" : colors.onSurface} style={{ textTransform: "capitalize" }}>{t}</AppText>
          </Pressable>
        ))}
      </View>
      <ScrollView
        refreshControl={<RefreshControl refreshing={refreshing} onRefresh={load} tintColor={colors.brandPrimary} />}
        contentContainerStyle={{ padding: spacing.lg, paddingBottom: 40 }}
      >
        {items.length === 0 ? (
          <View style={{ alignItems: "center", paddingVertical: spacing.xxl }}>
            <Icon name="time-outline" size={64} color={colors.onSurfaceMuted} />
            <AppText muted style={{ marginTop: spacing.md }}>
              {tab === "active" ? "No scheduled messages yet." : "No past scheduled messages."}
            </AppText>
          </View>
        ) : items.map((s) => (
          <Card key={s.id} style={{ marginBottom: spacing.md }}>
            <View style={{ flexDirection: "row", alignItems: "center", marginBottom: 6 }}>
              <Icon name="time-outline" size={18} color={colors.brandPrimary} />
              <AppText weight="semibold" style={{ marginLeft: 8, flex: 1 }} numberOfLines={1}>{chatName(s.chat_id)}</AppText>
              {s.recurrence ? (
                <View style={{ paddingHorizontal: 8, paddingVertical: 3, borderRadius: radius.pill, backgroundColor: colors.brandTertiary }}>
                  <AppText size="xs" color={colors.onBrandTertiary}>
                    {s.recurrence === "custom" ? `Every ${s.interval_days}d` : s.recurrence}
                  </AppText>
                </View>
              ) : null}
            </View>
            <AppText numberOfLines={3} style={{ marginBottom: 8 }}>{s.text}</AppText>
            <AppText size="sm" muted style={{ marginBottom: 8 }}>
              {tab === "past" && s.status === "sent" ? "Sent " : "Sends "}
              {dayjs(s.send_at).format("ddd, D MMM YYYY · h:mm A")}
              {s.paused ? "  •  Paused" : ""}
              {s.status === "failed" ? `  •  Failed: ${s.last_error || ""}` : ""}
            </AppText>
            {tab === "active" ? (
              <View style={{ flexDirection: "row", gap: 8 }}>
                <Pressable testID={`sched-edit-${s.id}`} onPress={() => setSheetOpen(s)} style={{ flex: 1, backgroundColor: colors.surfaceTertiary, borderRadius: radius.md, paddingVertical: 10, alignItems: "center" }}>
                  <AppText weight="semibold">Edit</AppText>
                </Pressable>
                <Pressable testID={`sched-pause-${s.id}`} onPress={() => togglePause(s)} style={{ flex: 1, backgroundColor: colors.surfaceTertiary, borderRadius: radius.md, paddingVertical: 10, alignItems: "center" }}>
                  <AppText weight="semibold">{s.paused ? "Resume" : "Pause"}</AppText>
                </Pressable>
                <Pressable testID={`sched-cancel-${s.id}`} onPress={() => cancel(s)} style={{ flex: 1, backgroundColor: colors.surfaceTertiary, borderRadius: radius.md, paddingVertical: 10, alignItems: "center" }}>
                  <AppText weight="semibold" color={colors.error}>Cancel</AppText>
                </Pressable>
              </View>
            ) : null}
          </Card>
        ))}
      </ScrollView>

      {sheetOpen ? (
        <SheetEditor
          value={sheetOpen === "new" ? null : sheetOpen}
          chats={chats}
          onClose={() => setSheetOpen(null)}
          onSaved={() => { setSheetOpen(null); load(); }}
        />
      ) : null}
    </SafeAreaView>
  );
}

function SheetEditor({ value, chats, onClose, onSaved }: {
  value: Schedule | null; chats: Chat[]; onClose: () => void; onSaved: () => void;
}) {
  const { colors } = useTheme();
  const toast = useToast();
  const [text, setText] = useState(value?.text || "");
  const [chatId, setChatId] = useState(value?.chat_id || chats[0]?.chat_id || "");
  const [when, setWhen] = useState(value?.send_at || dayjs().add(1, "hour").toISOString());
  const [rec, setRec] = useState<string>(value?.recurrence || "off");
  const [interval, setInterval] = useState<number>(value?.interval_days || 3);
  const [saving, setSaving] = useState(false);

  const setInMinutes = (min: number) => setWhen(dayjs().add(min, "minute").toISOString());
  const setTomorrowAt = (hour: number) => setWhen(dayjs().add(1, "day").hour(hour).minute(0).second(0).toISOString());

  const save = async () => {
    if (!text.trim()) { toast.show("Please type a message.", "error"); return; }
    if (!chatId) { toast.show("Pick a chat.", "error"); return; }
    if (dayjs(when).valueOf() <= Date.now() - 30_000) { toast.show("Pick a future time.", "error"); return; }
    setSaving(true);
    try {
      if (value) {
        const upd: any = { text: text.trim(), send_at: when };
        upd.recurrence = rec;
        if (rec === "custom") upd.interval_days = Number(interval) || 1;
        await api.patch(`/messages/schedule/${value.id}`, upd);
      } else {
        const payload: any = { chat_id: chatId, text: text.trim(), send_at: when };
        if (rec !== "off") { payload.recurrence = rec; if (rec === "custom") payload.interval_days = Number(interval) || 1; }
        await api.post("/messages/schedule", payload);
      }
      toast.show(value ? "Updated" : "Scheduled", "success");
      onSaved();
    } catch (e: any) { toast.show(e?.message || "Couldn't save.", "error"); }
    finally { setSaving(false); }
  };

  return (
    <Modal visible transparent animationType="slide" onRequestClose={onClose}>
      <Pressable style={{ flex: 1, backgroundColor: colors.overlay }} onPress={onClose} />
      <View style={{ backgroundColor: colors.card, padding: spacing.lg, borderTopLeftRadius: radius.xl, borderTopRightRadius: radius.xl, paddingBottom: 32 }}>
        <AppText size="lg" weight="bold" style={{ marginBottom: spacing.md }}>{value ? "Edit schedule" : "New scheduled message"}</AppText>
        {!value ? (
          <>
            <AppText size="sm" muted style={{ marginBottom: 6 }}>Chat</AppText>
            <ScrollView horizontal showsHorizontalScrollIndicator={false} style={{ marginBottom: spacing.md }} contentContainerStyle={{ gap: 8 }}>
              {chats.map((c) => (
                <Pressable key={c.chat_id} onPress={() => setChatId(c.chat_id)} style={{ paddingHorizontal: 12, paddingVertical: 8, borderRadius: radius.pill, borderWidth: 1, borderColor: chatId === c.chat_id ? colors.brandPrimary : colors.border, backgroundColor: chatId === c.chat_id ? colors.brandTertiary : "transparent" }}>
                  <AppText size="sm" weight="semibold" color={chatId === c.chat_id ? colors.onBrandTertiary : colors.onSurface}>{c.other?.name || "Chat"}</AppText>
                </Pressable>
              ))}
            </ScrollView>
          </>
        ) : null}
        <AppText size="sm" muted style={{ marginBottom: 6 }}>Message</AppText>
        <TextInput
          testID="sched-text"
          value={text} onChangeText={setText} multiline
          placeholder="What should Chatly send?"
          placeholderTextColor={colors.onSurfaceMuted}
          style={{ minHeight: 90, backgroundColor: colors.surfaceTertiary, borderRadius: radius.md, padding: 12, color: colors.onSurface, fontSize: fontSize.base, textAlignVertical: "top", marginBottom: spacing.md }}
        />
        <AppText size="sm" muted style={{ marginBottom: 6 }}>When — {dayjs(when).format("ddd, D MMM · h:mm A")}</AppText>
        <ScrollView horizontal showsHorizontalScrollIndicator={false} style={{ marginBottom: spacing.md }} contentContainerStyle={{ gap: 8 }}>
          {[["+15 min", () => setInMinutes(15)], ["+1 hour", () => setInMinutes(60)], ["Tomorrow 9am", () => setTomorrowAt(9)], ["Tomorrow 6pm", () => setTomorrowAt(18)]].map(([label, fn]: any) => (
            <Pressable key={label} onPress={fn} style={{ paddingHorizontal: 12, paddingVertical: 8, borderRadius: radius.pill, backgroundColor: colors.surfaceTertiary }}>
              <AppText size="sm" weight="semibold">{label}</AppText>
            </Pressable>
          ))}
        </ScrollView>
        <AppText size="sm" muted style={{ marginBottom: 6 }}>Repeat</AppText>
        <ScrollView horizontal showsHorizontalScrollIndicator={false} style={{ marginBottom: spacing.md }} contentContainerStyle={{ gap: 8 }}>
          {["off", "daily", "weekly", "custom"].map((r) => (
            <Pressable key={r} onPress={() => setRec(r)} style={{ paddingHorizontal: 12, paddingVertical: 8, borderRadius: radius.pill, borderWidth: 1, borderColor: rec === r ? colors.brandPrimary : colors.border, backgroundColor: rec === r ? colors.brandTertiary : "transparent" }}>
              <AppText size="sm" weight="semibold" color={rec === r ? colors.onBrandTertiary : colors.onSurface} style={{ textTransform: "capitalize" }}>{r}</AppText>
            </Pressable>
          ))}
        </ScrollView>
        {rec === "custom" ? (
          <View style={{ flexDirection: "row", alignItems: "center", marginBottom: spacing.md }}>
            <AppText style={{ marginRight: 8 }}>Every</AppText>
            <TextInput
              testID="sched-interval"
              value={String(interval)} onChangeText={(t) => setInterval(Number(t.replace(/[^0-9]/g, "") || 1))} keyboardType="number-pad"
              style={{ backgroundColor: colors.surfaceTertiary, borderRadius: radius.md, paddingHorizontal: 12, paddingVertical: 8, minWidth: 60, textAlign: "center", color: colors.onSurface, fontSize: fontSize.base }}
            />
            <AppText style={{ marginLeft: 8 }}>days</AppText>
          </View>
        ) : null}
        <Button testID="sched-save" title={value ? "Save changes" : "Schedule"} onPress={save} loading={saving} />
      </View>
    </Modal>
  );
}

const styles = StyleSheet.create({
  header: { flexDirection: "row", alignItems: "center", paddingHorizontal: spacing.md, height: 56 },
  iconBtn: { width: 40, height: 40, alignItems: "center", justifyContent: "center" },
});
