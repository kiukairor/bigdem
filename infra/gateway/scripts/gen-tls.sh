#!/usr/bin/env bash
# Generates a self-signed wildcard TLS certificate for *.pulse.local + pulse.local
# and creates/updates the nginx-gw-fabric-tls secret in the nginx-gateway namespace.
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
TLS_DIR="$SCRIPT_DIR/../tls"
mkdir -p "$TLS_DIR"

echo "==> Generating self-signed TLS certificate (*.pulse.local + pulse.local)..."
openssl req -x509 \
  -newkey rsa:4096 \
  -keyout "$TLS_DIR/tls.key" \
  -out   "$TLS_DIR/tls.crt" \
  -days  3650 \
  -nodes \
  -subj  "/CN=pulse.local/O=PULSE-local-dev" \
  -addext "subjectAltName=DNS:pulse.local,DNS:*.pulse.local"

echo "==> Creating/updating secret nginx-gw-fabric-tls in nginx-gateway namespace..."
kubectl create secret tls nginx-gw-fabric-tls \
  --cert="$TLS_DIR/tls.crt" \
  --key="$TLS_DIR/tls.key" \
  -n nginx-gateway \
  --dry-run=client -o yaml | kubectl apply -f -

echo "==> TLS cert written to $TLS_DIR and secret applied."
echo "    Valid for: pulse.local + *.pulse.local (3650 days)"
