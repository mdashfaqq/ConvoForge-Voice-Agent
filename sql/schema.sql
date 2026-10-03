-- Run this in the Supabase SQL editor (or supabase db push).
-- Tables match the eval harness; views power analysis from the Python client.

create table if not exists public.runs (
    id bigint generated always as identity primary key,
    prompt_version varchar(32) not null,
    created_at timestamptz not null default now()
);

create table if not exists public.conversations (
    id bigint generated always as identity primary key,
    run_id bigint not null references public.runs(id) on delete cascade,
    persona_id varchar(32) not null,
    language varchar(32) not null,
    transcript jsonb not null
);

create table if not exists public.scores (
    id bigint generated always as identity primary key,
    conversation_id bigint not null references public.conversations(id) on delete cascade,
    metric varchar(64) not null,
    score integer not null check (score between 1 and 5),
    reasoning text not null
);

create index if not exists idx_conversations_run on public.conversations(run_id);
create index if not exists idx_scores_conversation on public.scores(conversation_id);
create index if not exists idx_scores_metric on public.scores(metric);

alter table public.runs enable row level security;
alter table public.conversations enable row level security;
alter table public.scores enable row level security;

-- Service role (used by run_eval.py) bypasses RLS. No anon policies on purpose.

create or replace view public.avg_score_by_version as
select
    r.prompt_version,
    s.metric,
    round(avg(s.score)::numeric, 2) as avg_score,
    count(*) as n
from public.scores s
join public.conversations c on c.id = s.conversation_id
join public.runs r on r.id = c.run_id
group by r.prompt_version, s.metric;

create or replace view public.task_success_by_language as
select
    r.prompt_version,
    c.language,
    round(avg(s.score)::numeric, 2) as avg_task_success,
    round(100.0 * avg(case when s.score >= 4 then 1 else 0 end), 1) as success_rate_pct
from public.scores s
join public.conversations c on c.id = s.conversation_id
join public.runs r on r.id = c.run_id
where s.metric = 'task_success'
group by r.prompt_version, c.language;

create or replace view public.worst_conversations as
select
    c.id as conversation_id,
    r.prompt_version,
    c.persona_id,
    c.language,
    round(avg(s.score)::numeric, 2) as mean_score,
    min(s.reasoning) as sample_reasoning
from public.scores s
join public.conversations c on c.id = s.conversation_id
join public.runs r on r.id = c.run_id
group by c.id, r.prompt_version, c.persona_id, c.language
order by mean_score asc, c.id
limit 5;

create or replace view public.v1_vs_v2 as
select
    s.metric,
    round(avg(s.score) filter (where r.prompt_version = 'v1')::numeric, 2) as v1_avg,
    round(avg(s.score) filter (where r.prompt_version = 'v2')::numeric, 2) as v2_avg,
    round(
        (
            avg(s.score) filter (where r.prompt_version = 'v2')
            - avg(s.score) filter (where r.prompt_version = 'v1')
        )::numeric,
        2
    ) as delta_v2_minus_v1
from public.scores s
join public.conversations c on c.id = s.conversation_id
join public.runs r on r.id = c.run_id
where r.prompt_version in ('v1', 'v2')
group by s.metric;
