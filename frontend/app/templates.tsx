/**
 * Chat Templates screen (feature #35). CRUD + copy-to-clipboard.
 */
import React, { useEffect, useState, useCallback } from "react";
import { View, ScrollView, Pressable, StyleSheet, Modal, TextInput, RefreshControl, Alert } from "react-native";
import * as Clipboard from "expo-clipboard";
import { Stack, router } from "expo-router";
import { SafeAreaView } from "react-native-safe-area-context";
import { useTheme, spacing, radius, fontSize } from "@/src/theme";
import { AppText, Button, Card, Icon, useToast } from "@/src/ui";
import { api } from "@/src/api";

type T = { id: string; category: string; title: string; body: string; is_seed?: boolean };

export default function TemplatesScreen() {
  const { colors } = useTheme();
  const toast = useToast();
  const [items, setItems] = useState<T[]>([]);
  const [refreshing, setRefreshing] = useState(false);
  const [editing, setEditing] = useState<T | "new" | null>(null);

  const load = useCallback(async () => {
    setRefreshing(true);
    try {
      const r = await api.get<{ items: T[] }>("/templates");
      setItems(r.items || []);
    } catch (e: any) { toast.show(e?.message || "Couldn't load templates.", "error"); }
    finally { setRefreshing(false); }
  }, []);
  useEffect(() => { load(); }, [load]);

  const copy = async (t: T) => {
    try { await Clipboard.setStringAsync(t.body); toast.show("Copied", "success"); } catch { toast.show("Copy failed", "error"); }
  };
  const remove = (t: T) => {
    Alert.alert("Delete template?", t.title, [
      { text: "Cancel", style: "cancel" },
      { text: "Delete", style: "destructive", onPress: async () => {
        try { await api.del(`/templates/${t.id}`); toast.show("Deleted", "success"); load(); }
        catch (e: any) { toast.show(e?.message || "Couldn't delete.", "error"); }
      } },
    ]);
  };

  const grouped = items.reduce<Record<string, T[]>>((m, t) => {
    (m[t.category] ||= []).push(t); return m;
  }, {});

  return (
    <SafeAreaView style={{ flex: 1, backgroundColor: colors.background }} edges={["top", "bottom"]}>
      <Stack.Screen options={{ headerShown: false }} />
      <View style={styles.header}>
        <Pressable testID="tpl-back" onPress={() => router.back()} hitSlop={12} style={styles.iconBtn}>
          <Icon name="chevron-back" size={26} />
        </Pressable>
        <AppText size="xl" weight="bold" style={{ flex: 1, marginLeft: 8 }}>Templates</AppText>
        <Pressable testID="tpl-new" onPress={() => setEditing("new")} hitSlop={12} style={styles.iconBtn}>
          <Icon name="add" size={26} color={colors.brandPrimary} />
        </Pressable>
      </View>
      <ScrollView
        refreshControl={<RefreshControl refreshing={refreshing} onRefresh={load} tintColor={colors.brandPrimary} />}
        contentContainerStyle={{ padding: spacing.lg, paddingBottom: 40 }}
      >
        {Object.keys(grouped).length === 0 ? (
          <View style={{ alignItems: "center", paddingVertical: spacing.xxl }}>
            <Icon name="document-outline" size={64} color={colors.onSurfaceMuted} />
            <AppText muted style={{ marginTop: spacing.md }}>No templates yet.</AppText>
          </View>
        ) : Object.entries(grouped).map(([cat, list]) => (
          <View key={cat} style={{ marginBottom: spacing.lg }}>
            <AppText size="sm" weight="bold" muted style={{ marginBottom: 6, textTransform: "uppercase", letterSpacing: 0.5 }}>{cat}</AppText>
            {list.map((t) => (
              <Card key={t.id} style={{ marginBottom: spacing.sm }}>
                <View style={{ flexDirection: "row", alignItems: "center", marginBottom: 6 }}>
                  <AppText weight="bold" style={{ flex: 1 }}>{t.title}</AppText>
                  <Pressable onPress={() => copy(t)} style={styles.iconMini}><Icon name="copy-outline" size={18} color={colors.brandPrimary} /></Pressable>
                  <Pressable onPress={() => setEditing(t)} style={styles.iconMini}><Icon name="create-outline" size={18} /></Pressable>
                  {!t.is_seed ? (
                    <Pressable onPress={() => remove(t)} style={styles.iconMini}><Icon name="trash-outline" size={18} color={colors.error} /></Pressable>
                  ) : null}
                </View>
                <AppText numberOfLines={3} muted>{t.body}</AppText>
              </Card>
            ))}
          </View>
        ))}
      </ScrollView>
      {editing ? (
        <TplEditor value={editing === "new" ? null : editing} onClose={() => setEditing(null)} onSaved={() => { setEditing(null); load(); }} />
      ) : null}
    </SafeAreaView>
  );
}

