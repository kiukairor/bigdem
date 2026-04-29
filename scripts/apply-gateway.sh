#!/usr/bin/env bash
# Installs NGINX Gateway Fabric + Kubernetes Gateway API for PULSE.
# Run once on a fresh cluster (or after a full wipe).
# Safe to re-run — all steps are idempotent.
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
REPO_ROOT="$(cd "$SCRIPT_DIR/.." && pwd)"
GW_DIR="$REPO_ROOT/infra/gateway"

# ── 1. Kubernetes Gateway API CRDs (v1.3.0 standard channel) ────────────────
echo "==> [1/6] Applying Kubernetes Gateway API CRDs v1.3.0..."
kubectl apply -f https://github.com/kubernetes-sigs/gateway-api/releases/download/v1.3.0/standard-install.yaml

# ── 2. NGINX Gateway Fabric CRDs (v1.6.1) ───────────────────────────────────
echo "==> [2/6] Applying NGINX Gateway Fabric CRDs v1.6.1..."
kubectl apply -f https://raw.githubusercontent.com/nginx/nginx-gateway-fabric/v1.6.1/deploy/crds.yaml

# ── 3. NGINX Gateway Fabric DaemonSet (namespace + RBAC + DS + Service) ─────
echo "==> [3/6] Applying NGINX Gateway Fabric DaemonSet..."
kubectl apply -f "$GW_DIR/01-fabric-gw-ds.yaml"

# ── 4. TLS certificate ───────────────────────────────────────────────────────
echo "==> [4/6] Generating TLS certificate..."
chmod +x "$GW_DIR/scripts/gen-tls.sh"
bash "$GW_DIR/scripts/gen-tls.sh"

# ── 5. Gateway resource ──────────────────────────────────────────────────────
echo "==> [5/6] Applying Gateway resource..."
kubectl apply -f "$GW_DIR/02-gateway.yaml"

# ── 6. HTTPRoutes ────────────────────────────────────────────────────────────
echo "==> [6/6] Applying HTTPRoutes for PULSE services..."
kubectl apply -f "$GW_DIR/03-httproutes.yaml"

# ── Done ─────────────────────────────────────────────────────────────────────
PI_IP=$(kubectl get nodes -o jsonpath='{.items[0].status.addresses[?(@.type=="InternalIP")].address}' 2>/dev/null || echo "<PI_IP>")
echo ""
echo "Gateway is up. Add to /etc/hosts on your local machine:"
echo ""
echo "  $PI_IP  pulse.test feed.pulse.test event.pulse.test ai.pulse.test session.pulse.test"
echo ""
echo "Access PULSE:"
echo "  http://pulse.test:30080     (HTTP)"
echo "  https://pulse.test:30443    (HTTPS — accept the self-signed cert warning)"
echo ""
echo "Check gateway pod:"
echo "  kubectl get pods -n nginx-gateway"
echo "  kubectl get httproutes -n pulse-prod"
