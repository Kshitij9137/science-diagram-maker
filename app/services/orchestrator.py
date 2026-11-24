"""Coordinates one diagram: prompt -> Gemini -> checks -> (one retry) -> result."""
import logging
import random
import re
import time
from datetime import datetime, timezone

from app import config
from app.concepts import CONCEPTS
from app.services import gemini_client
from app.services.cost_tracker import estimate_cost
from app.services.svg_validator import all_passed, failure_messages, validate_svg

log = logging.getLogger("diagram")

RETRYABLE_CODES = {429, 503}


class GenerationError(Exception):
    """Raised when Gemini could not give us anything usable.

    .message is safe to show to a user on the web page.
    """

    def __init__(self, message, status_code=None, api_retries=0):
        super().__init__(message)
        self.message = message
        self.status_code = status_code
        self.api_retries = api_retries



# ------------------------------------------------------------ error helpers
def get_status_code(error):
    """Pull an HTTP-style code (429, 503...) out of an exception, or None."""
    for name in ("code", "status_code"):
        value = getattr(error, name, None)
        if isinstance(value, int):
            return value
    return None


def suggested_delay(error):
    """If Gemini says how long to wait ('retryDelay': '34s'), return seconds, else 0."""
    match = re.search(
        r"(?:retry\w*delay\W+|retry in\s+)(\d+(?:\.\d+)?)\s*s", str(error), re.I
    )
    return float(match.group(1)) if match else 0.0


def friendly_message(code, error):
    if code in (400, 401, 403) and "api key" in str(error).lower():
        return "Gemini rejected the API key. Check GEMINI_API_KEY."
    messages = {
        # ... the rest stays exactly as it was
        429: "Gemini's rate limit was reached. Free-tier limits are low, so please wait a minute and try again.",
        503: "Gemini is overloaded right now. Please try again shortly.",
        401: "Gemini rejected the API key. Check GEMINI_API_KEY.",
        403: "Gemini rejected the API key or this model is not allowed for it. Check GEMINI_API_KEY.",
        404: f"Model '{config.MODEL_NAME}' was not found. Check MODEL_NAME in config.py.",
        400: "Gemini rejected the request as invalid.",
    }
    if code in messages:
        return messages[code]
    return f"Gemini request failed ({type(error).__name__}): {str(error)[:200]}"


# --------------------------------------------------------------- API retry
def call_with_api_retry(call_model, prompt, profile, sleep):
    """Call the model. On 429/503 wait and retry, up to MAX_API_RETRIES times.

    Returns (reply, number_of_retries_used). Any other error stops immediately.
    """
    settings = config.RETRY_PROFILES[profile]
    delays = settings["delays"]
    retries = 0

    while True:
        try:
            return call_model(prompt), retries
        except Exception as error:
            code = get_status_code(error)
            retryable = code in RETRYABLE_CODES
            if not retryable or retries >= config.MAX_API_RETRIES:
                raise GenerationError(
                    friendly_message(code, error), code, api_retries=retries
                ) from error

            base = delays[min(retries, len(delays) - 1)]
            wait = min(max(base, suggested_delay(error)), settings["max_wait"])
            wait += random.uniform(0, 1)  # small random extra so retries don't all line up
            log.warning(
                "Gemini error %s. Waiting %.1fs, then API retry %d of %d",
                code, wait, retries + 1, config.MAX_API_RETRIES,
            )
            sleep(wait)
            retries += 1


# ------------------------------------------------------------- one attempt
def _run_attempt(call_model, prompt, profile, sleep, kind):
    """One model call plus the five checks. Returns a dictionary describing it."""
    reply, api_retries = call_with_api_retry(call_model, prompt, profile, sleep)

    text = reply["text"]
    problem = None
    try:
        svg = gemini_client.extract_svg(text)
        svg_ok = True
    except ValueError as error:
        svg, svg_ok = text, False
        problem = str(error)
        if "MAX_TOKENS" in str(reply.get("finish_reason")):
            problem += " (the reply was cut off: MAX_TOKENS)"

    checks = validate_svg(svg)
    if problem:
        checks["valid_xml"] = {"passed": False, "reason": problem}

    return {
        "kind": kind,
        "svg": svg,            # the SVG, or the raw reply text if no SVG was found
        "svg_ok": svg_ok,
        "checks": checks,
        "error": None,
        "api_retries": api_retries,
        "model": reply.get("model"),
        "input_tokens": reply.get("input_tokens", 0),
        "output_tokens": reply.get("output_tokens", 0),
        "thought_tokens": reply.get("thought_tokens", 0),
        "finish_reason": reply.get("finish_reason"),
    }


