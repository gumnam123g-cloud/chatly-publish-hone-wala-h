import { useCallback, useState } from "react";
import { View, ScrollView, Pressable, TextInput, StyleSheet, Modal } from "react-native";
import { useRouter, useLocalSearchParams, useFocusEffect } from "expo-router";
import { useSafeAreaInsets } from "react-native-safe-area-context";
import { useTheme, spacing, radius, fontSize } from "@/src/theme";
import { AppText, Icon, EmptyState, Loading, useToast, Button } from "@/src/ui";
import { api } from "@/src/api";

type Task = { id: string; title: string; assignee_id?: string; due_at?: string; status: "open" | "in_progress" | "done"; priority: string; notes?: string };

export default function GroupTasks() {
  const { colors } = useTheme();
  const insets = useSafeAreaInsets();
  const router = useRouter();
  const toast = useToast();
  const { id, name } = useLocalSearchParams<{ id: string; name?: string }>();
  const [tasks, setTasks] = useState<Task[]>([]);
  const [members, setMembers] = useState<any[]>([]);
  const [loading, setLoading] = useState(true);
  const [open, setOpen] = useState(false);
  const [title, setTitle] = useState("");
  const [assignee, setAssignee] = useState<string | null>(null);
  const [due, setDue] = useState("");
  const [saving, setSaving] = useState(false);

  const load = useCallback(async () => {
    setLoading(true);
    try {
      const t = await api.get<{ tasks: Task[] }>(`/groups/${id}/tasks`);
      setTasks(t.tasks || []);
      const g = await api.get<any>(`/groups/${id}`);
      setMembers(g.members || []);
    } catch (e: any) { toast.show(e?.message || "Failed", "error"); }
    finally { setLoading(false); }
  }, [id, toast]);
  useFocusEffect(useCallback(() => { load(); }, [load]));

  const create = async () => {
    if (!title.trim()) return;
    setSaving(true);
    try {
      await api.post(`/groups/${id}/tasks`, { title: title.trim(), assignee_id: assignee, due_at: due || undefined });
      toast.show("Task created", "success"); setOpen(false); setTitle(""); setAssignee(null); setDue(""); load();
    } catch (e: any) { toast.show(e?.message || "Failed", "error"); }
    finally { setSaving(false); }
  };

  const cycle = async (t: Task) => {
    const next = t.status === "open" ? "in_progress" : t.status === "in_progress" ? "done" : "open";
    try { await api.patch(`/groups/${id}/tasks/${t.id}`, { status: next }); load(); }
    catch (e: any) { toast.show(e?.message || "Failed", "error"); }
  };

  const remove = async (t: Task) => {
    try { await api.del(`/groups/${id}/tasks/${t.id}`); load(); }
    catch (e: any) { toast.show(e?.message || "Failed", "error"); }
  };

  const nameOf = (uid?: string | null) => members.find((m) => m.user_id === uid)?.name || "Unassigned";

  return (
    <View style={{ flex: 1, backgroundColor: colors.surface }}>
      <View style={{ paddingTop: insets.top + 6, paddingBottom: spacing.sm, paddingHorizontal: spacing.md, flexDirection: "row", alignItems: "center", backgroundColor: colors.card, borderBottomWidth: 1, borderBottomColor: colors.border }}>
        <Pressable onPress={() => router.back()} hitSlop={10}><Icon name="chevron-back" size={26} /></Pressable>
        <AppText weight="heavy" size="xl" style={{ marginLeft: spacing.sm, flex: 1 }} numberOfLines={1}>{name || "Group Tasks"}</AppText>
        <Pressable onPress={() => setOpen(true)} style={{ width: 38, height: 38, borderRadius: 19, backgroundColor: colors.brandTertiary, alignItems: "center", justifyContent: "center" }}>
          <Icon name="add" size={22} color={colors.brandPrimary} />
        </Pressable>
      </View>
      {loading ? <Loading /> : tasks.length === 0 ? (
        <EmptyState icon="checkbox-outline" title="No tasks yet" subtitle="Create a task and assign it to a group member." />
      ) : (
        <ScrollView contentContainerStyle={{ padding: spacing.md, gap: spacing.sm }}>
          {tasks.map((t) => (
            <View key={t.id} style={{ borderWidth: 1, borderColor: colors.border, borderRadius: radius.md, padding: spacing.md, backgroundColor: colors.card }}>
              <View style={{ flexDirection: "row", alignItems: "center" }}>
                <Pressable onPress={() => cycle(t)} hitSlop={10}>
                  <Icon name={t.status === "done" ? "checkbox" : t.status === "in_progress" ? "sync" : "square-outline"} size={22} color={t.status === "done" ? colors.success : colors.brandPrimary} />
                </Pressable>
                <AppText weight="bold" size="md" style={{ marginLeft: 10, flex: 1, textDecorationLine: t.status === "done" ? "line-through" : "none" }} numberOfLines={2}>{t.title}</AppText>
                <Pressable onPress={() => remove(t)} hitSlop={10}><Icon name="trash-outline" size={18} color={colors.error} /></Pressable>
              </View>
              <View style={{ flexDirection: "row", marginTop: 8, gap: 6, flexWrap: "wrap" }}>
                <View style={{ paddingHorizontal: 8, paddingVertical: 4, borderRadius: radius.pill, backgroundColor: colors.surfaceTertiary }}>
                  <AppText size="xs" muted>{nameOf(t.assignee_id)}</AppText>
                </View>
                {t.due_at && <View style={{ paddingHorizontal: 8, paddingVertical: 4, borderRadius: radius.pill, backgroundColor: colors.surfaceTertiary }}>
                  <AppText size="xs" muted>Due {t.due_at.slice(0, 10)}</AppText>
                </View>}
                <View style={{ paddingHorizontal: 8, paddingVertical: 4, borderRadius: radius.pill, backgroundColor: colors.brandTertiary }}>
                  <AppText size="xs" weight="semibold" color={colors.brandPrimary} style={{ textTransform: "capitalize" }}>{t.status.replace("_", " ")}</AppText>
                </View>
              </View>
            </View>
          ))}
        </ScrollView>
      )}

      <Modal visible={open} transparent animationType="slide" onRequestClose={() => setOpen(false)}>
        <Pressable style={{ flex: 1, backgroundColor: colors.overlay }} onPress={() => setOpen(false)} />
        <View style={[styles.sheet, { backgroundColor: colors.card, paddingBottom: insets.bottom + spacing.lg }]}>
          <AppText weight="bold" size="lg" style={{ marginBottom: spacing.sm }}>New Task</AppText>
          <TextInput value={title} onChangeText={setTitle} placeholder="Task title" placeholderTextColor={colors.onSurfaceMuted}
            style={{ borderWidth: 1, borderColor: colors.border, borderRadius: radius.md, paddingHorizontal: spacing.md, height: 46, color: colors.onSurface, fontSize: fontSize.base, marginBottom: spacing.sm }} />
          <TextInput value={due} onChangeText={setDue} placeholder="Due date (YYYY-MM-DD, optional)" placeholderTextColor={colors.onSurfaceMuted}
            style={{ borderWidth: 1, borderColor: colors.border, borderRadius: radius.md, paddingHorizontal: spacing.md, height: 46, color: colors.onSurface, fontSize: fontSize.base, marginBottom: spacing.sm }} />
          <AppText muted size="sm" style={{ marginBottom: 6 }}>Assign to</AppText>
          <ScrollView horizontal showsHorizontalScrollIndicator={false} contentContainerStyle={{ gap: 8, marginBottom: spacing.md }}>
            <Pressable onPress={() => setAssignee(null)} style={{ paddingHorizontal: 12, paddingVertical: 8, borderRadius: radius.pill, borderWidth: 1, borderColor: !assignee ? colors.brandPrimary : colors.border, backgroundColor: !assignee ? colors.brandTertiary : "transparent" }}>
              <AppText size="sm" weight="semibold">Nobody</AppText>
            </Pressable>
            {members.map((m: any) => (
              <Pressable key={m.user_id} onPress={() => setAssignee(m.user_id)} style={{ paddingHorizontal: 12, paddingVertical: 8, borderRadius: radius.pill, borderWidth: 1, borderColor: assignee === m.user_id ? colors.brandPrimary : colors.border, backgroundColor: assignee === m.user_id ? colors.brandTertiary : "transparent" }}>
                <AppText size="sm" weight="semibold" numberOfLines={1}>{m.name}</AppText>
              </Pressable>
            ))}
          </ScrollView>
          <Button title="Create Task" onPress={create} loading={saving} />
        </View>
      </Modal>
    </View>
  );
}

const styles = StyleSheet.create({
  sheet: { position: "absolute", bottom: 0, left: 0, right: 0, borderTopLeftRadius: radius.xl, borderTopRightRadius: radius.xl, padding: spacing.lg },
});
