#!/usr/bin/env bash
# Full narrative demo: 3 min baseline → inject bug + marker → 3 min spike
# NR story: clean latency → deployment marker → 8s spike visible in Distributed Tracing
set -e

REPO_ROOT="$(cd "$(dirname "$0")/.." && pwd)"
LOCUST_DIR="$REPO_ROOT/simulation/locust"
PHASE_SECONDS="${1:-180}"   # override: ./demo_ai_slow.sh 60  (1 min phases for a quick test)

source "$REPO_ROOT/config.env" 2>/dev/null || true

echo "==> Phase 1: baseline traffic (${PHASE_SECONDS}s) — watch NR for clean latency"
cd "$LOCUST_DIR"
.venv/bin/locust -f locustfile.py --host https://pulse.test:30443 \
  --headless --users 10 --spawn-rate 2 \
  --run-time "${PHASE_SECONDS}s" \
  AIUser BaselineUser ChatUser

echo ""
echo "==> Injecting BUG_AI_SLOW..."

# Instant K8s env update on both AI services (no CI)
kubectl set env deployment/ai-svc -n pulse-prod BUG_AI_SLOW=true
kubectl set env deployment/pulse-ai-dontask -n pulse-prod BUG_AI_SLOW=true

# Fire NR markers for both services immediately
NR_API="${NR_API_URL:-https://api.eu.newrelic.com/graphql}"
if [[ -n "$NEW_RELIC_USER_API_KEY" && -n "$NR_ENTITY_GUID_AI_SVC" ]]; then
  curl -s -X POST "$NR_API" \
    -H "Api-Key: $NEW_RELIC_USER_API_KEY" \
    -H "Content-Type: application/json" \
    -d "{\"query\": \"mutation { changeTrackingCreateDeployment(deployment: { entityGuid: \\\"$NR_ENTITY_GUID_AI_SVC\\\", version: \\\"bug-ai-slow\\\", description: \\\"demo: BUG_AI_SLOW enabled\\\" }) { deploymentId } }\"}" \
    > /dev/null
fi
if [[ -n "$NEW_RELIC_USER_API_KEY" && -n "$NR_ENTITY_GUID_PULSE_AI_DONTASK" ]]; then
  curl -s -X POST "$NR_API" \
    -H "Api-Key: $NEW_RELIC_USER_API_KEY" \
    -H "Content-Type: application/json" \
    -d "{\"query\": \"mutation { changeTrackingCreateDeployment(deployment: { entityGuid: \\\"$NR_ENTITY_GUID_PULSE_AI_DONTASK\\\", version: \\\"bug-ai-slow\\\", description: \\\"demo: BUG_AI_SLOW enabled\\\" }) { deploymentId } }\"}" \
    > /dev/null
fi
echo "NR markers fired."

# Wait for both pods to be ready
kubectl rollout restart deployment/ai-svc -n pulse-prod
kubectl rollout restart deployment/pulse-ai-dontask -n pulse-prod
kubectl rollout status deployment/ai-svc -n pulse-prod --timeout=60s
kubectl rollout status deployment/pulse-ai-dontask -n pulse-prod --timeout=60s

# Flush Redis so every request hits the 8s sleep (no cache hits masking the spike)
kubectl exec -n pulse-prod deploy/redis -- redis-cli FLUSHDB > /dev/null
echo "Redis flushed. Pod ready. Starting phase 2..."

echo ""
echo "==> Phase 2: traffic with 8s AI delay (${PHASE_SECONDS}s) — watch NR Distributed Tracing spike"
.venv/bin/locust -f locustfile.py --host https://pulse.test:30443 \
  --headless --users 10 --spawn-rate 2 \
  --run-time "${PHASE_SECONDS}s" \
  AIUser BaselineUser ChatUser

echo ""
echo "==> Demo complete."
echo "    NR: APM → ai-svc → Distributed Tracing — marker + spike should be visible"
echo "    Run ./scripts/revert_ai_slowness.sh to fix the bug live"

# GitOps cleanup in background
cd "$REPO_ROOT"
sed -i 's/BUG_AI_SLOW: "false"/BUG_AI_SLOW: "true"/' infra/helm/ai-svc/values.yaml
sed -i 's/BUG_AI_SLOW: "false"/BUG_AI_SLOW: "true"/' infra/helm/pulse-ai-dontask/values.yaml
git add infra/helm/ai-svc/values.yaml infra/helm/pulse-ai-dontask/values.yaml
git commit -m "demo: enable BUG_AI_SLOW on ai-svc and pulse-ai-dontask"
(git stash 2>/dev/null; git pull --rebase origin main && git push origin main; git stash pop 2>/dev/null; true) &
