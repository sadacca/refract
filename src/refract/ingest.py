import hashlib
import json
import logging
import time
from pathlib import Path
from typing import Optional

import requests
import trafilatura

from config import CACHE_DIR, PROCESSED_DIR, GUARDIAN_API_KEY, MAX_RETRIES, RETRY_BASE_DELAY

logger = logging.getLogger(__name__)

GUARDIAN_BASE = "https://content.guardianapis.com"


def _sha256(url: str, text: str) -> str:
    return hashlib.sha256(f"{url}{text}".encode()).hexdigest()[:16]


def _read_cache(article_id: str) -> Optional[dict]:
    path = CACHE_DIR / f"{article_id}_raw.json"
    if path.exists():
        return json.loads(path.read_text())
    return None


def _write_cache(article_id: str, record: dict) -> None:
    CACHE_DIR.mkdir(parents=True, exist_ok=True)
    path = CACHE_DIR / f"{article_id}_raw.json"
    path.write_text(json.dumps(record, indent=2))


def _already_evaluated(
    article_id: str,
    framework_version: str,
    model_sig: str = "",
    mode: str = "",
) -> Optional[dict]:
    """
    Return an existing evaluation record if one exists, else None.

    When model_sig is provided (batch eval path): checks the exact file for
    that model combination and mode — enabling re-scoring with a new model or
    in a different mode without overwriting the previous result. The mode is
    part of the filename, so it must be supplied to match an exact run.

    When model_sig is omitted (UI / get_article path): returns the most recent
    evaluation for this article+version across any model combination or mode.
    """
    if model_sig:
        stem = f"{article_id}_{framework_version}_{model_sig}"
        path = PROCESSED_DIR / (f"{stem}_{mode}.json" if mode else f"{stem}.json")
        return json.loads(path.read_text()) if path.exists() else None

    # No model_sig: find the most recent evaluation for this article+version.
    candidates = sorted(
        PROCESSED_DIR.glob(f"{article_id}_{framework_version}_*.json"),
        key=lambda p: p.stat().st_mtime,
        reverse=True,
    )
    # Also check the legacy filename format (pre-model-sig).
    legacy = PROCESSED_DIR / f"{article_id}_{framework_version}.json"
    if legacy.exists():
        candidates.append(legacy)
    if candidates:
        return json.loads(candidates[0].read_text())
    return None


def fetch_url(url: str) -> dict:
    """
    Fetch and extract article text from a URL using trafilatura.
    Returns a record dict with url, title, text, word_count, article_id.

    No retries: a failed fetch (timeout, 404, dead link) is usually a stale
    URL, not a transient blip, so retrying just burns time before the
    per-article failure batch_eval.py already handles by moving on.
    """
    headers = {
        "User-Agent": (
            "Mozilla/5.0 (compatible; Refract/0.1; research bot; "
            "+https://github.com/sadacca/refract)"
        )
    }

    downloaded = trafilatura.fetch_url(url)
    if not downloaded:
        # trafilatura fetch failed — try requests with browser UA
        resp = requests.get(url, headers=headers, timeout=20)
        if resp.status_code == 404:
            raise ValueError(f"404 Not Found: {url}")
        resp.raise_for_status()
        downloaded = resp.text
    if not downloaded:
        raise ValueError(f"empty response from {url}")

    text = trafilatura.extract(downloaded, include_comments=False, include_tables=False)
    if not text:
        raise ValueError(f"trafilatura extracted empty text from {url}")

    meta = trafilatura.extract_metadata(downloaded)
    title = meta.title if meta and meta.title else ""

    article_id = _sha256(url, text)
    record = {
        "article_id": article_id,
        "url": url,
        "title": title,
        "source": _source_from_url(url),
        "text": text,
        "word_count": len(text.split()),
    }
    _write_cache(article_id, record)
    return record


def fetch_guardian(query: str, page_size: int = 10, section: str = "") -> list[dict]:
    """
    Search The Guardian API and return a list of article records.
    """
    if not GUARDIAN_API_KEY:
        raise RuntimeError("GUARDIAN_API_KEY not set")

    params = {
        "q": query,
        "api-key": GUARDIAN_API_KEY,
        "show-fields": "bodyText,headline,wordcount",
        "page-size": page_size,
    }
    if section:
        params["section"] = section

    for attempt in range(1, MAX_RETRIES + 1):
        try:
            resp = requests.get(f"{GUARDIAN_BASE}/search", params=params, timeout=15)
            resp.raise_for_status()
            results = resp.json()["response"]["results"]
            records = []
            for item in results:
                text = item.get("fields", {}).get("bodyText", "")
                title = item.get("fields", {}).get("headline", item.get("webTitle", ""))
                url = item.get("webUrl", "")
                if not text:
                    continue
                article_id = _sha256(url, text)
                record = {
                    "article_id": article_id,
                    "url": url,
                    "title": title,
                    "source": "The Guardian",
                    "text": text,
                    "word_count": len(text.split()),
                }
                _write_cache(article_id, record)
                records.append(record)
            return records

        except Exception as e:
            logger.warning("Guardian API attempt %d failed: %s", attempt, e)
            if attempt == MAX_RETRIES:
                raise
            time.sleep(RETRY_BASE_DELAY * (2 ** (attempt - 1)))


def get_article(url: str, framework_version: str) -> tuple[dict, bool]:
    """
    Return (article_record, already_evaluated).
    Uses raw cache if available; skips fetch if article has already been evaluated.
    """
    # Check if fully evaluated already
    raw_path = CACHE_DIR / f"*_raw.json"  # need to search by url
    # scan cache for url match
    if CACHE_DIR.exists():
        for f in CACHE_DIR.glob("*_raw.json"):
            cached = json.loads(f.read_text())
            if cached.get("url") == url:
                article_id = cached["article_id"]
                if _already_evaluated(article_id, framework_version):
                    logger.info("Article %s already evaluated, returning cached", article_id)
                    return cached, True
                return cached, False

    record = fetch_url(url)
    evaluated = _already_evaluated(record["article_id"], framework_version) is not None
    return record, evaluated


def _source_from_url(url: str) -> str:
    try:
        from urllib.parse import urlparse
        return urlparse(url).netloc.replace("www.", "")
    except Exception:
        return ""
