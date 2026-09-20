import { useCallback, useState } from "react";
import { View, ScrollView, Pressable, TextInput, StyleSheet } from "react-native";
import { useRouter, useLocalSearchParams, useFocusEffect } from "expo-router";
import { useSafeAreaInsets } from "react-native-safe-area-context";
import { useTheme, spacing, radius, fontSize } from "@/src/theme";
import { AppText, Icon, EmptyState, Loading, useToast, Button } from "@/src/ui";
import { api } from "@/src/api";

type Suggestion = { slot: string; available: string[]; coverage: number };

export default function MeetingPlanner() {
  const { colors } = useTheme();
  const insets = useSafeAreaInsets();
  const router = useRouter();
  const toast = useToast();
  const { id, name } = useLocalSearchParams<{ id: string; name?: string }>();
  const [slots, setSlots] = useState<string[]>([]);
  const [suggestions, setSuggestions] = useState<Suggestion[]>([]);
  const [total, setTotal] = useState(0);
  const [loading, setLoading] = useState(true);
  const [saving, setSaving] = useState(false);
  const [meetingTitle, setMeetingTitle] = useState("Team meeting");
  const [location, setLocation] = useState("");

  const load = useCallback(async () => {
    setLoading(true);
    try {
      const r = await api.get<any>(`/groups/${id}/meeting/common`);
      setSuggestions(r.suggestions || []); setTotal(r.total_members || 0);
    } catch (e: any) { toast.show(e?.message || "Failed", "error"); }
    finally { setLoading(false); }
  }, [id, toast]);
  useFocusEffect(useCallback(() => { load(); }, [load]));

  const addQuickSlot = (hoursFromNow: number) => {
    const d = new Date(Date.now() + hoursFromNow * 3600 * 1000);
    setSlots((p) => Array.from(new Set([...p, d.toISOString().slice(0, 16)])));
  };
  const save = async () => {
    if (!slots.length) return toast.show("Add at least one slot.", "info");
    setSaving(true);
    try {
      await api.post(`/groups/${id}/meeting/availability`, { slots });
      toast.show("Availability saved", "success"); load();
    } catch (e: any) { toast.show(e?.message || "Failed", "error"); }
    finally { setSaving(false); }
  };
  const confirm = async (slot: string) => {
    try {
      await api.post(`/groups/${id}/meeting/confirm`, { slot, title: meetingTitle, location: location || undefined });
      toast.show("Meeting confirmed & posted to group", "success");
    } catch (e: any) { toast.show(e?.message || "Failed", "error"); }
  };

  return (
    <View style={{ flex: 1, backgroundColor: colors.surface }}>
      <View style={{ paddingTop: insets.top + 6, paddingBottom: spacing.sm, paddingHorizontal: spacing.md, flexDirection: "row", alignItems: "center", backgroundColor: colors.card, borderBottomWidth: 1, borderBottomColor: colors.border }}>
        <Pressable onPress={() => router.back()} hitSlop={10}><Icon name="chevron-back" size={26} /></Pressable>
        <AppText weight="heavy" size="xl" style={{ marginLeft: spacing.sm, flex: 1 }} numberOfLines={1}>{name || "Meeting Planner"}</AppText>
      </View>
      <ScrollView contentContainerStyle={{ padding: spacing.md }}>
        <AppText weight="bold" size="lg">Your availability</AppText>
        <AppText muted size="sm" style={{ marginTop: 4 }}>Add times you're free. Chatly finds common slots across the group.</AppText>
        <View style={{ flexDirection: "row", flexWrap: "wrap", gap: 8, marginTop: spacing.sm }}>
          {[2, 4, 24, 26, 48, 50].map((h) => (
            <Pressable key={h} onPress={() => addQuickSlot(h)} style={{ paddingHorizontal: 12, paddingVertical: 8, borderRadius: radius.pill, borderWidth: 1, borderColor: colors.border, backgroundColor: colors.card }}>
              <AppText size="sm">In {h}h</AppText>
            </Pressable>
          ))}
        </View>
        <View style={{ flexDirection: "row", flexWrap: "wrap", gap: 8, marginTop: spacing.sm }}>
          {slots.map((s) => (
            <Pressable key={s} onPress={() => setSlots((p) => p.filter((x) => x !== s))} style={{ paddingHorizontal: 12, paddingVertical: 8, borderRadius: radius.pill, backgroundColor: colors.brandTertiary, flexDirection: "row", alignItems: "center" }}>
              <AppText size="sm" weight="semibold" color={colors.brandPrimary}>{s.replace("T", " ")}</AppText>
              <Icon name="close" size={14} color={colors.brandPrimary} style={{ marginLeft: 6 }} />
            </Pressable>
          ))}
        </View>
        <Button title="Save availability" onPress={save} loading={saving} />

        <AppText weight="bold" size="lg" style={{ marginTop: spacing.xl }}>Suggested common slots</AppText>
        <AppText muted size="sm" style={{ marginTop: 4, marginBottom: spacing.sm }}>Chatly only suggests — confirm to post the meeting to the group.</AppText>
        <TextInput value={meetingTitle} onChangeText={setMeetingTitle} placeholder="Meeting title" placeholderTextColor={colors.onSurfaceMuted}
          style={{ borderWidth: 1, borderColor: colors.border, borderRadius: radius.md, paddingHorizontal: spacing.md, height: 44, color: colors.onSurface, fontSize: fontSize.base, marginBottom: spacing.sm }} />
        <TextInput value={location} onChangeText={setLocation} placeholder="Location (optional)" placeholderTextColor={colors.onSurfaceMuted}
          style={{ borderWidth: 1, borderColor: colors.border, borderRadius: radius.md, paddingHorizontal: spacing.md, height: 44, color: colors.onSurface, fontSize: fontSize.base, marginBottom: spacing.md }} />
        {loading ? <Loading /> : suggestions.length === 0 ? (
          <EmptyState icon="calendar-outline" title="No common slots yet" subtitle="Ask more members to submit availability." />
        ) : suggestions.map((s) => (
          <View key={s.slot} style={{ borderWidth: 1, borderColor: colors.border, borderRadius: radius.md, padding: spacing.md, backgroundColor: colors.card, marginBottom: spacing.sm }}>
            <View style={{ flexDirection: "row", alignItems: "center" }}>
              <Icon name="calendar" size={18} color={colors.brandPrimary} />
              <AppText weight="bold" style={{ marginLeft: 8, flex: 1 }}>{s.slot.replace("T", " ")}</AppText>
              <AppText size="sm" muted>{s.available.length}/{total}</AppText>
            </View>
            <Button title="Confirm this meeting" variant="secondary" onPress={() => confirm(s.slot)} />
          </View>
        ))}
      </ScrollView>
    </View>
  );
}
