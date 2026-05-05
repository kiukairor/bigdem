import os
from fastapi import FastAPI
from pydantic import BaseModel
from google import genai

app = FastAPI()
client = genai.Client(api_key=os.getenv("GEMINI_API_KEY", ""))
MODEL = os.getenv("GEMINI_MODEL", "gemini-2.0-flash-lite")


class PromptRequest(BaseModel):
    prompt: str


@app.get("/health")
def health():
    return {"status": "ok", "service": "test-svc"}


@app.post("/generate")
async def generate(req: PromptRequest):
    response = client.models.generate_content(model=MODEL, contents=req.prompt)
    return {"result": response.text}
