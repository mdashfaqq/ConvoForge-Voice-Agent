-- Paste into the Supabase SQL editor, or read the matching views:
-- avg_score_by_version, task_success_by_language, worst_conversations, v1_vs_v2

-- Average score per metric per prompt version
SELECT
    r.prompt_version,
    s.metric,
    ROUND(AVG(s.score)::numeric, 2) AS avg_score,
    COUNT(*) AS n
FROM scores s
JOIN conversations c ON c.id = s.conversation_id
JOIN runs r ON r.id = c.run_id
GROUP BY r.prompt_version, s.metric
ORDER BY r.prompt_version, s.metric;

-- Task success rate: English vs Hinglish
SELECT
    r.prompt_version,
    c.language,
    ROUND(AVG(s.score)::numeric, 2) AS avg_task_success,
    ROUND(100.0 * AVG(CASE WHEN s.score >= 4 THEN 1 ELSE 0 END), 1) AS success_rate_pct
FROM scores s
JOIN conversations c ON c.id = s.conversation_id
JOIN runs r ON r.id = c.run_id
WHERE s.metric = 'task_success'
GROUP BY r.prompt_version, c.language
ORDER BY r.prompt_version, c.language;

-- Five worst conversations (lowest mean score)
SELECT
    c.id AS conversation_id,
    r.prompt_version,
    c.persona_id,
    c.language,
    ROUND(AVG(s.score)::numeric, 2) AS mean_score,
    MIN(s.reasoning) AS sample_reasoning
FROM scores s
JOIN conversations c ON c.id = s.conversation_id
JOIN runs r ON r.id = c.run_id
GROUP BY c.id, r.prompt_version, c.persona_id, c.language
ORDER BY mean_score ASC, c.id
LIMIT 5;

-- v1 vs v2 comparison
SELECT
    s.metric,
    ROUND(AVG(s.score) FILTER (WHERE r.prompt_version = 'v1')::numeric, 2) AS v1_avg,
    ROUND(AVG(s.score) FILTER (WHERE r.prompt_version = 'v2')::numeric, 2) AS v2_avg,
    ROUND(
        (
            AVG(s.score) FILTER (WHERE r.prompt_version = 'v2')
            - AVG(s.score) FILTER (WHERE r.prompt_version = 'v1')
        )::numeric,
        2
    ) AS delta_v2_minus_v1
FROM scores s
JOIN conversations c ON c.id = s.conversation_id
JOIN runs r ON r.id = c.run_id
WHERE r.prompt_version IN ('v1', 'v2')
GROUP BY s.metric
ORDER BY s.metric;
