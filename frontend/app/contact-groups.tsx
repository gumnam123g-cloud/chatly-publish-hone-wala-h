import { useCallback, useState } from "react";
import { View, ScrollView, Pressable, TextInput, StyleSheet } from "react-native";
import { useRouter, useFocusEffect } from "expo-router";
import { useSafeAreaInsets } from "react-native-safe-area-context";
import { useTheme, spacing, radius, fontSize } from "@/src/theme";
import { AppText, Icon, EmptyState, Loading, useToast } from "@/src/ui";
import { api } from "@/src/api";

type Group = { label: string; contact_ids: string[]; count: number };

export default function ContactGroups() {
  const { colors } = useTheme();
  const insets = useSafeAreaInsets();
  const router = useRouter();
  const toast = useToast();
  const [groups, setGroups] = useState<Group[]>([]);
  const [contacts, setContacts] = useState<any[]>([]);
  const [selectedLabel, setSelectedLabel] = useState<string>("family");
  const [newLabel, setNewLabel] = useState("");
  const [loading, setLoading] = useState(true);

  const load = useCallback(async () => {
    setLoading(true);
    try {
      const g = await api.get<{ groups: Group[] }>("/contact-groups");
      setGroups(g.groups || []);
      const c = await api.get<{ contacts: any[] }>("/contacts/list");
      setContacts(c.contacts || []);
    } catch (e: any) { toast.show(e?.message || "Failed", "error"); }
    finally { setLoading(false); }
  }, [toast]);
  useFocusEffect(useCallback(() => { load(); }, [load]));

  const labels = Array.from(new Set([...groups.map((g) => g.label), "family", "friends", "work", "college"]));
  const memberIds = groups.find((g) => g.label === selectedLabel)?.contact_ids || [];

  const toggle = async (contactId: string) => {
    const existing = memberIds.includes(contactId);
    const currentLabels = Array.from(new Set([
      ...groups.filter((g) => g.contact_ids.includes(contactId)).map((g) => g.label),
    ]));
    const next = existing ? currentLabels.filter((l) => l !== selectedLabel) : [...currentLabels, selectedLabel];
    try {
      await api.put("/contact-groups", { contact_id: contactId, labels: next });
      load();
    } catch (e: any) { toast.show(e?.message || "Failed", "error"); }
  };

  const addLabel = () => {
    const clean = newLabel.trim().toLowerCase();
    if (!clean) return;
    if (!labels.includes(clean)) setGroups((p) => [...p, { label: clean, contact_ids: [], count: 0 }]);
    setSelectedLabel(clean); setNewLabel("");
  };

  return (
    <View style={{ flex: 1, backgroundColor: colors.surface }}>
      <View style={{ paddingTop: insets.top + 6, paddingBottom: spacing.sm, paddingHorizontal: spacing.md, flexDirection: "row", alignItems: "center", backgroundColor: colors.card, borderBottomWidth: 1, borderBottomColor: colors.border }}>
        <Pressable onPress={() => router.back()} hitSlop={10}><Icon name="chevron-back" size={26} /></Pressable>
        <AppText weight="heavy" size="xxl" style={{ marginLeft: spacing.sm, flex: 1 }}>Contact Groups</AppText>
      </View>
      <ScrollView horizontal showsHorizontalScrollIndicator={false}
        contentContainerStyle={{ paddingHorizontal: spacing.md, gap: 8, paddingVertical: spacing.sm }}>
        {labels.map((l) => (
          <Pressable key={l} onPress={() => setSelectedLabel(l)}
            style={{ paddingHorizontal: 12, paddingVertical: 8, borderRadius: radius.pill, borderWidth: 1,
              borderColor: selectedLabel === l ? colors.brandPrimary : colors.border,
              backgroundColor: selectedLabel === l ? colors.brandTertiary : "transparent" }}>
            <AppText size="sm" weight="semibold" style={{ textTransform: "capitalize" }}>{l}</AppText>
          </Pressable>
        ))}
      </ScrollView>
      <View style={{ flexDirection: "row", paddingHorizontal: spacing.md, gap: 8, marginTop: 4 }}>
        <TextInput value={newLabel} onChangeText={setNewLabel} placeholder="New group name" placeholderTextColor={colors.onSurfaceMuted}
          style={{ flex: 1, borderWidth: 1, borderColor: colors.border, borderRadius: radius.md, paddingHorizontal: spacing.md, height: 42, color: colors.onSurface, fontSize: fontSize.base }} />
        <Pressable onPress={addLabel} style={{ paddingHorizontal: 14, height: 42, borderRadius: radius.md, backgroundColor: colors.brandPrimary, justifyContent: "center" }}>
          <AppText weight="bold" color="#fff">Add</AppText>
        </Pressable>
      </View>
      {loading ? <Loading /> : contacts.length === 0 ? (
        <EmptyState icon="people-outline" title="No contacts" subtitle="Add contacts first, then organize them into groups." />
      ) : (
        <ScrollView contentContainerStyle={{ padding: spacing.md, gap: 6 }}>
          {contacts.map((c: any) => {
            const on = memberIds.includes(c.user_id);
            return (
              <Pressable key={c.user_id} onPress={() => toggle(c.user_id)}
                style={{ borderWidth: 1, borderColor: on ? colors.brandPrimary : colors.border, borderRadius: radius.md, padding: spacing.md, backgroundColor: on ? colors.brandTertiary : colors.card, flexDirection: "row", alignItems: "center" }}>
                <Icon name={on ? "checkmark-circle" : "ellipse-outline"} size={22} color={on ? colors.brandPrimary : colors.onSurfaceMuted} />
                <AppText style={{ marginLeft: 10, flex: 1 }} numberOfLines={1}>{c.name}</AppText>
                <AppText size="xs" muted>{c.username || ""}</AppText>
              </Pressable>
            );
          })}
        </ScrollView>
      )}
    </View>
  );
}

const styles = StyleSheet.create({});
