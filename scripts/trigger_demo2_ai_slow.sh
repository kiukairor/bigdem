#!/usr/bin/env bash
set -e

REPO_ROOT="$(cd "$(dirname "$0")/.." && pwd)"
cd "$REPO_ROOT"

source "$REPO_ROOT/config.env" 2>/dev/null || true

echo "==> Triggering BUG_AI_SLOW (values.yaml only — no CI rebuild, ~20s ArgoCD deploy)"

# 1. Flip both helm values
sed -i 's/BUG_AI_SLOW: "false"/BUG_AI_SLOW: "true"/' infra/helm/ai-svc/values.yaml
sed -i 's/BUG_AI_SLOW: "false"/BUG_AI_SLOW: "true"/' infra/helm/pulse-ai-dontask/values.yaml

# 2. Commit and push the bug
git add infra/helm/ai-svc/values.yaml infra/helm/pulse-ai-dontask/values.yaml
git commit -m "perf: disable recommendation cache to prevent stale AI responses"
git push origin main

BUG_SHA=$(git rev-parse HEAD)
CLEAN_SHA=$(git rev-parse HEAD~1)
CLEAN_DATE=$(git log -1 --format="%as" "$CLEAN_SHA")
CLEAN_MSG=$(git log -1 --format="%s" "$CLEAN_SHA")

echo "Bug commit:  $BUG_SHA"
echo "Clean SHA:   $CLEAN_SHA  ($CLEAN_DATE)"

# 3. Update SHA boundary in DEMO2_AGENT.md so the agent only looks at the bug commit
export _SHA="$CLEAN_SHA" _DATE="$CLEAN_DATE" _MSG="$CLEAN_MSG"
python3 - <<'PYEOF'
import re, os

sha = os.environ["_SHA"]
date = os.environ["_DATE"]
msg = os.environ["_MSG"]

path = "DEMO2_AGENT.md"
content = open(path).read()

old = r'Never inspect, revert, or reference any commit older than `[0-9a-f]+` \(\d{4}-\d{2}-\d{2},\n"[^"]*"\)'
new = f'Never inspect, revert, or reference any commit older than `{sha}` ({date},\n"{msg}")'

updated = re.sub(old, new, content)
if updated == content:
    print("WARNING: SHA boundary pattern not found in DEMO2_AGENT.md — update manually")
else:
    open(path, "w").write(updated)
    print(f"SHA boundary updated → {sha[:8]}")
PYEOF

# 4. Commit and push DEMO2_AGENT.md [skip ci]
git add DEMO2_AGENT.md
if ! git diff --cached --quiet; then
  git commit -m "chore: update agent SHA boundary to ${CLEAN_SHA:0:8} [skip ci]"
  git push origin main
fi

# 5. Fire NR deployment markers
NR_API="${NR_API_URL:-https://api.eu.newrelic.com/graphql}"
if [[ -n "$NEW_RELIC_USER_API_KEY" && -n "$NR_ENTITY_GUID_AI_SVC" ]]; then
  curl -s -X POST "$NR_API" \
    -H "Api-Key: $NEW_RELIC_USER_API_KEY" \
    -H "Content-Type: application/json" \
    -d "{\"query\": \"mutation { changeTrackingCreateDeployment(deployment: { entityGuid: \\\"$NR_ENTITY_GUID_AI_SVC\\\", version: \\\"bug-ai-slow\\\", description: \\\"demo2: BUG_AI_SLOW via values.yaml\\\" }) { deploymentId } }\"}" \
    > /dev/null && echo "NR marker fired: ai-svc"
fi
if [[ -n "$NEW_RELIC_USER_API_KEY" && -n "$NR_ENTITY_GUID_PULSE_AI_DONTASK" ]]; then
  curl -s -X POST "$NR_API" \
    -H "Api-Key: $NEW_RELIC_USER_API_KEY" \
    -H "Content-Type: application/json" \
    -d "{\"query\": \"mutation { changeTrackingCreateDeployment(deployment: { entityGuid: \\\"$NR_ENTITY_GUID_PULSE_AI_DONTASK\\\", version: \\\"bug-ai-slow\\\", description: \\\"demo2: BUG_AI_SLOW via values.yaml\\\" }) { deploymentId } }\"}" \
    > /dev/null && echo "NR marker fired: pulse-ai-dontask"
fi

echo ""
echo "Bug live. ArgoCD will deploy in ~20s."
echo "Agent SHA boundary: ${CLEAN_SHA:0:8} ($CLEAN_DATE)"
echo "Monitor: tail -f ~/pulse-demo2-agent.log"
