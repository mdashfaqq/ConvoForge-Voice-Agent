from __future__ import annotations

import json
import logging
from dataclasses import dataclass, field
from threading import Lock
from typing import Any

from agent.agent_config import AgentConfig
from agent.llm import LLMClient, build_llm_client, parse_json_object
from config import get_settings

logger = logging.getLogger(__name__)


@dataclass
class GenericSession:
    session_id: str
    agent_id: str
    agent_config_version: str
    goal: str
    fields: dict[str, Any] = field(default_factory=dict)
    history: list[dict[str, str]] = field(default_factory=list)
    current_intent: str | None = None
    last_intent: str | None = None
    language: str = "english"
    confidence: float = 0.0
    current_action: str | None = None
    action_results: dict[str, Any] = field(default_factory=dict)
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
            if (
                session is None
                or session.agent_id != config.id
                or session.agent_config_version != config.version
            ):
                session = GenericSession(
                    session_id,
                    config.id,
                    config.version,
                    config.goal.type,
                )
                self._sessions[session_id] = session
            return session


class ConvoForgeAgent:
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
        self.debug_prompts = get_settings().debug_prompts
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
            messages = self._messages(session)
            if self.debug_prompts:
                logger.debug("ConvoForge system prompt for %s: %s", self.config.id, messages[0]["content"])
            raw = self.llm.complete(
                messages,
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
        extracted = data.get("extracted") or data.get("fields") or {}
        if isinstance(extracted, dict):
            for field_id, value in extracted.items():
                if value not in (None, "") and any(
                    configured.id == field_id for configured in self.config.fields
                ):
                    session.fields[field_id] = value
        if bool(data.get("end")) or session.current_intent in {"goodbye", "cancellation"}:
            session.ended = True
        session.current_action = str(data.get("action") or "") or None
        if isinstance(data.get("action_result"), dict) and session.current_action:
            session.action_results[session.current_action] = data["action_result"]
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
                "guardrails": self.config.guardrails,
                "languages": [item.model_dump() for item in self.config.languages],
                "voice": self.config.voice,
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
                "extracted": "object containing only configured field ids",
                "fields": "accepted alias for extracted",
                "confidence": "number between 0 and 1",
                "action": "one configured action or null; do not execute it automatically",
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
            "agent_config_version": session.agent_config_version,
            "current_action": session.current_action,
            "action_results": session.action_results,
        }


VoiceAgent = ConvoForgeAgent