def _failed_attempt(kind, error):
    """Record an attempt that died from an API error (no SVG, no tokens)."""
    return {
        "kind": kind, "svg": "", "svg_ok": False, "checks": None,
        "error": error.message, "api_retries": error.api_retries,
        "model": None, "input_tokens": 0, "output_tokens": 0,
        "thought_tokens": 0, "finish_reason": None,
    }


# ------------------------------------------------------------- main entry
def generate_diagram(concept_id, call_model=None, sleep=time.sleep, profile="batch"):
    """Generate, check and (if needed) correct one diagram. Returns a result dict.

    call_model: function(prompt) -> dict. Defaults to the real Gemini call.
    sleep:      function(seconds). Tests pass a fake so they don't actually wait.
    profile:    "batch" (patient) or "live" (for the web page).
    Raises GenerationError if the FIRST call fails completely.
    """
    if concept_id not in CONCEPTS:
        raise ValueError(f"Unknown concept id: {concept_id!r}")
    call_model = call_model or gemini_client.call_gemini

    concept = CONCEPTS[concept_id]
    prompt = gemini_client.build_prompt(concept)
    log.info("[%s] Generating: %s", concept_id, concept["name"])

    attempts = [_run_attempt(call_model, prompt, profile, sleep, "initial")]
    validation_retries = 0

    # The validation retry: only if checks failed, and only MAX_VALIDATION_RETRIES times
    while (
        not all_passed(attempts[-1]["checks"])
        and validation_retries < config.MAX_VALIDATION_RETRIES
    ):
        validation_retries += 1
        failures = failure_messages(attempts[-1]["checks"])
        log.info("[%s] Checks failed: %s", concept_id, " | ".join(failures))
        correction = gemini_client.build_correction_prompt(
            concept, attempts[-1]["svg"], failures
        )
        try:
            attempts.append(
                _run_attempt(call_model, correction, profile, sleep, "correction")
            )
        except GenerationError as error:
            # Keep attempt 1 instead of losing it. We save what we have, honestly.
            log.warning("[%s] Correction attempt failed: %s", concept_id, error.message)
            attempts.append(_failed_attempt("correction", error))
            break

    # Choose the final attempt: the last one that produced checks. If that one had no
    # SVG at all but an earlier one did, keep the earlier SVG.
    scored = [a for a in attempts if a["checks"] is not None]
    final = scored[-1]
    if not final["svg_ok"]:
        for earlier in reversed(scored):
            if earlier["svg_ok"]:
                final = earlier
                break

    # Totals across ALL attempts, including the failed first one
    total_input = sum(a["input_tokens"] for a in attempts)
    total_output = sum(a["output_tokens"] for a in attempts)
    total_thoughts = sum(a["thought_tokens"] for a in attempts)
    api_retries = sum(a["api_retries"] for a in attempts)
    passed = all_passed(final["checks"])

    result = {
        "concept_id": concept_id,
        "concept_name": concept["name"],
        "subject": concept["subject"],
        "model": final["model"] or scored[0]["model"] or config.MODEL_NAME,
        "svg": final["svg"] if final["svg_ok"] else "",
        "status": "passed" if passed else "failed",
        "checks": final["checks"],
        "tokens": {
            "input": total_input,
            "output": total_output,
            "thoughts": total_thoughts,
            "billed_output": total_output + total_thoughts,
        },
        "cost_usd": estimate_cost(total_input, total_output, total_thoughts),
        "pricing": {
            "input_per_million": config.PRICE_INPUT_PER_M,
            "output_per_million": config.PRICE_OUTPUT_PER_M,
            "note": "Estimated paid-tier equivalent. The free tier charges $0.",
        },
        "retries": {
            "api": api_retries,
            "validation": validation_retries,
            "total": api_retries + validation_retries,
        },
        "attempts": [
            {
                "attempt": number,
                "kind": a["kind"],
                "api_retries": a["api_retries"],
                "input_tokens": a["input_tokens"],
                "output_tokens": a["output_tokens"],
                "thought_tokens": a["thought_tokens"],
                "finish_reason": a["finish_reason"],
                "error": a["error"],
                "failures": failure_messages(a["checks"]) if a["checks"] else [],
            }
            for number, a in enumerate(attempts, start=1)
        ],
        "generated_at": datetime.now(timezone.utc).isoformat(timespec="seconds"),
    }

    log.info(
        "[%s] %s | tokens in=%d out=%d thoughts=%d | cost $%.6f | retries api=%d validation=%d",
        concept_id, result["status"].upper(), total_input, total_output,
        total_thoughts, result["cost_usd"], api_retries, validation_retries,
    )
    return result