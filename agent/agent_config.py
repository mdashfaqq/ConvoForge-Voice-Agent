from pathlib import Path
from typing import Any, Literal

import yaml
from pydantic import BaseModel, Field


FieldType = Literal[
    "string",
    "number",
    "currency",
    "date",
    "time",
    "boolean",
    "enum",
    "email",
    "phone",
    "location",
    "duration",
]


class AgentField(BaseModel):
    id: str
    label: str
    type: FieldType = "string"
    required: bool = False
    options: list[str] = Field(default_factory=list)


class Personality(BaseModel):
    tone: str = "friendly"
    formality: str = "medium"
    verbosity: str = "concise"
    language: str = "auto"
    interruption_style: str = "natural"


class AgentGoal(BaseModel):
    type: str
    description: str


class AgentConfig(BaseModel):
    id: str
    name: str
    role: str
    greeting: str = "How can I help you today?"
    closing: str = "Thanks for speaking with me."
    personality: Personality = Field(default_factory=Personality)
    goal: AgentGoal
    fields: list[AgentField] = Field(default_factory=list)
    actions: list[str] = Field(default_factory=list)
    rules: list[str] = Field(default_factory=list)
    voice: dict[str, Any] = Field(default_factory=dict)

    @property
    def required_fields(self) -> list[AgentField]:
        return [field for field in self.fields if field.required]


def load_agent_config(path: str | Path) -> AgentConfig:
    config_path = Path(path)
    with config_path.open(encoding="utf-8") as handle:
        return AgentConfig.model_validate(yaml.safe_load(handle))
