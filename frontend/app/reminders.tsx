import { useState, useCallback, useEffect } from "react";
import { View, ScrollView, Pressable, Modal, StyleSheet, Keyboard, Platform } from "react-native";
import { useFocusEffect } from "expo-router";
import { useSafeAreaInsets } from "react-native-safe-area-context";
import { useTheme, spacing, radius } from "@/src/theme";
import { AppText, Icon, Card, EmptyState, Loading, Input, Button, useToast } from "@/src/ui";
import { StackHeader } from "@/src/Header";
import { api } from "@/src/api";
import { scheduleLocalReminder } from "@/src/notifications";

function parseWhen(s: string): Date | null {
  if (!s?.trim()) return null;
  const t = Date.parse(s);
  if (!isNaN(t)) return new Date(t);
  return null; // natural-language phrases are stored as-is; only ISO/parseable dates schedule a local notification
}

export default function Reminders() {
  const { colors } = useTheme();
  const insets = useSafeAreaInsets();
  const toast = useToast();
  const [items, setItems] = useState<any[]>([]);
  const [loading, setLoading] = useState(true);
  const [addOpen, setAddOpen] = useState(false);
  const [title, setTitle] = useState("");
  const [when, setWhen] = useState("");
  // Scoped keyboard handling (Reminder page only): no autoFocus; sheet rises above keyboard.
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
    try { const res = await api.get("/reminders"); setItems(res.reminders); } catch {} finally { setLoading(false); }
  }, []);
  useFocusEffect(useCallback(() => { load(); }, [load]));

  const complete = async (id: string) => { setItems((p) => p.map((x) => x.id === id ? { ...x, done: true } : x)); try { await api.put(`/reminders/${id}/done`); } catch { load(); } };
  const del = async (id: string) => { setItems((p) => p.filter((x) => x.id !== id)); try { await api.del(`/reminders/${id}`); } catch {} };
  const add = async () => {
    if (!title.trim()) return;
    Keyboard.dismiss();
    try {
      const res = await api.post<{ reminder?: any }>("/reminders", { title: title.trim(), remind_at: when.trim() || null });
      // Schedule a real local notification if the "when" is a concrete date/time.
      const at = parseWhen(when);
      if (at) { try { await scheduleLocalReminder(res?.reminder?.id || String(Date.now()), "Reminder", title.trim(), at); } catch {} }
      setTitle(""); setWhen(""); setAddOpen(false); load(); toast.show("Reminder set", "success");
    } catch { toast.show("Failed", "error"); }
  };

  return (
    <View style={{ flex: 1, backgroundColor: colors.surface }}>
      <StackHeader title="Reminders" right={<Pressable testID="add-reminder-button" onPress={() => setAddOpen(true)}><Icon name="add-circle" size={28} color={colors.brandPrimary} /></Pressable>} />
      {loading ? <Loading /> : items.length === 0 ? (
        <EmptyState icon="alarm-outline" title="No reminders yet" subtitle="Set reminders manually or ask Chatly to remind you from a message." action={<Button title="Add Reminder" onPress={() => setAddOpen(true)} full={false} icon="add" />} />
      ) : (
        <ScrollView contentContainerStyle={{ padding: spacing.lg, gap: spacing.sm }}>
          {items.map((r) => (
            <Card key={r.id} style={{ flexDirection: "row", alignItems: "center", padding: spacing.md }}>
              <Pressable testID={`complete-reminder-${r.id}`} onPress={() => complete(r.id)} hitSlop={8}>
                <Icon name={r.done ? "checkmark-circle" : "alarm-outline"} size={24} color={r.done ? colors.success : colors.brandPrimary} />
              </Pressable>
              <View style={{ flex: 1, marginLeft: spacing.md }}>
                <AppText weight="medium" style={{ opacity: r.done ? 0.5 : 1, textDecorationLine: r.done ? "line-through" : "none" }}>{r.title}</AppText>
                {r.remind_at ? <AppText size="sm" muted style={{ marginTop: 2 }}>{r.remind_at}</AppText> : null}
              </View>
              <Pressable testID={`delete-reminder-${r.id}`} onPress={() => del(r.id)} hitSlop={8}><Icon name="trash-outline" size={18} color={colors.onSurfaceMuted} /></Pressable>
            </Card>
          ))}
        </ScrollView>
      )}

      <Modal visible={addOpen} transparent animationType="slide" onRequestClose={closeAdd}>
        <Pressable style={{ flex: 1, backgroundColor: colors.overlay }} onPress={closeAdd} />
        <View style={[styles.sheet, { backgroundColor: colors.card, bottom: kb, paddingBottom: kb > 0 ? spacing.lg : insets.bottom + spacing.lg }]}>
          <AppText weight="bold" size="lg" style={{ marginBottom: spacing.md }}>New Reminder</AppText>
          <Input testID="reminder-title-input" label="Remind me to" value={title} onChangeText={setTitle} placeholder="e.g. Reply to Rahul" />
          <Input testID="reminder-when-input" label="When (optional)" value={when} onChangeText={setWhen} placeholder="e.g. 2025-08-20 09:00" autoCapitalize="none" />
          <Button testID="save-reminder" title="Set Reminder" onPress={add} />
        </View>
      </Modal>
    </View>
  );
}

const styles = StyleSheet.create({
  sheet: { position: "absolute", bottom: 0, left: 0, right: 0, borderTopLeftRadius: radius.xl, borderTopRightRadius: radius.xl, padding: spacing.lg },
});
