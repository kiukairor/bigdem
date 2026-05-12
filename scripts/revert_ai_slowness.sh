#!/usr/bin/env bash
set -e

REPO_ROOT="$(cd "$(dirname "$0")/.." && pwd)"
VALUES="$REPO_ROOT/infra/helm/ai-svc/values.yaml"

source "$REPO_ROOT/config.env" 2>/dev/null || true

kubectl set env deployment/ai-svc -n pulse-prod BUG_AI_SLOW=false
kubectl set env deployment/pulse-ai-dontask -n pulse-prod BUG_AI_SLOW=false

NR_API="${NR_API_URL:-https://api.eu.newrelic.com/graphql}"
if [[ -n "$NEW_RELIC_USER_API_KEY" && -n "$NR_ENTITY_GUID_AI_SVC" ]]; then
  curl -s -X POST "$NR_API" \
    -H "Api-Key: $NEW_RELIC_USER_API_KEY" \
    -H "Content-Type: application/json" \
    -d "{\"query\": \"mutation { changeTrackingCreateDeployment(deployment: { entityGuid: \\\"$NR_ENTITY_GUID_AI_SVC\\\", version: \\\"fix-ai-slow\\\", description: \\\"fix: BUG_AI_SLOW disabled\\\" }) { deploymentId } }\"}" \
    > /dev/null
fi
if [[ -n "$NEW_RELIC_USER_API_KEY" && -n "$NR_ENTITY_GUID_PULSE_AI_DONTASK" ]]; then
  curl -s -X POST "$NR_API" \
    -H "Api-Key: $NEW_RELIC_USER_API_KEY" \
    -H "Content-Type: application/json" \
    -d "{\"query\": \"mutation { changeTrackingCreateDeployment(deployment: { entityGuid: \\\"$NR_ENTITY_GUID_PULSE_AI_DONTASK\\\", version: \\\"fix-ai-slow\\\", description: \\\"fix: BUG_AI_SLOW disabled\\\" }) { deploymentId } }\"}" \
    > /dev/null
fi
echo "NR deployment markers fired."

kubectl rollout restart deployment/ai-svc -n pulse-prod
kubectl rollout restart deployment/pulse-ai-dontask -n pulse-prod
kubectl rollout status deployment/ai-svc -n pulse-prod --timeout=60s
kubectl rollout status deployment/pulse-ai-dontask -n pulse-prod --timeout=60s

cd "$REPO_ROOT"
sed -i 's/BUG_AI_SLOW: "true"/BUG_AI_SLOW: "false"/' infra/helm/ai-svc/values.yaml
sed -i 's/BUG_AI_SLOW: "true"/BUG_AI_SLOW: "false"/' infra/helm/pulse-ai-dontask/values.yaml
git add infra/helm/ai-svc/values.yaml infra/helm/pulse-ai-dontask/values.yaml
git commit -m "fix: disable BUG_AI_SLOW on ai-svc and pulse-ai-dontask"
(git stash 2>/dev/null; git pull --rebase origin main && git push origin main; git stash pop 2>/dev/null; true) &

echo "Bug disabled. Both AI services back to normal."
