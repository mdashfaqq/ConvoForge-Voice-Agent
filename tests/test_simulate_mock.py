from agent.chat import SalesAgent
from agent.session import SessionStore
from eval.judge import judge_transcript
from eval.mock_llm import MockLLM
from eval.simulate import load_personas, simulate_conversation


def test_mock_simulate_and_judge_one_persona():
    persona = load_personas()[0]
    llm = MockLLM("v2")
    agent = SalesAgent(store=SessionStore(), llm=llm, prompt_version="v2")
    convo = simulate_conversation(persona, agent, llm, max_turns=8)
    assert convo["transcript"]
    assert convo["transcript"][0]["role"] == "customer"
    scores = judge_transcript(convo["transcript"], llm)
    assert 1 <= scores.task_success <= 5
    assert scores.reasoning
