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