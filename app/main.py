import json

from fastapi import FastAPI, HTTPException
from fastapi.responses import FileResponse
from fastapi.staticfiles import StaticFiles

from app import config

app = FastAPI(title="Science Diagram Maker")

STATIC_DIR = config.BASE_DIR / "static"
app.mount("/static", StaticFiles(directory=STATIC_DIR), name="static")


@app.get("/")
def home():
    """The dashboard page."""
    return FileResponse(STATIC_DIR / "index.html")


@app.get("/health")
def health():
    """Handy for checking that the deployed server is awake."""
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