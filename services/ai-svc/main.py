import os
import json
import time
import logging
import newrelic.agent
import redis as redis_lib
from fastapi import FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel
from typing import Optional
from anthropic import Anthropic, APIError as AnthropicAPIError
from google import genai as google_genai
from circuit_breaker import CircuitBreaker

newrelic.agent.initialize()

logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(name)s %(message)s")
log = logging.getLogger("ai-svc")

app = FastAPI(title="pulse-ai-svc")
app.add_middleware(CORSMiddleware, allow_origins=["*"], allow_methods=["*"], allow_headers=["*"])

anthropic_client = Anthropic(api_key=os.getenv("ANTHROPIC_API_KEY", ""))
gemini_client = google_genai.Client(api_key=os.getenv("GEMINI_API_KEY", ""))

cb = CircuitBreaker(
    failure_threshold=int(os.getenv("CB_FAILURE_THRESHOLD", "5")),
    recovery_timeout=int(os.getenv("CB_RECOVERY_TIMEOUT_SECONDS", "60")),
)

CLAUDE_MODEL = os.getenv("CLAUDE_MODEL", "claude-sonnet-4-20250514")
GEMINI_MODEL = os.getenv("GEMINI_MODEL", "gemini-2.0-flash-lite")
DEFAULT_PROVIDER = os.getenv("AI_PROVIDER", "gemini")
DEMO_CITY = os.getenv("DEMO_CITY", "London")
REC_CACHE_TTL = 300
BUG_AI_SLOW = os.getenv("BUG_AI_SLOW", "false").lower() == "true"

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
    saved_event_ids: list[str]
    available_events: list[dict]
    provider: Optional[str] = None  # "gemini" or "claude"; falls back to AI_PROVIDER env


class RecommendationResponse(BaseModel):
    recommendations: list[dict]
    mode: str  # "ai", "degraded", "fallback"
    ai_response_ms: Optional[int] = None
    provider: Optional[str] = None


@app.get("/health")
def health():
    return {"status": "ok", "service": "ai-svc", "circuit_breaker": cb.state}


@app.get("/status")
def status():
    return {
        "circuit_breaker_state": cb.state,
        "failure_count": cb.failure_count,
        "provider": DEFAULT_PROVIDER,
        "model": GEMINI_MODEL if DEFAULT_PROVIDER == "gemini" else CLAUDE_MODEL,
    }


@app.post("/recommendations", response_model=RecommendationResponse)
@newrelic.agent.function_trace()
def get_recommendations(req: RecommendationRequest):
    start = time.time()
    provider = req.provider or DEFAULT_PROVIDER
    city = req.user_preferences.get("city", DEMO_CITY)
    cache_key = f"rec:{req.user_id}:{city}:{provider}"

    newrelic.agent.add_custom_attribute("user_id", req.user_id)
    newrelic.agent.add_custom_attribute("available_events_count", len(req.available_events))
    newrelic.agent.add_custom_attribute("circuit_breaker_state", cb.state)
    newrelic.agent.add_custom_attribute("ai_provider", provider)

    if redis_client and not BUG_AI_SLOW:
        try:
            cached = redis_client.get(cache_key)
            if cached:
                newrelic.agent.add_custom_attribute("cache_hit", True)
                log.info(f"Cache hit for {cache_key}")
                return RecommendationResponse(
                    recommendations=json.loads(cached),
                    mode="ai",
                    ai_response_ms=0,
                    provider=provider,
                )
        except Exception as e:
            log.warning(f"Redis read error: {e}")
    newrelic.agent.add_custom_attribute("cache_hit", False)

    if cb.state == "OPEN":
        log.warning("Circuit breaker OPEN — using rule-based fallback")
        newrelic.agent.record_custom_event("AIFallback", {
            "user_id": req.user_id,
            "reason": "circuit_breaker_open",
        })
        return RecommendationResponse(
            recommendations=rule_based_fallback(req),
            mode="fallback",
            provider=provider,
        )

    try:
        recs = call_ai(req, provider)
        elapsed_ms = int((time.time() - start) * 1000)
        cb.record_success()

        newrelic.agent.add_custom_attribute("ai_response_ms", elapsed_ms)
        newrelic.agent.add_custom_attribute("ai_mode", "ai")

        if redis_client:
            try:
                redis_client.setex(cache_key, REC_CACHE_TTL, json.dumps(recs))
            except Exception as e:
                log.warning(f"Redis write error: {e}")

        return RecommendationResponse(
            recommendations=recs,
            mode="ai",
            ai_response_ms=elapsed_ms,
            provider=provider,
        )

    except Exception as e:
        log.error(f"{provider} API error: {e}")
        cb.record_failure()

        newrelic.agent.notice_error()
        newrelic.agent.record_custom_event("AIServiceError", {
            "user_id": req.user_id,
            "provider": provider,
            "error_type": type(e).__name__,
            "circuit_breaker_state": cb.state,
        })

        return RecommendationResponse(
            recommendations=rule_based_fallback(req),
            mode="degraded" if cb.state != "OPEN" else "fallback",
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
        return call_claude(req)
    return call_gemini(req)


def _build_prompt(req: RecommendationRequest) -> str:
    prefs = req.user_preferences
    saved_ids = set(req.saved_event_ids)
    events_summary = []
    for e in req.available_events[:20]:
        events_summary.append(
            f"- [{e['id']}] {e['title']} ({e['category']}) on {e['date'][:10]} "
            f"at {e['venue']} — £{e.get('price_gbp', 0) or 0}"
        )
    return f"""You are a personalised event recommendation engine for {DEMO_CITY}.

User preferences:
- Favourite categories: {prefs.get('categories', [])}
- Preferred times: {prefs.get('times', [])}
- Previously saved events: {list(saved_ids)}

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


def call_gemini(req: RecommendationRequest) -> list[dict]:
    response = gemini_client.models.generate_content(
        model=GEMINI_MODEL,
        contents=_build_prompt(req),
    )
    return _parse_recs(response.text, req)


def call_claude(req: RecommendationRequest) -> list[dict]:
    response = anthropic_client.messages.create(
        model=CLAUDE_MODEL,
        max_tokens=256,
        messages=[{"role": "user", "content": _build_prompt(req)}],
    )
    return _parse_recs(response.content[0].text, req)


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
