# event-svc

## What is it?

event-svc is the **core data service** — it owns all event data and user profiles. Every event card the user sees in the feed comes from this service, and every user preference (including AI opt-out) is stored here.

From a user's perspective, this is invisible — but it powers every event listing, category filter, and user setting in the app.

## User Journey (Behind the Scenes)

1. User opens the app → pulse-feed calls `GET /events` → event-svc queries PostgreSQL → returns 20 London events
2. User filters by category → pulse-feed filters client-side (the `/events/category/:category` endpoint exists but isn't used by the frontend)
3. User toggles AI off → pulse-feed calls `PUT /user/ai-preference` → event-svc updates the user row and logs the opt-out reason to `ai_opt_out_log`
4. Header shows AI status → pulse-shell calls `GET /user` → event-svc returns the user's `ai_enabled` flag

## Technical Details

| | |
|---|---|
| **Language** | Go 1.22 |
| **Framework** | Gin |
| **Port** | 8080 |
| **Database** | PostgreSQL |
| **Observability** | New Relic Go Agent + nrgin middleware |

### Endpoints

| Method | Path | Description |
|--------|------|-------------|
| `GET` | `/health` | Health check |
| `GET` | `/events` | All events, sorted by date |
| `GET` | `/events/:id` | Single event by ID |
| `GET` | `/events/category/:category` | Events filtered by category |
| `GET` | `/user` | Current user (uses `DEMO_USER_ID`) |
| `PUT` | `/user/ai-preference` | Toggle AI on/off with optional reason |
| `PUT` | `/user/preferences` | Save category preferences |
| `GET` | `/user/saved-events` | Get saved event IDs for the demo user |
| `POST` | `/user/saved-events` | Save an event (body: `{"event_id": "..."}`) |
| `DELETE` | `/user/saved-events/:event_id` | Unsave an event |

### Key Files

- `cmd/main.go` — Entry point: DB connection, NR init, Gin routes, CORS setup
- `go.mod` / `go.sum` — Dependencies
- `Dockerfile` — 2-stage build (Go 1.22 Alpine builder → Alpine 3.19 runtime), targets `linux/arm64`

### Environment Variables

| Variable | Default | Purpose |
|----------|---------|---------|
| `PORT` | `8080` | Server port |
| `POSTGRES_HOST` | `localhost` | DB host |
| `POSTGRES_PORT` | `5432` | DB port |
| `POSTGRES_USER` | `pulse` | DB user |
| `POSTGRES_PASSWORD` | (none) | DB password |
| `POSTGRES_DB` | `pulse` | DB name |
| `DEMO_USER_ID` | `demo_user` | Which user row to return from `/user` |
| `NEW_RELIC_APP_NAME` | `pulse-event-svc` | NR app name |
| `NEW_RELIC_LICENSE_KEY` | (none) | NR license |

### Run Locally

```bash
cd cmd
go run main.go  # http://localhost:8080
```

## Be Careful Of

- **`pqArray` helper is a stub** — the `tags` field on events will always return empty. If you need tags, implement proper `pq.StringArray` scanning
- **`go.mod` module path** still says `github.com/YOUR_ORG/pulse/event-svc` — harmless for a single-package service but should be updated
- The `services/event-svc/main` binary artifact has been accidentally committed — it should be in `.gitignore`
- All DB queries use raw SQL with `database/sql` (no ORM) — keep it that way
- The `/user` endpoint always returns the user matching `DEMO_USER_ID` — there's no auth, this is a demo app
- AI opt-out logging writes to the `ai_opt_out_log` table AND fires a New Relic custom event (`UserAIOptOut`)
- Docker builds must target **arm64** (Raspberry Pi cluster)
