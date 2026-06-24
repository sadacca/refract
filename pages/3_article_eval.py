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

from config import (
    FRAMEWORK_VERSION, TAXONOMY_VERSION, PROCESSED_DIR,
    EVAL_MODEL, JUDGE_MODEL, TRIAGE_MODEL,
    EVAL_MODEL_OPTIONS, JUDGE_MODEL_OPTIONS, TRIAGE_MODEL_OPTIONS,
)
from src.refract.ingest import fetch_url, get_article
from src.refract.bias_eval import evaluate_article
from components.eval_display import (
    render_summary_bar,
    render_bias_card,
    render_article_highlighted,
)

st.set_page_config(page_title="Article Evaluation — Refract", layout="wide")
st.title("Article Evaluation")
st.caption(f"Framework {FRAMEWORK_VERSION} · Taxonomy {TAXONOMY_VERSION}")

POLL_INTERVAL = 3  # seconds between result-file checks


def _load_results_by_mode(article_id: str) -> dict[str, dict]:
    """Return {mode: result_dict} across every stored run of this article+version.

    The pipeline names files {article_id}_{version}_{model_sig}_{mode}.json, so a
    deep run and a flat run coexist on disk. Keyed by mode (latest wins) to drive
    the comparison toggle. Legacy files without a mode tag are treated as "deep".
    """
    out: dict[str, dict] = {}
    for p in sorted(
        PROCESSED_DIR.glob(f"{article_id}_{FRAMEWORK_VERSION}_*.json"),
        key=lambda p: p.stat().st_mtime,
    ):
        try:
            r = json.loads(p.read_text())
        except Exception:
            continue
        out[r.get("mode") or "deep"] = r
    return out


def _run_eval_thread(
    article: dict, eval_model: str, judge_model: str, triage_model: str, modes: list[str]
) -> None:
    """Runs in a daemon thread. Evaluates each requested mode in sequence, writing
    one result file per mode; updates session flags via the shared state dict."""
    try:
        for m in modes:
            evaluate_article(
                article,
                eval_model=eval_model,
                judge_model=judge_model,
                triage_model=triage_model,
                mode=m,
                run_judge=True,
            )
        st.session_state["_eval_done"] = True
    except Exception as e:
        st.session_state["_eval_error"] = str(e)
        st.session_state["_eval_done"] = True


def _start_eval(article: dict, modes: list[str], eval_model: str, judge_model: str, triage_model: str) -> None:
    """Set up session state and launch evaluation for any modes not already on disk."""
    article_id = article["article_id"]
    existing = _load_results_by_mode(article_id)
    missing = [m for m in modes if m not in existing]

    st.session_state["eval_article_id"] = article_id
    st.session_state["eval_article"] = article
    st.session_state["_eval_expected_modes"] = modes
    st.session_state["_eval_error"] = None

    if not missing:
        # Every requested mode is already cached — skip straight to display.
        st.session_state["_eval_done"] = True
        st.session_state["_eval_running"] = False
        return

    st.session_state["_eval_done"] = False
    st.session_state["_eval_running"] = True
    threading.Thread(
        target=_run_eval_thread,
        args=(article, eval_model, judge_model, triage_model, missing),
        daemon=True,
    ).start()


# ---------------------------------------------------------------------------
# Model selection
# ---------------------------------------------------------------------------
with st.expander("Model settings", expanded=False):
    mc1, mc2, mc3 = st.columns(3)
    sel_eval = mc1.selectbox(
        "Eval model (Pass 2)",
        EVAL_MODEL_OPTIONS,
        index=EVAL_MODEL_OPTIONS.index(EVAL_MODEL) if EVAL_MODEL in EVAL_MODEL_OPTIONS else 0,
        help="Large model used for bias identification (Pass 2).",
    )
    sel_judge = mc2.selectbox(
        "Judge model (Pass 4)",
        JUDGE_MODEL_OPTIONS,
        index=JUDGE_MODEL_OPTIONS.index(JUDGE_MODEL) if JUDGE_MODEL in JUDGE_MODEL_OPTIONS else 0,
        help="Model used to review and rate detections (Pass 4).",
    )
    sel_triage = mc3.selectbox(
        "Triage model (Pass 0/1/3)",
        TRIAGE_MODEL_OPTIONS,
        index=TRIAGE_MODEL_OPTIONS.index(TRIAGE_MODEL) if TRIAGE_MODEL in TRIAGE_MODEL_OPTIONS else 0,
        help="Small/fast model for paragraph triage and recall probes.",
    )

