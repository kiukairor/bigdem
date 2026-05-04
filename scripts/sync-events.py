#!/usr/bin/env python3
"""
Sync AI-generated events into the PULSE events table using Google Gemini.

Gemini generates 40 realistic upcoming events (20 London + 20 Paris) across
5 categories each. Dates are always in the future relative to today, using
real venue names for each city.

Direct DB mode (K8s CronJob — when POSTGRES_HOST is set):
  Writes directly to PostgreSQL via psycopg2.

SQL stdout mode (manual use):
  python3 scripts/sync-events.py | kubectl exec -n pulse-prod -i postgresql-0 -- psql -U pulse -d pulse
"""

import os
import sys
import json
from datetime import datetime, timezone
from google import genai as google_genai

GEMINI_API_KEY = os.getenv("GEMINI_API_KEY", "")
GEMINI_MODEL   = os.getenv("GEMINI_MODEL", "gemini-3.1-flash-lite-preview")
TODAY          = datetime.now(timezone.utc).strftime("%Y-%m-%d")

client = google_genai.Client(api_key=GEMINI_API_KEY)

CITIES = [
    {"city": "London", "id_prefix": "lon"},
    {"city": "Paris",  "id_prefix": "par"},
]

CATEGORIES = ["music", "food", "art", "sport", "tech"]


# ---------------------------------------------------------------------------
# Gemini fetch
# ---------------------------------------------------------------------------

def build_prompt(city: str, id_prefix: str) -> str:
    return f"""Generate 20 realistic upcoming events for {city}.
Use exactly 4 events per category: {', '.join(CATEGORIES)}.
Today is {TODAY}. Set event dates between tomorrow and {TODAY} + 30 days.
Use real, well-known venue names in {city}.

Return ONLY a valid JSON array of exactly 20 objects. No preamble, no explanation.
Each object must have these exact fields:
{{
  "id": "{id_prefix}-music-1",
  "title": "...",
  "description": "...",
  "category": "music",
  "venue": "...",
  "address": "full street address, {city}",
  "city": "{city}",
  "date": "2026-05-10T19:00:00+00:00",
  "price_gbp": 0.00,
  "image_url": "",
  "ticket_url": "",
  "tags": ["tag1", "tag2"]
}}

Rules:
- id format: {id_prefix}-<category>-<1..4>  (e.g. {id_prefix}-music-1 through {id_prefix}-music-4)
- category must be one of: {', '.join(CATEGORIES)}
- date must be ISO 8601 UTC
- price_gbp is numeric (GBP equivalent, 0 if free)
- tags: 2-3 short lowercase strings"""


def parse_json(raw: str) -> list[dict]:
    raw = raw.strip()
    if raw.startswith("```"):
        parts = raw.split("```")
        raw = parts[1] if len(parts) > 1 else raw
        if raw.startswith("json"):
            raw = raw[4:]
        raw = raw.strip()
    return json.loads(raw)


def fetch_events(city: str, id_prefix: str) -> list[dict]:
    print(f"-- Generating {city} events via Gemini...", file=sys.stderr)
    response = client.models.generate_content(
        model=GEMINI_MODEL,
        contents=build_prompt(city, id_prefix),
    )
    events = parse_json(response.text)
    print(f"-- {city}: {len(events)} events generated", file=sys.stderr)
    return events


# ---------------------------------------------------------------------------
# SQL output (stdout / legacy mode)
# ---------------------------------------------------------------------------

def sq(s: str) -> str:
    return s.replace("'", "''")


