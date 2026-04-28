# PULSE ⚡

> Real-time London events feed with AI recommendations — built for observability demos with New Relic.

## Services

| Service | Tech | Port | Description |
|---|---|---|---|
| `pulse-shell` | Next.js (host MFE) | 3000 | App shell, layout, header |
| `pulse-feed` | Next.js (remote MFE) | 3001 | Events feed, AI toggle, recommendations panel |
| `pulse-profile` | Next.js (remote MFE) | 3002 | User profile (Week 2) |
| `event-svc` | Go + Gin | 8080 | Events CRUD, user preferences |
| `ai-svc` | Python + FastAPI | 8082 | Claude AI recommendations, circuit breaker |
| `session-svc` | Python + FastAPI | 8081 | Session management, Redis cache, saved events |

## Quick Start

### 1. Configure secrets
```bash
cp config.env.example config.env
# Edit config.env with your keys
```

### 2. Install prerequisites (if cluster is fresh)
```bash
# local-path StorageClass (for postgres/redis PVCs)
kubectl apply -f https://raw.githubusercontent.com/rancher/local-path-provisioner/v0.0.26/deploy/local-path-storage.yaml

# ArgoCD
kubectl create namespace argocd
kubectl apply -n argocd -f https://raw.githubusercontent.com/argoproj/argo-cd/v3.3.2/manifests/install.yaml
```

### 3. Apply secrets to K8s
```bash
chmod +x scripts/apply-secrets.sh
kubectl create namespace pulse-prod
./scripts/apply-secrets.sh pulse-prod

# GHCR pull secret (add GITHUB_USER + GITHUB_PAT to config.env first)
export $(grep -v '^#' config.env | grep -v '^$' | xargs)
kubectl create secret docker-registry ghcr-secret \
  --docker-server=ghcr.io \
  --docker-username="$GITHUB_USER" \
  --docker-password="$GITHUB_PAT" \
  -n pulse-prod --dry-run=client -o yaml | kubectl apply -f -
```

### 4. Deploy via ArgoCD
```bash
kubectl apply -f argocd/app-of-apps.yaml
```

### 5. Seed the database
```bash
cat db/seed.sql | kubectl exec -i -n pulse-prod postgresql-0 -- psql -U pulse -d pulse
```

### 6. Access the app
Add to `/etc/hosts`: `<PI_IP>  pulse.local`  
Open: http://pulse.local

## Observability Demo Script

See [docs/demo-script.md](docs/demo-script.md) for the full 15-minute NR demo walkthrough.

## Architecture

```
pulse-shell (host)
  └── loads pulse-feed MFE (Module Federation)
  └── loads pulse-profile MFE (Module Federation)
        │
        ├── event-svc (Go)     ← events, user prefs, opt-out logging
        ├── ai-svc (Python)    ← Claude API, circuit breaker, fallback
        └── session-svc (Py)   ← sessions, saved events
              │
              ├── PostgreSQL   ← events, users, opt-out log, saved events
              └── Redis        ← session cache
```
