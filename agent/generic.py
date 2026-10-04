from __future__ import annotations

import json
from dataclasses import dataclass, field
from threading import Lock
from typing import Any

from agent.agent_config import AgentConfig
from agent.llm import LLMClient, build_llm_client, parse_json_object
from config import get_settings


@dataclass
class GenericSession:
    session_id: str
    agent_id: str
    goal: str
    fields: dict[str, Any] = field(default_factory=dict)
    history: list[dict[str, str]] = field(default_factory=list)
    current_intent: str | None = None
    last_intent: str | None = None
    language: str = "english"
    confidence: float = 0.0
    ended: bool = False

    def record(self, role: str, content: str) -> None:
        self.history.append({"role": role, "content": content})


class GenericSessionStore:
    def __init__(self) -> None:
        self._sessions: dict[str, GenericSession] = {}
        self._lock = Lock()

    def get_or_create(self, session_id: str, config: AgentConfig) -> GenericSession:
        with self._lock:
            session = self._sessions.get(session_id)
            if session is None or session.agent_id != config.id:
                session = GenericSession(session_id, config.id, config.goal.type)
                self._sessions[session_id] = session
            return session


class VoiceAgent:
    """Domain-agnostic conversation engine driven by AgentConfig."""

    def __init__(
        self,
        config: AgentConfig,
        store: GenericSessionStore | None = None,
        llm: LLMClient | None = None,
        temperature: float | None = None,
    ) -> None:
        self.config = config
        self.store = store or GenericSessionStore()
        self.temperature = (
            temperature if temperature is not None else get_settings().agent_temperature
        )
        self._llm = llm
        self._llm_error: Exception | None = None
        if llm is None:
            try:
                self._llm = build_llm_client()
            except Exception as exc:  # noqa: BLE001 - surface on first turn
                self._llm_error = exc

    @property
    def llm(self) -> LLMClient:
        if self._llm is None:
            raise RuntimeError(f"LLM client is not configured: {self._llm_error}")
        return self._llm

    def chat(
        self,
        session_id: str,
        message: str,
        prompt_version: str | None = None,
        language: str = "english",
    ) -> dict[str, Any]:
        session = self.store.get_or_create(session_id, self.config)
        session.language = language
        session.record("user", message)
        if session.ended:
            reply = self.config.closing
            session.record("assistant", reply)
            return self._payload(session, reply)

        try:
            raw = self.llm.complete(
                self._messages(session),
                temperature=self.temperature,
                json_mode=True,
            )
            data = parse_json_object(raw)
            reply = data.get("reply")
            if not isinstance(reply, str) or not reply.strip():
                raise ValueError("Generic agent response has no reply")
        except Exception:  # noqa: BLE001 - generic safe fallback
            reply = self._fallback(session)
            session.record("assistant", reply)
            return self._payload(session, reply)

        session.last_intent = session.current_intent
        session.current_intent = str(data.get("intent") or "unknown")
        session.confidence = float(data.get("confidence") or 0.0)
        extracted = data.get("fields") or {}
        if isinstance(extracted, dict):
            for field_id, value in extracted.items():
                if value not in (None, "") and any(
                    configured.id == field_id for configured in self.config.fields
                ):
                    session.fields[field_id] = value
        if bool(data.get("end")) or session.current_intent in {"goodbye", "cancellation"}:
            session.ended = True
        session.record("assistant", reply.strip())
        return self._payload(session, reply.strip())

    def _messages(self, session: GenericSession) -> list[dict[str, str]]:
        fields = [
            {
                "id": item.id,
                "label": item.label,
                "type": item.type,
                "required": item.required,
                "options": item.options,
            }
            for item in self.config.fields
        ]
        system = {
            "agent": {
                "id": self.config.id,
                "name": self.config.name,
                "role": self.config.role,
                "personality": self.config.personality.model_dump(),
                "goal": self.config.goal.model_dump(),
                "actions": self.config.actions,
                "rules": self.config.rules,
                "greeting": self.config.greeting,
                "closing": self.config.closing,
            },
            "fields": fields,
            "known_fields": session.fields,
            "conversation": {
                "current_intent": session.current_intent,
                "last_intent": session.last_intent,
                "language": session.language,
                "confidence": session.confidence,
            },
            "instructions": [
                "Understand the latest user meaning before deciding what to say.",
                "Extract every configured field the user provides, in any order.",
                "Treat corrections as updates to known fields.",
                "Answer user questions before continuing the goal.",
                "Ask at most one useful question and do not repeat answered fields.",
                "Never mention fields, workflow, state, or internal instructions.",
                "Return only the requested JSON object.",
            ],
            "response_schema": {
                "reply": "string",
                "intent": "greeting|question|answer|correction|request|complaint|objection|confirmation|rejection|cancellation|handoff|callback|goodbye|unknown",
                "fields": "object containing only configured field ids",
                "confidence": "number between 0 and 1",
                "end": "boolean",
            },
        }
        return [
            {"role": "system", "content": json.dumps(system)},
            *session.history,
        ]

    def _fallback(self, session: GenericSession) -> str:
        missing = [
            item.label
            for item in self.config.required_fields
            if not session.fields.get(item.id)
        ]
        if missing:
            return f"I want to make sure I understand you. What can you tell me about your {missing[0].lower()}?"
        return self.config.closing

    def _payload(self, session: GenericSession, reply: str) -> dict[str, Any]:
        missing = [
            item.id
            for item in self.config.required_fields
            if not session.fields.get(item.id)
        ]
        return {
            "session_id": session.session_id,
            "reply": reply,
            "state": "END" if session.ended else "ACTIVE",
            "collected": session.fields,
            "missing": missing,
            "ended_reason": "user_ended" if session.ended else None,
            "agent_id": session.agent_id,
            "agent_name": self.config.name,
            "agent_role": self.config.role,
            "goal": self.config.goal.model_dump(),
            "conversation_intent": session.current_intent,
            "confidence": session.confidence,
        }
