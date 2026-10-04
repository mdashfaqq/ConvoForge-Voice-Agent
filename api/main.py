from pathlib import Path

from fastapi import FastAPI, HTTPException
from fastapi.responses import FileResponse
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel, Field
from typing import Literal

from agent.agent_config import load_agent_config
from agent.chat import SalesAgent
from agent.generic import GenericSessionStore, VoiceAgent
from agent.session import SessionStore
from config import get_settings

app = FastAPI(title="ConvoForge", version="1.0.0")
WEB_ROOT = Path(__file__).resolve().parent.parent / "web"
app.mount("/assets", StaticFiles(directory=WEB_ROOT), name="assets")
store = SessionStore()
_agent: SalesAgent | VoiceAgent | None = None
_generic_store = GenericSessionStore()


def get_agent() -> SalesAgent | VoiceAgent:
    global _agent
    if _agent is None:
        settings = get_settings()
        config_path = Path(settings.agent_config)
        if not config_path.is_absolute():
            config_path = Path(__file__).resolve().parent.parent / config_path
        _agent = VoiceAgent(
            config=load_agent_config(config_path),
            store=_generic_store,
        )
    return _agent


class ChatRequest(BaseModel):
    session_id: str = Field(min_length=1)
    message: str = Field(min_length=1)
    prompt_version: str | None = None
    language: Literal["english", "hinglish", "hindi"] = "english"


class ChatResponse(BaseModel):
    session_id: str
    reply: str
    state: str
    collected: dict
    missing: list[str]
    ended_reason: str | None = None
    qualification_complete: bool = False
    conversation_complete: bool = False
    conversation_intent: str | None = None
    last_user_intent: str | None = None
    clarification_needed: str | None = None
    declined_fields: list[str] = Field(default_factory=list)
    agent_id: str | None = None
    agent_name: str | None = None
    agent_role: str | None = None
    goal: dict = Field(default_factory=dict)
    confidence: float = 0.0


@app.get("/", include_in_schema=False)
def frontend() -> FileResponse:
    return FileResponse(WEB_ROOT / "index.html")


@app.get("/health")
def health() -> dict:
    return {"status": "ok"}


@app.get("/agent-config")
def agent_config() -> dict:
    agent = get_agent()
    if isinstance(agent, VoiceAgent):
        return agent.config.model_dump()
    return {"id": "quickloan", "name": "Priya", "role": "Sales representative"}


@app.post("/chat", response_model=ChatResponse)
def chat(body: ChatRequest) -> ChatResponse:
    try:
        result = get_agent().chat(
            body.session_id,
            body.message,
            body.prompt_version,
            body.language,
        )
    except FileNotFoundError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    except RuntimeError as exc:
        raise HTTPException(status_code=503, detail=str(exc)) from exc
    return ChatResponse(**result)
