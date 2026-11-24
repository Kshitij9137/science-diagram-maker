import pytest
from fastapi.testclient import TestClient

from app import config, main
from app.services.orchestrator import GenerationError

client = TestClient(main.app)


@pytest.fixture(autouse=True)
def reset_protection(monkeypatch):
    """Each test starts with no cooldown and no previous generation."""
    monkeypatch.setattr(config, "GENERATE_COOLDOWN_SECONDS", 0)
    monkeypatch.setattr(main, "_last_finished", None)


def post(concept_id="1"):
    return client.post("/api/generate", json={"concept_id": concept_id})


def test_success_returns_the_result(monkeypatch):
    monkeypatch.setattr(main, "generate_diagram",
                        lambda cid, profile: {"concept_id": cid, "status": "passed"})
    response = post("2")
    assert response.status_code == 200
    assert response.json() == {"concept_id": "2", "status": "passed"}


def test_unknown_concept_is_404():
    response = post("99")
    assert response.status_code == 404
    assert "Unknown concept" in response.json()["error"]


def test_missing_body_is_rejected():
    assert client.post("/api/generate", json={}).status_code == 422


def test_gemini_rate_limit_becomes_429_with_clear_message(monkeypatch):
    def fail(cid, profile):
        raise GenerationError("Gemini's rate limit was reached. Please wait.", 429)
    monkeypatch.setattr(main, "generate_diagram", fail)
    response = post()
    assert response.status_code == 429
    assert "rate limit" in response.json()["error"]


def test_other_gemini_errors_become_502(monkeypatch):
    def fail(cid, profile):
        raise GenerationError("Gemini rejected the API key.", 401)
    monkeypatch.setattr(main, "generate_diagram", fail)
    response = post()
    assert response.status_code == 502
    assert "API key" in response.json()["error"]


def test_unexpected_crash_returns_generic_message(monkeypatch):
    def boom(cid, profile):
        raise RuntimeError("secret internal detail")
    monkeypatch.setattr(main, "generate_diagram", boom)
    response = post()
    assert response.status_code == 500
    assert "secret internal detail" not in response.text


def test_second_request_while_busy_is_refused():
    main._generate_lock.acquire()
    try:
        response = post()
    finally:
        main._generate_lock.release()
    assert response.status_code == 429
    assert "Another diagram" in response.json()["error"]


def test_cooldown_blocks_a_quick_second_request(monkeypatch):
    monkeypatch.setattr(config, "GENERATE_COOLDOWN_SECONDS", 60)
    monkeypatch.setattr(main, "generate_diagram", lambda cid, profile: {"ok": True})
    assert post().status_code == 200
    second = post()
    assert second.status_code == 429
    assert "wait" in second.json()["error"].lower()
    assert "Retry-After" in second.headers