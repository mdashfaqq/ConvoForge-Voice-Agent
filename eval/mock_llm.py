"""Deterministic stand-in LLMs so the harness can run without API keys."""

from __future__ import annotations

import json
import re
from typing import Any

from agent.llm import parse_json_object


class MockLLM:
    def __init__(self, prompt_version: str = "v1") -> None:
        self.prompt_version = prompt_version

    def complete(self, messages: list[dict[str, str]], *, temperature: float, json_mode: bool = False) -> str:
        blob = "\n".join(m["content"] for m in messages)
        if "Score this conversation" in blob or "strict evaluation judge" in blob:
            return _judge(blob)
        if "Persona JSON" in blob:
            return _customer(blob)
        return _agent(blob, self.prompt_version)


def _agent(blob: str, version: str) -> str:
    user_turns = re.findall(r"(?:^|\n)(?:user|customer): (.+)", blob, flags=re.I)
    last = user_turns[-1] if user_turns else ""
    extracted = {
        "name": _find(r"(?:name is|I am|main|naam)\s+([A-Z][a-zA-Z]+(?:\s+[A-Z][a-zA-Z]+)?)", last)
        or _find(r"([A-Z][a-z]+ [A-Z][a-z]+)", last),
        "city": _city(last),
        "monthly_income": _find(r"(\d{4,9})", last) if re.search(r"income|salary|kama|lakh", last, re.I) else None,
        "loan_amount": _find(r"(\d{4,9})", last) if re.search(r"loan|amount|chahiye|need", last, re.I) else None,
        "employment_type": _employment(last),
    }
    busy = bool(re.search(r"busy|callback|baad mein|driving|meeting", last, re.I))
    objection = bool(re.search(r"interest|rate|emi|fee|kitna", last, re.I))
    not_interested = bool(re.search(r"not interested|nahi chahiye|already closed|no loan", last, re.I))

    if busy:
        reply = "Of course, I will arrange a callback at a better time. Thank you for speaking with QuickLoan."
    elif not_interested:
        reply = "Thank you for letting me know. I will not keep you on this call."
    elif objection:
        if version == "v2":
            reply = (
                "I hear the rate matters, and I cannot quote one because it depends on your profile. "
                "I can set a specialist callback — what city are you in?"
            )
        else:
            reply = "I cannot quote a rate on this call. Could I take your city while we are talking?"
    else:
        collected = _collected_from_prompt(blob)
        for key, value in extracted.items():
            if value:
                collected[key] = value
        remaining = [
            key
            for key in ("name", "city", "monthly_income", "loan_amount", "employment_type")
            if not collected.get(key)
        ]
        if "Current state: GREET" in blob and not any(extracted.values()):
            reply = "Hi, this is Priya from QuickLoan. May I have your name to get started?"
        elif remaining:
            label = remaining[0].replace("_", " ")
            reply = f"Thanks. Could you share your {label} so I can continue?"
        else:
            reply = "Thanks, I have your details. A specialist will follow up without promising approval."

    return json.dumps(
        {
            "reply": reply,
            "extracted": extracted,
            "customer_busy": busy,
            "objection": objection and not busy,
            "not_interested": not_interested,
            "conversation_end": busy or not_interested,
        }
    )


def _customer(blob: str) -> str:
    start = blob.find("Persona JSON:")
    chunk = blob[start:].split("Recent transcript", 1)[0]
    persona = parse_json_object(chunk[chunk.find("{") :])
    facts = persona["hidden_facts"]
    intent = persona.get("intent")
    hinglish = persona.get("language") == "Hinglish"
    agent_line = blob.split("Agent just said:")[-1].lower()

    hang_up = False
    if intent == "busy":
        message = "Abhi busy hoon, baad mein call karo." if hinglish else "I am busy, please call later."
        hang_up = True
    elif intent == "not-interested":
        message = "Mujhe loan nahi chahiye." if hinglish else "I am not interested in a loan."
        hang_up = True
    elif "interest" in agent_line or "rate" in agent_line or intent == "price-sensitive" and "city" not in agent_line:
        if intent == "price-sensitive" and "rate" not in agent_line and "specialist" not in agent_line:
            message = "Haan ji, but interest rate kitna hai?" if hinglish else "What is the interest rate?"
        else:
            message = _answer_next(agent_line, facts, hinglish)
    else:
        message = _answer_next(agent_line, facts, hinglish)
        if intent == "confused" and "loan" in agent_line and "name" in agent_line:
            message = "Yeh loan hai ya credit card?" if hinglish else "Is this a loan or a credit card?"
    return json.dumps({"message": message, "hang_up": hang_up})


