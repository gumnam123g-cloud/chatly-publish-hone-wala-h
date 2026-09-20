import { useState } from "react";
import { View, ScrollView, Pressable, StyleSheet, ActivityIndicator, Image, TextInput } from "react-native";
import { useRouter } from "expo-router";
import { useSafeAreaInsets } from "react-native-safe-area-context";
import * as ImagePicker from "expo-image-picker";
import * as ImageManipulator from "expo-image-manipulator";
import { useTheme, spacing, radius, fontSize } from "@/src/theme";
import { AppText, Icon, Button, useToast } from "@/src/ui";
import { API_ORIGIN } from "@/src/api";
import { useAuth } from "@/src/auth";

type Mode = "screenshot" | "receipt" | "business_card" | "document";
type Result = { kind: Mode; data: any; text: string };

const MODES: { key: Mode; label: string; icon: string; desc: string }[] = [
  { key: "screenshot", label: "Screenshot Assistant", icon: "phone-portrait-outline", desc: "Read a screenshot, summarize & suggest actions." },
  { key: "receipt", label: "Receipt Scanner", icon: "receipt-outline", desc: "Extract merchant, items, tax & total." },
  { key: "business_card", label: "Business Card", icon: "id-card-outline", desc: "Extract contact info & save (with confirm)." },
  { key: "document", label: "Document Scanner", icon: "document-outline", desc: "Multi-page scan → enhance → save." },
];

