// Message Vault — client-side encrypted secure storage.
import { useCallback, useState } from "react";
import { View, ScrollView, Pressable, TextInput, StyleSheet, Modal } from "react-native";
import { useRouter, useFocusEffect } from "expo-router";
import { useSafeAreaInsets } from "react-native-safe-area-context";
import { useTheme, spacing, radius, fontSize } from "@/src/theme";
import { AppText, Icon, Button, useToast, Loading, EmptyState } from "@/src/ui";
import { api } from "@/src/api";
import { vaultEncrypt, vaultDecrypt } from "@/src/vaultCrypto";

type Item = { id: string; title: string; kind: string; ciphertext: string; iv?: string; created_at: string };

export default function Vault() {
  const { colors } = useTheme();
  const insets = useSafeAreaInsets();
  const router = useRouter();
  const toast = useToast();
  const [items, setItems] = useState<Item[]>([]);
  const [loading, setLoading] = useState(true);
  const [open, setOpen] = useState(false);
  const [title, setTitle] = useState("");
  const [text, setText] = useState("");
  const [saving, setSaving] = useState(false);
  const [preview, setPreview] = useState<{ item: Item; text: string } | null>(null);

  const load = useCallback(async () => {
    setLoading(true);
    try {
      const r = await api.get<{ items: Item[] }>("/vault");
      setItems(r.items || []);
    } catch (e: any) { toast.show(e?.message || "Failed", "error"); }
    finally { setLoading(false); }
  }, [toast]);
  useFocusEffect(useCallback(() => { load(); }, [load]));

  const save = async () => {
    if (!title.trim() || !text.trim()) return;
    setSaving(true);
    try {
      const { ciphertext, iv } = await vaultEncrypt(text);
      await api.post("/vault", { title: title.trim(), kind: "note", ciphertext, iv });
      toast.show("Saved securely", "success"); setOpen(false); setTitle(""); setText(""); load();
    } catch (e: any) { toast.show(e?.message || "Encryption failed", "error"); }
    finally { setSaving(false); }
  };

  const reveal = async (it: Item) => {
    try {
      const t = await vaultDecrypt(it.ciphertext, it.iv || "");
      setPreview({ item: it, text: t });
    } catch (e: any) { toast.show("Could not decrypt on this device.", "error"); }
  };

  const remove = async (it: Item) => {
    try { await api.del(`/vault/${it.id}`); load(); if (preview?.item.id === it.id) setPreview(null); }
    catch (e: any) { toast.show(e?.message || "Failed", "error"); }
  };

  return (
    <View style={{ flex: 1, backgroundColor: colors.surface }}>
      <View style={{ paddingTop: insets.top + 6, paddingBottom: spacing.sm, paddingHorizontal: spacing.md, flexDirection: "row", alignItems: "center", backgroundColor: colors.card, borderBottomWidth: 1, borderBottomColor: colors.border }}>
        <Pressable onPress={() => router.back()} hitSlop={10}><Icon name="chevron-back" size={26} /></Pressable>
        <AppText weight="heavy" size="xxl" style={{ marginLeft: spacing.sm, flex: 1 }}>Message Vault</AppText>
        <Pressable onPress={() => setOpen(true)} style={{ width: 38, height: 38, borderRadius: 19, backgroundColor: colors.brandTertiary, alignItems: "center", justifyContent: "center" }}>
          <Icon name="add" size={22} color={colors.brandPrimary} />
        </Pressable>
      </View>
      <ScrollView contentContainerStyle={{ padding: spacing.md }}>
        <AppText size="sm" muted>Everything you save here is encrypted on this device before it leaves. Losing your device or clearing app storage removes the key permanently.</AppText>
        {loading ? <Loading /> : items.length === 0 ? (
          <EmptyState icon="lock-closed-outline" title="Vault is empty" subtitle="Add a secret note, password or sensitive message." />
        ) : items.map((it) => (
          <Pressable key={it.id} onPress={() => reveal(it)}
            style={{ marginTop: spacing.sm, borderWidth: 1, borderColor: colors.border, borderRadius: radius.md, padding: spacing.md, backgroundColor: colors.card, flexDirection: "row", alignItems: "center" }}>
            <Icon name="lock-closed" size={18} color={colors.brandPrimary} />
            <View style={{ marginLeft: 10, flex: 1 }}>
              <AppText weight="bold" numberOfLines={1}>{it.title}</AppText>
              <AppText size="xs" muted>{it.created_at.slice(0, 10)}</AppText>
            </View>
            <Pressable onPress={() => remove(it)} hitSlop={10}><Icon name="trash-outline" size={18} color={colors.error} /></Pressable>
          </Pressable>
        ))}
      </ScrollView>

      <Modal visible={open} transparent animationType="slide" onRequestClose={() => setOpen(false)}>
        <Pressable style={{ flex: 1, backgroundColor: colors.overlay }} onPress={() => setOpen(false)} />
        <View style={[styles.sheet, { backgroundColor: colors.card, paddingBottom: insets.bottom + spacing.lg }]}>
          <AppText weight="bold" size="lg" style={{ marginBottom: spacing.sm }}>Add secret</AppText>
          <TextInput value={title} onChangeText={setTitle} placeholder="Title" placeholderTextColor={colors.onSurfaceMuted}
            style={{ borderWidth: 1, borderColor: colors.border, borderRadius: radius.md, paddingHorizontal: spacing.md, height: 44, color: colors.onSurface, fontSize: fontSize.base, marginBottom: spacing.sm }} />
          <TextInput value={text} onChangeText={setText} placeholder="Secret content (never sent in plaintext)" placeholderTextColor={colors.onSurfaceMuted} multiline secureTextEntry={false}
            style={{ borderWidth: 1, borderColor: colors.border, borderRadius: radius.md, paddingHorizontal: spacing.md, minHeight: 100, color: colors.onSurface, fontSize: fontSize.base, marginBottom: spacing.md, textAlignVertical: "top", paddingVertical: 10 }} />
          <Button title="Encrypt & save" onPress={save} loading={saving} />
        </View>
      </Modal>

      <Modal visible={!!preview} transparent animationType="fade" onRequestClose={() => setPreview(null)}>
        <Pressable style={{ flex: 1, backgroundColor: colors.overlay }} onPress={() => setPreview(null)} />
        <View style={[styles.sheet, { backgroundColor: colors.card, paddingBottom: insets.bottom + spacing.lg }]}>
          <AppText weight="bold" size="lg">{preview?.item.title}</AppText>
          <AppText style={{ marginTop: spacing.sm }}>{preview?.text}</AppText>
          <Button title="Close" variant="secondary" onPress={() => setPreview(null)} />
        </View>
      </Modal>
    </View>
  );
}

const styles = StyleSheet.create({
  sheet: { position: "absolute", bottom: 0, left: 0, right: 0, borderTopLeftRadius: radius.xl, borderTopRightRadius: radius.xl, padding: spacing.lg },
});
