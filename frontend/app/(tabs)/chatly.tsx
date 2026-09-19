import { useState, useCallback } from "react";
import { View, ScrollView, Pressable, StyleSheet, RefreshControl } from "react-native";
import { useRouter } from "expo-router";
import { useFocusEffect } from "@react-navigation/native";
import { useSafeAreaInsets } from "react-native-safe-area-context";
import { LinearGradient } from "expo-linear-gradient";
import { Image } from "expo-image";
import { useTheme, spacing, radius } from "@/src/theme";
import { AppText, Icon, Card } from "@/src/ui";
import { api } from "@/src/api";
import { useAuth } from "@/src/auth";

const HERO = "https://images.unsplash.com/photo-1590959651373-a3db0f38a961?crop=entropy&cs=srgb&fm=jpg&w=800&q=80";

const QUICK = [
  { key: "assistant", label: "Ask Anything", icon: "sparkles", route: "/assistant" },
  { key: "ask-chats", label: "Ask Your Chats", icon: "chatbubble-ellipses-outline", route: "/ask-chats" },
  { key: "research", label: "Deep Research", icon: "globe-outline", route: "/research" },
  { key: "daily-brief", label: "Daily Brief", icon: "newspaper-outline", route: "/daily-brief" },
  { key: "search-all", label: "Search All", icon: "search-outline", route: "/universal-search" },
  { key: "scheduled", label: "Scheduled", icon: "time-outline", route: "/scheduled" },
  { key: "templates", label: "Templates", icon: "document-text-outline", route: "/templates" },
  { key: "creations", label: "AI Studio", icon: "color-wand-outline", route: "/creations" },
  { key: "tasks", label: "Tasks", icon: "checkbox-outline", route: "/tasks" },
  { key: "important", label: "Important", icon: "flag-outline", route: "/important" },
];

