"""
PULSE load simulation — targets backend services via pulse-shell proxy.

Run from the simulation/locust/ directory:
  pip install -r requirements.txt
  locust -f locustfile.py --host https://pulse.test:30443

Then open http://localhost:8089 and start a swarm.

Recommended settings for demo:
  - Baseline:      5 users, spawn rate 1  → ~1-5 rpm on event-svc (normal)
  - Live-refresh:  50 users, spawn rate 5 → ~60 rpm on event-svc (matches Bug 4)
  - AI stress:     10 users, spawn rate 2 → drives ai-svc latency (Bug 1 visible fast)
  - Memory leak:   30 users, spawn rate 3 → accelerates Bug 3 session buffer growth
"""

import json
import random
import uuid
from locust import HttpUser, task, between, constant_throughput

CITIES   = ["London", "Paris"]
DEMO_USER = "demo_user"


class BaselineUser(HttpUser):
    """Normal browsing — loads events, reads one, no saves. Baseline APM traffic."""
    wait_time = between(3, 8)
    weight = 3

    def on_start(self):
        self.city = random.choice(CITIES)
        self.session_id = self._create_session()
        self.event_ids: list[str] = []

    def _create_session(self) -> str | None:
        with self.client.post(
            "/api/session-svc/sessions",
            json={"user_id": f"load_{uuid.uuid4().hex[:8]}"},
            catch_response=True,
        ) as r:
            if r.status_code == 200:
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


class AIUser(HttpUser):
    """Requests AI recommendations — stresses ai-svc and Redis cache.
    With BUG_AI_SLOW active, each task takes ~8s → latency spike in NR Distributed Tracing."""
    wait_time = between(5, 15)
    weight = 2

    def on_start(self):
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
            },
            name="/api/ai-svc/recommendations",
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


class SaveUser(HttpUser):
    """Saves and unsaves events — drives session-svc traffic.
    With BUG_MEMORY_LEAK active, each session call grows the in-process buffer."""
    wait_time = between(2, 6)
    weight = 2

    def on_start(self):
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
            json={"user_id": f"load_{uuid.uuid4().hex[:8]}"},
        )
        if r2.status_code == 200:
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
