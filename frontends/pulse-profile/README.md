# pulse-profile

## What is it?

pulse-profile will be the **user profile micro-frontend** — a place where users can view their saved events, edit their preferences (favourite categories, preferred times), and manage their AI settings. It will be loaded into pulse-shell via Module Federation, just like pulse-feed.

**Status: Not built yet (Week 2 backlog)**

## Planned User Journey

1. User navigates to their profile section within pulse-shell
2. They see a list of events they've saved (fetched from session-svc)
3. They can unsave events or adjust their category/time preferences
4. Preference changes feed into ai-svc's recommendation engine

## Technical Details (Planned)

| | |
|---|---|
| **Framework** | Next.js 14 (App Router) |
| **Language** | TypeScript |
| **Port** | 3002 |
| **Role** | Module Federation **REMOTE** |
| **Styling** | CSS Modules |

### Will Connect To

- **session-svc** (port 8081) — saved events CRUD
- **event-svc** (port 8080) — user preferences read/write

## Be Careful Of

- pulse-shell's `next.config.js` already references this MFE at `NEXT_PUBLIC_PROFILE_MFE_URL` (default `http://localhost:3002`) — the Module Federation remote name must be `profile` and expose `./ProfileApp`
- Follow the same CSS Modules pattern as pulse-feed — no global styles, use the design tokens from pulse-shell's `globals.css`
- Must use the same font and color conventions as the rest of the app (Bebas Neue + DM Sans, accent #e8ff3c)
