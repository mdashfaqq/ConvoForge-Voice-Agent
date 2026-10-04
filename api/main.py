from pathlib import Path

from fastapi import FastAPI, HTTPException, Request
from fastapi.responses import FileResponse, Response
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel, Field
from typing import Literal

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
    language: Literal["english", "hinglish", "hindi"] = "english"


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


def _speech_gather(response, action: str = "/voice/gather") -> None:
    gather = response.gather(
        input="speech",
        action=action,
        method="POST",
        language="en-IN",
        speech_timeout="auto",
        timeout=5,
    )
    gather.say(
        "Please tell me how I can help you with your loan requirement.",
        language="en-IN",
    )


@app.post("/voice/incoming", include_in_schema=False)
def voice_incoming() -> Response:
    from twilio.twiml.voice_response import VoiceResponse

    response = VoiceResponse()
    response.say(
        "Hello, this is Priya from QuickLoan. I would like to understand your loan requirement.",
        language="en-IN",
    )
    _speech_gather(response)
    return Response(content=str(response), media_type="application/xml")


@app.post("/voice/gather", include_in_schema=False)
async def voice_gather(request: Request) -> Response:
    from twilio.twiml.voice_response import VoiceResponse

    form = await request.form()
    session_id = str(form.get("CallSid") or "voice-unknown")
    speech = str(form.get("SpeechResult") or "").strip()
    response = VoiceResponse()

    if not speech:
        response.say("I did not catch that. Please say that again.", language="en-IN")
        _speech_gather(response)
        return Response(content=str(response), media_type="application/xml")

    try:
        result = get_agent().chat(session_id, speech, language="english")
    except RuntimeError:
        response.say(
            "I am sorry, the service is temporarily unavailable. Please try again later.",
            language="en-IN",
        )
        response.hangup()
        return Response(content=str(response), media_type="application/xml")

    response.say(result["reply"], language="en-IN")
    if result["state"] == "END":
        response.hangup()
    else:
        _speech_gather(response)
    return Response(content=str(response), media_type="application/xml")


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
