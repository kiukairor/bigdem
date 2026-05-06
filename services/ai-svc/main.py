import newrelic.agent
newrelic.agent.initialize()

import os
import re
import json
import time
import logging
import requests as http_requests
import redis as redis_lib
from fastapi import FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel
from typing import Optional
from anthropic import Anthropic
from google import genai as google_genai
from openai import OpenAI
from circuit_breaker import CircuitBreaker

logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(name)s %(message)s")
log = logging.getLogger("ai-svc")

app = FastAPI(title="pulse-ai-svc")
app.add_middleware(CORSMiddleware, allow_origins=["*"], allow_methods=["*"], allow_headers=["*"])

anthropic_client = Anthropic(api_key=os.getenv("ANTHROPIC_API_KEY", ""))
gemini_client    = google_genai.Client(api_key=os.getenv("GEMINI_API_KEY", ""))
_openai_key   = os.getenv("OPENAI_API_KEY", "")
openai_client = OpenAI(api_key=_openai_key) if _openai_key else None

cb = CircuitBreaker(
    failure_threshold=int(os.getenv("CB_FAILURE_THRESHOLD", "5")),
    recovery_timeout=int(os.getenv("CB_RECOVERY_TIMEOUT_SECONDS", "60")),
)

CLAUDE_MODEL     = os.getenv("CLAUDE_MODEL", "claude-sonnet-4-6")
GEMINI_MODEL     = os.getenv("GEMINI_MODEL", "gemini-3.1-flash-lite-preview")
OPENAI_MODEL     = os.getenv("OPENAI_MODEL", "gpt-4o-mini")
DEFAULT_PROVIDER = os.getenv("AI_PROVIDER", "gemini")
DEMO_CITY        = os.getenv("DEMO_CITY", "London")
EVENT_SVC_URL    = os.getenv("EVENT_SVC_URL", "http://event-svc:8080")
SESSION_SVC_URL  = os.getenv("SESSION_SVC_URL", "http://session-svc:8081")
REC_CACHE_TTL    = 300
BUG_AI_SLOW      = os.getenv("BUG_AI_SLOW", "false").lower() == "true"
TM_API_KEY       = os.getenv("TICKETMASTER_API_KEY", "")
TM_BASE          = "https://app.ticketmaster.com/discovery/v2/events.json"
EB_API_KEY       = os.getenv("EVENTBRITE_API_KEY", "")
EB_BASE          = "https://www.eventbriteapi.com/v3/events/search/"
TODAY            = time.strftime("%Y-%m-%d", time.gmtime())

try:
    redis_client = redis_lib.Redis(
        host=os.getenv("REDIS_HOST", "redis"),
        port=int(os.getenv("REDIS_PORT", "6379")),
        decode_responses=True,
    )
    redis_client.ping()
    log.info("Connected to Redis")
except Exception as e:
    log.warning(f"Redis unavailable, caching disabled: {e}")
    redis_client = None


class RecommendationRequest(BaseModel):
    user_id: str
    user_preferences: dict
    saved_event_ids: list[str] = []
    available_events: list[dict] = []
    provider: Optional[str] = None
    session_id: Optional[str] = None
    city: Optional[str] = None


class RecommendationResponse(BaseModel):
    recommendations: list[dict]
    mode: str  # "ai", "degraded", "fallback"
    ai_response_ms: Optional[int] = None
    provider: Optional[str] = None


def _fetch_events_from_event_svc(city: str) -> list[dict]:
    try:
        resp = http_requests.get(
            f"{EVENT_SVC_URL}/events",
            params={"city": city},
            timeout=5,
        )
        resp.raise_for_status()
        events = resp.json()
        log.info(f"Fetched {len(events)} events from event-svc: city={city}")
        return events
    except Exception as e:
        log.warning(f"Failed to fetch events from event-svc: city={city} error={e}")
        return []


def _fetch_saved_from_session_svc(session_id: str) -> list[str]:
    try:
        resp = http_requests.get(
            f"{SESSION_SVC_URL}/sessions/{session_id}",
            timeout=5,
        )
        resp.raise_for_status()
        data = resp.json()
        saved = data.get("saved_event_ids", [])
        log.info(f"Fetched {len(saved)} saved events from session-svc: session={session_id}")
        return saved
    except Exception as e:
        log.warning(f"Failed to fetch saved events from session-svc: session={session_id} error={e}")
        return []


