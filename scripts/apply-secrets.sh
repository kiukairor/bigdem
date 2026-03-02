#!/bin/bash
# PULSE — Apply all secrets to Kubernetes from config.env
# Usage: ./scripts/apply-secrets.sh [namespace]

set -e

NAMESPACE=${1:-pulse-prod}
CONFIG_FILE="$(dirname "$0")/../config.env"

if [ ! -f "$CONFIG_FILE" ]; then
  echo "ERROR: config.env not found at $CONFIG_FILE"
  echo "Copy config.env.example to config.env and fill in your values"
  exit 1
fi

# Load config
export $(grep -v '^#' "$CONFIG_FILE" | grep -v '^$' | xargs)

echo "Applying secrets to namespace: $NAMESPACE"

# Anthropic
kubectl create secret generic anthropic-secret \
  --from-literal=api-key="$ANTHROPIC_API_KEY" \
  --from-literal=model="$CLAUDE_MODEL" \
  -n "$NAMESPACE" --dry-run=client -o yaml | kubectl apply -f -

# New Relic
kubectl create secret generic newrelic-secret \
  --from-literal=license-key="$NEW_RELIC_LICENSE_KEY" \
  --from-literal=account-id="$NEW_RELIC_ACCOUNT_ID" \
  -n "$NAMESPACE" --dry-run=client -o yaml | kubectl apply -f -

# PostgreSQL
kubectl create secret generic postgres-secret \
  --from-literal=username="$POSTGRES_USER" \
  --from-literal=password="$POSTGRES_PASSWORD" \
  --from-literal=database="$POSTGRES_DB" \
  --from-literal=host="$POSTGRES_HOST" \
  --from-literal=port="$POSTGRES_PORT" \
  -n "$NAMESPACE" --dry-run=client -o yaml | kubectl apply -f -

# Redis
kubectl create secret generic redis-secret \
  --from-literal=host="$REDIS_HOST" \
  --from-literal=port="$REDIS_PORT" \
  -n "$NAMESPACE" --dry-run=client -o yaml | kubectl apply -f -

# App config
kubectl create secret generic app-secret \
  --from-literal=demo-city="$DEMO_CITY" \
  --from-literal=demo-user-id="$DEMO_USER_ID" \
  --from-literal=demo-user-name="$DEMO_USER_NAME" \
  --from-literal=cb-failure-threshold="$CB_FAILURE_THRESHOLD" \
  --from-literal=cb-recovery-timeout="$CB_RECOVERY_TIMEOUT_SECONDS" \
  -n "$NAMESPACE" --dry-run=client -o yaml | kubectl apply -f -

# GHCR pull secret (needs GITHUB_USER and GITHUB_PAT env vars)
if [ -n "$GITHUB_USER" ] && [ -n "$GITHUB_PAT" ]; then
  kubectl create secret docker-registry ghcr-secret \
    --docker-server=ghcr.io \
    --docker-username="$GITHUB_USER" \
    --docker-password="$GITHUB_PAT" \
    -n "$NAMESPACE" --dry-run=client -o yaml | kubectl apply -f -
  echo "GHCR pull secret applied"
else
  echo "WARN: GITHUB_USER or GITHUB_PAT not set, skipping GHCR secret"
fi

echo ""
echo "All secrets applied to $NAMESPACE"
kubectl get secrets -n "$NAMESPACE"
