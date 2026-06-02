import json
import sys
from pathlib import Path

import streamlit as st

ROOT = Path(__file__).parent.parent
sys.path.insert(0, str(ROOT))

from config import FRAMEWORK_VERSION, TAXONOMY_VERSION, PRECOMPUTED_DIR, PROCESSED_DIR, PENDING_EXAMPLES_DIR
from components.corpus import load_corpus, load_taxonomy, render_refresh_button

st.set_page_config(page_title="Framework Dashboard — Refract", layout="wide")
st.title("Framework Dashboard")
col_title, col_refresh = st.columns([8, 1])
col_title.caption(f"Framework {FRAMEWORK_VERSION} · Taxonomy {TAXONOMY_VERSION}")
with col_refresh:
    render_refresh_button()

# ---------------------------------------------------------------------------
# Taxonomy status
# ---------------------------------------------------------------------------
st.header("Taxonomy Status")

taxonomy = load_taxonomy()
biases = taxonomy.get("biases", [])

total = len(biases)
canonical = sum(1 for b in biases if b.get("status") == "canonical")
verified_ex = sum(1 for b in biases if b.get("examples_status") == "verified")
pending_ex = sum(1 for b in biases if b.get("examples_status") == "pending")

cols = st.columns(4)
cols[0].metric("Total biases", total)
cols[1].metric("Canonical entries", canonical)
cols[2].metric("Verified examples", verified_ex)
cols[3].metric("Pending examples", pending_ex)

# ---------------------------------------------------------------------------
# Pending example review queue
# ---------------------------------------------------------------------------
st.header("Pending Example Review")

pending_files = list(PENDING_EXAMPLES_DIR.glob("*.json")) if PENDING_EXAMPLES_DIR.exists() else []

if not pending_files:
    st.info("No pending examples to review. Run the **precompute_examples** GitHub Action to generate candidates.")
else:
    st.markdown(f"**{len(pending_files)}** bias entries have candidate examples awaiting review.")

    for pf in sorted(pending_files):
        bias_id = pf.stem
        try:
            candidates = json.loads(pf.read_text())
        except Exception:
            continue

        bias_name = next((b["name"] for b in biases if b["id"] == bias_id), bias_id)

        with st.expander(f"**{bias_name}** ({bias_id})"):
            positives = candidates.get("positive", [])
            near_misses = candidates.get("near_miss", [])
            contrast = candidates.get("contrast")

            st.markdown("**Positive examples (should exhibit the bias):**")
            for i, ex in enumerate(positives, 1):
                excerpt = ex.get("excerpt", "")
                mechanism = ex.get("mechanism", "")
                domain = ex.get("domain", "")
                st.markdown(f"{i}. [{domain}] *{excerpt}*")
                st.caption(f"Mechanism: {mechanism}")

            st.markdown("**Near-miss examples (should NOT exhibit the bias):**")
            for ex in near_misses:
                st.markdown(f"- *{ex.get('excerpt', '')}*")
                st.caption(f"Why not: {ex.get('why_not', '')}")

            if contrast:
                st.markdown(f"**Contrast ({contrast.get('bias', '')}):**")
                st.markdown(f"*{contrast.get('excerpt', '')}*")
                st.caption(f"Distinction: {contrast.get('distinction', '')}")

            col1, col2 = st.columns(2)
            with col1:
                if st.button(f"Accept into taxonomy", key=f"accept_{bias_id}"):
                    st.warning(
                        "To accept: copy the examples into taxonomy.json under "
                        f"`reference_examples` for `{bias_id}`, set "
                        "`examples_status: verified`, and commit."
                    )
            with col2:
                if st.button(f"Reject / regenerate", key=f"reject_{bias_id}"):
                    st.info("Delete the pending file and re-run the precompute_examples workflow.")

# ---------------------------------------------------------------------------
# Corpus stats (derived live from processed records)
# ---------------------------------------------------------------------------
st.header("Corpus Stats")

corpus = load_corpus(FRAMEWORK_VERSION)

if not corpus:
    st.info("No evaluation results yet. Run the batch_eval workflow or evaluate an article first.")
else:
    total_instances = sum(len(r.get("bias_instances", [])) for r in corpus)
    total_occ = sum(r.get("summary", {}).get("total_occurrences", 0) for r in corpus)
    cols = st.columns(3)
    cols[0].metric("Articles evaluated", len(corpus))
    cols[1].metric("Total bias instances", total_instances)
    cols[2].metric("Total occurrences", total_occ)

    cat_dist: dict[str, int] = {}
    bias_arts: dict[str, dict] = {}
    for r in corpus:
        for inst in r.get("bias_instances", []):
            cat = inst.get("category", "Unknown")
            cat_dist[cat] = cat_dist.get(cat, 0) + len(inst.get("occurrences", []))
            bid = inst["bias_id"]
            if bid not in bias_arts:
                bias_arts[bid] = {"name": inst["bias_name"], "articles": set()}
            bias_arts[bid]["articles"].add(r["article_id"])

    if cat_dist:
        st.markdown("**Occurrences by category:**")
        for cat, count in sorted(cat_dist.items(), key=lambda x: -x[1]):
            st.progress(count / max(cat_dist.values()), text=f"{cat}: {count}")

    if bias_arts:
        st.markdown("**Most prevalent biases (% of articles):**")
        for bid, info in sorted(bias_arts.items(), key=lambda x: -len(x[1]["articles"]))[:10]:
            pct = round(100 * len(info["articles"]) / len(corpus))
            st.markdown(f"- **{info['name']}**: {pct}% of articles")

# ---------------------------------------------------------------------------
# Precomputed artifacts status
# ---------------------------------------------------------------------------
st.header("Precomputed Artifacts")

index_path = PRECOMPUTED_DIR / "taxonomy_index.json"
if not index_path.exists():
    st.warning("Precomputed artifacts not found. Run `python scripts/precompute.py`.")
else:
    index = json.loads(index_path.read_text())
    bias_blocks = list((PRECOMPUTED_DIR / "bias_blocks").glob("*.txt"))
    probe_blocks = list((PRECOMPUTED_DIR / "recall_probe_blocks").glob("*.txt"))
    reframe_blocks = list((PRECOMPUTED_DIR / "reframe_blocks").glob("*.txt"))

    cols = st.columns(4)
    cols[0].metric("Taxonomy index entries", len(index))
    cols[1].metric("Bias blocks", len(bias_blocks))
    cols[2].metric("Recall probe blocks", len(probe_blocks))
    cols[3].metric("Reframe blocks", len(reframe_blocks))
    st.success(f"Artifacts current for taxonomy {TAXONOMY_VERSION}")