@app.get("/health")
def health():
    return {"status": "ok", "service": "ai-svc", "circuit_breaker": cb.state}


@app.get("/status")
def status():
    return {
        "circuit_breaker_state": cb.state,
        "failure_count": cb.failure_count,
        "provider": DEFAULT_PROVIDER,
        "model": GEMINI_MODEL if DEFAULT_PROVIDER == "gemini" else (OPENAI_MODEL if DEFAULT_PROVIDER == "openai" else CLAUDE_MODEL),
    }


@app.post("/recommendations", response_model=RecommendationResponse)
@newrelic.agent.function_trace()
def get_recommendations(req: RecommendationRequest):
    start = time.time()
    provider = req.provider or DEFAULT_PROVIDER
    city = req.city or req.user_preferences.get("city", DEMO_CITY)

    # Fetch data from internal services when not supplied by the caller — creates
    # real service-to-service spans visible in NR Service Maps
    available_events = req.available_events
    if not available_events:
        log.info(f"No events in request — fetching from event-svc: city={city}")
        available_events = _fetch_events_from_event_svc(city)

    saved_event_ids = req.saved_event_ids
    if not saved_event_ids and req.session_id:
        log.info(f"No saved IDs in request — fetching from session-svc: session={req.session_id}")
        saved_event_ids = _fetch_saved_from_session_svc(req.session_id)

    req = req.model_copy(update={
        "available_events": available_events,
        "saved_event_ids": saved_event_ids,
    })

    cache_key = f"rec:{req.user_id}:{city}:{provider}"

    newrelic.agent.add_custom_attribute("user_id", req.user_id)
    newrelic.agent.add_custom_attribute("available_events_count", len(req.available_events))
    newrelic.agent.add_custom_attribute("circuit_breaker_state", cb.state)
    newrelic.agent.add_custom_attribute("ai_provider", provider)

    log.info(
        f"Recommendations request: user={req.user_id} city={city} provider={provider} "
        f"events={len(req.available_events)} saved={len(req.saved_event_ids)} cb={cb.state}"
    )

    if redis_client and not BUG_AI_SLOW:
        try:
            cached = redis_client.get(cache_key)
            if cached:
                newrelic.agent.add_custom_attribute("cache_hit", True)
                log.info(f"Cache HIT for key={cache_key} — returning cached recommendations")
                return RecommendationResponse(
                    recommendations=json.loads(cached),
                    mode="ai",
                    ai_response_ms=0,
                    provider=provider,
                )
            else:
                log.info(f"Cache MISS for key={cache_key} — will call {provider} AI")
        except Exception as e:
            log.warning(f"Redis read error (cache disabled for this request): {e}")
    newrelic.agent.add_custom_attribute("cache_hit", False)

    if cb.state == "OPEN":
        log.warning(
            f"Circuit breaker OPEN — skipping AI call for user={req.user_id}, "
            f"falling back to rule-based recommendations"
        )
        newrelic.agent.record_custom_event("AIFallback", {
            "user_id": req.user_id,
            "reason": "circuit_breaker_open",
        })
        fallback_recs = rule_based_fallback(req)
        log.info(f"Rule-based fallback produced {len(fallback_recs)} recommendations for user={req.user_id}")
        return RecommendationResponse(
            recommendations=fallback_recs,
            mode="fallback",
            provider=provider,
        )

    try:
        recs = call_ai(req, provider)
        elapsed_ms = int((time.time() - start) * 1000)
        cb.record_success()

        log.info(
            f"AI recommendations OK: user={req.user_id} provider={provider} "
            f"recs={len(recs)} latency_ms={elapsed_ms} cb={cb.state}"
        )

        newrelic.agent.add_custom_attribute("ai_response_ms", elapsed_ms)
        newrelic.agent.add_custom_attribute("ai_mode", "ai")

        if redis_client:
            try:
                redis_client.setex(cache_key, REC_CACHE_TTL, json.dumps(recs))
                log.info(f"Cached recommendations for key={cache_key} TTL={REC_CACHE_TTL}s")
            except Exception as e:
                log.warning(f"Redis write error (recommendations not cached): {e}")

        return RecommendationResponse(
            recommendations=recs,
            mode="ai",
            ai_response_ms=elapsed_ms,
            provider=provider,
        )

    except Exception as e:
        log.error(
            f"AI call FAILED: provider={provider} user={req.user_id} "
            f"error={type(e).__name__}: {e} cb_state_after={cb.state}"
        )
        cb.record_failure()

        newrelic.agent.notice_error()
        newrelic.agent.record_custom_event("AIServiceError", {
            "user_id": req.user_id,
            "provider": provider,
            "error_type": type(e).__name__,
            "circuit_breaker_state": cb.state,
        })

        mode = "degraded" if cb.state != "OPEN" else "fallback"
        fallback_recs = rule_based_fallback(req)
        log.warning(f"Serving {mode} response: {len(fallback_recs)} rule-based recs for user={req.user_id}")
        return RecommendationResponse(
            recommendations=fallback_recs,
            mode=mode,
            provider=provider,
        )


