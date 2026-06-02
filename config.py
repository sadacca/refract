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
# from EVAL_MODEL to eliminate self-preference bias (arXiv:2404.13076). Gemini-family
# eval → Groq judge; any other eval → Gemini judge. Override with JUDGE_MODEL env var.
# Any provider model may serve as eval OR judge — role assignment is fully flexible.


def _cross_family_default(eval_model: str) -> str:
    """Return the opposite-provider judge for cross-family evaluation.
    Gemini-family eval → Groq judge; all others → Gemini judge."""
    m = eval_model.lower()
    if "/" in m:
        is_gemini = m.split("/")[0] == "gemini"
    else:
        is_gemini = m.startswith(("gemini", "gemma"))
    return "llama-3.3-70b-versatile" if is_gemini else "gemini-3.1-flash-lite"


# Short filename-safe abbreviations — used in output filenames so parallel model
# runs don't overwrite each other: {article_id}_{fw_version}_{eval}_{judge}.json
_MODEL_ABBREVS = {
    # Groq (per-model RPD: 14,400 / 30 RPM / 6K TPM)
    "deepseek-r1-distill-llama-70b":             "dsr170b",
    "llama-3.3-70b-versatile":                   "llama70b",
    "llama-3.1-70b-versatile":                   "llama70b",
    "llama-3.1-8b-instant":                      "llama8b",
    "llama-3.2-3b-preview":                      "llama3b",
    "mixtral-8x7b-32768":                        "mixtral",
    # Gemini / Google
    "gemini-2.0-flash":                          "gemflash",
    "gemini-2.0-flash-exp":                      "gemflash",
    "gemini-1.5-flash":                          "gem15flash",
    "gemini-1.5-pro":                            "gempro",
    "gemini-2.5-flash-lite":                     "gem25lite",
    "gemini-2.5-flash":                          "gem25flash",
    "gemini-2.5-pro":                            "gem25pro",
    "gemini-3.1-flash-lite":                     "gem31lite",
    "gemma-4-31b-it":                            "gemma431b",
    "gemma-4-26b-a4b-it":                        "gemma426b",
    # Cerebras (account-wide ~1,000 RPD / 1M tokens-per-day / 30 RPM)
    # gpt-oss-120b and zai-glm-4.7 have 131K context; all others capped at 8K free-tier
    "gpt-oss-120b":                              "gptoss120",
    "cerebras/gpt-oss-120b":                     "gptoss120",
    "qwen-3-235b":                               "qwn3235b",
    "cerebras/qwen-3-235b":                      "qwn3235b",
    "qwen-3-32b":                                "qwn332b",
    "cerebras/qwen-3-32b":                       "qwn332b",
    "zai-glm-4.7":                               "zaiglm47",
    "cerebras/zai-glm-4.7":                      "zaiglm47",
    "llama-4-scout-17b":                         "llm4sct17",
    "cerebras/llama-4-scout-17b":                "llm4sct17",
    "cerebras/deepseek-r1-distill-llama-70b":    "cbrdsr170b",
    "cerebras/llama-3.3-70b":                    "cbrlma70b",
    "cerebras/llama-3.1-70b":                    "cbr31l70b",
    "cerebras/llama-3.1-8b":                     "cbrlma8b",
    # Mistral (2 RPM free / 1B tokens-per-month / account-wide; ~2,880 RPD theoretical max)
    "mistral-large-latest":                      "mstrlg",
    "mistral/mistral-large-latest":              "mstrlg",
    "mistral-medium-3":                          "mstrmd3",
    "mistral/mistral-medium-3":                  "mstrmd3",
    "mistral-small-latest":                      "mistrsm4",
    "mistral-small-2603":                        "mistrsm4",
    "mistral/mistral-small-latest":              "mistrsm4",
    "mistral/mistral-small-2603":                "mistrsm4",
    "codestral-latest":                          "codstrl",
    "mistral/codestral-latest":                  "codstrl",
    "pixtral-12b":                               "pixtrl12",
    "mistral/pixtral-12b":                       "pixtrl12",
}


def model_abbrev(model: str) -> str:
    """Short filename-safe abbreviation for a model name."""
    if model in _MODEL_ABBREVS:
        return _MODEL_ABBREVS[model]
    clean = model.lower().replace(".", "").replace("-", "").replace("/", "")
    return clean[:12]


