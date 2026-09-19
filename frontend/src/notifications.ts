/**
 * Chatly notifications — real FCM (push) + local scheduled reminders via expo-notifications.
 *
 * NATIVE-ONLY runtime: push delivery (foreground/background/terminated) and scheduled
 * local reminders only execute on a real device / the Emergent Publish APK. On web/Expo Go
 * these calls no-op gracefully (guarded) so the preview never crashes.
 */
import { Platform } from "react-native";
import Constants from "expo-constants";
import { api } from "./api";

let Notifications: any = null;
let Device: any = null;
try { Notifications = require("expo-notifications"); } catch {}
try { Device = require("expo-device"); } catch {}

const isNative = Platform.OS !== "web";

export function configureNotificationHandler() {
  if (!Notifications) return;
  try {
    Notifications.setNotificationHandler({
      handleNotification: async () => ({
        shouldShowBanner: true, shouldShowList: true,
        shouldPlaySound: true, shouldSetBadge: true,
      }),
    });
  } catch {}
}

export async function ensureAndroidChannels() {
  if (!Notifications || Platform.OS !== "android") return;
  try {
    await Notifications.setNotificationChannelAsync("messages", {
      name: "Messages", importance: Notifications.AndroidImportance.HIGH,
      vibrationPattern: [0, 250, 250, 250], sound: "default",
    });
    await Notifications.setNotificationChannelAsync("calls", {
      name: "Calls", importance: Notifications.AndroidImportance.MAX,
      vibrationPattern: [0, 500, 500, 500], sound: "default", bypassDnd: false,
    });
    await Notifications.setNotificationChannelAsync("reminders", {
      name: "Reminders", importance: Notifications.AndroidImportance.HIGH,
      vibrationPattern: [0, 250, 250, 250], sound: "default",
    });
  } catch {}
}

/** Request permission + register this device's FCM token with the backend. */
export async function registerPushToken(): Promise<string | null> {
  if (!isNative || !Notifications) return null;
  try {
    if (Device && !Device.isDevice) return null; // emulators may lack FCM
    const existing = await Notifications.getPermissionsAsync();
    let status = existing.status;
    if (status !== "granted") {
      const req = await Notifications.requestPermissionsAsync();
      status = req.status;
    }
    if (status !== "granted") return null;
    await ensureAndroidChannels();
    const projectId =
      Constants?.expoConfig?.extra?.eas?.projectId ||
      (Constants as any)?.easConfig?.projectId;
    // Native FCM device token (works with @react-native-firebase or a dev/APK build).
    let token: string | null = null;
    try {
      const dev = await Notifications.getDevicePushTokenAsync();
      token = dev?.data || null;
    } catch {}
    if (!token && projectId) {
      try {
        const expoTok = await Notifications.getExpoPushTokenAsync({ projectId });
        token = expoTok?.data || null;
      } catch {}
    }
    if (token) {
      await api.post("/fcm/register", { token, platform: Platform.OS });
    }
    return token;
  } catch (e) {
    console.warn("[push] register failed", e);
    return null;
  }
}

export async function unregisterPushToken(token?: string | null) {
  if (!token) return;
  try { await api.post("/fcm/unregister", { token }); } catch {}
}

/** Route a notification tap to the correct screen. Returns a route or null. */
export function routeFromNotificationData(data: any): { pathname: string; params?: any } | null {
  if (!data) return null;
  if (data.type === "chat_message" && data.chat_id)
    return { pathname: "/chat/[id]", params: { id: data.chat_id } };
  if (data.type === "reminder" && data.reminder_id)
    return { pathname: "/reminders" };
  return null;
}

// ---------------- Local scheduled reminders (offline-capable) ----------------

export async function scheduleLocalReminder(id: string, title: string, body: string, when: Date): Promise<string | null> {
  if (!isNative || !Notifications) return null;
  try {
    await ensureAndroidChannels();
    const trigger = when.getTime() > Date.now() ? { date: when } : null;
    const notifId = await Notifications.scheduleNotificationAsync({
      content: { title, body, sound: "default", data: { type: "reminder", reminder_id: id }, channelId: "reminders" },
      trigger,
    });
    return notifId;
  } catch (e) {
    console.warn("[reminder] schedule failed", e);
    return null;
  }
}

export async function cancelLocalReminder(notifId?: string | null) {
  if (!Notifications || !notifId) return;
  try { await Notifications.cancelScheduledNotificationAsync(notifId); } catch {}
}
