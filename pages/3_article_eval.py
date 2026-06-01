"""
Article evaluation page with background-thread execution and file-based polling.

The evaluation pipeline can take 60-180s. Running it synchronously blocks the
Streamlit WebSocket, causing timeouts and losing session state on tab switches.

Strategy:
  - Launch evaluate_article() in a daemon thread; thread writes result to
    data/processed/ on completion (the pipeline already does this).
  - Store only article_id + thread status flags in session_state — these
    survive reconnects as plain strings/bools.
  - Poll for the result file every 3s via st.rerun(). Polling also keeps the
    WebSocket alive, preventing Community Cloud idle timeouts.
  - On reconnect (tab switch, refresh), if the file already exists it loads
    immediately regardless of thread state.
"""
import hashlib
import json
import sys
import threading
import time
from pathlib import Path

import streamlit as st

ROOT = Path(__file__).parent.parent
sys.path.insert(0, str(ROOT))

from config import FRAMEWORK_VERSION, TAXONOMY_VERSION, EVAL_MODEL, JUDGE_MODEL, TRIAGE_MODEL, PROCESSED_DIR
from src.refract.ingest import fetch_url, get_article
from src.refract.bias_eval import evaluate_article
from components.eval_display import (
    render_summary_bar,
    render_bias_card,
    render_article_highlighted,
)

st.set_page_config(page_title="Article Evaluation — Refract", layout="wide")
st.title("Article Evaluation")
st.caption(f"Framework {FRAMEWORK_VERSION} · Taxonomy {TAXONOMY_VERSION} · Model: {EVAL_MODEL}")

POLL_INTERVAL = 3  # seconds between result-file checks


def _result_path(article_id: str) -> Path:
    return PROCESSED_DIR / f"{article_id}_{FRAMEWORK_VERSION}.json"


def _load_result(article_id: str) -> dict | None:
    p = _result_path(article_id)
    if p.exists():
        try:
            return json.loads(p.read_text())
        except Exception:
            return None
    return None


def _run_eval_thread(article: dict) -> None:
    """Runs in a daemon thread. Writes result to disk; updates session flags via shared dict."""
    try:
        evaluate_article(
            article,
            eval_model=EVAL_MODEL,
            judge_model=JUDGE_MODEL,
            triage_model=TRIAGE_MODEL,
            run_judge=True,
        )
        st.session_state["_eval_done"] = True
    except Exception as e:
        st.session_state["_eval_error"] = str(e)
        st.session_state["_eval_done"] = True


# ---------------------------------------------------------------------------
# Input
# ---------------------------------------------------------------------------
input_mode = st.radio("Input mode", ["URL", "Paste text"], horizontal=True)

if input_mode == "URL":
    url_input = st.text_input("Article URL", placeholder="https://example.com/article")
    if st.button("Fetch & Evaluate", type="primary") and url_input:
        with st.spinner("Fetching article..."):
            try:
                article, already_done = get_article(url_input, FRAMEWORK_VERSION)
            except Exception as e:
                st.error(f"Could not fetch article: {e}")
                st.stop()

        article_id = article["article_id"]

        if already_done and _load_result(article_id):
            # Already evaluated — skip straight to display
            st.session_state["eval_article_id"] = article_id
            st.session_state["eval_article"] = article
            st.session_state["_eval_done"] = True
            st.session_state["_eval_error"] = None
            st.session_state["_eval_running"] = False
        else:
            st.session_state["eval_article_id"] = article_id
            st.session_state["eval_article"] = article
            st.session_state["_eval_done"] = False
            st.session_state["_eval_error"] = None
            st.session_state["_eval_running"] = True
            t = threading.Thread(target=_run_eval_thread, args=(article,), daemon=True)
            t.start()

        st.rerun()

else:
    pasted = st.text_area("Paste article text", height=200)
    title_input = st.text_input("Title (optional)")
    if st.button("Evaluate", type="primary") and pasted:
        article_id = hashlib.sha256(pasted.encode()).hexdigest()[:16]
        article = {
            "article_id": article_id,
            "url": None,
            "title": title_input or "Pasted text",
            "source": "pasted",
            "text": pasted,
            "word_count": len(pasted.split()),
        }
        existing = _load_result(article_id)
        if existing:
            st.session_state["eval_article_id"] = article_id
            st.session_state["eval_article"] = article
            st.session_state["_eval_done"] = True
            st.session_state["_eval_error"] = None
            st.session_state["_eval_running"] = False
        else:
            st.session_state["eval_article_id"] = article_id
            st.session_state["eval_article"] = article
            st.session_state["_eval_done"] = False
            st.session_state["_eval_error"] = None
            st.session_state["_eval_running"] = True
            t = threading.Thread(target=_run_eval_thread, args=(article,), daemon=True)
            t.start()
        st.rerun()

