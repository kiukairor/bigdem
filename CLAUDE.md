# PULSE — Claude Code Instructions
> This file is automatically read by Claude Code at the start of every session.
> Do not delete or rename this file.

---

## What is PULSE?

PULSE is a real-time London events feed app with AI-powered personalised recommendations.
It is NOT a real product — it is a **demo app built to showcase New Relic observability**, specifically:
- How to debug a distributed microservices app
- How to observe and debug AI/LLM services
- How business signals (user behaviour) can surface technical problems

The target audience is engineers and technical managers being introduced to New Relic.

---

## Repo Structure

```
versus/                          ← repo root (github.com/kiukairor/bigdem)
├── CLAUDE.md                    ← this file
├── config.env                   ← local secrets (gitignored, never commit)
├── config.env.example           ← placeholder template (safe to commit)
├── scripts/
│   ├── apply-secrets.sh         ← creates all K8s secrets from config.env
│   ├── sync-events.py           ← Gemini-powered event generator (run by CronJob or manually)
│   └── Dockerfile               ← image for sync-events CronJob (python:3.12-slim + google-genai + psycopg2)
├── db/
│   └── seed.sql                 ← PostgreSQL schema + demo user (events now managed by sync-events CronJob)
├── frontends/
│   ├── pulse-shell/             ← Next.js 14, Module Federation HOST, port 3000
│   └── pulse-feed/              ← Next.js 14, Module Federation REMOTE MFE, port 3001
│   └── pulse-profile/           ← Next.js 14, Module Federation REMOTE MFE, port 3002 (Week 2)
├── services/
│   ├── event-svc/               ← Go 1.22 + Gin, port 8080, REAL CODE EXISTS
│   │   └── cmd/main.go          ← entry point
│   ├── ai-svc/                  ← Python 3.12 + FastAPI, port 8082, REAL CODE EXISTS
│   │   ├── main.py              ← entry point
│   │   └── circuit_breaker.py   ← AI circuit breaker (CLOSED/OPEN/HALF_OPEN)
│   ├── session-svc/             ← Python 3.12 + FastAPI, port 8081, REAL CODE EXISTS
│   │   ├── main.py              ← entry point
│   │   ├── Dockerfile            ← runs via newrelic-admin
│   │   └── requirements.txt
│   └── test-svc/                ← Python 3.12 + FastAPI, port 8090, Gemini only, no NR instrumentation
├── infra/
│   └── helm/                    ← one Helm chart per service
│       ├── pulse-shell/
│       ├── pulse-feed/
│       ├── pulse-profile/
│       ├── event-svc/
│       ├── ai-svc/
│       ├── session-svc/
│       ├── sync-events/
│       ├── postgresql/
│       └── redis/
├── argocd/
│   ├── app-of-apps.yaml         ← root ArgoCD app
│   └── apps/                    ← one ArgoCD Application per service
└── .github/
    └── workflows/               ← one CI pipeline per service
```

---

## Current Status

| Service | Status | Notes |
|---------|--------|-------|
| `pulse-shell` | ✅ Running | MFE host, city picker (London/Paris), single public entry point |
| `pulse-feed` | ✅ Running | Events grid, category filter, AI panel with GEMINI/CLAUDE/OPENAI toggle |
| `pulse-profile` | ✅ Running | Saved events list + preferences editor; enhanced-resolve pinned to 5.20.0 |
| `event-svc` | ✅ Running | Go, city filter (?city=), auto-updates user preferences on event save |
| `ai-svc` | ✅ Running | Python, circuit breaker CLOSED, 3 providers (Gemini/Claude/OpenAI), per-category Gemini fill |
| `session-svc` | ✅ Running | Python/FastAPI, Redis + PG, NR instrumented |
| `sync-events` | ✅ Running | CronJob, runs daily at midnight UTC, hybrid TM + per-category Gemini |
| `postgresql` | ✅ Running | Events refreshed daily, 1 demo user with auto-updating preferences |
| `redis` | ✅ Running | local-path StorageClass |
| `gateway` | ✅ Running | NGINX GW Fabric v1.6.1, NodePort :30443, pulse.test only |
| `test-svc` | ✅ Running | Multi-model chat (Gemini/Claude/OpenAI), NR instrumented via newrelic-admin, app name: pulse-ai-dontask |

