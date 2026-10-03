from pathlib import Path

from fastapi import FastAPI, HTTPException
from fastapi.responses import FileResponse
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel, Field

from agent.chat import SalesAgent
from agent.session import SessionStore
from config import get_settings

app = FastAPI(title="SalesVoice Eval", version="1.0.0")
WEB_ROOT = Path(__file__).resolve().parent.parent / "web"
app.mount("/assets", StaticFiles(directory=WEB_ROOT), name="assets")
store = SessionStore()
_agent: SalesAgent | None = None


def get_agent() -> SalesAgent:
    global _agent
    if _agent is None:
        settings = get_settings()
        _agent = SalesAgent(store=store, prompt_version=settings.prompt_version)
    return _agent


class ChatRequest(BaseModel):
    session_id: str = Field(min_length=1)
    message: str = Field(min_length=1)
    prompt_version: str | None = None


class ChatResponse(BaseModel):
    session_id: str
    reply: str
    state: str
    collected: dict
    missing: list[str]
    ended_reason: str | None = None


@app.get("/", include_in_schema=False)
def frontend() -> FileResponse:
    return FileResponse(WEB_ROOT / "index.html")


@app.get("/health")
def health() -> dict:
    return {"status": "ok"}


@app.post("/chat", response_model=ChatResponse)
def chat(body: ChatRequest) -> ChatResponse:
    try:
        result = get_agent().chat(body.session_id, body.message, body.prompt_version)
    except FileNotFoundError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    except RuntimeError as exc:
        raise HTTPException(status_code=503, detail=str(exc)) from exc
    return ChatResponse(**result)
