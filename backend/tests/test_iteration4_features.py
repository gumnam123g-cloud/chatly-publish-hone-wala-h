"""Iteration 4 backend tests - Chatly 24-feature pass.

Covers only NEW surfaces requested by the main agent:
- Auth extras: /auth/username-available, /auth/session (Google), forgot-password, /auth/me
- Messaging idempotency via client_message_id
- Offline sync (POST /api/sync/messages, GET /api/sync/pull)
- Priority + Smart Inbox
- AI Autopilot rules CRUD + analyze + confirm
- Smart features: unread-catchup, digest, smart-reminder-suggest, follow-ups
- Group AI: assistant (group only), decision-maker analyze / polls / vote / close
- Calls: create, accept, reject, end, list, ice-servers (Google STUN + Metered TURN)
- Call transcription (transcript-text) + AI summary via Sarvam
- Feedback + analytics
- Push register (503 acceptable if EMERGENT_PUSH_KEY placeholder)
- Firebase status ready:true

AI calls (Sarvam) can be slow; treat 200 or 503 as PASS per review request.
"""
import os
import uuid
import time

import pytest
import requests


BASE_URL = (os.environ.get("EXPO_PUBLIC_BACKEND_URL") or "").rstrip("/")
if not BASE_URL:
    with open("/app/frontend/.env") as f:
        for line in f:
            if line.startswith("EXPO_PUBLIC_BACKEND_URL="):
                BASE_URL = line.split("=", 1)[1].strip().rstrip("/")
                break
API = f"{BASE_URL}/api"

DEMO_EMAIL = "demo@chatly.app"
DEMO_PASS = "Demo1234"
DEMO2_EMAIL = "demo2@chatly.app"
DEMO2_PASS = "Demo1234"


def _login(email: str, password: str) -> tuple[str, dict]:
    r = requests.post(f"{API}/auth/login", json={"email": email, "password": password}, timeout=30)
    assert r.status_code == 200, f"Login failed for {email}: {r.status_code} {r.text}"
    d = r.json()
    return d["token"], d["user"]


# ---- Session-scoped fixtures ----
@pytest.fixture(scope="session")
def demo():
    tok, user = _login(DEMO_EMAIL, DEMO_PASS)
    return {"token": tok, "user": user, "headers": {"Authorization": f"Bearer {tok}"},
            "jheaders": {"Authorization": f"Bearer {tok}", "Content-Type": "application/json"}}


@pytest.fixture(scope="session")
def demo2():
    tok, user = _login(DEMO2_EMAIL, DEMO2_PASS)
    return {"token": tok, "user": user, "headers": {"Authorization": f"Bearer {tok}"},
            "jheaders": {"Authorization": f"Bearer {tok}", "Content-Type": "application/json"}}


@pytest.fixture(scope="session")
def rahul_chat_id(demo):
    r = requests.get(f"{API}/chats", headers=demo["headers"], timeout=15)
    assert r.status_code == 200
    for c in r.json()["chats"]:
        if c.get("type") != "group" and "Rahul" in (c.get("other") or {}).get("name", ""):
            return c["chat_id"]
    pytest.skip("Rahul DM missing")


@pytest.fixture(scope="session")
def group_chat_id(demo, demo2):
    """Create a group with demo2 so group endpoints have a real target."""
    r = requests.post(f"{API}/groups",
                      json={"name": "TEST_Iter4_Group_" + uuid.uuid4().hex[:6],
                            "member_ids": [demo2["user"]["user_id"]]},
                      headers=demo["jheaders"], timeout=15)
    assert r.status_code == 200, r.text
    gid = r.json()["chat_id"]
    # seed some messages so AI has content
    for text in ("Team, should we ship on Friday or Monday?",
                 "I vote Friday to unblock design.",
                 "Let's decide by tomorrow EOD."):
        requests.post(f"{API}/chats/{gid}/messages", json={"text": text},
                      headers=demo["jheaders"], timeout=15)
    return gid


