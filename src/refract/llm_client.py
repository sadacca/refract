"""
Thin LLM client: structured JSON calls via REST APIs.
Supports Groq (primary) and Gemini (fallback/judge).
Provider is inferred from the model name prefix.
"""
import datetime
import json
import logging
import os
import time
from typing import Any

import requests

from config import (
    GEMINI_API_KEY, GROQ_API_KEY, CEREBRAS_API_KEY, MISTRAL_API_KEY,
    MAX_RETRIES, RETRY_BASE_DELAY, POST_CALL_DELAY, CACHE_DIR,
    MODEL_CONTEXT_LIMITS,
)

logger = logging.getLogger(__name__)

GEMINI_BASE = "https://generativelanguage.googleapis.com/v1beta/models"
GROQ_BASE = "https://api.groq.com/openai/v1/chat/completions"
CEREBRAS_BASE = "https://api.cerebras.ai/v1/chat/completions"
MISTRAL_BASE = "https://api.mistral.ai/v1/chat/completions"

# Minimum seconds between calls, tracked per model to avoid cross-model interference.
# Groq free: 30 RPM / model. TPM limits (not just RPM) cause most 429s on long articles.
# 6s per call = ~10 RPM, leaving headroom for token bursts.
_CALL_MIN_INTERVAL = float(os.getenv("LLM_CALL_INTERVAL", "6"))
_last_call_time: dict[str, float] = {}

# ---------------------------------------------------------------------------
# Daily call tracking — prevents tripping Google's free-tier RPD limit, which
# upgrades the project to a paid tier and causes 429s across ALL models.
# Stored in data/cache/llm_daily_usage.json; auto-resets each calendar day.
# ---------------------------------------------------------------------------
_USAGE_FILE = CACHE_DIR / "llm_daily_usage.json"


def _today() -> str:
    return datetime.date.today().isoformat()


def _load_daily_usage() -> dict:
    try:
        if _USAGE_FILE.exists():
            data = json.loads(_USAGE_FILE.read_text())
            today = _today()
            return {today: data.get(today, {})}
    except Exception:
        pass
    return {}


def _save_daily_usage(data: dict) -> None:
    CACHE_DIR.mkdir(parents=True, exist_ok=True)
    _USAGE_FILE.write_text(json.dumps(data, indent=2))


def _increment_daily_calls(model: str) -> None:
    today = _today()
    data = _load_daily_usage()
    day = data.get(today, {})
    day[model] = day.get(model, 0) + 1
    _save_daily_usage({today: day})


def get_daily_calls(model: str) -> int:
    """Return successful LLM calls made today for this model."""
    return _load_daily_usage().get(_today(), {}).get(model, 0)


def _is_near_daily_limit(model: str, rpd_limit: int, soft_pct: float = 0.85) -> bool:
    calls = get_daily_calls(model)
    soft = int(rpd_limit * soft_pct)
    if calls >= soft:
        logger.info("Daily usage: %s at %d calls (soft limit %d/%d RPD)", model, calls, soft, rpd_limit)
        return True
    return False


def select_from_chain(model_chain: list[tuple[str, int]]) -> str:
    """
    Return the first model in the chain below its daily RPD soft limit (85%).
    Logs which models are skipped. Falls back to the last model if all are near limit.
    """
    for model, rpd in model_chain:
        calls = get_daily_calls(model)
        soft = int(rpd * 0.85)
        if calls < soft:
            logger.debug("Chain: selected %s (%d/%d calls today)", model, calls, rpd)
            return model
        logger.info("Chain: skipping %s (%d calls >= soft limit %d/%d RPD)", model, calls, soft, rpd)
    fallback = model_chain[-1][0]
    logger.warning("All chain models near daily RPD limit — forcing %s", fallback)
    return fallback


# Conservative chars-per-token for English text; used only for limit estimates.
_CHARS_PER_TOKEN = 4


def _check_context_limit(prompt: str, system: str, model: str) -> None:
    """
    Warn when estimated token count approaches or exceeds a model's context limit.
    Cerebras free tier: 8 192 tokens — warn at 80%, error-log at 100%.
    Estimates are rough (~4 chars/token); actual tokenisation may differ.
    """
    bare = _bare_model(model)
    limit = MODEL_CONTEXT_LIMITS.get(model) or MODEL_CONTEXT_LIMITS.get(bare)
    if not limit:
        return
    est = int((len(prompt) + len(system)) / _CHARS_PER_TOKEN)
    pct = 100 * est / limit
    if est >= limit:
        logger.error(
            "Context limit EXCEEDED for %s: ~%d estimated tokens (%.0f%% of %d) — "
            "prompt=%d chars, system=%d chars. Call will likely fail.",
            model, est, pct, limit, len(prompt), len(system),
        )
    elif pct >= 80:
        logger.warning(
            "Context limit WARNING for %s: ~%d tokens estimated (%.0f%% of %d limit). "
            "Consider truncating the prompt.",
            model, est, pct, limit,
        )


def provider_for(model: str) -> str:
    """Return 'groq', 'gemini', 'cerebras', or 'mistral' for a given model name."""
    return _provider(model)


def _bare_model(model: str) -> str:
    """Strip 'provider/' prefix for the actual API call."""
    return model.split("/", 1)[1] if "/" in model else model