Image tags are managed by CI (GitHub Actions updates values.yaml automatically on each push).

---

## The Demo Story

Core narrative:
> "Something is wrong in production. I don't know what. Watch how fast I find it with New Relic."

6 pre-planned bug scenarios:

| # | Env Flag / Trigger | Bug | NR Feature |
|---|-------------------|-----|------------|
| 1 | `BUG_AI_SLOW=true` | AI call delayed 8s (Gemini or Claude) | Distributed Tracing |
| 2 | `BUG_STALE_CACHE=true` | Events return wrong dates, no errors | Logs in Context |
| 3 | `BUG_MEMORY_LEAK=true` | session-svc accumulates connections | Infrastructure monitoring |
| 4 | `BUG_TOKEN_FLOOD=true` | Full DB sent as Claude context every request | LLM Observability |
| 5 | UI "LIVE" button | 1s polling of event-svc (~60 req/min) | Service Maps + Alerts |
| 6 | Scripted | ai-svc killed → retry storm → cascade | Service Maps + Alerts |

Bugs 1-4 are toggled via Helm values.yaml env vars — no redeployment needed, just a git push.
Bug 5 (`BUG_LIVE_REFRESH`) is UI-only: the "● LIVE" toggle in pulse-feed activates 1s polling of event-svc. AI recommendation refresh is a separate background timer set to every 4 hours.

---

## Architecture

### Request flow
```
User → pulse-shell (3000)
     → loads pulse-feed MFE via Module Federation
     → pulse-feed → event-svc (8080) → PostgreSQL
     → pulse-feed → ai-svc (8082) → Gemini API (default) or Claude API or OpenAI API
     → ai-svc: saved event IDs enriched with full event details before AI call
     → ai-svc fallback → rule-based recs (when AI unavailable)
     → user saves event → event-svc → PostgreSQL
                       → event-svc auto-updates user.preferences.categories (preference feedback loop)
     → user toggles AI off → event-svc → ai_opt_out_log table → NR custom event
```

### AI providers (multi-LLM)
- **Default**: Gemini (`AI_PROVIDER=gemini`, model `gemini-3.1-flash-lite-preview`)
- **Alternative**: Claude (`AI_PROVIDER=claude`, model from `anthropic-secret.model` K8s secret = `claude-sonnet-4-6`)
- **Alternative**: OpenAI (`AI_PROVIDER=openai`, model `gpt-4o-mini` from `OPENAI_MODEL` env)
- Users can switch provider live in the UI (GEMINI / CLAUDE / OPENAI buttons in AI panel)
- Per-request override: `provider` field in the POST /recommendations body
- **Event data** is generated by a hybrid pipeline: Ticketmaster (music/art) + per-category Gemini fill for thin categories (food/sport/tech). Gemini also handles recommendation ranking in ai-svc — separate calls with separate prompts.
- AI recs background refresh: every **4 hours** in FeedApp.tsx (Redis server-side cache TTL: 5 min)

### Preference feedback loop
- When a user saves an event, `event-svc/saveEventHandler` automatically adds the event's category to `user.preferences.categories` if not already present
- This means the AI prompt receives richer preferences with each save — no manual profile editing required
- Also: saved event IDs in the recommendation prompt are now enriched with full event title + category (not opaque IDs), so the AI can reason about user taste from save history
- Fires `PreferencesAutoUpdated` NR custom event on each auto-update

### Event data sources
- **Ticketmaster**: music, arts (strong). Food/sport/tech sparse — expected.
- **Eventbrite**: API token acquired but public search endpoint restricted to approved partners (returns 404). Code stub in place, gracefully returns empty. Revisit if partnership access granted.
- **Gemini per-category fill** (`_fetch_gemini_category`): when any category has < 2 events after TM, a targeted prompt generates realistic events for that specific category (supper clubs for food, 5K runs for sport, hackathons for tech). Better quality than the generic 20-event prompt.
- **Gemini full fallback** (`_fetch_gemini_city`): used when TM + EB return nothing at all for a city.

