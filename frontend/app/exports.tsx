import { useState } from "react";
import { View, ScrollView, Pressable, TextInput, StyleSheet } from "react-native";
import { useRouter, useLocalSearchParams } from "expo-router";
import { useSafeAreaInsets } from "react-native-safe-area-context";
import * as Print from "expo-print";
import * as Sharing from "expo-sharing";
import { useTheme, spacing, radius, fontSize } from "@/src/theme";
import { AppText, Icon, Button, useToast, Loading } from "@/src/ui";
import { api } from "@/src/api";

type Kind = "pdf" | "doc" | "pptx" | "invoice" | "form" | "spreadsheet";
const KINDS: { key: Kind; label: string; icon: string }[] = [
  { key: "pdf", label: "PDF / Document", icon: "document-text-outline" },
  { key: "doc", label: "Notes", icon: "reader-outline" },
  { key: "pptx", label: "Presentation", icon: "easel-outline" },
  { key: "invoice", label: "Invoice / Quote", icon: "receipt-outline" },
  { key: "form", label: "Form", icon: "list-outline" },
  { key: "spreadsheet", label: "Spreadsheet", icon: "grid-outline" },
];

function jsonToHtml(kind: Kind, content: any, prompt: string): string {
  const title = content?.title || prompt || "Chatly Export";
  const style = "body{font-family:sans-serif;color:#111;padding:24px;} h1,h2,h3{margin:16px 0 8px;} table{border-collapse:collapse;width:100%;} td,th{border:1px solid #ddd;padding:6px;text-align:left;} .slide{page-break-after:always;border-bottom:1px solid #eee;padding:16px 0;}";
  if (kind === "pptx" && content?.slides) {
    const slides = content.slides.map((s: any) => `<div class="slide"><h2>${s.heading || ""}</h2><ul>${(s.bullets || []).map((b: string) => `<li>${b}</li>`).join("")}</ul>${s.notes ? `<p><em>Notes:</em> ${s.notes}</p>` : ""}</div>`).join("");
    return `<html><head><meta charset="utf-8"><style>${style}</style></head><body><h1>${title}</h1>${slides}</body></html>`;
  }
  if (kind === "spreadsheet" && content?.columns) {
    const head = `<tr>${(content.columns || []).map((c: string) => `<th>${c}</th>`).join("")}</tr>`;
    const rows = (content.rows || []).map((r: any[]) => `<tr>${r.map((c: any) => `<td>${c ?? ""}</td>`).join("")}</tr>`).join("");
    return `<html><head><meta charset="utf-8"><style>${style}</style></head><body><h1>${title}</h1>${content.summary ? `<p>${content.summary}</p>` : ""}<table>${head}${rows}</table></body></html>`;
  }
  if (kind === "invoice" && content) {
    const items = (content.items || []).map((i: any) => `<tr><td>${i.description ?? ""}</td><td>${i.qty ?? ""}</td><td>${i.unit_price ?? ""}</td><td>${i.amount ?? ""}</td></tr>`).join("");
    return `<html><head><meta charset="utf-8"><style>${style}</style></head><body><h1>${title}</h1><p><strong>From:</strong> ${content.from || ""}<br><strong>To:</strong> ${content.to || ""}<br><strong>Date:</strong> ${content.date || ""}${content.due_date ? `<br><strong>Due:</strong> ${content.due_date}` : ""}</p><table><tr><th>Description</th><th>Qty</th><th>Unit</th><th>Amount</th></tr>${items}</table><p style="text-align:right;margin-top:12px;">Subtotal: ${content.subtotal ?? ""}<br>Tax: ${content.tax ?? ""}<br><strong>Total: ${content.currency || ""} ${content.total ?? ""}</strong></p>${content.notes ? `<p><em>${content.notes}</em></p>` : ""}</body></html>`;
  }
  if (kind === "form" && content?.fields) {
    const fields = content.fields.map((f: any) => `<p><label><strong>${f.label}${f.required ? " *" : ""}</strong></label><br><span>Type: ${f.type}${f.options ? " (" + f.options.join(", ") + ")" : ""}</span></p>`).join("");
    return `<html><head><meta charset="utf-8"><style>${style}</style></head><body><h1>${title}</h1><p>${content.description || ""}</p>${fields}</body></html>`;
  }
  const md = content?.markdown || "";
  return `<html><head><meta charset="utf-8"><style>${style}</style></head><body><pre style="white-space:pre-wrap;font-family:sans-serif;">${md.replace(/&/g, "&amp;").replace(/</g, "&lt;")}</pre></body></html>`;
}

