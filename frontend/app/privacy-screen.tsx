// Privacy Screen: on Android we set FLAG_SECURE which blurs the app in the recents
// switcher and blocks screenshots system-wide. Toggle is persisted locally.
import { useEffect, useState } from "react";
import { View, Pressable, Switch, StyleSheet, Platform } from "react-native";
import { useRouter } from "expo-router";
import { useSafeAreaInsets } from "react-native-safe-area-context";
import * as ScreenCapture from "expo-screen-capture";
import { storage } from "@/src/utils/storage";
import { useTheme, spacing, radius } from "@/src/theme";
import { AppText, Icon, useToast } from "@/src/ui";

const KEY = "chatly_privacy_screen_on";

export async function applyPrivacyScreen() {
  const on = await storage.getItem<boolean>(KEY, false);
  try {
    if (on) await ScreenCapture.preventScreenCaptureAsync();
    else await ScreenCapture.allowScreenCaptureAsync();
  } catch {}
}

export default function PrivacyScreen() {
  const { colors } = useTheme();
  const insets = useSafeAreaInsets();
  const router = useRouter();
  const toast = useToast();
  const [on, setOn] = useState(false);

  useEffect(() => { storage.getItem<boolean>(KEY, false).then((v) => setOn(!!v)); }, []);
  const toggle = async (v: boolean) => {
    setOn(v); await storage.setItem(KEY, v as any);
    try {
      if (v) await ScreenCapture.preventScreenCaptureAsync();
      else await ScreenCapture.allowScreenCaptureAsync();
      toast.show(v ? "Privacy Screen ON" : "Privacy Screen OFF", "success");
    } catch (e: any) { toast.show("Not supported on this device.", "info"); }
  };

  return (
    <View style={{ flex: 1, backgroundColor: colors.surface }}>
      <View style={{ paddingTop: insets.top + 6, paddingBottom: spacing.sm, paddingHorizontal: spacing.md, flexDirection: "row", alignItems: "center", backgroundColor: colors.card, borderBottomWidth: 1, borderBottomColor: colors.border }}>
        <Pressable onPress={() => router.back()} hitSlop={10}><Icon name="chevron-back" size={26} /></Pressable>
        <AppText weight="heavy" size="xxl" style={{ marginLeft: spacing.sm, flex: 1 }}>Privacy Screen</AppText>
      </View>
      <View style={{ padding: spacing.md }}>
        <View style={{ borderWidth: 1, borderColor: colors.border, borderRadius: radius.md, padding: spacing.md, backgroundColor: colors.card, flexDirection: "row", alignItems: "center" }}>
          <Icon name="eye-off-outline" size={22} color={colors.brandPrimary} />
          <View style={{ flex: 1, marginLeft: 10 }}>
            <AppText weight="bold">Block screenshots & recents preview</AppText>
            <AppText size="xs" muted>
              {Platform.OS === "android"
                ? "Blurs the app in the recent apps switcher and prevents screenshots."
                : "Prevents screenshots and screen recording while Chatly is open."}
            </AppText>
          </View>
          <Switch value={on} onValueChange={toggle} />
        </View>
        <AppText muted size="xs" style={{ marginTop: spacing.md }}>Setting takes effect immediately.</AppText>
      </View>
    </View>
  );
}
const styles = StyleSheet.create({});
