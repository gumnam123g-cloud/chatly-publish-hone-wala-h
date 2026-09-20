import { useState, useCallback } from "react";
import { View, ScrollView, Pressable, Modal, RefreshControl, ActivityIndicator, StyleSheet } from "react-native";
import { useRouter } from "expo-router";
import { useFocusEffect } from "expo-router";
import { useSafeAreaInsets } from "react-native-safe-area-context";
import { LinearGradient } from "expo-linear-gradient";
import { useTheme, spacing, radius } from "@/src/theme";
import { AppText, Avatar, Icon, EmptyState, useToast } from "@/src/ui";
import { api } from "@/src/api";
import { useAuth } from "@/src/auth";
import { pickStatusImage, pickStatusVideo, uploadStatusVideo } from "@/src/upload";

function ago(iso: string) {
  const s = Math.max(0, (Date.now() - new Date(iso).getTime()) / 1000);
  if (s < 60) return "just now";
  if (s < 3600) return `${Math.floor(s / 60)}m ago`;
  if (s < 86400) return `${Math.floor(s / 3600)}h ago`;
  return `${Math.floor(s / 86400)}d ago`;
}

export default function Status() {
  const { colors } = useTheme();
  const insets = useSafeAreaInsets();
  const router = useRouter();
  const toast = useToast();
  const { user } = useAuth();
  const [feed, setFeed] = useState<any>({ mine: [], others: [] });
  const [loading, setLoading] = useState(true);
  const [refreshing, setRefreshing] = useState(false);
  const [createOpen, setCreateOpen] = useState(false);
  const [uploading, setUploading] = useState(false);

  const load = useCallback(async () => {
    try { setFeed(await api.get("/status/feed")); } catch {}
    finally { setLoading(false); setRefreshing(false); }
  }, []);
  useFocusEffect(useCallback(() => { load(); }, [load]));

  const addPhoto = async () => {
    setCreateOpen(false);
    try {
      const dataUri = await pickStatusImage();
      if (!dataUri) return;
      setUploading(true);
      await api.post("/status", { kind: "image", media_b64: dataUri });
      toast.show("Status posted", "success");
      load();
    } catch (e: any) {
      if (String(e.message).includes("permission")) toast.show("Photo permission needed", "error");
      else toast.show(e.message || "Failed to post", "error");
    } finally { setUploading(false); }
  };

  const addVideo = async () => {
    setCreateOpen(false);
    try {
      const r = await pickStatusVideo();
      if (r.canceled || !r.assets?.[0]) return;
      setUploading(true);
      await uploadStatusVideo(r.assets[0]);
      toast.show("Status posted", "success");
      load();
    } catch (e: any) {
      if (String(e.message).includes("permission")) toast.show("Media permission needed", "error");
      else toast.show(e.message || "Failed to post", "error");
    } finally { setUploading(false); }
  };

  const mine = feed.mine || [];
  const others = feed.others || [];

  return (
    <View style={{ flex: 1, backgroundColor: colors.surface }}>
      <View style={{ paddingTop: insets.top + spacing.sm, paddingHorizontal: spacing.lg, paddingBottom: spacing.sm, flexDirection: "row", alignItems: "center", justifyContent: "space-between" }}>
        <AppText size="xxxl" weight="heavy">Status</AppText>
        <Pressable testID="create-status" onPress={() => setCreateOpen(true)} style={{ width: 40, height: 40, borderRadius: 20, backgroundColor: colors.brandTertiary, alignItems: "center", justifyContent: "center" }}>
          {uploading ? <ActivityIndicator size="small" color={colors.brandPrimary} /> : <Icon name="add" size={24} color={colors.brandPrimary} />}
        </Pressable>
      </View>

      <ScrollView
        contentContainerStyle={{ padding: spacing.lg }}
        refreshControl={<RefreshControl refreshing={refreshing} onRefresh={() => { setRefreshing(true); load(); }} tintColor={colors.brandPrimary} />}
      >
        {/* My status */}
        <Pressable
          testID="my-status-row"
          onPress={() => mine.length ? router.push({ pathname: "/status/[uid]", params: { uid: "me" } }) : setCreateOpen(true)}
          style={[styles.myRow, { borderColor: colors.border, backgroundColor: colors.card }]}
        >
          <View>
            {mine.length ? (
              <LinearGradient colors={[colors.brandPrimary, colors.brandSecondary]} style={{ padding: 2.5, borderRadius: 32 }}>
                <View style={{ borderRadius: 30, borderWidth: 2, borderColor: colors.card }}>
                  <Avatar name={user?.name} uri={user?.avatar} size={54} />
                </View>
              </LinearGradient>
            ) : (
              <>
                <Avatar name={user?.name} uri={user?.avatar} size={54} />
                <View style={{ position: "absolute", right: -2, bottom: -2, width: 22, height: 22, borderRadius: 11, backgroundColor: colors.brandPrimary, alignItems: "center", justifyContent: "center", borderWidth: 2, borderColor: colors.card }}>
                  <Icon name="add" size={14} color="#fff" />
                </View>
              </>
            )}
          </View>
          <View style={{ marginLeft: spacing.md, flex: 1 }}>
            <AppText weight="semibold" size="lg">My Status</AppText>
            <AppText muted size="base">{mine.length ? `${mine.length} update${mine.length > 1 ? "s" : ""} · ${ago(mine[mine.length - 1].created_at)}` : "Tap to add a status update"}</AppText>
          </View>
          <Pressable onPress={() => setCreateOpen(true)} hitSlop={12}><Icon name="camera-outline" size={22} color={colors.brandPrimary} /></Pressable>
        </Pressable>

        <AppText weight="bold" muted size="sm" style={{ marginTop: spacing.xl, marginBottom: spacing.md }}>RECENT UPDATES</AppText>
        {loading ? (
          <ActivityIndicator color={colors.brandPrimary} style={{ marginTop: spacing.xl }} />
        ) : others.length === 0 ? (
          <EmptyState icon="radio-outline" title="No recent updates" subtitle="Status updates from your contacts will appear here." />
        ) : (
          <View style={{ gap: spacing.xs }}>
            {others.map((g: any) => (
              <Pressable
                key={g.user.user_id}
                testID={`status-${g.user.user_id}`}
                onPress={() => router.push({ pathname: "/status/[uid]", params: { uid: g.user.user_id } })}
                style={[styles.statusRow, { backgroundColor: colors.card, borderColor: colors.border }]}
              >
                <LinearGradient colors={g.has_unseen ? [colors.brandPrimary, colors.brandSecondary] : [colors.border, colors.border]} style={{ padding: 2.5, borderRadius: 30 }}>
                  <View style={{ borderRadius: 28, borderWidth: 2, borderColor: colors.card }}>
                    <Avatar name={g.user.name} uri={g.user.avatar} size={48} />
                  </View>
                </LinearGradient>
                <View style={{ marginLeft: spacing.md, flex: 1 }}>
                  <AppText weight="semibold">{g.user.name}</AppText>
                  <AppText muted size="base">{g.statuses.length} update{g.statuses.length > 1 ? "s" : ""} · {ago(g.last_ts)}</AppText>
                </View>
              </Pressable>
            ))}
          </View>
        )}
      </ScrollView>

      {/* Create sheet */}
      <Modal visible={createOpen} transparent animationType="slide" onRequestClose={() => setCreateOpen(false)}>
        <Pressable style={{ flex: 1, backgroundColor: colors.overlay }} onPress={() => setCreateOpen(false)} />
        <View style={[styles.sheet, { backgroundColor: colors.card, paddingBottom: insets.bottom + spacing.lg }]}>
          <AppText weight="bold" size="lg" style={{ marginBottom: spacing.md }}>Create Status</AppText>
          <View style={{ flexDirection: "row", justifyContent: "space-around" }}>
            {[
              { key: "text", label: "Text", icon: "text", onPress: () => { setCreateOpen(false); router.push("/status/compose"); } },
              { key: "photo", label: "Photo", icon: "image", onPress: addPhoto },
              { key: "video", label: "Video", icon: "videocam", onPress: addVideo },
            ].map((o) => (
              <Pressable key={o.key} testID={`status-${o.key}`} onPress={o.onPress} style={{ alignItems: "center" }}>
                <View style={{ width: 64, height: 64, borderRadius: 20, backgroundColor: colors.brandTertiary, alignItems: "center", justifyContent: "center" }}>
                  <Icon name={o.icon as any} size={28} color={colors.brandPrimary} />
                </View>
                <AppText size="base" weight="semibold" style={{ marginTop: 8 }}>{o.label}</AppText>
              </Pressable>
            ))}
          </View>
        </View>
      </Modal>
    </View>
  );
}

const styles = StyleSheet.create({
  myRow: { flexDirection: "row", alignItems: "center", padding: spacing.md, borderRadius: radius.lg, borderWidth: 1 },
  statusRow: { flexDirection: "row", alignItems: "center", padding: spacing.sm, borderRadius: radius.lg, borderWidth: 1 },
  sheet: { position: "absolute", bottom: 0, left: 0, right: 0, borderTopLeftRadius: radius.xl, borderTopRightRadius: radius.xl, padding: spacing.lg },
});
