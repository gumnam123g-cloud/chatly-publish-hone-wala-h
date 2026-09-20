import { useState, useCallback } from "react";
import { View, ScrollView, Pressable } from "react-native";
import { useRouter } from "expo-router";
import { useFocusEffect } from "expo-router";
import { useTheme, spacing, radius } from "@/src/theme";
import { AppText, Avatar, Icon, Loading, EmptyState, useToast } from "@/src/ui";
import { StackHeader } from "@/src/Header";
import { api } from "@/src/api";
import { useWs } from "@/src/ws";

export default function Requests() {
  const { colors } = useTheme();
  const router = useRouter();
  const toast = useToast();
  const { subscribe } = useWs();
  const [requests, setRequests] = useState<any[]>([]);
  const [loading, setLoading] = useState(true);

  const load = useCallback(async () => {
    try { const r = await api.get("/contacts/requests"); setRequests(r.requests); }
    catch {} finally { setLoading(false); }
  }, []);
  useFocusEffect(useCallback(() => { load(); }, [load]));
  useFocusEffect(useCallback(() => subscribe((ev: any) => {
    if (ev.type === "contact_request" || ev.type === "contact_accepted") load();
  }), [subscribe, load]));

  const respond = async (r: any, accept: boolean) => {
    setRequests((p) => p.filter((x) => x.request_id !== r.request_id));
    try { await api.post("/contacts/respond", { request_id: r.request_id, accept }); toast.show(accept ? "Connected" : "Declined", "success"); }
    catch { toast.show("Failed", "error"); load(); }
  };

  return (
    <View style={{ flex: 1, backgroundColor: colors.surface }}>
      <StackHeader title="Friend Requests" />
      {loading ? <Loading /> : (
        <ScrollView contentContainerStyle={{ padding: spacing.lg }}>
          {requests.length === 0 ? (
            <View style={{ marginTop: spacing.xxxl }}>
              <EmptyState icon="person-add-outline" title="No friend requests" subtitle="When someone adds you, their request shows up here." />
            </View>
          ) : requests.map((r) => (
            <View key={r.request_id} style={{ flexDirection: "row", alignItems: "center", paddingVertical: spacing.md }}>
              <Pressable onPress={() => router.push({ pathname: "/user/[id]", params: { id: r.user_id } })}>
                <Avatar name={r.name} uri={r.avatar} size={52} online={r.online} />
              </Pressable>
              <View style={{ flex: 1, marginLeft: spacing.md }}>
                <AppText weight="semibold" size="lg" numberOfLines={1}>{r.name}</AppText>
                <AppText muted size="base" numberOfLines={1}>@{r.username}</AppText>
              </View>
              <View style={{ flexDirection: "row", gap: spacing.sm }}>
                <Pressable testID={`accept-${r.request_id}`} onPress={() => respond(r, true)} style={{ paddingHorizontal: spacing.md, height: 38, borderRadius: radius.pill, backgroundColor: colors.brandPrimary, alignItems: "center", justifyContent: "center" }}>
                  <AppText weight="bold" color="#fff">Accept</AppText>
                </Pressable>
                <Pressable testID={`reject-${r.request_id}`} onPress={() => respond(r, false)} style={{ width: 38, height: 38, borderRadius: 19, backgroundColor: colors.surfaceTertiary, alignItems: "center", justifyContent: "center" }}>
                  <Icon name="close" size={18} />
                </Pressable>
              </View>
            </View>
          ))}
        </ScrollView>
      )}
    </View>
  );
}
