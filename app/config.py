import os
from pathlib import Path
from dotenv import load_dotenv

# Project root folder (the folder that contains "app/")
BASE_DIR = Path(__file__).resolve().parent.parent

# Reads the .env file and loads its values as environment variables
load_dotenv(BASE_DIR / ".env")

GEMINI_API_KEY = os.getenv("GEMINI_API_KEY")

# Confirm this exact ID in AI Studio. If it fails, see the troubleshooting table below.
MODEL_NAME = "gemini-3.6-flash"

# The drawing area we ask the model to use
VIEWBOX_WIDTH = 800
VIEWBOX_HEIGHT = 600

# Upper limit on the model's reply. Thinking tokens count toward this too,
# so keep it generous or the SVG may be cut off halfway.
MAX_OUTPUT_TOKENS = 16000


# --- SVG validation settings ---
MIN_LABELS = 3            # minimum number of <text> labels
BOUNDS_TOLERANCE = 2.0    # allowed overshoot past the viewBox, in SVG units
CHAR_WIDTH_FACTOR = 0.55  # rough text width = font-size * this * number of characters
DEFAULT_FONT_SIZE = 16.0  # used when a <text> has no font-size



# --- Standard paid-tier pricing: USD per 1 million tokens ---
# Source: https://ai.google.dev/gemini-api/docs/pricing
# Verified on: 2026-11-24
PRICES = {
    "gemini-3.5-flash-lite": {"input": 0.30, "output": 2.50},
    # Gemini 3.5 Flash is deprecated and routed to Gemini 3.6 Flash.
    "gemini-3.5-flash": {"input": 0.75, "output": 3.75},
    "gemini-3.6-flash": {"input": 0.75, "output": 3.75},
}
DEFAULT_PRICE = PRICES["gemini-3.6-flash"]

# --- Retry settings ---
MAX_API_RETRIES = 3          # extra tries after a 429/503 (so up to 4 calls in total)
MAX_VALIDATION_RETRIES = 1   # the brief says: retry once

# "batch" is for scripts that can afford to wait. "live" is for the Generate button,
# where a person is staring at a spinner, so we wait less and give up sooner.
RETRY_PROFILES = {
    "batch": {"delays": [15, 30, 60], "max_wait": 70},
    "live": {"delays": [3, 6, 12], "max_wait": 20},
}


# --- Files and batch generation ---
RESULTS_FILE = BASE_DIR / "data" / "results.json"
DELAY_BETWEEN_CONCEPTS = 8   # seconds to pause between concepts (free-tier limits are low)


# --- Live Generate button protection ---
GENERATE_COOLDOWN_SECONDS = 10   # minimum gap between live generations (protects the free quota)