from eval.judge import JudgeScores


class _Result:
    def __init__(self, data):
        self.data = data


class FakeTable:
    def __init__(self, store, name):
        self.store = store
        self.name = name
        self._op = None
        self._payload = None

    def insert(self, payload):
        self._op = "insert"
        self._payload = payload
        return self

    def select(self, _cols="*"):
        self._op = "select"
        return self

    def execute(self):
        if self._op == "insert":
            rows = self._payload if isinstance(self._payload, list) else [self._payload]
            created = []
            for row in rows:
                item = dict(row)
                item["id"] = self.store["seq"]
                self.store["seq"] += 1
                self.store[self.name].append(item)
                created.append(item)
            return _Result(created)
        return _Result(list(self.store.get(self.name, [])))


class FakeClient:
    def __init__(self):
        self.store = {
            "seq": 1,
            "runs": [],
            "conversations": [],
            "scores": [],
            "v1_vs_v2": [{"metric": "tone", "v1_avg": 4, "v2_avg": 5, "delta_v2_minus_v1": 1}],
        }

    def table(self, name):
        return FakeTable(self.store, name)


def test_persist_run_writes_nested_rows():
    from db.store import persist_run

    scores = JudgeScores(
        task_success=4,
        script_adherence=4,
        tone=5,
        objection_handling=3,
        hallucination=5,
        reasoning="ok",
    )
    client = FakeClient()
    run = persist_run(
        "v1",
        [{"persona_id": "p01", "language": "English", "transcript": [{"role": "agent", "content": "Hi"}]}],
        {"p01": scores},
        client=client,
    )
    assert run.id == 1
    assert client.store["runs"][0]["prompt_version"] == "v1"
    assert client.store["conversations"][0]["persona_id"] == "p01"
    assert len(client.store["scores"]) == 5
