import { useState, useCallback } from "react";
import { View, ScrollView, Pressable } from "react-native";
import { useRouter } from "expo-router";
import { useFocusEffect } from "expo-router";
import { useTheme, spacing, radius } from "@/src/theme";
import { AppText, Icon, Card, EmptyState, Loading } from "@/src/ui";
import { StackHeader } from "@/src/Header";
import { api } from "@/src/api";
import dayjs from "dayjs";

export default function Important() {
  const { colors } = useTheme();
  const router = useRouter();
  const [items, setItems] = useState<any[]>([]);
  const [loading, setLoading] = useState(true);

  const load = useCallback(async () => {
    try { const res = await api.get("/important"); setItems(res.important); } catch {} finally { setLoading(false); }
  }, []);
  useFocusEffect(useCallback(() => { load(); }, [load]));

  return (
    <View style={{ flex: 1, backgroundColor: colors.surface }}>
      <StackHeader title="Important Messages" />
      {loading ? <Loading /> : items.length === 0 ? (
        <EmptyState icon="flag-outline" title="Nothing marked important" subtitle="Long-press any message and tap 'Mark Important' to keep it here." />
      ) : (
        <ScrollView contentContainerStyle={{ padding: spacing.lg, gap: spacing.sm }}>
          {items.map((m) => (
            <Card key={m.id} testID={`important-${m.id}`} onPress={() => router.push({ pathname: "/chat/[id]", params: { id: m.chat_id, name: m.sender_name || "Chat" } })} style={{ padding: spacing.md }}>
              <View style={{ flexDirection: "row", alignItems: "center", marginBottom: 4 }}>
                <View style={{ paddingHorizontal: 8, paddingVertical: 2, borderRadius: radius.pill, backgroundColor: (m.level === "urgent" ? colors.error : colors.warning) + "22" }}>
                  <AppText size="xs" weight="bold" color={m.level === "urgent" ? colors.error : colors.warning}>{m.level?.toUpperCase()}</AppText>
                </View>
                <AppText size="sm" muted style={{ marginLeft: spacing.sm, flex: 1 }}>{m.sender_name}</AppText>
                <AppText size="xs" muted>{dayjs(m.created_at).format("DD MMM")}</AppText>
              </View>
              <AppText numberOfLines={3}>{m.text}</AppText>
            </Card>
          ))}
        </ScrollView>
      )}
    </View>
  );
}