export default function Chatly() {
  const { colors, isDark } = useTheme();
  const insets = useSafeAreaInsets();
  const router = useRouter();
  const { user } = useAuth();
  const [insights, setInsights] = useState<any>({});
  const [refreshing, setRefreshing] = useState(false);

  const load = useCallback(async () => {
    try {
      const res = await api.get("/ai/insights");
      setInsights(res);
    } catch {} finally { setRefreshing(false); }
  }, []);

  useFocusEffect(useCallback(() => { load(); }, [load]));

  const greeting = () => {
    const h = new Date().getHours();
    return h < 12 ? "Good morning" : h < 17 ? "Good afternoon" : "Good evening";
  };

  const insightCards = [
    { label: "Important", value: insights.important ?? 0, icon: "flag", route: "/important", color: colors.error },
    { label: "Pending Tasks", value: insights.pending_tasks ?? 0, icon: "checkbox", route: "/tasks", color: colors.brandPrimary },
    { label: "Pending Replies", value: insights.pending_replies ?? 0, icon: "arrow-undo", route: "/(tabs)", color: colors.warning },
    { label: "Reminders", value: insights.reminders ?? 0, icon: "alarm", route: "/reminders", color: colors.success },
  ];

  return (
    <View style={{ flex: 1, backgroundColor: colors.surface }}>
      <ScrollView
        contentContainerStyle={{ paddingBottom: spacing.xxl }}
        showsVerticalScrollIndicator={false}
        refreshControl={<RefreshControl refreshing={refreshing} onRefresh={() => { setRefreshing(true); load(); }} tintColor={colors.brandPrimary} />}
      >
        {/* Hero */}
        <View style={{ height: 240 }}>
          <Image source={{ uri: HERO }} style={StyleSheet.absoluteFill} contentFit="cover" />
          <LinearGradient colors={["rgba(0,0,0,0.15)", "rgba(0,0,0,0.75)"]} style={StyleSheet.absoluteFill} />
          <View style={{ flex: 1, padding: spacing.xl, paddingTop: insets.top + spacing.md, justifyContent: "flex-end" }}>
            <AppText size="base" color="rgba(255,255,255,0.85)">{greeting()},</AppText>
            <AppText size="xxxl" weight="heavy" color="#fff">{user?.name?.split(" ")[0] || "there"}</AppText>
            <AppText size="base" color="rgba(255,255,255,0.9)" style={{ marginTop: 4 }}>Your AI assistant is ready to handle your day.</AppText>
            <Pressable
              testID="handle-my-day-button"
              onPress={() => router.push("/assistant?prompt=Handle my day")}
              style={{ flexDirection: "row", alignItems: "center", alignSelf: "flex-start", marginTop: spacing.lg, backgroundColor: colors.brandPrimary, paddingHorizontal: spacing.lg, height: 46, borderRadius: radius.pill }}
            >
              <Icon name="sparkles" size={18} color="#fff" />
              <AppText weight="bold" color="#fff" style={{ marginLeft: 8 }}>Handle My Day</AppText>
            </Pressable>
          </View>
        </View>

        {/* Ask Chatly card */}
        <Pressable testID="ask-chatly-card" onPress={() => router.push("/assistant")} style={{ marginHorizontal: spacing.lg, marginTop: -spacing.xl }}>
          <LinearGradient colors={[colors.brandPrimary, colors.brandSecondary]} start={{ x: 0, y: 0 }} end={{ x: 1, y: 1 }} style={styles.askCard}>
            <View style={{ width: 46, height: 46, borderRadius: 14, backgroundColor: "rgba(255,255,255,0.22)", alignItems: "center", justifyContent: "center" }}>
              <Icon name="sparkles" size={26} color="#fff" />
            </View>
            <View style={{ flex: 1, marginLeft: spacing.md }}>
              <AppText weight="bold" size="lg" color="#fff">Ask Chatly</AppText>
              <AppText size="base" color="rgba(255,255,255,0.9)">Anything, in English, Hindi or Hinglish</AppText>
            </View>
            <Icon name="arrow-forward" size={20} color="#fff" />
          </LinearGradient>
        </Pressable>

        {/* Quick actions */}
        <AppText weight="bold" size="lg" style={{ marginTop: spacing.xl, marginHorizontal: spacing.lg, marginBottom: spacing.md }}>Quick Actions</AppText>
        <View style={styles.grid}>
          {QUICK.map((q) => (
            <Pressable key={q.key} testID={`quick-${q.key}`} onPress={() => router.push(q.route as any)} style={{ width: "33.33%", padding: spacing.xs }}>
              <View style={[styles.quickCard, { backgroundColor: colors.card, borderColor: colors.border }]}>
                <View style={{ width: 44, height: 44, borderRadius: 13, backgroundColor: colors.brandTertiary, alignItems: "center", justifyContent: "center", marginBottom: spacing.sm }}>
                  <Icon name={q.icon as any} size={22} color={colors.brandPrimary} />
                </View>
                <AppText size="sm" weight="semibold" center numberOfLines={2}>{q.label}</AppText>
              </View>
            </Pressable>
          ))}
        </View>

        {/* Insights */}
        <AppText weight="bold" size="lg" style={{ marginTop: spacing.xl, marginHorizontal: spacing.lg, marginBottom: spacing.md }}>AI Insights</AppText>
        <View style={{ paddingHorizontal: spacing.lg, gap: spacing.md }}>
          {insightCards.map((c) => (
            <Card key={c.label} testID={`insight-${c.label}`} onPress={() => router.push(c.route as any)} style={{ flexDirection: "row", alignItems: "center", padding: spacing.md }}>
              <View style={{ width: 42, height: 42, borderRadius: 12, backgroundColor: c.color + "22", alignItems: "center", justifyContent: "center" }}>
                <Icon name={c.icon as any} size={20} color={c.color} />
              </View>
              <AppText weight="semibold" style={{ flex: 1, marginLeft: spacing.md }}>{c.label}</AppText>
              <AppText size="xl" weight="heavy" color={c.color}>{c.value}</AppText>
              <Icon name="chevron-forward" size={18} color={colors.onSurfaceMuted} />
            </Card>
          ))}
        </View>
      </ScrollView>
    </View>
  );
}

const styles = StyleSheet.create({
  askCard: { flexDirection: "row", alignItems: "center", padding: spacing.lg, borderRadius: radius.lg },
  grid: { flexDirection: "row", flexWrap: "wrap", paddingHorizontal: spacing.lg - spacing.xs },
  quickCard: { borderWidth: 1, borderRadius: radius.md, padding: spacing.md, alignItems: "center", minHeight: 110, justifyContent: "center" },
});