# ============================================================
# AUTH extras
# ============================================================
class TestAuthExtras:
    def test_me(self, demo):
        r = requests.get(f"{API}/auth/me", headers=demo["headers"], timeout=15)
        assert r.status_code == 200
        assert r.json()["user"]["email"] == DEMO_EMAIL

    def test_username_available_requires_auth(self):
        r = requests.get(f"{API}/auth/username-available", params={"u": "someuser"}, timeout=10)
        assert r.status_code in (401, 403)

    def test_username_available_ok(self, demo):
        r = requests.get(f"{API}/auth/username-available",
                         params={"u": f"free_{uuid.uuid4().hex[:8]}"},
                         headers=demo["headers"], timeout=10)
        assert r.status_code == 200
        assert r.json().get("available") is True

    def test_session_rejects_bad_session_id(self):
        r = requests.post(f"{API}/auth/session",
                          json={"session_id": "invalid_" + uuid.uuid4().hex}, timeout=30)
        assert r.status_code == 401

    def test_forgot_password_accepts_known_email(self):
        r = requests.post(f"{API}/auth/forgot-password",
                          json={"email": DEMO_EMAIL}, timeout=30)
        # Should never leak whether the email exists; 200 either way (or 500 if
        # email provider blocks)
        assert r.status_code in (200, 500), r.text


# ============================================================
# Messaging idempotency (client_message_id)
# ============================================================
class TestMessagingIdempotency:
    def test_send_same_client_message_id_returns_same_message(self, demo, rahul_chat_id):
        cmid = f"cmid_{uuid.uuid4().hex}"
        payload = {"text": "TEST_idem_1", "client_message_id": cmid}
        r1 = requests.post(f"{API}/chats/{rahul_chat_id}/messages",
                           json=payload, headers=demo["jheaders"], timeout=15)
        assert r1.status_code == 200, r1.text
        m1 = r1.json()["message"]
        r2 = requests.post(f"{API}/chats/{rahul_chat_id}/messages",
                           json=payload, headers=demo["jheaders"], timeout=15)
        assert r2.status_code == 200
        m2 = r2.json()["message"]
        assert m1["message_id"] == m2["message_id"], "Idempotency failed - different IDs"
        # Verify no duplicate persisted
        r3 = requests.get(f"{API}/chats/{rahul_chat_id}/messages",
                          headers=demo["headers"], timeout=15)
        matches = [m for m in r3.json()["messages"]
                   if m.get("client_message_id") == cmid]
        assert len(matches) == 1, f"Expected 1 persisted, got {len(matches)}"

    def test_sync_messages_outbox_is_idempotent(self, demo, rahul_chat_id):
        cmid = f"cmid_sync_{uuid.uuid4().hex}"
        body = {"text": "TEST_outbox", "client_message_id": cmid}
        # POST /api/sync/messages?chat_id=...
        r1 = requests.post(f"{API}/sync/messages", params={"chat_id": rahul_chat_id},
                           json=body, headers=demo["jheaders"], timeout=15)
        assert r1.status_code == 200, r1.text
        r2 = requests.post(f"{API}/sync/messages", params={"chat_id": rahul_chat_id},
                           json=body, headers=demo["jheaders"], timeout=15)
        assert r2.status_code == 200
        assert r1.json()["message"]["message_id"] == r2.json()["message"]["message_id"]

    def test_sync_pull_returns_messages(self, demo):
        r = requests.get(f"{API}/sync/pull", headers=demo["headers"], timeout=15)
        assert r.status_code == 200
        d = r.json()
        assert "messages" in d and isinstance(d["messages"], list)
        assert "server_time" in d

    def test_sync_pull_since_filters(self, demo):
        # since=future should return zero messages
        r = requests.get(f"{API}/sync/pull",
                         params={"since": "2099-01-01T00:00:00+00:00"},
                         headers=demo["headers"], timeout=15)
        assert r.status_code == 200
        assert r.json()["messages"] == []


