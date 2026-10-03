from __future__ import annotations

from typing import Any, Protocol

from db.client import get_supabase
from eval.judge import JudgeScores


class RunRecord:
    def __init__(self, run_id: int, prompt_version: str) -> None:
        self.id = run_id
        self.prompt_version = prompt_version


class SupabaseLike(Protocol):
    def table(self, name: str) -> Any: ...


def persist_run(
    prompt_version: str,
    conversations: list[dict],
    scores_by_persona: dict[str, JudgeScores],
    client: SupabaseLike | None = None,
) -> RunRecord:
    sb = client or get_supabase()
    run_row = (
        sb.table("runs")
        .insert({"prompt_version": prompt_version})
        .execute()
        .data[0]
    )
    run_id = int(run_row["id"])

    for item in conversations:
        convo_row = (
            sb.table("conversations")
            .insert(
                {
                    "run_id": run_id,
                    "persona_id": item["persona_id"],
                    "language": item["language"],
                    "transcript": item["transcript"],
                }
            )
            .execute()
            .data[0]
        )
        judged = scores_by_persona[item["persona_id"]]
        payload = [
            {
                "conversation_id": convo_row["id"],
                "metric": row["metric"],
                "score": row["score"],
                "reasoning": row["reasoning"],
            }
            for row in judged.as_metric_rows()
        ]
        sb.table("scores").insert(payload).execute()

    return RunRecord(run_id, prompt_version)


def fetch_analysis(client: SupabaseLike | None = None) -> dict[str, list[dict]]:
    sb = client or get_supabase()
    return {
        "avg_score_by_version": sb.table("avg_score_by_version").select("*").execute().data,
        "task_success_by_language": sb.table("task_success_by_language").select("*").execute().data,
        "worst_conversations": sb.table("worst_conversations").select("*").execute().data,
        "v1_vs_v2": sb.table("v1_vs_v2").select("*").execute().data,
    }
