import json
import logging
import math
import threading
import time

from fastapi import FastAPI, HTTPException
from fastapi.responses import FileResponse, JSONResponse
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel

from app import config
from app.concepts import CONCEPTS
from app.services.orchestrator import GenerationError, generate_diagram

log = logging.getLogger("diagram")

app = FastAPI(title="Science Diagram Maker")

STATIC_DIR = config.BASE_DIR / "static"
app.mount("/static", StaticFiles(directory=STATIC_DIR), name="static")

# Only one live generation at a time, with a pause between them
_generate_lock = threading.Lock()
_last_finished = None  # time.monotonic() value when the last generation ended


class GenerateRequest(BaseModel):
    concept_id: str


def error_response(status, message, headers=None):
    """Every error is JSON like {"error": "..."} so the web page can show it."""
    return JSONResponse(status_code=status, content={"error": message}, headers=headers)


@app.get("/")
def home():
    return FileResponse(STATIC_DIR / "index.html")


@app.get("/health")
def health():
    return {"status": "healthy"}


@app.get("/api/results")
def get_results():
    """The saved results. Reads a file only, so it never calls Gemini."""
    try:
        text = config.RESULTS_FILE.read_text(encoding="utf-8")
        return {"results": json.loads(text)}
    except FileNotFoundError:
        return {"results": []}
    except json.JSONDecodeError:
        raise HTTPException(status_code=500, detail="results.json is not valid JSON")


@app.post("/api/generate")
def generate(request: GenerateRequest):
    """Run the whole pipeline live for one concept."""
    global _last_finished

    if request.concept_id not in CONCEPTS:
        return error_response(404, f"Unknown concept id: {request.concept_id!r}")

    # Don't wait for the lock. If someone else is generating, say so immediately.
    if not _generate_lock.acquire(blocking=False):
        return error_response(
            429, "Another diagram is being generated right now. Please wait for it to finish."
        )
    try:
        if _last_finished is not None:
            wait = config.GENERATE_COOLDOWN_SECONDS - (time.monotonic() - _last_finished)
            if wait > 0:
                seconds = math.ceil(wait)
                return error_response(
                    429,
                    f"Please wait {seconds} more second(s) before generating again. "
                    "This protects the free API quota.",
                    headers={"Retry-After": str(seconds)},
                )
        try:
            return generate_diagram(request.concept_id, profile="live")
        except GenerationError as error:
            status = error.status_code if error.status_code in (429, 503) else 502
            return error_response(status, error.message)
        except Exception:
            log.exception("Unexpected error while generating")
            return error_response(
                500, "Something went wrong on the server while generating. Please try again."
            )
        finally:
            _last_finished = time.monotonic()
    finally:
        _generate_lock.release()