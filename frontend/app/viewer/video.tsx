/**
 * In-app fullscreen video player using expo-video. Play/pause/seek/fullscreen
 * are provided by the native controls. We cache the downloaded video on device
 * so previously played videos work offline.
 */
import React, { useEffect, useState } from "react";
import { View, Pressable, StyleSheet, StatusBar, Platform, ActivityIndicator } from "react-native";
import { Stack, useLocalSearchParams, router } from "expo-router";
import { VideoView, useVideoPlayer } from "expo-video";
import { Ionicons } from "@expo/vector-icons";
import { AppText } from "@/src/ui";
import { ensureCached } from "@/src/mediaCache";
import { track } from "@/src/analytics";

export default function VideoViewer() {
  const params = useLocalSearchParams<{ uri: string; cacheKey?: string; title?: string; ext?: string }>();
  const [source, setSource] = useState<string | null>(null);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    track("media_viewed_video");
    (async () => {
      try {
        setLoading(true);
        const uri = String(params.uri || "");
        const key = String(params.cacheKey || uri);
        const ext = String(params.ext || ".mp4");
        const cached = await ensureCached(uri, key, ext);
        setSource(cached);
      } catch {
        setError("Couldn't load this video.");
      } finally {
        setLoading(false);
      }
    })();
  }, [params.uri, params.cacheKey, params.ext]);

  const player = useVideoPlayer(source || "", (p) => {
    p.loop = false;
    p.muted = false;
    try { p.play(); } catch {}
  });

  return (
    <View style={{ flex: 1, backgroundColor: "#000" }}>
      <Stack.Screen options={{ headerShown: false }} />
      <StatusBar barStyle="light-content" backgroundColor="#000" />
      <View style={styles.header}>
        <Pressable testID="video-viewer-close" onPress={() => router.back()} hitSlop={12} style={styles.iconBtn}>
          <Ionicons name="close" size={26} color="#fff" />
        </Pressable>
        <AppText color="#fff" weight="semibold" numberOfLines={1} style={{ flex: 1, marginLeft: 12 }}>
          {String(params.title || "Video")}
        </AppText>
      </View>
      {loading && !source ? (
        <View style={{ flex: 1, alignItems: "center", justifyContent: "center" }}>
          <ActivityIndicator color="#fff" size="large" />
          <AppText color="#fff" style={{ marginTop: 12 }}>Preparing video…</AppText>
        </View>
      ) : error ? (
        <View style={{ flex: 1, alignItems: "center", justifyContent: "center" }}>
          <AppText color="#fff">{error}</AppText>
        </View>
      ) : (
        <VideoView
          player={player}
          style={{ flex: 1 }}
          nativeControls
          allowsFullscreen
          allowsPictureInPicture
          contentFit="contain"
        />
      )}
    </View>
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
