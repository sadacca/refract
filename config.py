import os
from pathlib import Path
from dotenv import load_dotenv

load_dotenv()

# Paths
ROOT = Path(__file__).parent
BIAS_INDEX_DIR = ROOT / "bias_index"
DATA_DIR = ROOT / "data"
PRECOMPUTED_DIR = DATA_DIR / "precomputed"
CACHE_DIR = DATA_DIR / "cache"
PROCESSED_DIR = DATA_DIR / "processed"
INPUT_DIR = DATA_DIR / "input"
PENDING_EXAMPLES_DIR = DATA_DIR / "pending_examples"
EVAL_DIR = ROOT / "eval"

# Versions — increment framework_version whenever prompts or taxonomy change
FRAMEWORK_VERSION = "v0.1.0"
TAXONOMY_VERSION = "v0.1.0"

# Model config — tiered: small model for triage/probes, large for identification/judge
EVAL_MODEL = os.getenv("EVAL_MODEL", "llama-3.3-70b-versatile")        # Pass 2 identification
JUDGE_MODEL = os.getenv("JUDGE_MODEL", "llama-3.3-70b-versatile")       # Pass 4 judge
TRIAGE_MODEL = os.getenv("TRIAGE_MODEL", "llama-3.1-8b-instant")        # Pass 1 triage + Pass 3 recall probes

# API keys
GEMINI_API_KEY = os.getenv("GEMINI_API_KEY", "")
GUARDIAN_API_KEY = os.getenv("GUARDIAN_API_KEY", "")
GROQ_API_KEY = os.getenv("GROQ_API_KEY", "")

# Pipeline config
EVAL_MODE = os.getenv("EVAL_MODE", "deep")  # "deep" or "bulk"
RATE_LIMIT_DELAY = int(os.getenv("RATE_LIMIT_DELAY", "5"))   # seconds between articles
MAX_ARTICLE_WORDS = 10_000
BULK_MODE_TOP_K = 25  # biases to inject in Mode B embedding pre-filter

# LLM call config
MAX_RETRIES = 4
RETRY_BASE_DELAY = 2  # seconds; doubles each retry

# Pass 2 payload compression via LLMLingua-2 (T4 / TODO 6.9)
# Requires: pip install llmlingua  (downloads ~400 MB model on first use)
# rate=0.5 keeps 50% of tokens (2x compression); safe range: 0.33–0.67
COMPRESS_PASS2 = os.getenv("COMPRESS_PASS2", "false").lower() == "true"
COMPRESSION_RATE = float(os.getenv("COMPRESSION_RATE", "0.5"))