EVAL_MODEL = os.getenv("EVAL_MODEL", "deepseek-r1-distill-llama-70b")  # Pass 2 identification
_judge_env = os.getenv("JUDGE_MODEL", "")
JUDGE_MODEL = _judge_env if _judge_env else _cross_family_default(EVAL_MODEL)  # Pass 4 judge
TRIAGE_MODEL = os.getenv("TRIAGE_MODEL", "cerebras/qwen-3-32b")  # Pass 0/1/3 triage + probes

# Curated model menus for the Streamlit UI — grouped by role suitability.
# Keys are display labels, values are model IDs passed to the pipeline.
EVAL_MODEL_OPTIONS = [
    # Groq — best for Pass 2 identification (large context, strong reasoning)
    "deepseek-r1-distill-llama-70b",
    "llama-3.3-70b-versatile",
    # Cerebras — fast inference, large context
    "cerebras/gpt-oss-120b",
    "cerebras/qwen-3-235b",
    "cerebras/llama-3.3-70b",
    # Gemini — high quality, generous free tier
    "gemini-2.5-flash",
    "gemini-2.5-pro",
    "gemini-2.0-flash",
    # Mistral
    "mistral-large-latest",
    "mistral-medium-3",
]

JUDGE_MODEL_OPTIONS = [
    # Cross-family defaults first
    "gemini-2.5-flash",
    "gemini-2.0-flash",
    "gemini-2.5-pro",
    # Groq
    "llama-3.3-70b-versatile",
    "deepseek-r1-distill-llama-70b",
    # Cerebras
    "cerebras/gpt-oss-120b",
    # Mistral
    "mistral-large-latest",
]

TRIAGE_MODEL_OPTIONS = [
    # Reasoning models — better triage quality, ~1M tok/day on Cerebras free tier
    "cerebras/qwen-3-32b",
    "cerebras/deepseek-r1-distill-llama-70b",
    "gemini-2.5-flash-lite",
    # Fast small models — higher RPD ceiling, no reasoning
    "llama-3.1-8b-instant",
    "llama-3.2-3b-preview",
    "cerebras/llama-3.1-8b",
    "cerebras/llama-4-scout-17b",
    "mistral-small-latest",
    "llama-3.3-70b-versatile",
]

# API keys
GEMINI_API_KEY = os.getenv("GEMINI_API_KEY", "")
GUARDIAN_API_KEY = os.getenv("GUARDIAN_API_KEY", "")
GROQ_API_KEY = os.getenv("GROQ_API_KEY", "")
CEREBRAS_API_KEY = os.getenv("CEREBRAS_API_KEY", "")
MISTRAL_API_KEY = os.getenv("MISTRAL_API_KEY", "")

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

# ---------------------------------------------------------------------------
# Ordered Gemini judge fallback chain: (model_id, free_tier_rpd_limit).
# At runtime, select_from_chain() picks the first model below 85% of its daily
# RPD limit. On 429, evaluate_article() steps to the next model in the list.
# Tripping the free-tier RPD cap forces a billing-tier upgrade that causes 429s
# across ALL Google API models for the rest of the day — this chain prevents that.
# Gemini RPD is per-model, so chaining within Gemini provides real benefit.
# RPD limits as of 2026-06: gemini-3.1-flash-lite=500, gemma-4-*=1500.
# ---------------------------------------------------------------------------
GEMINI_JUDGE_CHAIN: list[tuple[str, int]] = [
    ("gemini-3.1-flash-lite", 500),
    ("gemma-4-31b-it",        1500),
    ("gemma-4-26b-a4b-it",   1500),
]

