"""
Shared corpus loader for Streamlit pages.

All pages that display evaluated articles use load_corpus() so cache
behaviour and data shape are consistent. Call render_refresh_button()
on any page where the user might want to force a reload.
"""
import json
from pathlib import Path

import streamlit as st

# Resolve paths relative to repo root regardless of working directory
_ROOT = Path(__file__).parent.parent
_PROCESSED_DIR = _ROOT / "data" / "processed"
_TAXONOMY_PATH = _ROOT / "bias_index" / "taxonomy.json"


@st.cache_data(ttl=60, show_spinner=False)
def load_corpus(framework_version: str) -> list[dict]:
    """
    Scan data/processed/ and return all evaluation records for the given
    framework version. Cached for 60 seconds; call load_corpus.clear() to
    force an immediate reload.
    """
    results = []
    for p in sorted(_PROCESSED_DIR.glob(f"*_{framework_version}*.json")):
        try:
            d = json.loads(p.read_text())
            d["_word_count"] = len(d.get("article_text", "").split())
            results.append(d)
        except Exception:
            continue
    return results


@st.cache_data(ttl=60, show_spinner=False)
def load_taxonomy() -> dict:
    if _TAXONOMY_PATH.exists():
        return json.loads(_TAXONOMY_PATH.read_text())
    return {"biases": []}


def render_refresh_button(label: str = "🔄 Refresh data") -> None:
    """Render a button that clears all corpus caches and reruns the page."""
    if st.button(label, help="Reload evaluated articles from disk"):
        load_corpus.clear()
        load_taxonomy.clear()
        st.rerun()