def call_ai(req: RecommendationRequest, provider: str) -> list[dict]:
    if BUG_AI_SLOW:
        log.warning(f"BUG_AI_SLOW active: injecting 8s delay before {provider} call")
        newrelic.agent.add_custom_attribute("bug_ai_slow", True)
        newrelic.agent.record_custom_event("BugScenarioEnabled", {
            "bug": "BUG_AI_SLOW",
            "service": "ai-svc",
            "delay_ms": 8000,
        })
        time.sleep(8)

    if provider == "claude":
        model = CLAUDE_MODEL
    elif provider == "openai":
        model = OPENAI_MODEL
    else:
        model = GEMINI_MODEL
    log.info(f"Calling {provider} API: model={model} user={req.user_id} events={len(req.available_events)}")
    t0 = time.time()
    if provider == "claude":
        result = call_claude(req)
    elif provider == "openai":
        result = call_openai(req)
    else:
        result = call_gemini(req)
    log.info(f"{provider} API returned {len(result)} recommendations in {int((time.time()-t0)*1000)}ms")
    return result


def _build_prompt(req: RecommendationRequest) -> str:
    prefs = req.user_preferences
    city = req.city or prefs.get("city", DEMO_CITY)
    saved_ids = set(req.saved_event_ids)
    event_map = {e["id"]: e for e in req.available_events}

    saved_details = [
        f"  - {event_map[eid]['title']} ({event_map[eid]['category']}) at {event_map[eid]['venue']}"
        for eid in saved_ids
        if eid in event_map
    ]
    saved_summary = "\n".join(saved_details) if saved_details else "  (none yet)"

    events_summary = []
    for e in req.available_events[:20]:
        events_summary.append(
            f"- [{e['id']}] {e['title']} ({e['category']}) on {e['date'][:10]} "
            f"at {e['venue']} — £{e.get('price_gbp', 0) or 0}"
        )
    return f"""You are a personalised event recommendation engine for {city}.

User preferences:
- Favourite categories: {prefs.get('categories', [])}
- Preferred times: {prefs.get('times', [])}
- Previously saved events (use these to understand their taste):
{saved_summary}

Available events:
{chr(10).join(events_summary)}

Return ONLY a JSON array of exactly 3 event IDs that best match this user, with a short reason for each.
Format: [{{"id": "evt_xxx", "reason": "..."}}, ...]
No preamble, no explanation, just the JSON array."""


def _parse_recs(raw: str, req: RecommendationRequest) -> list[dict]:
    raw = raw.strip()
    if raw.startswith("```"):
        parts = raw.split("```")
        raw = parts[1] if len(parts) > 1 else raw
        if raw.startswith("json"):
            raw = raw[4:]
        raw = raw.strip()
    recs_raw = json.loads(raw)
    event_map = {e["id"]: e for e in req.available_events}
    return [
        {**event_map[r["id"]], "reason": r["reason"]}
        for r in recs_raw
        if r["id"] in event_map
    ]


