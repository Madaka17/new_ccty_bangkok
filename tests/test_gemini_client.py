from types import SimpleNamespace

import pytest

from backend.core import gemini


@pytest.fixture(autouse=True)
def _fresh_cache(monkeypatch):
    # monkeypatch restores the module state after each test
    monkeypatch.setattr(gemini, "_key", None)
    monkeypatch.setattr(gemini, "_client", None)
    monkeypatch.delenv("GEMINI_API_KEY", raising=False)
    monkeypatch.delenv("GOOGLE_API_KEY", raising=False)


def _fake_genai(monkeypatch, created):
    class FakeClient:
        def __init__(self, api_key):
            self.api_key = api_key
            created.append(self)

    monkeypatch.setattr(gemini, "genai", SimpleNamespace(Client=FakeClient))


def test_no_key_returns_none(monkeypatch):
    created = []
    _fake_genai(monkeypatch, created)
    assert gemini.gemini_client() is None
    assert created == []


def test_import_failed_returns_none(monkeypatch):
    monkeypatch.setenv("GEMINI_API_KEY", "k1")
    monkeypatch.setattr(gemini, "genai", None)
    assert gemini.gemini_client() is None


def test_same_key_returns_same_client(monkeypatch):
    created = []
    _fake_genai(monkeypatch, created)
    monkeypatch.setenv("GEMINI_API_KEY", "k1")
    a = gemini.gemini_client()
    b = gemini.gemini_client()
    assert a is not None
    assert a is b
    assert len(created) == 1


def test_google_api_key_is_used_as_fallback(monkeypatch):
    created = []
    _fake_genai(monkeypatch, created)
    monkeypatch.setenv("GOOGLE_API_KEY", "g1")
    client = gemini.gemini_client()
    assert client.api_key == "g1"


def test_gemini_key_wins_over_google_key(monkeypatch):
    created = []
    _fake_genai(monkeypatch, created)
    monkeypatch.setenv("GEMINI_API_KEY", "k1")
    monkeypatch.setenv("GOOGLE_API_KEY", "g1")
    assert gemini.gemini_client().api_key == "k1"


def test_new_key_makes_new_client(monkeypatch):
    created = []
    _fake_genai(monkeypatch, created)
    monkeypatch.setenv("GEMINI_API_KEY", "k1")
    a = gemini.gemini_client()
    monkeypatch.setenv("GEMINI_API_KEY", "k2")
    b = gemini.gemini_client()
    assert a is not b
    assert b.api_key == "k2"
    assert len(created) == 2


def test_client_error_returns_none(monkeypatch):
    class BrokenClient:
        def __init__(self, api_key):
            raise RuntimeError("bad key")

    monkeypatch.setattr(gemini, "genai", SimpleNamespace(Client=BrokenClient))
    monkeypatch.setenv("GEMINI_API_KEY", "k1")
    assert gemini.gemini_client() is None
