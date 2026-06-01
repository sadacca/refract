"""
Thin LLM client: structured JSON calls via REST APIs.
Supports Groq (primary) and Gemini (fallback/judge).
Provider is inferred from the model name prefix.
"""
import json
import logging
import os
import time
from typing import Any

import requests

from config import GEMINI_API_KEY, GROQ_API_KEY, MAX_RETRIES, RETRY_BASE_DELAY

logger = logging.getLogger(__name__)

GEMINI_BASE = "https://generativelanguage.googleapis.com/v1beta/models"
GROQ_BASE = "https://api.groq.com/openai/v1/chat/completions"

# Minimum seconds between calls, tracked per model to avoid cross-model interference.
# Groq free: 30 RPM / model. TPM limits (not just RPM) cause most 429s on long articles.
# 6s per call = ~10 RPM, leaving headroom for token bursts.
_CALL_MIN_INTERVAL = float(os.getenv("LLM_CALL_INTERVAL", "6"))
_last_call_time: dict[str, float] = {}


def _provider(model: str) -> str:
    """Infer provider from model name."""
    if model.startswith(("llama", "mixtral", "gemma", "qwen", "deepseek")):
        return "groq"
    return "gemini"


def _call_groq(prompt: str, model: str, system: str = "", expect_json: bool = True, temperature: float = 0.0) -> dict | str:
    if not GROQ_API_KEY:
        raise RuntimeError("GROQ_API_KEY not set")

    messages = []
    if system:
        messages.append({"role": "system", "content": system})
    messages.append({"role": "user", "content": prompt})

    body: dict[str, Any] = {
        "model": model,
        "messages": messages,
        "temperature": temperature,
    }
    if expect_json:
        body["response_format"] = {"type": "json_object"}

    resp = requests.post(
        GROQ_BASE,
        json=body,
        headers={"Authorization": f"Bearer {GROQ_API_KEY}"},
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
    global _last_call_time
    last = _last_call_time.get(model, 0.0)
    elapsed = time.time() - last
    if elapsed < _CALL_MIN_INTERVAL:
        time.sleep(_CALL_MIN_INTERVAL - elapsed)

    provider = _provider(model)
    caller = _call_groq if provider == "groq" else _call_gemini

    for attempt in range(1, MAX_RETRIES + 1):
        try:
            _last_call_time[model] = time.time()
            return caller(
                prompt=prompt,
                model=model,
                system=system,
                expect_json=expect_json,
                temperature=temperature,
            )
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
