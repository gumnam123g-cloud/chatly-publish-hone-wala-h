import { useState, useCallback } from "react";
import { View, ScrollView, Pressable, StyleSheet } from "react-native";
import { useRouter, useLocalSearchParams } from "expo-router";
import { useFocusEffect } from "expo-router";
import { useTheme, spacing, radius } from "@/src/theme";
import { AppText, Avatar, Icon, Button, Loading, useToast } from "@/src/ui";
import { StackHeader } from "@/src/Header";
import { api } from "@/src/api";
import { useAuth } from "@/src/auth";

export default function UserProfile() {
  const { colors } = useTheme();
  const router = useRouter();
  const toast = useToast();
  const { id } = useLocalSearchParams<{ id: string }>();
  const { user: me } = useAuth();
  const [u, setU] = useState<any>(null);
  const [loading, setLoading] = useState(true);
  const [busy, setBusy] = useState(false);

  const load = useCallback(async () => {
    try { const res = await api.get(`/users/${id}`); setU(res.user); }
    catch (e: any) { toast.show(e.message || "Could not load profile", "error"); }
    finally { setLoading(false); }
  }, [id]);
  useFocusEffect(useCallback(() => { load(); }, [load]));

  const rel = u?.relationship?.status;

  const openChat = async () => {
    try {
      const res = await api.post<{ chat_id: string }>("/chats", { contact_id: u.user_id });
      router.replace({ pathname: "/chat/[id]", params: { id: res.chat_id, name: u.name } });
    } catch { toast.show("Failed to open chat", "error"); }
  };

  const sendRequest = async () => {
    setBusy(true);
    try {
      const res = await api.post<{ status: string }>("/contacts/request", { to_id: u.user_id });
      if (res.status === "accepted" || res.status === "already_contacts") toast.show("Connected", "success");
      else toast.show("Request sent", "success");
      load();
    } catch (e: any) { toast.show(e.message, "error"); }
    finally { setBusy(false); }
  };

  const respond = async (accept: boolean) => {
    setBusy(true);
    try {
      await api.post("/contacts/respond", { request_id: u.relationship.request_id, accept });
      toast.show(accept ? "Connected" : "Declined", "success");
      load();
    } catch (e: any) { toast.show(e.message, "error"); }
    finally { setBusy(false); }
  };

  const toggleBlock = async () => {
    setBusy(true);
    try {
      const res = await api.post<{ blocked: boolean }>("/contacts/block", { user_id: u.user_id });
      toast.show(res.blocked ? "User blocked" : "User unblocked", "success");
      load();
    } catch { toast.show("Failed", "error"); }
    finally { setBusy(false); }
  };

  return (
    <View style={{ flex: 1, backgroundColor: colors.surface }}>
      <StackHeader title="Profile" />
      {loading ? <Loading /> : !u ? (
        <View style={{ padding: spacing.xl }}><AppText muted center>Profile unavailable.</AppText></View>
      ) : (
        <ScrollView contentContainerStyle={{ padding: spacing.xl, alignItems: "center" }}>
          <Avatar name={u.name} uri={u.avatar} size={110} online={u.online} />
          <AppText size="xxl" weight="heavy" style={{ marginTop: spacing.md }}>{u.name}</AppText>
          <AppText muted>@{u.username}</AppText>
          {u.bio ? <AppText center style={{ marginTop: spacing.sm, maxWidth: 300 }}>{u.bio}</AppText> : null}

          <View style={{ height: spacing.xl }} />

          {rel === "self" ? (
            <Button testID="edit-own-profile" title="Edit Profile" variant="secondary" onPress={() => router.replace("/(tabs)/profile")} />
          ) : rel === "friends" ? (
            <Button testID="message-user" title="Message" icon="chatbubble-outline" onPress={openChat} />
          ) : rel === "request_sent" ? (
            <Button testID="request-sent" title="Request Sent" variant="secondary" onPress={() => {}} disabled />
          ) : rel === "request_incoming" ? (
            <View style={{ flexDirection: "row", gap: spacing.md, alignSelf: "stretch" }}>
              <View style={{ flex: 1 }}><Button testID="accept-request" title="Accept" onPress={() => respond(true)} loading={busy} /></View>
              <View style={{ flex: 1 }}><Button testID="reject-request" title="Reject" variant="secondary" onPress={() => respond(false)} /></View>
            </View>
          ) : (
            <Button testID="add-friend" title="Add Friend" icon="person-add-outline" onPress={sendRequest} loading={busy} />
          )}

          {rel !== "self" && (
            <Pressable testID="block-user" onPress={toggleBlock} disabled={busy} style={{ marginTop: spacing.xl, flexDirection: "row", alignItems: "center" }}>
              <Icon name={u.blocked_by_me ? "lock-open-outline" : "ban-outline"} size={18} color={colors.error} />
              <AppText weight="bold" color={colors.error} style={{ marginLeft: 8 }}>{u.blocked_by_me ? "Unblock User" : "Block User"}</AppText>
            </Pressable>
          )}
        </ScrollView>
      )}
    </View>
  );
}

const styles = StyleSheet.create({});