def _record_llm_event(vendor: str, model: str, prompt: str, reply: str,
                      input_tokens: int, output_tokens: int) -> None:
    import uuid
    request_id = str(uuid.uuid4())
    span_id     = newrelic.agent.current_span_id()   if hasattr(newrelic.agent, "current_span_id")   else ""
    trace_id    = newrelic.agent.current_trace_id()
    tx          = newrelic.agent.current_transaction()
    tx_id       = tx.guid if tx else ""
    base = {
        "id": request_id, "vendor": vendor, "ingest_source": "Python",
        "request.model": model, "response.model": model,
        "request_id": request_id, "trace_id": trace_id,
        "span_id": span_id, "transaction_id": tx_id,
        "response.usage.input_tokens": input_tokens,
        "response.usage.output_tokens": output_tokens,
        "response.usage.total_tokens": input_tokens + output_tokens,
        "response.number_of_messages": 2,
    }
    newrelic.agent.record_custom_event("LlmChatCompletionSummary", base)
    newrelic.agent.record_custom_event("LlmChatCompletionMessage", {
        **base, "sequence": 0, "role": "user",
        "content": prompt[:4095], "completion_id": request_id,
    })
    newrelic.agent.record_custom_event("LlmChatCompletionMessage", {
        **base, "sequence": 1, "role": "assistant",
        "content": reply[:4095], "completion_id": request_id,
    })


def _record_tokens(provider: str, model: str, input_tokens: int, output_tokens: int) -> None:
    total = input_tokens + output_tokens
    newrelic.agent.add_custom_attribute("llm.provider", provider)
    newrelic.agent.add_custom_attribute("llm.model", model)
    newrelic.agent.add_custom_attribute("llm.input_tokens", input_tokens)
    newrelic.agent.add_custom_attribute("llm.output_tokens", output_tokens)
    newrelic.agent.add_custom_attribute("llm.total_tokens", total)
    newrelic.agent.record_custom_metric("Custom/LLM/InputTokens", input_tokens)
    newrelic.agent.record_custom_metric("Custom/LLM/OutputTokens", output_tokens)
    log.info(f"LLM tokens: provider={provider} model={model} in={input_tokens} out={output_tokens} total={total}")


def call_gemini(req: RecommendationRequest) -> list[dict]:
    response = gemini_client.models.generate_content(
        model=GEMINI_MODEL,
        contents=_build_prompt(req),
    )
    if getattr(response, "usage_metadata", None):
        _record_tokens(
            "gemini", GEMINI_MODEL,
            response.usage_metadata.prompt_token_count or 0,
            response.usage_metadata.candidates_token_count or 0,
        )
    return _parse_recs(response.text, req)


def call_claude(req: RecommendationRequest) -> list[dict]:
    response = anthropic_client.messages.create(
        model=CLAUDE_MODEL,
        max_tokens=256,
        messages=[{"role": "user", "content": _build_prompt(req)}],
    )
    reply = response.content[0].text
    if getattr(response, "usage", None):
        _record_tokens("claude", CLAUDE_MODEL,
                       response.usage.input_tokens or 0,
                       response.usage.output_tokens or 0)
    _record_llm_event("anthropic", CLAUDE_MODEL, _build_prompt(req), reply,
                      getattr(response.usage, "input_tokens", 0) if response.usage else 0,
                      getattr(response.usage, "output_tokens", 0) if response.usage else 0)
    return _parse_recs(reply, req)


def call_openai(req: RecommendationRequest) -> list[dict]:
    response = openai_client.chat.completions.create(
        model=OPENAI_MODEL,
        max_tokens=256,
        messages=[{"role": "user", "content": _build_prompt(req)}],
    )
    if getattr(response, "usage", None):
        _record_tokens(
            "openai", OPENAI_MODEL,
            response.usage.prompt_tokens or 0,
            response.usage.completion_tokens or 0,
        )
    return _parse_recs(response.choices[0].message.content, req)


def rule_based_fallback(req: RecommendationRequest) -> list[dict]:
    prefs = req.user_preferences
    preferred_cats = prefs.get("categories", [])
    saved_ids = set(req.saved_event_ids)

    candidates = [e for e in req.available_events if e["id"] not in saved_ids]

    if preferred_cats:
        preferred = [e for e in candidates if e["category"] in preferred_cats]
        candidates = preferred if preferred else candidates

    result = candidates[:3]
    for e in result:
        e["reason"] = "Popular in your area"
    return result


# ---------------------------------------------------------------------------
# On-demand city event generation
# ---------------------------------------------------------------------------

TM_SEGMENTS_GENERIC = [
    {"tm": "Music",          "pulse": "music", "count": 5},
    {"tm": "Arts & Theatre", "pulse": "art",   "count": 4},
    {"tm": "Sports",         "pulse": "sport",  "count": 4},
    {"tm": "Food & Drink",   "pulse": "food",   "count": 3},
    {"tm": "Miscellaneous",  "pulse": "tech",   "count": 3},
]


