import os
import newrelic.agent
from fastapi import FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel
from typing import Optional
from google import genai
from google.genai import types as genai_types
from anthropic import Anthropic
from openai import OpenAI

app = FastAPI()
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_methods=["*"],
    allow_headers=["*"],
)

gemini_client    = genai.Client(api_key=os.getenv("GEMINI_API_KEY", ""))
anthropic_client = Anthropic(api_key=os.getenv("ANTHROPIC_API_KEY", ""))
_openai_key      = os.getenv("OPENAI_API_KEY", "")
openai_client    = OpenAI(api_key=_openai_key) if _openai_key else None

DEFAULT_MODEL = os.getenv("GEMINI_MODEL", "gemini-3.1-flash-lite-preview")

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


class FeedbackRequest(BaseModel):
    trace_id: str
    rating: str  # "good" or "bad"
    message: Optional[str] = None


@app.get("/health")
def health():
    return {"status": "ok", "service": "test-svc"}


@app.post("/generate")
async def generate(req: PromptRequest):
    response = gemini_client.models.generate_content(model=DEFAULT_MODEL, contents=req.prompt)
    return {"result": response.text}


@app.post("/chat")
async def chat(req: ChatRequest):
    provider = _provider(req.model)

    if provider == "gemini":
        response = gemini_client.models.generate_content(
            model=req.model,
            contents=req.message,
            config=genai_types.GenerateContentConfig(system_instruction=SYSTEM_PROMPT),
        )
        reply = response.text

    elif provider == "claude":
        response = anthropic_client.messages.create(
            model=req.model,
            max_tokens=1024,
            system=SYSTEM_PROMPT,
            messages=[{"role": "user", "content": req.message}],
        )
        reply = response.content[0].text

    else:
        if not openai_client:
            raise HTTPException(status_code=503, detail="OpenAI key not configured")
        response = openai_client.chat.completions.create(
            model=req.model,
            messages=[
                {"role": "system", "content": SYSTEM_PROMPT},
                {"role": "user", "content": req.message},
            ],
        )
        reply = response.choices[0].message.content

    trace_id = newrelic.agent.current_trace_id()
    return {"reply": reply, "model": req.model, "provider": provider, "trace_id": trace_id}


@app.post("/chat/feedback", status_code=204)
async def chat_feedback(req: FeedbackRequest):
    newrelic.agent.record_llm_feedback_event(
        trace_id=req.trace_id,
        rating=req.rating,
        message=req.message,
        metadata={"source": "pulse-chat"},
    )
    return None
