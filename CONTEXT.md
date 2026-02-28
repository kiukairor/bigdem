# PULSE — Project Context for Claude Code
> Read this file before making any changes to the codebase.
> This captures all architectural decisions, goals, and conventions agreed during the initial design session.

---

## What is PULSE?

PULSE is a real-time London events feed app with AI-powered personalised recommendations.
It is NOT a real product — it is a **demo app built to showcase New Relic observability**, specifically:
- How to debug a distributed microservices app
- How to observe and debug AI/LLM services
- How business signals (user behaviour) can surface technical problems

The target audience for the demo is engineers and technical managers being introduced to New Relic.

---

## The Demo Story

The core narrative is:
> "Something is wrong in production. I don't know what. Watch how fast I find it with New Relic."

There are 5 pre-planned bug scenarios, each demonstrating a different NR feature:

| # | Bug | How it manifests | NR Feature |
|---|-----|-----------------|------------|
| 1 | AI slow response | Claude API call artificially delayed | Distributed Tracing — spot the slow span |
| 2 | Stale cache | Events return wrong dates, no errors | Logs in Context — cache TTL bug in logs |
| 3 | Memory leak | session-svc accumulates connections | Infrastructure — pod memory climbs then OOMKill |
| 4 | AI token explosion | Full DB sent as prompt context on every request | LLM Observability — token cost spikes 100x |
| 5 | Cascade failure | ai-svc down → retries → hammers event-svc → both down | Service Maps + Alerts |

### The 15-minute demo script

```
Act 1 — Everything looks fine (2 min)
  Show app working, NR dashboard all green

Act 2 — Something is slow (3 min)
  Enable Bug 1: AI slow response
  NR distributed trace shows ai-svc span at 8s
  Fix live: show bad prompt, fix it

Act 3 — Wrong data, no errors (3 min)
  Enable Bug 2: stale cache
  NR logs in context show cache TTL bug
  Fix: one line config change

Act 4 — It's getting worse (4 min)
  Enable Bug 3+4: memory leak + token explosion
  NR infrastructure: pod memory climbing
  NR LLM observability: cost per request 100x normal

Act 4.5 — AI exhausted, app survives (3 min)
  Rate limit / quota exhaustion kicks in
  Circuit breaker opens automatically
  App degrades gracefully — still works, just less smart
  NR: circuit breaker metric flips, fallback traffic visible
  Fix: show circuit breaker config, suggest request queuing

Act 5 — The cascade (3 min)
  Kill ai-svc entirely
  NR service map goes red in real time
  Alerts fire
  NR AI: ask "why is pulse-feed down?" in plain English
  Traces back to ai-svc in seconds
```

---

## Architecture

### Services

| Service | Tech | Port | Status |
|---------|------|------|--------|
| `pulse-shell` | Next.js 14 (Module Federation host) | 3000 | Week 1 done |
| `pulse-feed` | Next.js 14 (Module Federation remote MFE) | 3001 | Week 1 done |
| `pulse-profile` | Next.js 14 (Module Federation remote MFE) | 3002 | Week 2 |
| `event-svc` | Go 1.22 + Gin | 8080 | Week 1 done |
| `ai-svc` | Python 3.12 + FastAPI | 8082 | Week 1 done |
| `session-svc` | Python 3.12 + FastAPI | 8081 | Week 2 |

### Data stores
- **PostgreSQL 16** — events, users, saved_events, ai_opt_out_log
- **Redis 7** — session cache (Week 2)

### Frontend composition
- Module Federation (Webpack 5 via @module-federation/nextjs-mf)
- pulse-shell is the HOST — loads remotes at runtime
- pulse-feed exposes `./FeedApp`
- pulse-profile exposes `./ProfileApp` (Week 2)