# ---------------------------------------------------------------------------
# Polling / progress display
# ---------------------------------------------------------------------------
article_id = st.session_state.get("eval_article_id")

if article_id and not st.session_state.get("_eval_done"):
    # Check if the file appeared even if the flag hasn't updated yet
    if _load_result(article_id):
        st.session_state["_eval_done"] = True
        st.session_state["_eval_running"] = False
        st.rerun()
    else:
        st.info(
            "⏳ **Evaluation running** — this takes 60–180 seconds depending on article length. "
            "You can switch tabs and come back; the result will be here when complete."
        )
        st.caption("Checking for results every 3 seconds…")
        time.sleep(POLL_INTERVAL)
        st.rerun()

# ---------------------------------------------------------------------------
# Error state
# ---------------------------------------------------------------------------
if st.session_state.get("_eval_error"):
    st.error(f"Evaluation failed: {st.session_state['_eval_error']}")
    if st.button("Clear and retry"):
        for k in ["eval_article_id", "eval_article", "_eval_done", "_eval_error", "_eval_running"]:
            st.session_state.pop(k, None)
        st.rerun()
    st.stop()

# ---------------------------------------------------------------------------
# Results display
# ---------------------------------------------------------------------------
if article_id and st.session_state.get("_eval_done"):
    result = _load_result(article_id)
    if not result:
        st.error("Evaluation completed but result file not found. Try re-evaluating.")
        st.stop()

    article = st.session_state.get("eval_article", {})
    bias_instances = result.get("bias_instances", [])
    judge_result = result.get("judge_result", {})

    verdicts = {j["bias_id"]: j for j in judge_result.get("judgments", [])}
    for inst in bias_instances:
        v = verdicts.get(inst.get("bias_id"))
        if v:
            inst["_judge_verdict"] = v

    title = result.get("title") or article.get("title") or "Article"
    st.subheader(title)
    if result.get("source_url"):
        st.caption(result["source_url"])

    st.divider()
    render_summary_bar(result.get("summary", {}))
    st.divider()

    tab1, tab2 = st.tabs(["Bias Cards", "Article View"])

    with tab1:
        if not bias_instances:
            st.info("No bias instances detected.")
        else:
            by_cat: dict[str, list] = {}
            for inst in bias_instances:
                by_cat.setdefault(inst.get("category", "Other"), []).append(inst)
            for cat, instances in sorted(by_cat.items()):
                st.markdown(f"#### {cat}")
                for i, inst in enumerate(instances):
                    render_bias_card(inst, i)

    with tab2:
        st.markdown("**Original article with detected excerpts highlighted**")
        render_article_highlighted(
            result.get("article_text", article.get("text", "")),
            bias_instances,
        )

    st.divider()

    col1, col2 = st.columns(2)
    with col1:
        st.download_button(
            "Download full evaluation JSON",
            data=json.dumps(result, indent=2),
            file_name=f"{article_id}.json",
            mime="application/json",
        )
    with col2:
        summary = result.get("summary", {})
        md = f"# Refract Evaluation: {title}\n\n"
        md += f"Framework: {result.get('framework_version')} | Model: {result.get('model')}\n\n"
        md += f"## Summary\n- Bias types: {summary.get('bias_type_count', 0)}\n"
        md += f"- Occurrences: {summary.get('total_occurrences', 0)}\n"
        md += f"- Dominant: {', '.join(summary.get('dominant_categories', []))}\n\n## Detected Biases\n"
        for inst in bias_instances:
            md += f"\n### {inst.get('bias_name')}\n"
            for occ in inst.get("occurrences", []):
                md += f'> "{occ.get("excerpt", "")}"\n\n*{occ.get("explanation", "")}*\n\n'
        st.download_button(
            "Download summary markdown",
            data=md,
            file_name=f"{article_id}.md",
            mime="text/markdown",
        )

    if bias_instances:
        st.info("Evaluation complete. Go to **Article Reframe** in the sidebar to generate a reframed version.")

    if st.button("Evaluate another article"):
        for k in ["eval_article_id", "eval_article", "_eval_done", "_eval_error", "_eval_running"]:
            st.session_state.pop(k, None)
        st.rerun()
