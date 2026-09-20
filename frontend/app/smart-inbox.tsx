import { useCallback, useState } from "react";
import { View, FlatList, Pressable, ScrollView, StyleSheet, RefreshControl } from "react-native";
import { useRouter } from "expo-router";
import { useFocusEffect } from "expo-router";
import { useSafeAreaInsets } from "react-native-safe-area-context";
import { useTheme, spacing, radius } from "@/src/theme";
import { AppText, Icon, EmptyState, Loading, useToast } from "@/src/ui";
import { api } from "@/src/api";
import dayjs from "dayjs";

const CATEGORIES: { key: "all" | "important" | "action_required" | "follow_up_required" | "normal" | "low"; label: string; icon: string; color?: string }[] = [
  { key: "all", label: "All", icon: "layers-outline" },
  { key: "important", label: "Important", icon: "flag" },
  { key: "action_required", label: "Action", icon: "flash" },
  { key: "follow_up_required", label: "Follow-up", icon: "return-up-forward" },
  { key: "normal", label: "Normal", icon: "chatbubble-ellipses-outline" },
  { key: "low", label: "Low", icon: "moon-outline" },
];

type Msg = {
  message_id: string; chat_id: string; sender_id: string; text: string;
  priority?: string; created_at: string; unread?: boolean;
};

export default function SmartInbox() {
  const { colors } = useTheme();
  const insets = useSafeAreaInsets();
  const router = useRouter();
  const toast = useToast();
  const [category, setCategory] = useState<typeof CATEGORIES[number]["key"]>("all");
  const [messages, setMessages] = useState<Msg[]>([]);
  const [loading, setLoading] = useState(true);
  const [refreshing, setRefreshing] = useState(false);

  const load = useCallback(async () => {
    try {
      const res = await api.get<{ messages: Msg[] }>(`/inbox/smart?category=${category}`);
      setMessages(res.messages || []);
    } catch (e: any) { toast.show(e?.message || "Couldn't load smart inbox", "error"); }
    finally { setLoading(false); setRefreshing(false); }
  }, [category, toast]);

  useFocusEffect(useCallback(() => { load(); }, [load]));

  const setPriority = async (m: Msg, priority: string) => {
    try {
      await api.patch(`/messages/${m.message_id}/priority`, { priority, source: "manual" });
      toast.show("Priority updated", "success");
      load();
    } catch (e: any) { toast.show(e?.message || "Failed", "error"); }
  };

  const renderRow = ({ item }: { item: Msg }) => (
    <Pressable onPress={() => router.push({ pathname: "/chat/[id]", params: { id: item.chat_id, name: "Chat" } })}
      style={[styles.row, { backgroundColor: colors.card, borderColor: colors.border }]}>
      <View style={{ flexDirection: "row", alignItems: "center" }}>
        <Icon name={item.priority === "important" ? "flag" : item.priority === "action_required" ? "flash" : item.priority === "follow_up_required" ? "return-up-forward" : "chatbubble"} size={18} color={item.priority === "important" ? colors.error : colors.brandPrimary} />
        <AppText size="sm" muted style={{ marginLeft: 8, flex: 1 }}>{dayjs(item.created_at).format("D MMM · HH:mm")}</AppText>
        {item.unread && <View style={{ width: 8, height: 8, borderRadius: 4, backgroundColor: colors.brandPrimary }} />}
      </View>
      <AppText size="md" style={{ marginTop: 6 }} numberOfLines={3}>{item.text}</AppText>
      <ScrollView horizontal showsHorizontalScrollIndicator={false} style={{ marginTop: spacing.sm }} contentContainerStyle={{ gap: 6 }}>
        {["important", "action_required", "follow_up_required", "normal", "low"].map((p) => (
          <Pressable key={p} onPress={() => setPriority(item, p)}
            style={{ paddingHorizontal: 10, paddingVertical: 6, borderRadius: radius.pill, borderWidth: 1,
              borderColor: item.priority === p ? colors.brandPrimary : colors.border,
              backgroundColor: item.priority === p ? colors.brandTertiary : "transparent" }}>
            <AppText size="xs" weight="semibold" style={{ textTransform: "capitalize" }}>{p.replace("_", " ")}</AppText>
          </Pressable>
        ))}
      </ScrollView>
    </Pressable>
  );

  return (
    <View style={{ flex: 1, backgroundColor: colors.surface }}>
      <View style={{ paddingTop: insets.top + 6, paddingBottom: spacing.sm, paddingHorizontal: spacing.md, flexDirection: "row", alignItems: "center", backgroundColor: colors.card, borderBottomWidth: 1, borderBottomColor: colors.border }}>
        <Pressable onPress={() => router.back()} hitSlop={10}><Icon name="chevron-back" size={26} /></Pressable>
        <AppText weight="heavy" size="xxl" style={{ marginLeft: spacing.sm, flex: 1 }}>Smart Inbox</AppText>
      </View>
      <ScrollView horizontal showsHorizontalScrollIndicator={false}
        contentContainerStyle={{ paddingHorizontal: spacing.md, gap: 8, paddingVertical: spacing.sm }}>
        {CATEGORIES.map((c) => (
          <Pressable key={c.key} onPress={() => setCategory(c.key)}
            style={{ paddingHorizontal: 12, paddingVertical: 8, borderRadius: radius.pill, borderWidth: 1,
              borderColor: category === c.key ? colors.brandPrimary : colors.border,
              backgroundColor: category === c.key ? colors.brandTertiary : "transparent",
              flexDirection: "row", alignItems: "center" }}>
            <Icon name={c.icon as any} size={14} color={category === c.key ? colors.brandPrimary : colors.onSurfaceMuted} />
            <AppText size="sm" weight="semibold" style={{ marginLeft: 6 }}>{c.label}</AppText>
          </Pressable>
        ))}
      </ScrollView>
      {loading ? <Loading /> : messages.length === 0 ? (
        <EmptyState icon="filter-outline" title="Nothing here yet" subtitle="Mark messages as important/action or let Autopilot suggest priorities." />
      ) : (
        <FlatList data={messages} keyExtractor={(m) => m.message_id} renderItem={renderRow}
          contentContainerStyle={{ padding: spacing.md, gap: spacing.md }}
          refreshControl={<RefreshControl refreshing={refreshing} onRefresh={() => { setRefreshing(true); load(); }} tintColor={colors.brandPrimary} />} />
      )}
    </View>
  );
}

const styles = StyleSheet.create({
  row: { borderWidth: 1, borderRadius: radius.md, padding: spacing.md },
});
