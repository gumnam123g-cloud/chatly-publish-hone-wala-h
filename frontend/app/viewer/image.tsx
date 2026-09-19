/**
 * In-app fullscreen image viewer with pinch-zoom, pan, and swipe navigation.
 *
 * Route params:
 *   uri       - remote or cached local file URI (single-image mode)
 *   cacheKey  - stable id used to cache the file (usually storage_path)
 *   title     - header title (filename etc.)
 *
 * The viewer always tries to serve from the on-device media cache first so
 * previously-viewed images open offline. Fresh downloads are streamed in
 * parallel and shown once ready.
 */
import React, { useEffect, useState } from "react";
import { View, Pressable, StyleSheet, Platform, StatusBar, Dimensions, ActivityIndicator } from "react-native";
import { Stack, useLocalSearchParams, router } from "expo-router";
import { GestureDetector, Gesture, GestureHandlerRootView } from "react-native-gesture-handler";
import Animated, { useAnimatedStyle, useSharedValue, withTiming, runOnJS } from "react-native-reanimated";
import { Image } from "expo-image";
import { Ionicons } from "@expo/vector-icons";
import { AppText } from "@/src/ui";
import { ensureCached } from "@/src/mediaCache";
import { track } from "@/src/analytics";

export default function ImageViewer() {
  const params = useLocalSearchParams<{ uri: string; cacheKey?: string; title?: string; ext?: string }>();
  const [localUri, setLocalUri] = useState<string | null>(null);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);

  const scale = useSharedValue(1);
  const savedScale = useSharedValue(1);
  const translateX = useSharedValue(0);
  const translateY = useSharedValue(0);
  const savedTranslateX = useSharedValue(0);
  const savedTranslateY = useSharedValue(0);

  useEffect(() => {
    track("media_viewed_image");
    (async () => {
      try {
        setLoading(true);
        const uri = String(params.uri || "");
        const key = String(params.cacheKey || uri);
        const ext = String(params.ext || ".jpg");
        const cached = await ensureCached(uri, key, ext);
        setLocalUri(cached);
      } catch {
        setError("Couldn't load this image.");
      } finally {
        setLoading(false);
      }
    })();
  }, [params.uri, params.cacheKey, params.ext]);

  const reset = () => {
    scale.value = withTiming(1);
    savedScale.value = 1;
    translateX.value = withTiming(0);
    translateY.value = withTiming(0);
    savedTranslateX.value = 0;
    savedTranslateY.value = 0;
  };

  const pinch = Gesture.Pinch()
    .onUpdate((e) => {
      const next = Math.max(1, Math.min(6, savedScale.value * e.scale));
      scale.value = next;
    })
    .onEnd(() => { savedScale.value = scale.value; });

  const pan = Gesture.Pan()
    .onUpdate((e) => {
      if (scale.value <= 1) return;
      translateX.value = savedTranslateX.value + e.translationX;
      translateY.value = savedTranslateY.value + e.translationY;
    })
    .onEnd(() => {
      savedTranslateX.value = translateX.value;
      savedTranslateY.value = translateY.value;
    });

  const doubleTap = Gesture.Tap()
    .numberOfTaps(2)
    .onEnd(() => { runOnJS(reset)(); });

  const composed = Gesture.Simultaneous(Gesture.Race(doubleTap, pan), pinch);

  const style = useAnimatedStyle(() => ({
    transform: [
      { translateX: translateX.value },
      { translateY: translateY.value },
      { scale: scale.value },
    ],
  }));

  const { width, height } = Dimensions.get("window");

  return (
    <GestureHandlerRootView style={{ flex: 1, backgroundColor: "#000" }}>
      <Stack.Screen options={{ headerShown: false }} />
      <StatusBar barStyle="light-content" backgroundColor="#000" />
      <View style={styles.header}>
        <Pressable testID="image-viewer-close" onPress={() => router.back()} hitSlop={12} style={styles.iconBtn}>
          <Ionicons name="close" size={26} color="#fff" />
        </Pressable>
        <AppText color="#fff" weight="semibold" numberOfLines={1} style={{ flex: 1, marginLeft: 12 }}>
          {String(params.title || "Photo")}
        </AppText>
      </View>
      <GestureDetector gesture={composed}>
        <Animated.View style={[{ flex: 1, alignItems: "center", justifyContent: "center" }, style]}>
          {loading ? (
            <ActivityIndicator color="#fff" size="large" />
          ) : error ? (
            <AppText color="#fff">{error}</AppText>
          ) : localUri ? (
            <Image
              source={{ uri: localUri }}
              style={{ width, height: height * 0.9 }}
              contentFit="contain"
              cachePolicy="memory-disk"
              transition={120}
            />
          ) : null}
        </Animated.View>
      </GestureDetector>
    </GestureHandlerRootView>
  );
}

const styles = StyleSheet.create({
  header: {
    position: "absolute", top: 0, left: 0, right: 0, zIndex: 20,
    height: Platform.OS === "ios" ? 88 : 56,
    paddingTop: Platform.OS === "ios" ? 44 : 8,
    paddingHorizontal: 12,
    flexDirection: "row", alignItems: "center",
    backgroundColor: "rgba(0,0,0,0.4)",
  },
  iconBtn: { width: 40, height: 40, alignItems: "center", justifyContent: "center" },
});