export default function ScannerHub() {
  const { colors } = useTheme();
  const insets = useSafeAreaInsets();
  const router = useRouter();
  const toast = useToast();
  const { token } = useAuth();
  const [mode, setMode] = useState<Mode>("screenshot");
  const [images, setImages] = useState<string[]>([]);
  const [busy, setBusy] = useState(false);
  const [result, setResult] = useState<Result | null>(null);
  const [docName, setDocName] = useState("Scanned Document");

  const pick = async () => {
    const res = await ImagePicker.launchImageLibraryAsync({
      mediaTypes: ImagePicker.MediaTypeOptions?.Images ?? undefined as any,
      quality: 0.9, allowsMultipleSelection: mode === "document",
    });
    if (res.canceled) return;
    // Enhance for readability
    const out: string[] = [];
    for (const a of res.assets || []) {
      const m = await ImageManipulator.manipulateAsync(a.uri,
        [{ resize: { width: 1600 } }],
        { compress: 0.85, format: ImageManipulator.SaveFormat.JPEG });
      out.push(m.uri);
    }
    setImages(mode === "document" ? [...images, ...out] : out);
    setResult(null);
  };
  const shoot = async () => {
    const cam = await ImagePicker.requestCameraPermissionsAsync();
    if (!cam.granted) return toast.show("Camera permission is needed for scanning.", "info");
    const res = await ImagePicker.launchCameraAsync({ quality: 0.9 });
    if (res.canceled) return;
    const m = await ImageManipulator.manipulateAsync(res.assets[0].uri,
      [{ resize: { width: 1600 } }],
      { compress: 0.85, format: ImageManipulator.SaveFormat.JPEG });
    setImages(mode === "document" ? [...images, m.uri] : [m.uri]);
    setResult(null);
  };

  const analyzeOne = async (uri: string) => {
    const form = new FormData();
    const filename = uri.split("/").pop() || "image.jpg";
    form.append("file", { uri, name: filename, type: "image/jpeg" } as any);
    form.append("kind", mode === "document" ? "generic" : mode);
    const res = await fetch(`${API_ORIGIN}/api/ai/vision`, {
      method: "POST", headers: { Authorization: `Bearer ${token}` }, body: form,
    });
    if (!res.ok) throw new Error(`HTTP ${res.status}`);
    return await res.json();
  };

  const analyze = async () => {
    if (!images.length) return;
    setBusy(true);
    try {
      if (mode === "document") {
        // Save the document as a multi-page scan (client-side, no analysis).
        // Upload each page via /api/files then persist a doc record.
        const uploaded: string[] = [];
        for (const uri of images) {
          const f = new FormData();
          const filename = uri.split("/").pop() || "page.jpg";
          f.append("file", { uri, name: filename, type: "image/jpeg" } as any);
          const r = await fetch(`${API_ORIGIN}/api/files`, {
            method: "POST", headers: { Authorization: `Bearer ${token}` }, body: f,
          });
          if (!r.ok) throw new Error(`Upload failed ${r.status}`);
          const j = await r.json();
          uploaded.push(j.url || j.storage_path || j.path);
        }
        const r = await fetch(`${API_ORIGIN}/api/ai/document-scan/save`, {
          method: "POST",
          headers: { Authorization: `Bearer ${token}`, "Content-Type": "application/json" },
          body: JSON.stringify({ pages: uploaded, name: docName || "Scanned Document" }),
        });
        if (!r.ok) throw new Error(`HTTP ${r.status}`);
        toast.show("Document saved", "success");
        setImages([]); setResult(null);
      } else {
        const r = await analyzeOne(images[0]);
        setResult(r as Result);
      }
    } catch (e: any) { toast.show(e?.message || "Analysis failed", "error"); }
    finally { setBusy(false); }
  };

  const saveContact = async () => {
    // For business card we just show extracted fields — the user copies/edits then adds contact.
    toast.show("Copy fields into New Chat → Add Contact.", "info");
  };

  return (
    <View style={{ flex: 1, backgroundColor: colors.surface }}>
      <View style={{ paddingTop: insets.top + 6, paddingBottom: spacing.sm, paddingHorizontal: spacing.md, flexDirection: "row", alignItems: "center", backgroundColor: colors.card, borderBottomWidth: 1, borderBottomColor: colors.border }}>
        <Pressable onPress={() => router.back()} hitSlop={10}><Icon name="chevron-back" size={26} /></Pressable>
        <AppText weight="heavy" size="xxl" style={{ marginLeft: spacing.sm, flex: 1 }}>Scanners</AppText>
      </View>
      <ScrollView contentContainerStyle={{ padding: spacing.md, paddingBottom: spacing.xxl }}>
        <View style={{ gap: 8 }}>
          {MODES.map((m) => (
            <Pressable key={m.key} onPress={() => { setMode(m.key); setImages([]); setResult(null); }}
              style={{ padding: spacing.md, borderWidth: 1, borderColor: mode === m.key ? colors.brandPrimary : colors.border, borderRadius: radius.md, backgroundColor: mode === m.key ? colors.brandTertiary : colors.card, flexDirection: "row", alignItems: "center" }}>
              <Icon name={m.icon as any} size={22} color={mode === m.key ? colors.brandPrimary : colors.onSurfaceMuted} />
              <View style={{ flex: 1, marginLeft: 10 }}>
                <AppText weight="bold">{m.label}</AppText>
                <AppText size="xs" muted>{m.desc}</AppText>
              </View>
              {mode === m.key && <Icon name="checkmark-circle" size={20} color={colors.brandPrimary} />}
            </Pressable>
          ))}
        </View>

        <View style={{ flexDirection: "row", gap: 8, marginTop: spacing.lg }}>
          <Pressable onPress={pick} style={{ flex: 1, height: 44, borderRadius: radius.md, borderWidth: 1, borderColor: colors.border, alignItems: "center", justifyContent: "center", flexDirection: "row" }}>
            <Icon name="images-outline" size={18} /><AppText style={{ marginLeft: 6 }}>Pick image</AppText>
          </Pressable>
          <Pressable onPress={shoot} style={{ flex: 1, height: 44, borderRadius: radius.md, borderWidth: 1, borderColor: colors.border, alignItems: "center", justifyContent: "center", flexDirection: "row" }}>
            <Icon name="camera-outline" size={18} /><AppText style={{ marginLeft: 6 }}>Camera</AppText>
          </Pressable>
        </View>

        {mode === "document" && (
          <TextInput value={docName} onChangeText={setDocName} placeholder="Document name" placeholderTextColor={colors.onSurfaceMuted}
            style={{ marginTop: spacing.md, borderWidth: 1, borderColor: colors.border, borderRadius: radius.md, paddingHorizontal: spacing.md, height: 44, color: colors.onSurface, fontSize: fontSize.base }} />
        )}

        <View style={{ marginTop: spacing.md, flexDirection: "row", flexWrap: "wrap", gap: 8 }}>
          {images.map((u) => (
            <View key={u} style={{ width: 80, height: 100, borderRadius: radius.sm, overflow: "hidden", position: "relative" }}>
              <Image source={{ uri: u }} style={{ width: "100%", height: "100%" }} />
              <Pressable onPress={() => setImages((p) => p.filter((x) => x !== u))} style={{ position: "absolute", top: 4, right: 4, backgroundColor: "rgba(0,0,0,0.5)", borderRadius: 12, padding: 2 }}>
                <Icon name="close" size={14} color="#fff" />
              </Pressable>
            </View>
          ))}
        </View>

        {images.length > 0 && (
          <Button title={mode === "document" ? `Save ${images.length} page${images.length > 1 ? "s" : ""}` : "Analyze with Sarvam Vision"} onPress={analyze} loading={busy} />
        )}

        {result && (
          <View style={{ marginTop: spacing.lg, backgroundColor: colors.card, borderWidth: 1, borderColor: colors.border, borderRadius: radius.md, padding: spacing.md }}>
            <AppText weight="bold" size="lg" style={{ textTransform: "capitalize" }}>{result.kind.replace("_", " ")} result</AppText>
            {result.data ? (
              <AppText style={{ marginTop: 8, fontFamily: "SpaceMono" as any }}>{JSON.stringify(result.data, null, 2)}</AppText>
            ) : (
              <AppText style={{ marginTop: 8 }}>{result.text}</AppText>
            )}
            {result.kind === "business_card" && result.data && (
              <Button title="Add to contacts (confirm)" onPress={saveContact} variant="secondary" />
            )}
          </View>
        )}
      </ScrollView>
      {busy && <View style={StyleSheet.absoluteFill as any} pointerEvents="none">
        <View style={{ flex: 1, alignItems: "center", justifyContent: "center" }}>
          <ActivityIndicator size="large" color={colors.brandPrimary} />
        </View>
      </View>}
    </View>
  );
}
