# PULSE Demo Cheatsheet

## Full demo runbook

```bash
# 1. Run the full narrative (3 min baseline → inject bug → 3 min spike)
./scripts/demo_ai_slow.sh

# 2. While Locust is running, open NR:
#    APM → ai-svc → Response time (watch the spike after the marker)
#    APM → pulse-ai-dontask → Response time (same spike)
#    AI Monitoring → both services showing 8s+ latency

# 3. Fix the bug live on stage
./scripts/revert_ai_slowness.sh
```

---


## Full narrative demo (AI latency story)

```bash
./scripts/demo_ai_slow.sh          # 3 min baseline → inject bug → 3 min spike
./scripts/demo_ai_slow.sh 60       # same but 1 min phases (quick test)
```

What happens:
1. Locust runs 3 min → NR shows clean latency
2. Script injects `BUG_AI_SLOW` via `kubectl set env` (~15s pod restart, no CI)
3. NR deployment marker fires instantly via API
4. Locust runs 3 more min → NR shows 8s spike

After: `./scripts/revert_ai_slowness.sh` to fix the bug live on stage.

---

## Individual controls

```bash
./scripts/trigger_ai_slowness.sh   # enable bug (instant kubectl + NR marker)
./scripts/revert_ai_slowness.sh    # disable bug (instant kubectl + NR marker)
```

---

## Locust only

```bash
cd simulation/locust

# Headless full mix
.venv/bin/locust -f locustfile.py --host https://pulse.test:30443 \
  --headless --users 30 --spawn-rate 3 --run-time 10m

# Interactive UI at http://localhost:8089
.venv/bin/locust -f locustfile.py --host https://pulse.test:30443
```

| Scenario | Users | Spawn |
|----------|-------|-------|
| Baseline APM | 5 | 1 |
| AI stress | 10 | 2 |
| Memory leak (Bug 3) | 30 | 3 |
| Live refresh (Bug 5) | 50 | 5 |
| NR AI Monitoring (chat) | 10 | 2 |
| Full mix | 30 | 3 |
