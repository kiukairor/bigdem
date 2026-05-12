import newrelic.agent
newrelic.agent.initialize()

import os
import time
import logging
import requests as http_requests
from fastapi import FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel
from typing import Optional, Union
from anthropic import Anthropic
from google import genai
from google.genai import types as genai_types
from openai import OpenAI

logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(name)s %(message)s")
log = logging.getLogger("pulse-ai-dontask")

app = FastAPI()
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_methods=["*"],
    allow_headers=["*"],
)

anthropic_client = Anthropic(api_key=os.getenv("ANTHROPIC_API_KEY", ""))
gemini_client    = genai.Client(api_key=os.getenv("GEMINI_API_KEY", ""))
_openai_key      = os.getenv("OPENAI_API_KEY", "")
openai_client    = OpenAI(api_key=_openai_key) if _openai_key else None

DEFAULT_MODEL  = os.getenv("GEMINI_MODEL", "gemini-3.1-flash-lite-preview")
EVENT_SVC_URL  = os.getenv("EVENT_SVC_URL", "http://event-svc:8080")

SYSTEM_PROMPT = (
    "You are an AI assistant for PULSE, an urban events discovery app. "
    "You help users find and explore events happening in cities worldwide — "
    "concerts, exhibitions, food & drink events, sports, tech meetups, nightlife, arts, and more. "
    "Only answer questions related to events, venues, activities, entertainment, culture, "
    "city exploration, and recommendations. "
    "If asked about anything unrelated to events or city life, politely decline and "
    "redirect the conversation back to helping the user discover events."
)


def _provider(model: str) -> str:
    if model.startswith("gemini"):
        return "gemini"
    if model.startswith("claude"):
        return "claude"
    return "openai"


class PromptRequest(BaseModel):
    prompt: str


class ChatRequest(BaseModel):
    message: str
    model: str = DEFAULT_MODEL
    city: Optional[str] = None


class FeedbackRequest(BaseModel):
    trace_id: str
    rating: Union[str, int]  # numeric 0-10 or legacy "good"/"bad"
    message: Optional[str] = None


def _record_llm_event(vendor: str, model: str, prompt: str, reply: str,
                      input_tokens: int, output_tokens: int,
                      duration_ms: int = 0, finish_reason: str = "") -> None:
    import uuid
    request_id = str(uuid.uuid4())
    span_id    = newrelic.agent.current_span_id() if hasattr(newrelic.agent, "current_span_id") else ""
    trace_id   = newrelic.agent.current_trace_id()
    tx         = newrelic.agent.current_transaction()
    tx_id      = tx.guid if tx else ""
    base = {
        "id": request_id, "vendor": vendor, "ingest_source": "Python",
        "request.model": model, "response.model": model,
        "request_id": request_id, "trace_id": trace_id,
        "span_id": span_id, "transaction_id": tx_id,
        "response.usage.input_tokens": input_tokens,
        "response.usage.output_tokens": output_tokens,
        "response.usage.total_tokens": input_tokens + output_tokens,
        # OpenAI-convention aliases — required by NR curated AI Monitoring queries
        "response.usage.prompt_tokens": input_tokens,
        "response.usage.completion_tokens": output_tokens,
        "response.number_of_messages": 2,
        "duration": duration_ms,
    }
    if finish_reason:
        base["response.choices.finish_reason"] = finish_reason
    newrelic.agent.record_custom_event("LlmChatCompletionSummary", base)
    newrelic.agent.record_custom_event("LlmChatCompletionMessage", {
        **base, "sequence": 0, "role": "user", "is_response": False,
        "content": prompt[:4095], "completion_id": request_id,
        "token_count": input_tokens,
    })
    newrelic.agent.record_custom_event("LlmChatCompletionMessage", {
        **base, "sequence": 1, "role": "assistant", "is_response": True,
        "content": reply[:4095], "completion_id": request_id,
        "token_count": output_tokens,
    })


def _fetch_events_context(city: str) -> str:
    try:
        resp = http_requests.get(
            f"{EVENT_SVC_URL}/events",
            params={"city": city},
            timeout=5,
        )
        resp.raise_for_status()
        events = resp.json()
        if not events:
            return ""
        lines = [
            f"- {e['title']} ({e['category']}) on {e['date'][:10]} at {e['venue']}"
            for e in events[:15]
        ]
        log.info(f"Fetched {len(events)} events from event-svc for chat context: city={city}")
        return f"\n\nReal upcoming events in {city}:\n" + "\n".join(lines)
    except Exception as e:
        log.warning(f"Could not fetch events from event-svc for chat: city={city} error={e}")
        return ""


@app.get("/health")
def health():
    return {"status": "ok", "service": "pulse-ai-dontask"}


@app.post("/generate")
async def generate(req: PromptRequest):
    response = gemini_client.models.generate_content(model=DEFAULT_MODEL, contents=req.prompt)
    return {"result": response.text}


