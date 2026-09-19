# Chatly Firebase configuration

Project: **chatlyai-12478**

## Files
- `firestore.rules` — Firestore security rules
- `storage.rules` — Storage security rules
- `firestore.indexes.json` — composite indexes

## Deploy (from your machine, with the Firebase CLI + your login)
```bash
npm i -g firebase-tools
firebase login
firebase use chatlyai-12478
# firebase.json should reference these files
firebase deploy --only firestore:rules,firestore:indexes,storage
```

## Console steps you must complete
1. **Authentication → Sign-in method:** enable Email/Password and Google; ensure Anonymous is DISABLED.
2. **Firestore Database:** already created (verified live).
3. **Storage → Get started:** provision the default bucket (currently NOT provisioned — media uploads fail until this is done).
4. **Google Sign-In:** after the first Emergent Publish APK build, add its SHA-1 + SHA-256 to the Android app in Project Settings, then re-download `google-services.json`.
5. **Cloud Messaging:** enabled by default; the app registers device tokens via `/api/fcm/register`.

The Admin service-account JSON lives only on the backend (`/app/backend/firebase-admin.json`, git-ignored). Never ship it to the client.
