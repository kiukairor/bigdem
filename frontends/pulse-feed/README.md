# pulse-feed

## What is it?

pulse-feed is the **main content experience** — it shows a grid of London events, lets users filter by category, save events, and toggle AI-powered recommendations on or off. It runs as a remote micro-frontend loaded into pulse-shell via Module Federation.

From a user's perspective, this is where they spend most of their time: browsing events, reading AI suggestions, and deciding what to attend.

## User Journey

1. User sees a grid of event cards (music, food, art, sport, tech) fetched from event-svc
2. Category filter pills at the top let them narrow down by type
3. Each card shows title, venue, date/time, price (or "FREE"), and a save button
4. On the right, an AI recommendation panel suggests 3 personalised events with reasons
5. User can toggle "AI Enhanced" off — a micro-survey pops up asking why (wrong / slow / impersonal / prefer browsing)
6. The opt-out reason is sent to event-svc and logged as a New Relic custom event (`UserAIOptOut`)

## Technical Details

| | |
|---|---|
| **Framework** | Next.js 14 (App Router) |
| **Language** | TypeScript |
| **Port** | 3001 |
| **Role** | Module Federation **REMOTE** |
| **Styling** | CSS Modules (`.module.css` per component) |
| **Exposed** | `./FeedApp` component via `static/chunks/remoteEntry.js` |

### Key Files

- `components/FeedApp.tsx` — Main orchestrator: fetches events + user, manages AI toggle, renders grid + sidebar
- `components/EventCard.tsx` — Individual event card with category color coding and save button
- `components/AIToggle.tsx` — Toggle button + reason survey modal on disable
- `components/RecommendationPanel.tsx` — AI sidebar showing recommendations with mode indicator (AI / Cached / Rule-based)
- `next.config.js` — Module Federation REMOTE config, exposes `./FeedApp`

### Environment Variables

| Variable | Default | Purpose |
|----------|---------|---------|
| `NEXT_PUBLIC_EVENT_SVC_URL` | `http://localhost:8080` | event-svc base URL for events + user data |
| `NEXT_PUBLIC_AI_SVC_URL` | `http://localhost:8082` | ai-svc base URL for recommendations |

### Run Locally

```bash
npm install
npm run dev  # http://localhost:3001
```

## Be Careful Of

- **Save button is local state only** — saved event IDs are tracked in React state, NOT persisted to session-svc yet (Week 2 backlog)
- The `POST /recommendations` request sends the **full `available_events` array** to ai-svc — this can cause token explosion if the event list grows. ai-svc caps at 20 events on its side, but the network payload still includes everything
- Category color mapping is hardcoded in `EventCard.tsx` — if you add new categories, add their colors there
- The AI toggle sends the preference update but **doesn't await the response** — fire-and-forget
- Recommendation panel shows 3 modes: "AI POWERED" (green), "CACHED" (orange), "RULE-BASED" (dim) — these map to the `mode` field in the ai-svc response
