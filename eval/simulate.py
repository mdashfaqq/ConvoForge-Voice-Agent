from __future__ import annotations

import json
from pathlib import Path
from typing import Any

from agent.chat import SalesAgent
from agent.llm import LLMClient, parse_json_object
from agent.session import SessionStore
from config import get_settings

PERSONAS_PATH = Path(__file__).with_name("personas.json")
MAX_TURNS = 12

SIMULATOR_SYSTEM = """
You are role-playing a loan lead on a phone call. Stay in character.
Speak like a real person, not a form. One to three short sentences.
Do not volunteer hidden facts until asked, unless your goal says otherwise.
Never break character. Never mention that you are an AI or a persona.
If language_style is Hinglish, mix Hindi and English naturally
(example: "Haan ji, but interest rate kitna hai?").
Return JSON: {{"message": "your next spoken line", "hang_up": false}}
Set hang_up true only when you would actually end the call.
"""


def load_personas(path: Path | None = None) -> list[dict[str, Any]]:
    target = path or PERSONAS_PATH
    with target.open(encoding="utf-8") as handle:
        data = json.load(handle)
    if not isinstance(data, list):
        raise ValueError("personas.json must be a list")
    return data


def simulate_conversation(
    persona: dict[str, Any],
    agent: SalesAgent,
    llm: LLMClient,
    *,
    max_turns: int = MAX_TURNS,
) -> dict[str, Any]:
    store = agent.store
    session_id = f"sim-{persona['id']}"
    store.reset(session_id)
    customer_line = _opener(persona)
    transcript: list[dict[str, str]] = []
    last_agent = ""

    for _ in range(max_turns):
        result = agent.chat(session_id, customer_line)
        transcript.append({"role": "customer", "content": customer_line})
        transcript.append({"role": "agent", "content": result["reply"]})
        last_agent = result["reply"]
        if result["state"] == "END":
            break
        nxt = _customer_turn(llm, persona, transcript, last_agent)
        customer_line = nxt["message"]
        if nxt.get("hang_up"):
            result = agent.chat(session_id, customer_line)
            transcript.append({"role": "customer", "content": customer_line})
            transcript.append({"role": "agent", "content": result["reply"]})
            break

    session = store.get(session_id)
    return {
        "persona_id": persona["id"],
        "language": persona.get("language") or persona.get("language_style") or "English",
        "intent": persona.get("intent"),
        "transcript": transcript,
        "collected": session.fields.model_dump() if session else {},
        "ended_reason": session.ended_reason if session else None,
        "final_state": session.state.value if session else None,
    }


def _opener(persona: dict[str, Any]) -> str:
    if persona.get("language_style") == "Hinglish" or persona.get("language") == "Hinglish":
        return "Hello? Haan, kaun bol raha hai?"
    return "Hello?"


def _customer_turn(
    llm: LLMClient,
    persona: dict[str, Any],
    transcript: list[dict[str, str]],
    last_agent: str,
) -> dict[str, Any]:
    settings = get_settings()
    history = "\n".join(f"{turn['role']}: {turn['content']}" for turn in transcript[-8:])
    raw = llm.complete(
        [
            {"role": "system", "content": SIMULATOR_SYSTEM.strip()},
            {
                "role": "user",
                "content": (
                    f"Persona JSON:\n{json.dumps(persona, ensure_ascii=False)}\n\n"
                    f"Recent transcript:\n{history}\n\n"
                    f"Agent just said: {last_agent}\n"
                    "Reply now as the customer."
                ),
            },
        ],
        temperature=settings.simulator_temperature,
        json_mode=True,
    )
    data = parse_json_object(raw)
    message = str(data.get("message") or "").strip() or "Sorry, can you repeat that?"
    return {"message": message, "hang_up": bool(data.get("hang_up"))}


def run_simulations(
    personas: list[dict[str, Any]],
    prompt_version: str,
    agent_llm: LLMClient,
    customer_llm: LLMClient | None = None,
) -> list[dict[str, Any]]:
    customer_llm = customer_llm or agent_llm
    agent = SalesAgent(
        store=SessionStore(),
        llm=agent_llm,
        prompt_version=prompt_version,
    )
    return [simulate_conversation(persona, agent, customer_llm) for persona in personas]
