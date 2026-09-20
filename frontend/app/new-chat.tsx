import { useState, useEffect, useCallback } from "react";
import { View, FlatList, Pressable, TextInput, ScrollView } from "react-native";
import { useRouter } from "expo-router";
import { useFocusEffect } from "expo-router";
import { useTheme, spacing, radius, fontSize } from "@/src/theme";
import { AppText, Avatar, Icon, Loading, EmptyState, useToast } from "@/src/ui";
import { StackHeader } from "@/src/Header";
import { api } from "@/src/api";

export default function NewChat() {
  const { colors } = useTheme();
  const router = useRouter();
  const toast = useToast();
  const [q, setQ] = useState("");
  const [results, setResults] = useState<any[]>([]);
  const [contacts, setContacts] = useState<any[]>([]);
  const [requests, setRequests] = useState<any[]>([]);
  const [loading, setLoading] = useState(true);
  const [searching, setSearching] = useState(false);

  const loadBase = useCallback(async () => {
    try {
      const [c, r] = await Promise.all([api.get("/contacts"), api.get("/contacts/requests")]);
      setContacts(c.contacts); setRequests(r.requests);
    } catch {} finally { setLoading(false); }
  }, []);
  useFocusEffect(useCallback(() => { loadBase(); }, [loadBase]));

  useEffect(() => {
    if (q.trim().length < 2) { setResults([]); return; }
    setSearching(true);
    const t = setTimeout(async () => {
      try { const res = await api.get(`/users/search?q=${encodeURIComponent(q.trim())}`); setResults(res.users); }
      catch {} finally { setSearching(false); }
    }, 350);
    return () => clearTimeout(t);
  }, [q]);

  const startChat = async (u: any) => {
    try {
      const res = await api.post<{ chat_id: string }>("/chats", { contact_id: u.user_id });
      router.replace({ pathname: "/chat/[id]", params: { id: res.chat_id, name: u.name } });
    } catch { toast.show("Failed to open chat", "error"); }
  };

  const sendRequest = async (u: any) => {
    try {
      const res = await api.post<{ status: string }>("/contacts/request", { to_id: u.user_id });
      if (res.status === "accepted" || res.status === "already_contacts") { toast.show("Connected", "success"); loadBase(); }
      else toast.show("Request sent", "success");
      setResults((p) => p.map((x) => x.user_id === u.user_id ? { ...x, request_sent: true } : x));
    } catch (e: any) { toast.show(e.message, "error"); }
  };

  const respond = async (r: any, accept: boolean) => {
    try { await api.post("/contacts/respond", { request_id: r.request_id, accept }); loadBase(); toast.show(accept ? "Connected" : "Declined", "success"); }
    catch { toast.show("Failed", "error"); }
  };

  const personRow = (u: any, action: React.ReactNode) => (
    <View key={u.user_id} style={{ flexDirection: "row", alignItems: "center", paddingVertical: spacing.md }}>
      <Avatar name={u.name} uri={u.avatar} size={48} online={u.online} />
      <View style={{ flex: 1, marginLeft: spacing.md }}>
        <AppText weight="semibold" size="lg" numberOfLines={1}>{u.name}</AppText>
        <AppText muted size="base" numberOfLines={1}>@{u.username}</AppText>
      </View>
      {action}
    </View>
  );

  const pill = (label: string, onPress: () => void, testID: string, filled = true) => (
    <Pressable testID={testID} onPress={onPress} style={{ paddingHorizontal: spacing.md, height: 36, borderRadius: radius.pill, alignItems: "center", justifyContent: "center", backgroundColor: filled ? colors.brandPrimary : colors.surfaceTertiary }}>
      <AppText size="base" weight="bold" color={filled ? "#fff" : colors.onSurface}>{label}</AppText>
    </Pressable>
  );

  return (
    <View style={{ flex: 1, backgroundColor: colors.surface }}>
      <StackHeader title="New Chat" />
      <View style={{ padding: spacing.lg, paddingBottom: spacing.sm }}>
        <Pressable testID="new-group-entry" onPress={() => router.push("/new-group")} style={{ flexDirection: "row", alignItems: "center", paddingVertical: spacing.sm }}>
          <View style={{ width: 48, height: 48, borderRadius: 24, backgroundColor: colors.brandTertiary, alignItems: "center", justifyContent: "center" }}>
            <Icon name="people" size={22} color={colors.brandPrimary} />
          </View>
          <AppText weight="bold" size="lg" style={{ marginLeft: spacing.md }}>New Group</AppText>
          <View style={{ flex: 1 }} />
          <Icon name="chevron-forward" size={20} color={colors.onSurfaceMuted} />
        </Pressable>
        <View style={{ flexDirection: "row", alignItems: "center", height: 44, borderRadius: radius.pill, backgroundColor: colors.surfaceTertiary, paddingHorizontal: spacing.md, marginTop: spacing.sm }}>
          <Icon name="search" size={18} color={colors.onSurfaceMuted} />
          <TextInput testID="user-search-input" value={q} onChangeText={setQ} placeholder="Search people by name or @username" placeholderTextColor={colors.onSurfaceMuted} autoCapitalize="none" style={{ flex: 1, marginLeft: 8, color: colors.onSurface, fontSize: fontSize.lg }} />
        </View>
      </View>

      {loading ? <Loading /> : (
        <ScrollView contentContainerStyle={{ paddingHorizontal: spacing.lg, paddingBottom: spacing.xxl }} keyboardShouldPersistTaps="handled">
          {q.trim().length >= 2 ? (
            <>
              <AppText weight="bold" muted size="sm" style={{ marginVertical: spacing.sm }}>SEARCH RESULTS</AppText>
              {searching && results.length === 0 ? <AppText muted>Searching…</AppText> :
                results.length === 0 ? <EmptyState icon="search-outline" title="No people found" /> :
                results.map((u) => personRow(u, u.is_contact || u.is_bot ? pill("Message", () => startChat(u), `msg-${u.user_id}`) : u.request_sent ? pill("Requested", () => {}, `req-${u.user_id}`, false) : pill("Add", () => sendRequest(u), `add-${u.user_id}`)))}
            </>
          ) : (
            <>
              {requests.length > 0 && (
                <>
                  <AppText weight="bold" muted size="sm" style={{ marginVertical: spacing.sm }}>CONTACT REQUESTS</AppText>
                  {requests.map((r) => personRow(r, (
                    <View style={{ flexDirection: "row", gap: spacing.sm }}>
                      {pill("Accept", () => respond(r, true), `accept-${r.request_id}`)}
                      {pill("✕", () => respond(r, false), `reject-${r.request_id}`, false)}
                    </View>
                  )))}
                </>
              )}
              <AppText weight="bold" muted size="sm" style={{ marginVertical: spacing.sm }}>CONTACTS</AppText>
              {contacts.length === 0 ? <EmptyState icon="people-outline" title="No contacts yet" subtitle="Search above to find people and send a request." /> :
                contacts.map((u) => personRow(u, pill("Message", () => startChat(u), `msg-${u.user_id}`)))}
            </>
          )}
        </ScrollView>
      )}
    </View>
  );
}
