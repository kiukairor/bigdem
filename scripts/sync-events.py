#!/usr/bin/env python3
"""
Sync real events into the PULSE events table using the best available source per city:

  London → Ticketmaster Discovery API  (TICKETMASTER_API_KEY required)
  Paris  → Paris Open Data "que-faire-a-paris" (no auth, 1 800+ events)

Outputs SQL on stdout; pipe into the Postgres pod:
  python3 scripts/sync-events.py | kubectl exec -n pulse-prod -i postgresql-0 -- psql -U pulse -d pulse

Adding a new city:
  Implement a fetch_<city>() that returns a list of dicts matching EVENT_FIELDS,
  then add it to CITIES below.
"""

import html
import os
import re
import sys
import json
import requests
from datetime import datetime, timezone
from typing import Optional

# ---------------------------------------------------------------------------
# Config
# ---------------------------------------------------------------------------

TM_API_KEY = os.getenv("TICKETMASTER_API_KEY", "")
TM_BASE    = "https://app.ticketmaster.com/discovery/v2/events.json"
PARIS_BASE = "https://opendata.paris.fr/api/explore/v2.1/catalog/datasets/que-faire-a-paris-/records"
TODAY      = datetime.now(timezone.utc).strftime("%Y-%m-%d")

# Ticketmaster segment → PULSE category
TM_SEGMENT_MAP = {
    "Music":           "music",
    "Arts & Theatre":  "art",
    "Sports":          "sport",
    "Food & Drink":    "food",
}

# Paris Open Data qfap_tags → PULSE category (first match wins)
PARIS_TAG_MAP = [
    ({"Concert", "Spectacle musical", "Festival", "Nuit"}, "music"),
    ({"Sport"},                                             "sport"),
    ({"Gastronomie", "Marché"},                            "food"),
    ({"Conférence", "Atelier", "Numérique"},               "tech"),
    ({"Théâtre", "Danse", "Expo", "Humour", "Cirque",
      "Littérature", "Ecrans", "Balade urbaine"},           "art"),
]

# Per-city, per-category target event counts
TM_SEGMENTS = [
    {"tm": "Music",          "pulse": "music", "count": 14},
    {"tm": "Arts & Theatre", "pulse": "art",   "count": 10},
    {"tm": "Sports",         "pulse": "sport",  "count": 8},
    {"tm": "Food & Drink",   "pulse": "food",   "count": 3},
]

PARIS_SEGMENTS = [
    {"tags": ["Concert", "Festival", "Spectacle musical"], "pulse": "music", "count": 12},
    {"tags": ["Théâtre", "Danse", "Expo", "Humour"],       "pulse": "art",   "count": 10},
    {"tags": ["Sport"],                                     "pulse": "sport",  "count": 8},
    {"tags": ["Conférence"],                                "pulse": "tech",   "count": 5},
]


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def strip_html(text: str) -> str:
    """Remove HTML tags and decode entities."""
    text = re.sub(r"<[^>]+>", " ", text or "")
    text = html.unescape(text)
    return " ".join(text.split())


def parse_eur_price(price_detail: Optional[str]) -> float:
    """Extract the first numeric value from price_detail HTML. Returns 0.0 if free."""
    if not price_detail:
        return 0.0
    text = strip_html(price_detail).lower()
    if any(w in text for w in ("gratuit", "libre", "free")):
        return 0.0
    match = re.search(r"(\d+(?:[.,]\d+)?)", text)
    if match:
        return round(float(match.group(1).replace(",", ".")), 2)
    return 0.0


# ---------------------------------------------------------------------------
# Ticketmaster source (London, or any city with TM coverage)
# ---------------------------------------------------------------------------

def fetch_tm_segment(lat: str, lon: str, segment: dict, size: int) -> list[dict]:
    params = {
        "apikey":             TM_API_KEY,
        "geoPoint":           f"{lat},{lon}",
        "radius":             20,
        "unit":               "km",
        "size":               size,
        "classificationName": segment["tm"],
        "sort":               "date,asc",
        "locale":             "*",
    }
    resp = requests.get(TM_BASE, params=params, timeout=15)
    resp.raise_for_status()
    return resp.json().get("_embedded", {}).get("events", [])


def map_tm_event(ev: dict, city: str, pulse_category: str) -> Optional[dict]:
    venues = (ev.get("_embedded") or {}).get("venues") or [{}]
    venue  = venues[0]
    addr_parts = [
        (venue.get("address") or {}).get("line1", ""),
        (venue.get("city")    or {}).get("name", ""),
        venue.get("postalCode", ""),
    ]
    address    = ", ".join(p for p in addr_parts if p)
    venue_name = venue.get("name", "")

    classifications = ev.get("classifications") or []
    genre = (classifications[0].get("genre") or {}).get("name", "") if classifications else ""

    start    = (ev.get("dates") or {}).get("start") or {}
    date_str = start.get("dateTime")
    if not date_str:
        local = start.get("localDate", "")
        if not local:
            return None
        date_str = local + "T20:00:00Z"
    try:
        date = datetime.fromisoformat(date_str.replace("Z", "+00:00"))
    except Exception:
        return None

    prices = ev.get("priceRanges") or []
    price  = float(prices[0].get("min", 0)) if prices else 0.0

    images    = ev.get("images") or []
    image_url = max(images, key=lambda i: i.get("width", 0)).get("url", "") if images else ""

    tags = [pulse_category]
    if genre and genre not in ("Undefined", "Other", ""):
        tags.append(genre.lower())

    return {
        "id":          ev["id"][:64],
        "title":       ev.get("name", "")[:255],
        "description": strip_html(ev.get("info") or ev.get("pleaseNote") or ev.get("name", ""))[:2000],
        "category":    pulse_category,
        "venue":       venue_name[:255],
        "address":     address[:255],
        "city":        city,
        "date":        date.isoformat(),
        "price_gbp":   round(price, 2),
        "image_url":   image_url[:512],
        "ticket_url":  ev.get("url", "")[:512],
        "tags":        tags,
    }