### Request flow
```
User → pulse-shell
     → loads pulse-feed MFE
     → pulse-feed calls event-svc (GET /events)
     → pulse-feed calls ai-svc (POST /recommendations)
     → ai-svc calls Claude API
     → returns recommendations
     → user saves event → event-svc (PUT /user/saved-events)
     → user toggles AI off → event-svc (PUT /user/ai-preference) + logs to NR
```

---

## Key Design Decisions

### Single demo user (no auth in Week 1)
- No login screen — app opens directly to the feed
- User ID is always `demo_user` (set via env var DEMO_USER_ID)
- User profile exists in PostgreSQL from day 1 with full schema ready for real auth
- Auth (username + password) is a Week 3+ upgrade — schema already supports it

### Hardcoded London (no real location in Week 1)
- DEMO_CITY=London in config.env
- Location is a field on the user profile, ready to be made dynamic later
- Week 3+ upgrade: browser geolocation or user-picked city

### Fake events (no real API in Week 1)
- 20 seeded events in db/seed.sql across 5 categories: music, food, art, sport, tech
- Real events API (Ticketmaster/Eventbrite) is a Week 3+ upgrade
- event-svc data source swap will be isolated to the repository layer

### AI recommendations
- Claude receives: user preferences, saved event IDs, available events (max 20)
- Returns: 3 event IDs with reasons
- Prompt is profile-aware from day 1 — richer profile = better recs, same endpoint
- Week 2+: enrich with viewing history, time-of-day, weather

### AI degradation (3 modes)
```
FULL AI    → Claude responds, fresh recommendations
DEGRADED   → Cached Claude response, stale but ok (circuit breaker HALF_OPEN)
NO AI      → Rule-based fallback in ai-svc, app 100% functional
```
- Circuit breaker in services/ai-svc/circuit_breaker.py
- States: CLOSED → OPEN → HALF_OPEN
- Config: CB_FAILURE_THRESHOLD and CB_RECOVERY_TIMEOUT_SECONDS in config.env
- NR custom metrics: Custom/AICircuitBreaker/State, Custom/AICircuitBreaker/FailureCount

### User AI opt-out
- Toggle in pulse-feed UI: "AI Enhanced" ↔ "Classic Mode"
- When disabling: micro-survey with 4 reasons:
  - wrong (recommendations felt wrong)
  - slow (it was too slow)
  - impersonal (felt impersonal)
  - prefer_browsing (prefer browsing myself)
- Each opt-out fires a NR custom event: UserAIOptOut with user_id, reason, session_count, last_ai_response_ms
- Stored in ai_opt_out_log table in PostgreSQL
- This enables the "business observability" demo moment:
  "NR didn't just show the system was slow — it showed users were losing trust in your AI"

### Graceful degradation when AI is down
- App remains 100% functional without ai-svc
- Rule-based fallback in ai-svc returns popular events by preferred category
- UI shows appropriate banner: "AI service unavailable — showing curated picks"
- This is a key demo moment: show the app surviving ai-svc being killed

---

## Config & Secrets

**Single source of truth: config.env at repo root (gitignored)**

Never hardcode keys. All services read from environment variables.
All K8s secrets are created from config.env by running:
```bash
./scripts/apply-secrets.sh pulse-prod
```

K8s secret names (referenced in all Helm charts):
- `anthropic-secret` — api-key, model
- `newrelic-secret` — license-key, account-id
- `postgres-secret` — username, password, database, host, port
- `redis-secret` — host, port
- `app-secret` — demo-city, demo-user-id, demo-user-name, cb-failure-threshold, cb-recovery-timeout
- `ghcr-secret` — docker registry pull secret

config.env.example contains placeholder values only — never real keys.
config.env is gitignored — never commit it.

---

## Infrastructure