# ---------------------------------------------------------------------------
# Eval model fallback chain for Pass 2 identification.
# Chains cross provider boundaries only — Cerebras and Mistral have account-wide
# RPD (not per-model), so switching within those providers yields no benefit.
# Cross-provider order: Groq (highest RPD) → Cerebras → Mistral (last resort).
# Benchmark-ranked best models: DeepSeek-R1 (AIME 86.7%) → GPT-OSS-120B (~85%)
# → Mistral Large (~81%). GPT-OSS-120B chosen over Qwen3-235B despite lower
# benchmark because it has 131K context (avoids Cerebras 8K free-tier limit).
# Provider RPD reality check (as of 2026-06):
#   Groq:     30 RPM / 14,400 RPD per-model / 6K TPM  (high-volume primary)
#   Cerebras: 30 RPM / ~1,000 RPD ACCOUNT-WIDE / 1M tokens-per-day / 8K context
#             (gpt-oss-120b and zai-glm-4.7 are exceptions with 131K context)
#   Mistral:  2 RPM free "Experiment" / 1B tokens/month / no hard RPD cap
#             (2 RPM × 60 × 24 = 2,880 RPD theoretical max — slow, last resort)
# ---------------------------------------------------------------------------
EVAL_CHAIN: list[tuple[str, int]] = [
    ("deepseek-r1-distill-llama-70b", 14_400),  # Groq: 14,400 RPD per-model; AIME 86.7%
    ("cerebras/gpt-oss-120b",           500),   # Cerebras: ~1,000 RPD account-wide; 131K ctx
    ("mistral-large-latest",           2_800),  # Mistral: 2 RPM free ≈ 2,880 RPD; last resort
]

# ---------------------------------------------------------------------------
# Triage model fallback chain for Pass 0 / 1 / 3 (small-model calls).
# Cross-provider: Groq → Cerebras → Mistral. Same RPD budgeting logic as EVAL_CHAIN.
# Cerebras RPD here and in EVAL_CHAIN draw from the same account-wide pool (~500 each).
# ---------------------------------------------------------------------------
TRIAGE_CHAIN: list[tuple[str, int]] = [
    ("llama-3.1-8b-instant",     14_400),   # Groq 8B: highest per-model RPD on Groq
    ("cerebras/llama-3.1-8b",      500),    # Cerebras: fast, shares account pool with eval
    ("mistral-small-latest",      2_800),   # Mistral: overkill but available as last resort
]

# ---------------------------------------------------------------------------
# Per-model context window limits (in tokens).
# Used by llm_client to warn when estimated prompt size approaches the limit.
# Cerebras free tier is capped at 8,192 tokens for most models — the tightest
# constraint in the pipeline. Exceptions: gpt-oss-120b and zai-glm-4.7 have 131K.
# Estimates use ~4 chars/token (conservative for English).
# ---------------------------------------------------------------------------
MODEL_CONTEXT_LIMITS: dict[str, int] = {
    # Cerebras — 8,192 token hard limit on free tier for most models
    "qwen-3-32b":                              8_192,
    "cerebras/qwen-3-32b":                     8_192,
    "qwen-3-235b":                             8_192,
    "cerebras/qwen-3-235b":                    8_192,
    "cerebras/deepseek-r1-distill-llama-70b":  8_192,
    "cerebras/llama-3.3-70b":                  8_192,
    "cerebras/llama-3.1-70b":                  8_192,
    "cerebras/llama-3.1-8b":                   8_192,
    "cerebras/llama-3.1-8b-instant":           8_192,
    "llama-4-scout-17b":                       8_192,
    "cerebras/llama-4-scout-17b":              8_192,
    # Cerebras large-context exceptions (131K — free-tier exemptions)
    "gpt-oss-120b":                            131_072,
    "cerebras/gpt-oss-120b":                   131_072,
    "zai-glm-4.7":                             131_072,
    "cerebras/zai-glm-4.7":                    131_072,
    # Groq
    "deepseek-r1-distill-llama-70b":            32_000,
    "llama-3.3-70b-versatile":                128_000,
    "llama-3.1-70b-versatile":                128_000,
    "llama-3.1-8b-instant":                   128_000,
    "mixtral-8x7b-32768":                      32_768,
    # Gemini / Gemma
    "gemini-3.1-flash-lite":               1_000_000,
    "gemini-2.5-flash":                    1_000_000,
    "gemini-2.5-pro":                      1_000_000,
    "gemma-4-31b-it":                        128_000,
    "gemma-4-26b-a4b-it":                    128_000,
    # Mistral
    "mistral-large-latest":                  128_000,
    "mistral/mistral-large-latest":          128_000,
    "mistral-medium-3":                      128_000,
    "mistral/mistral-medium-3":              128_000,
    "mistral-small-latest":                  128_000,
    "mistral-small-2603":                    128_000,
    "mistral/mistral-small-latest":          128_000,
    "mistral/mistral-small-2603":            128_000,
    "codestral-latest":                       32_768,
    "mistral/codestral-latest":               32_768,
    "pixtral-12b":                           128_000,
    "mistral/pixtral-12b":                   128_000,
}

