import { Stack, useRouter } from "expo-router";
import * as SplashScreen from "expo-splash-screen";
import { useEffect } from "react";
import { LogBox } from "react-native";
import { GestureHandlerRootView } from "react-native-gesture-handler";
import { SafeAreaProvider } from "react-native-safe-area-context";
import { KeyboardProvider } from "react-native-keyboard-controller";
import { StatusBar } from "expo-status-bar";

import { useIconFonts } from "@/src/hooks/use-icon-fonts";
import { ThemeProvider, useTheme } from "@/src/theme";
import { AuthProvider } from "@/src/auth";
import { WsProvider } from "@/src/ws";
import { ToastProvider } from "@/src/ui";
import { CallProvider } from "@/src/calls";
import { ErrorBoundary } from "@/src/ErrorBoundary";
import { installGlobalErrorHandlers } from "@/src/globalErrors";
import { configureNotificationHandler, ensureAndroidChannels, routeFromNotificationData } from "@/src/notifications";
import { track } from "@/src/analytics";

LogBox.ignoreAllLogs(true);
SplashScreen.preventAutoHideAsync();
installGlobalErrorHandlers();
configureNotificationHandler();

function ThemedStatusBar() {
  const { isDark } = useTheme();
  return <StatusBar style={isDark ? "light" : "dark"} />;
}

// Routes a tapped push notification to the right screen (foreground/background/cold-start).
function NotificationRouter() {
  const router = useRouter();
  useEffect(() => {
    let Notifications: any = null;
    try { Notifications = require("expo-notifications"); } catch { return; }
    ensureAndroidChannels();
    const handle = (resp: any) => {
      const data = resp?.notification?.request?.content?.data;
      const route = routeFromNotificationData(data);
      if (route) { try { router.push(route as any); } catch {} }
    };
    const sub = Notifications.addNotificationResponseReceivedListener(handle);
    Notifications.getLastNotificationResponseAsync?.().then((r: any) => { if (r) handle(r); }).catch(() => {});
    return () => { try { sub.remove(); } catch {} };
  }, [router]);
  return null;
}

export default function RootLayout() {
  const [loaded, error] = useIconFonts();

  useEffect(() => {
    if (loaded || error) SplashScreen.hideAsync();
  }, [loaded, error]);

  // Fire once per cold-start so we can measure launches. Deferred so it doesn't
  // race the auth hydrate (no /analytics/event call before we have a session).
  useEffect(() => {
    const t = setTimeout(() => { try { track("app_open"); } catch {} }, 2500);
    return () => clearTimeout(t);
  }, []);

  if (!loaded && !error) return null;

  return (
    <GestureHandlerRootView style={{ flex: 1 }}>
      <ErrorBoundary>
        <SafeAreaProvider>
          <KeyboardProvider>
            <ThemeProvider>
              <AuthProvider>
                <WsProvider>
                  <ToastProvider>
                    <CallProvider>
                      <ThemedStatusBar />
                      <NotificationRouter />
                      <Stack screenOptions={{ headerShown: false, animation: "slide_from_right" }}>
                        <Stack.Screen name="index" />
                        <Stack.Screen name="(auth)" />
                        <Stack.Screen name="(tabs)" />
                        <Stack.Screen name="chat/[id]" />
                        <Stack.Screen name="assistant" options={{ presentation: "card" }} />
                      </Stack>
                    </CallProvider>
                  </ToastProvider>
                </WsProvider>
              </AuthProvider>
            </ThemeProvider>
          </KeyboardProvider>
        </SafeAreaProvider>
      </ErrorBoundary>
    </GestureHandlerRootView>
  );
}