- **Kubernetes**: plain K8s (NOT k3s) on Raspberry Pi
- **GitOps**: ArgoCD v3.3.2
- **CI**: GitHub Actions — one workflow per service, builds arm64 Docker images, pushes to GHCR, updates Helm values.yaml image tag
- **Ingress**: nginx ingress controller
- **Package manager**: Helm (one chart per service in infra/helm/)
- **ArgoCD pattern**: app-of-apps (argocd/app-of-apps.yaml → argocd/apps/*.yaml)
- **Namespace**: pulse-prod
- **GitHub repo**: https://github.com/kiukairor/bigdem

### GitOps flow
```
git push → GitHub Actions
         → docker build (linux/arm64) + push to GHCR
         → sed updates infra/helm/<svc>/values.yaml image tag
         → git commit [skip ci]
         → ArgoCD detects drift → deploys to Pi
```

---

## New Relic Instrumentation Plan

| Service | NR Agent | Custom metrics/events |
|---------|----------|----------------------|
| pulse-shell | NR Browser | page load, navigation, JS errors |
| pulse-feed | NR Browser | interaction traces, MFE load time |
| event-svc | NR Go Agent | APM, DB query spans, custom attributes |
| ai-svc | NR Python Agent | APM, LLM latency, circuit breaker state, UserAIOptOut events |
| session-svc | NR Python Agent | APM, Redis hit/miss, WebSocket connections |
| K8s cluster | NR Infrastructure | pod CPU/RAM, node health, OOMKill events |

NR custom events to implement:
- `UserAIOptOut` — when user disables AI (with reason, timing)
- `AIFallback` — when circuit breaker triggers fallback
- `AIServiceError` — when Claude API call fails
- `BugScenarioEnabled` — when a demo bug is toggled on (Week 3)

NR custom metrics:
- `Custom/AICircuitBreaker/State` — 1=CLOSED, 0.5=HALF_OPEN, 0=OPEN
- `Custom/AICircuitBreaker/FailureCount`
- `Custom/AI/ResponseMs` — Claude API latency per request
- `Custom/AI/TokensUsed` — tokens per recommendation call

---

## Week-by-Week Build Plan

### Week 1 — COMPLETE ✓
- [x] event-svc (Go): /health, /events, /events/:id, /events/category/:c, /user, /user/ai-preference
- [x] ai-svc (Python): /health, /status, /recommendations with circuit breaker and rule-based fallback
- [x] pulse-shell: dark theme, header with AI status, Module Federation host
- [x] pulse-feed: event grid, category filter, save button, AI recommendations panel, AI toggle with reason survey
- [x] db/seed.sql: 20 London events + users + ai_opt_out_log tables
- [x] config.env.example + scripts/apply-secrets.sh
- [x] Helm charts for all services + ArgoCD app-of-apps + GitHub Actions CI per service
- [x] CONTEXT.md

### Week 2 — TODO (start here)
- [ ] session-svc (Python/FastAPI): session management, saved events persistence to PostgreSQL, Redis caching
- [ ] pulse-profile MFE: user profile page, saved events list, category preferences editor
- [ ] event-svc: add POST /events/saved and DELETE /events/saved/:id endpoints
- [ ] ai-svc: cache last recommendation per user in Redis (avoid repeat Claude calls)
- [ ] pulse-feed: connect save button to session-svc (persist saves, not just local state)
- [ ] New Relic APM instrumentation on event-svc and ai-svc (verify traces working)
- [ ] Distributed tracing working end-to-end (shell → feed → event-svc → ai-svc)
- [ ] Deploy to Pi cluster and verify full stack works

### Week 3 — TODO
- [ ] Bug scenario 1: AI slow response (env flag BUG_AI_SLOW=true adds artificial delay)
- [ ] Bug scenario 2: Stale cache (env flag BUG_STALE_CACHE=true disables cache TTL)
- [ ] Bug scenario 3: Memory leak (env flag BUG_MEMORY_LEAK=true accumulates connections)
- [ ] NR dashboards: circuit breaker state, opt-out rate, AI latency, token cost
- [ ] NR alerts: error rate > 5%, latency p99 > 3s, memory > 80%
- [ ] User auth: simple username + password (no email required)
- [ ] Real location: user picks city on first visit (dropdown of major UK cities)

### Week 4 — TODO
- [ ] Bug scenario 4: Token explosion (env flag BUG_TOKEN_FLOOD=true sends full DB as context)
- [ ] Bug scenario 5: Cascade failure (scripted kill of ai-svc + retry storm)
- [ ] Real events API (Ticketmaster free tier or Eventbrite)
- [ ] NR AI querying demo setup ("why is pulse-feed down?")
- [ ] UI polish pass
- [ ] Demo script rehearsal — time all 5 acts

---

## Code Conventions

### Go (event-svc)
- Framework: Gin
- NR: newrelic/go-agent/v3 with nrgin middleware
- DB: database/sql + lib/pq (no ORM)
- Error handling: always return JSON errors, never panic in handlers
- Logging: structured JSON via log package
- Config: always via os.Getenv with fallback defaults, never hardcoded

### Python (ai-svc, session-svc)
- Framework: FastAPI
- NR: newrelic agent, always run via `newrelic-admin run-program`
- Config: os.getenv with sensible defaults
- Logging: Python logging module, structured format
- NR custom events: newrelic.agent.record_custom_event()
- NR custom metrics: newrelic.agent.record_custom_metric()

### TypeScript/Next.js (frontends)
- Module Federation via @module-federation/nextjs-mf
- CSS Modules for component styles
- No global state library — keep it simple for demo purposes
- Fonts: Bebas Neue (display) + DM Sans (body) — DO NOT change these
- Color palette defined in frontends/pulse-shell/app/globals.css — DO NOT change:
  - --bg: #080808
  - --surface: #111111
  - --accent: #e8ff3c (yellow-green)
  - --text: #f0f0f0
  - --text-dim: #888888
  - --red: #ff3c3c
  - --green: #3cff8a

### General
- ARM64 Docker builds (Raspberry Pi target)
- All services expose /health endpoint returning {"status":"ok","service":"<name>"}
- CORS enabled on all backend services (demo app)
- All config via environment variables — no hardcoded values
- K8s secrets named consistently (see Config & Secrets section)

---

## Upgrade Path (future weeks)

These are confirmed future features — build current code to support them without implementing yet:

1. **Real auth** — users table already has columns ready, session-svc will handle JWT tokens
2. **Real location** — DEMO_CITY env var already abstracted, swap to geolocation or city picker
3. **Real events** — event-svc data layer already isolated, swap seed data for Ticketmaster API
4. **Richer AI profiles** — Claude prompt already receives user.preferences object, just enrich it
5. **Multi-user** — demo_user pattern already abstracted via DEMO_USER_ID env var

---

## How to work on this project with Claude Code

### Starting a session
```bash
cd ~/workspace/bigdem/versus
claude
```

### First message in every session
```
Read CONTEXT.md first, then let me know you're ready and what week we're on.
```

### Example prompts by week

Week 2:
```
Read CONTEXT.md. Start Week 2.
Build session-svc in Python/FastAPI following the conventions in CONTEXT.md.
It needs: session management, saved events to PostgreSQL, Redis caching, NR instrumentation.
```

Week 3:
```
Read CONTEXT.md. Start Week 3 bug scenarios.
Add BUG_AI_SLOW env flag to ai-svc that adds a 8 second artificial delay to Claude calls.
It should be toggleable without redeployment via Helm values.yaml.
```

### Important reminders for Claude Code
- Always run `curl localhost:<port>/health` after modifying a service
- Always run `helm template infra/helm/<svc>` after modifying Helm charts
- Never hardcode secrets — always use os.getenv
- Never change the UI color palette or fonts
- ARM64 Docker builds only (Raspberry Pi)
- Commit message format: `feat:`, `fix:`, `chore:`, `ci:`
