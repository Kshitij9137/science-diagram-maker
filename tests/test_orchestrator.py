import pytest

from app import config
from app.services import orchestrator
from app.services.orchestrator import GenerationError, generate_diagram

GOOD = """<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 800 600">
<title>T</title><style>@keyframes p{from{opacity:.4}to{opacity:1}}.d{animation:p 1s infinite}</style>
<circle class="d" cx="400" cy="300" r="50"/>
<text x="100" y="100" font-size="16">A</text><text x="100" y="150" font-size="16">B</text>
<text x="100" y="200" font-size="16">C</text></svg>"""
BAD = GOOD.replace('cx="400"', 'cx="900"')          # circle outside the viewBox
NO_SVG = "Sorry, I cannot draw that."


class ApiError(Exception):
    def __init__(self, code):
        super().__init__(f"error {code}")
        self.code = code


class RemoteProtocolError(Exception):
    pass


def reply(text, inp=100, out=1000, thoughts=0):
    return {"text": text, "model": config.MODEL_NAME, "input_tokens": inp,
            "output_tokens": out, "thought_tokens": thoughts, "finish_reason": "STOP"}


class Fake:
    """Returns/raises the scripted items one by one and remembers the prompts."""
    def __init__(self, *script):
        self.script, self.prompts = list(script), []

    def __call__(self, prompt):
        self.prompts.append(prompt)
        item = self.script.pop(0)
        if isinstance(item, Exception):
            raise item
        return item


def run(fake, sleeps=None):
    sleeps = [] if sleeps is None else sleeps
    return generate_diagram("1", call_model=fake, sleep=sleeps.append)


def test_first_try_pass_has_no_retries():
    r = run(Fake(reply(GOOD)))
    assert r["status"] == "passed"
    assert r["retries"] == {"api": 0, "validation": 0, "total": 0}


def test_validation_retry_sends_failed_svg_and_reason():
    fake = Fake(reply(BAD), reply(GOOD))
    r = run(fake)
    assert r["status"] == "passed"
    assert r["retries"]["validation"] == 1
    assert "viewbox_bounds" in fake.prompts[1] and 'cx="900"' in fake.prompts[1]


def test_only_one_validation_retry():
    fake = Fake(reply(BAD), reply(BAD))
    r = run(fake)
    assert r["status"] == "failed"
    assert r["retries"]["validation"] == 1
    assert len(fake.prompts) == 2


def test_no_svg_in_reply_is_a_failed_check_not_a_crash():
    r = run(Fake(reply(NO_SVG), reply(GOOD)))
    assert r["status"] == "passed" and r["retries"]["validation"] == 1


@pytest.mark.parametrize("code", [429, 503])
def test_api_retry_then_success(code):
    sleeps = []
    r = run(Fake(ApiError(code), reply(GOOD)), sleeps)
    assert r["retries"]["api"] == 1 and len(sleeps) == 1


def test_remote_disconnect_is_retried():
    sleeps = []
    r = run(Fake(RemoteProtocolError("server disconnected"), reply(GOOD)), sleeps)
    assert r["retries"]["api"] == 1 and len(sleeps) == 1


def test_api_retry_gives_up_after_three():
    sleeps = []
    with pytest.raises(GenerationError) as info:
        run(Fake(*[ApiError(429)] * 4), sleeps)
    assert len(sleeps) == config.MAX_API_RETRIES == 3
    assert info.value.status_code == 429


def test_other_errors_are_not_retried():
    sleeps = []
    with pytest.raises(GenerationError):
        run(Fake(ApiError(401)), sleeps)
    assert sleeps == []


def test_tokens_and_cost_are_summed_over_all_attempts():
    r = run(Fake(reply(BAD, 100, 1000, 500), reply(GOOD, 200, 2000, 0)))
    assert r["tokens"] == {"input": 300, "output": 3000, "thoughts": 500, "billed_output": 3500}
    p = config.PRICES[config.MODEL_NAME]
    expected = 300 / 1e6 * p["input"] + 3500 / 1e6 * p["output"]
    assert r["cost_usd"] == pytest.approx(expected, abs=1e-6)


def test_failed_correction_call_keeps_the_first_attempt():
    r = run(Fake(reply(BAD), ApiError(503), ApiError(503), ApiError(503), ApiError(503)))
    assert r["status"] == "failed" and r["svg"]          # first SVG kept, honestly marked failed
    assert r["attempts"][-1]["error"]


def test_result_has_the_fields_the_page_needs():
    r = run(Fake(reply(GOOD)))
    for k in ("concept_id", "concept_name", "model", "svg", "status", "checks",
              "tokens", "cost_usd", "retries", "attempts"):
        assert k in r
    assert len(r["checks"]) == 5