@app.post("/chat")
async def chat(req: ChatRequest):
    provider = _provider(req.model)
    log.info(f"Chat request: model={req.model} provider={provider} city={req.city} msg_len={len(req.message)}")

    system = SYSTEM_PROMPT
    if req.city:
        system += _fetch_events_context(req.city)

    input_tokens = output_tokens = 0
    finish_reason = ""

    if os.getenv("BUG_AI_SLOW", "false").lower() == "true":
        log.warning("BUG_AI_SLOW active — injecting 8s delay before chat call")
        newrelic.agent.add_custom_attribute("bug_ai_slow", True)
        time.sleep(8)

    try:
        if provider == "gemini":
            t0 = time.time()
            response = gemini_client.models.generate_content(
                model=req.model,
                contents=req.message,
                config=genai_types.GenerateContentConfig(system_instruction=system),
            )
            duration_ms = int((time.time() - t0) * 1000)
            reply = response.text
            if getattr(response, "usage_metadata", None):
                input_tokens  = response.usage_metadata.prompt_token_count or 0
                output_tokens = response.usage_metadata.candidates_token_count or 0
            if input_tokens == 0 and output_tokens == 0:
                input_tokens  = max(1, len(system + req.message) // 4)
                output_tokens = max(1, len(reply) // 4)
            if getattr(response, "candidates", None) and response.candidates:
                finish_reason = str(getattr(response.candidates[0], "finish_reason", "") or "")
            _record_llm_event("gemini", req.model, req.message, reply,
                              input_tokens, output_tokens, duration_ms, finish_reason)

        elif provider == "claude":
            t0 = time.time()
            response = anthropic_client.messages.create(
                model=req.model,
                max_tokens=1024,
                system=system,
                messages=[{"role": "user", "content": req.message}],
            )
            duration_ms = int((time.time() - t0) * 1000)
            reply = response.content[0].text
            if getattr(response, "usage", None):
                input_tokens  = response.usage.input_tokens or 0
                output_tokens = response.usage.output_tokens or 0
            finish_reason = response.stop_reason or ""
            _record_llm_event("anthropic", req.model, req.message, reply,
                              input_tokens, output_tokens, duration_ms, finish_reason)

        else:
            if not openai_client:
                raise HTTPException(status_code=503, detail="OpenAI key not configured")
            t0 = time.time()
            response = openai_client.chat.completions.create(
                model=req.model,
                messages=[
                    {"role": "system", "content": system},
                    {"role": "user", "content": req.message},
                ],
            )
            duration_ms = int((time.time() - t0) * 1000)
            reply = response.choices[0].message.content
            if getattr(response, "usage", None):
                input_tokens  = response.usage.prompt_tokens or 0
                output_tokens = response.usage.completion_tokens or 0
            finish_reason = response.choices[0].finish_reason or "" if response.choices else ""
            _record_llm_event("openai", req.model, req.message, reply,
                              input_tokens, output_tokens, duration_ms, finish_reason)

    except HTTPException:
        raise
    except Exception as e:
        log.error(f"Chat LLM call failed: model={req.model} provider={provider} error={e}")
        raise HTTPException(status_code=502, detail=str(e))

    trace_id = newrelic.agent.current_trace_id()
    total_tokens = input_tokens + output_tokens
    newrelic.agent.add_custom_attribute("llm.model", req.model)
    newrelic.agent.add_custom_attribute("llm.provider", provider)
    newrelic.agent.add_custom_attribute("llm.input_tokens", input_tokens)
    newrelic.agent.add_custom_attribute("llm.output_tokens", output_tokens)
    newrelic.agent.add_custom_attribute("llm.total_tokens", total_tokens)
    newrelic.agent.add_custom_attribute("llm.duration_ms", duration_ms)
    newrelic.agent.add_custom_attribute("llm.finish_reason", finish_reason)
    newrelic.agent.record_custom_metric("Custom/LLM/InputTokens", input_tokens)
    newrelic.agent.record_custom_metric("Custom/LLM/OutputTokens", output_tokens)
    newrelic.agent.record_custom_metric("Custom/LLM/DurationMs", duration_ms)
    log.info(
        f"Chat response: model={req.model} provider={provider} trace_id={trace_id} "
        f"tokens={input_tokens}+{output_tokens}={total_tokens} duration_ms={duration_ms} finish={finish_reason}"
    )
    return {"reply": reply, "model": req.model, "provider": provider, "trace_id": trace_id}


@app.post("/chat/feedback", status_code=204)
async def chat_feedback(req: FeedbackRequest):
    # Numeric 0-10: pass directly. String "good"/"bad": normalize to NR expected form.
    if isinstance(req.rating, int):
        rating = req.rating
    else:
        _RATING_MAP = {"good": "Good", "bad": "Bad", "positive": "Good", "negative": "Bad"}
        rating = _RATING_MAP.get(req.rating.lower(), req.rating.capitalize())
    log.info(f"Chat feedback: raw={req.rating} normalized={rating} trace_id={req.trace_id}")
    try:
        newrelic.agent.record_llm_feedback_event(
            trace_id=req.trace_id,
            rating=rating,
            message=req.message,
            metadata={"source": "pulse-chat"},
        )
    except Exception as e:
        log.warning(f"NR feedback recording failed (non-fatal): {e}")
    return None
