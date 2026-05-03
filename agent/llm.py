import json
from typing import Any, Protocol

from config import Settings, get_settings


class LLMClient(Protocol):
    def complete(
        self,
        messages: list[dict[str, str]],
        *,
        temperature: float,
        json_mode: bool = False,
    ) -> str: ...


class OpenAIClient:
    def __init__(self, settings: Settings) -> None:
        from openai import OpenAI

        if not settings.openai_api_key:
            raise RuntimeError("OPENAI_API_KEY is not set")
        self._client = OpenAI(api_key=settings.openai_api_key)
        self._model = settings.openai_model

    def complete(
        self,
        messages: list[dict[str, str]],
        *,
        temperature: float,
        json_mode: bool = False,
    ) -> str:
        kwargs: dict[str, Any] = {
            "model": self._model,
            "messages": messages,
            "temperature": temperature,
        }
        if json_mode:
            kwargs["response_format"] = {"type": "json_object"}
        response = self._client.chat.completions.create(**kwargs)
        return response.choices[0].message.content or ""


class AnthropicClient:
    def __init__(self, settings: Settings) -> None:
        from anthropic import Anthropic

        if not settings.anthropic_api_key:
            raise RuntimeError("ANTHROPIC_API_KEY is not set")
        self._client = Anthropic(api_key=settings.anthropic_api_key)
        self._model = settings.anthropic_model

    def complete(
        self,
        messages: list[dict[str, str]],
        *,
        temperature: float,
        json_mode: bool = False,
    ) -> str:
        system = ""
        converted = []
        for message in messages:
            if message["role"] == "system":
                system += message["content"] + "\n"
                continue
            converted.append({"role": message["role"], "content": message["content"]})
        if json_mode:
            system += "\nRespond with a single JSON object only."
        response = self._client.messages.create(
            model=self._model,
            system=system.strip() or "You are a helpful assistant.",
            messages=converted,
            temperature=temperature,
            max_tokens=1024,
        )
        return response.content[0].text


class HuggingFaceClient:
    def __init__(self, settings: Settings) -> None:
        if not settings.hf_token:
            raise RuntimeError("HF_TOKEN is not set")
        self._token = settings.hf_token
        self._model = settings.hf_model

    def complete(
        self,
        messages: list[dict[str, str]],
        *,
        temperature: float,
        json_mode: bool = False,
    ) -> str:
        import httpx

        payload: dict[str, Any] = {
            "model": self._model,
            "messages": messages,
            "temperature": temperature,
        }
        if json_mode:
            payload["response_format"] = {"type": "json_object"}

        response = httpx.post(
            "https://router.huggingface.co/v1/chat/completions",
            headers={"Authorization": f"Bearer {self._token}"},
            json=payload,
            timeout=60.0,
        )
        response.raise_for_status()
        data = response.json()
        return data["choices"][0]["message"]["content"] or ""


def build_llm_client(settings: Settings | None = None) -> LLMClient:
    settings = settings or get_settings()
    if settings.llm_provider == "anthropic":
        return AnthropicClient(settings)
    if settings.llm_provider == "huggingface":
        return HuggingFaceClient(settings)
    return OpenAIClient(settings)


def parse_json_object(text: str) -> dict[str, Any]:
    """Parse a JSON object, including when wrapped in markdown fences."""
    cleaned = text.strip()
    if cleaned.startswith("```"):
        cleaned = cleaned.split("\n", 1)[1]
        if cleaned.endswith("```"):
            cleaned = cleaned[: -3]
        cleaned = cleaned.strip()
        if cleaned.startswith("json"):
            cleaned = cleaned[4:].strip()
    start = cleaned.find("{")
    end = cleaned.rfind("}")
    if start == -1 or end == -1 or end <= start:
        raise ValueError(f"No JSON object found in model output: {text[:200]!r}")
    return json.loads(cleaned[start : end + 1])
