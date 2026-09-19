import { Tabs, usePathname, useRouter } from "expo-router";
import { Platform, View } from "react-native";
import { Ionicons } from "@expo/vector-icons";
import { Gesture, GestureDetector } from "react-native-gesture-handler";
import { runOnJS } from "react-native-reanimated";
import { useTheme } from "@/src/theme";

// Order must match the visible bottom-tab order below.
const TAB_ROUTES = ["/", "/chatly", "/status", "/calls", "/profile"];

export default function TabsLayout() {
  const { colors } = useTheme();
  const router = useRouter();
  const pathname = usePathname();

  const goToIndex = (i: number) => {
    if (i < 0 || i >= TAB_ROUTES.length) return;
    router.navigate(TAB_ROUTES[i] as any);
  };

  // Horizontal-only pan: activeOffsetX makes it trigger on clear horizontal drags,
  // failOffsetY lets vertical scrolls / chat lists win so we never hijack scrolling.
  const swipe = Gesture.Pan()
    .activeOffsetX([-28, 28])
    .failOffsetY([-16, 16])
    .onEnd((e) => {
      "worklet";
      const idx = TAB_ROUTES.indexOf(pathname === "" ? "/" : pathname);
      const cur = idx < 0 ? 0 : idx;
      if (e.translationX <= -60 && Math.abs(e.velocityX) > 120) {
        runOnJS(goToIndex)(cur + 1);
      } else if (e.translationX >= 60 && Math.abs(e.velocityX) > 120) {
        runOnJS(goToIndex)(cur - 1);
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
