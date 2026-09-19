# Chatly Roadmap (Phase 1 + Phase 2)

This document tracks the full 68-feature scope the user requested. Items marked
DONE were shipped in the current milestone; the rest are ordered by
dependency + user-visible impact so subsequent sessions can pick up cleanly.

## Session Delivered (Milestone A + auth verify)

- **Status 24h expiry restored** — server filters by created_at, `expires_at`
  set to now+24h for both text/image and video statuses.
- **In-app media viewers**
  - `/viewer/image` — pinch-zoom, pan, double-tap reset, disk cache via
    `expo-file-system`, offline reopen.
  - `/viewer/video` — expo-video player with native controls + PiP + cache.
  - `/viewer/pdf` — cache + in-app Custom-Tabs preview (Google Docs viewer)
    + fallback to OS share sheet. Never punts to a random browser.
- **Chat media routing** — `openFile()` now routes image/video/PDF/DOC/PPT/XLS/
  TXT/MD/CSV to the correct in-app viewer.
- **AI action reliability** — nested-modal race fix, loading + retry + empty-
  response + friendly error states. Tracks `ai_action_started/completed/failed`.
- **Send Feedback** — new screen (`/feedback`) + backend `POST /api/feedback`
  and `GET /api/feedback/mine`.
- **Share Chatly** — Profile row uses native Android share sheet.
- **Analytics** — client `src/analytics.ts` batches events (5s / 20 items)
  to backend `POST /api/analytics/event`. Events emitted:
  `app_open, sign_up, login, google_sign_in, logout, message_sent,
  ai_action_started/completed/failed, share_app, feedback_submitted,
  media_viewed_image/video/pdf`.

## Milestone B — Auth polish (next)

- Google Sign-In: verify redirect + Firebase bridge end-to-end on Android,
  add "Cancelled" toast, network-lost toast, duplicate-account merge.
- Email verification UX: cooldown timer visible on Resend, expired-code path,
  "email sent" only after backend 202 confirmation.
- Forgot password expired/invalid code UX polish.

## Milestone C — Messaging reliability + calls

- Message dedup: stable client_msg_id, server idempotent write, listener
  cleanup on chat unmount, offline outbox with retry.
- Offline mode: hydrate cached chats/messages from AsyncStorage, offline
  banner, queued send once WS reconnects.
- Call ringtone (foreground) via expo-av, incoming call UI already exists —
  wire the ring/vibrate to the WS `call_offer` event.
- FCM signaling for calls (already in backend push_to_user); wake screen on
  Android via `SCHEDULE_EXACT_ALARM` + `USE_FULL_SCREEN_INTENT` in app.json.
- "Ringing" vs "Calling" label — check receiver presence via WS before
  showing ringing.
- Firebase Analytics native — via dev-build + `@react-native-firebase/analytics`;
  current backend log is a safe superset used until then.

## Milestone D — Expo SDK 57 upgrade

- Currently on SDK 54. Upgrade with `npx expo install --check`, verify
  Firebase, expo-video, expo-audio, expo-notifications, WebRTC config plugin.

## Phase 2 (50 features) — Ordered backlog

1. **AI Personal Assistant** — natural-language task capture, uses existing
   `/tasks` + new `/reminders/schedule` + `/ai/summarize-chat`.
2. **AI Autopilot** — user-defined rules (`db.autopilot_rules`), evaluated
   in `chat_routes.send_message` post-hook.
3. **Smart Inbox** — server-side classifier on new-message; UI filter chips
   on Chats tab.
4. **Priority Messages** — manual flag + AI suggestion via existing
   `/ai/message-action`.
5. **Unread Catch-Up** — `POST /ai/chat-brain kind=unread_summary`.
6. **Chat Digest** — daily/weekly cron via `webhook-crond`, email via
   Emergent email service.
7. **Smart Reminders** — extends existing `/reminders` with AI suggestion
   surfaced in the message action sheet.
8. **Follow-Up Tracker** — new `db.followups` collection populated by
   `/ai/chat-brain kind=pending`.
9. **Scheduled Messages** — `POST /api/messages/schedule` + cron.
10. **Recurring Messages** — extension of scheduled with `rrule` field.
11. **AI Group Assistant** — `/ai/chat-brain` already supports groups.
12. **Group Decision Maker** — new `/api/groups/{id}/poll`.
13. **Group Task Manager** — new `db.group_tasks`.
14. **Group Meeting Planner** — availability slots UI.
15. **Contact Intelligence** — `/api/users/{id}/brief` via `/ai/chat-brain`.
16. **Smart Contact Groups** — labels on `contacts` doc.
17. **AI Scam Detector** — pre-send hook, warns on suspicious links.
18. **Link Preview + Analyzer** — server-side OG scrape + safety check.
19. **AI Screenshot Assistant** — share-to-Chatly + image_qa.
20. **Receipt Scanner** — same, structured JSON output.
21. **Business Card Scanner** — same, contact create.
22. **Document Scanner** — expo-camera + doc-scanner-native shim.
23. **Image Cleanup** — Emergent LLM image gen (Nano Banana / gpt-image-1).
24. **Audio Cleanup** — server-side ffmpeg pipeline.
25. **Voice Commands** — expo-speech-recognition + `/ai/interpret`.
26. **Chat → PPT** — `/api/exports/pptx` (already scaffolded).
27. **Chat → Document/PDF** — new `/api/exports/pdf` via reportlab.
28. **Chat → Invoice/Quote** — `/api/exports/invoice`.
29. **Chat → Form** — `/api/exports/form`.
30. **Chat → Spreadsheet** — `/api/exports/xlsx`.
31. **AI Meeting Mode** — extends live-call transcription + summary.
32. **AI Negotiation Assistant** — new `/ai/negotiate` prompt.
33. **Conversation Memory** — extends existing `/memory`.
34. **AI Contact Brief** — see #15.
35. **Chat Templates** — new `/api/templates`.
36. **Multi-Message Composer** — merge-tag rendering on template.
37. **AI Voice Reply** — expo-speech-recognition → `/ai/message-action`.
38. **Two-Way Translation Mode** — per-chat setting, uses `/ai/message-action`.
39. **Chat Export** — `/api/chats/{id}/export`.
40. **Privacy Screen** — Android FLAG_SECURE + biometric gate.
41. **Message Vault** — encrypted local store via expo-secure-store.
42. **Temporary Chat** — per-chat TTL setting.
43. **Message Expiry** — per-message TTL field.
44. **Universal Search** — server + local index.
45. **Universal Share-to-Chatly** — Android share-intent target via
    `app.json intentFilters`.
46. **AI Daily Brief** — cron + notification.
47. **AI Morning Plan** — extends daily brief.
48. **AI End-of-Day Summary** — cron.
49. **Offline AI Tools** — on-device basic writing/notes via local models
    (feasibility: only very small ONNX; fallback = "not available offline").
50. **Analytics event verification** — dashboard endpoint (already writes to
    `db.analytics_events`).

Each Phase-2 item is scoped to 30-90 minutes of focused work and depends only
on primitives that are already in the codebase (auth, chat, WS, storage,
Emergent LLM, Firebase, push).
