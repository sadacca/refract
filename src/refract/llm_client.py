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
    MODEL_CONTEXT_LIMITS, MODEL_TPD_LIMITS,
)

logger = logging.getLogger(__name__)

GEMINI_BASE = "https://generativelanguage.googleapis.com/v1beta/models"
GROQ_BASE = "https://api.groq.com/openai/v1/chat/completions"
CEREBRAS_BASE = "https://api.cerebras.ai/v1/chat/completions"
MISTRAL_BASE = "https://api.mistral.ai/v1/chat/completions"

# Minimum seconds between calls, tracked per model to avoid cross-model interference.
# Per-provider defaults reflect each free tier's actual RPM cap:
#   Groq/Cerebras: 30 RPM -> 6s leaves headroom for token bursts (~10 RPM effective).
#   Mistral: 2 RPM hard cap -> 31s (30s minimum + 1s buffer) to avoid 429s.
#   Gemini: paced via GEMINI_JUDGE_CHAIN RPD tracking; 6s is a safe default.
# LLM_CALL_INTERVAL overrides this for ALL providers (e.g. local testing).
_PROVIDER_MIN_INTERVALS = {
    "groq": 6.0,
    "cerebras": 6.0,
    "mistral": 31.0,
    "gemini": 6.0,
}
_last_call_time: dict[str, float] = {}


def _min_interval_for(model: str) -> float:
    override = os.getenv("LLM_CALL_INTERVAL")
    if override:
        return float(override)
    return _PROVIDER_MIN_INTERVALS.get(_provider(model), 6.0)


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


def _increment_daily_calls(model: str, tokens: int = 0) -> None:
    today = _today()
    data = _load_daily_usage()
    day = data.get(today, {})
    entry = day.get(model, {})
    if not isinstance(entry, dict):  # legacy format: bare call-count int
        entry = {"calls": entry, "tokens": 0}
    entry["calls"] = entry.get("calls", 0) + 1
    entry["tokens"] = entry.get("tokens", 0) + tokens
    day[model] = entry
    _save_daily_usage({today: day})


def get_daily_calls(model: str) -> int:
    """Return successful LLM calls made today for this model."""
    entry = _load_daily_usage().get(_today(), {}).get(model, 0)
    return entry.get("calls", 0) if isinstance(entry, dict) else entry


def get_daily_tokens(model: str) -> int:
    """Return total tokens (prompt + completion) consumed today for this model."""
    entry = _load_daily_usage().get(_today(), {}).get(model, 0)
    return entry.get("tokens", 0) if isinstance(entry, dict) else 0


def _is_near_daily_limit(model: str, rpd_limit: int, soft_pct: float = 0.85) -> bool:
    calls = get_daily_calls(model)
    soft = int(rpd_limit * soft_pct)
    if calls >= soft:
        logger.info("Daily usage: %s at %d calls (soft limit %d/%d RPD)", model, calls, soft, rpd_limit)
        return True
    return False


def _is_near_daily_token_limit(model: str, tpd_limit: int, soft_pct: float = 0.85) -> bool:
    tokens = get_daily_tokens(model)
    soft = int(tpd_limit * soft_pct)
    if tokens >= soft:
        logger.info("Daily usage: %s at %d tokens (soft limit %d/%d TPD)", model, tokens, soft, tpd_limit)
        return True
    return False


def select_from_chain(model_chain: list[tuple[str, int]]) -> str:
    """
    Return the first model in the chain below its daily RPD soft limit (85%)
    and, where MODEL_TPD_LIMITS has an entry, below its TPD soft limit too.
    TPD matters because Pass 2 sends full article text — token budgets can be
    exhausted well before the request count looks high. Logs which models are
    skipped. Falls back to the last model if all are near a limit.
    """
    for model, rpd in model_chain:
        calls = get_daily_calls(model)
        soft_rpd = int(rpd * 0.85)
        rpd_ok = calls < soft_rpd
        tpd_limit = MODEL_TPD_LIMITS.get(model)
        tpd_ok = tpd_limit is None or not _is_near_daily_token_limit(model, tpd_limit)
        if rpd_ok and tpd_ok:
            logger.debug("Chain: selected %s (%d/%d calls, %d tokens today)", model, calls, rpd, get_daily_tokens(model))
            return model
        logger.info(
            "Chain: skipping %s (%d calls >= soft limit %d/%d RPD, or TPD soft limit reached)",
            model, calls, soft_rpd, rpd,
        )
    fallback = model_chain[-1][0]
    logger.warning("All chain models near daily RPD/TPD limit — forcing %s", fallback)
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


def _call_groq(prompt: str, model: str, system: str = "", expect_json: bool = True, temperature: float = 0.0) -> tuple[dict | str, int]:
    return _call_openai_compat(prompt, _bare_model(model), system, expect_json, temperature, GROQ_BASE, GROQ_API_KEY, "groq")


