# PULSE Demo Runbook

Three demos. Each builds on the last.

| Demo | Status | Story |
|------|--------|-------|
| Demo 1 — Light | Working | NR finds the bug, human reverts |
| Demo 2 — Cloud Agent | To build | NR wakes a cloud Claude Code agent via webhook; agent uses NR MCP + codebase knowledge to fix |
| Demo 3 — Full Loop | To build | NR SRE Agent investigates, creates GitHub issue, Pi Claude fixes |

---

## Demo 1 — Light: NR Bug Investigation (Working)

A developer pushes a bad commit. NR shows exactly where and why. You find it
and revert it manually. Fast, reliable, no external dependencies.

### Prerequisites

GitHub Secrets required for NR deployment markers:
- `NEW_RELIC_USER_API_KEY` — NR User API key (not license key)
- `NR_ENTITY_GUID_AI_SVC` — Entity GUID for `pulse-ai-svc`
- `NR_ENTITY_GUID_SESSION_SVC` — Entity GUID for `pulse-session-svc`

All three go in GitHub → repo → Settings → Secrets and variables → Actions.

---

### Bug 1 — AI Slow (ai-svc)

**Story**: Developer removes the Redis recommendation cache to prevent stale
AI picks. Every call now hits the LLM live.

**NR signal**: ai-svc p99 spikes from ~100ms → 3–8s. Distributed Trace shows
every request ending with a live Gemini/Claude call, zero cache spans.
Deployment marker sits at the exact inflection point on the latency chart.

#### Trigger

```bash
cd $(git rev-parse --show-toplevel)
cp demos/sources/ai-svc-main-bug-ai-slow.py services/ai-svc/main.py
cp demos/sources/pulse-ai-dontask-main-bug-ai-slow.py services/pulse-ai-dontask/main.py
sed -i 's/BUG_AI_SLOW: "false"/BUG_AI_SLOW: "true"/' infra/helm/ai-svc/values.yaml
sed -i 's/BUG_AI_SLOW: "false"/BUG_AI_SLOW: "true"/' infra/helm/pulse-ai-dontask/values.yaml
git add services/ai-svc/main.py services/pulse-ai-dontask/main.py \
        infra/helm/ai-svc/values.yaml infra/helm/pulse-ai-dontask/values.yaml
git commit -m "fix: disable recommendation cache to prevent stale AI responses"
git push origin main
```

Check state at any time: `grep BUG_AI_SLOW infra/helm/ai-svc/values.yaml infra/helm/pulse-ai-dontask/values.yaml`

Wait ~5 min for CI to build and ArgoCD to deploy. NR marker appears ~2 min
after push (when CI marker job runs).

#### Investigate in NR

1. APM → pulse-ai-svc → Summary. Vertical line = deployment marker.
2. Click the marker → commit message is shown.
3. Compare latency before/after.
4. Open a slow trace → Distributed Trace → spot the live Gemini span (2–5s).
5. NR AI Monitoring → every request shows LLM call, zero cache hits.

#### Revert

```bash
git revert HEAD --no-edit
git push origin main
```

Second marker appears ~2 min later. Latency returns to baseline within one
cache warmup cycle (~5 min).

---

### Bug 2 — Memory Leak / Connection Pool Exhaustion (session-svc)

**Story**: Developer caches DB connections per user to reduce pool churn.
Connections are never returned. Pool (10 connections) exhausts after 10 unique
users. All subsequent DB ops fail.

**NR signal**: session-svc error rate climbs to 100%. DB spans show
`PoolError: connection pool exhausted`. Infrastructure shows RAM growing steadily.

#### Trigger

```bash
cd $(git rev-parse --show-toplevel)
cp demos/sources/session-svc-main-bug-memory-leak.py services/session-svc/main.py
git add services/session-svc/main.py
git commit -m "perf: cache database connections per user to reduce pool contention"
git push origin main
```

Accelerate with Locust:

```bash
cd simulation/locust
locust -f locustfile.py --host https://pulse.test:30443 \
  --user-classes SaveUser BaselineUser --users 20 --spawn-rate 3 --headless
```

#### Investigate in NR

1. APM → pulse-session-svc → Summary. Marker at the commit.
2. Error rate climbs to 100%.
3. Failing trace → DB span: `PoolError: connection pool exhausted`.
4. Infrastructure → session-svc → Memory chart: steady climb from the marker.
5. Logs in Context → stack trace pinpoints `_get_conn`.

#### Revert

```bash
git revert HEAD --no-edit
git push origin main
```

Stop Locust. Second marker appears. New session creations succeed again.

---

### Demo 1 Flow

```
presenter:   [trigger command]
             ↓ ~2 min
NR chart:    vertical marker labelled with the commit message
NR chart:    metric line diverges RIGHT at the marker
presenter:   "something changed at 14:32..."
             clicks marker → sees commit → traces → root cause

presenter:   git revert HEAD --no-edit && git push
             ↓ ~2 min
NR chart:    second marker, metrics recover
```

