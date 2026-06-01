"""
Thin LLM client: structured JSON calls via REST APIs.
Supports Gemini (primary, free tier) and is extensible to other providers.
Uses requests directly to avoid SDK dependency conflicts.
"""
import json
import logging
import time
from typing import Any

import requests

from config import GEMINI_API_KEY, MAX_RETRIES, RETRY_BASE_DELAY

logger = logging.getLogger(__name__)

GEMINI_BASE = "https://generativelanguage.googleapis.com/v1beta/models"


def _call_gemini(
    prompt: str,
    model: str,
    system: str = "",
    expect_json: bool = True,
    temperature: float = 0.0,
) -> dict | str:
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
    Retries on transient errors with exponential backoff.
    """
    for attempt in range(1, MAX_RETRIES + 1):
        try:
            return _call_gemini(
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
            # 429 rate limit: wait much longer — free tier resets per minute
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