def _map_tm_event(ev: dict, city: str, pulse_category: str) -> Optional[dict]:
    venues     = (ev.get("_embedded") or {}).get("venues") or [{}]
    venue      = venues[0]
    addr_parts = [
        (venue.get("address") or {}).get("line1", ""),
        (venue.get("city")    or {}).get("name", ""),
        venue.get("postalCode", ""),
    ]
    address    = ", ".join(p for p in addr_parts if p)
    start      = (ev.get("dates") or {}).get("start") or {}
    date_str   = start.get("dateTime")
    if not date_str:
        local = start.get("localDate", "")
        if not local:
            return None
        date_str = local + "T20:00:00Z"
    try:
        from datetime import datetime
        date = datetime.fromisoformat(date_str.replace("Z", "+00:00"))
    except Exception:
        return None
    prices    = ev.get("priceRanges") or []
    price     = float(prices[0].get("min", 0)) if prices else 0.0
    images    = ev.get("images") or []
    image_url = max(images, key=lambda i: i.get("width", 0)).get("url", "") if images else ""
    return {
        "id":          ev["id"][:64],
        "title":       ev.get("name", "")[:255],
        "description": ev.get("name", "")[:255],
        "category":    pulse_category,
        "venue":       venue.get("name", "")[:255],
        "address":     address[:255],
        "city":        city,
        "date":        date.isoformat(),
        "price_gbp":   round(price, 2),
        "image_url":   image_url[:512],
        "ticket_url":  ev.get("url", "")[:512],
        "tags":        [pulse_category],
    }


def _fetch_tm_city(city: str) -> list[dict]:
    result, seen = [], set()
    for seg in TM_SEGMENTS_GENERIC:
        try:
            params = {
                "apikey": TM_API_KEY, "city": city,
                "size": seg["count"] * 2, "classificationName": seg["tm"],
                "sort": "date,asc", "locale": "*",
            }
            resp = http_requests.get(TM_BASE, params=params, timeout=15)
            resp.raise_for_status()
            raw = resp.json().get("_embedded", {}).get("events", [])
        except Exception as e:
            log.warning(f"TM fetch failed for {city}/{seg['tm']}: {e}")
            continue
        added = 0
        for ev in raw:
            if added >= seg["count"]:
                break
            mapped = _map_tm_event(ev, city, seg["pulse"])
            if mapped and mapped["id"] not in seen:
                seen.add(mapped["id"])
                result.append(mapped)
                added += 1
    return result


# ---------------------------------------------------------------------------
# Eventbrite event source (food, sport, tech)
# ---------------------------------------------------------------------------

EB_CATEGORY_MAP = {
    "108": "sport",   # Sports & Fitness
    "110": "food",    # Food & Drink
    "102": "tech",    # Science & Technology
}
EB_CATEGORIES = ",".join(EB_CATEGORY_MAP.keys())


def _map_eb_event(ev: dict, city: str) -> Optional[dict]:
    venue     = ev.get("venue") or {}
    addr      = (venue.get("address") or {}).get("localized_address_display", city)
    start     = (ev.get("start") or {}).get("utc")
    if not start:
        return None
    try:
        from datetime import datetime
        date = datetime.fromisoformat(start.replace("Z", "+00:00"))
    except Exception:
        return None
    price_obj = ((ev.get("ticket_availability") or {}).get("minimum_ticket_price") or {})
    price     = float(price_obj.get("major_value", 0) or 0)
    image_url = ((ev.get("logo") or {}).get("url") or "")
    cat_id    = str(ev.get("category_id", ""))
    category  = EB_CATEGORY_MAP.get(cat_id, "tech")
    name      = (ev.get("name") or {}).get("text", "") or ""
    desc      = (ev.get("description") or {}).get("text", "") or name
    return {
        "id":          f"eb-{ev['id'][:60]}",
        "title":       name[:255],
        "description": desc[:255],
        "category":    category,
        "venue":       (venue.get("name") or "")[:255],
        "address":     addr[:255],
        "city":        city,
        "date":        date.isoformat(),
        "price_gbp":   round(price, 2),
        "image_url":   image_url[:512],
        "ticket_url":  (ev.get("url") or "")[:512],
        "tags":        [category],
    }