def _answer_next(agent_line: str, facts: dict[str, Any], hinglish: bool) -> str:
    if "name" in agent_line:
        return f"Haan, mera naam {facts['name']} hai." if hinglish else f"My name is {facts['name']}."
    if "city" in agent_line:
        return f"Main {facts['city']} se hoon." if hinglish else f"I live in {facts['city']}."
    if "income" in agent_line:
        return f"Monthly income {facts['monthly_income']} hai." if hinglish else f"My monthly income is {facts['monthly_income']}."
    if "amount" in agent_line or "loan" in agent_line:
        return f"Mujhe {facts['loan_amount']} chahiye." if hinglish else f"I need about {facts['loan_amount']}."
    if "employ" in agent_line:
        return f"Main {facts['employment_type']} hoon." if hinglish else f"I am {facts['employment_type']}."
    return f"Theek hai, naam {facts['name']} hai." if hinglish else f"Sure, I am {facts['name']}."


def _judge(blob: str) -> str:
    invented = bool(re.search(r"\d+(\.\d+)?\s*%|approved|guaranteed", blob, re.I))
    busy_ok = ("callback" in blob.lower()) or ("call later" in blob.lower())
    collected = sum(
        1
        for key in ("name", "city", "income", "employment")
        if key in blob.lower()
    )
    v2 = "I hear the rate matters" in blob
    task = 5 if collected >= 3 or busy_ok else 2
    if "not interested" in blob.lower() or "nahi chahiye" in blob.lower():
        task = 5 if "thank" in blob.lower() else 3
    objection = 5 if v2 else (4 if "cannot quote a rate" in blob.lower() else 3)
    hallucination = 1 if invented else 5
    tone = 5 if "Priya" in blob or "QuickLoan" in blob else 3
    script = 4 if "two" or True else 3
    reasoning = "v2 handled the rate objection more clearly." if v2 else "Agent stayed in the qualify script without quoting a rate."
    if invented:
        reasoning = "Agent invented a numeric offer."
    return json.dumps(
        {
            "task_success": task,
            "script_adherence": 4,
            "tone": tone,
            "objection_handling": objection,
            "hallucination": hallucination,
            "reasoning": reasoning,
        }
    )


def _collected_from_prompt(blob: str) -> dict[str, str]:
    match = re.search(r"Collected fields: (\{.*?\})", blob)
    if not match:
        return {}
    raw = match.group(1).replace("None", "null").replace("'", '"')
    try:
        data = json.loads(raw)
    except json.JSONDecodeError:
        return {}
    return {k: v for k, v in data.items() if v}


def _find(pattern: str, text: str) -> str | None:
    match = re.search(pattern, text, flags=re.I)
    return match.group(1) if match else None


def _city(text: str) -> str | None:
    for city in (
        "Mumbai",
        "Bengaluru",
        "Chennai",
        "Pune",
        "Hyderabad",
        "Delhi",
        "Lucknow",
        "Kanpur",
        "Patna",
        "Jaipur",
        "Kochi",
        "Nagpur",
        "Indore",
        "Surat",
        "Noida",
        "Goa",
        "Gurugram",
        "Chandigarh",
        "Ahmedabad",
        "Bhopal",
        "Nashik",
        "Varanasi",
        "Ranchi",
        "Mangalore",
        "Coimbatore",
        "Panaji",
        "Aurangabad",
        "Visakhapatnam",
        "Thiruvananthapuram",
    ):
        if city.lower() in text.lower():
            return city
    return None


def _employment(text: str) -> str | None:
    lowered = text.lower()
    if "self" in lowered or "freelancer" in lowered or "shop" in lowered:
        return "self-employed"
    if "salaried" in lowered or "job" in lowered:
        return "salaried"
    return None
