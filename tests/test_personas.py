from eval.simulate import load_personas


def test_thirty_personas_and_hinglish_quota():
    personas = load_personas()
    assert len(personas) == 30
    hinglish = [p for p in personas if p["language"] == "Hinglish"]
    assert len(hinglish) >= 10
    intents = {p["intent"] for p in personas}
    assert intents >= {"interested", "busy", "price-sensitive", "not-interested", "confused"}
    for persona in personas:
        facts = persona["hidden_facts"]
        assert {"name", "city", "monthly_income", "loan_amount", "employment_type"} <= set(facts)