def _provider(model: str) -> str:
    """
    Infer API provider from model name.
    Supports explicit 'provider/model' routing (e.g. 'cerebras/qwen-3-32b')
    to disambiguate model IDs that exist on multiple providers.
    """
    if "/" in model:
        prefix = model.split("/", 1)[0].lower()
        if prefix in ("groq", "gemini", "cerebras", "mistral"):
            return prefix
    if model.startswith("gemma-4"):
        return "gemini"       # Gemma 4 via Google AI
    if model.startswith(("qwen-3", "gpt-oss", "zai")):
        return "cerebras"     # Qwen 3 / GPT-OSS / ZAI-GLM on Cerebras
    if model.startswith(("llama", "mixtral", "gemma", "qwen", "deepseek")):
        return "groq"
    if model.startswith("mistral"):
        return "mistral"
    return "gemini"


def _call_groq(prompt: str, model: str, system: str = "", expect_json: bool = True, temperature: float = 0.0) -> dict | str:
    return _call_openai_compat(prompt, model, system, expect_json, temperature, GROQ_BASE, GROQ_API_KEY, "groq")


def _call_gemini(prompt: str, model: str, system: str = "", expect_json: bool = True, temperature: float = 0.0) -> dict | str:
    if not GEMINI_API_KEY:
        raise RuntimeError("GEMINI_API_KEY not set")

    contents = []
    if system:
        contents.append({"role": "user", "parts": [{"text": system}]})
        contents.append({"role": "model", "parts": [{"text": "Understood."}]})
    contents.append({"role": "user", "parts": [{"text": prompt}]})

    body: dict[str, Any] = {
        "contents": contents,
        "generationConfig": {"temperature": temperature},
    }
    if expect_json:
        body["generationConfig"]["responseMimeType"] = "application/json"

    url = f"{GEMINI_BASE}/{model}:generateContent?key={GEMINI_API_KEY}"
    resp = requests.post(url, json=body, timeout=120)
    resp.raise_for_status()

    raw = resp.json()["candidates"][0]["content"]["parts"][0]["text"].strip()
    if expect_json:
        if raw.startswith("```"):
            raw = raw.split("```")[1]
            if raw.startswith("json"):
                raw = raw[4:]
        return json.loads(raw)
    return raw


def _call_openai_compat(
    prompt: str, model: str, system: str, expect_json: bool, temperature: float,
    base_url: str, api_key: str, provider_name: str,
) -> dict | str:
    """Shared caller for OpenAI-compatible endpoints (Groq, Cerebras, Mistral)."""
    if not api_key:
        raise RuntimeError(f"{provider_name.upper()}_API_KEY not set")

    messages = []
    if system:
        messages.append({"role": "system", "content": system})
    messages.append({"role": "user", "content": prompt})

    body: dict[str, Any] = {
        "model": _bare_model(model),
        "messages": messages,
        "temperature": temperature,
    }
    if expect_json:
        body["response_format"] = {"type": "json_object"}

    resp = requests.post(
        base_url,
        json=body,
        headers={"Authorization": f"Bearer {api_key}"},
        timeout=120,
    )
    resp.raise_for_status()
    raw = resp.json()["choices"][0]["message"]["content"].strip()

    if expect_json:
        if raw.startswith("```"):
            raw = raw.split("```")[1]
            if raw.startswith("json"):
                raw = raw[4:]
        return json.loads(raw)
    return raw


def _call_cerebras(prompt: str, model: str, system: str = "", expect_json: bool = True, temperature: float = 0.0) -> dict | str:
    return _call_openai_compat(prompt, model, system, expect_json, temperature, CEREBRAS_BASE, CEREBRAS_API_KEY, "cerebras")


def _call_mistral(prompt: str, model: str, system: str = "", expect_json: bool = True, temperature: float = 0.0) -> dict | str:
    return _call_openai_compat(prompt, model, system, expect_json, temperature, MISTRAL_BASE, MISTRAL_API_KEY, "mistral")


def call_llm(
    prompt: str,
    model: str,
    system: str = "",
    expect_json: bool = True,
    temperature: float = 0.0,
) -> dict | str:
    """
    Send a prompt to the specified model and return parsed JSON (or raw text).
    Provider is inferred from model name. Retries with exponential backoff.
    """
    _check_context_limit(prompt, system, model)

    global _last_call_time
    last = _last_call_time.get(model, 0.0)
    elapsed = time.time() - last
    if elapsed < _CALL_MIN_INTERVAL:
        time.sleep(_CALL_MIN_INTERVAL - elapsed)

    provider = _provider(model)
    caller = {
        "groq": _call_groq,
        "cerebras": _call_cerebras,
        "mistral": _call_mistral,
    }.get(provider, _call_gemini)

    for attempt in range(1, MAX_RETRIES + 1):
        try:
            _last_call_time[model] = time.time()
            result = caller(
                prompt=prompt,
                model=model,
                system=system,
                expect_json=expect_json,
                temperature=temperature,
            )
            _increment_daily_calls(model)
            if POST_CALL_DELAY > 0:
                time.sleep(POST_CALL_DELAY)
            return result
        except json.JSONDecodeError as e:
            logger.warning("JSON parse error on attempt %d: %s", attempt, e)
            if attempt == MAX_RETRIES:
                raise
        except requests.HTTPError as e:
            status = e.response.status_code if e.response is not None else 0
            logger.warning("HTTP %d on attempt %d: %s", status, attempt, e)
            if attempt == MAX_RETRIES:
                raise
            wait = 65 if status == 429 else RETRY_BASE_DELAY * (2 ** (attempt - 1))
            logger.info("Waiting %ds before retry...", wait)
            time.sleep(wait)
            continue
        except Exception as e:
            logger.warning("LLM call error on attempt %d: %s", attempt, e)
            if attempt == MAX_RETRIES:
                raise
        time.sleep(RETRY_BASE_DELAY * (2 ** (attempt - 1)))

    raise RuntimeError("LLM call failed after all retries")
