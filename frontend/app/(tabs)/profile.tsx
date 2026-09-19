import { useState, useCallback, useEffect } from "react";
import { View, ScrollView, Pressable, Modal, StyleSheet, Linking, Keyboard, Platform } from "react-native";
import { useRouter } from "expo-router";
import { useFocusEffect } from "@react-navigation/native";
import { useSafeAreaInsets } from "react-native-safe-area-context";
import { useTheme, spacing, radius } from "@/src/theme";
import { AppText, Avatar, Icon, Card, SettingRow, Input, Button, useToast } from "@/src/ui";
import { useAuth } from "@/src/auth";
import { api } from "@/src/api";
import { pickAvatar } from "@/src/upload";
import { SUPPORT_EMAIL } from "@/src/LegalDoc";

export default function Profile() {
  const { colors, mode, setMode } = useTheme();
  const insets = useSafeAreaInsets();
  const router = useRouter();
  const toast = useToast();
  const { user, logout, setUser } = useAuth();
  const [editOpen, setEditOpen] = useState(false);
  const [name, setName] = useState(user?.name || "");
  const [bio, setBio] = useState(user?.bio || "");
  const [nameErr, setNameErr] = useState("");
  const [saving, setSaving] = useState(false);
  const [confirmDelete, setConfirmDelete] = useState(false);
  const [photoMenu, setPhotoMenu] = useState(false);
  const [photoBusy, setPhotoBusy] = useState(false);
  const [reqCount, setReqCount] = useState(0);
  // Component-level keyboard handling for the Edit Profile bottom sheet only.
  // Raises the bottom-anchored sheet above the keyboard so the focused input and
  // Save button stay visible; returns to original position when the keyboard hides.
  const [editKbOffset, setEditKbOffset] = useState(0);
  useEffect(() => {
    const showEvt = Platform.OS === "ios" ? "keyboardWillShow" : "keyboardDidShow";
    const hideEvt = Platform.OS === "ios" ? "keyboardWillHide" : "keyboardDidHide";
    const s = Keyboard.addListener(showEvt, (e) => setEditKbOffset(e?.endCoordinates?.height ?? 0));
    const h = Keyboard.addListener(hideEvt, () => setEditKbOffset(0));
    return () => { s.remove(); h.remove(); };
  }, []);

  const openEdit = () => {
    setName(user?.name || "");
    setBio(user?.bio || "");
    setNameErr("");
    setEditOpen(true);
  };
  const closeEdit = () => {
    if (saving) return; // don't dismiss mid-save
    Keyboard.dismiss();
    setEditOpen(false);
  };

  useFocusEffect(useCallback(() => {
    api.get("/contacts/requests").then((r) => setReqCount(r.requests?.length || 0)).catch(() => {});
  }, []));

  const changePhoto = async () => {
    setPhotoMenu(false);
    try {
      const dataUri = await pickAvatar();
      if (!dataUri) return;
      setPhotoBusy(true);
      const res = await api.put<{ user: any }>("/auth/me", { avatar: dataUri });
      setUser(res.user);
      toast.show("Photo updated", "success");
    } catch (e: any) {
      if (String(e.message).includes("permission")) toast.show("Photo permission needed", "error");
      else toast.show("Failed to update photo", "error");
    } finally { setPhotoBusy(false); }
  };

  const removePhoto = async () => {
    setPhotoMenu(false);
    setPhotoBusy(true);
    try {
      const res = await api.put<{ user: any }>("/auth/me", { avatar: "" });
      setUser(res.user);
      toast.show("Photo removed", "success");
    } catch { toast.show("Failed", "error"); }
    finally { setPhotoBusy(false); }
  };

  const saveProfile = async () => {
    if (saving) return; // guard against double taps
    const trimmedName = name.trim();
    const trimmedBio = bio.trim();
    if (!trimmedName) { setNameErr("Please enter your name."); return; }
    if (trimmedName.length > 60) { setNameErr("Name is too long (max 60 characters)."); return; }
    if (trimmedBio.length > 200) { setNameErr("Bio is too long (max 200 characters)."); return; }
    setNameErr("");
    setSaving(true);
    try {
      const res = await api.put<{ user: any }>("/auth/me", { name: trimmedName, bio: trimmedBio });
      if (!res?.user) throw new Error("We received an unexpected response. Please try again.");
      setUser(res.user);
      toast.show("Profile updated", "success");
      Keyboard.dismiss();
      setEditOpen(false);
    } catch (e: any) {
      // Keep the sheet open so the user can fix input and retry. api errors already
      // carry a user-safe, category-aware message (network/timeout/server/etc.).
      toast.show(e?.message || "Couldn't update your profile. Please try again.", "error");
    } finally { setSaving(false); }
  };

  const [deleting, setDeleting] = useState(false);
  const doDelete = async () => {
    if (deleting) return;
    setDeleting(true);
    try {
      // Full account deletion: Firebase Auth user + all Mongo data + Storage media + mirror.
      await api.del("/account");
      setConfirmDelete(false);
      await logout();
      router.replace("/(auth)/login");
    } catch (e: any) {
      // Only report success if it actually completed; otherwise keep the user in place.
      toast.show(e?.message || "Couldn't delete your account. Please try again.", "error");
    } finally { setDeleting(false); }
  };

  const modes: any[] = [["light", "sunny-outline"], ["dark", "moon-outline"], ["system", "contrast-outline"]];

  return (
    <View style={{ flex: 1, backgroundColor: colors.surface }}>
      <ScrollView contentContainerStyle={{ paddingBottom: spacing.xxl }}>
        <View style={{ alignItems: "center", paddingTop: insets.top + spacing.lg, paddingBottom: spacing.lg }}>
          <Pressable testID="change-avatar" onPress={() => setPhotoMenu(true)}>
            <Avatar name={user?.name} uri={user?.avatar} size={96} />
            <View style={{ position: "absolute", right: -2, bottom: -2, width: 30, height: 30, borderRadius: 15, backgroundColor: colors.brandPrimary, alignItems: "center", justifyContent: "center", borderWidth: 2, borderColor: colors.surface }}>
              <Icon name="camera" size={15} color="#fff" />
            </View>
          </Pressable>
          <AppText size="xxl" weight="heavy" style={{ marginTop: spacing.md }}>{user?.name}</AppText>
          <AppText muted>@{user?.username}</AppText>
          {user?.bio ? <AppText center style={{ marginTop: 6, maxWidth: 280 }}>{user.bio}</AppText> : null}
          <Pressable testID="edit-profile-button" onPress={openEdit} style={{ marginTop: spacing.md, flexDirection: "row", alignItems: "center", paddingHorizontal: spacing.lg, height: 40, borderRadius: radius.pill, backgroundColor: colors.brandTertiary }}>
            <Icon name="create-outline" size={16} color={colors.brandPrimary} />
            <AppText weight="semibold" color={colors.brandPrimary} style={{ marginLeft: 6 }}>Edit Profile</AppText>
          </Pressable>
        </View>

        <View style={{ paddingHorizontal: spacing.lg, gap: spacing.lg }}>
          <Card style={{ paddingVertical: spacing.xs }}>
            <SettingRow testID="row-my-qr" icon="qr-code-outline" label="My QR Code" onPress={() => router.push("/qr")} />
            <SettingRow testID="row-scan-qr" icon="scan-outline" label="Scan QR Code" onPress={() => router.push("/scan")} />
            <SettingRow testID="row-requests" icon="person-add-outline" label="Friend Requests" onPress={() => router.push("/requests")}
              right={reqCount > 0 ? (
                <View style={{ backgroundColor: colors.brandPrimary, borderRadius: 11, minWidth: 22, height: 22, alignItems: "center", justifyContent: "center", paddingHorizontal: 6 }}>
                  <AppText size="xs" weight="bold" color="#fff">{reqCount}</AppText>
                </View>
              ) : undefined} />
          </Card>

          <Card style={{ paddingVertical: spacing.xs }}>
            <SettingRow testID="row-ai-memory" icon="bookmark-outline" label="AI Memory" onPress={() => router.push("/memory")} />
            <SettingRow testID="row-creations" icon="color-wand-outline" label="AI Creations" onPress={() => router.push("/creations")} />
            <SettingRow testID="row-research" icon="globe-outline" label="Research History" onPress={() => router.push("/research")} />
            <SettingRow testID="row-reminders" icon="alarm-outline" label="Reminders" onPress={() => router.push("/reminders")} />
          </Card>

          <View>
            <AppText weight="bold" muted size="sm" style={{ marginBottom: spacing.sm }}>APPEARANCE</AppText>
            <Card style={{ flexDirection: "row", gap: spacing.sm, padding: spacing.sm }}>
              {modes.map(([m, ic]) => (
                <Pressable key={m} testID={`theme-${m}`} onPress={() => setMode(m)} style={{ flex: 1, alignItems: "center", paddingVertical: spacing.md, borderRadius: radius.md, backgroundColor: mode === m ? colors.brandPrimary : colors.surfaceTertiary }}>
                  <Icon name={ic} size={20} color={mode === m ? "#fff" : colors.onSurface} />
                  <AppText size="sm" weight="semibold" color={mode === m ? "#fff" : colors.onSurface} style={{ marginTop: 4, textTransform: "capitalize" }}>{m}</AppText>
                </Pressable>
              ))}
            </Card>
          </View>

          <Card style={{ paddingVertical: spacing.xs }}>
            <SettingRow testID="row-privacy" icon="shield-checkmark-outline" label="Privacy & Security" onPress={() => router.push("/privacy")} />
            <SettingRow testID="row-settings" icon="settings-outline" label="Settings" onPress={() => router.push("/settings")} />
          </Card>

          <Card style={{ paddingVertical: spacing.xs }}>
            <SettingRow testID="row-privacy-policy" icon="reader-outline" label="Privacy Policy" onPress={() => router.push("/legal/privacy")} />
            <SettingRow testID="row-terms" icon="document-text-outline" label="Terms & Conditions" onPress={() => router.push("/legal/terms")} />
            <SettingRow testID="row-support" icon="mail-outline" label="Contact Support" onPress={() => Linking.openURL(`mailto:${SUPPORT_EMAIL}`)} />
          </Card>

          <Card style={{ paddingVertical: spacing.xs }}>
            <SettingRow testID="logout-button" icon="log-out-outline" label="Log Out" color={colors.error} onPress={async () => { await logout(); router.replace("/(auth)/login"); }} right={null} />
            <SettingRow testID="delete-account-button" icon="trash-outline" label="Delete Account" color={colors.error} onPress={() => setConfirmDelete(true)} right={null} />
          </Card>
        </View>
      </ScrollView>

      {/* Edit modal */}
      <Modal visible={editOpen} transparent animationType="slide" onRequestClose={closeEdit}>
        <Pressable style={{ flex: 1, backgroundColor: colors.overlay }} onPress={closeEdit} />
        <View style={[styles.sheet, { backgroundColor: colors.card, bottom: editKbOffset, paddingBottom: (editKbOffset > 0 ? spacing.lg : insets.bottom + spacing.lg) }]}>
          <AppText weight="bold" size="lg" style={{ marginBottom: spacing.md }}>Edit Profile</AppText>
          <Input testID="edit-name" label="Name" value={name} onChangeText={(t: string) => { setName(t); if (nameErr) setNameErr(""); }} autoCapitalize="words" error={nameErr} returnKeyType="done" />
          <Input testID="edit-bio" label="Bio" value={bio} onChangeText={setBio} placeholder="A short bio" multiline />
          <Button testID="save-profile" title="Save" onPress={saveProfile} loading={saving} />
        </View>
      </Modal>

      {/* Photo action sheet */}
      <Modal visible={photoMenu} transparent animationType="slide" onRequestClose={() => setPhotoMenu(false)}>
        <Pressable style={{ flex: 1, backgroundColor: colors.overlay }} onPress={() => setPhotoMenu(false)} />
        <View style={[styles.sheet, { backgroundColor: colors.card, paddingBottom: insets.bottom + spacing.lg }]}>
          <AppText weight="bold" size="lg" style={{ marginBottom: spacing.md }}>Profile Photo</AppText>
          <Pressable testID="choose-photo" onPress={changePhoto} style={{ flexDirection: "row", alignItems: "center", paddingVertical: spacing.md }}>
            <Icon name="image-outline" size={22} color={colors.brandPrimary} />
            <AppText weight="medium" style={{ marginLeft: spacing.md }}>Choose Photo</AppText>
          </Pressable>
          {user?.avatar ? (
            <Pressable testID="remove-photo" onPress={removePhoto} style={{ flexDirection: "row", alignItems: "center", paddingVertical: spacing.md }}>
              <Icon name="trash-outline" size={22} color={colors.error} />
              <AppText weight="medium" color={colors.error} style={{ marginLeft: spacing.md }}>Remove Photo</AppText>
            </Pressable>
          ) : null}
        </View>
      </Modal>

      {/* Delete confirm */}
      <Modal visible={confirmDelete} transparent animationType="fade" onRequestClose={() => setConfirmDelete(false)}>
        <View style={{ flex: 1, backgroundColor: colors.overlay, alignItems: "center", justifyContent: "center", padding: spacing.xl }}>
          <View style={{ backgroundColor: colors.card, borderRadius: radius.lg, padding: spacing.xl, width: "100%" }}>
            <AppText weight="bold" size="lg" center>Delete account?</AppText>
            <AppText muted center style={{ marginTop: spacing.sm, marginBottom: spacing.lg }}>This will deactivate your account and data. This cannot be undone.</AppText>
            <Button testID="confirm-delete" title="Delete Account" variant="danger" onPress={doDelete} loading={deleting} />
            <Pressable onPress={() => setConfirmDelete(false)} style={{ marginTop: spacing.md, alignItems: "center" }}><AppText weight="semibold">Cancel</AppText></Pressable>
          </View>
        </View>
      </Modal>
    </View>
  );
}

const styles = StyleSheet.create({
  sheet: { position: "absolute", bottom: 0, left: 0, right: 0, borderTopLeftRadius: radius.xl, borderTopRightRadius: radius.xl, padding: spacing.lg },
});