# ---------------------------------------------------------------------------
# Model registry — benchmark-ranked free-tier models per provider and role.
# Indexed by: provider → role → list of model descriptors.
# Any model may serve as eval (Pass 2) OR judge (Pass 4) — role assignment is
# flexible via EVAL_MODEL / JUDGE_MODEL env vars. Gemini can be initial classifier.
# Benchmark sources: AIME 2024/2025, MATH-500 (reasoning); MMLU (general knowledge).
# Limits verified 2026-06; re-check when adding new models.
# ---------------------------------------------------------------------------
MODEL_REGISTRY: dict[str, dict[str, list[dict]]] = {
    "groq": {
        # Per-model RPD; 6K TPM is the tighter real-world constraint on long prompts.
        "eval": [
            {
                "id": "deepseek-r1-distill-llama-70b",
                "context": 32_000, "rpm": 30, "rpd": 14_400, "tpm": 6_000,
                "benchmark": {"aime_2024": 86.7, "math_500": 94.5},
                "notes": "Best Groq reasoning; AIME 86.7%; 32K context",
            },
            {
                "id": "llama-3.3-70b-versatile",
                "context": 128_000, "rpm": 30, "rpd": 14_400, "tpm": 6_000,
                "benchmark": {"mmlu": 86.0},
                "notes": "Strong general; 128K context; fallback when 32K is tight",
            },
            {
                "id": "mixtral-8x7b-32768",
                "context": 32_768, "rpm": 30, "rpd": 14_400, "tpm": 6_000,
                "notes": "MoE architecture; 32K context; legacy option",
            },
        ],
        "triage": [
            {
                "id": "llama-3.1-8b-instant",
                "context": 128_000, "rpm": 30, "rpd": 14_400, "tpm": 6_000,
                "notes": "Fast/cheap triage; highest Groq RPD per model",
            },
        ],
    },
    "cerebras": {
        # ACCOUNT-WIDE pool: ~1,000 RPD / 1M tokens-per-day, 30 RPM.
        # Most models: 8,192 token context limit on free tier.
        # Large-context exceptions: gpt-oss-120b and zai-glm-4.7 (131K each).
        # Use explicit cerebras/ prefix to route: cerebras/gpt-oss-120b
        "eval": [
            {
                "id": "cerebras/gpt-oss-120b",
                "context": 131_072, "rpm": 30, "rpd": 1_000, "tpm": 60_000,
                "rpd_scope": "account",
                "benchmark": {"aime_2024": 85.0},
                "notes": "Best Cerebras eval; 131K context; avoids 8K free-tier limit",
            },
            {
                "id": "cerebras/qwen-3-235b",
                "context": 8_192, "rpm": 30, "rpd": 1_000, "tpm": 60_000,
                "rpd_scope": "account",
                "benchmark": {"aime_2024": 92.3},
                "notes": "Highest benchmark (AIME 92.3%); Hybrid CoT; 8K context limits long articles",
            },
            {
                "id": "cerebras/deepseek-r1-distill-llama-70b",
                "context": 8_192, "rpm": 30, "rpd": 1_000, "tpm": 60_000,
                "rpd_scope": "account",
                "benchmark": {"aime_2024": 72.6},
                "notes": "R1 reasoning; fastest 70B inference; 8K context",
            },
            {
                "id": "cerebras/zai-glm-4.7",
                "context": 131_072, "rpm": 30, "rpd": 1_000, "tpm": 60_000,
                "rpd_scope": "account",
                "notes": "131K context; GLM architecture; large-context alternative",
            },
            {
                "id": "cerebras/llama-3.1-70b",
                "context": 8_192, "rpm": 30, "rpd": 1_000, "tpm": 60_000,
                "rpd_scope": "account",
                "notes": "Llama 3.1 70B; 8K context; lower priority than R1/Qwen3",
            },
            {
                "id": "cerebras/llama-4-scout-17b",
                "context": 8_192, "rpm": 30, "rpd": 1_000, "tpm": 60_000,
                "rpd_scope": "account",
                "notes": "Llama 4 Scout 17B MoE; 8K context",
            },
            {
                "id": "cerebras/qwen-3-32b",
                "context": 8_192, "rpm": 30, "rpd": 1_000, "tpm": 60_000,
                "rpd_scope": "account",
                "notes": "Smaller Qwen 3; Hybrid CoT; ~2,400 tok/s; 8K context",
            },
        ],
        "triage": [
            {
                "id": "cerebras/llama-3.1-8b",
                "context": 8_192, "rpm": 30, "rpd": 1_000, "tpm": 60_000,
                "rpd_scope": "account",
                "notes": "Fast triage; shares account-wide pool with eval models",
            },
        ],
    },
    "mistral": {
        # Free "Experiment" tier: 2 RPM hard limit, 1B tokens/month, account-wide.
        # 2 RPM × 60 × 24 = 2,880 RPD theoretical max. Slow — last-resort fallback.
        "eval": [
            {
                "id": "mistral-large-latest",
                "context": 128_000, "rpm": 2, "rpd": 2_880, "tpm": 500_000,
                "rpd_scope": "account",
                "benchmark": {"mmlu": 81.0},
                "notes": "Best Mistral reasoning; 128K ctx; 1B tokens/month; 2 RPM free",
            },
            {
                "id": "mistral-medium-3",
                "context": 128_000, "rpm": 2, "rpd": 2_880, "tpm": 500_000,
                "rpd_scope": "account",
                "notes": "Newer mid-tier Mistral; 128K ctx; 2 RPM free",
            },
            {
                "id": "mistral-small-latest",
                "context": 128_000, "rpm": 2, "rpd": 2_880, "tpm": 500_000,
                "rpd_scope": "account",
                "notes": "Efficient; 128K ctx; good for cost-sensitive runs",
            },
            {
                "id": "pixtral-12b",
                "context": 128_000, "rpm": 2, "rpd": 2_880, "tpm": 500_000,
                "rpd_scope": "account",
                "notes": "Multimodal; 128K ctx; viable for text bias eval",
            },
            {
                "id": "codestral-latest",
                "context": 32_768, "rpm": 2, "rpd": 2_880, "tpm": 500_000,
                "rpd_scope": "account",
                "notes": "Code-focused; 32K ctx; not optimal for text bias analysis",
            },
        ],
        "triage": [
            {
                "id": "mistral-small-latest",
                "context": 128_000, "rpm": 2, "rpd": 2_880, "tpm": 500_000,
                "rpd_scope": "account",
                "notes": "Overkill for triage; available as last-resort fallback",
            },
        ],
    },
    "gemini": {
        # Per-model RPD for the Google AI free tier.
        # GEMINI_JUDGE_CHAIN handles RPD-aware selection at runtime.
        # Gemini can serve as eval (Pass 2) OR judge (Pass 4) — set EVAL_MODEL
        # to a gemini-* model; cross-family default will then switch judge to Groq.
        "judge": [
            {
                "id": "gemini-3.1-flash-lite",
                "context": 1_000_000, "rpm": 15, "rpd": 500, "tpm": 250_000,
                "notes": "Primary judge; best free RPD among Gemini flash models",
            },
            {
                "id": "gemma-4-31b-it",
                "context": 128_000, "rpm": 15, "rpd": 1_500, "tpm": 250_000,
                "notes": "Fallback judge; highest free RPD on Google AI",
            },
            {
                "id": "gemma-4-26b-a4b-it",
                "context": 128_000, "rpm": 15, "rpd": 1_500, "tpm": 250_000,
                "notes": "MoE fallback; 4B active params, efficient; 1,500 free RPD",
            },
            {
                "id": "gemini-2.5-flash",
                "context": 1_000_000, "rpm": 10, "rpd": 250, "tpm": 250_000,
                "benchmark": {"aime_2024": 88.0},
                "notes": "Higher quality (AIME 88%); lower free RPD (250/day)",
            },
            {
                "id": "gemini-2.5-pro",
                "context": 1_000_000, "rpm": 5, "rpd": 100, "tpm": 250_000,
                "notes": "Highest quality; very restrictive free RPD (100/day)",
            },
        ],
        "eval": [
            {
                "id": "gemini-2.5-flash",
                "context": 1_000_000, "rpm": 10, "rpd": 250, "tpm": 250_000,
                "benchmark": {"aime_2024": 88.0},
                "notes": "Best free Gemini eval; AIME 88%; 1M ctx; judge auto-switches to Groq",
            },
            {
                "id": "gemini-3.1-flash-lite",
                "context": 1_000_000, "rpm": 15, "rpd": 500, "tpm": 250_000,
                "notes": "Fast Gemini eval; 500 RPD; judge auto-switches to Groq when used as eval",
            },
        ],
    },
}