def emit_sql(events: list[dict]) -> None:
    cities = list({sq(ev["city"]) for ev in events})
    city_list = ", ".join(f"'{c}'" for c in cities)
    print("BEGIN;")
    print()
    print(f"-- Full replacement for cities: {city_list}")
    print(f"DELETE FROM saved_events WHERE event_id IN (SELECT id FROM events WHERE city IN ({city_list}));")
    print(f"DELETE FROM events WHERE city IN ({city_list});")
    print()
    for ev in events:
        tags = "ARRAY[" + ", ".join(f"'{sq(t)}'" for t in ev["tags"]) + "]"
        print(
            f"INSERT INTO events "
            f"(id, title, description, category, venue, address, city, date, price_gbp, image_url, ticket_url, tags) VALUES ("
            f"'{sq(ev['id'])}', "
            f"'{sq(ev['title'])}', "
            f"'{sq(ev['description'])}', "
            f"'{sq(ev['category'])}', "
            f"'{sq(ev['venue'])}', "
            f"'{sq(ev['address'])}', "
            f"'{sq(ev['city'])}', "
            f"'{ev['date']}', "
            f"{ev['price_gbp']}, "
            f"'{sq(ev['image_url'])}', "
            f"'{sq(ev['ticket_url'])}', "
            f"{tags}"
            f") ON CONFLICT (id) DO UPDATE SET "
            f"title=EXCLUDED.title, description=EXCLUDED.description, "
            f"category=EXCLUDED.category, venue=EXCLUDED.venue, "
            f"address=EXCLUDED.address, city=EXCLUDED.city, "
            f"date=EXCLUDED.date, price_gbp=EXCLUDED.price_gbp, "
            f"image_url=EXCLUDED.image_url, ticket_url=EXCLUDED.ticket_url, tags=EXCLUDED.tags;"
        )
    print()
    print("COMMIT;")
    print(f"\\echo 'Synced {len(events)} events via Gemini'")


# ---------------------------------------------------------------------------
# Direct DB mode (K8s CronJob)
# ---------------------------------------------------------------------------

def execute_to_db(events: list[dict]) -> None:
    import psycopg2
    conn = psycopg2.connect(
        host=os.getenv("POSTGRES_HOST", "postgresql"),
        port=int(os.getenv("POSTGRES_PORT", "5432")),
        user=os.getenv("POSTGRES_USER", "pulse"),
        password=os.getenv("POSTGRES_PASSWORD", ""),
        dbname=os.getenv("POSTGRES_DB", "pulse"),
    )
    conn.autocommit = False
    cur = conn.cursor()
    cities = list({ev["city"] for ev in events})
    try:
        cur.execute("DELETE FROM saved_events WHERE event_id IN (SELECT id FROM events WHERE city = ANY(%s))", (cities,))
        cur.execute("DELETE FROM events WHERE city = ANY(%s)", (cities,))
        for ev in events:
            cur.execute(
                """
                INSERT INTO events
                  (id, title, description, category, venue, address, city, date,
                   price_gbp, image_url, ticket_url, tags)
                VALUES (%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s)
                ON CONFLICT (id) DO UPDATE SET
                  title=EXCLUDED.title, description=EXCLUDED.description,
                  category=EXCLUDED.category, venue=EXCLUDED.venue,
                  address=EXCLUDED.address, city=EXCLUDED.city,
                  date=EXCLUDED.date, price_gbp=EXCLUDED.price_gbp,
                  image_url=EXCLUDED.image_url, ticket_url=EXCLUDED.ticket_url,
                  tags=EXCLUDED.tags
                """,
                (
                    ev["id"], ev["title"], ev["description"], ev["category"],
                    ev["venue"], ev["address"], ev["city"], ev["date"],
                    ev["price_gbp"], ev["image_url"], ev["ticket_url"], ev["tags"],
                ),
            )
        conn.commit()
        print(f"-- Synced {len(events)} events to database", file=sys.stderr)
    except Exception:
        conn.rollback()
        raise
    finally:
        cur.close()
        conn.close()


# ---------------------------------------------------------------------------
# Main
# ---------------------------------------------------------------------------

def main() -> None:
    events = []
    for c in CITIES:
        events += fetch_events(c["city"], c["id_prefix"])
    print(f"-- Grand total: {len(events)} events", file=sys.stderr)
    if not events:
        print("-- ERROR: no events generated — aborting to preserve existing data", file=sys.stderr)
        sys.exit(1)
    if os.getenv("POSTGRES_HOST"):
        execute_to_db(events)
    else:
        emit_sql(events)


if __name__ == "__main__":
    main()
