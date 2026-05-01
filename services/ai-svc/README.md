# ai-svc

## What is it?

ai-svc is the **AI recommendation engine** — it takes a user's preferences and the available events, sends them to Claude (Anthropic's LLM), and returns 3 personalised event recommendations with reasons. If Claude is slow or unavailable, it degrades gracefully through a circuit breaker: first serving cached responses, then falling back to rule-based filtering.

From a user's perspective, this powers the "Recommended for you" sidebar in the feed. When working well, recommendations feel personal and relevant. When degraded, the app still works — just with simpler suggestions.

## User Journey (Behind the Scenes)

1. User opens the feed → pulse-feed sends `POST /recommendations` with user preferences + all available events
2. **Happy path**: ai-svc calls Claude, parses the response, returns 3 recommendations with `mode: "ai"`
3. **Claude slow/down**: Circuit breaker opens → returns last cached response with `mode: "degraded"`
4. **Full fallback**: No cache available → rule-based filter matches categories and returns top 3 with `mode: "fallback"`
5. Recommendation panel in pulse-feed shows the mode so the user knows what they're getting

## Technical Details

| | |
|---|---|
| **Language** | Python 3.12 |
| **Framework** | FastAPI |
| **Port** | 8082 |
| **External API** | Anthropic Claude (model configurable via env) |
| **Observability** | New Relic Python Agent (run via `newrelic-admin`) |

### Endpoints

| Method | Path | Description |
|--------|------|-------------|
| `GET` | `/health` | Health check + circuit breaker state |
| `GET` | `/status` | Circuit breaker state, failure count, model name |
| `POST` | `/recommendations` | Get personalised event recommendations |

### Key Files

- `main.py` — FastAPI app, Claude API call, rule-based fallback, NR instrumentation
- `circuit_breaker.py` — 3-state breaker: CLOSED → OPEN → HALF_OPEN
- `requirements.txt` — Pinned dependencies
- `newrelic.ini` — NR agent config (distributed tracing enabled)
- `Dockerfile` — Python 3.12 slim, runs via `newrelic-admin run-program uvicorn`

### Circuit Breaker States

| State | Meaning | Behaviour |
|-------|---------|-----------|
| **CLOSED** | All good | Calls Claude normally |
| **OPEN** | Claude failing | Returns cached/fallback, skips Claude |
| **HALF_OPEN** | Testing recovery | Lets one request through to Claude, resets or re-opens based on result |

### Environment Variables

| Variable | Default | Purpose |
|----------|---------|---------|
| `PORT` | `8082` | Server port |
| `ANTHROPIC_API_KEY` | (none) | Claude API key |
| `CLAUDE_MODEL` | `claude-sonnet-4-20250514` | Which Claude model to use |
| `DEMO_CITY` | `London` | City name injected into Claude prompt |
| `CB_FAILURE_THRESHOLD` | `5` | Failures before circuit opens |
| `CB_RECOVERY_TIMEOUT_SECONDS` | `60` | Seconds before trying HALF_OPEN |
| `NEW_RELIC_LICENSE_KEY` | (none) | NR license |

### Custom NR Signals

- **Metrics**: `Custom/AICircuitBreaker/State`, `Custom/AICircuitBreaker/FailureCount`, `Custom/AI/ResponseMs`, `Custom/AI/TokensUsed`
- **Events**: `AIFallback`, `AIServiceError`

### Run Locally

```bash
pip install -r requirements.txt
uvicorn main:app --host 0.0.0.0 --port 8082  # without NR
# or
newrelic-admin run-program uvicorn main:app --host 0.0.0.0 --port 8082  # with NR
```

## Be Careful Of

- **Token explosion risk**: The request body includes the full `available_events` array. ai-svc caps at 20 events before sending to Claude, but be aware of this if the event list grows
- **Claude response parsing assumes valid JSON** — if Claude returns malformed output, the parse will fail and trigger the circuit breaker. There's no retry or repair logic
- **`httpx` version pinned to `<0.28.0`** in requirements.txt — the Anthropic SDK breaks with httpx 0.28+. Don't upgrade httpx without testing
- **Rule-based fallback is naive** — it just filters by matching categories and slices the first 3. No scoring or ranking
- **Redis cache is live** — recommendations are cached per `{user_id}:{city}` with a 300s TTL. A cache hit bypasses the Claude call entirely and is not reflected in the circuit breaker state
- Docker builds must target **arm64** (Raspberry Pi cluster)
