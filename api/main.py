from pathlib import Path
import re

from fastapi import FastAPI, HTTPException
from fastapi.responses import FileResponse
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel, Field

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
_agents: dict[str, VoiceAgent] = {}
AGENTS_ROOT = Path(__file__).resolve().parent.parent / "agents"


def get_agent(agent_id: str | None = None) -> SalesAgent | VoiceAgent:
    global _agent
    if agent_id is None and _agent is not None:
        return _agent
    settings = get_settings()
    if agent_id is None:
        config_path = Path(settings.agent_config)
    else:
        if not re.fullmatch(r"[A-Za-z0-9_-]+", agent_id):
            raise HTTPException(status_code=400, detail="Invalid agent id")
        config_path = AGENTS_ROOT / f"{agent_id}.yaml"
    if not config_path.is_absolute():
        config_path = Path(__file__).resolve().parent.parent / config_path
    config = load_agent_config(config_path)
    if agent_id and config.id != agent_id:
        raise HTTPException(status_code=400, detail="Agent configuration id mismatch")
    if config.id not in _agents:
        _agents[config.id] = VoiceAgent(config=config, store=_generic_store)
    return _agents[config.id]


class ChatRequest(BaseModel):
    session_id: str = Field(min_length=1)
    message: str = Field(min_length=1)
    agent_id: str | None = None
    prompt_version: str | None = None
    language: str = "english"


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
    agent_config_version: str | None = None
    current_action: str | None = None
    action_results: dict = Field(default_factory=dict)


@app.get("/", include_in_schema=False)
def frontend() -> FileResponse:
    return FileResponse(WEB_ROOT / "index.html")


@app.get("/health")
def health() -> dict:
    return {"status": "ok"}


@app.get("/agent-config")
def agent_config(agent_id: str | None = None) -> dict:
    agent = get_agent(agent_id)
    if isinstance(agent, VoiceAgent):
        return agent.config.model_dump()
    return {"id": "quickloan", "name": "Priya", "role": "Sales representative"}


@app.post("/chat", response_model=ChatResponse)
def chat(body: ChatRequest) -> ChatResponse:
    try:
        active_agent = get_agent(body.agent_id)
        result = active_agent.chat(
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
