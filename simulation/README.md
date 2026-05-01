# PULSE — Load & Browser Simulation

Two complementary tools covering different NR signal layers:

| Tool | What it generates | NR surface |
|------|------------------|------------|
| Locust | HTTP load on backend APIs | APM throughput, spans, errors, Distributed Tracing |
| NR Synthetics | Real Chrome browser sessions | Browser JS Errors, PageView, AJAX timeline, Session Replay |

---

## Locust — backend API load

Targets the backend services via the pulse-shell proxy at `https://pulse.test:30443`.

Three user classes (mix them to match the demo scenario):

| Class | What it does | Good for |
|-------|-------------|----------|
| `BaselineUser` | Browses events, reads details | Establishing normal APM baseline |
| `AIUser` | Fires `POST /recommendations` repeatedly | Accelerating Bug 1 (BUG_AI_SLOW) visibility |
| `SaveUser` | Creates sessions, saves/unsaves events | Accelerating Bug 3 (BUG_MEMORY_LEAK) growth |

### Run

```bash
cd simulation/locust
pip install -r requirements.txt
locust -f locustfile.py --host https://pulse.test:30443
# Open http://localhost:8089
```

### Recommended settings per demo moment

| Demo moment | Users | Spawn rate | Notes |
|-------------|-------|-----------|-------|
| Baseline (before bugs) | 5 | 1 | Low steady APM traffic |
| Bug 1 (AI slow) | 10 AI users | 2 | Each req takes 8s → p99 spike |
| Bug 3 (memory leak) | 30 Save users | 5 | Combine with Bug 4 for fastest growth |
| Bug 4 simulation | 50 Baseline | 10 | Mimics the 1s poll (~60 rpm) |

Run from the Pi directly (`locust --headless -u 10 -r 2`) or from your laptop if `pulse.test` resolves.

---

## NR Synthetics — real browser journeys

Scripted Browser monitors that run actual Chrome sessions against `pulse.test:30443`.
Each run fires the NR Browser SPA agent, generating Browser-tier signals invisible to Locust.

### Scripts

| File | User journey | NR signal |
|------|-------------|-----------|
| `baseline-journey.js` | Load feed, filter by category, open event modal | PageView, BrowserInteraction, AjaxRequest |
| `tech-save-bug.js` | Filter TECH, click Save | JavaScriptError (TypeError), BrowserInteraction |
| `ai-panel-journey.js` | Load AI panel, toggle off with reason, re-enable | AjaxRequest latency (8s with BUG_AI_SLOW), UserAIOptOut custom event |

### Why a private location is required

`pulse.test:30443` is a local Raspberry Pi cluster — NR's public Synthetics locations cannot reach it. You need a **Synthetics Job Manager (SJM)** running inside the cluster (or on the Pi) as a private location.

### Setup — Synthetics Job Manager

**Step 1** — Create a private location in NR console:  
`one.newrelic.com` → Synthetics → Private Locations → **Create private location**  
Copy the key.

**Step 2** — Find the Pi's node IP:
```bash
kubectl get nodes -o wide | awk 'NR>1{print $6}'
```

**Step 3** — Edit `sjm-deployment.yaml`:
- Replace `PASTE_PRIVATE_LOCATION_KEY_HERE` with your key
- Replace `NODE_IP` with the Pi's IP from Step 2

**Step 4** — Deploy:
```bash
kubectl apply -f simulation/synthetics/sjm-deployment.yaml
kubectl get pods -n nr-synthetics   # wait for Running
```

**Step 5** — Create monitors in NR console:  
`one.newrelic.com` → Synthetics → **Create monitor** → Scripted Browser  
- Paste the script content from each `.js` file
- Select your private location
- Set cadence (1 min for `tech-save-bug.js`, 2 min for others)

### Verify it works

After creating the `baseline-journey.js` monitor:
1. NR → Browser → **pulse-shell** → Page views — should show a new entry from `Synthetics`
2. NR → Browser → **pulse-shell** → AJAX — `/api/event-svc/events` calls from Synthetics
3. After `tech-save-bug.js` runs: NR → Browser → **pulse-shell** → JS Errors → `TypeError: Cannot read properties of undefined (reading 'tags')`

---

## Signal coverage map

```
                     Locust      Synthetics
                     ------      ----------
APM spans              ✅           ✅ (via proxy)
APM throughput         ✅           ✅
Distributed Tracing    ✅           ✅ (browser → backend)
Browser PageView        ✗           ✅
Browser JS Errors       ✗           ✅  ← only way to trigger BUG_TECH_SAVE
Browser AJAX timeline   ✗           ✅
Session Replay          ✗           ✅ (if enabled)
NR custom events        ✅           ✅ (UserAIOptOut from ai-panel journey)
Infrastructure          ✅ (load)    ✅ (load)
```
