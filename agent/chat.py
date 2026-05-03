from agent.llm import LLMClient, build_llm_client, parse_json_object
from agent.prompts import render_system_prompt
from agent.session import SessionStore
from agent.state import AgentState, QualificationFields, Session, TurnSignals, next_state
from config import get_settings

EXTRACT_INSTRUCTIONS = """
After the customer's latest message, return JSON with this schema:
{
  "reply": "your spoken reply, max two sentences",
  "extracted": {
    "name": string or null,
    "city": string or null,
    "monthly_income": string or null,
    "loan_amount": string or null,
    "employment_type": string or null
  },
  "customer_busy": boolean,
  "objection": boolean,
  "not_interested": boolean,
  "conversation_end": boolean
}
Only fill extracted fields that the customer actually stated. Never invent values.
Interpret the customer's meaning, not just exact keywords. A customer can answer with a
sentence, a short answer, or a correction to an earlier answer. If they say they are a
student or are not earning yet, record employment_type as "student" and monthly_income as
"0". If they identify a parent or guardian as the financial supporter, record the stated
supporter's income in monthly_income and keep employment_type as the customer's situation.
Do not treat "I am a student" or equivalent employment statements as the customer's name.
Accept numbers expressed as words, Indian lakh/crore notation, or digits for loan and income.
Do not ask again for a field that is already answered, including a zero income.
Before responding, review every customer turn in the transcript and validate that each
answered field is present in extracted. For example, if the customer says they are a
student and are not earning yet, extracted must include employment_type="student" and
monthly_income="0"; asking for monthly income again is incorrect.
If all five fields are present after extraction, set the reply as a brief closing summary
and say a specialist will follow up. Do not ask a confirmation question or request another
field when all five fields are complete.
If they ask for an interest rate, set objection=true and do not quote a number.
If they are busy, set customer_busy=true and offer a callback in reply.
"""


class SalesAgent:
    def __init__(
        self,
        store: SessionStore | None = None,
        llm: LLMClient | None = None,
        prompt_version: str = "v1",
        temperature: float | None = None,
    ) -> None:
        self.store = store or SessionStore()
        self.prompt_version = prompt_version
        self.temperature = (
            temperature if temperature is not None else get_settings().agent_temperature
        )
        self._llm = llm
        self._llm_error: Exception | None = None
        if llm is None:
            try:
                self._llm = build_llm_client()
            except Exception as exc:  # noqa: BLE001 - surface later on first turn
                self._llm_error = exc

    @property
    def llm(self) -> LLMClient:
        if self._llm is None:
            raise RuntimeError(f"LLM client is not configured: {self._llm_error}")
        return self._llm

    def chat(
        self,
        session_id: str,
        message: str,
        prompt_version: str | None = None,
        language: str = "english",
    ) -> dict:
        version = prompt_version or self.prompt_version
        session = self.store.get_or_create(session_id, prompt_version=version)
        session.prompt_version = version
        session.record("user", message)

        if session.state == AgentState.END:
            reply = _terminal_reply(session)
            session.record("assistant", reply)
            return _payload(session, reply)

        raw = self.llm.complete(
            [
                {
                    "role": "system",
                    "content": (
                        render_system_prompt(session)
                        + EXTRACT_INSTRUCTIONS
                        + _language_instruction(language)
                    ),
                },
                *[{"role": turn["role"], "content": turn["content"]} for turn in session.transcript],
            ],
            temperature=self.temperature,
            json_mode=True,
        )
        data = parse_json_object(raw)
        model_fields = QualificationFields.model_validate(data.get("extracted") or {})
        signals = TurnSignals(
            extracted=model_fields,
            customer_busy=bool(data.get("customer_busy")),
            objection=bool(data.get("objection")),
            not_interested=bool(data.get("not_interested")),
            conversation_end=bool(data.get("conversation_end")),
        )
        session.state = next_state(session, signals)
        reply = str(data.get("reply") or "").strip() or _fallback_reply(session)
        if session.fields.is_complete() and session.state == AgentState.CLOSE:
            reply = _fallback_reply(session)
        session.record("assistant", reply)
        if session.state == AgentState.CLOSE and (
            signals.not_interested or signals.conversation_end
        ):
            session.state = AgentState.END
        return _payload(session, reply)


def _language_instruction(language: str) -> str:
    instructions = {
        "english": "Reply in clear, natural English.",
        "hinglish": "Reply in natural Indian Hinglish, mixing simple Hindi and English.",
        "hindi": "Reply in clear, conversational Hindi using Devanagari script.",
    }
    return f"\n\nResponse language: {instructions.get(language, instructions['english'])}"


def _payload(session: Session, reply: str) -> dict:
    return {
        "session_id": session.session_id,
        "reply": reply,
        "state": session.state.value,
        "collected": session.fields.model_dump(),
        "missing": session.fields.missing(),
        "ended_reason": session.ended_reason,
    }


def _terminal_reply(session: Session) -> str:
    if session.ended_reason == "busy_callback":
        return "No problem at all. I will arrange a callback at a better time. Thank you."
    return "Thank you for your time. Have a good day."


def _fallback_reply(session: Session) -> str:
    missing = session.fields.missing()
    if session.state == AgentState.END:
        return _terminal_reply(session)
    if missing:
        label = missing[0].replace("_", " ")
        return f"Thanks. Could you share your {label} so I can continue?"
    return "Thanks, I have what I need. A specialist will follow up without promising any approval."