**Talking points:**
- "The deployment marker landed before I even knew there was a problem"
- "NR connected the latency spike to the exact commit in one click"
- "From alert to root cause: under 2 minutes"

---

---

## Demo 2 — Webhook Relay → Pi Claude + NR MCP (To Build)

**Status: architecture confirmed, not yet built.**

NR fires an alert. Workflow Automation POSTs to a public GCP VM — which is
purely a relay. The GCP VM SSHes into the Pi via Tailscale and writes a
trigger file. A local file watcher on the Pi detects it and wakes Claude Code.
Claude Code uses the NR MCP server for live telemetry context and its
knowledge of the codebase to revert, analyse, fix, and redeploy.

```
Bad commit → NR alert fires
    ↓
NR Workflow Automation: internal.http.post → https://<gcp-vm>/sre-wake
    ↓
GCP VM (relay only — no Claude Code):
    — receives webhook
    — SSHes into Pi via Tailscale
    — writes trigger file: /home/kiu/bigdem/versus/.sre-demo2-trigger
    — returns 202 immediately
    ↓
Pi file watcher detects trigger file
    — spawns: claude -p DEMO2_AGENT.md
    ↓
Claude Code on Pi:
    1. Reads alert context from trigger file
    2. NR MCP: execute_nrql_query → slowest transactions, error rate
    3. NR MCP: list_recent_issues → iRCA root cause
    4. git log → find and confirm bad commit
    5. Commit 1: git revert + push (CI starts, service recovers ~7 min)
    6. Analyse diff + write proper fix
    7. Commit 2: fix + push
    ↓
Pi CI (arm64) builds both commits → ArgoCD deploys → NR shows recovery
```

**What makes this different from Demo 1:**
- NR wakes the agent directly — no human, no GitHub issue as intermediary
- Agent queries NR live via MCP instead of reading pre-baked issue content
- GCP VM is a thin public relay — all intelligence stays on the Pi

**What stays the same:**
- Claude Code runs on the Pi (same machine, same NR MCP, same codebase)
- Two-commit flow: fast revert + proper fix
- CI + ArgoCD handles the deploy

**Setup:** See `docs/demo2-relay-setup.md` (to be written).
Agent prompt: `DEMO2_AGENT.md` (to be written).

### Trigger (same constraint as all SRE demos)

Must use git commit — not `kubectl set env`. NR needs a CI deployment marker
to correlate the alert to a SHA.

```bash
cd /home/kiu/bigdem/versus
cp demos/sources/ai-svc-main-bug-ai-slow.py services/ai-svc/main.py
git add services/ai-svc/main.py
git commit -m "fix: disable recommendation cache to prevent stale AI responses"
git push origin main

cd simulation/locust
.venv/bin/locust -f locustfile.py --host https://pulse.test:30443 \
  --headless --users 10 --spawn-rate 2 --run-time 15m
```

---

---

## Demo 3 — Full Loop: NR SRE Agent → GitHub Issue → Pi Claude (To Build)

**Status: architecture confirmed, NR SRE Agent wiring in progress.**

The NR SRE Agent is the first responder — it investigates inside NR, then
creates a GitHub issue as a structured handoff. Pi Claude picks up the issue
and remediates autonomously.

```
NR alert fires
    ↓
NR Workflow Automation → AI agent notification destination → NR SRE Agent
    ↓
NR SRE Agent investigates (iRCA, telemetry, deployment correlation)
NR SRE Agent creates GitHub issue labelled sre-remediate (pre-approved)
    ↓
Pi cron (every 1 min): claude -p SRE_AGENT.md
    — reads NR SRE Agent's investigation
    — investigates repo to find/confirm bad commit
    — Commit 1: git revert + push
    — Commit 2: proper fix + push
    — closes issue with audit report
```

**Two agents, clear roles:**
- **NR SRE Agent**: NR-native observer — investigates inside NR, creates handoff issue
- **Pi Claude** (`SRE_AGENT.md`): autonomous engineer — reads handoff, fixes code

**Setup:** See `docs/nr-sre-agent-setup.md`.

### Trigger

Same as Demo 2 — git commit required, not `kubectl set env`.

### Verify the loop

```bash
gh issue list --label sre-remediate --state open --repo kiukairor/bigdem
tail -f ~/pulse-sre-agent.log
gh issue list --label sre-resolved --state closed --repo kiukairor/bigdem
```

---

## Useful commands

```bash
# Recent commits
git log --oneline -5

# What image is live on a pod
kubectl get deployment ai-svc -n pulse-prod \
  -o jsonpath='{.spec.template.spec.containers[0].image}'

# Force ArgoCD sync immediately
kubectl patch application ai-svc -n argocd --type merge \
  -p '{"operation":{"initiatedBy":{"username":"admin"},"sync":{"syncStrategy":{"hook":{}}}}}'
```
