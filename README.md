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
| `session-svc` | Python + FastAPI | 8081 | Session management (Week 2) |

## Quick Start

### 1. Configure secrets
```bash
cp config.env.example config.env
# Edit config.env with your keys
```

### 2. Apply secrets to K8s
```bash
chmod +x scripts/apply-secrets.sh
./scripts/apply-secrets.sh pulse-prod
```

### 3. Seed the database
```bash
kubectl exec -n pulse-prod deploy/postgresql -- psql -U pulse -d pulse < db/seed.sql
```

### 4. Deploy via ArgoCD
```bash
kubectl apply -f argocd/app-of-apps.yaml
```

### 5. Access the app
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
        └── session-svc (Py)   ← sessions (Week 2)
              │
              ├── PostgreSQL   ← events, users, opt-out log
              └── Redis        ← session cache (Week 2)
```
