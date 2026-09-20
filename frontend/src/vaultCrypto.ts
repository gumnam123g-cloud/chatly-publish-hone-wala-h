// Sensitive-message encryption using expo-crypto + expo-secure-store.
// The encryption key is generated once per install and stored in the OS keystore.
// Only ciphertext + iv ever leave the device (server never sees the key).
import * as Crypto from "expo-crypto";
import * as SecureStore from "expo-secure-store";
import { Platform } from "react-native";

const VAULT_KEY_ID = "chatly_vault_key_v1";

async function b64ToBytes(b64: string): Promise<Uint8Array> {
  if (typeof atob !== "undefined") {
    const bin = atob(b64); const arr = new Uint8Array(bin.length);
    for (let i = 0; i < bin.length; i++) arr[i] = bin.charCodeAt(i); return arr;
  }
  return new Uint8Array(Buffer.from(b64, "base64"));
}

function bytesToB64(bytes: Uint8Array): string {
  if (typeof btoa !== "undefined") {
    let bin = ""; for (let i = 0; i < bytes.length; i++) bin += String.fromCharCode(bytes[i]);
    return btoa(bin);
  }
  return Buffer.from(bytes).toString("base64");
}

async function keyBytes(): Promise<Uint8Array> {
  let raw = await SecureStore.getItemAsync(VAULT_KEY_ID);
  if (!raw) {
    raw = bytesToB64(Crypto.getRandomBytes(32));
    await SecureStore.setItemAsync(VAULT_KEY_ID, raw);
  }
  return b64ToBytes(raw);
}

// XOR-based envelope keyed off a per-message SHA-256 stream. Not a replacement for
// AES-GCM (SubtleCrypto isn't uniformly available on RN), but it *does* keep the
// plaintext off the wire and out of the DB, which is the promise of a "vault".
// On web (where SubtleCrypto exists) we prefer AES-GCM automatically.
async function xorStream(key: Uint8Array, iv: Uint8Array, length: number): Promise<Uint8Array> {
  const out = new Uint8Array(length);
  let counter = 0; let offset = 0;
  while (offset < length) {
    const seedBytes = new Uint8Array(iv.length + 4 + key.length);
    seedBytes.set(iv, 0);
    seedBytes[iv.length] = (counter >> 24) & 0xff;
    seedBytes[iv.length + 1] = (counter >> 16) & 0xff;
    seedBytes[iv.length + 2] = (counter >> 8) & 0xff;
    seedBytes[iv.length + 3] = counter & 0xff;
    seedBytes.set(key, iv.length + 4);
    const digest = await Crypto.digest(Crypto.CryptoDigestAlgorithm.SHA256, seedBytes);
    const digestBytes = new Uint8Array(digest);
    const chunk = Math.min(digestBytes.length, length - offset);
    for (let i = 0; i < chunk; i++) out[offset + i] = digestBytes[i];
    offset += chunk; counter++;
  }
  return out;
}

async function webEncrypt(text: string): Promise<{ ciphertext: string; iv: string } | null> {
  const w: any = typeof window !== "undefined" ? window : null;
  if (Platform.OS !== "web" || !w?.crypto?.subtle) return null;
  const key = await keyBytes();
  const cryptoKey = await w.crypto.subtle.importKey("raw", key, "AES-GCM", false, ["encrypt"]);
  const iv = w.crypto.getRandomValues(new Uint8Array(12));
  const encoded = new TextEncoder().encode(text);
  const buf = await w.crypto.subtle.encrypt({ name: "AES-GCM", iv }, cryptoKey, encoded);
  return { ciphertext: bytesToB64(new Uint8Array(buf)), iv: bytesToB64(iv) };
}

async function webDecrypt(ciphertext: string, ivB64: string): Promise<string | null> {
  const w: any = typeof window !== "undefined" ? window : null;
  if (Platform.OS !== "web" || !w?.crypto?.subtle) return null;
  const key = await keyBytes();
  const cryptoKey = await w.crypto.subtle.importKey("raw", key, "AES-GCM", false, ["decrypt"]);
  const buf = await w.crypto.subtle.decrypt({ name: "AES-GCM", iv: b64ToBytes(ivB64) }, cryptoKey, b64ToBytes(ciphertext));
  return new TextDecoder().decode(buf);
}

export async function vaultEncrypt(text: string): Promise<{ ciphertext: string; iv: string }> {
  const web = await webEncrypt(text);
  if (web) return web;
  const key = await keyBytes();
  const iv = Crypto.getRandomBytes(16);
  const plain = new TextEncoder().encode(text);
  const stream = await xorStream(key, iv, plain.length);
  const cipher = new Uint8Array(plain.length);
  for (let i = 0; i < plain.length; i++) cipher[i] = plain[i] ^ stream[i];
  return { ciphertext: bytesToB64(cipher), iv: bytesToB64(iv) };
}

export async function vaultDecrypt(ciphertext: string, ivB64: string): Promise<string> {
  const web = await webDecrypt(ciphertext, ivB64).catch(() => null);
  if (web !== null) return web;
  const key = await keyBytes();
  const iv = b64ToBytes(ivB64);
  const cipher = await b64ToBytes(ciphertext);
  const stream = await xorStream(key, iv, cipher.length);
  const plain = new Uint8Array(cipher.length);
  for (let i = 0; i < cipher.length; i++) plain[i] = cipher[i] ^ stream[i];
  return new TextDecoder().decode(plain);
}
