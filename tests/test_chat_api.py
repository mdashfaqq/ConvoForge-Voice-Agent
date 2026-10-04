from fastapi.testclient import TestClient

from agent.chat import SalesAgent
from agent.session import SessionStore
from api import main as api_main


class FakeLLM:
    def __init__(self, payload: str) -> None:
        self.payload = payload
        self.calls = 0

    def complete(self, messages, *, temperature, json_mode=False) -> str:
        self.calls += 1
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
def test_incoming_voice_returns_speech_gather():
    client = TestClient(api_main.app)

    response = client.post("/voice/incoming")

    assert response.status_code == 200
    assert response.headers["content-type"] == "application/xml"
    assert "<Gather" in response.text
    assert 'action="/voice/gather"' in response.text


def test_voice_gather_speaks_agent_reply():
    store = SessionStore()
    llm = FakeLLM(
        '{"reply": "May I have your name?", "extracted": {}, '
        '"customer_busy": false, "objection": false, '
        '"not_interested": false, "conversation_end": false}'
    )
    api_main.store = store
    api_main._agent = SalesAgent(store=store, llm=llm, prompt_version="v1")
    client = TestClient(api_main.app)

    response = client.post(
        "/voice/gather",
        data={"CallSid": "CA123", "SpeechResult": "Hello"},
    )

    assert response.status_code == 200
    assert "May I have your name?" in response.text
    assert "<Gather" in response.text
    assert llm.calls == 1
