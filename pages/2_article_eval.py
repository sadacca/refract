import json
import sys
from pathlib import Path

import streamlit as st

ROOT = Path(__file__).parent.parent
sys.path.insert(0, str(ROOT))

from config import FRAMEWORK_VERSION, TAXONOMY_VERSION, EVAL_MODEL, JUDGE_MODEL, PROCESSED_DIR
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

# ---------------------------------------------------------------------------
# Input
# ---------------------------------------------------------------------------
input_mode = st.radio("Input mode", ["URL", "Paste text"], horizontal=True)

article_text = ""
article_url = ""
article_title = ""

if input_mode == "URL":
    url_input = st.text_input("Article URL", placeholder="https://www.theguardian.com/...")
    if st.button("Fetch & Evaluate", type="primary") and url_input:
        st.session_state["eval_url"] = url_input
        st.session_state["eval_result"] = None
        st.session_state["eval_article"] = None
else:
    pasted = st.text_area("Paste article text", height=200)
    title_input = st.text_input("Title (optional)")
    if st.button("Evaluate", type="primary") and pasted:
        import hashlib
        h = hashlib.sha256(pasted.encode()).hexdigest()[:16]
        st.session_state["eval_article"] = {
            "article_id": h,
            "url": None,
            "title": title_input,
            "source": "pasted",
            "text": pasted,
            "word_count": len(pasted.split()),
        }
        st.session_state["eval_result"] = None
        st.session_state["eval_url"] = None

# ---------------------------------------------------------------------------
# Evaluation execution
# ---------------------------------------------------------------------------
if st.session_state.get("eval_url") and st.session_state.get("eval_result") is None:
    url = st.session_state["eval_url"]
    with st.spinner("Fetching article..."):
        try:
            article, already_done = get_article(url, FRAMEWORK_VERSION)
            st.session_state["eval_article"] = article
        except Exception as e:
            st.error(f"Could not fetch article: {e}")
            st.stop()

    if already_done:
        cached_path = list(PROCESSED_DIR.glob(f"{article['article_id']}_{FRAMEWORK_VERSION}.json"))
        if cached_path:
            result = json.loads(cached_path[0].read_text())
            st.session_state["eval_result"] = result
            st.info(f"Loaded from cache (framework {FRAMEWORK_VERSION})")

if st.session_state.get("eval_article") and st.session_state.get("eval_result") is None:
    article = st.session_state["eval_article"]

    progress_area = st.empty()
    with progress_area.container():
        st.markdown("**Running evaluation...**")
        p1_status = st.empty()
        p2_status = st.empty()
        p3_status = st.empty()
        p4_status = st.empty()

    p1_status.info("Pass 1: Category triage...")
    try:
        result = evaluate_article(
            article,
            eval_model=EVAL_MODEL,
            judge_model=JUDGE_MODEL,
            run_judge=True,
        )
        st.session_state["eval_result"] = result
        progress_area.empty()
    except Exception as e:
        progress_area.empty()
        st.error(f"Evaluation failed: {e}")
        st.stop()

# ---------------------------------------------------------------------------
# Results display
# ---------------------------------------------------------------------------
if st.session_state.get("eval_result"):
    result = st.session_state["eval_result"]
    article = st.session_state.get("eval_article", {})
    bias_instances = result.get("bias_instances", [])
    judge_result = result.get("judge_result", {})

    # Attach judge verdicts to instances for display
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

    # Summary bar
    render_summary_bar(result.get("summary", {}))

    st.divider()

    # Main content tabs
    tab1, tab2 = st.tabs(["Bias Cards", "Article View"])

    with tab1:
        if not bias_instances:
            st.info("No bias instances detected.")
        else:
            # Group by category
            by_cat: dict[str, list] = {}
            for inst in bias_instances:
                cat = inst.get("category", "Other")
                by_cat.setdefault(cat, []).append(inst)

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

    # Export
    col1, col2 = st.columns(2)
    with col1:
        st.download_button(
            "Download full evaluation JSON",
            data=json.dumps(result, indent=2),
            file_name=f"{result.get('article_id', 'evaluation')}.json",
            mime="application/json",
        )
    with col2:
        summary = result.get("summary", {})
        md = f"""# Refract Evaluation: {title}

Framework: {result.get('framework_version')} | Model: {result.get('model')}

## Summary
- Bias types detected: {summary.get('bias_type_count', 0)}
- Total occurrences: {summary.get('total_occurrences', 0)}
- Dominant categories: {', '.join(summary.get('dominant_categories', []))}

## Detected Biases
"""
        for inst in bias_instances:
            md += f"\n### {inst.get('bias_name')}\n"
            for occ in inst.get("occurrences", []):
                md += f'> "{occ.get("excerpt", "")}"\n\n'
                md += f"*{occ.get('explanation', '')}*\n\n"

        st.download_button(
            "Download summary markdown",
            data=md,
            file_name=f"{result.get('article_id', 'evaluation')}.md",
            mime="text/markdown",
        )

    # Reframe link
    if bias_instances:
        st.info("Evaluation complete. Go to **Article Reframe** in the sidebar to generate a reframed version.")
