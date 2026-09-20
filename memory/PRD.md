# Chatly AI Messenger — PRD & Build Log

## Original Problem Statement
Build "Chatly AI Messenger" — an AI-native real-time messaging + personal AI + productivity + research + document intelligence platform (Android-first, iOS-ready, web-ready backend). Chatly AI is deeply integrated into messaging, groups, files, search, research, productivity and workflows. NOT a WhatsApp clone — positioned as "an AI-native communication operating system."

## User Choices (v1)
- MVP focus: Messaging + Chatly AI + AI intelligence (broad foundation)
- Auth: Email + Password with backend Email OTP verification (Emergent-managed email)
- AI provider: Sarvam AI (`sarvam-105b`) primary, Emergent universal LLM as fallback
- Realtime: WebSocket
- Theme: Light + Dark + System (bright orange #FF5E00 accent)

## Architecture
- Frontend: Expo Router (React Native), theme/auth/ws/toast providers, Ionicons, expo-image, expo-linear-gradient.
- Backend: FastAPI + MongoDB (motor), JWT auth (bcrypt), WebSocket manager, provider-agnostic AI layer.
- AI: Sarvam AI chat completions (reasoning model — output budget padded + reasoning_effort low), Tavily web search, Emergent email for OTP, Emergent LLM fallback.
- Data isolation: every endpoint verifies Bearer token + ownership (participants / user_id).

## User Personas
- Busy professional who wants AI to turn messages into tasks, summaries, replies.
- Student/knowledge worker using Chatly for research, documents, and productivity.

## Implemented (2026-06 / iteration 1)
- Auth: signup, 6-digit email OTP (hashed, single-use, expiry, resend cooldown, max attempts, rate limit), login (unverified handling), forgot/reset password, me/update/delete. Pre-verified demo account `demo@chatly.app` / `Demo1234`.
- Messaging: chats list, 1-to-1 chat, send/receive over WebSocket, optimistic send, typing indicator, message states, reactions, star, edit, delete, pin, mute. Seeded AI persona contacts (Rahul/Priya/Aman) that auto-reply via Sarvam.
- Chatly AI: assistant chat (persisted conversations), smart reply, message actions (rewrite/improve/grammar/translate/summarize/explain/shorten/expand/tone), chat brain (summary/important/timeline/pending/decisions/find), task/deadline extraction.
- Intelligence: Ask Your Chats (cross-chat search + cited sources), Deep Research (Tavily + cited report + history).
- Creation Studio: documents/presentations/spreadsheets/notes/checklist/plan; artifact library + viewer.
- Productivity: tasks CRUD, reminders CRUD, important messages, AI insights dashboard.
- AI Memory (user-controlled), AI Privacy Control Center (per-feature access toggles).
- Tabs: Chats, Chatly (dashboard), Status, Calls, Profile. Settings, Privacy, Memory, Creations screens.
- Theming light/dark/system; polished empty/loading/error states throughout.

## Testing (iteration 1)
- Backend: 30/30 pytest passing. Frontend: full login→chat→AI flows verified. Report: /app/test_reports/iteration_1.json.

## Implemented — Phase 1 & 2 (2026-06 / iteration 2)
- Google Sign-In/Sign-Up (Emergent OAuth): POST /api/auth/session upserts by email (no duplicates), issues existing JWT; frontend "Continue with Google" (web + mobile).
- Real user-to-user: /api/users/search, contact requests (send/accept/reject, mutual auto-accept), /api/contacts/list, block. New Chat searches real users; demo<->persona seeded as contacts.
- Photo & file sharing: Emergent Object Storage (storage_service.py), private, token-gated /api/files/{path} with participant check; upload via /api/chats/{id}/attachments.
- Attachment Intelligence: doc text extraction (pypdf/python-docx/openpyxl/csv/txt) + image vision/OCR (gpt-4o); /api/ai/attachment actions with source citation; /api/ai/attachment-search.
- Groups + Group Brain: /api/groups CRUD, roles, add/remove/leave; reuse chat/messages + WS; Group Brain via /api/ai/chat-brain. New Group + Group Info screens.
- Voice messages: expo-audio record -> /api/chats/{id}/voice -> Whisper transcription; voice bubble + transcript; attachment AI applies.
- Privacy Center: added attachments/images/documents/voice_messages/group_intelligence toggles. app.json camera/mic/photos permissions. Bundle IDs unchanged.

## Implemented — Phase 3 (2026-06 / iteration 3): Calls + Call Intelligence
- Real call SIGNALING over existing WebSocket (call_offer/answer/ice/hangup relayed to target) + REST call lifecycle: POST /api/calls, accept, reject, end (states ringing/connected/ended/missed/rejected), GET /api/calls (history) + GET /api/calls/{id}. Authorization: participant/membership checks; 401/404 guards.
- Call History UI (Calls tab) with type icon, missed/duration, timestamp, AI indicator, call-back.
- Global Call overlay (src/calls.tsx CallProvider): incoming/outgoing/connected UI, mute/speaker/camera/end controls, ring haptics. Voice/Video call buttons in chat header.
- AI Call Intelligence: /api/calls/{id}/transcript (Whisper audio) + /transcript-text; /api/calls/{id}/ai actions summary(structured)/tasks/ask(with source); GET+DELETE transcript; /api/calls/search. Call Intelligence screen: record notes->transcribe, summary, detected action items -> create task/reminder/calendar (confirm only).
- Calendar events collection: POST/GET /api/calendar. Call->calendar/reminder/task all require user confirmation.
- Privacy: added call_intelligence/call_transcription/call_summary/call_memory toggles (gating enforced server-side; 403 when off). UI toggles added.
- (superseded) Media layer now implemented — see Phase 6 below.

## Testing (iteration 3)
- Backend 28/28 Phase 3 + regression pass. Frontend call surfaces verified. Report: /app/test_reports/iteration_3.json.

## Testing (iteration 2)
- Backend 35/35 after contacts-seed fix. Frontend Phase-1/2 surfaces verified. Report: /app/test_reports/iteration_2.json.

## Still Pending (next)
- 2FA/biometric lock, disappearing messages, push notifications (device build).
- Voice->smart-reply chips, group polls/announcements/pinned UI, conversation-aware web search, automations, admin dashboard, export PPTX/PDF/XLSX, E2EE.

## Backlog (prioritized)
- P0: Real 2-user messaging (currently single-user + AI persona demo), image/file attachments via Object Storage, push notifications.
- P1: Groups + Group Brain, Status media, Voice (STT/TTS) + voice-to-message, document upload & PDF intelligence (RAG), automations engine, follow-up tracker.
- P2: Voice/video calls (WebRTC, device build), Google Sign-In, 2FA/biometric lock, admin dashboard, export PPTX/PDF/XLSX, scam shield, link intelligence.

## Notes
- Email OTP delivers only to real addresses (provider blocks fake domains). Real users' emails work.
- Sarvam is a reasoning model; ai_service pads token budget and retries once on empty output.

## Implemented — Phase 6 (2026-09): Real call media + live transcription
- WebRTC 1:1 audio/video: web preview uses browser RTCPeerConnection; Android/iOS builds use react-native-webrtc (124.x) via @config-plugins/react-native-webrtc@13 (SDK 54). Expo Go shows a clear "needs installed app" banner (WebRTC is native code).
- Signaling reuses WS relay (call_offer/call_answer/call_ice). Caller offers after call_accepted; callee answers; ICE candidates queued until remote SDP set. ICE config from GET /api/calls/ice-servers (Google STUN + OpenRelay TURN default; env STUN_URLS/TURN_URLS/TURN_USERNAME/TURN_CREDENTIAL for production).
- Call UI (src/calls.tsx): remote video full-screen, local mirrored PiP, real Mute/Camera/Flip/Speaker (expo-audio earpiece routing on native), connection state, Expo Go/permission/failed banners, live captions overlay + CC toggle.
- Live transcription: each participant records own mic in 8s chunks (web MediaRecorder + VAD; native expo-audio recorder loop) -> POST /api/calls/{id}/transcript-chunk -> Whisper (auto language EN/HI/Hinglish) -> speaker-labelled segments merged into call.transcript -> WS call_transcript to both sides. Privacy toggles enforced server-side (403). Call Intelligence works on the live transcript right after hang-up.
- Fixed pre-existing media_service.transcribe_audio bug (path string passed to Whisper client) which had broken all voice transcription.
- Group calls remain signaling-only (banner shown); planned for a later phase.

## Implemented — Phase 9 & 10 (2025-08): Firebase integration + messaging/AI upgrades
- Firebase Admin on FastAPI (firebase_service.py): Firestore, Storage, FCM send, ID-token verify, user mirror, account cleanup. Live-verified (ready:true). SA JSON server-only (git-ignored).
- New endpoints: /api/firebase/status, /api/fcm/register|unregister, /api/auth/firebase (ID-token→JWT, rejects anonymous), /api/auth/firebase-token (custom token bridge), DELETE /api/account (full Firebase Auth + Mongo + Storage + mirror cleanup), /api/auth/username-available.
- QR "user not found" ROOT-CAUSE FIX: deep link was sent as a URL path param (%2F broke routing). New /api/users/by-qr?code= + {code:path} + robust token extractor (backend + scan.tsx).
- AI: per-action output language + tone; real Reply Draft; translate auto-detect; chat-brain out_lang.
- Messaging: delete-for-me / delete-for-everyone; long messages (20k); FCM push on new message (skip sender/bot/muted).
- Status: made PERMANENT (no 24h expiry), video limit 200MB.
- Client: firebase JS SDK (src/firebase.ts, custom-token sign-in), notifications (src/notifications.ts, FCM + local reminders), gallery auto-save (src/gallery.ts, images/videos only), left/right swipe tab nav, scoped Task/Reminder keyboard fix, account-deletion UI → DELETE /api/account.
- Firebase artifacts delivered in /app/firebase: firestore.rules, storage.rules, firestore.indexes.json, README.
- Config: firebase-admin.json (backend), EXPO_PUBLIC_FIREBASE_* (frontend .env), app.json plugins (expo-notifications, expo-media-library) + Android permissions (POST_NOTIFICATIONS, VIBRATE, USE_FULL_SCREEN_INTENT, SCHEDULE_EXACT_ALARM, READ_MEDIA_VIDEO).
- Native-only (code complete, verify on APK): FCM push delivery (bg/terminated), WebRTC media + native incoming-call UI/ringtone, background/closed reminders, gallery save, QR camera.
- OUTSTANDING user action: enable Firebase Storage bucket (still not provisioned — media upload blocked until done); add Google SHA-1/256 after first APK build.

## Implemented — Iteration 4 (2026-06): 24-feature pass on SDK 57 (Sarvam-only AI)
- **Sarvam AI everywhere**: rewrote `media_service.py` to use Sarvam Speech-to-Text (saaras:v3, auto-detects Hindi/English/Hinglish) and Sarvam Vision (Indic VLM) for OCR. Removed Emergent/Claude LLM fallback from `ai_service.py` — Sarvam is now the SOLE AI provider for chat completions, transcription, and vision per user directive.
- **Offline chat + messaging reliability**:
  - New `/app/frontend/src/offlineChat.ts`: per-chat AsyncStorage cache (last 200 msgs), pending-message outbox keyed by stable `client_message_id`, `drainOutbox()` on reconnect, `pullSince()` catches up missed messages.
  - Wired into `chat/[id].tsx` (instant hydrate from cache, queued send on failure, cache-upsert on receive) and `src/ws.tsx` (on WS reconnect: drain outbox + pull-since fanout to listeners).
  - Backend already exposed `/api/sync/messages?chat_id=` (idempotent on `client_message_id`) and `/api/sync/pull?since=` — validated by 38/38 pytest run.
- **Calls upgraded**:
  - Cross-platform ringtone at `src/ringtone.ts` (expo-audio looping player on native, HTMLAudioElement on web, coordinated Vibration.vibrate) — plays on `incoming_call`, stopped on accept/reject/end.
  - `calls_routes.py` now fires a high-priority FCM push (`type=incoming_call`, `full_screen_intent=true`, `channel_id=calls`) to callees on `POST /api/calls` so background/killed devices can wake and ring.
  - Added `start_call_sweeper()` — every 10s marks ringing calls older than 45s as `missed` and notifies participants via WS.
- **New AI screens (all confirm-first, no auto actions)**:
  - `/app/frontend/app/smart-inbox.tsx` — priority-filter chips (Important / Action / Follow-up / Normal / Low) over GET /api/inbox/smart; per-message priority toggle via PATCH /api/messages/{id}/priority.
  - `/app/frontend/app/autopilot.tsx` — AI Autopilot rules CRUD (name, enabled, summary, suggest_priority, suggest_reminder, suggest_follow_up, chat_ids) + Analyze-a-chat that returns suggestions; each suggestion has an explicit "Confirm & apply" button hitting POST /api/ai/autopilot/confirm — nothing is applied without the user tapping.
  - `/app/frontend/app/catchup.tsx` — GET /api/ai/unread-catchup summary + important / action / questions sections.
  - `/app/frontend/app/digest.tsx` — POST /api/ai/digest with daily/weekly toggle.
  - `/app/frontend/app/followups.tsx` — GET /api/follow-ups + PUT /api/reminders/{id}/done.
  - `/app/frontend/app/group-assistant/[id].tsx` — group summary + AI decision detection + create/vote/close polls (GET/POST /api/groups/{id}/decision-maker/polls/**). Linked from Group Info via "Group Assistant & Polls" button.
  - All 6 screens wired into the Chatly-tab quick actions grid.
- **SDK 57 migration cleanup**: `package.json` now on Expo SDK 57 / react-native 0.86.3. Fixed compile error by replacing `@react-navigation/native` `useFocusEffect` imports with `expo-router`'s equivalent (SDK 56+ dropped react-navigation compatibility). Metro bundle now builds successfully; app boots to Login and post-auth to the Chatly dashboard.
- **Backend validation**: 38/38 pytest in `/app/backend/tests/test_iteration4_features.py` (iteration_4 report). Covers Auth, messaging idempotency, offline sync, priority + smart inbox, autopilot CRUD + analyze + confirm, catchup / digest / smart-reminder-suggest / follow-ups, group assistant + poll lifecycle, calls (start/accept/reject/end, ice-servers with Google STUN + Metered TURN), transcription/AI-summary via Sarvam, feedback + analytics allow-list, push registration guardrails, Firebase status, and auth-gate on 12 new endpoints.