def _fetch_eventbrite_city(city: str) -> list[dict]:
    if not EB_API_KEY:
        return []
    from datetime import datetime, timezone
    now = datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")
    try:
        resp = http_requests.get(
            EB_BASE,
            headers={"Authorization": f"Bearer {EB_API_KEY}"},
            params={
                "location.address": city,
                "location.within": "20km",
                "categories": EB_CATEGORIES,
                "expand": "venue,ticket_availability",
                "sort_by": "date",
                "start_date.range_start": now,
                "page_size": "50",
            },
            timeout=15,
        )
        resp.raise_for_status()
    except Exception as e:
        log.warning(f"Eventbrite fetch failed for city={city}: {e}")
        return []
    result, seen = [], set()
    for ev in resp.json().get("events", []):
        mapped = _map_eb_event(ev, city)
        if mapped and mapped["id"] not in seen:
            seen.add(mapped["id"])
            result.append(mapped)
    log.info(f"Eventbrite returned {len(result)} events for city={city}")
    return result


_CATEGORY_CONTEXT = {
    "food":  "food & drink events such as supper clubs, food festivals, cooking masterclasses, wine and cocktail tastings, pop-up restaurants, street food markets, and chef's table dinners",
    "sport": "sport & fitness events such as 5K and 10K runs, cycling sportives, yoga and pilates sessions, fitness bootcamps, local football and rugby fixtures, climbing sessions, open-water swims, and tennis tournaments",
    "tech":  "technology events such as hackathons, developer meetups, startup pitch nights, AI and ML workshops, product demo days, coding bootcamps, open-source sprints, and founder networking evenings",
}


def _fetch_gemini_category(city: str, category: str, count: int) -> list[dict]:
    prefix = re.sub(r"[^a-z]", "", city.lower())[:4]
    context = _CATEGORY_CONTEXT.get(category, f"{category} events")
    prompt = f"""Generate {count} realistic upcoming {context} in {city}.
Today is {TODAY}. Set event dates between tomorrow and {TODAY} + 30 days.
Use real, well-known venues in {city} that genuinely host this type of event.
Return ONLY a valid JSON array of exactly {count} objects. No preamble, no explanation.
Each object must follow this exact schema:
{{"id":"{prefix}-{category}-1","title":"...","description":"...","category":"{category}","venue":"<real venue name>","address":"<full street address>, {city}","city":"{city}","date":"2026-05-10T19:00:00+00:00","price_gbp":0.00,"image_url":"","ticket_url":"","tags":["{category}"]}}
Rules: id must be {prefix}-{category}-<1..{count}>. date must be ISO 8601 UTC. title and venue must be specific and realistic, not generic."""
    try:
        response = gemini_client.models.generate_content(model=GEMINI_MODEL, contents=prompt)
        raw = response.text.strip()
        if raw.startswith("```"):
            parts = raw.split("```")
            raw = parts[1][4:].strip() if len(parts) > 1 else raw
        events = json.loads(raw)
        log.info(f"Gemini category fill: city={city} category={category} generated={len(events)}")
        return events
    except Exception as e:
        log.warning(f"Gemini category fill failed: city={city} category={category} error={e}")
        return []


def _fetch_gemini_city(city: str) -> list[dict]:
    prefix = re.sub(r"[^a-z]", "", city.lower())[:4]
    prompt = f"""Generate 20 realistic upcoming events for {city}.
Use exactly 4 events per category: music, food, art, sport, tech.
Today is {TODAY}. Set event dates between tomorrow and {TODAY} + 30 days.
Use real, well-known venue names in {city}.
Return ONLY a valid JSON array of exactly 20 objects. No preamble.
Each object: {{"id":"{prefix}-music-1","title":"...","description":"...","category":"music",
"venue":"...","address":"full address, {city}","city":"{city}","date":"2026-05-10T19:00:00+00:00",
"price_gbp":0.00,"image_url":"","ticket_url":"","tags":["tag1","tag2"]}}
id: {prefix}-<category>-<1..4>. date ISO 8601 UTC."""
    response = gemini_client.models.generate_content(model=GEMINI_MODEL, contents=prompt)
    raw = response.text.strip()
    if raw.startswith("```"):
        parts = raw.split("```")
        raw = parts[1][4:].strip() if len(parts) > 1 else raw
    return json.loads(raw)


