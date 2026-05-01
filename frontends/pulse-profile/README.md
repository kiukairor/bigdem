# pulse-profile

## What is it?

pulse-profile is the **user profile micro-frontend** — it shows saved events and lets users manage their category preferences. It is loaded into pulse-shell via Module Federation, just like pulse-feed.

**Status: Built and deployed (Week 2). Pod pending image push from CI arm64 build.**

## User Journey

1. User navigates to their profile section within pulse-shell
2. They see a list of events they've saved, fetched from both session-svc (session state) and event-svc (saved-event IDs → full event details)
3. They can remove saved events (fires DELETE to both event-svc and session-svc)
4. They can toggle their favourite categories and hit "Save Preferences" (PUT to event-svc)
5. Saved preferences are used by ai-svc on the next recommendation request

## Technical Details

| | |
|---|---|
| **Framework** | Next.js 14 (Pages Router) |
| **Language** | TypeScript |
| **Port** | 3002 |
| **Role** | Module Federation **REMOTE** |
| **Styling** | CSS Modules |
| **Exposed** | `./ProfileApp` component via `static/chunks/remoteEntry.js` |

### Key Files

- `components/ProfileApp.tsx` — Main component: session restore, saved events fetch, preferences editor
- `components/ProfileApp.module.css` — Styles
- `pages/_app.tsx` — Minimal Next.js entry
- `next.config.js` — MF remote config: name `profile`, exposes `./ProfileApp`

### Connects To

| Service | Endpoint | Purpose |
|---------|----------|---------|
| `event-svc` (8080) | `GET /user` | Load user preferences |
| `event-svc` (8080) | `GET /user/saved-events` | Load saved event IDs |
| `event-svc` (8080) | `GET /events/:id` | Resolve IDs to full event details |
| `event-svc` (8080) | `DELETE /user/saved-events/:id` | Unsave event |
| `event-svc` (8080) | `PUT /user/preferences` | Save category preferences |
| `session-svc` (8081) | `GET /sessions/:id` | Restore session (reads sessionId from localStorage) |
| `session-svc` (8081) | `DELETE /sessions/:id/saved-events/:id` | Sync unsave to session |

### Environment Variables

| Variable | Default | Purpose |
|----------|---------|---------|
| `NEXT_PUBLIC_EVENT_SVC_URL` | `http://localhost:8080` | event-svc base URL |
| `NEXT_PUBLIC_SESSION_SVC_URL` | `http://localhost:8081` | session-svc base URL |
| `NEXT_PRIVATE_LOCAL_WEBPACK` | `true` (set in Dockerfile) | Required by MF plugin |

### Run Locally

```bash
npm install
npm run dev  # http://localhost:3002
```

## Be Careful Of

- **MF remote name must be `profile`** and expose `./ProfileApp` — pulse-shell's `next.config.js` imports it by this exact name
- **Session ID is read from `localStorage.pulse_session_id`** — set by pulse-feed when the session is first created. If pulse-feed hasn't run yet, the session restore silently skips
- **Saved events are loaded in two hops**: event-svc returns only IDs, then each ID is fetched individually — fine for demo scale
- **Preferences save is best-effort** — the `PUT /user/preferences` call has no retry or error toast on failure
- Docker builds must target **arm64** (Raspberry Pi cluster)
- The `enhanced-resolve` package must be pinned to `5.20.0` in `package-lock.json` — the default version breaks the arm64 Docker build