eval_mode_choice = st.radio(
    "Evaluation mode",
    ["deep", "flat", "both"],
    horizontal=True,
    help=(
        "deep = full pipeline (Pass 1 category triage + Pass 3 recall probes). "
        "flat = Pass 2 on every category, no triage/probes. "
        "both = run each and compare side by side via a toggle."
    ),
)
_modes = ["deep", "flat"] if eval_mode_choice == "both" else [eval_mode_choice]

# ---------------------------------------------------------------------------
# Input
# ---------------------------------------------------------------------------
input_mode = st.radio("Input mode", ["URL", "Paste text"], horizontal=True)

if input_mode == "URL":
    url_input = st.text_input("Article URL", placeholder="https://example.com/article")
    if st.button("Fetch & Evaluate", type="primary") and url_input:
        with st.spinner("Fetching article..."):
            try:
                article, _already_done = get_article(url_input, FRAMEWORK_VERSION)
            except Exception as e:
                st.error(f"Could not fetch article: {e}")
                st.stop()

        _start_eval(article, _modes, sel_eval, sel_judge, sel_triage)
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
        _start_eval(article, _modes, sel_eval, sel_judge, sel_triage)
        st.rerun()

# ---------------------------------------------------------------------------
# Polling / progress display
# ---------------------------------------------------------------------------
article_id = st.session_state.get("eval_article_id")
expected_modes = st.session_state.get("_eval_expected_modes", [])

if article_id and not st.session_state.get("_eval_done"):
    results = _load_results_by_mode(article_id)
    # Done when every requested mode has a result file (covers the case where the
    # thread's session flag was lost across a reconnect).
    if expected_modes and all(m in results for m in expected_modes):
        st.session_state["_eval_done"] = True
        st.session_state["_eval_running"] = False
        st.rerun()
    else:
        done_n = sum(1 for m in expected_modes if m in results)
        suffix = f" ({done_n}/{len(expected_modes)} modes complete)" if len(expected_modes) > 1 else ""
        st.info(
            "⏳ **Evaluation running** — this takes 60–180 seconds per mode depending on article "
            f"length.{suffix} You can switch tabs and come back; the result will be here when complete."
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
        for k in ["eval_article_id", "eval_article", "_eval_done", "_eval_error", "_eval_running", "_eval_expected_modes"]:
            st.session_state.pop(k, None)
        st.rerun()
    st.stop()

# ---------------------------------------------------------------------------
# Results display
# ---------------------------------------------------------------------------
if article_id and st.session_state.get("_eval_done"):
    results_by_mode = _load_results_by_mode(article_id)
    if not results_by_mode:
        st.error("Evaluation completed but result file not found. Try re-evaluating.")
        st.stop()

    # Mode toggle — only shown when more than one mode is available for this article.
    available_modes = sorted(results_by_mode.keys())
    if len(available_modes) > 1:
        sel_view_mode = st.radio(
            "View mode",
            available_modes,
            horizontal=True,
            format_func=lambda m: m.capitalize(),
            help="Switch between the deep and flat evaluations of this article.",
        )
    else:
        sel_view_mode = available_modes[0]

    result = results_by_mode[sel_view_mode]

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

    models = result.get("models", {})
    st.caption(
        f"**Mode:** {result.get('mode', 'deep')} · "
        f"eval `{models.get('eval', result.get('model', '?'))}` · "
        f"judge `{models.get('judge', '?')}` · triage `{models.get('triage', '?')}`"
    )

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
            file_name=f"{article_id}_{sel_view_mode}.json",
            mime="application/json",
        )
    with col2:
        summary = result.get("summary", {})
        md = f"# Refract Evaluation: {title}\n\n"
        md += f"Framework: {result.get('framework_version')} | Mode: {result.get('mode', 'deep')} | Model: {result.get('model')}\n\n"
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
            file_name=f"{article_id}_{sel_view_mode}.md",
            mime="text/markdown",
        )

    if bias_instances:
        st.info("Evaluation complete. Go to **Article Reframe** in the sidebar to generate a reframed version.")

    if st.button("Evaluate another article"):
        for k in ["eval_article_id", "eval_article", "_eval_done", "_eval_error", "_eval_running", "_eval_expected_modes"]:
            st.session_state.pop(k, None)
        st.rerun()
