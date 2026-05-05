import os
from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel
from google import genai

app = FastAPI()
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_methods=["*"],
    allow_headers=["*"],
)

client = genai.Client(api_key=os.getenv("GEMINI_API_KEY", ""))
MODEL = os.getenv("GEMINI_MODEL", "gemini-3.1-flash-lite-preview")


class PromptRequest(BaseModel):
    prompt: str


class ChatRequest(BaseModel):
    message: str


@app.get("/health")
def health():
    return {"status": "ok", "service": "test-svc"}


@app.post("/generate")
async def generate(req: PromptRequest):
    response = client.models.generate_content(model=MODEL, contents=req.prompt)
    return {"result": response.text}


@app.post("/chat")
async def chat(req: ChatRequest):
    response = client.models.generate_content(model=MODEL, contents=req.message)
    return {"reply": response.text, "model": MODEL}
