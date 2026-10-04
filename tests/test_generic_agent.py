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
        self.messages = []

    def complete(self, messages, *, temperature, json_mode=False) -> str:
        self.messages.append(messages)
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
            {"specialty": "dermatology", "appointment_date": "tomorrow"},
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
        llm=ConfiguredLLM({"loan_amount": "30000", "specialty": "dermatology"}),
    )

    result = agent.chat("clinic-fields", "I need a dermatologist")

    assert result["collected"] == {"specialty": "dermatology"}
    assert "loan_amount" not in result["collected"]


def test_restaurant_prompt_contains_only_restaurant_configuration():
    config = load_agent_config(ROOT / "agents" / "restaurant.yaml")
    llm = ConfiguredLLM({"party_size": 5})
    agent = VoiceAgent(config=config, store=GenericSessionStore(), llm=llm)

    result = agent.chat("restaurant-prompt", "I need a 5 seater table booking")
    prompt = llm.messages[0][0]["content"]

    assert result["collected"] == {"party_size": 5}
    assert "Ava" in prompt
    assert "Reservation Assistant" in prompt
    assert "check_availability" in prompt
    assert "special_requests" in prompt
    assert "QuickLoan" not in prompt
    assert "loan_amount" not in prompt


def test_generic_engine_replaces_corrected_field_value():
    config = load_agent_config(ROOT / "agents" / "restaurant.yaml")
    store = GenericSessionStore()
    first = VoiceAgent(config=config, store=store, llm=ConfiguredLLM({"party_size": 5}))
    second = VoiceAgent(config=config, store=store, llm=ConfiguredLLM({"party_size": 6}))

    first.chat("correction", "A table for five")
    result = second.chat("correction", "Actually, make that six")

    assert result["collected"]["party_size"] == 6


def test_sessions_remain_isolated_by_agent_id():
    store = GenericSessionStore()
    restaurant = load_agent_config(ROOT / "agents" / "restaurant.yaml")
    clinic = load_agent_config(ROOT / "agents" / "clinic.yaml")
    restaurant_agent = VoiceAgent(
        config=restaurant,
        store=store,
        llm=ConfiguredLLM({"party_size": 5}),
    )
    clinic_agent = VoiceAgent(
        config=clinic,
        store=store,
        llm=ConfiguredLLM({"specialty": "dermatology"}),
    )

    restaurant_result = restaurant_agent.chat("restaurant-session", "Table for five")
    clinic_result = clinic_agent.chat("clinic-session", "Dermatologist tomorrow")

    assert restaurant_result["agent_id"] == "restaurant"
    assert restaurant_result["collected"] == {"party_size": 5}
    assert clinic_result["agent_id"] == "clinic"
    assert clinic_result["collected"] == {"specialty": "dermatology"}


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
