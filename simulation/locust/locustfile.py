"""
PULSE load simulation — targets backend services via pulse-shell proxy.

Run from the simulation/locust/ directory:
  pip install -r requirements.txt
  locust -f locustfile.py --host https://pulse.test:30443

Then open http://localhost:8089 and start a swarm.

Recommended settings for demo:
  - Baseline:        5 users,  spawn 1  → ~1-5 rpm on event-svc (normal APM)
  - AI stress:      10 users,  spawn 2  → drives ai-svc latency (Bug 1 visible fast)
  - Memory leak:    30 users,  spawn 3  → accelerates Bug 3 session buffer growth
  - Live-refresh:   50 users,  spawn 5  → ~60 rpm on event-svc (Bug 5)
  - Chat / LLM:     10 users,  spawn 2  → NR AI Monitoring: tokens, errors, feedback
  - Full demo mix:  30 users,  spawn 3  → all user classes active, realistic traffic

User class weights (applied automatically when running all classes):
  BaselineUser 3 · AIUser 2 · SaveUser 2 · ChatUser 2 · LiveRefreshUser 1
"""

import json
import random
import uuid
import urllib3
from locust import HttpUser, task, between, constant_throughput

urllib3.disable_warnings(urllib3.exceptions.InsecureRequestWarning)

# Models available in the chat UI — weights control how often each is picked.
# gemini-2.0-flash is intentionally included with low weight: it will error
# silently in the UI but produce visible errors in NR logs (demo scenario).
_CHAT_MODELS = [
    ("gemini-3.1-flash-lite-preview", 30),
    ("gemini-2.5-flash",              20),
    ("gemini-2.5-pro",                10),
    ("claude-sonnet-4-6",             20),
    ("claude-haiku-4-5-20251001",     10),
    ("gpt-4o-mini",                   15),
    ("gpt-4.1-nano",                  10),
    ("gemini-2.0-flash",               5),  # deprecated — errors in NR, silent in UI
]
_CHAT_MODEL_VALUES   = [m[0] for m in _CHAT_MODELS]
_CHAT_MODEL_WEIGHTS  = [m[1] for m in _CHAT_MODELS]

_CHAT_MESSAGES = [
    "What's on this weekend in {city}?",
    "Any good food events happening in {city}?",
    "Recommend a sports event in {city}.",
    "What tech meetups are coming up in {city}?",
    "I'm looking for live music in {city}.",
    "Any art exhibitions I shouldn't miss in {city}?",
    "What's a fun night out in {city}?",
    "Suggest something unique happening in {city} this month.",
    "Are there any family-friendly events in {city}?",
    "What's the best event for a first date in {city}?",
]

CITIES   = ["London", "Paris"]
DEMO_USER = "demo_user"


class PulseUser(HttpUser):
    """Base class — disables TLS verification for self-signed cert on pulse.test."""
    abstract = True

    def on_start(self):
        self.client.verify = False


class BaselineUser(PulseUser):
    """Normal browsing — loads events, reads one, no saves. Baseline APM traffic."""
    wait_time = between(3, 8)
    weight = 3

    def on_start(self):
        super().on_start()
        self.city = random.choice(CITIES)
        self.session_id = self._create_session()
        self.event_ids: list[str] = []

    def _create_session(self) -> str | None:
        with self.client.post(
            "/api/session-svc/sessions",
            json={"user_id": f"load_{uuid.uuid4().hex[:8]}"},
            catch_response=True,
        ) as r:
            if r.status_code in (200, 201):
                return r.json().get("session_id")
            r.failure(f"session create failed: {r.status_code}")
            return None

    @task(5)
    def browse_events(self):
        with self.client.get(
            f"/api/event-svc/events?city={self.city}",
            name="/api/event-svc/events",
            catch_response=True,
        ) as r:
            if r.status_code == 200:
                events = r.json()
                self.event_ids = [e["id"] for e in events] if events else []
                r.success()
            else:
                r.failure(f"events failed: {r.status_code}")

    @task(2)
    def get_event_detail(self):
        if not self.event_ids:
            return
        event_id = random.choice(self.event_ids)
        self.client.get(
            f"/api/event-svc/events/{event_id}",
            name="/api/event-svc/events/:id",
        )

    @task(1)
    def get_user_prefs(self):
        self.client.get("/api/event-svc/user", name="/api/event-svc/user")


