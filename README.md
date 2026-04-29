# PULSE

> Real-time city events feed with AI-powered recommendations — built to demo New Relic observability on a live distributed system.

---

## Architecture

```mermaid
flowchart TB
    User(["Browser"])

    subgraph GW["NGINX Gateway Fabric — NodePort :30443"]
        direction LR
        HTTP["HTTP :30080"]
        HTTPS["HTTPS :30443\npulse.test"]
    end

    subgraph K8s["Kubernetes — namespace: pulse-prod"]
        Shell["pulse-shell\nNext.js host MFE · :3000"]

        subgraph MFE["Module Federation remotes (JS loaded into browser)"]
            Feed["pulse-feed\nNext.js · :3001\nevents grid · AI panel · save"]
            Profile["pulse-profile\nNext.js · :3002\n⬜ Week 2"]
        end

        subgraph Backends["Backend services"]
            EventSvc["event-svc\nGo + Gin · :8080\nevents · user prefs · opt-out log"]
            AiSvc["ai-svc\nPython + FastAPI · :8082\nClaude recs · circuit breaker"]
            SessionSvc["session-svc\nPython + FastAPI · :8081\nsessions · saved events"]
        end

        subgraph Data["Data layer"]
            PG[("PostgreSQL\nevents · users\nopt-out log · saved events")]
            Redis[("Redis\nsession cache\nAI rec cache")]
        end
    end

    Claude["Anthropic\nClaude API"]

    subgraph NR["New Relic"]
        NRBrowser["Browser agent\n⬜ snippet pending"]
        NREvent["APM: Go\npulse-event-svc"]
        NRAi["APM: Python\npulse-ai-svc"]
        NRSession["APM: Python\npulse-session-svc"]
    end

    User -- "HTTPS :30443" --> GW
    GW -- "pulse.test" --> Shell

    Shell -- "/_mfe/feed/* proxy" --> Feed
    Shell -- "/_mfe/profile/* proxy" --> Profile
    Shell -- "/api/event-svc/* proxy" --> EventSvc
    Shell -- "/api/ai-svc/* proxy" --> AiSvc
    Shell -- "/api/session-svc/* proxy" --> SessionSvc

    EventSvc --> PG
    SessionSvc --> PG
    SessionSvc --> Redis
    AiSvc --> Claude
    AiSvc -. "rec cache" .-> Redis

    User -. "distributed traces" .-> NRBrowser
    EventSvc -. "" .-> NREvent
    AiSvc -. "" .-> NRAi
    SessionSvc -. "" .-> NRSession
```

**Key design decisions:**

- Only `pulse.test` is exposed publicly — backends and MFEs are cluster-internal.
- pulse-shell proxies all MFE asset fetches and API calls via Next.js `rewrites()`. The browser never leaves `pulse.test:30443`.
- Module Federation loads MFE JavaScript into the browser — there is no server-to-server call between MFEs.
- NR Browser snippets must be injected into `_document.tsx` for pulse-shell and pulse-feed to enable distributed tracing from browser to backends.

---

## Services

| Service | Tech | Port | Description |
|---|---|---|---|
| `pulse-shell` | Next.js 14 (MFE host) | 3000 | App shell, header, city picker, routing |
| `pulse-feed` | Next.js 14 (MFE remote) | 3001 | Events grid, category filter, AI panel, save |
| `pulse-profile` | Next.js 14 (MFE remote) | 3002 | User profile, saved events (Week 2) |
| `event-svc` | Go 1.22 + Gin | 8080 | Events CRUD, user prefs, opt-out logging |
| `ai-svc` | Python 3.12 + FastAPI | 8082 | Claude recommendations, circuit breaker |
| `session-svc` | Python 3.12 + FastAPI | 8081 | Session management, Redis cache, saved events |

---

## Quick Start

### 1. Configure secrets
```bash
cp config.env.example config.env
# Fill in: ANTHROPIC_API_KEY, NEW_RELIC_LICENSE_KEY, NEW_RELIC_ACCOUNT_ID, GITHUB_USER, GITHUB_PAT
```

### 2. Install prerequisites (fresh cluster)
```bash
# local-path StorageClass (for postgres/redis PVCs)
kubectl apply -f https://raw.githubusercontent.com/rancher/local-path-provisioner/v0.0.26/deploy/local-path-storage.yaml

# ArgoCD
kubectl create namespace argocd
kubectl apply -n argocd -f https://raw.githubusercontent.com/argoproj/argo-cd/v3.3.2/manifests/install.yaml
```

### 3. Apply secrets
```bash
kubectl create namespace pulse-prod
chmod +x scripts/apply-secrets.sh
./scripts/apply-secrets.sh pulse-prod

# GHCR pull secret
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

### 6. Install the gateway
```bash
chmod +x scripts/apply-gateway.sh
./scripts/apply-gateway.sh
```

Add to `/etc/hosts` on your local machine (the script prints the exact line):
```
<PI_IP>  pulse.test
```

The app is available at `https://pulse.test:30443`. Accept the self-signed cert warning, or install `infra/gateway/tls/tls.crt` into your local trust store.

---

## New Relic Instrumentation

| Service | Agent | NR App Name | Status |
|---|---|---|---|
| pulse-shell | Browser (JS snippet) | pulse-shell | ⬜ snippet not yet added |
| pulse-feed | Browser (JS snippet) | pulse-feed | ⬜ snippet not yet added |
| event-svc | Go APM | pulse-event-svc | ✅ reporting |
| ai-svc | Python APM | pulse-ai-svc | ✅ reporting |
| session-svc | Python APM | pulse-session-svc | ✅ reporting |
| K8s nodes | Infrastructure | — | ✅ reporting |

**To add Browser monitoring:**
1. In NR: Add data → Browser → create app named `pulse-shell`, copy snippet
2. Paste into `frontends/pulse-shell/pages/_document.tsx` inside `<Head>`
3. Repeat for `pulse-feed` (app name: `pulse-feed`)

Once Browser snippets are in place, distributed traces will connect browser interactions to backend APM spans (browser fetch → event-svc Go spans → PostgreSQL queries).

---

## Demo Bug Scenarios

Toggled via `infra/helm/<svc>/values.yaml` — no redeploy needed, just `git push`.

| # | Env Flag | Bug | NR Feature shown |
|---|---|---|---|
| 1 | `BUG_AI_SLOW=true` | Claude API call delayed 8s | Distributed Tracing |
| 2 | `BUG_STALE_CACHE=true` | Events show wrong dates silently | Logs in Context |
| 3 | `BUG_MEMORY_LEAK=true` | session-svc accumulates connections | Infrastructure monitoring |
| 4 | `BUG_TOKEN_FLOOD=true` | Full DB sent as Claude context per request | LLM Observability |
| 5 | Scripted | ai-svc killed → retry storm → cascade | Service Maps + Alerts |

See [docs/demo-script.md](docs/demo-script.md) for the full 15-minute walkthrough.

---

## Cities

London and Paris are currently supported. The city picker is in the header. Events, venues, and AI recommendations are filtered per city.

To add a city: seed events in `db/seed.sql` with the new city name — event-svc filters by `?city=` query param automatically.