export default function Exports() {
  const { colors } = useTheme();
  const insets = useSafeAreaInsets();
  const router = useRouter();
  const toast = useToast();
  const { chat_id } = useLocalSearchParams<{ chat_id?: string }>();
  const [kind, setKind] = useState<Kind>("pdf");
  const [prompt, setPrompt] = useState("");
  const [busy, setBusy] = useState(false);
  const [result, setResult] = useState<any | null>(null);

  const build = async () => {
    if (!chat_id) return toast.show("Open this from a chat's menu.", "info");
    setBusy(true); setResult(null);
    try {
      const r = await api.post<any>("/exports", { chat_id, kind, prompt: prompt || undefined });
      setResult(r);
    } catch (e: any) { toast.show(e?.message || "Failed", "error"); }
    finally { setBusy(false); }
  };

  const share = async () => {
    if (!result) return;
    const html = jsonToHtml(kind, result.content, prompt);
    const { uri } = await Print.printToFileAsync({ html });
    await Sharing.shareAsync(uri, { mimeType: "application/pdf", dialogTitle: "Share export", UTI: "com.adobe.pdf" });
  };

  return (
    <View style={{ flex: 1, backgroundColor: colors.surface }}>
      <View style={{ paddingTop: insets.top + 6, paddingBottom: spacing.sm, paddingHorizontal: spacing.md, flexDirection: "row", alignItems: "center", backgroundColor: colors.card, borderBottomWidth: 1, borderBottomColor: colors.border }}>
        <Pressable onPress={() => router.back()} hitSlop={10}><Icon name="chevron-back" size={26} /></Pressable>
        <AppText weight="heavy" size="xxl" style={{ marginLeft: spacing.sm, flex: 1 }}>Export Chat</AppText>
      </View>
      <ScrollView contentContainerStyle={{ padding: spacing.md }}>
        {!chat_id && <AppText muted size="sm">Open a chat, tap ⋯ → Export to fill this in.</AppText>}
        <View style={{ flexDirection: "row", flexWrap: "wrap", gap: 8, marginTop: spacing.sm }}>
          {KINDS.map((k) => (
            <Pressable key={k.key} onPress={() => setKind(k.key)}
              style={{ paddingHorizontal: 12, paddingVertical: 10, borderRadius: radius.md, borderWidth: 1, borderColor: kind === k.key ? colors.brandPrimary : colors.border, backgroundColor: kind === k.key ? colors.brandTertiary : colors.card, flexDirection: "row", alignItems: "center" }}>
              <Icon name={k.icon as any} size={16} color={kind === k.key ? colors.brandPrimary : colors.onSurfaceMuted} />
              <AppText size="sm" weight="semibold" style={{ marginLeft: 6 }}>{k.label}</AppText>
            </Pressable>
          ))}
        </View>
        <TextInput value={prompt} onChangeText={setPrompt} placeholder="Optional focus / instructions" placeholderTextColor={colors.onSurfaceMuted}
          style={{ marginTop: spacing.md, borderWidth: 1, borderColor: colors.border, borderRadius: radius.md, paddingHorizontal: spacing.md, height: 46, color: colors.onSurface, fontSize: fontSize.base }} />
        <Button title="Generate draft" onPress={build} loading={busy} />
        {busy && <Loading />}
        {result && (
          <View style={{ marginTop: spacing.lg, borderWidth: 1, borderColor: colors.border, borderRadius: radius.md, padding: spacing.md, backgroundColor: colors.card }}>
            <AppText weight="bold" size="lg" style={{ marginBottom: 8 }}>Draft ready</AppText>
            <AppText size="sm" muted style={{ marginBottom: 8 }}>Chatly never sends or finalizes — you review then share.</AppText>
            <AppText style={{ fontSize: 12 }} numberOfLines={12}>{typeof result.content === "string" ? result.content : JSON.stringify(result.content, null, 2)}</AppText>
            <Button title="Preview & share as PDF" onPress={share} variant="secondary" />
          </View>
        )}
      </ScrollView>
    </View>
  );
}

const styles = StyleSheet.create({});
