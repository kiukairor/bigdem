# PULSE — Kubernetes Gateway (NGINX Gateway Fabric)

Replaces `kubectl port-forward` with a permanent, host-accessible gateway.

## What this sets up

| Component | Version | Source |
|---|---|---|
| Kubernetes Gateway API CRDs | v1.3.0 (standard channel) | `kubernetes-sigs/gateway-api` upstream release |
| NGINX Gateway Fabric CRDs | v1.6.1 | `nginx/nginx-gateway-fabric` upstream release |
| NGINX Gateway Fabric DaemonSet | v1.6.1 | Copied verbatim from `kiukairor/gateway-api-nginx-fabric` |
| Gateway resource | — | Copied verbatim from `kiukairor/gateway-api-nginx-fabric` |
| HTTPRoutes | — | Written for PULSE (this repo) |
| TLS certificate | — | Locally generated self-signed (openssl, 10-year validity) |

**No version changes were made** — the same image tags and CRD versions from `kiukairor/gateway-api-nginx-fabric` were used as-is.

The only modification to `fabric-gw-ds.yaml` relative to the upstream repo:
- NodePort values (`30080`, `30443`) are set inline in the Service spec instead of via kustomize patches, since we don't use kustomize here.

## Routing

| Hostname | Backend | Notes |
|---|---|---|
| `pulse.test` | pulse-shell:3000 | Only public entry point |

Both HTTP (30080) and HTTPS (30443) listeners are active. TLS terminates at the gateway.

pulse-shell proxies everything else internally via Next.js `rewrites()`:

| Browser path | Proxied to |
|---|---|
| `/_mfe/feed/*` | `http://pulse-feed:3001/*` |
| `/_mfe/profile/*` | `http://pulse-profile:3002/*` |
| `/api/event-svc/*` | `http://event-svc:8080/*` |
| `/api/ai-svc/*` | `http://ai-svc:8082/*` |
| `/api/session-svc/*` | `http://session-svc:8081/*` |

The browser never leaves `pulse.test:30443`.

## Install

```bash
# From repo root — run once, idempotent
chmod +x scripts/apply-gateway.sh
./scripts/apply-gateway.sh
```

The script applies in order:
1. K8s Gateway API CRDs (from upstream URL)
2. NGINX Gateway Fabric CRDs (from upstream URL)
3. `infra/gateway/01-fabric-gw-ds.yaml` — namespace, RBAC, DaemonSet, NodePort Service
4. `infra/gateway/scripts/gen-tls.sh` — generates cert + creates `nginx-gw-fabric-tls` secret
5. `infra/gateway/02-gateway.yaml` — Gateway resource
6. `infra/gateway/03-httproutes.yaml` — HTTPRoutes for all PULSE services

## /etc/hosts (local machine)

```
<PI_IP>  pulse.test feed.pulse.test event.pulse.test ai.pulse.test session.pulse.test
```

Replace `<PI_IP>` with the Pi's IP. The script prints it for you.

## Verify

```bash
kubectl get pods -n nginx-gateway
kubectl get gateway -n nginx-gateway
kubectl get httproutes -n pulse-prod
```

Expected gateway pod state: `2/2 Running` (init container exits, then gateway + nginx containers run).

## Regenerate TLS cert

```bash
bash infra/gateway/scripts/gen-tls.sh
```

The cert covers `pulse.test` and `*.pulse.test` (wildcard). Browsers will show an untrusted cert warning — accept it, or install `infra/gateway/tls/tls.crt` into your local trust store.

## Revert

```bash
kubectl delete -f infra/gateway/03-httproutes.yaml
kubectl delete -f infra/gateway/02-gateway.yaml
kubectl delete -f infra/gateway/01-fabric-gw-ds.yaml
kubectl delete secret nginx-gw-fabric-tls -n nginx-gateway
# CRDs are cluster-wide — only remove if no other gateway controllers exist:
kubectl delete -f https://raw.githubusercontent.com/nginx/nginx-gateway-fabric/v1.6.1/deploy/crds.yaml
kubectl delete -f https://github.com/kubernetes-sigs/gateway-api/releases/download/v1.3.0/standard-install.yaml
```

## Source references

- `kiukairor/gateway-api-nginx-fabric` — base DaemonSet and Gateway manifests
- `kubernetes-sigs/gateway-api` v1.3.0 — standard-install.yaml (CRDs)
- `nginx/nginx-gateway-fabric` v1.6.1 — deploy/crds.yaml (NGINX CRDs)
