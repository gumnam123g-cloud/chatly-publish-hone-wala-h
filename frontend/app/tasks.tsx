import { useState, useCallback, useEffect } from "react";
import { View, ScrollView, Pressable, Modal, StyleSheet, Keyboard, Platform } from "react-native";
import { useFocusEffect } from "@react-navigation/native";
import { useSafeAreaInsets } from "react-native-safe-area-context";
import { useTheme, spacing, radius } from "@/src/theme";
import { AppText, Icon, Card, EmptyState, Loading, Input, Button, useToast } from "@/src/ui";
import { StackHeader } from "@/src/Header";
import { api } from "@/src/api";

export default function Tasks() {
  const { colors } = useTheme();
  const insets = useSafeAreaInsets();
  const toast = useToast();
  const [tasks, setTasks] = useState<any[]>([]);
  const [loading, setLoading] = useState(true);
  const [addOpen, setAddOpen] = useState(false);
  const [title, setTitle] = useState("");
  const [due, setDue] = useState("");
  // Scoped keyboard handling (Task page only): raise the add-sheet above the keyboard.
  // No autoFocus anywhere, so the keyboard only opens when the user taps a field.
  const [kb, setKb] = useState(0);
  useEffect(() => {
    const showEvt = Platform.OS === "ios" ? "keyboardWillShow" : "keyboardDidShow";
    const hideEvt = Platform.OS === "ios" ? "keyboardWillHide" : "keyboardDidHide";
    const s = Keyboard.addListener(showEvt, (e) => setKb(e.endCoordinates?.height || 0));
    const h = Keyboard.addListener(hideEvt, () => setKb(0));
    return () => { s.remove(); h.remove(); };
  }, []);
  const closeAdd = () => { Keyboard.dismiss(); setAddOpen(false); };

  const load = useCallback(async () => {
    try { const res = await api.get("/tasks"); setTasks(res.tasks); } catch {} finally { setLoading(false); }
  }, []);
  useFocusEffect(useCallback(() => { load(); }, [load]));

  const toggle = async (t: any) => {
    setTasks((p) => p.map((x) => x.id === t.id ? { ...x, status: t.status === "done" ? "pending" : "done" } : x));
    try { await api.put(`/tasks/${t.id}`, { status: t.status === "done" ? "pending" : "done" }); } catch { load(); }
  };
  const del = async (id: string) => { setTasks((p) => p.filter((x) => x.id !== id)); try { await api.del(`/tasks/${id}`); } catch {} };
  const add = async () => {
    if (!title.trim()) return;
    try { await api.post("/tasks", { title: title.trim(), due: due.trim() || null, priority: "normal" }); setTitle(""); setDue(""); setAddOpen(false); load(); toast.show("Task added", "success"); }
    catch { toast.show("Failed", "error"); }
  };

  const pColor = (p: string) => p === "high" ? colors.error : p === "low" ? colors.onSurfaceMuted : colors.brandPrimary;

  return (
    <View style={{ flex: 1, backgroundColor: colors.surface }}>
      <StackHeader title="Tasks" right={<Pressable testID="add-task-button" onPress={() => setAddOpen(true)}><Icon name="add-circle" size={28} color={colors.brandPrimary} /></Pressable>} />
      {loading ? <Loading /> : tasks.length === 0 ? (
        <EmptyState icon="checkbox-outline" title="You're all caught up" subtitle="Tasks you create — or Chatly extracts from chats — will appear here." action={<Button title="Add Task" onPress={() => setAddOpen(true)} full={false} icon="add" />} />
      ) : (
        <ScrollView contentContainerStyle={{ padding: spacing.lg, gap: spacing.sm }}>
          {tasks.map((t) => (
            <Card key={t.id} style={{ flexDirection: "row", alignItems: "center", padding: spacing.md }}>
              <Pressable testID={`toggle-task-${t.id}`} onPress={() => toggle(t)} hitSlop={8}>
                <Icon name={t.status === "done" ? "checkmark-circle" : "ellipse-outline"} size={26} color={t.status === "done" ? colors.success : colors.borderStrong} />
              </Pressable>
              <View style={{ flex: 1, marginLeft: spacing.md }}>
                <AppText weight="medium" style={{ textDecorationLine: t.status === "done" ? "line-through" : "none", opacity: t.status === "done" ? 0.5 : 1 }}>{t.title}</AppText>
                <View style={{ flexDirection: "row", alignItems: "center", marginTop: 3, gap: spacing.sm }}>
                  {t.due ? <AppText size="sm" muted>Due {t.due}</AppText> : null}
                  <View style={{ paddingHorizontal: 8, paddingVertical: 1, borderRadius: radius.pill, backgroundColor: pColor(t.priority) + "22" }}>
                    <AppText size="xs" weight="bold" color={pColor(t.priority)}>{t.priority}</AppText>
                  </View>
                </View>
              </View>
              <Pressable testID={`delete-task-${t.id}`} onPress={() => del(t.id)} hitSlop={8}><Icon name="trash-outline" size={18} color={colors.onSurfaceMuted} /></Pressable>
            </Card>
          ))}
        </ScrollView>
      )}

      <Modal visible={addOpen} transparent animationType="slide" onRequestClose={closeAdd}>
        <Pressable style={{ flex: 1, backgroundColor: colors.overlay }} onPress={closeAdd} />
        <View style={[styles.sheet, { backgroundColor: colors.card, bottom: kb, paddingBottom: kb > 0 ? spacing.lg : insets.bottom + spacing.lg }]}>
          <AppText weight="bold" size="lg" style={{ marginBottom: spacing.md }}>New Task</AppText>
          <Input testID="task-title-input" label="Title" value={title} onChangeText={setTitle} placeholder="What needs doing?" />
          <Input testID="task-due-input" label="Due (optional)" value={due} onChangeText={setDue} placeholder="e.g. Friday" autoCapitalize="none" />
          <Button testID="save-task" title="Add Task" onPress={add} />
        </View>
      </Modal>
    </View>
  );
}

const styles = StyleSheet.create({
  sheet: { position: "absolute", bottom: 0, left: 0, right: 0, borderTopLeftRadius: radius.xl, borderTopRightRadius: radius.xl, padding: spacing.lg },
});