def _parse_json_response(raw: str) -> Any:
    """Parse a model's JSON response, tolerating code fences, leading prose, and
    trailing data after the first complete JSON value.

    Models occasionally emit a valid JSON object followed by extra content — a
    second object, a trailing note, or a stray fence — even when asked for pure
    JSON (e.g. via responseMimeType). A plain json.loads then raises
    'Extra data: ...'. Because the eval calls run at temperature 0, that bad
    output is deterministic and every retry reproduces it, so the article fails.
    We strip fences, skip to the first '{'/'[', and use raw_decode so trailing
    bytes after the first complete value are ignored. Genuinely malformed output
    still raises json.JSONDecodeError for the caller's retry loop to handle.
    """
    text = raw.strip()
    if text.startswith("```"):
        text = text[3:]
        if text[:4].lower() == "json":
            text = text[4:]
        fence = text.rfind("```")
        if fence != -1:
            text = text[:fence]
        text = text.strip()

    start = next((i for i, ch in enumerate(text) if ch in "{["), -1)
    if start == -1:
        return json.loads(text)  # no JSON object/array found — raise clear error
    obj, _end = json.JSONDecoder().raw_decode(text[start:])
    return obj


def _call_gemini(prompt: str, model: str, system: str = "", expect_json: bool = True, temperature: float = 0.0) -> tuple[dict | str, int]:
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

    payload = resp.json()
    raw = payload["candidates"][0]["content"]["parts"][0]["text"].strip()
    tokens = payload.get("usageMetadata", {}).get("totalTokenCount", 0)
    result = _parse_json_response(raw) if expect_json else raw
    return result, tokens


def _call_openai_compat(
    prompt: str, model: str, system: str, expect_json: bool, temperature: float,
    base_url: str, api_key: str, provider_name: str,
) -> tuple[dict | str, int]:
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
    payload = resp.json()
    raw = payload["choices"][0]["message"]["content"].strip()
    tokens = payload.get("usage", {}).get("total_tokens", 0)

    result = _parse_json_response(raw) if expect_json else raw
    return result, tokens


def _call_cerebras(prompt: str, model: str, system: str = "", expect_json: bool = True, temperature: float = 0.0) -> tuple[dict | str, int]:
    return _call_openai_compat(prompt, _bare_model(model), system, expect_json, temperature, CEREBRAS_BASE, CEREBRAS_API_KEY, "cerebras")


def _call_mistral(prompt: str, model: str, system: str = "", expect_json: bool = True, temperature: float = 0.0) -> tuple[dict | str, int]:
    return _call_openai_compat(prompt, _bare_model(model), system, expect_json, temperature, MISTRAL_BASE, MISTRAL_API_KEY, "mistral")


def _parse_retry_after(resp: requests.Response | None) -> int | None:
    """Seconds to wait before retrying, per the Retry-After header. None if absent/invalid."""
    if resp is None:
        return None
    value = resp.headers.get("Retry-After")
    if value is None:
        return None
    try:
        return int(float(value))
    except ValueError:
        return None


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
    min_interval = _min_interval_for(model)
    if elapsed < min_interval:
        time.sleep(min_interval - elapsed)

    provider = _provider(model)
    caller = {
        "groq": _call_groq,
        "cerebras": _call_cerebras,
        "mistral": _call_mistral,
    }.get(provider, _call_gemini)

    for attempt in range(1, MAX_RETRIES + 1):
        try:
            _last_call_time[model] = time.time()
            result, tokens = caller(
                prompt=prompt,
                model=model,
                system=system,
                expect_json=expect_json,
                temperature=temperature,
            )
            _increment_daily_calls(model, tokens)
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
            if status == 400:
                # 400s (e.g. decommissioned model, malformed request) won't
                # change on retry — fail immediately instead of burning the
                # full backoff schedule.
                raise
            if status == 429:
                retry_after = _parse_retry_after(e.response)
                # A long Retry-After (or none at all) means a daily RPD/TPD cap
                # was tripped, not a transient per-minute throttle — retrying
                # the same model won't help until the cap resets. Fail fast so
                # the caller's chain fallback (select_from_chain / per-call
                # retry against the next model) can switch models immediately
                # instead of burning the whole retry budget on a dead model.
                if retry_after is None or retry_after > 60:
                    logger.warning(
                        "%s: 429 with retry-after=%s suggests a daily cap — "
                        "failing fast instead of retrying", model, retry_after,
                    )
                    raise
                if attempt == MAX_RETRIES:
                    raise
                logger.info("Waiting %ds before retry (Retry-After)...", retry_after)
                time.sleep(retry_after)
                continue
            if attempt == MAX_RETRIES:
                raise
            wait = RETRY_BASE_DELAY * (2 ** (attempt - 1))
            logger.info("Waiting %ds before retry...", wait)
            time.sleep(wait)
            continue
        except Exception as e:
            logger.warning("LLM call error on attempt %d: %s", attempt, e)
            if attempt == MAX_RETRIES:
                raise
        time.sleep(RETRY_BASE_DELAY * (2 ** (attempt - 1)))

    raise RuntimeError("LLM call failed after all retries")