def fetch_london() -> list[dict]:
    if not TM_API_KEY:
        print("-- WARN: TICKETMASTER_API_KEY not set, skipping London", file=sys.stderr)
        return []
    lat, lon = "51.5074", "-0.1278"
    result, seen = [], set()
    for seg in TM_SEGMENTS:
        fetch_n = seg["count"] * 2
        print(f"-- London / {seg['tm']} (want {seg['count']})...", file=sys.stderr)
        try:
            raw = fetch_tm_segment(lat, lon, seg, fetch_n)
        except Exception as e:
            print(f"--   WARN: {e}", file=sys.stderr)
            continue
        added = 0
        for ev in raw:
            if added >= seg["count"]:
                break
            mapped = map_tm_event(ev, "London", seg["pulse"])
            if mapped and mapped["id"] not in seen:
                seen.add(mapped["id"])
                result.append(mapped)
                added += 1
        print(f"--   → {added} added", file=sys.stderr)
    print(f"-- London total: {len(result)}", file=sys.stderr)
    return result


# ---------------------------------------------------------------------------
# Paris Open Data source
# ---------------------------------------------------------------------------

def fetch_paris_segment(tags: list[str], pulse_category: str, count: int) -> list[dict]:
    tag_filter = " OR ".join(f"qfap_tags LIKE '%{t}%'" for t in tags)
    where = f"date_start >= date'{TODAY}' AND address_name IS NOT NULL AND ({tag_filter})"
    params = {
        "limit":    count * 2,
        "where":    where,
        "order_by": "date_start",
    }
    resp = requests.get(PARIS_BASE, params=params, timeout=15)
    resp.raise_for_status()
    return resp.json().get("results", [])


def map_paris_event(rec: dict, pulse_category: str) -> Optional[dict]:
    date_str = rec.get("date_start")
    if not date_str:
        return None
    try:
        date = datetime.fromisoformat(date_str.replace("Z", "+00:00"))
    except Exception:
        return None

    venue    = rec.get("address_name", "") or rec.get("contact_organisation_name", "")
    zipcode  = rec.get("address_zipcode", "") or ""
    address  = f"{venue}, {zipcode} Paris".strip(", ") if venue else "Paris"

    raw_tags = [t.strip() for t in (rec.get("qfap_tags") or "").split(";") if t.strip()]
    tags     = [pulse_category] + [t.lower() for t in raw_tags[:3] if t.lower() != pulse_category]

    desc = strip_html(rec.get("description") or rec.get("lead_text") or rec.get("title", ""))

    return {
        "id":          f"par-{rec['id']}"[:64],
        "title":       rec.get("title", "")[:255],
        "description": desc[:2000],
        "category":    pulse_category,
        "venue":       venue[:255],
        "address":     address[:255],
        "city":        "Paris",
        "date":        date.isoformat(),
        "price_gbp":   parse_eur_price(rec.get("price_detail") or ("0" if rec.get("price_type") == "gratuit" else None)),
        "image_url":   (rec.get("cover_url") or "")[:512],
        "ticket_url":  (rec.get("url") or rec.get("url_canonical") or "")[:512],
        "tags":        tags,
    }


def fetch_paris() -> list[dict]:
    result, seen = [], set()
    for seg in PARIS_SEGMENTS:
        print(f"-- Paris / {seg['tags'][0]} (want {seg['count']})...", file=sys.stderr)
        try:
            raw = fetch_paris_segment(seg["tags"], seg["pulse"], seg["count"])
        except Exception as e:
            print(f"--   WARN: {e}", file=sys.stderr)
            continue
        added = 0
        for rec in raw:
            if added >= seg["count"]:
                break
            mapped = map_paris_event(rec, seg["pulse"])
            if mapped and mapped["id"] not in seen:
                seen.add(mapped["id"])
                result.append(mapped)
                added += 1
        print(f"--   → {added} added", file=sys.stderr)
    print(f"-- Paris total: {len(result)}", file=sys.stderr)
    return result


# ---------------------------------------------------------------------------
# SQL output
# ---------------------------------------------------------------------------

def sq(s: str) -> str:
    """SQL-escape a string value."""
    return s.replace("'", "''")


def emit_sql(events: list[dict]) -> None:
    print("BEGIN;")
    print()
    print("DELETE FROM saved_events;")
    print("DELETE FROM events;")
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
    print(f"\\echo 'Synced {len(events)} events (London: Ticketmaster, Paris: Paris Open Data)'")


# ---------------------------------------------------------------------------
# Main
# ---------------------------------------------------------------------------

def main() -> None:
    events  = fetch_london()
    events += fetch_paris()
    print(f"-- Grand total: {len(events)} events", file=sys.stderr)
    emit_sql(events)


if __name__ == "__main__":
    main()
