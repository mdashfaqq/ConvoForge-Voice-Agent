from agent.llm import parse_json_object
from eval.judge import JudgeScores, METRICS


def test_parse_plain_json():
    data = parse_json_object('{"task_success": 4, "reasoning": "ok"}')
    assert data["task_success"] == 4


def test_parse_fenced_json():
    raw = """```json
    {
      "task_success": 5,
      "script_adherence": 4,
      "tone": 5,
      "objection_handling": 3,
      "hallucination": 5,
      "reasoning": "Collected all fields without inventing rates."
    }
    ```"""
    scores = JudgeScores.model_validate(parse_json_object(raw))
    assert scores.task_success == 5
    assert scores.hallucination == 5
    assert "rates" in scores.reasoning


def test_parse_json_with_preamble():
    raw = 'Here you go:\n{"task_success": 2, "script_adherence": 2, "tone": 3, "objection_handling": 1, "hallucination": 4, "reasoning": "Missed the busy callback."}'
    scores = JudgeScores.model_validate(parse_json_object(raw))
    assert scores.objection_handling == 1


def test_score_rows_cover_all_metrics():
    scores = JudgeScores(
        task_success=4,
        script_adherence=4,
        tone=5,
        objection_handling=3,
        hallucination=5,
        reasoning="Solid qualify path.",
    )
    rows = scores.as_metric_rows()
    assert [row["metric"] for row in rows] == list(METRICS)


def test_invalid_score_rejected():
    try:
        JudgeScores(
            task_success=6,
            script_adherence=1,
            tone=1,
            objection_handling=1,
            hallucination=1,
            reasoning="bad",
        )
        assert False, "expected validation error"
    except Exception:
        pass
