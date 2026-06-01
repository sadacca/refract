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
#
# Cross-family judging (TODO 6.1): JUDGE_MODEL defaults to the opposite provider
# from EVAL_MODEL to eliminate self-preference bias (arXiv:2404.13076). Groq eval
# → Gemini judge; Gemini eval → Llama judge. Override with JUDGE_MODEL env var.
_GROQ_PREFIXES = ("llama", "mixtral", "gemma", "qwen", "deepseek")


def _is_groq_model(model: str) -> bool:
    return any(model.lower().startswith(p) for p in _GROQ_PREFIXES)


def _cross_family_default(eval_model: str) -> str:
    """Return the opposite-provider judge model for cross-family evaluation."""
    # gemini-1.5-flash preferred over 2.0-flash: same 15 RPM free tier but
    # more permissive token quota; 2.0-flash hits 429 on first call in practice.
    return "gemini-1.5-flash" if _is_groq_model(eval_model) else "llama-3.3-70b-versatile"


# Short filename-safe abbreviations — used in output filenames so parallel model
# runs don't overwrite each other: {article_id}_{fw_version}_{eval}_{judge}.json
_MODEL_ABBREVS = {
    "llama-3.3-70b-versatile": "llama70b",
    "llama-3.1-70b-versatile": "llama70b",
    "llama-3.1-8b-instant":    "llama8b",
    "llama-3.2-3b-preview":    "llama3b",
    "gemini-2.0-flash":        "gemflash",
    "gemini-2.0-flash-exp":    "gemflash",
    "gemini-1.5-flash":        "gem15flash",
    "gemini-1.5-pro":          "gempro",
    "gemini-2.5-pro":          "gem25pro",
    "mixtral-8x7b-32768":      "mixtral",
}


def model_abbrev(model: str) -> str:
    """Short filename-safe abbreviation for a model name."""
    if model in _MODEL_ABBREVS:
        return _MODEL_ABBREVS[model]
    clean = model.lower().replace(".", "").replace("-", "").replace("/", "")
    return clean[:12]


EVAL_MODEL = os.getenv("EVAL_MODEL", "llama-3.3-70b-versatile")   # Pass 2 identification
_judge_env = os.getenv("JUDGE_MODEL", "")
JUDGE_MODEL = _judge_env if _judge_env else _cross_family_default(EVAL_MODEL)  # Pass 4 judge
TRIAGE_MODEL = os.getenv("TRIAGE_MODEL", "llama-3.1-8b-instant")  # Pass 0/1/3 triage + probes

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

# Per-call pause injected after every successful LLM response.
# Applies globally across all models/providers — a cross-model pace-setter that
# the per-model _CALL_MIN_INTERVAL (in llm_client.py) does not cover.
# Default 2 s: enough to absorb token-bucket recovery without noticeably slowing
# a batch run. Set LLM_POST_CALL_DELAY=0 to disable during local testing.
POST_CALL_DELAY = float(os.getenv("LLM_POST_CALL_DELAY", "2.0"))

# Pass 2 payload compression via LLMLingua-2 (T4 / TODO 6.9)
# Requires: pip install llmlingua  (downloads ~400 MB model on first use)
# rate=0.5 keeps 50% of tokens (2x compression); safe range: 0.33–0.67
COMPRESS_PASS2 = os.getenv("COMPRESS_PASS2", "false").lower() == "true"
COMPRESSION_RATE = float(os.getenv("COMPRESSION_RATE", "0.5"))

# Pass 4 swap augmentation (T2 / TODO 6.2)
# Runs the judge twice with instance order reversed. Verdicts that flip across
# orderings are downgraded to "suspect" — if the verdict depends on where in the
# list the instance appeared, it was position-biased, not content-grounded.
# Doubles Pass 4 LLM calls; disable for cost-sensitive runs.
JUDGE_SWAP_AUGMENTATION = os.getenv("JUDGE_SWAP_AUGMENTATION", "true").lower() == "true"

# Pass 4 cross-family judge (TODO 6.1)
# Set JUDGE_MODEL env var to a Gemini model (e.g. gemini-2.0-flash) once
# GEMINI_API_KEY is configured. Eliminates self-preference bias (arXiv:2404.13076).
# Default retains current Llama judge until API key is available.
