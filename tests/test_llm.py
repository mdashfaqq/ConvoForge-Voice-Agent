from agent.llm import FallbackClient


class StubLLM:
    def __init__(self, result: str | None = None, error: str | None = None) -> None:
        self.result = result
        self.error = error
        self.calls = 0

    def complete(self, messages, *, temperature, json_mode=False) -> str:
        self.calls += 1
        if self.error:
            raise RuntimeError(self.error)
        return self.result or ""


def test_fallback_client_uses_huggingface_after_openai_failure():
    primary = StubLLM(error="OpenAI credits exhausted")
    fallback = StubLLM(result='{"reply":"ok"}')

    result = FallbackClient(primary, fallback).complete(
        [{"role": "user", "content": "Hello"}],
        temperature=0.4,
        json_mode=True,
    )

    assert result == '{"reply":"ok"}'
    assert primary.calls == 1
    assert fallback.calls == 1
