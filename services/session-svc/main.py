import os
import uuid
import json
import logging
import newrelic.agent
import psycopg2
import psycopg2.pool
import redis
from fastapi import FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel

newrelic.agent.initialize()

logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(name)s %(message)s")
log = logging.getLogger("session-svc")

app = FastAPI(title="pulse-session-svc")
app.add_middleware(CORSMiddleware, allow_origins=["*"], allow_methods=["*"], allow_headers=["*"])

pg_pool = psycopg2.pool.SimpleConnectionPool(
    1, 10,
    host=os.getenv("POSTGRES_HOST", "localhost"),
    port=int(os.getenv("POSTGRES_PORT", "5432")),
    user=os.getenv("POSTGRES_USER", "pulse"),
    password=os.getenv("POSTGRES_PASSWORD", ""),
    dbname=os.getenv("POSTGRES_DB", "pulse"),
)

redis_client = redis.Redis(
    host=os.getenv("REDIS_HOST", "localhost"),
    port=int(os.getenv("REDIS_PORT", "6379")),
    decode_responses=True,
)

SESSION_TTL = 3600  # 1 hour
BUG_MEMORY_LEAK = os.getenv("BUG_MEMORY_LEAK", "false").lower() == "true"
_leak_buffer: list = []  # accumulates when BUG_MEMORY_LEAK is active, never freed


class CreateSessionRequest(BaseModel):
    user_id: str


class SaveEventRequest(BaseModel):
    event_id: str


def session_key(session_id: str) -> str:
    return f"session:{session_id}"


def load_saved_events_from_db(user_id: str) -> list[str]:
    conn = pg_pool.getconn()
    try:
        with conn.cursor() as cur:
            cur.execute(
                "SELECT event_id FROM saved_events WHERE user_id = %s ORDER BY saved_at DESC",
                (user_id,),
            )
            return [row[0] for row in cur.fetchall()]
    finally:
        pg_pool.putconn(conn)


@app.get("/health")
def health():
    return {"status": "ok", "service": "session-svc"}


@app.post("/sessions", status_code=201)
@newrelic.agent.function_trace()
def create_session(req: CreateSessionRequest):
    session_id = str(uuid.uuid4())
    saved_event_ids = load_saved_events_from_db(req.user_id)

    session_data = {
        "session_id": session_id,
        "user_id": req.user_id,
        "saved_event_ids": saved_event_ids,
    }
    redis_client.setex(session_key(session_id), SESSION_TTL, json.dumps(session_data))

    newrelic.agent.add_custom_attribute("user_id", req.user_id)
    newrelic.agent.add_custom_attribute("session_id", session_id)
    newrelic.agent.record_custom_event("SessionCreated", {
        "user_id": req.user_id,
        "session_id": session_id,
        "saved_event_count": len(saved_event_ids),
    })

    if BUG_MEMORY_LEAK:
        _leak_buffer.append({"session": session_data, "events": saved_event_ids * 100})
        log.warning(f"BUG_MEMORY_LEAK active: buffer has {len(_leak_buffer)} entries")
        newrelic.agent.record_custom_event("BugScenarioEnabled", {
            "bug": "BUG_MEMORY_LEAK",
            "service": "session-svc",
            "leaked_entries": len(_leak_buffer),
        })

    log.info(f"Session created: {session_id} for user {req.user_id}")
    return session_data


@app.get("/sessions/{session_id}")
@newrelic.agent.function_trace()
def get_session(session_id: str):
    raw = redis_client.get(session_key(session_id))
    if not raw:
        raise HTTPException(status_code=404, detail="Session not found")

    newrelic.agent.add_custom_attribute("session_id", session_id)

    if BUG_MEMORY_LEAK:
        _leak_buffer.append(json.loads(raw))
        log.warning(f"BUG_MEMORY_LEAK active: buffer has {len(_leak_buffer)} entries")

    return json.loads(raw)


@app.post("/sessions/{session_id}/saved-events", status_code=201)
@newrelic.agent.function_trace()
def save_event(session_id: str, req: SaveEventRequest):
    raw = redis_client.get(session_key(session_id))
    if not raw:
        raise HTTPException(status_code=404, detail="Session not found")

    session = json.loads(raw)
    user_id = session["user_id"]

    conn = pg_pool.getconn()
    try:
        with conn.cursor() as cur:
            cur.execute(
                "INSERT INTO saved_events (user_id, event_id) VALUES (%s, %s) ON CONFLICT DO NOTHING",
                (user_id, req.event_id),
            )
            conn.commit()
    finally:
        pg_pool.putconn(conn)

    if req.event_id not in session["saved_event_ids"]:
        session["saved_event_ids"].append(req.event_id)
    redis_client.setex(session_key(session_id), SESSION_TTL, json.dumps(session))

    newrelic.agent.add_custom_attribute("user_id", user_id)
    newrelic.agent.add_custom_attribute("event_id", req.event_id)
    newrelic.agent.record_custom_event("EventSaved", {
        "user_id": user_id,
        "event_id": req.event_id,
        "session_id": session_id,
    })

    log.info(f"Event {req.event_id} saved for user {user_id}")
    return {"session_id": session_id, "saved_event_ids": session["saved_event_ids"]}


@app.delete("/sessions/{session_id}/saved-events/{event_id}")
@newrelic.agent.function_trace()
def unsave_event(session_id: str, event_id: str):
    raw = redis_client.get(session_key(session_id))
    if not raw:
        raise HTTPException(status_code=404, detail="Session not found")

    session = json.loads(raw)
    user_id = session["user_id"]

    conn = pg_pool.getconn()
    try:
        with conn.cursor() as cur:
            cur.execute(
                "DELETE FROM saved_events WHERE user_id = %s AND event_id = %s",
                (user_id, event_id),
            )
            conn.commit()
    finally:
        pg_pool.putconn(conn)

    session["saved_event_ids"] = [e for e in session["saved_event_ids"] if e != event_id]
    redis_client.setex(session_key(session_id), SESSION_TTL, json.dumps(session))

    newrelic.agent.add_custom_attribute("user_id", user_id)
    newrelic.agent.add_custom_attribute("event_id", event_id)
    newrelic.agent.record_custom_event("EventUnsaved", {
        "user_id": user_id,
        "event_id": event_id,
        "session_id": session_id,
    })

    log.info(f"Event {event_id} unsaved for user {user_id}")
    return {"session_id": session_id, "saved_event_ids": session["saved_event_ids"]}
