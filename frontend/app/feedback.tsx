/**
 * User-facing feedback screen.
 *
 * Sends POST /api/feedback with the entered message + a picked category + app
 * version + platform info. On success we show a toast and pop the screen so
 * the user is back in Profile.
 */
import React, { useState } from "react";
import { View, ScrollView, Pressable, KeyboardAvoidingView, Platform, StyleSheet } from "react-native";
import { Stack, router } from "expo-router";
import Constants from "expo-constants";
import { SafeAreaView } from "react-native-safe-area-context";
import { AppText, Button, Input, useToast } from "@/src/ui";
import { useTheme, spacing, radius, fontSize } from "@/src/theme";
import { api } from "@/src/api";
import { track } from "@/src/analytics";

const CATEGORIES = ["general", "bug", "feature", "performance", "ai", "calls"];

export default function FeedbackScreen() {
  const { colors } = useTheme();
  const toast = useToast();
  const [category, setCategory] = useState("general");
  const [message, setMessage] = useState("");
  const [submitting, setSubmitting] = useState(false);

  const submit = async () => {
    const trimmed = message.trim();
    if (trimmed.length < 3) {
      toast.show("Please write a bit more so we can help.", "error");
      return;
    }
    setSubmitting(true);
    try {
      await api.post("/feedback", {
        message: trimmed,
        category,
        app_version: (Constants.expoConfig?.version as string) || "dev",
        platform: Platform.OS,
        device: Platform.OS === "android" ? "Android" : Platform.OS === "ios" ? "iOS" : "Web",
      });
      track("feedback_submitted", { category });
      toast.show("Thanks! We received your feedback.", "success");
      router.back();
    } catch (e: any) {
      toast.show(e?.message || "Couldn't send feedback. Please try again.", "error");
    } finally {
      setSubmitting(false);
    }
  };

  return (
    <SafeAreaView style={{ flex: 1, backgroundColor: colors.background }} edges={["top", "bottom"]}>
      <Stack.Screen options={{ headerShown: false }} />
      <View style={styles.header}>
        <Pressable testID="feedback-back" onPress={() => router.back()} hitSlop={12} style={styles.iconBtn}>
          <AppText size="lg">←</AppText>
        </Pressable>
        <AppText size="xl" weight="bold" style={{ marginLeft: 8 }}>Send Feedback</AppText>
      </View>
      <KeyboardAvoidingView behavior={Platform.OS === "ios" ? "padding" : undefined} style={{ flex: 1 }}>
        <ScrollView contentContainerStyle={{ padding: spacing.lg, paddingBottom: 40 }} keyboardShouldPersistTaps="handled">
          <AppText muted style={{ marginBottom: spacing.md }}>
            Tell us what's working, what's not, or what you'd like to see. We read every message.
          </AppText>

          <AppText weight="semibold" style={{ marginBottom: 8 }}>Category</AppText>
          <View style={{ flexDirection: "row", flexWrap: "wrap", gap: 8, marginBottom: spacing.lg }}>
            {CATEGORIES.map((c) => (
              <Pressable
                key={c}
                testID={`feedback-cat-${c}`}
                onPress={() => setCategory(c)}
                style={{
                  paddingHorizontal: 14,
                  paddingVertical: 8,
                  borderRadius: radius.pill,
                  borderWidth: 1,
                  borderColor: category === c ? colors.brandPrimary : colors.border,
                  backgroundColor: category === c ? colors.brandTertiary : "transparent",
                }}
              >
                <AppText size="sm" weight="semibold" style={{ textTransform: "capitalize" }} color={category === c ? colors.onBrandTertiary : colors.onSurface}>{c}</AppText>
              </Pressable>
            ))}
          </View>

          <AppText weight="semibold" style={{ marginBottom: 8 }}>Your message</AppText>
          <Input
            testID="feedback-message"
            value={message}
            onChangeText={setMessage}
            placeholder="What can we improve for you?"
            multiline
            numberOfLines={6}
            maxLength={4000}
            style={{ height: 160, textAlignVertical: "top", paddingTop: 12, fontSize: fontSize.base }}
          />
          <AppText size="xs" muted style={{ marginTop: 6, textAlign: "right" }}>{message.length} / 4000</AppText>

          <View style={{ marginTop: spacing.xl }}>
            <Button testID="feedback-submit" title="Send Feedback" onPress={submit} loading={submitting} />
          </View>
        </ScrollView>
      </KeyboardAvoidingView>
    </SafeAreaView>
  );
}

const styles = StyleSheet.create({
  header: { flexDirection: "row", alignItems: "center", paddingHorizontal: spacing.lg, height: 56 },
  iconBtn: { width: 40, height: 40, alignItems: "center", justifyContent: "center" },
});
