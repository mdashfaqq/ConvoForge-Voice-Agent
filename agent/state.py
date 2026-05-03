from enum import Enum
from typing import Optional

from pydantic import BaseModel, Field


class AgentState(str, Enum):
    GREET = "GREET"
    QUALIFY = "QUALIFY"
    HANDLE_OBJECTION = "HANDLE_OBJECTION"
    CLOSE = "CLOSE"
    END = "END"


REQUIRED_FIELDS = (
    "name",
    "city",
    "monthly_income",
    "loan_amount",
    "employment_type",
)


class QualificationFields(BaseModel):
    name: Optional[str] = None
    city: Optional[str] = None
    monthly_income: Optional[str] = None
    loan_amount: Optional[str] = None
    employment_type: Optional[str] = None

    def merge(self, other: "QualificationFields") -> "QualificationFields":
        data = self.model_dump()
        for key, value in other.model_dump().items():
            if value not in (None, ""):
                data[key] = str(value).strip()
        return QualificationFields(**data)

    def missing(self) -> list[str]:
        return [name for name in REQUIRED_FIELDS if not getattr(self, name)]

    def is_complete(self) -> bool:
        return not self.missing()


class TurnSignals(BaseModel):
    extracted: QualificationFields = Field(default_factory=QualificationFields)
    customer_busy: bool = False
    objection: bool = False
    not_interested: bool = False
    conversation_end: bool = False


class Session(BaseModel):
    session_id: str
    prompt_version: str = "v1"
    state: AgentState = AgentState.GREET
    fields: QualificationFields = Field(default_factory=QualificationFields)
    objection_handled: bool = False
    transcript: list[dict] = Field(default_factory=list)
    ended_reason: Optional[str] = None

    def record(self, role: str, content: str) -> None:
        self.transcript.append({"role": role, "content": content})


def next_state(session: Session, signals: TurnSignals) -> AgentState:
    """Pure state transition used by the agent and unit tests."""
    if session.state == AgentState.END:
        return AgentState.END

    session.fields = session.fields.merge(signals.extracted)

    if signals.customer_busy:
        session.ended_reason = "busy_callback"
        return AgentState.END

    if signals.not_interested or signals.conversation_end:
        session.ended_reason = session.ended_reason or "declined"
        if session.state == AgentState.CLOSE:
            return AgentState.END
        return AgentState.CLOSE

    if signals.objection:
        session.objection_handled = True
        return AgentState.HANDLE_OBJECTION

    if session.state == AgentState.GREET:
        return AgentState.QUALIFY if not session.fields.is_complete() else AgentState.CLOSE

    if session.state == AgentState.HANDLE_OBJECTION:
        if session.fields.is_complete():
            return AgentState.CLOSE
        return AgentState.QUALIFY

    if session.state == AgentState.QUALIFY:
        if session.fields.is_complete():
            return AgentState.CLOSE
        return AgentState.QUALIFY

    if session.state == AgentState.CLOSE:
        return AgentState.END

    return session.state
