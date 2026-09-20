import { useState, useCallback } from "react";
import { View, ScrollView, Pressable, Modal, StyleSheet } from "react-native";
import { useRouter, useLocalSearchParams } from "expo-router";
import { useFocusEffect } from "expo-router";
import { useSafeAreaInsets } from "react-native-safe-area-context";
import { useTheme, spacing, radius } from "@/src/theme";
import { AppText, Avatar, Icon, Card, Loading, Button, useToast } from "@/src/ui";
import { StackHeader } from "@/src/Header";
import { api } from "@/src/api";
import { useAuth } from "@/src/auth";

export default function GroupInfo() {
  const { colors } = useTheme();
  const insets = useSafeAreaInsets();
  const router = useRouter();
  const toast = useToast();
  const { id } = useLocalSearchParams<{ id: string }>();
  const { user } = useAuth();
  const [group, setGroup] = useState<any>(null);
  const [loading, setLoading] = useState(true);
  const [addOpen, setAddOpen] = useState(false);
  const [contacts, setContacts] = useState<any[]>([]);

  const load = useCallback(async () => {
    try { const res = await api.get(`/groups/${id}`); setGroup(res); } catch {} finally { setLoading(false); }
  }, [id]);
  useFocusEffect(useCallback(() => { load(); }, [load]));

  const openAdd = async () => {
    try { const r = await api.get("/contacts"); const memberIds = new Set(group.members.map((m: any) => m.user_id)); setContacts(r.contacts.filter((c: any) => !memberIds.has(c.user_id))); setAddOpen(true); } catch {}
  };
  const addMember = async (uid: string) => {
    try { await api.post(`/groups/${id}/members`, { member_ids: [uid] }); setAddOpen(false); load(); toast.show("Member added", "success"); }
    catch (e: any) { toast.show(e.message, "error"); }
  };
  const leave = async () => {
    try { await api.post(`/groups/${id}/leave`); router.replace("/(tabs)"); } catch { toast.show("Failed", "error"); }
  };

  if (loading || !group) return <View style={{ flex: 1, backgroundColor: colors.surface }}><StackHeader title="Group" /><Loading /></View>;
  const isAdmin = group.my_role === "owner" || group.my_role === "admin";

  return (
    <View style={{ flex: 1, backgroundColor: colors.surface }}>
      <StackHeader title="Group Info" />
      <ScrollView contentContainerStyle={{ padding: spacing.lg, gap: spacing.lg }}>
        <View style={{ alignItems: "center" }}>
          <Avatar name={group.name} uri={group.avatar} size={88} />
          <AppText size="xxl" weight="heavy" style={{ marginTop: spacing.md }}>{group.name}</AppText>
          <AppText muted>{group.members.length} members</AppText>
        </View>

        <Button testID="group-brain-button" title="Ask Group Brain" icon="sparkles" onPress={() => router.push({ pathname: "/chat/[id]", params: { id: String(id), name: group.name, group: "1" } })} />
        <Button testID="group-assistant-button" title="Group Assistant & Polls" icon="checkmark-done-outline" variant="secondary" onPress={() => router.push({ pathname: "/group-assistant/[id]", params: { id: String(id), name: group.name } })} />
        <Button testID="group-tasks-button" title="Group Tasks" icon="checkbox-outline" variant="secondary" onPress={() => router.push({ pathname: "/group-tasks/[id]", params: { id: String(id), name: group.name } })} />
        <Button testID="meeting-planner-button" title="Meeting Planner" icon="calendar-outline" variant="secondary" onPress={() => router.push({ pathname: "/meeting-planner/[id]", params: { id: String(id), name: group.name } })} />

        <View>
          <View style={{ flexDirection: "row", alignItems: "center", marginBottom: spacing.sm }}>
            <AppText weight="bold" muted size="sm" style={{ flex: 1 }}>MEMBERS</AppText>
            {isAdmin && <Pressable testID="add-member-button" onPress={openAdd}><AppText weight="bold" color={colors.brandPrimary}>Add</AppText></Pressable>}
          </View>
          <Card style={{ paddingVertical: spacing.xs }}>
            {group.members.map((m: any, i: number) => (
              <View key={m.user_id} style={{ flexDirection: "row", alignItems: "center", paddingVertical: spacing.sm, borderTopWidth: i ? 1 : 0, borderTopColor: colors.divider }}>
                <Avatar name={m.name} uri={m.avatar} size={42} online={m.online} />
                <AppText weight="semibold" style={{ flex: 1, marginLeft: spacing.md }}>{m.name}{m.user_id === user?.user_id ? " (You)" : ""}</AppText>
                {m.role !== "member" && <View style={{ paddingHorizontal: 8, paddingVertical: 2, borderRadius: radius.pill, backgroundColor: colors.brandTertiary }}><AppText size="xs" weight="bold" color={colors.brandPrimary}>{m.role}</AppText></View>}
              </View>
            ))}
          </Card>
        </View>

        <Button testID="leave-group-button" title="Leave Group" variant="danger" onPress={leave} />
      </ScrollView>

      <Modal visible={addOpen} transparent animationType="slide" onRequestClose={() => setAddOpen(false)}>
        <Pressable style={{ flex: 1, backgroundColor: colors.overlay }} onPress={() => setAddOpen(false)} />
        <View style={[styles.sheet, { backgroundColor: colors.card, paddingBottom: insets.bottom + spacing.lg }]}>
          <AppText weight="bold" size="lg" style={{ marginBottom: spacing.md }}>Add Member</AppText>
          <ScrollView style={{ maxHeight: 380 }}>
            {contacts.length === 0 ? <AppText muted>No contacts to add.</AppText> : contacts.map((c) => (
              <Pressable key={c.user_id} testID={`add-${c.user_id}`} onPress={() => addMember(c.user_id)} style={{ flexDirection: "row", alignItems: "center", paddingVertical: spacing.md }}>
                <Avatar name={c.name} uri={c.avatar} size={44} />
                <AppText weight="semibold" style={{ flex: 1, marginLeft: spacing.md }}>{c.name}</AppText>
                <Icon name="add-circle" size={24} color={colors.brandPrimary} />
              </Pressable>
            ))}
          </ScrollView>
        </View>
      </Modal>
    </View>
  );
}

const styles = StyleSheet.create({
  sheet: { position: "absolute", bottom: 0, left: 0, right: 0, borderTopLeftRadius: radius.xl, borderTopRightRadius: radius.xl, padding: spacing.lg },
});
