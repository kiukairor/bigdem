# PULSE — Bug Scenarios Reference

Demo bugs for the "something is wrong in production" narrative.  
Three are activated via the CI/CD pipeline (Helm env toggle + git push).  
One is activated live from the UI with no push required.

---

## Overview

| # | Name | Trigger | Service | NR Feature | Status |
|---|------|---------|---------|------------|--------|
| 1 | BUG_AI_SLOW | Helm env + git push | ai-svc | Distributed Tracing | ✅ Ready |
| 2 | BUG_STALE_CACHE | Helm env + git push | event-svc | Logs in Context | ✅ Ready |
| 3 | BUG_MEMORY_LEAK | Helm env + git push | session-svc | Infrastructure | ✅ Ready |
| 4 | LIVE_REFRESH | UI toggle in feed | event-svc | APM Throughput + Browser AJAX | ✅ Ready |

All bugs fire `BugScenarioEnabled` custom events to New Relic (except LIVE_REFRESH, which shows via auto-captured AJAX).

---

## NR Change Tracker

Before activating any bug in a demo, mark the moment in New Relic so you get the before/after on every chart.

**Via NR UI:** [one.newrelic.com](https://one.newrelic.com) → APM → *pulse-event-svc* (or relevant service) → **Change tracking** → Mark deployment.

**Via API (recommended for pipeline):**
```bash
curl -X POST https://api.newrelic.com/graphql \
  -H "Api-Key: $NEW_RELIC_USER_API_KEY" \
  -H "Content-Type: application/json" \
  -d '{
    "query": "mutation { changeTrackingCreateDeployment(deployment: { entityGuid: \"ENTITY_GUID\", version: \"bug-activated\", description: \"BUG_AI_SLOW enabled\", changelog: \"Demo scenario\" }) { deploymentId } }"
  }'
```

Get the entity GUID from NR UI: APM → service → **See metadata and manage tags**.

**Recommended:** add a Change Tracker API call to the GitHub Actions workflow right after ArgoCD syncs. This way every bug activation shows automatically on NR charts.

---

## Bug 1 — BUG_AI_SLOW

**Story:** AI recommendations start taking 8 seconds per request. No errors, no alerts — just user-visible slowness. NR Distributed Tracing shows exactly which span is responsible.

**What it does:** Injects an 8-second `time.sleep()` in `ai-svc` before the Claude call. Bypasses Redis cache so the delay hits every single request.

**Activate:**
```bash
# 1. Edit the flag
sed -i 's/BUG_AI_SLOW: "false"/BUG_AI_SLOW: "true"/' infra/helm/ai-svc/values.yaml

# 2. Commit and push — ArgoCD restarts the pod in ~30s, no image rebuild
git add infra/helm/ai-svc/values.yaml
git commit -m "demo: enable BUG_AI_SLOW"
git push
```

**Recover:**
```bash
sed -i 's/BUG_AI_SLOW: "true"/BUG_AI_SLOW: "false"/' infra/helm/ai-svc/values.yaml
git add infra/helm/ai-svc/values.yaml && git commit -m "demo: disable BUG_AI_SLOW" && git push
```

**Observe in NR:**
1. Go to `https://pulse.test:30443`, open the AI Recommendations panel and click refresh.
2. NR → APM → **pulse-ai-svc** → Distributed Tracing → find a `/recommendations` trace.
3. The `call_claude` span will show 8 000 ms. All other spans are normal.
4. NR Logs in Context on that trace: `BUG_AI_SLOW active: injecting 8s delay before Claude call`.
5. Custom event: `SELECT * FROM BugScenarioEnabled WHERE bug = 'BUG_AI_SLOW' SINCE 10 minutes ago`.

**NR NRQL to paste live:**
```sql
SELECT average(duration) FROM Span
WHERE appName = 'pulse-ai-svc' AND name LIKE '%recommendations%'
TIMESERIES SINCE 30 minutes ago
```

---

## Bug 2 — BUG_STALE_CACHE

**Story:** Events in the feed show dates 45 days in the past. No 5xx, no error rate alert fires. Users see wrong data silently. NR Logs in Context reveals the cause — a stale cache bug.

**What it does:** Shifts all returned event dates back 45 days in the `event-svc` response. Data looks plausible (valid dates, valid format) but is wrong.

**Activate:**
```bash
sed -i 's/BUG_STALE_CACHE: "false"/BUG_STALE_CACHE: "true"/' infra/helm/event-svc/values.yaml
git add infra/helm/event-svc/values.yaml
git commit -m "demo: enable BUG_STALE_CACHE"
git push
```

**Recover:**
```bash
sed -i 's/BUG_STALE_CACHE: "true"/BUG_STALE_CACHE: "false"/' infra/helm/event-svc/values.yaml
git add infra/helm/event-svc/values.yaml && git commit -m "demo: disable BUG_STALE_CACHE" && git push
```

**Observe in NR:**
1. Feed shows events dated ~45 days ago (no error, UI looks fine at a glance).
2. NR → APM → **pulse-event-svc** → Logs in Context → filter `level:warn`.
3. Log line: `{"level":"warn","bug":"BUG_STALE_CACHE","msg":"returning stale cached events, dates shifted -45 days","count":20}`.
4. Custom event: `SELECT * FROM BugScenarioEnabled WHERE bug = 'BUG_STALE_CACHE' SINCE 10 minutes ago`.

**NR NRQL to paste live:**
```sql
SELECT message FROM Log
WHERE service.name = 'pulse-event-svc' AND level = 'warn'
SINCE 15 minutes ago LIMIT 20
```

---

## Bug 3 — BUG_MEMORY_LEAK

**Story:** session-svc memory keeps climbing. No crash — yet. NR Infrastructure shows the trend. Connecting it back to the code shows a global buffer that accumulates session payloads and is never freed.

**What it does:** Appends each session payload (multiplied ×100) to a global Python list on every `POST /sessions` and `GET /sessions/:id` call. Memory grows linearly with traffic. Process is never restarted so the buffer keeps growing.

**Activate:**
```bash
sed -i 's/BUG_MEMORY_LEAK: "false"/BUG_MEMORY_LEAK: "true"/' infra/helm/session-svc/values.yaml
git add infra/helm/session-svc/values.yaml
git commit -m "demo: enable BUG_MEMORY_LEAK"
git push
```

**Recover:**
```bash
sed -i 's/BUG_MEMORY_LEAK: "true"/BUG_MEMORY_LEAK: "false"/' infra/helm/session-svc/values.yaml
git add infra/helm/session-svc/values.yaml && git commit -m "demo: disable BUG_MEMORY_LEAK" && git push
# Pod restart on next push clears the in-process buffer automatically
```

**Observe in NR:**
1. NR → Infrastructure → **Kubernetes** → pod `session-svc-*` → Memory chart.
2. Generate load: refresh the app a few times (each page load hits session-svc).
3. Memory climbs with each request. Pod logs: `BUG_MEMORY_LEAK active: buffer has N entries`.
4. Custom event: `SELECT latest(leaked_entries) FROM BugScenarioEnabled WHERE bug = 'BUG_MEMORY_LEAK' TIMESERIES`.

**NR NRQL to paste live:**
```sql
SELECT latest(leaked_entries) FROM BugScenarioEnabled
WHERE bug = 'BUG_MEMORY_LEAK'
TIMESERIES 1 minute SINCE 30 minutes ago
```

**To accelerate the demo:** combine with Bug 4 (LIVE_REFRESH). The 1-second polling also hits session-svc on page load, so memory grows faster.

---

## Bug 4 — LIVE_REFRESH (UI toggle)

**Story:** A "Live Updates" button was added to the feed. A user clicks it. event-svc throughput goes from ~1 req/min to 60 req/min. No code change, no deploy — just a UI toggle. NR APM and NR Browser both show the spike the moment it's activated.

**What it does:** Polls `event-svc /events` every 1 second with a cache-busting timestamp parameter. The SPA agent captures every XHR automatically.

**Activate from the UI:**
1. Go to `https://pulse.test:30443`
2. In the event feed toolbar, click **○ LIVE** — it turns red and starts pulsing (● LIVE)
3. A red banner appears: `● LIVE REFRESH ACTIVE — polling event-svc every 1s`

**Deactivate:**
Click **● LIVE** again. The interval clears immediately, requests stop.

**No git push, no pod restart — instant on/off.**

**Observe in NR:**
1. NR → APM → **pulse-event-svc** → Throughput chart (top of Overview page).
2. Throughput spikes from baseline (~1-5 rpm) to ~60 rpm within 1 minute of toggling on.
3. NR → Browser → **pulse-shell** → AJAX → requests to `/api/event-svc/events` — flood of calls visible per second.
4. Toggle off → throughput drops back to baseline within 1 minute.

**NR NRQL to paste live:**
```sql
SELECT rate(count(*), 1 minute) FROM Transaction
WHERE appName = 'pulse-event-svc' AND request.uri LIKE '/events%'
TIMESERIES 30 seconds SINCE 15 minutes ago
```

---

## Combining bugs for a full demo

Suggested sequence for a 10-minute live demo:

| Time | Action | NR moment |
|------|--------|-----------|
| 0:00 | Show green baseline in NR | "Everything healthy" |
| 0:30 | Enable Bug 4 (LIVE, from UI) | Throughput chart spikes live |
| 1:30 | Enable Bug 3 (MEMORY_LEAK, git push) | Infrastructure memory trend |
| 3:00 | Enable Bug 1 (AI_SLOW, git push) | Distributed Tracing 8s span |
| 5:00 | Show Bug 2 (STALE_CACHE) | Logs in Context |
| 7:00 | Recover all bugs one by one | Charts normalise live |
| 9:00 | "Found and fixed in under 10 minutes with NR" | |

Register a Change Tracker deployment marker before enabling each bug so every chart shows the exact moment of change.
