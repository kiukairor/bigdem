# session-svc

## What is it?

session-svc manages **user sessions and saved events**. When a user saves an event they want to attend, this service persists it to PostgreSQL and caches the session state in Redis for fast reads. It's the bridge between "I like this event" and that preference being remembered.

From a user's perspective, this is what makes their saved events stick around between page loads (once pulse-feed is wired up to call it — currently the save button only uses local React state).

## User Journey (Behind the Scenes)

1. User opens the app → a session is created via `POST /sessions` (stores user ID + loads any existing saved events from DB)
2. User clicks "Save" on an event → `POST /sessions/:id/saved-events` persists to PostgreSQL and updates Redis cache
3. User unsaves an event → `DELETE /sessions/:id/saved-events/:event_id` removes from both stores
4. On page reload → `GET /sessions/:id` reads from Redis (fast) with DB as the source of truth

## Technical Details

| | |
|---|---|
| **Language** | Python 3.12 |
| **Framework** | FastAPI |
| **Port** | 8081 |
| **Database** | PostgreSQL (persistent) + Redis (session cache) |
| **Observability** | New Relic Python Agent (run via `newrelic-admin`) |

### Endpoints

| Method | Path | Description |
|--------|------|-------------|
| `GET` | `/health` | Health check |
| `POST` | `/sessions` | Create a new session (loads saved events from DB) |
| `GET` | `/sessions/{session_id}` | Get session data (from Redis cache) |
| `POST` | `/sessions/{session_id}/saved-events` | Save an event |
| `DELETE` | `/sessions/{session_id}/saved-events/{event_id}` | Unsave an event |

### Key Files

- `main.py` — FastAPI app, all endpoints, PostgreSQL pool, Redis client, NR instrumentation
- `requirements.txt` — Pinned dependencies
- `Dockerfile` — Python 3.12 slim, runs via `newrelic-admin run-program uvicorn`

### Data Flow

```
Write path:  API → PostgreSQL (INSERT) → Redis (SET with 1hr TTL)
Read path:   API → Redis (GET) → fallback to PostgreSQL if cache miss
```

### Environment Variables

| Variable | Default | Purpose |
|----------|---------|---------|
| `PORT` | `8081` | Server port |
| `POSTGRES_HOST` | `localhost` | DB host |
| `POSTGRES_PORT` | `5432` | DB port |
| `POSTGRES_USER` | `pulse` | DB user |
| `POSTGRES_PASSWORD` | (none) | DB password |
| `POSTGRES_DB` | `pulse` | DB name |
| `REDIS_HOST` | `localhost` | Redis host |
| `REDIS_PORT` | `6379` | Redis port |
| `NEW_RELIC_LICENSE_KEY` | (none) | NR license |

### Custom NR Events

- `SessionCreated` — user_id, session_id, saved_event_count
- `EventSaved` — user_id, event_id, session_id
- `EventUnsaved` — user_id, event_id, session_id

### Run Locally

```bash
pip install -r requirements.txt
uvicorn main:app --host 0.0.0.0 --port 8081  # without NR
# or
newrelic-admin run-program uvicorn main:app --host 0.0.0.0 --port 8081  # with NR
```

## Be Careful Of

- **Session TTL is hardcoded to 3600 seconds** (1 hour) in Redis — not configurable via env var
- **Redis is a single client, not a connection pool** — fine for demo load but wouldn't scale
- **`POST /sessions` loads all saved events from PostgreSQL** on creation — could be slow if a user has many saved events
- **DELETE is silent** — unsaving an event that wasn't saved returns success (no error, no indication)
- **`saved_events` table uses `ON CONFLICT DO NOTHING`** — saving the same event twice is a no-op, which is correct but means no "already saved" feedback
- Docker builds must target **arm64** (Raspberry Pi cluster)
