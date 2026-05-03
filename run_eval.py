"""CLI: run simulated customers, judge transcripts, store results, print a summary."""

from __future__ import annotations

import argparse
from collections import defaultdict
from pathlib import Path

from rich.console import Console
from rich.table import Table

from agent.llm import build_llm_client
from config import get_settings
from db.client import get_supabase
from db.store import persist_run
from eval.judge import JudgeScores, judge_transcript
from eval.simulate import load_personas, run_simulations

console = Console()


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Run SalesVoice evaluation harness")
    parser.add_argument("--prompt", default="v1", choices=["v1", "v2"], help="Prompt version")
    parser.add_argument("--personas", type=int, default=30, help="Number of personas to run")
    parser.add_argument(
        "--skip-db",
        action="store_true",
        help="Print results without writing to Supabase",
    )
    parser.add_argument(
        "--mock",
        action="store_true",
        help="Use deterministic mock LLMs (no API key required)",
    )
    return parser.parse_args()


def summarize(prompt_version: str, scored: list[tuple[dict, JudgeScores]]) -> None:
    by_metric: dict[str, list[int]] = defaultdict(list)
    by_lang: dict[str, list[int]] = defaultdict(list)
    table = Table(title=f"SalesVoice Eval — prompt {prompt_version}")
    table.add_column("Persona")
    table.add_column("Lang")
    table.add_column("Intent")
    table.add_column("Task")
    table.add_column("Script")
    table.add_column("Tone")
    table.add_column("Objection")
    table.add_column("Halluc.")
    table.add_column("Reasoning")

    for convo, scores in scored:
        table.add_row(
            convo["persona_id"],
            convo["language"],
            str(convo.get("intent") or ""),
            str(scores.task_success),
            str(scores.script_adherence),
            str(scores.tone),
            str(scores.objection_handling),
            str(scores.hallucination),
            scores.reasoning,
        )
        by_metric["task_success"].append(scores.task_success)
        by_metric["script_adherence"].append(scores.script_adherence)
        by_metric["tone"].append(scores.tone)
        by_metric["objection_handling"].append(scores.objection_handling)
        by_metric["hallucination"].append(scores.hallucination)
        by_lang[convo["language"]].append(scores.task_success)

    console.print(table)

    avg = Table(title="Average by metric")
    avg.add_column("Metric")
    avg.add_column("Average")
    for metric, values in by_metric.items():
        avg.add_row(metric, f"{sum(values) / len(values):.2f}")
    console.print(avg)

    lang = Table(title="Task success by language")
    lang.add_column("Language")
    lang.add_column("Avg task_success")
    for language, values in sorted(by_lang.items()):
        lang.add_row(language, f"{sum(values) / len(values):.2f}")
    console.print(lang)


def main() -> None:
    args = parse_args()
    settings = get_settings()
    personas = load_personas()[: max(1, args.personas)]
    if args.mock:
        from eval.mock_llm import MockLLM

        llm = MockLLM(prompt_version=args.prompt)
        source = "mock"
    else:
        llm = build_llm_client(settings)
        source = settings.llm_provider
    console.print(f"Running {len(personas)} personas with prompt {args.prompt} via {source}")
    conversations = run_simulations(personas, args.prompt, llm)
    scored: list[tuple[dict, JudgeScores]] = []
    by_persona: dict[str, JudgeScores] = {}
    for convo in conversations:
        judged = judge_transcript(convo["transcript"], llm)
        scored.append((convo, judged))
        by_persona[convo["persona_id"]] = judged

    summarize(args.prompt, scored)

    if args.skip_db:
        console.print("[yellow]Skipped database write (--skip-db).[/yellow]")
        return

    supabase = get_supabase(settings)
    run = persist_run(args.prompt, conversations, by_persona, supabase)
    console.print(f"[green]Saved run id={run.id} to Supabase.[/green]")

    report_path = Path("eval_last_summary.txt")
    report_path.write_text(
        "\n".join(
            f"{c['persona_id']}\t{j.task_success}\t{j.script_adherence}\t{j.tone}\t"
            f"{j.objection_handling}\t{j.hallucination}\t{j.reasoning}"
            for c, j in scored
        ),
        encoding="utf-8",
    )


if __name__ == "__main__":
    main()
