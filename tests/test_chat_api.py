from fastapi.testclient import TestClient

from agent.chat import SalesAgent
from agent.session import SessionStore
from api import main as api_main


class FakeLLM:
    def __init__(self, payload: str) -> None:
        self.payload = payload
        self.calls = 0
        self.messages = []

    def complete(self, messages, *, temperature, json_mode=False) -> str:
        self.calls += 1
        self.messages.append(messages)
        return self.payload


def test_health():
    client = TestClient(api_main.app)
    assert client.get("/health").json() == {"status": "ok"}


def test_chat_endpoint_with_fake_llm():
    store = SessionStore()
    llm = FakeLLM(
        '{"reply": "Hi, this is Priya from QuickLoan. May I have your name?", '
        '"extracted": {}, "customer_busy": false, "objection": false, '
        '"not_interested": false, "conversation_end": false}'
    )
    api_main.store = store
    api_main._agent = SalesAgent(store=store, llm=llm, prompt_version="v1")
    client = TestClient(api_main.app)
    response = client.post("/chat", json={"session_id": "abc", "message": "Hello"})
    assert response.status_code == 200
    body = response.json()
    assert "Priya" in body["reply"]
    assert body["state"] == "QUALIFY"
    assert llm.calls == 1


def test_chat_remembers_out_of_order_details_and_intent():
    store = SessionStore()
    llm = FakeLLM(
        '{"reply": "Around 30,000 in Chennai, got it. What do you do for work?", '
        '"extracted": {"city": "Chennai", "loan_amount": "30000"}, '
        '"conversation_intent": "answer", "last_user_intent": "shared city and amount", '
        '"clarification_needed": null, "user_declined_field": null, '
        '"customer_busy": false, "objection": false, '
        '"not_interested": false, "conversation_end": false}'
    )
    agent = SalesAgent(store=store, llm=llm, prompt_version="v2")

    result = agent.chat("memory", "I need 30k and I live in Chennai")

    assert result["collected"]["city"] == "Chennai"
    assert result["collected"]["loan_amount"] == "30000"
    assert result["conversation_intent"] == "answer"
    assert "Recent Priya replies" in llm.messages[0][0]["content"]


def test_chat_preserves_model_clarification_for_ambiguous_amount():
    store = SessionStore()
    llm = FakeLLM(
        '{"reply": "Just to check, do you mean 5,000 or 50,000 per month?", '
        '"extracted": {}, "conversation_intent": "clarification", '
        '"last_user_intent": "gave an unclear amount", '
        '"clarification_needed": "5000 or 50000", "user_declined_field": null, '
        '"customer_busy": false, "objection": false, '
        '"not_interested": false, "conversation_end": false}'
    )
    result = SalesAgent(store=store, llm=llm).chat("ambiguous", "5")

    assert result["clarification_needed"] == "5000 or 50000"
    assert "5,000" in result["reply"]
