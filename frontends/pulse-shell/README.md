# pulse-shell

## What is it?

pulse-shell is the **main app shell** — the first thing a user sees when they open PULSE. It renders the global header (logo, city, AI status indicator) and dynamically loads the other micro-frontends (pulse-feed, pulse-profile) into the page via Module Federation.

From a user's perspective, this _is_ the app. They never navigate to a different domain — pulse-shell orchestrates everything under one roof.

## User Journey

1. User opens the app at `/`
2. pulse-shell renders the header showing "PULSE" branding, the demo city (London), and a live AI status dot (green/amber/red)
3. The main content area loads the `FeedApp` component from pulse-feed (port 3001) at runtime via Module Federation
4. If the feed MFE fails to load, a fallback message appears instead of a blank screen

## Technical Details

| | |
|---|---|
| **Framework** | Next.js 14 (App Router) |
| **Language** | TypeScript |
| **Port** | 3000 |
| **Role** | Module Federation **HOST** |
| **Styling** | CSS Modules + global CSS variables in `globals.css` |
| **Fonts** | Bebas Neue (display) + DM Sans (body) |

### Key Files

- `app/page.tsx` — Root page, dynamically imports `FeedApp` from pulse-feed MFE
- `app/layout.tsx` — HTML metadata, font loading, global styles
- `components/Header.tsx` — Logo, city label, AI status indicator (fetches `/user` from event-svc)
- `next.config.js` — Module Federation HOST config (imports `feed` and `profile` remotes)
- `app/globals.css` — Design system tokens (colors, fonts)

### Environment Variables

| Variable | Default | Purpose |
|----------|---------|---------|
| `NEXT_PUBLIC_FEED_MFE_URL` | `http://localhost:3001` | Where to load pulse-feed's remoteEntry.js |
| `NEXT_PUBLIC_PROFILE_MFE_URL` | `http://localhost:3002` | Where to load pulse-profile's remoteEntry.js |
| `NEXT_PRIVATE_LOCAL_WEBPACK` | `true` (set in Dockerfile) | Required by Module Federation plugin |

### Run Locally

```bash
npm install
npm run dev  # http://localhost:3000
```

## Be Careful Of

- **Do NOT change the fonts or color variables** in `globals.css` — they are the design system and shared across all MFEs
- Module Federation loading is **client-side only** — these dynamic imports don't work during SSR
- The Dockerfile sets `NEXT_PRIVATE_LOCAL_WEBPACK=true` which is required for the `@module-federation/nextjs-mf` plugin to work — don't remove it
- The header fetches `/user` from event-svc to show AI status — if event-svc is down, the status dot won't render (no error, just missing)
