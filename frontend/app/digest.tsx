import { useCallback, useState } from "react";
import { View, ScrollView, Pressable, StyleSheet } from "react-native";
import { useRouter } from "expo-router";
import { useSafeAreaInsets } from "react-native-safe-area-context";
import { useTheme, spacing, radius } from "@/src/theme";
import { AppText, Icon, EmptyState, Loading, useToast } from "@/src/ui";
import { api } from "@/src/api";

export default function DigestScreen() {
  const { colors } = useTheme();
  const insets = useSafeAreaInsets();
  const router = useRouter();
  const toast = useToast();
  const [period, setPeriod] = useState<"daily" | "weekly">("daily");
  const [data, setData] = useState<any | null>(null);
  const [loading, setLoading] = useState(false);

  const load = useCallback(async (p: "daily" | "weekly") => {
    setLoading(true); setData(null);
    try {
      const r = await api.post<any>("/ai/digest", { period: p });
      setData(r);
    } catch (e: any) { toast.show(e?.message || "Failed", "error"); }
    finally { setLoading(false); }
  }, [toast]);

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

  const digest = data?.digest || {};

  return (
    <View style={{ flex: 1, backgroundColor: colors.surface }}>
      <View style={{ paddingTop: insets.top + 6, paddingBottom: spacing.sm, paddingHorizontal: spacing.md, flexDirection: "row", alignItems: "center", backgroundColor: colors.card, borderBottomWidth: 1, borderBottomColor: colors.border }}>
        <Pressable onPress={() => router.back()} hitSlop={10}><Icon name="chevron-back" size={26} /></Pressable>
        <AppText weight="heavy" size="xxl" style={{ marginLeft: spacing.sm, flex: 1 }}>Chat Digest</AppText>
      </View>
      <View style={{ flexDirection: "row", padding: spacing.md, gap: spacing.sm }}>
        {(["daily", "weekly"] as const).map((p) => (
          <Pressable key={p} onPress={() => { setPeriod(p); load(p); }}
            style={{ flex: 1, paddingVertical: 10, borderRadius: radius.md, borderWidth: 1,
              borderColor: period === p ? colors.brandPrimary : colors.border,
              backgroundColor: period === p ? colors.brandTertiary : "transparent", alignItems: "center" }}>
            <AppText weight="semibold" style={{ textTransform: "capitalize" }}>{p}</AppText>
          </Pressable>
        ))}
      </View>
      <ScrollView contentContainerStyle={{ paddingHorizontal: spacing.md, paddingBottom: spacing.xxl }}>
        {loading ? <Loading /> : !data ? (
          <EmptyState icon="newspaper-outline" title="Generate a digest" subtitle="Tap Daily or Weekly to summarize your activity." />
        ) : (
          <>
            <View style={{ backgroundColor: colors.card, borderColor: colors.border, borderWidth: 1, borderRadius: radius.md, padding: spacing.md }}>
              <AppText muted size="sm">{data.message_count} messages · {period}</AppText>
            </View>
            <Section title="Important conversations" items={digest.important_conversations} icon="chatbubbles" />
            <Section title="Pending replies" items={digest.pending_replies} icon="arrow-undo" />
            <Section title="Tasks" items={digest.tasks} icon="checkbox" />
            <Section title="Decisions" items={digest.decisions} icon="checkmark-done" />
            <Section title="Follow-ups" items={digest.follow_ups} icon="return-up-forward" />
          </>
        )}
      </ScrollView>
    </View>
  );
}

const styles = StyleSheet.create({});
