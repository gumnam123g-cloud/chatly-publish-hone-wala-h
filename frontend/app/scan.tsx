import { useState, useRef } from "react";
import { View, Pressable, StyleSheet, Platform, TextInput } from "react-native";
import { useRouter } from "expo-router";
import { CameraView, useCameraPermissions } from "expo-camera";
import { useTheme, spacing, radius, fontSize } from "@/src/theme";
import { AppText, Icon, Button, useToast } from "@/src/ui";
import { StackHeader } from "@/src/Header";
import { api } from "@/src/api";

export default function ScanScreen() {
  const { colors } = useTheme();
  const router = useRouter();
  const toast = useToast();
  const [permission, requestPermission] = useCameraPermissions();
  const [resolving, setResolving] = useState(false);
  const [manual, setManual] = useState("");
  const handled = useRef(false);

  const extractToken = (raw: string) => {
    let code = (raw || "").trim();
    try { code = decodeURIComponent(code); } catch {}
    if (code.includes("code=")) {
      const m = code.match(/[?&]code=([^&]+)/);
      if (m) code = decodeURIComponent(m[1]);
    }
    if (code.includes("chatly://user/")) code = code.split("chatly://user/").pop() || code;
    else if (code.includes("/user/")) code = code.split("/user/").pop() || code;
    return code.replace(/^\/+|\/+$/g, "").split("?")[0].split("/")[0].trim();
  };

  const resolve = async (raw: string) => {
    if (resolving) return;
    const token = extractToken(raw);
    if (!token) { toast.show("Invalid QR code", "error"); handled.current = false; return; }
    setResolving(true);
    try {
      const res = await api.get(`/users/by-qr?code=${encodeURIComponent(token)}`);
      router.replace({ pathname: "/user/[id]", params: { id: res.user.user_id } });
    } catch (e: any) {
      toast.show(e.message || "Invalid QR code", "error");
      handled.current = false;
    } finally {
      setResolving(false);
    }
  };

  const onScan = ({ data }: { data: string }) => {
    if (handled.current) return;
    handled.current = true;
    resolve(data);
  };

  const isWeb = Platform.OS === "web";

  return (
    <View style={{ flex: 1, backgroundColor: "#000" }}>
      <StackHeader title="Scan QR Code" />
      {isWeb ? (
        <View style={{ flex: 1, backgroundColor: colors.surface, padding: spacing.xl, justifyContent: "center" }}>
          <Icon name="qr-code-outline" size={48} color={colors.brandPrimary} />
          <AppText weight="bold" size="xl" style={{ marginTop: spacing.md }}>Camera scanning is on mobile</AppText>
          <AppText muted style={{ marginTop: 6, marginBottom: spacing.lg }}>Open Chatly on your phone to scan, or paste a code below.</AppText>
          <View style={{ flexDirection: "row", alignItems: "center", backgroundColor: colors.surfaceTertiary, borderRadius: radius.md, paddingHorizontal: spacing.md, height: 52, marginBottom: spacing.md }}>
            <TextInput testID="manual-code" value={manual} onChangeText={setManual} placeholder="Paste code e.g. CHATLY-xxxx" placeholderTextColor={colors.onSurfaceMuted} autoCapitalize="none" style={{ flex: 1, color: colors.onSurface, fontSize: fontSize.lg }} />
          </View>
          <Button testID="resolve-manual" title="Find User" onPress={() => manual.trim() && resolve(manual)} loading={resolving} />
        </View>
      ) : !permission ? (
        <View style={{ flex: 1 }} />
      ) : !permission.granted ? (
        <View style={{ flex: 1, backgroundColor: colors.surface, padding: spacing.xl, justifyContent: "center", alignItems: "center" }}>
          <Icon name="camera-outline" size={48} color={colors.brandPrimary} />
          <AppText weight="bold" size="xl" center style={{ marginTop: spacing.md }}>Camera access needed</AppText>
          <AppText muted center style={{ marginTop: 6, marginBottom: spacing.lg }}>We use your camera only to scan Chatly QR codes.</AppText>
          <Button testID="grant-camera" title="Allow Camera" onPress={requestPermission} />
        </View>
      ) : (
        <View style={{ flex: 1 }}>
          <CameraView
            style={StyleSheet.absoluteFill}
            facing="back"
            barcodeScannerSettings={{ barcodeTypes: ["qr"] }}
            onBarcodeScanned={onScan}
          />
          <View style={styles.overlay} pointerEvents="none">
            <View style={[styles.frame, { borderColor: colors.brandPrimary }]} />
            <AppText color="#fff" weight="bold" style={{ marginTop: spacing.lg }}>{resolving ? "Looking up…" : "Point at a Chatly QR code"}</AppText>
          </View>
        </View>
      )}
    </View>
  );
}

const styles = StyleSheet.create({
  overlay: { ...StyleSheet.absoluteFillObject, alignItems: "center", justifyContent: "center" },
  frame: { width: 240, height: 240, borderWidth: 3, borderRadius: 24 },
});