### AI models — canonical versions (use these everywhere, do not change without updating all references)
| Provider | Model ID | Used in |
|----------|----------|---------|
| Google Gemini | `gemini-3.1-flash-lite-preview` | ai-svc recommendations, sync-events CronJob, test-svc |
| Anthropic Claude | `claude-sonnet-4-6` (from `anthropic-secret.model` K8s secret) | ai-svc (when provider=claude) |
| OpenAI | `gpt-4o-mini` (from `OPENAI_MODEL` env / `openai-secret`) | ai-svc (when provider=openai) |

### AI degradation (3 modes)
```
FULL AI    → Gemini (default) or Claude responds normally
DEGRADED   → Cached AI response (circuit breaker HALF_OPEN)
NO AI      → Rule-based fallback, app 100% functional
```

Circuit breaker: `services/ai-svc/circuit_breaker.py`
States: CLOSED → OPEN → HALF_OPEN
Config via env: `CB_FAILURE_THRESHOLD`, `CB_RECOVERY_TIMEOUT_SECONDS`

### User AI opt-out
- Toggle in pulse-feed: "AI Enhanced" ↔ "Classic Mode"
- On disable: micro-survey (wrong / slow / impersonal / prefer_browsing)
- Fires NR custom event: `UserAIOptOut` with reason, timing
- Stored in `ai_opt_out_log` PostgreSQL table
- Demo moment: "NR showed users were losing trust in AI before any alert fired"

---

## Infrastructure

- **Cluster**: plain Kubernetes (NOT k3s) on Raspberry Pi
- **GitOps**: ArgoCD v3.3.2, namespace `pulse-prod`
- **CI**: GitHub Actions, builds `linux/arm64` Docker images, pushes to GHCR
- **Gateway**: NGINX Gateway Fabric v1.6.1 + K8s Gateway API v1.3.0, namespace `nginx-gateway`
  - NodePort 30080 (HTTP) and 30443 (HTTPS), self-signed TLS for `*.pulse.test`
  - Apply: `./scripts/apply-gateway.sh` (idempotent)
  - See: `infra/gateway/README.md`
- **Helm**: one chart per service in `infra/helm/`
- **ArgoCD**: app-of-apps pattern
- **GitHub repo**: https://github.com/kiukairor/bigdem

### GitOps flow
```
git push → GitHub Actions
         → docker build linux/arm64 → push to ghcr.io/kiukairor/<svc>
         → sed updates infra/helm/<svc>/values.yaml image tag
         → git commit [skip ci]
         → ArgoCD detects drift → deploys to Pi
```

### Recovery commands

**Revert last commit and redeploy (safest — keeps history):**
```bash
git revert HEAD --no-edit
git push origin main
# CI rebuilds previous code → ArgoCD redeploys automatically
```

**Revert a specific commit by hash:**
```bash
git revert <commit-sha> --no-edit
git push origin main
```

**Find commit hashes:**
```bash
git log --oneline -10
```

**Roll back a service to a previous image tag without reverting code:**
```bash
# Edit infra/helm/<svc>/values.yaml — set tag to previous sha
git add infra/helm/<svc>/values.yaml
git commit -m "chore: rollback <svc> to <sha>"
git push origin main
# ArgoCD detects the tag change and redeploys the old image — no CI build needed
```

**Force ArgoCD to sync immediately (without waiting for drift detection):**
```bash
kubectl patch application <app-name> -n argocd --type merge \
  -p '{"operation":{"initiatedBy":{"username":"admin"},"sync":{"syncStrategy":{"hook":{}}}}}'
```

**Cancel a running CI build:**
```bash
gh run cancel <run-id> --repo kiukairor/bigdem
# Find run-id with: gh run list --repo kiukairor/bigdem --limit=5
```

**Check what image is currently running on a pod:**
```bash
kubectl get deployment <svc> -n pulse-prod -o jsonpath='{.spec.template.spec.containers[0].image}'
```

---

## Config & Secrets

Single source of truth: `config.env` at repo root (gitignored — NEVER commit it).

Apply all secrets to K8s:
```bash
./scripts/apply-secrets.sh pulse-prod
```