def _write_events_to_db(events: list[dict], city: str) -> None:
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
    try:
        cur.execute("DELETE FROM saved_events WHERE event_id IN (SELECT id FROM events WHERE city = %s)", (city,))
        cur.execute("DELETE FROM events WHERE city = %s", (city,))
        for ev in events:
            cur.execute(
                """INSERT INTO events
                     (id, title, description, category, venue, address, city, date,
                      price_gbp, image_url, ticket_url, tags)
                   VALUES (%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s)
                   ON CONFLICT (id) DO UPDATE SET
                     title=EXCLUDED.title, description=EXCLUDED.description,
                     category=EXCLUDED.category, venue=EXCLUDED.venue,
                     address=EXCLUDED.address, city=EXCLUDED.city,
                     date=EXCLUDED.date, price_gbp=EXCLUDED.price_gbp,
                     image_url=EXCLUDED.image_url, ticket_url=EXCLUDED.ticket_url,
                     tags=EXCLUDED.tags""",
                (ev["id"], ev["title"], ev["description"], ev["category"],
                 ev["venue"], ev["address"], ev["city"], ev["date"],
                 ev["price_gbp"], ev["image_url"], ev["ticket_url"], ev["tags"]),
            )
        conn.commit()
    except Exception:
        conn.rollback()
        raise
    finally:
        cur.close()
        conn.close()


class EventGenerateRequest(BaseModel):
    city: str


@app.post("/events/generate")
@newrelic.agent.function_trace()
def generate_events(req: EventGenerateRequest):
    city = req.city.strip().title()
    log.info(
        f"Event generation request: city={city} "
        f"tm={'set' if TM_API_KEY else 'missing'} eb={'set' if EB_API_KEY else 'missing'}"
    )
    newrelic.agent.add_custom_attribute("city", city)

    events: list[dict] = []
    sources: list[str] = []

    # Ticketmaster: strong for music and art
    if TM_API_KEY:
        log.info(f"Fetching music/art from Ticketmaster: city={city}")
        tm_events = _fetch_tm_city(city)
        log.info(f"Ticketmaster returned {len(tm_events)} events for city={city}")
        events.extend(tm_events)
        if tm_events:
            sources.append("ticketmaster")

    # Eventbrite: fills food, sport, tech that TM misses
    if EB_API_KEY:
        log.info(f"Fetching food/sport/tech from Eventbrite: city={city}")
        eb_events = _fetch_eventbrite_city(city)
        log.info(f"Eventbrite returned {len(eb_events)} events for city={city}")
        existing_ids = {e["id"] for e in events}
        added = [e for e in eb_events if e["id"] not in existing_ids]
        events.extend(added)
        if added:
            sources.append("eventbrite")

    # Count coverage per category
    by_cat: dict[str, int] = {}
    for e in events:
        by_cat[e["category"]] = by_cat.get(e["category"], 0) + 1

    if not events:
        log.warning(f"Both TM and EB empty for city={city} — falling back to full Gemini generation")
        events = _fetch_gemini_city(city)
        log.info(f"Gemini full fallback: city={city} generated={len(events)}")
        sources = ["gemini"]
        by_cat = {}
        for e in events:
            by_cat[e["category"]] = by_cat.get(e["category"], 0) + 1
    else:
        # Top up any category that is thin (< 2 events) with targeted Gemini prompts
        thin = [cat for cat in ["food", "sport", "tech"] if by_cat.get(cat, 0) < 2]
        if thin:
            log.info(f"Thin categories {thin} for city={city} — topping up with per-category Gemini prompts")
            existing_ids = {e["id"] for e in events}
            for cat in thin:
                needed = max(1, 4 - by_cat.get(cat, 0))
                fill = _fetch_gemini_category(city, cat, needed)
                new = [e for e in fill if e["id"] not in existing_ids]
                events.extend(new)
                existing_ids.update(e["id"] for e in new)
                by_cat[cat] = by_cat.get(cat, 0) + len(new)
            if "gemini-fill" not in sources:
                sources.append("gemini-fill")

    source = "+".join(sources) if sources else "none"

    if events:
        log.info(f"Writing {len(events)} events to DB: city={city} source={source} by_category={by_cat}")
        _write_events_to_db(events, city)
        log.info(f"Stored {len(events)} events for city={city} source={source}")
    else:
        log.error(f"No events generated for city={city} — DB not updated")

    newrelic.agent.add_custom_attribute("events_count", len(events))
    newrelic.agent.add_custom_attribute("source", source)
    return {"city": city, "count": len(events), "source": source}
