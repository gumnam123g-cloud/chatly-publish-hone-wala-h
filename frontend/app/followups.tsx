import { useCallback, useState } from "react";
import { View, FlatList, Pressable, StyleSheet, RefreshControl } from "react-native";
import { useRouter } from "expo-router";
import { useFocusEffect } from "expo-router";
import { useSafeAreaInsets } from "react-native-safe-area-context";
import { useTheme, spacing, radius } from "@/src/theme";
import { AppText, Icon, EmptyState, Loading, useToast } from "@/src/ui";
import { api } from "@/src/api";
import dayjs from "dayjs";

type Followup = { id: string; title: string; created_at: string; remind_at?: string; source_message_id?: string; done?: boolean };

export default function FollowUps() {
  const { colors } = useTheme();
  const insets = useSafeAreaInsets();
  const router = useRouter();
  const toast = useToast();
  const [items, setItems] = useState<Followup[]>([]);
  const [loading, setLoading] = useState(true);
  const [refreshing, setRefreshing] = useState(false);

  const load = useCallback(async () => {
    try {
      const r = await api.get<{ items: Followup[] }>("/follow-ups");
      setItems(r.items || []);
    } catch (e: any) { toast.show(e?.message || "Failed", "error"); }
    finally { setLoading(false); setRefreshing(false); }
  }, [toast]);
  useFocusEffect(useCallback(() => { load(); }, [load]));

  const markDone = async (r: Followup) => {
    try {
      await api.put(`/reminders/${r.id}/done`);
      setItems((p) => p.filter((x) => x.id !== r.id));
    } catch (e: any) { toast.show(e?.message || "Failed", "error"); }
  };

  const renderRow = ({ item }: { item: Followup }) => (
    <View style={[styles.row, { backgroundColor: colors.card, borderColor: colors.border }]}>
      <View style={{ flex: 1 }}>
        <AppText weight="semibold" numberOfLines={2}>{item.title}</AppText>
        <AppText size="xs" muted style={{ marginTop: 4 }}>{item.remind_at ? `Remind ${dayjs(item.remind_at).format("D MMM · HH:mm")}` : dayjs(item.created_at).fromNow?.() || dayjs(item.created_at).format("D MMM")}</AppText>
      </View>
      <Pressable onPress={() => markDone(item)} style={{ paddingHorizontal: 12, paddingVertical: 8, borderRadius: radius.pill, backgroundColor: colors.brandTertiary }}>
        <AppText size="sm" weight="bold" color={colors.brandPrimary}>Done</AppText>
      </Pressable>
    </View>
  );

  return (
    <View style={{ flex: 1, backgroundColor: colors.surface }}>
      <View style={{ paddingTop: insets.top + 6, paddingBottom: spacing.sm, paddingHorizontal: spacing.md, flexDirection: "row", alignItems: "center", backgroundColor: colors.card, borderBottomWidth: 1, borderBottomColor: colors.border }}>
        <Pressable onPress={() => router.back()} hitSlop={10}><Icon name="chevron-back" size={26} /></Pressable>
        <AppText weight="heavy" size="xxl" style={{ marginLeft: spacing.sm, flex: 1 }}>Follow-ups</AppText>
      </View>
      {loading ? <Loading /> : items.length === 0 ? (
        <EmptyState icon="return-up-forward-outline" title="No follow-ups" subtitle="Autopilot creates follow-ups when you confirm them from chats." />
      ) : (
        <FlatList data={items} keyExtractor={(i) => i.id} renderItem={renderRow}
          contentContainerStyle={{ padding: spacing.md, gap: spacing.sm }}
          refreshControl={<RefreshControl refreshing={refreshing} onRefresh={() => { setRefreshing(true); load(); }} tintColor={colors.brandPrimary} />} />
      )}
    </View>
  );
}

const styles = StyleSheet.create({
  row: { borderWidth: 1, borderRadius: radius.md, padding: spacing.md, flexDirection: "row", alignItems: "center" },
});