# ============================================================
# Priority + Smart Inbox
# ============================================================
class TestPrioritySmartInbox:
    def test_set_priority_important(self, demo, rahul_chat_id):
        sent = requests.post(f"{API}/chats/{rahul_chat_id}/messages",
                             json={"text": "TEST_priority_target"},
                             headers=demo["jheaders"], timeout=15).json()["message"]
        r = requests.patch(f"{API}/messages/{sent['message_id']}/priority",
                           json={"priority": "important"},
                           headers=demo["jheaders"], timeout=15)
        assert r.status_code == 200, r.text
        assert r.json()["priority"] == "important"
        TestPrioritySmartInbox._msg_id = sent["message_id"]

    def test_smart_inbox_important(self, demo):
        r = requests.get(f"{API}/inbox/smart", params={"category": "important"},
                         headers=demo["headers"], timeout=15)
        assert r.status_code == 200
        d = r.json()
        assert d["category"] == "important"
        assert any(m["message_id"] == TestPrioritySmartInbox._msg_id for m in d["messages"])

    def test_smart_inbox_all_has_groups(self, demo):
        r = requests.get(f"{API}/inbox/smart", params={"category": "all"},
                         headers=demo["headers"], timeout=15)
        assert r.status_code == 200
        d = r.json()
        for k in ("important", "normal", "low", "action_required", "follow_up_required"):
            assert k in d["groups"]


# ============================================================
# AI Autopilot rules + suggestions
# ============================================================
class TestAutopilot:
    def test_rule_crud(self, demo):
        # Create
        r = requests.post(f"{API}/ai/autopilot/rules",
                          json={"name": "TEST_rule_" + uuid.uuid4().hex[:6],
                                "enabled": True, "summary": True,
                                "suggest_priority": True, "suggest_reminder": True,
                                "suggest_follow_up": True, "chat_ids": []},
                          headers=demo["jheaders"], timeout=15)
        assert r.status_code == 200, r.text
        rid = r.json()["id"]
        # List
        rl = requests.get(f"{API}/ai/autopilot/rules",
                          headers=demo["headers"], timeout=15)
        assert rl.status_code == 200
        assert any(x["id"] == rid for x in rl.json()["rules"])
        # Patch (enabled=False)
        rp = requests.patch(f"{API}/ai/autopilot/rules/{rid}",
                            json={"name": "TEST_rule_upd", "enabled": False,
                                  "summary": False, "suggest_priority": False,
                                  "suggest_reminder": False, "suggest_follow_up": False,
                                  "chat_ids": []},
                            headers=demo["jheaders"], timeout=15)
        assert rp.status_code == 200
        assert rp.json()["enabled"] is False
        # Delete
        rd = requests.delete(f"{API}/ai/autopilot/rules/{rid}",
                             headers=demo["headers"], timeout=15)
        assert rd.status_code == 200

    def test_analyze_returns_suggestions_or_gracefully(self, demo, rahul_chat_id):
        r = requests.post(f"{API}/ai/autopilot/analyze",
                          json={"chat_id": rahul_chat_id},
                          headers=demo["jheaders"], timeout=120)
        # 200 with suggestions[] OR 503 if Sarvam times out — both acceptable
        assert r.status_code in (200, 503), r.text
        if r.status_code == 200:
            d = r.json()
            assert "suggestions" in d and isinstance(d["suggestions"], list)

    def test_confirm_priority(self, demo, rahul_chat_id):
        sent = requests.post(f"{API}/chats/{rahul_chat_id}/messages",
                             json={"text": "TEST_confirm_target"},
                             headers=demo["jheaders"], timeout=15).json()["message"]
        r = requests.post(f"{API}/ai/autopilot/confirm",
                          json={"suggestion_type": "priority",
                                "message_id": sent["message_id"],
                                "title": "Mark important",
                                "priority": "important"},
                          headers=demo["jheaders"], timeout=15)
        assert r.status_code == 200, r.text
        assert r.json()["status"] == "priority_updated"

    def test_confirm_reminder(self, demo):
        r = requests.post(f"{API}/ai/autopilot/confirm",
                          json={"suggestion_type": "reminder",
                                "title": "TEST_reminder_from_confirm"},
                          headers=demo["jheaders"], timeout=15)
        assert r.status_code == 200
        assert r.json()["status"] == "reminder_created"


