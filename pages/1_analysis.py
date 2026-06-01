"""
Bias analysis dashboard — three tabs:
  1. Per-article: select any evaluated article and inspect its detections
  2. Cross-article: aggregate stats and prevalence across the corpus
  3. By bias: drill into a single bias or category across all articles
"""
import json
import sys
from pathlib import Path

import streamlit as st

ROOT = Path(__file__).parent.parent
sys.path.insert(0, str(ROOT))

from config import FRAMEWORK_VERSION, TAXONOMY_VERSION, PROCESSED_DIR

st.set_page_config(page_title="Bias Analysis — Refract", layout="wide")
st.title("Bias Analysis")
st.caption(f"Framework {FRAMEWORK_VERSION} · Taxonomy {TAXONOMY_VERSION}")


# ---------------------------------------------------------------------------
# Data loading
# ---------------------------------------------------------------------------
@st.cache_data(ttl=60)
def load_results() -> list[dict]:
    results = []
    for p in sorted(PROCESSED_DIR.glob(f"*_{FRAMEWORK_VERSION}.json")):
        try:
            d = json.loads(p.read_text())
            d["_word_count"] = len(d.get("article_text", "").split())
            results.append(d)
        except Exception:
            continue
    return results


def bias_table(results: list[dict]) -> dict:
    """Return aggregated per-bias stats across all results."""
    counts: dict[str, dict] = {}
    for r in results:
        aid = r["article_id"]
        for inst in r.get("bias_instances", []):
            bid = inst["bias_id"]
            if bid not in counts:
                counts[bid] = {
                    "name": inst["bias_name"],
                    "category": inst.get("category", "Unknown"),
                    "occurrences": 0,
                    "articles": set(),
                    "high_conf": 0,
                    "excerpts": [],
                }
            occ_list = inst.get("occurrences", [])
            counts[bid]["occurrences"] += len(occ_list)
            counts[bid]["articles"].add(aid)
            counts[bid]["high_conf"] += sum(1 for o in occ_list if o.get("confidence") == "high")
            for o in occ_list:
                counts[bid]["excerpts"].append({
                    "article_id": aid,
                    "title": r.get("title", ""),
                    "url": r.get("source_url", ""),
                    "excerpt": o.get("excerpt", ""),
                    "explanation": o.get("explanation", ""),
                    "confidence": o.get("confidence", ""),
                    "text_region": o.get("text_region", ""),
                })
    return counts


results = load_results()
n_articles = len(results)

if not results:
    st.warning("No evaluated articles found. Run the batch_eval workflow first.")
    st.stop()

bias_stats = bias_table(results)

# ---------------------------------------------------------------------------
# Tabs
# ---------------------------------------------------------------------------
tab1, tab2, tab3 = st.tabs(["Per-Article", "Cross-Article", "By Bias"])


# ── Tab 1: Per-article ───────────────────────────────────────────────────────
with tab1:
    article_options = {
        f"{r.get('title', r['article_id'])[:70]} ({r['_word_count']} words)": r
        for r in results
    }
    selected_label = st.selectbox("Select article", list(article_options.keys()))
    r = article_options[selected_label]
    instances = r.get("bias_instances", [])
    s = r["summary"]
    judge = r.get("judge_result", {})

    st.markdown(f"### {r.get('title', r['article_id'])}")
    if r.get("source_url"):
        st.caption(r["source_url"])

    # Headline metrics
    c1, c2, c3, c4, c5 = st.columns(5)
    c1.metric("Words", r["_word_count"])
    c2.metric("Bias types", s.get("bias_type_count", 0))
    c3.metric("Occurrences", s.get("total_occurrences", 0))
    c4.metric("Low confidence", s.get("low_confidence_count", 0))
    c5.metric("Judge quality", judge.get("overall_quality", "—").capitalize())

    if judge.get("notes"):
        st.info(f"**Judge notes:** {judge['notes']}")

    st.divider()

    if not instances:
        st.info("No bias instances detected.")
    else:
        # Group by category
        by_cat: dict[str, list] = {}
        for inst in instances:
            by_cat.setdefault(inst.get("category", "Unknown"), []).append(inst)

        # Build verdict lookup
        verdicts = {j["bias_id"]: j.get("verdict", "") for j in judge.get("judgments", [])}

        for cat, cat_instances in sorted(by_cat.items()):
            st.markdown(f"#### {cat}")
            for inst in cat_instances:
                verdict = verdicts.get(inst["bias_id"], "")
                verdict_badge = {"confirmed": "✅", "suspect": "⚠️", "rejected": "❌"}.get(verdict, "")
                with st.expander(
                    f"{verdict_badge} **{inst['bias_name']}** — "
                    f"{len(inst.get('occurrences', []))} occurrence(s), severity: {inst.get('severity', '?')}"
                ):
                    for i, occ in enumerate(inst.get("occurrences", []), 1):
                        conf_color = {"high": "🟢", "medium": "🟡", "low": "🔴"}.get(occ.get("confidence", ""), "")
                        st.markdown(f"**{i}. {conf_color} {occ.get('confidence', '').capitalize()} confidence**")
                        st.markdown(f"> *\"{occ.get('excerpt', '')}\"*")
                        st.caption(occ.get("explanation", ""))
                        st.caption(f"Region: {occ.get('text_region', '?')}")

                    if verdict:
                        j_entry = next((j for j in judge.get("judgments", []) if j.get("bias_id") == inst["bias_id"]), {})
                        st.markdown(f"**Judge verdict: {verdict_badge} {verdict.capitalize()}**")
                        if j_entry.get("rationale"):
                            st.caption(j_entry["rationale"])


