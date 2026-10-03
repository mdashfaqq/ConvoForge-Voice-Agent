from agent.prompts import load_prompt_bundle, render_system_prompt
from agent.state import Session


def test_prompt_versions_load():
    v1 = load_prompt_bundle("v1")
    v2 = load_prompt_bundle("v2")
    assert "Priya" in v1["system"]
    assert "QuickLoan" in v1["system"]
    assert len(v1["few_shot"]) == 3
    assert "Objection playbook" in v2["system"]


def test_render_includes_state_and_examples():
    text = render_system_prompt(Session(session_id="s1", prompt_version="v1"))
    assert "Current state: GREET" in text
    assert "Customer:" in text
    assert "Priya:" in text
