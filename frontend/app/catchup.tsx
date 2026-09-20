import { useCallback, useState } from "react";
import { View, ScrollView, Pressable, StyleSheet, RefreshControl } from "react-native";
import { useRouter } from "expo-router";
import { useFocusEffect } from "expo-router";
import { useSafeAreaInsets } from "react-native-safe-area-context";
import { useTheme, spacing, radius } from "@/src/theme";
import { AppText, Icon, EmptyState, Loading, useToast } from "@/src/ui";
import { api } from "@/src/api";

type Catchup = {
  summary?: string;
  important_points?: string[];
  questions?: string[];
  action_items?: string[];
  items: any[];
  count: number;
};

export default function CatchUp() {
  const { colors } = useTheme();
  const insets = useSafeAreaInsets();
  const router = useRouter();
  const toast = useToast();
  const [data, setData] = useState<Catchup | null>(null);
  const [loading, setLoading] = useState(true);
  const [refreshing, setRefreshing] = useState(false);

  const load = useCallback(async () => {
    try {
      const r = await api.get<Catchup>("/ai/unread-catchup");
      setData(r);
    } catch (e: any) { toast.show(e?.message || "Failed", "error"); }
    finally { setLoading(false); setRefreshing(false); }
  }, [toast]);
  useFocusEffect(useCallback(() => { load(); }, [load]));

  const Section = ({ title, items, icon }: { title: string; items?: string[]; icon: string }) => {
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
            <AppText style={{ flex: 1 }}>{t}</AppText>
          </View>
        ))}
      </View>
    );
  };

  return (
    <View style={{ flex: 1, backgroundColor: colors.surface }}>
      <View style={{ paddingTop: insets.top + 6, paddingBottom: spacing.sm, paddingHorizontal: spacing.md, flexDirection: "row", alignItems: "center", backgroundColor: colors.card, borderBottomWidth: 1, borderBottomColor: colors.border }}>
        <Pressable onPress={() => router.back()} hitSlop={10}><Icon name="chevron-back" size={26} /></Pressable>
        <AppText weight="heavy" size="xxl" style={{ marginLeft: spacing.sm, flex: 1 }}>Catch Up</AppText>
      </View>
      {loading ? <Loading /> : !data || data.count === 0 ? (
        <EmptyState icon="checkmark-done-outline" title="You're all caught up" subtitle="No unread messages." />
      ) : (
        <ScrollView contentContainerStyle={{ padding: spacing.md, paddingBottom: spacing.xxl }}
          refreshControl={<RefreshControl refreshing={refreshing} onRefresh={() => { setRefreshing(true); load(); }} tintColor={colors.brandPrimary} />}>
          <View style={{ backgroundColor: colors.card, borderColor: colors.border, borderWidth: 1, borderRadius: radius.md, padding: spacing.md }}>
            <View style={{ flexDirection: "row", alignItems: "center" }}>
              <Icon name="sparkles" size={18} color={colors.brandPrimary} />
              <AppText weight="bold" size="lg" style={{ marginLeft: 8 }}>Summary</AppText>
            </View>
            <AppText style={{ marginTop: 6 }}>{data.summary || `You have ${data.count} unread messages.`}</AppText>
          </View>
          <Section title="Important" items={data.important_points} icon="flag" />
          <Section title="Action items" items={data.action_items} icon="flash" />
          <Section title="Open questions" items={data.questions} icon="help-circle" />
        </ScrollView>
      )}
    </View>
  );
}

const styles = StyleSheet.create({});
