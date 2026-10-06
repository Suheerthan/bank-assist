"""Central configuration. Values come from environment variables or a .env file."""
import os
from pathlib import Path

try:
    from dotenv import load_dotenv
    load_dotenv(Path(__file__).resolve().parent.parent / ".env")
except ImportError:  # python-dotenv is optional
    pass

BASE_DIR = Path(__file__).resolve().parent.parent
DATA_DIR = BASE_DIR / "data"
PROMPT_DIR = BASE_DIR / "prompts"

# LLM provider: "none" (rules + templates only, works offline), "gemini" or "anthropic"
LLM_PROVIDER = os.getenv("LLM_PROVIDER", "none").strip().lower()
GEMINI_API_KEY = os.getenv("GEMINI_API_KEY", "")
GEMINI_MODEL = os.getenv("GEMINI_MODEL", "gemini-3.8-flash")
ANTHROPIC_API_KEY = os.getenv("ANTHROPIC_API_KEY", "")
ANTHROPIC_MODEL = os.getenv("ANTHROPIC_MODEL", "claude-haiku-4-5-20251001")
LLM_TIMEOUT_SECONDS = float(os.getenv("LLM_TIMEOUT_SECONDS", "12"))
# Tried in order when the main Gemini model is busy (503) or unavailable
GEMINI_FALLBACK_MODELS = os.getenv("GEMINI_FALLBACK_MODELS", "gemini-3.7-flash,gemini-3.5-flash-lite")
# After every model fails, skip AI calls for this long so the console stays fast
LLM_COOLDOWN_SECONDS = float(os.getenv("LLM_COOLDOWN_SECONDS", "60"))

# Storage: MongoDB if reachable, otherwise a local JSON file
MONGO_URI = os.getenv("MONGO_URI", "mongodb://localhost:27017")
MONGO_DB = os.getenv("MONGO_DB", "bank_assist")
LOCAL_STORE = Path(os.getenv("LOCAL_STORE_PATH", str(DATA_DIR / "local_store.json")))

# Retrieval: below this normalised score the assistant says "no reliable FAQ match"
MIN_RETRIEVAL_SCORE = float(os.getenv("MIN_RETRIEVAL_SCORE", "0.18"))

BANK_NAME = "Lotus Harbour Bank"  # fictional
