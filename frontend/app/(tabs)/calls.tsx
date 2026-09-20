import { useState, useCallback } from "react";
import { View, ScrollView, Pressable, StyleSheet, RefreshControl } from "react-native";
import { useRouter } from "expo-router";
import { useFocusEffect } from "expo-router";
import { useSafeAreaInsets } from "react-native-safe-area-context";
import { useTheme, spacing, radius } from "@/src/theme";
import { AppText, Avatar, Icon, EmptyState, Loading } from "@/src/ui";
import { api } from "@/src/api";
import { useCall } from "@/src/calls";
import dayjs from "dayjs";

export default function Calls() {
  const { colors } = useTheme();
  const insets = useSafeAreaInsets();
  const router = useRouter();
  const { startCall } = useCall();
  const [calls, setCalls] = useState<any[]>([]);
  const [loading, setLoading] = useState(true);
  const [refreshing, setRefreshing] = useState(false);

  const load = useCallback(async () => {
    try { const res = await api.get("/calls"); setCalls(res.calls); } catch {} finally { setLoading(false); setRefreshing(false); }
  }, []);
  useFocusEffect(useCallback(() => { load(); }, [load]));

  const meta = (c: any) => {
    const missed = c.status === "missed" || c.status === "rejected";
    const icon = c.direction === "incoming" ? "arrow-down-outline" : "arrow-up-outline";
    const color = missed ? colors.error : colors.onSurfaceMuted;
    const label = missed ? "Missed" : c.duration ? `${Math.max(1, Math.round(c.duration / 60))} min` : "Cancelled";
    return { icon, color, label };
  };

  return (
    <View style={{ flex: 1, backgroundColor: colors.surface }}>
      <View style={{ paddingTop: insets.top + spacing.sm, paddingHorizontal: spacing.lg, paddingBottom: spacing.sm }}>
        <AppText size="xxxl" weight="heavy">Calls</AppText>
      </View>
      {loading ? <Loading /> : calls.length === 0 ? (
        <EmptyState icon="call-outline" title="No calls yet" subtitle="Start a voice or video call from any chat. Chatly can summarize it afterwards." />
      ) : (
        <ScrollView contentContainerStyle={{ paddingHorizontal: spacing.lg, paddingBottom: spacing.xl }}
          refreshControl={<RefreshControl refreshing={refreshing} onRefresh={() => { setRefreshing(true); load(); }} tintColor={colors.brandPrimary} />}>
          {calls.map((c) => {
            const m = meta(c);
            return (
              <Pressable key={c.call_id} testID={`call-${c.call_id}`} onPress={() => c.has_transcript ? router.push({ pathname: "/call-intelligence/[id]", params: { id: c.call_id } }) : c.peer.user_id && startCall(c.chat_id, c.peer.name, c.type)} style={styles.row}>
                <Avatar name={c.peer?.name} uri={c.peer?.avatar} size={50} />
                <View style={{ flex: 1, marginLeft: spacing.md }}>
                  <AppText weight="semibold" size="lg" color={c.status === "missed" ? colors.error : colors.onSurface}>{c.peer?.name}</AppText>
                  <View style={{ flexDirection: "row", alignItems: "center", marginTop: 2 }}>
                    <Icon name={m.icon as any} size={13} color={m.color} />
                    <Icon name={c.type === "video" ? "videocam" : "call"} size={13} color={m.color} />
                    <AppText size="base" muted style={{ marginLeft: 6 }}>{m.label} · {dayjs(c.started_at).format("DD MMM, HH:mm")}</AppText>
                  </View>
                </View>
                {c.has_transcript && <View style={{ marginRight: spacing.md }}><Icon name="sparkles" size={18} color={colors.brandPrimary} /></View>}
                <Pressable testID={`callback-${c.call_id}`} onPress={() => c.peer.user_id && startCall(c.chat_id, c.peer.name, c.type)} hitSlop={8}>
                  <Icon name={c.type === "video" ? "videocam-outline" : "call-outline"} size={22} color={colors.brandPrimary} />
                </Pressable>
              </Pressable>
            );
          })}
        </ScrollView>
      )}
    </View>
  );
}

const styles = StyleSheet.create({
  row: { flexDirection: "row", alignItems: "center", paddingVertical: spacing.md },
});