# ── Tab 2: Cross-article ────────────────────────────────────────────────────
with tab2:
    total_occ = sum(s.get("total_occurrences", 0) for r in results for s in [r["summary"]])

    c1, c2, c3, c4 = st.columns(4)
    c1.metric("Articles", n_articles)
    c2.metric("Total occurrences", total_occ)
    c3.metric("Distinct bias types", len(bias_stats))
    c4.metric("Avg occ / article", f"{total_occ / n_articles:.1f}" if n_articles else "—")

    st.divider()

    # Category distribution
    cat_counts: dict[str, int] = {}
    for r in results:
        for inst in r.get("bias_instances", []):
            cat = inst.get("category", "Unknown")
            cat_counts[cat] = cat_counts.get(cat, 0) + len(inst.get("occurrences", []))

    st.markdown("#### Occurrences by category")
    max_cat = max(cat_counts.values()) if cat_counts else 1
    for cat, cnt in sorted(cat_counts.items(), key=lambda x: -x[1]):
        st.progress(cnt / max_cat, text=f"{cat}  —  {cnt} occurrences")

    st.divider()

    # Bias prevalence table
    st.markdown("#### Bias prevalence across articles")
    rows = []
    for bid, info in sorted(bias_stats.items(), key=lambda x: -x[1]["occurrences"]):
        rows.append({
            "Bias": info["name"],
            "Category": info["category"],
            "Occurrences": info["occurrences"],
            "Articles hit": len(info["articles"]),
            "% of corpus": f"{100 * len(info['articles']) // n_articles}%",
            "High confidence": info["high_conf"],
        })
    st.dataframe(rows, use_container_width=True, hide_index=True)

    st.divider()

    # Per-article strip
    st.markdown("#### Article-level summary")
    article_rows = []
    for r in sorted(results, key=lambda x: -x["summary"].get("total_occurrences", 0)):
        s = r["summary"]
        article_rows.append({
            "Title": (r.get("title") or r["article_id"])[:60],
            "Words": r["_word_count"],
            "Bias types": s.get("bias_type_count", 0),
            "Occurrences": s.get("total_occurrences", 0),
            "Dominant category": (s.get("dominant_categories") or ["—"])[0],
            "Judge quality": r.get("judge_result", {}).get("overall_quality", "—"),
        })
    st.dataframe(article_rows, use_container_width=True, hide_index=True)


# ── Tab 3: By bias ───────────────────────────────────────────────────────────
with tab3:
    # Category filter → bias selector
    all_categories = sorted({info["category"] for info in bias_stats.values()})
    selected_cat = st.selectbox(
        "Filter by category", ["All categories"] + all_categories
    )

    filtered_biases = {
        bid: info for bid, info in bias_stats.items()
        if selected_cat == "All categories" or info["category"] == selected_cat
    }

    if not filtered_biases:
        st.info("No biases found for this category.")
        st.stop()

    bias_options = {info["name"]: bid for bid, info in sorted(filtered_biases.items(), key=lambda x: -x[1]["occurrences"])}
    selected_bias_name = st.selectbox("Select bias", list(bias_options.keys()))
    selected_bid = bias_options[selected_bias_name]
    info = bias_stats[selected_bid]

    st.markdown(f"### {info['name']}")
    st.caption(f"Category: {info['category']}")

    c1, c2, c3 = st.columns(3)
    c1.metric("Total occurrences", info["occurrences"])
    c2.metric("Articles", f"{len(info['articles'])} / {n_articles}")
    c3.metric("High confidence", info["high_conf"])

    st.divider()
    st.markdown("#### All occurrences across articles")

    conf_filter = st.multiselect(
        "Confidence", ["high", "medium", "low"], default=["high", "medium", "low"]
    )

    for ex in info["excerpts"]:
        if ex["confidence"] not in conf_filter:
            continue
        conf_color = {"high": "🟢", "medium": "🟡", "low": "🔴"}.get(ex["confidence"], "")
        title = (ex.get("title") or ex["article_id"])[:60]
        with st.container():
            st.markdown(f"**{conf_color} {title}**")
            if ex.get("url"):
                st.caption(ex["url"])
            st.markdown(f"> *\"{ex['excerpt']}\"*")
            st.caption(ex.get("explanation", ""))
            st.divider()
