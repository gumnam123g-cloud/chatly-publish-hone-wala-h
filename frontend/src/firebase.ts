/**
 * Chatly client Firebase (JS SDK) — works in Expo Go, web preview and native builds.
 * Auth uses a Firebase CUSTOM TOKEN minted by our backend (/api/auth/firebase-token)
 * for the already-JWT-authenticated user, so Firestore/Storage security rules see the
 * correct request.auth.uid. NO anonymous auth is ever used.
 */
import { initializeApp, getApps, getApp } from "firebase/app";
import {
  getAuth,
  initializeAuth,
  signInWithCustomToken,
  signOut as fbSignOut,
} from "firebase/auth";
import { getFirestore } from "firebase/firestore";
import { getStorage } from "firebase/storage";
import { Platform } from "react-native";
import AsyncStorage from "@react-native-async-storage/async-storage";

const firebaseConfig = {
  apiKey: process.env.EXPO_PUBLIC_FIREBASE_API_KEY,
  authDomain: process.env.EXPO_PUBLIC_FIREBASE_AUTH_DOMAIN,
  projectId: process.env.EXPO_PUBLIC_FIREBASE_PROJECT_ID,
  storageBucket: process.env.EXPO_PUBLIC_FIREBASE_STORAGE_BUCKET,
  messagingSenderId: process.env.EXPO_PUBLIC_FIREBASE_SENDER_ID,
  appId: process.env.EXPO_PUBLIC_FIREBASE_APP_ID,
};

export const firebaseReady = !!firebaseConfig.projectId;

let app: any = null;
let _auth: any = null;

if (firebaseReady) {
  app = getApps().length ? getApp() : initializeApp(firebaseConfig);
  try {
    if (Platform.OS === "web") {
      _auth = getAuth(app);
    } else {
      // Persist the RN session across restarts.
      const { getReactNativePersistence } = require("firebase/auth");
      _auth = initializeAuth(app, { persistence: getReactNativePersistence(AsyncStorage) });
    }
  } catch {
    _auth = getAuth(app);
  }
}

export const fbAuth = _auth;
export const fbDb = firebaseReady ? getFirestore(app) : null;
export const fbStorage = firebaseReady ? getStorage(app) : null;

/** Sign the client into Firebase using a backend-minted custom token. Idempotent. */
export async function signInFirebaseWithCustomToken(token: string): Promise<boolean> {
  if (!firebaseReady || !_auth || !token) return false;
  try {
    if (_auth.currentUser) return true;
    await signInWithCustomToken(_auth, token);
    return true;
  } catch (e) {
    console.warn("[firebase] custom-token sign-in failed", e);
    return false;
  }
}

export async function signOutFirebase() {
  try { if (_auth?.currentUser) await fbSignOut(_auth); } catch {}
}
