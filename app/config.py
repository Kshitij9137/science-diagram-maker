import os
from pathlib import Path
from dotenv import load_dotenv

# Project root folder (the folder that contains "app/")
BASE_DIR = Path(__file__).resolve().parent.parent

# Reads the .env file and loads its values as environment variables
load_dotenv(BASE_DIR / ".env")

GEMINI_API_KEY = os.getenv("GEMINI_API_KEY")

# Confirm this exact ID in AI Studio. If it fails, see the troubleshooting table below.
MODEL_NAME = "gemini-3.5-flash-lite"

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



# --- Pricing: USD per 1 million tokens ---
# TODO: open https://ai.google.dev/gemini-api/docs/pricing, find your model, and
# confirm these two numbers. Then write today's date in the comment below.
# Verified on: ____
PRICE_INPUT_PER_M = 0.30
PRICE_OUTPUT_PER_M = 2.50   # Gemini bills thinking tokens at the output price

# --- Retry settings ---
MAX_API_RETRIES = 3          # extra tries after a 429/503 (so up to 4 calls in total)
MAX_VALIDATION_RETRIES = 1   # the brief says: retry once

# "batch" is for scripts that can afford to wait. "live" is for the Generate button,
# where a person is staring at a spinner, so we wait less and give up sooner.
RETRY_PROFILES = {
    "batch": {"delays": [15, 30, 60], "max_wait": 70},
    "live": {"delays": [3, 6, 12], "max_wait": 20},
}