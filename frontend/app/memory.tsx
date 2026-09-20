import { useState, useCallback } from "react";
import { View, ScrollView, Pressable, Modal, StyleSheet } from "react-native";
import { useFocusEffect } from "expo-router";
import { useSafeAreaInsets } from "react-native-safe-area-context";
import { useTheme, spacing, radius } from "@/src/theme";
import { AppText, Icon, Card, EmptyState, Loading, Input, Button, useToast } from "@/src/ui";
import { StackHeader } from "@/src/Header";
import { api } from "@/src/api";

export default function Memory() {
  const { colors } = useTheme();
  const insets = useSafeAreaInsets();
  const toast = useToast();
  const [items, setItems] = useState<any[]>([]);
  const [loading, setLoading] = useState(true);
  const [addOpen, setAddOpen] = useState(false);
  const [text, setText] = useState("");

  const load = useCallback(async () => {
    try { const res = await api.get("/ai/memory"); setItems(res.memories); } catch {} finally { setLoading(false); }
  }, []);
  useFocusEffect(useCallback(() => { load(); }, [load]));

  const add = async () => {
    if (!text.trim()) return;
    try { await api.post("/ai/memory", { text: text.trim() }); setText(""); setAddOpen(false); load(); toast.show("Saved to memory", "success"); }
    catch { toast.show("Failed", "error"); }
  };
  const del = async (id: string) => { setItems((p) => p.filter((x) => x.id !== id)); try { await api.del(`/ai/memory/${id}`); } catch {} };
  const clearAll = async () => { try { await api.del("/ai/memory"); setItems([]); toast.show("Memory cleared", "success"); } catch {} };

  return (
    <View style={{ flex: 1, backgroundColor: colors.surface }}>
      <StackHeader title="AI Memory" right={<Pressable testID="add-memory-button" onPress={() => setAddOpen(true)}><Icon name="add-circle" size={28} color={colors.brandPrimary} /></Pressable>} />
      {loading ? <Loading /> : (
        <ScrollView contentContainerStyle={{ padding: spacing.lg, gap: spacing.sm }}>
          <View style={[styles.note, { backgroundColor: colors.brandTertiary }]}>
            <Icon name="lock-closed-outline" size={16} color={colors.brandPrimary} />
            <AppText size="base" color={colors.onBrandTertiary} style={{ flex: 1, marginLeft: 8 }}>Chatly only remembers what you save here. You're in full control.</AppText>
          </View>
          {items.length === 0 ? (
            <EmptyState icon="bookmark-outline" title="Chatly has no saved memory yet" subtitle={"Save preferences like 'I prefer short replies' so Chatly can help better."} />
          ) : (
            <>
              {items.map((m) => (
                <Card key={m.id} style={{ flexDirection: "row", alignItems: "center", padding: spacing.md }}>
                  <Icon name="bookmark" size={18} color={colors.brandPrimary} />
                  <AppText style={{ flex: 1, marginLeft: spacing.md }}>{m.text}</AppText>
                  <Pressable testID={`delete-memory-${m.id}`} onPress={() => del(m.id)} hitSlop={8}><Icon name="close-circle" size={20} color={colors.onSurfaceMuted} /></Pressable>
                </Card>
              ))}
              <Pressable testID="clear-memory" onPress={clearAll} style={{ marginTop: spacing.md, alignItems: "center" }}>
                <AppText weight="semibold" color={colors.error}>Delete All Memory</AppText>
              </Pressable>
            </>
          )}
        </ScrollView>
      )}

      <Modal visible={addOpen} transparent animationType="slide" onRequestClose={() => setAddOpen(false)}>
        <Pressable style={{ flex: 1, backgroundColor: colors.overlay }} onPress={() => setAddOpen(false)} />
        <View style={[styles.sheet, { backgroundColor: colors.card, paddingBottom: insets.bottom + spacing.lg }]}>
          <AppText weight="bold" size="lg" style={{ marginBottom: spacing.md }}>Remember this</AppText>
          <Input testID="memory-input" value={text} onChangeText={setText} placeholder="e.g. I prefer short, professional replies" multiline />
          <Button testID="save-memory" title="Save" onPress={add} />
        </View>
      </Modal>
    </View>
  );
}

const styles = StyleSheet.create({
  note: { flexDirection: "row", alignItems: "flex-start", padding: spacing.md, borderRadius: radius.md, marginBottom: spacing.sm },
  sheet: { position: "absolute", bottom: 0, left: 0, right: 0, borderTopLeftRadius: radius.xl, borderTopRightRadius: radius.xl, padding: spacing.lg },
});
