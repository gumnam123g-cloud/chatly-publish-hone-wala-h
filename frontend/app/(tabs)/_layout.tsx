import { Tabs, usePathname, useRouter } from "expo-router";
import { Platform, View } from "react-native";
import { Ionicons } from "@expo/vector-icons";
import { Gesture, GestureDetector } from "react-native-gesture-handler";
import { runOnJS } from "react-native-reanimated";
import { useTheme } from "@/src/theme";

// Bottom-tab visual order is defined by the <Tabs.Screen> children below.
// Swipe navigation is enabled ONLY between these four tabs, in this exact
// cyclic order:
//   Chats  -> Status  -> Chatly  -> Profile  -> Chats  (left swipe)
//   reverse for right swipe.
// The Calls tab is intentionally excluded from swipe navigation, but the user
// can still reach Calls by tapping the bottom-tab icon.
const SWIPE_ORDER = ["/", "/status", "/chatly", "/profile"];

export default function TabsLayout() {
  const { colors } = useTheme();
  const router = useRouter();
  const pathname = usePathname();

  const goToRoute = (route: string) => {
    router.navigate(route as any);
  };

  // Horizontal-only pan: activeOffsetX makes it trigger on clear horizontal drags,
  // failOffsetY lets vertical scrolls / chat lists win so we never hijack scrolling.
  const swipe = Gesture.Pan()
    .activeOffsetX([-28, 28])
    .failOffsetY([-16, 16])
    .onEnd((e) => {
      "worklet";
      const current = pathname === "" ? "/" : pathname;
      const idx = SWIPE_ORDER.indexOf(current);
      // If the user is on a tab outside the swipe cycle (e.g. /calls), do not
      // hijack their gesture at all.
      if (idx < 0) return;
      const n = SWIPE_ORDER.length;
      if (e.translationX <= -60 && Math.abs(e.velocityX) > 120) {
        // Left swipe: advance forward through the cycle (wraps to start).
        runOnJS(goToRoute)(SWIPE_ORDER[(idx + 1) % n]);
      } else if (e.translationX >= 60 && Math.abs(e.velocityX) > 120) {
        // Right swipe: step backward through the cycle (wraps to end).
        runOnJS(goToRoute)(SWIPE_ORDER[(idx - 1 + n) % n]);
      }
    });

  return (
    <GestureDetector gesture={swipe}>
      <View style={{ flex: 1 }}>
        <Tabs
          screenOptions={{
            headerShown: false,
            tabBarActiveTintColor: colors.brandPrimary,
            tabBarInactiveTintColor: colors.onSurfaceMuted,
            tabBarStyle: {
              backgroundColor: colors.card,
              borderTopColor: colors.border,
              ...(Platform.OS === "web" ? { height: 64 } : {}),
            },
            tabBarItemStyle: { alignSelf: "center" },
            tabBarLabelStyle: { fontSize: 11, fontWeight: "600" },
          }}
        >
          <Tabs.Screen name="index" options={{ title: "Chats", tabBarIcon: ({ color, size }) => <Ionicons name="chatbubbles" size={size} color={color} /> }} />
          <Tabs.Screen name="chatly" options={{ title: "Chatly", tabBarIcon: ({ color, size }) => <Ionicons name="sparkles" size={size} color={color} /> }} />
          <Tabs.Screen name="status" options={{ title: "Status", tabBarIcon: ({ color, size }) => <Ionicons name="radio" size={size} color={color} /> }} />
          <Tabs.Screen name="calls" options={{ title: "Calls", tabBarIcon: ({ color, size }) => <Ionicons name="call" size={size} color={color} /> }} />
          <Tabs.Screen name="profile" options={{ title: "Profile", tabBarIcon: ({ color, size }) => <Ionicons name="person" size={size} color={color} /> }} />
        </Tabs>
      </View>
    </GestureDetector>
  );
}