class AIUser(PulseUser):
    """Requests AI recommendations — stresses ai-svc and Redis cache.
    With BUG_AI_SLOW active, each task takes ~8s → latency spike in NR Distributed Tracing."""
    wait_time = between(5, 15)
    weight = 2

    def on_start(self):
        super().on_start()
        self.city = random.choice(CITIES)
        self.events: list[dict] = []
        self._load_events()

    def _load_events(self):
        r = self.client.get(
            f"/api/event-svc/events?city={self.city}",
            name="/api/event-svc/events (ai-user init)",
        )
        if r.status_code == 200:
            self.events = r.json()[:20]  # ai-svc caps at 20 anyway

    @task
    def get_recommendations(self):
        if not self.events:
            self._load_events()
            return
        provider = random.choices(
            ["gemini", "claude", "openai"],
            weights=[50, 30, 20],
            k=1,
        )[0]
        with self.client.post(
            "/api/ai-svc/recommendations",
            json={
                "user_id": DEMO_USER,
                "user_preferences": {"categories": random.sample(
                    ["music", "food", "art", "sport", "tech"], k=random.randint(1, 3)
                )},
                "saved_event_ids": [],
                "available_events": self.events,
                "city": self.city,
                "provider": provider,
            },
            name=f"/api/ai-svc/recommendations",
            catch_response=True,
            timeout=20,
        ) as r:
            if r.status_code == 200:
                mode = r.json().get("mode", "unknown")
                r.success()
                # tag the response with AI mode for NR custom attributes
                if mode != "ai":
                    r.failure(f"degraded mode: {mode}")
            else:
                r.failure(f"ai-svc {r.status_code}")


class SaveUser(PulseUser):
    """Saves and unsaves events — drives session-svc traffic.
    With BUG_MEMORY_LEAK active, each session call grows the in-process buffer."""
    wait_time = between(2, 6)
    weight = 2

    def on_start(self):
        super().on_start()
        self.city = random.choice(CITIES)
        self.session_id: str | None = None
        self.saved_ids: list[str] = []
        self.all_event_ids: list[str] = []
        self._setup()

    def _setup(self):
        r = self.client.get(f"/api/event-svc/events?city={self.city}")
        if r.status_code == 200:
            self.all_event_ids = [e["id"] for e in r.json()]

        r2 = self.client.post(
            "/api/session-svc/sessions",
            json={"user_id": DEMO_USER},
        )
        if r2.status_code in (200, 201):
            self.session_id = r2.json().get("session_id")

    @task(3)
    def restore_session(self):
        if not self.session_id:
            return
        with self.client.get(
            f"/api/session-svc/sessions/{self.session_id}",
            name="/api/session-svc/sessions/:id",
            catch_response=True,
        ) as r:
            if r.status_code == 200:
                self.saved_ids = r.json().get("saved_event_ids", [])
                r.success()
            else:
                r.failure(f"session restore {r.status_code}")

    @task(2)
    def save_event(self):
        if not self.session_id or not self.all_event_ids:
            return
        unsaved = [e for e in self.all_event_ids if e not in self.saved_ids]
        if not unsaved:
            return
        event_id = random.choice(unsaved)
        with self.client.post(
            f"/api/session-svc/sessions/{self.session_id}/saved-events",
            json={"event_id": event_id},
            name="/api/session-svc/sessions/:id/saved-events (POST)",
            catch_response=True,
        ) as r:
            if r.status_code in (200, 201):
                self.saved_ids.append(event_id)
                r.success()
            else:
                r.failure(f"save failed: {r.status_code}")

    @task(1)
    def unsave_event(self):
        if not self.session_id or not self.saved_ids:
            return
        event_id = random.choice(self.saved_ids)
        with self.client.delete(
            f"/api/session-svc/sessions/{self.session_id}/saved-events/{event_id}",
            name="/api/session-svc/sessions/:id/saved-events (DELETE)",
            catch_response=True,
        ) as r:
            if r.status_code == 200:
                self.saved_ids.remove(event_id)
                r.success()
            else:
                r.failure(f"unsave failed: {r.status_code}")