# ============================================================
# Smart features (AI - Sarvam)
# ============================================================
class TestSmartFeatures:
    def test_unread_catchup(self, demo):
        r = requests.get(f"{API}/ai/unread-catchup",
                         headers=demo["headers"], timeout=120)
        assert r.status_code in (200, 503), r.text
        if r.status_code == 200:
            d = r.json()
            assert "items" in d and "count" in d

    def test_digest_daily(self, demo):
        r = requests.post(f"{API}/ai/digest",
                          json={"period": "daily"},
                          headers=demo["jheaders"], timeout=120)
        assert r.status_code in (200, 503), r.text
        if r.status_code == 200:
            d = r.json()
            assert d["period"] == "daily"
            assert "digest" in d

    def test_smart_reminder_suggest(self, demo, rahul_chat_id):
        r = requests.post(f"{API}/ai/smart-reminder-suggest",
                          json={"chat_id": rahul_chat_id},
                          headers=demo["jheaders"], timeout=120)
        assert r.status_code in (200, 503), r.text

    def test_follow_ups(self, demo):
        # Ensure at least one follow-up exists via confirm
        requests.post(f"{API}/ai/autopilot/confirm",
                      json={"suggestion_type": "follow_up",
                            "title": "TEST_followup_" + uuid.uuid4().hex[:6]},
                      headers=demo["jheaders"], timeout=15)
        r = requests.get(f"{API}/follow-ups", headers=demo["headers"], timeout=15)
        assert r.status_code == 200
        d = r.json()
        assert "items" in d and isinstance(d["items"], list)


# ============================================================
# Group AI + Decision Maker (polls)
# ============================================================
class TestGroupAI:
    def test_assistant_group_only(self, demo, rahul_chat_id):
        # DM should be rejected with 400
        r = requests.get(f"{API}/groups/{rahul_chat_id}/assistant",
                         headers=demo["headers"], timeout=30)
        assert r.status_code == 400

    def test_assistant_for_group(self, demo, group_chat_id):
        r = requests.get(f"{API}/groups/{group_chat_id}/assistant",
                         headers=demo["headers"], timeout=120)
        assert r.status_code in (200, 503), r.text
        if r.status_code == 200:
            d = r.json()
            assert d["chat_id"] == group_chat_id and "assistant" in d

    def test_decision_analyze(self, demo, group_chat_id):
        r = requests.post(f"{API}/groups/{group_chat_id}/decision-maker/analyze",
                          headers=demo["jheaders"], timeout=120)
        assert r.status_code in (200, 503), r.text
        if r.status_code == 200:
            d = r.json()
            assert d.get("requires_confirmation") is True
            assert "analysis" in d

    def test_poll_crud_vote_close(self, demo, group_chat_id):
        # Create
        r = requests.post(f"{API}/groups/{group_chat_id}/decision-maker/polls",
                          json={"question": "TEST_ship_day?", "options": ["Friday", "Monday"]},
                          headers=demo["jheaders"], timeout=15)
        assert r.status_code == 200, r.text
        poll = r.json()["poll"]
        pid = poll["id"]
        assert len(poll["options"]) == 2
        # List
        rl = requests.get(f"{API}/groups/{group_chat_id}/decision-maker/polls",
                          headers=demo["headers"], timeout=15)
        assert rl.status_code == 200
        assert any(p["id"] == pid for p in rl.json()["polls"])
        # Vote
        rv = requests.post(f"{API}/groups/{group_chat_id}/decision-maker/polls/{pid}/vote",
                           json={"option_id": "0"},
                           headers=demo["jheaders"], timeout=15)
        assert rv.status_code == 200
        # Vote again on different option (should switch)
        rv2 = requests.post(f"{API}/groups/{group_chat_id}/decision-maker/polls/{pid}/vote",
                            json={"option_id": "1"},
                            headers=demo["jheaders"], timeout=15)
        assert rv2.status_code == 200
        # Close
        rc = requests.post(f"{API}/groups/{group_chat_id}/decision-maker/polls/{pid}/close",
                           headers=demo["jheaders"], timeout=15)
        assert rc.status_code == 200
        d = rc.json()
        assert d["status"] == "closed"
        assert d["final_decision"] and d["final_decision"]["label"] == "Monday"

    def test_vote_invalid_option(self, demo, group_chat_id):
        r = requests.post(f"{API}/groups/{group_chat_id}/decision-maker/polls",
                          json={"question": "TEST_pref?", "options": ["A", "B"]},
                          headers=demo["jheaders"], timeout=15)
        pid = r.json()["poll"]["id"]
        rv = requests.post(f"{API}/groups/{group_chat_id}/decision-maker/polls/{pid}/vote",
                           json={"option_id": "99"},
                           headers=demo["jheaders"], timeout=15)
        assert rv.status_code == 400