Then apply the GHCR pull secret separately (GITHUB_USER and GITHUB_PAT must be in config.env):
```bash
export $(grep -v '^#' config.env | grep -v '^$' | xargs)
kubectl create secret docker-registry ghcr-secret \
  --docker-server=ghcr.io \
  --docker-username="$GITHUB_USER" \
  --docker-password="$GITHUB_PAT" \
  -n pulse-prod --dry-run=client -o yaml | kubectl apply -f -
```

K8s secret names used in Helm charts:
- `gemini-secret` → api-key (**used by both ai-svc recommendations and sync-events CronJob**, model: gemini-3.1-flash-lite-preview)
- `anthropic-secret` → api-key, model (`claude-sonnet-4-6`) — config.env must use this exact model string; `claude-sonnet-4-20250514` is NOT valid
- `openai-secret` → api-key (optional=true in Helm, pod starts without it; needed for OPENAI provider button)
- `eventbrite-secret` → api-key (optional=true; search API currently restricted, kept for future use)
- `newrelic-secret` → license-key, account-id
- `postgres-secret` → username, password, database, host, port
- `redis-secret` → host, port
- `app-secret` → demo-city, demo-user-id, demo-user-name, cb-failure-threshold, cb-recovery-timeout
- `ghcr-secret` → Docker registry pull secret (GITHUB_USER + GITHUB_PAT in config.env, not applied by apply-secrets.sh)

---

## New Relic Instrumentation

| Service | Agent | Key signals |
|---------|-------|-------------|
| pulse-shell | NR Browser | page load, JS errors |
| pulse-feed | NR Browser | MFE load time, interaction traces, page actions on every button click |
| event-svc | NR Go Agent | APM, DB query spans |
| ai-svc | NR Python Agent | LLM latency, circuit breaker state, token count |
| session-svc | NR Python Agent | Redis hit/miss, session lifecycle |
| test-svc | NR Python Agent | LLM Observability (Gemini/Claude/OpenAI auto-instrumented), LLM feedback events |
| K8s | NR Infrastructure | pod CPU/RAM, OOMKill |

Custom NR events: `UserAIOptOut`, `AIFallback`, `AIServiceError`, `BugScenarioEnabled`, `PreferencesAutoUpdated`, `LlmFeedback` (via `record_llm_feedback_event` in test-svc)
Custom NR metrics: `Custom/AICircuitBreaker/State`, `Custom/AI/ResponseMs`, `Custom/AI/TokensUsed`
NR Browser page actions (via `window.newrelic?.addPageAction`): `pulse.category_filter`, `pulse.live_refresh`, `pulse.event_save`, `pulse.event_unsave`, `pulse.event_save_error`, `pulse.provider_change`, `pulse.ai_toggle`, `pulse.recommendations_received`, `pulse.recommendations_error`, `pulse.chat_open`

All backend services have verbose INFO/WARNING/ERROR logging at every meaningful step (request entry, cache hit/miss, AI call start/end, DB ops, fallback triggers). Frontend uses `console.info/warn/error` on all button interactions — visible in NR Browser logs and browser console during demos.

---

## Week-by-Week Build Plan

### ✅ Week 1 — COMPLETE
- event-svc (Go): /health, /events, /events/:id, /events/category/:c, /user, /user/ai-preference
- event-svc: city filter via ?city= query param (DEMO_CITY env fallback)
- ai-svc (Python): /health, /status, /recommendations + circuit breaker + rule-based fallback
- pulse-shell: dark theme, Module Federation host, header with city picker (London / Paris)
- pulse-shell: single public entry point — Next.js rewrites proxy all MFE + API traffic
- pulse-feed: event grid, category filter (sport = 🏃), save button, AI panel, AI toggle + reason survey
- pulse-feed: city-aware (re-fetches events + AI recs on city change)
- db/seed.sql: schema + demo user (events populated by sync-events CronJob, not seed)
- Helm charts, ArgoCD apps, GitHub Actions CI
- NGINX Gateway Fabric v1.6.1 + K8s GW API v1.3.0, NodePort :30080/:30443, self-signed TLS for *.pulse.test

### ✅ Week 2 — COMPLETE
- [x] session-svc: build real Python/FastAPI service
  - POST /sessions, GET /sessions/:id
  - POST /sessions/:id/saved-events, DELETE /sessions/:id/saved-events/:event_id
  - Redis caching for session state
  - PostgreSQL persistence for saved events
  - NR instrumentation (SessionCreated, EventSaved, EventUnsaved custom events)
