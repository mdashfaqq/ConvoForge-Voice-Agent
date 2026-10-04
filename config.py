from functools import lru_cache
from pathlib import Path
from typing import Literal

from pydantic_settings import BaseSettings, SettingsConfigDict

ROOT = Path(__file__).resolve().parent


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", extra="ignore")

    llm_provider: Literal["openai", "anthropic", "huggingface"] = "huggingface"
    openai_api_key: str = ""
    openai_model: str = "gpt-4o-mini"
    anthropic_api_key: str = ""
    anthropic_model: str = "claude-3-5-haiku-latest"
    hf_token: str = ""
    hf_model: str = "Qwen/Qwen2.5-72B-Instruct"
    agent_temperature: float = 0.4
    simulator_temperature: float = 0.7
    prompt_version: str = "v1"
    agent_config: str = "agents/quickloan.yaml"

    supabase_url: str = ""
    supabase_service_role_key: str = ""


@lru_cache
def get_settings() -> Settings:
    return Settings()
