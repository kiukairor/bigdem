# PULSE Demo Runbook — Controlled Bug Scenarios

Each bug is triggered by copying a broken source file and committing it.
New Relic shows a deployment marker at the exact moment of the deploy,
labelled with the commit message. Metrics spike right at that line.
Revert with `git revert HEAD` — a second marker appears and metrics recover.

---

## Prerequisites

GitHub Secrets that must be set before markers appear in NR:
- `NEW_RELIC_USER_API_KEY` — NR User API key (not license key). Create at
  newrelic.com → Account → API Keys → User key.
- `NR_ENTITY_GUID_AI_SVC` — Entity GUID for `pulse-ai-svc`.
  Find it: NR UI → APM → pulse-ai-svc → Settings → Application → Entity GUID.
- `NR_ENTITY_GUID_SESSION_SVC` — same, for `pulse-session-svc`.

All three secrets go in GitHub → repo → Settings → Secrets and variables → Actions.

---

## Bug 1 — AI Slow (ai-svc)

**Story**: A developer removes the Redis recommendation cache because they
suspect users are seeing stale AI picks. Every call now hits the LLM live.

**NR signal**: ai-svc p99 spikes from ~100ms → 3-8s. Distributed Trace shows
every request ending with a live Gemini/Claude call, zero cache spans.
Deployment marker sits at the exact inflection point on the latency chart.

### Trigger

```bash
cd $(git rev-parse --show-toplevel)
cp demos/sources/ai-svc-main-bug-ai-slow.py services/ai-svc/main.py
git add services/ai-svc/main.py
git commit -m "fix: disable recommendation cache to prevent stale AI responses"
git push origin main
```

Wait ~5 min for CI to build and ArgoCD to deploy. The NR marker appears as
soon as the CI marker job runs (~2 min after push).

### Investigate in NR

1. Open APM → pulse-ai-svc → Summary. Vertical line = deployment marker.
2. Click the marker → "fix: disable recommendation cache..." commit is shown.
3. Compare latency before/after the line.
4. Open a slow trace → Distributed Trace → spot the live Gemini span (2-5s).
5. NR AI Monitoring → every request shows LLM call (no cache hits).

### Revert

```bash
git revert HEAD --no-edit
git push origin main
```

Second marker appears ~2 min later. Latency returns to baseline within one
cache warmup cycle (~5 min).

---

## Bug 2 — Memory Leak / Connection Pool Exhaustion (session-svc)

**Story**: A developer caches database connections per user to reduce pool
churn. Connections are never returned to the pool. The pool (10 connections)
exhausts after 10 unique users touch the service. All subsequent DB ops fail.

**NR signal**: session-svc error rate climbs to 100% as pool exhausts.
DB spans show `PoolError: connection pool exhausted`. NR Infrastructure shows
session-svc RAM growing steadily until errors start.

### Trigger

```bash
cd $(git rev-parse --show-toplevel)
cp demos/sources/session-svc-main-bug-memory-leak.py services/session-svc/main.py
git add services/session-svc/main.py
git commit -m "perf: cache database connections per user to reduce pool contention"
git push origin main
```

Start Locust to accelerate the failure (10+ unique user IDs exhaust the pool):

```bash
cd simulation/locust
locust -f locustfile.py --host https://pulse.test:30443 \
  --user-classes SaveUser BaselineUser --users 20 --spawn-rate 3 --headless
```

Pool exhausts in under 2 minutes. Without load, it exhausts after 10 manual
session creations.

### Investigate in NR

1. Open APM → pulse-session-svc → Summary. Marker appears at the commit.
2. Error rate climbs to 100% after pool exhaustion.
3. Open a failing trace → DB span shows `PoolError: connection pool exhausted`.
4. NR Infrastructure → session-svc → Memory chart: steady climb from the marker.
5. NR Logs in Context on a failing request → stack trace pinpoints `_get_conn`.

### Revert

```bash
git revert HEAD --no-edit
git push origin main
```

Stop Locust. Second marker appears. New session creations succeed again.

---

## Full Demo Flow (either bug)

```
presenter:   [trigger command above]
             ↓ ~2 min
NR chart:    vertical marker labelled with that commit message
NR chart:    metric line diverges RIGHT at the marker
presenter:   "something changed at 14:32..."
             clicks marker → sees commit message → traces → root cause

presenter:   git revert HEAD --no-edit && git push origin main
             ↓ ~2 min
NR chart:    second marker, metrics recover
```

---

## Useful commands

```bash
# Find commit hash after push
git log --oneline -5

# Check what image is live on the pod
kubectl get deployment ai-svc -n pulse-prod \
  -o jsonpath='{.spec.template.spec.containers[0].image}'

# Force ArgoCD sync without waiting
kubectl patch application ai-svc -n argocd --type merge \
  -p '{"operation":{"initiatedBy":{"username":"admin"},"sync":{"syncStrategy":{"hook":{}}}}}'
```
