from agent.state import AgentState, QualificationFields, Session, TurnSignals, next_state


def _session(**kwargs) -> Session:
    return Session(session_id="test", **kwargs)


def test_greet_moves_to_qualify():
    session = _session()
    state = next_state(session, TurnSignals())
    assert state == AgentState.QUALIFY


def test_qualify_stays_until_fields_complete():
    session = _session(state=AgentState.QUALIFY)
    state = next_state(session, TurnSignals(extracted=QualificationFields(name="Ravi")))
    assert state == AgentState.QUALIFY
    assert session.fields.name == "Ravi"


def test_complete_fields_move_to_close():
    session = _session(state=AgentState.QUALIFY)
    signals = TurnSignals(
        extracted=QualificationFields(
            name="Ravi",
            city="Pune",
            monthly_income="80000",
            loan_amount="300000",
            employment_type="salaried",
        )
    )
    state = next_state(session, signals)
    assert state == AgentState.CLOSE
    assert session.fields.is_complete()


def test_busy_ends_with_callback_reason():
    session = _session(state=AgentState.QUALIFY)
    state = next_state(session, TurnSignals(customer_busy=True))
    assert state == AgentState.END
    assert session.ended_reason == "busy_callback"


def test_objection_enters_handle_objection():
    session = _session(state=AgentState.QUALIFY, fields=QualificationFields(name="Neha"))
    state = next_state(session, TurnSignals(objection=True))
    assert state == AgentState.HANDLE_OBJECTION


def test_after_objection_returns_to_qualify_if_incomplete():
    session = _session(
        state=AgentState.HANDLE_OBJECTION,
        fields=QualificationFields(name="Neha", city="Delhi"),
    )
    state = next_state(session, TurnSignals())
    assert state == AgentState.QUALIFY


def test_not_interested_goes_to_close_then_end():
    session = _session(state=AgentState.QUALIFY)
    state = next_state(session, TurnSignals(not_interested=True))
    assert state == AgentState.CLOSE
    session.state = state
    state = next_state(session, TurnSignals(conversation_end=True))
    assert state == AgentState.END


def test_close_then_end():
    session = _session(
        state=AgentState.CLOSE,
        fields=QualificationFields(
            name="Asha",
            city="Jaipur",
            monthly_income="50000",
            loan_amount="200000",
            employment_type="self-employed",
        ),
    )
    state = next_state(session, TurnSignals())
    assert state == AgentState.END


def test_end_is_terminal():
    session = _session(state=AgentState.END, ended_reason="declined")
    state = next_state(session, TurnSignals(extracted=QualificationFields(name="X")))
    assert state == AgentState.END
