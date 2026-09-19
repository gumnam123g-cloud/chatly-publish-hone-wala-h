/**
 * Daily Brief screen (features #46, #47, #48). Generates a briefing using
 * server /insights/daily-brief and lets the user switch kind + language.
 */
import React, { useEffect, useState } from "react";
import { View, ScrollView, Pressable, StyleSheet, ActivityIndicator } from "react-native";
import { Stack, router } from "expo-router";
import { SafeAreaView } from "react-native-safe-area-context";
import { useTheme, spacing, radius } from "@/src/theme";
import { AppText, Button, Card, Icon, useToast } from "@/src/ui";
import { api } from "@/src/api";
import { track } from "@/src/analytics";

type Kind = "daily" | "morning" | "end_of_day";
type Resp = { kind: Kind; brief: string; unread_count: number; open_tasks: number; reminders: number; generated_at: string };

const LANGS = ["English", "Hindi", "Hinglish"];

export default function DailyBriefScreen() {
  const { colors } = useTheme();
  const toast = useToast();
  const [kind, setKind] = useState<Kind>("daily");
  const [lang, setLang] = useState("English");
  const [loading, setLoading] = useState(false);
  const [data, setData] = useState<Resp | null>(null);

  const generate = async () => {
    setLoading(true); setData(null);
    try {
      const r = await api.post<Resp>("/insights/daily-brief", { kind, out_lang: lang });
      setData(r);
      track("ai_action_completed", { action: "brief_" + kind });
    } catch (e: any) {
      toast.show(e?.message || "Couldn't generate the brief.", "error");
      track("ai_action_failed", { action: "brief_" + kind });
    } finally { setLoading(false); }
  };

  useEffect(() => { generate(); /* auto-run on open */ /* eslint-disable-next-line */ }, []);

  return (
    <SafeAreaView style={{ flex: 1, backgroundColor: colors.background }} edges={["top", "bottom"]}>
      <Stack.Screen options={{ headerShown: false }} />
      <View style={styles.header}>
        <Pressable onPress={() => router.back()} hitSlop={12} style={styles.iconBtn}>
          <Icon name="chevron-back" size={26} />
        </Pressable>
        <AppText size="xl" weight="bold" style={{ flex: 1, marginLeft: 8 }}>Daily Brief</AppText>
      </View>
      <ScrollView contentContainerStyle={{ padding: spacing.lg, paddingBottom: 40 }}>
        <View style={{ flexDirection: "row", gap: 8, marginBottom: spacing.md }}>
          {((["daily", "morning", "end_of_day"]) as Kind[]).map((k) => (
            <Pressable key={k} onPress={() => setKind(k)} style={{ flex: 1, paddingVertical: 10, borderRadius: radius.pill, borderWidth: 1, borderColor: kind === k ? colors.brandPrimary : colors.border, backgroundColor: kind === k ? colors.brandTertiary : "transparent", alignItems: "center" }}>
              <AppText weight="semibold" size="sm" color={kind === k ? colors.onBrandTertiary : colors.onSurface}>
                {k === "end_of_day" ? "End of Day" : k.charAt(0).toUpperCase() + k.slice(1)}
              </AppText>
            </Pressable>
          ))}
        </View>
        <ScrollView horizontal showsHorizontalScrollIndicator={false} style={{ marginBottom: spacing.md }} contentContainerStyle={{ gap: 8 }}>
          {LANGS.map((l) => (
            <Pressable key={l} onPress={() => setLang(l)} style={{ paddingHorizontal: 12, paddingVertical: 8, borderRadius: radius.pill, borderWidth: 1, borderColor: lang === l ? colors.brandPrimary : colors.border, backgroundColor: lang === l ? colors.brandTertiary : "transparent" }}>
              <AppText size="sm" weight="semibold" color={lang === l ? colors.onBrandTertiary : colors.onSurface}>{l}</AppText>
            </Pressable>
          ))}
        </ScrollView>
        <Button title={loading ? "Generating..." : "Refresh brief"} onPress={generate} loading={loading} />

        {data ? (
          <Card style={{ marginTop: spacing.lg }}>
            <View style={{ flexDirection: "row", justifyContent: "space-between", marginBottom: spacing.md }}>
              <Stat label="Unread" value={String(data.unread_count)} />
              <Stat label="Tasks" value={String(data.open_tasks)} />
              <Stat label="Reminders" value={String(data.reminders)} />
            </View>
            <AppText style={{ lineHeight: 22 }}>{data.brief || "Nothing new right now."}</AppText>
          </Card>
        ) : loading ? (
          <View style={{ paddingVertical: spacing.xxl, alignItems: "center" }}>
            <ActivityIndicator color={colors.brandPrimary} size="large" />
            <AppText muted style={{ marginTop: spacing.md }}>Reading your day...</AppText>
          </View>
        ) : null}
      </ScrollView>
    </SafeAreaView>
  );
}

function Stat({ label, value }: { label: string; value: string }) {
  return (
    <View style={{ alignItems: "center", flex: 1 }}>
      <AppText size="xxl" weight="heavy">{value}</AppText>
      <AppText size="xs" muted style={{ textTransform: "uppercase", letterSpacing: 0.5 }}>{label}</AppText>
    </View>
  );
}

const styles = StyleSheet.create({
  header: { flexDirection: "row", alignItems: "center", paddingHorizontal: spacing.md, height: 56 },
  iconBtn: { width: 40, height: 40, alignItems: "center", justifyContent: "center" },
});