function TplEditor({ value, onClose, onSaved }: { value: T | null; onClose: () => void; onSaved: () => void }) {
  const { colors } = useTheme();
  const toast = useToast();
  const [title, setTitle] = useState(value?.title || "");
  const [body, setBody] = useState(value?.body || "");
  const [category, setCategory] = useState(value?.category || "custom");
  const [saving, setSaving] = useState(false);

  const save = async () => {
    if (!title.trim() || !body.trim()) { toast.show("Title and body are required.", "error"); return; }
    setSaving(true);
    try {
      if (value) await api.patch(`/templates/${value.id}`, { title: title.trim(), body: body.trim(), category });
      else await api.post("/templates", { title: title.trim(), body: body.trim(), category });
      toast.show(value ? "Updated" : "Created", "success");
      onSaved();
    } catch (e: any) { toast.show(e?.message || "Couldn't save.", "error"); }
    finally { setSaving(false); }
  };

  return (
    <Modal visible transparent animationType="slide" onRequestClose={onClose}>
      <Pressable style={{ flex: 1, backgroundColor: colors.overlay }} onPress={onClose} />
      <View style={{ backgroundColor: colors.card, padding: spacing.lg, borderTopLeftRadius: radius.xl, borderTopRightRadius: radius.xl, paddingBottom: 32 }}>
        <AppText size="lg" weight="bold" style={{ marginBottom: spacing.md }}>{value ? "Edit template" : "New template"}</AppText>
        <AppText size="sm" muted style={{ marginBottom: 6 }}>Title</AppText>
        <TextInput value={title} onChangeText={setTitle} maxLength={80} placeholderTextColor={colors.onSurfaceMuted} placeholder="e.g. Availability check"
          style={{ backgroundColor: colors.surfaceTertiary, borderRadius: radius.md, padding: 12, color: colors.onSurface, fontSize: fontSize.base, marginBottom: spacing.md }} />
        <AppText size="sm" muted style={{ marginBottom: 6 }}>Category</AppText>
        <ScrollView horizontal showsHorizontalScrollIndicator={false} style={{ marginBottom: spacing.md }} contentContainerStyle={{ gap: 8 }}>
          {["work", "college", "customer", "followup", "meeting", "custom"].map((c) => (
            <Pressable key={c} onPress={() => setCategory(c)} style={{ paddingHorizontal: 12, paddingVertical: 8, borderRadius: radius.pill, borderWidth: 1, borderColor: category === c ? colors.brandPrimary : colors.border, backgroundColor: category === c ? colors.brandTertiary : "transparent" }}>
              <AppText size="sm" weight="semibold" color={category === c ? colors.onBrandTertiary : colors.onSurface} style={{ textTransform: "capitalize" }}>{c}</AppText>
            </Pressable>
          ))}
        </ScrollView>
        <AppText size="sm" muted style={{ marginBottom: 6 }}>Body — use {"{name}"}, {"{topic}"}, {"{date}"} etc. as merge tokens</AppText>
        <TextInput value={body} onChangeText={setBody} multiline maxLength={4000} placeholderTextColor={colors.onSurfaceMuted} placeholder="Hi {name}, ..."
          style={{ minHeight: 140, backgroundColor: colors.surfaceTertiary, borderRadius: radius.md, padding: 12, color: colors.onSurface, fontSize: fontSize.base, textAlignVertical: "top", marginBottom: spacing.md }} />
        <Button title={value ? "Save" : "Create"} onPress={save} loading={saving} />
      </View>
    </Modal>
  );
}

const styles = StyleSheet.create({
  header: { flexDirection: "row", alignItems: "center", paddingHorizontal: spacing.md, height: 56 },
  iconBtn: { width: 40, height: 40, alignItems: "center", justifyContent: "center" },
  iconMini: { width: 32, height: 32, alignItems: "center", justifyContent: "center" },
});