- [x] Fix CI workflow: path trigger + build context (frontends/ → services/)
- [x] Fix Helm values: replace YOUR_ORG placeholder with kiukairor
- [x] Fix Dockerfile: run via newrelic-admin for NR instrumentation
- [x] Fix apply-secrets.sh: default namespace was versus-prod, fixed to pulse-prod
- [x] Unblock cluster: fix postgresql + redis PVC binding (storageClass standard → local-path)
- [x] Apply K8s secrets via apply-secrets.sh + GHCR pull secret
- [x] Fix CI workflows: replaced stale versus-era workflows with correct PULSE workflows
- [x] Fix pulse-shell + pulse-feed CI (MF build, webpack devDep, public/ dir, NEXT_PRIVATE_LOCAL_WEBPACK)
- [x] Full cluster rebuild from repo config (ArgoCD + local-path + secrets + seed)
- [x] All backend services smoke tested and healthy on cluster
- [x] NR Browser: pulse-shell _document.tsx — full SPA agent v1.313.1, secrets from K8s env at runtime (getServerSideProps forces SSR)
- [x] NR Browser: pulse-feed MFE micro-agent — @newrelic/browser-agent MicroAgent in FeedApp.tsx, NEXT_PUBLIC_NR_* baked at CI build time
  - Note: requires NR MFE feature flag activated on the account to report separately; host agent (pulse-shell) captures all feed traffic regardless
- [x] pulse-profile MFE: saved events list + preferences editor, exposed as profile/ProfileApp via MFE
- [x] event-svc: GET/POST/DELETE /user/saved-events, PUT /user/preferences
- [x] ai-svc: Redis cache for recommendations (TTL 300s, key rec:{user_id}:{city})
- [x] pulse-feed: save button wired to session-svc, session restored from localStorage
- [ ] Verify distributed tracing end-to-end: open NR and confirm browser → shell → event-svc → PostgreSQL trace is visible
- [ ] End-to-end UI smoke test: load https://pulse.test:30443 in browser, verify feed renders, events load, AI panel works, save button works
- [x] pulse-profile CI: fixed package-lock.json (npm ci error) and pinned enhanced-resolve@5.20.0 (arm64 build failure); pod Running as of 2026-05-01

### 🔄 Week 3 — IN PROGRESS
- [x] Bug scenarios 1-3 as env flag toggles (BUG_AI_SLOW, BUG_STALE_CACHE, BUG_MEMORY_LEAK)
  - BUG_AI_SLOW: 8s sleep in ai-svc before Gemini/Claude call, cache bypassed so delay is always visible
  - BUG_STALE_CACHE: event-svc shifts all event dates back 45 days silently
  - BUG_MEMORY_LEAK: session-svc appends session payloads to a global list on every request, never freed
  - Each bug fires `BugScenarioEnabled` custom event to NR; toggle is one line in infra/helm/<svc>/values.yaml + git push
- [x] Multi-LLM support: Gemini (default) + Claude + OpenAI selectable in UI
  - Provider toggle in AI panel (GEMINI / CLAUDE / OPENAI buttons)
  - Gemini via gemini-secret; Claude via anthropic-secret (model: claude-sonnet-4-6); OpenAI via openai-secret (optional)
  - Claude billing issue: account ran out of credits (key itself valid) — top up at console.anthropic.com
- [x] BUG_LIVE_REFRESH: UI "LIVE" button enables 1s polling of event-svc (~60 req/min)
  - AI recommendation refresh is separate: background timer every 4 hours (server-side Redis cache: 5 min TTL)
- [x] Verbose logging across all services for demo visibility
  - All backends: INFO at every handler entry, cache hit/miss, AI call start/end, DB ops, fallbacks
  - Frontend: console.info/warn/error + window.newrelic?.addPageAction on every button interaction
  - test-svc NR app name: pulse-ai-dontask
- [x] Preference feedback loop
  - Saving an event auto-adds its category to user.preferences (event-svc, no schema changes)
  - AI prompt enriched: saved event IDs replaced with full event title + category for better AI reasoning
  - Fires PreferencesAutoUpdated NR custom event