# ============================================================
# Calls: signaling + ice-servers + transcription + AI
# ============================================================
class TestCallsAndTranscript:
    def test_ice_servers_stun_and_turn(self, demo):
        r = requests.get(f"{API}/calls/ice-servers", headers=demo["headers"], timeout=15)
        assert r.status_code == 200
        servers = r.json()["iceServers"]
        assert isinstance(servers, list) and len(servers) >= 1
        # Google STUN present
        flat = []
        for s in servers:
            urls = s["urls"] if isinstance(s["urls"], list) else [s["urls"]]
            flat.extend(urls)
        assert any("stun.l.google.com" in u for u in flat), f"Google STUN missing: {flat}"
        # Metered TURN present
        assert any("openrelay.metered.ca" in u or "turn:" in u for u in flat), f"TURN missing: {flat}"
        turn_entry = next((s for s in servers if any("turn" in u.split(":")[0]
                                                     for u in (s["urls"] if isinstance(s["urls"], list) else [s["urls"]]))), None)
        assert turn_entry is not None
        assert turn_entry.get("username") and turn_entry.get("credential")

    def test_call_lifecycle(self, demo, rahul_chat_id):
        r = requests.post(f"{API}/calls",
                          json={"chat_id": rahul_chat_id, "type": "voice"},
                          headers=demo["jheaders"], timeout=15)
        assert r.status_code == 200, r.text
        call = r.json()["call"]
        assert call["status"] == "ringing"
        cid = call["call_id"]
        # Accept
        ra = requests.post(f"{API}/calls/{cid}/accept",
                           headers=demo["jheaders"], timeout=10)
        assert ra.status_code == 200 and ra.json()["status"] == "connected"
        # End
        re = requests.post(f"{API}/calls/{cid}/end",
                           headers=demo["jheaders"], timeout=10)
        assert re.status_code == 200 and re.json()["status"] == "ended"

    def test_call_reject(self, demo, rahul_chat_id):
        r = requests.post(f"{API}/calls",
                          json={"chat_id": rahul_chat_id, "type": "video"},
                          headers=demo["jheaders"], timeout=15)
        cid = r.json()["call"]["call_id"]
        rr = requests.post(f"{API}/calls/{cid}/reject",
                           headers=demo["jheaders"], timeout=10)
        assert rr.status_code == 200 and rr.json()["status"] == "rejected"

    def test_list_calls(self, demo):
        r = requests.get(f"{API}/calls", headers=demo["headers"], timeout=15)
        assert r.status_code == 200
        assert isinstance(r.json()["calls"], list)

    def test_transcript_text_and_ai_summary(self, demo, rahul_chat_id):
        # Fresh call
        r = requests.post(f"{API}/calls",
                          json={"chat_id": rahul_chat_id, "type": "voice"},
                          headers=demo["jheaders"], timeout=15)
        cid = r.json()["call"]["call_id"]
        requests.post(f"{API}/calls/{cid}/accept",
                      headers=demo["jheaders"], timeout=10)
        # Upload transcript
        text = ("Alice: Let's schedule the release for Feb 5. "
                "Bob: I'll send the budget by tomorrow. Owner: Bob.")
        rt = requests.post(f"{API}/calls/{cid}/transcript-text",
                           json={"text": text},
                           headers=demo["jheaders"], timeout=15)
        assert rt.status_code == 200, rt.text
        # Get transcript
        rg = requests.get(f"{API}/calls/{cid}/transcript",
                          headers=demo["headers"], timeout=10)
        assert rg.status_code == 200
        assert "budget" in rg.json()["transcript"].lower()
        # End
        requests.post(f"{API}/calls/{cid}/end",
                      headers=demo["jheaders"], timeout=10)
        # Summary via Sarvam
        rs = requests.post(f"{API}/calls/{cid}/ai",
                           json={"action": "summary"},
                           headers=demo["jheaders"], timeout=120)
        assert rs.status_code in (200, 503), rs.text
        if rs.status_code == 200:
            assert "summary" in rs.json()


