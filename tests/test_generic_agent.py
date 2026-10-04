import json
from pathlib import Path

import pytest
from fastapi.testclient import TestClient

from agent.agent_config import load_agent_config
from agent.generic import GenericSessionStore, VoiceAgent
from api import main as api_main


ROOT = Path(__file__).resolve().parent.parent


class ConfiguredLLM:
    def __init__(self, fields: dict[str, str]) -> None:
        self.fields = fields

    def complete(self, messages, *, temperature, json_mode=False) -> str:
        return json.dumps(
            {
                "reply": "I have noted those details. What would you like to do next?",
                "intent": "answer",
                "fields": self.fields,
                "confidence": 0.95,
                "end": False,
            }
        )


@pytest.mark.parametrize(
    ("config_name", "fields"),
    [
        (
            "quickloan",
            {"city": "Chennai", "employment_type": "self-employed", "loan_amount": "30000"},
        ),
        (
            "clinic",
            {"doctor": "dermatology", "appointment_date": "tomorrow"},
        ),
        (
            "restaurant",
            {"date": "tomorrow", "time": "evening", "party_size": "4"},
        ),
    ],
)
def test_same_engine_supports_multiple_domains(config_name, fields):
    config = load_agent_config(ROOT / "agents" / f"{config_name}.yaml")
    agent = VoiceAgent(
        config=config,
        store=GenericSessionStore(),
        llm=ConfiguredLLM(fields),
    )

    result = agent.chat("demo", "I have several details to share")

    assert result["agent_id"] == config_name
    assert result["collected"] == fields
    assert result["goal"]["type"] == config.goal.type


def test_generic_engine_only_accepts_fields_from_active_configuration():
    config = load_agent_config(ROOT / "agents" / "clinic.yaml")
    agent = VoiceAgent(
        config=config,
        store=GenericSessionStore(),
        llm=ConfiguredLLM({"loan_amount": "30000", "doctor": "dermatology"}),
    )

    result = agent.chat("clinic-fields", "I need a dermatologist")

    assert result["collected"] == {"doctor": "dermatology"}
    assert "loan_amount" not in result["collected"]


def test_api_accepts_generic_agent_with_legacy_chat_contract():
    config = load_agent_config(ROOT / "agents" / "clinic.yaml")
    api_main._agent = VoiceAgent(
        config=config,
        store=GenericSessionStore(),
        llm=ConfiguredLLM({"doctor": "dermatology"}),
    )

    response = TestClient(api_main.app).post(
        "/chat",
        json={"session_id": "clinic-api", "message": "I need a dermatologist"},
    )

    assert response.status_code == 200
    assert response.json()["agent_id"] == "clinic"
