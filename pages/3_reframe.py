import json
import sys
from pathlib import Path

import streamlit as st

ROOT = Path(__file__).parent.parent
sys.path.insert(0, str(ROOT))

from config import EVAL_MODEL
from src.refract.reframe import reframe_article

st.set_page_config(page_title="Article Reframe — Refract", layout="wide")
st.title("Article Reframe")
st.markdown(
    "*The reframed version is not the 'right' version — it is one possible alternative "
    "framing with identified cognitive patterns reduced. Both versions are valid; "
    "the comparison is the value.*"
)

result = st.session_state.get("eval_result")
article = st.session_state.get("eval_article")

if not result or not article:
    st.warning("No evaluation loaded. Run an evaluation on the **Article Evaluation** page first.")
    st.stop()

bias_instances = result.get("bias_instances", [])
if not bias_instances:
    st.info("No bias instances were detected in this article — nothing to reframe.")
    st.stop()

# Load taxonomy for strategy blocks
try:
    taxonomy = json.loads((ROOT / "bias_index" / "taxonomy.json").read_text())
except Exception as e:
    st.error(f"Could not load taxonomy: {e}")
    st.stop()

# ---------------------------------------------------------------------------
# Mode selection
# ---------------------------------------------------------------------------
title = result.get("title") or article.get("title") or "Article"
st.subheader(title)

mode = st.radio(
    "Reframe mode",
    ["Neutralize", "Steelman", "Annotated"],
    horizontal=True,
    help=(
        "**Neutralize:** Rewrite to reduce identified biases while preserving all facts.\n\n"
        "**Steelman:** Present the strongest version of each competing perspective.\n\n"
        "**Annotated:** Keep original text; insert inline annotations explaining each bias."
    ),
)

if st.button("Generate Reframe", type="primary"):
    with st.spinner(f"Generating {mode.lower()} reframe..."):
        try:
            reframe_result = reframe_article(
                article_text=result.get("article_text", article.get("text", "")),
                bias_instances=bias_instances,
                taxonomy=taxonomy,
                mode=mode.lower(),
                model=EVAL_MODEL,
            )
            st.session_state["reframe_result"] = reframe_result
            st.session_state["reframe_mode"] = mode
        except Exception as e:
            st.error(f"Reframe failed: {e}")
            st.stop()

# ---------------------------------------------------------------------------
# Results display
# ---------------------------------------------------------------------------
if st.session_state.get("reframe_result") and st.session_state.get("reframe_mode") == mode:
    reframe = st.session_state["reframe_result"]
    original_text = result.get("article_text", article.get("text", ""))

    st.divider()

    # Coverage indicator
    biases_addressed = reframe.get("biases_addressed", [])
    all_bias_ids = list({i.get("bias_id") for i in bias_instances})
    if biases_addressed:
        addressed_pct = int(100 * len(biases_addressed) / max(len(all_bias_ids), 1))
        st.metric("Biases addressed", f"{len(biases_addressed)}/{len(all_bias_ids)} ({addressed_pct}%)")

    gaps = reframe.get("gaps", [])
    if gaps:
        with st.expander("Gaps (information needed but unavailable in source)"):
            for g in gaps:
                st.markdown(f"- {g}")

    notes = reframe.get("notes", "")
    if notes:
        st.caption(f"Notes: {notes}")

    st.divider()

    # Side-by-side or annotated view
    if mode == "Annotated":
        st.markdown("**Annotated article**")
        annotated = reframe.get("annotated_text", "")
        # Render BIAS: annotations in a distinct style
        st.markdown(annotated)
    else:
        col1, col2 = st.columns(2)
        with col1:
            st.markdown("**Original**")
            st.markdown(original_text)
        with col2:
            st.markdown(f"**Reframed ({mode})**")
            reframed = reframe.get("reframed_text", "")
            st.markdown(reframed)

    st.divider()

    # Export
    col1, col2 = st.columns(2)
    reframed_text = reframe.get("reframed_text") or reframe.get("annotated_text", "")
    with col1:
        st.download_button(
            "Download reframed text",
            data=reframed_text,
            file_name=f"reframed_{result.get('article_id', 'article')}.txt",
            mime="text/plain",
        )
    with col2:
        st.download_button(
            "Download as markdown",
            data=f"# {title} — {mode} Reframe\n\n{reframed_text}",
            file_name=f"reframed_{result.get('article_id', 'article')}.md",
            mime="text/markdown",
        )
