"""Size-capped JSON bodies read from the stream (chunked uploads have no content-length), and the chat
text that reaches the paid model stays bounded."""
import json

from fastapi import FastAPI, Request
from fastapi.testclient import TestClient

from backend.agents import chat_service
from backend.core import access_guard


def _chunks(data, size=64):
    def gen():
        for i in range(0, len(data), size):
            yield data[i:i + size]
    return gen()


def _app():
    app = FastAPI()

    @app.post("/echo")
    async def echo(request: Request):
        return await access_guard.read_json_body(request, 100, "too big", "not json")

    return app


def test_chunked_body_over_limit_is_413():
    client = TestClient(_app())
    r = client.post("/echo", content=_chunks(b"x" * 500))
    assert r.status_code == 413
    assert r.json()["detail"] == "too big"


def test_chunked_small_object_is_read():
    client = TestClient(_app())
    body = json.dumps({"a": "b" * 20, "n": 1}).encode()
    assert len(body) < 100
    r = client.post("/echo", content=_chunks(body, size=7))
    assert r.status_code == 200
    assert r.json() == {"a": "b" * 20, "n": 1}


def test_invalid_json_is_400():
    client = TestClient(_app())
    r = client.post("/echo", content=_chunks(b"{not json"))
    assert r.status_code == 400
    assert r.json()["detail"] == "not json"


def test_json_list_is_400():
    client = TestClient(_app())
    r = client.post("/echo", content=_chunks(b"[1, 2, 3]"))
    assert r.status_code == 400
    assert r.json()["detail"] == "not json"


class _FakeLLM:
    model = "test-model"

    def __init__(self):
        self.prompts = []

    def enabled(self):
        return True

    def token_budget(self, *texts, reply_tokens=0):
        return 1_000_000

    def chat(self, prompt, max_tokens=0, temperature=0.4, **kwargs):
        self.prompts.append(prompt)
        return "ok"


def test_chat_truncates_long_question_and_history(monkeypatch):
    fake = _FakeLLM()
    monkeypatch.setattr(chat_service, "llm", fake)
    monkeypatch.setattr(chat_service, "build_context", lambda *a, **k: "")
    monkeypatch.setattr(chat_service, "answer_style", lambda *a, **k: "")
    long_text = "ก" * 50000
    messages = [{"role": "user", "content": long_text}, {"role": "assistant", "content": "x"}]
    out = chat_service.chat(None, messages, {}, None, {})
    assert out["reply"] == "ok"
    prompt = fake.prompts[-1]
    for m in prompt[1:-1]:                       # history turns (the system prompt is fixed text)
        assert len(m["content"]) <= chat_service.HISTORY_CHARS
    turn = prompt[-1]["content"]
    question = turn.split("คำถาม: ", 1)[1]
    assert len(question) <= chat_service.HISTORY_CHARS
    assert question == "ก" * len(question)