# ============================================================
# Feedback + analytics
# ============================================================
class TestFeedbackAnalytics:
    def test_submit_feedback(self, demo):
        r = requests.post(f"{API}/feedback",
                          json={"message": "TEST_feedback_" + uuid.uuid4().hex[:6],
                                "category": "bug"},
                          headers=demo["jheaders"], timeout=15)
        assert r.status_code == 200, r.text
        assert r.json()["status"] == "received"

    def test_my_feedback(self, demo):
        r = requests.get(f"{API}/feedback/mine",
                         headers=demo["headers"], timeout=15)
        assert r.status_code == 200
        assert isinstance(r.json()["items"], list)

    def test_analytics_event(self, demo):
        r = requests.post(f"{API}/analytics/event",
                          json={"events": [{"event": "app_open"},
                                           {"event": "screen_view",
                                            "props": {"screen": "home"}}]},
                          headers=demo["jheaders"], timeout=15)
        assert r.status_code == 200
        assert r.json()["accepted"] == 2

    def test_analytics_event_rejects_unknown(self, demo):
        r = requests.post(f"{API}/analytics/event",
                          json={"events": [{"event": "unknown_bogus"}]},
                          headers=demo["jheaders"], timeout=15)
        assert r.status_code == 200
        assert r.json()["accepted"] == 0
        assert r.json()["rejected"] == 1


# ============================================================
# Push + Firebase status
# ============================================================
class TestPushAndFirebase:
    def test_register_push_own_user(self, demo):
        r = requests.post(f"{API}/register-push",
                          json={"user_id": demo["user"]["user_id"],
                                "platform": "android",
                                "device_token": "test_device_token_" + uuid.uuid4().hex},
                          headers=demo["jheaders"], timeout=30)
        # 201 if EMERGENT_PUSH_KEY configured, 503 acceptable per review request
        assert r.status_code in (201, 502, 503), r.text

    def test_register_push_wrong_user_forbidden(self, demo, demo2):
        r = requests.post(f"{API}/register-push",
                          json={"user_id": demo2["user"]["user_id"],
                                "platform": "android",
                                "device_token": "TEST_token"},
                          headers=demo["jheaders"], timeout=15)
        assert r.status_code == 403

    def test_firebase_status_ready(self):
        r = requests.get(f"{API}/firebase/status", timeout=15)
        assert r.status_code == 200, r.text
        assert r.json().get("ready") is True


# ============================================================
# AuthN on new endpoints
# ============================================================
class TestNewEndpointsAuth:
    def test_unauth_endpoints_reject(self):
        endpoints = [
            ("GET", "/inbox/smart"),
            ("GET", "/ai/autopilot/rules"),
            ("POST", "/ai/autopilot/analyze"),
            ("POST", "/ai/autopilot/confirm"),
            ("GET", "/ai/unread-catchup"),
            ("POST", "/ai/digest"),
            ("POST", "/ai/smart-reminder-suggest"),
            ("GET", "/follow-ups"),
            ("GET", "/sync/pull"),
            ("POST", "/feedback"),
            ("POST", "/analytics/event"),
            ("POST", "/register-push"),
        ]
        for m, p in endpoints:
            r = requests.request(m, f"{API}{p}", json={}, timeout=15)
            assert r.status_code in (401, 403, 422), f"{m} {p} -> {r.status_code}"