- [x] LLM feedback in chat (test-svc)
  - `/chat` returns `trace_id` from `newrelic.agent.current_trace_id()`
  - `POST /chat/feedback` calls `record_llm_feedback_event(trace_id, rating, message?)`
  - ChatModal: thumbs up/down per assistant message, wired to feedback endpoint
  - Routed via pulse-shell rewrite: `/api/test-svc/chat/feedback`
- [x] Per-category Gemini event fill
  - Thin categories (< 2 events after TM) topped up with targeted Gemini prompts per category
  - Category-specific prompts: food → supper clubs/markets, sport → 5Ks/fitness, tech → hackathons/meetups
  - Eventbrite key acquired but search API restricted to approved partners — stub in place, gracefully fails
- [ ] NR dashboards: circuit breaker, opt-out rate, AI latency, token cost
- [ ] NR alerts: error rate > 5%, p99 > 3s, memory > 80%
- [ ] Simple auth: username + password (no email)
- [ ] Free-text city input (see design note below)

### 🔲 Week 4
- [ ] Bug scenarios 4-5
- [ ] Richer event data (more categories, images, ticket URLs)
- [ ] NR AI querying demo
- [ ] UI polish + demo script timing

---

## Code Conventions

### Go (event-svc)
- Framework: Gin
- NR: newrelic/go-agent/v3 + nrgin middleware
- DB: database/sql + lib/pq (no ORM)
- Errors: always return JSON, never panic in handlers
- Config: os.Getenv with fallback defaults, never hardcoded
- Logging: structured JSON

### Python (ai-svc, session-svc)
- Framework: FastAPI
- NR: always run via `newrelic-admin run-program uvicorn ...`
- Config: os.getenv with defaults
- NR events: newrelic.agent.record_custom_event()
- NR metrics: newrelic.agent.record_custom_metric()

### TypeScript/Next.js (frontends)
- Module Federation via @module-federation/nextjs-mf
- CSS Modules for all component styles
- No global state library
- Fonts: Bebas Neue (display) + DM Sans (body) — DO NOT CHANGE
- Colors (in frontends/pulse-shell/app/globals.css) — DO NOT CHANGE:
  - --bg: #080808, --surface: #111111, --accent: #e8ff3c
  - --text: #f0f0f0, --text-dim: #888888, --red: #ff3c3c, --green: #3cff8a

### General rules — always follow these
- ARM64 Docker builds only (`GOARCH=arm64`, `platforms: linux/arm64`)
- All services expose `GET /health` → `{"status":"ok","service":"<name>"}`
- CORS enabled on all backend services
- Never hardcode secrets — always os.Getenv / os.getenv
- Never commit config.env
- Commit format: `feat:`, `fix:`, `chore:`, `ci:`

---

## How to Verify Your Work

After modifying any backend service:
```bash
# Test health endpoint locally
curl localhost:<port>/health

# Validate Helm chart before committing
helm template infra/helm/<svc-name>

# Check pod status on cluster
kubectl get pods -n pulse-prod
kubectl logs -n pulse-prod deploy/<svc-name>
```

After modifying ArgoCD apps:
```bash
kubectl apply -f argocd/apps/<svc>.yaml
# Then check ArgoCD UI or:
kubectl get applications -n argocd
```

---

## Upgrade Path (do not implement yet)

1. **Real auth** — users table schema already supports it, session-svc will add JWT
2. **Free-text city input** — keep the London/Paris dropdown as defaults, add a text input alongside it so users can type any city; event-svc returns `[]` for unknown cities; frontend calls `POST /api/ai-svc/events/generate?city=X` which runs the Gemini sync prompt on demand and stores results; sync-events CronJob queries `SELECT DISTINCT city FROM events` at runtime to refresh all known cities nightly. Cost: ~$0.001 per new city typed. No schema changes needed.
3. **Richer events** — event-svc data layer isolated, enrich Gemini prompt for images/ticket URLs or swap for a real API
4. **Richer AI profiles** — Claude prompt already receives user.preferences, just enrich
5. **Multi-user** — DEMO_USER_ID env var already abstracted