class ChatUser(PulseUser):
    """Drives pulse-ai-dontask /chat with realistic model rotation.

    Key NR demo signals:
    - LLM Observability: token counts, latency per model, feedback sentiment
    - gemini-2.0-flash (weight 5) fails silently in the UI but logs errors →
      shows up as errors in NR AI Monitoring without alerting real users
    - Thumbs-up/down feedback wired to record_llm_feedback_event in NR
    """
    wait_time = between(8, 20)
    weight = 2

    def on_start(self):
        super().on_start()
        self.city = random.choice(CITIES)
        self.last_trace_id: str | None = None
        self.last_model: str | None = None

    def _pick_model(self) -> str:
        return random.choices(_CHAT_MODEL_VALUES, weights=_CHAT_MODEL_WEIGHTS, k=1)[0]

    @task(4)
    def send_chat_message(self):
        model = self._pick_model()
        message = random.choice(_CHAT_MESSAGES).format(city=self.city)
        with self.client.post(
            "/api/test-svc/chat",
            json={"message": message, "model": model, "city": self.city},
            name="/api/test-svc/chat",
            catch_response=True,
            timeout=30,
        ) as r:
            if r.status_code == 200:
                data = r.json()
                self.last_trace_id = data.get("trace_id")
                self.last_model = data.get("model", model)
                r.success()
            else:
                # Mark as failure in Locust stats (NR will show error too)
                r.failure(f"chat failed: model={model} status={r.status_code}")
                self.last_trace_id = None

    @task(1)
    def send_feedback(self):
        if not self.last_trace_id:
            return
        rating = random.choices(["good", "bad"], weights=[75, 25], k=1)[0]
        with self.client.post(
            "/api/test-svc/chat/feedback",
            json={"trace_id": self.last_trace_id, "rating": rating},
            name="/api/test-svc/chat/feedback",
            catch_response=True,
        ) as r:
            if r.status_code in (200, 204):
                r.success()
            else:
                r.failure(f"feedback failed: {r.status_code}")
        self.last_trace_id = None  # one feedback per response

    @task(1)
    def switch_city(self):
        self.city = random.choice(CITIES)


class LiveRefreshUser(PulseUser):
    """Simulates the LIVE button — polls event-svc at ~1 req/s per user.

    5 users of this class → ~300 rpm on event-svc, enough to saturate the
    service map edge and trigger NR alerts if thresholds are configured.
    Matches Bug 5 behaviour without needing the UI toggle.
    """
    wait_time = constant_throughput(1)  # 1 request per second per user
    weight = 1

    def on_start(self):
        super().on_start()
        self.city = random.choice(CITIES)

    @task(8)
    def poll_events(self):
        with self.client.get(
            f"/api/event-svc/events?city={self.city}",
            name="/api/event-svc/events [LIVE]",
            catch_response=True,
        ) as r:
            if r.status_code == 200:
                r.success()
            else:
                r.failure(f"live poll failed: {r.status_code}")

    @task(1)
    def poll_ai_status(self):
        with self.client.get(
            "/api/ai-svc/status",
            name="/api/ai-svc/status [LIVE]",
            catch_response=True,
        ) as r:
            if r.status_code == 200:
                r.success()
            else:
                r.failure(f"ai status failed: {r.status_code}")
