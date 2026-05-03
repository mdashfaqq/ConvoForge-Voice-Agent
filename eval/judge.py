from __future__ import annotations

from typing import Any

from pydantic import BaseModel, Field, field_validator

from agent.llm import LLMClient, parse_json_object

METRICS = (
    "task_success",
    "script_adherence",
    "tone",
    "objection_handling",
    "hallucination",
)

JUDGE_RUBRIC = """
You are a strict evaluation judge for a loan-qualification sales call.
Score the transcript only. Temperature must be treated as 0: be consistent.
Return a single JSON object with keys:
task_success, script_adherence, tone, objection_handling, hallucination, reasoning.

Each metric is an integer 1-5.
reasoning is one sentence.

Fixed rubric:
- task_success: 5 if the agent collected name, city, monthly income, loan amount, and
  employment type, OR correctly took a graceful exit (busy callback / not interested)
  without pressuring. 1 if it ignored a hang-up or failed both collection and exit.
- script_adherence: 5 if replies stay within Priya/QuickLoan, max about two sentences,
  no banned data requests. Deduct for rambling or skipping the state flow.
- tone: 5 polite, concise, voice-like. Deduct for pushy, rude, or overly long turns.
- objection_handling: 5 if rate/busy/not-interested/confusion is handled without
  inventing terms and with a callback when needed. 3 if mixed. 1 if ignored.
- hallucination: 5 means NO invented facts (rates, approval, EMI, bank claims).
  1 means the agent invented interest rates, promised approval, or fabricated policy.

Do not reward hallucinated rates. Lower hallucination if any number is invented.
"""


class JudgeScores(BaseModel):
    task_success: int
    script_adherence: int
    tone: int
    objection_handling: int
    hallucination: int
    reasoning: str = Field(min_length=1)

    @field_validator(
        "task_success",
        "script_adherence",
        "tone",
        "objection_handling",
        "hallucination",
        mode="before",
    )
    @classmethod
    def score_range(cls, value: Any) -> int:
        number = int(value)
        if number < 1 or number > 5:
            raise ValueError("scores must be integers 1-5")
        return number

    def as_metric_rows(self) -> list[dict[str, Any]]:
        rows = []
        for metric in METRICS:
            rows.append(
                {
                    "metric": metric,
                    "score": getattr(self, metric),
                    "reasoning": self.reasoning,
                }
            )
        return rows


def judge_transcript(transcript: list[dict[str, str]], llm: LLMClient) -> JudgeScores:
    rendered = "\n".join(f"{turn['role']}: {turn['content']}" for turn in transcript)
    raw = llm.complete(
        [
            {"role": "system", "content": JUDGE_RUBRIC.strip()},
            {
                "role": "user",
                "content": (
                    "Score this conversation.\n\n"
                    f"{rendered}\n\n"
                    "JSON keys: task_success, script_adherence, tone, "
                    "objection_handling, hallucination, reasoning."
                ),
            },
        ],
        temperature=0,
        json_mode=True,
    )
    return JudgeScores.model_validate(parse_json_object(raw))
