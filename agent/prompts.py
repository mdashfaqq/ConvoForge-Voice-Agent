import json
from pathlib import Path
from typing import Any

import yaml

from agent.state import AgentState, Session

PROMPTS_DIR = Path(__file__).resolve().parent.parent / "prompts"


def load_prompt_bundle(version: str) -> dict[str, Any]:
    path = PROMPTS_DIR / f"{version}.yaml"
    if not path.exists():
        raise FileNotFoundError(f"Unknown prompt version '{version}'. Expected {path}")
    with path.open(encoding="utf-8") as handle:
        return yaml.safe_load(handle)


def render_system_prompt(session: Session) -> str:
    bundle = load_prompt_bundle(session.prompt_version)
    few_shot_lines = []
    for example in bundle.get("few_shot", []):
        few_shot_lines.append(f"Customer: {example['customer']}")
        few_shot_lines.append(f"Priya: {example['agent']}")

    missing = ", ".join(session.fields.missing()) or "none"
    collected = json.dumps(session.fields.model_dump())
    return (
        f"{bundle['system'].strip()}\n\n"
        f"Current state: {session.state.value}\n"
        f"Collected fields: {collected}\n"
        f"Still missing: {missing}\n"
        f"Ended reason: {session.ended_reason or 'n/a'}\n\n"
        "Few-shot examples:\n"
        + "\n".join(few_shot_lines)
        + "\n\n"
        + _state_instruction(session.state)
    )


def _state_instruction(state: AgentState) -> str:
    if state == AgentState.GREET:
        return (
            "You are greeting the customer. Introduce yourself as Priya from QuickLoan "
            "and ask for their name."
        )
    if state == AgentState.QUALIFY:
        return (
            "Stay in qualification. Ask only for the next missing field. "
            "Do not jump ahead or repeat fields you already have."
        )
    if state == AgentState.HANDLE_OBJECTION:
        return (
            "Handle the objection calmly. Do not invent rates or promise approval. "
            "Offer a human callback if they want specifics, then continue qualifying if possible."
        )
    if state == AgentState.CLOSE:
        return (
            "Close politely: summarize the details you collected and say a loan specialist "
            "will follow up. Do not promise approval."
        )
    return (
        "The conversation is ending. Thank them briefly. If they were busy, offer a callback. "
        "Do not ask more qualification questions."
    )
