"""
Pipeline Inspector — per-pass output viewer with LLM-as-judge summaries.

Tabs: Pass 0 | Pass 1 | Pass 2 | Pass 3 | Pass 4 | Judge Summary

Judge Summary answers three diagnostic questions:
  Q2: Did Pass 1 category triage lead to specific, well-grounded instances?
  Q3: Did Pass 3 reveal systematic gaps — categories or instances missed by Pass 1/2?
  Q4: Were the Pass 2/3 findings convincing, or mostly false positives?
"""
import json
import sys
from pathlib import Path

import streamlit as st

ROOT = Path(__file__).parent.parent
sys.path.insert(0, str(ROOT))

from config import FRAMEWORK_VERSION, TAXONOMY_VERSION, PROCESSED_DIR

st.set_page_config(page_title="Pipeline Inspector — Refract", layout="wide")
st.title("Pipeline Inspector")
st.caption(f"Framework {FRAMEWORK_VERSION} · Taxonomy {TAXONOMY_VERSION}")


# ---------------------------------------------------------------------------
# Data loading
# ---------------------------------------------------------------------------
@st.cache_data(ttl=60)
def load_results() -> dict[str, dict]:
    out = {}
    for p in sorted(PROCESSED_DIR.glob(f"*_{FRAMEWORK_VERSION}.json")):
        try:
            d = json.loads(p.read_text())
            label = (d.get("title") or d.get("source_url") or d["article_id"])[:70]
            d["_word_count"] = len(d.get("article_text", "").split())
            out[label] = d
        except Exception:
            continue
    return out


results = load_results()

if not results:
    st.warning("No evaluated articles found. Run the batch_eval workflow first.")
    st.stop()

# ---------------------------------------------------------------------------
# Article selector
# ---------------------------------------------------------------------------
selected_label = st.selectbox(
    "Select article",
    list(results.keys()),
    format_func=lambda x: x,
)
r = results[selected_label]

st.markdown(f"**{r.get('title', r['article_id'])}**")
col1, col2, col3 = st.columns(3)
col1.caption(f"Mode: {r.get('mode', '—')}")
col2.caption(f"Model: {r.get('model', '—')}")
col3.caption(f"Words: {r['_word_count']}")
if r.get("source_url"):
    st.caption(r["source_url"])

st.divider()

# ---------------------------------------------------------------------------
# Pre-compute derived data used across tabs
# ---------------------------------------------------------------------------
p0        = r.get("pass0_result") or {}
p1        = r.get("pass1_result") or {}
instances = r.get("bias_instances", [])
judge     = r.get("judge_result", {})
summary   = r.get("summary", {})

flagged_cats   = set(p1.get("flagged_categories", []))
p1_rationale   = p1.get("rationale", {})
cat_paragraphs = p0.get("category_paragraphs", {})

# Split instances by origin
p2_instances = [i for i in instances if not i.get("recall_probe")]
p3_instances = [i for i in instances if i.get("recall_probe")]

# Judge verdict lookup keyed by bias_id
verdicts = {j["bias_id"]: j for j in judge.get("judgments", [])}

# Derive which categories went through each path
all_cats_in_data = (
    set(cat_paragraphs.keys()) if cat_paragraphs
    else flagged_cats | {i.get("category", "") for i in instances}
)
p2_cats  = sorted({i.get("category", "?") for i in p2_instances})
p3_cats  = sorted({i.get("category", "?") for i in p3_instances})

# ---------------------------------------------------------------------------
# Tabs
# ---------------------------------------------------------------------------
t0, t1, t2, t3, t4, tj = st.tabs(
    ["Pass 0 — Para Triage", "Pass 1 — Category Triage",
     "Pass 2 — Identification", "Pass 3 — Recall Probes",
     "Pass 4 — Judge Verdicts", "Judge Summary"]
)


# ── Pass 0 ──────────────────────────────────────────────────────────────────
with t0:
    if not p0:
        st.info("Pass 0 data not present — this article was evaluated before paragraph triage was introduced.")
    else:
        n_paras = p0.get("paragraph_count", 0)
        st.metric("Total paragraphs", n_paras)

        st.markdown("#### Category → paragraph assignments")
        st.caption(
            "Paragraphs selected per category. Categories with 0 paragraphs are "
            "gated from Pass 2 and routed to Pass 3 instead."
        )

        max_sel = max((len(v) for v in cat_paragraphs.values()), default=1)
        for cat, idxs in sorted(cat_paragraphs.items(), key=lambda x: -len(x[1])):
            pct = len(idxs) / n_paras if n_paras else 0
            label = f"{cat}  —  {len(idxs)}/{n_paras} paragraphs ({pct:.0%})"
            if len(idxs) == 0:
                st.warning(f"⛔ {cat}  —  0 paragraphs selected → gated from Pass 2")
            else:
                st.progress(len(idxs) / max(max_sel, 1), text=label)

        avg = summary.get("pass0_avg_paragraphs_per_category", "—")
        st.caption(f"Average paragraphs per category: {avg}")


# ── Pass 1 ──────────────────────────────────────────────────────────────────
with t1:
    if not p1:
        st.info("Pass 1 data not present for this article.")
    else:
        flagged_list = sorted(flagged_cats)
        unflagged_list = sorted(all_cats_in_data - flagged_cats)

        c1, c2 = st.columns(2)
        c1.metric("Categories flagged", len(flagged_list))
        c2.metric("Categories skipped to Pass 3", len(unflagged_list))

        st.markdown("#### Flagged categories")
        for cat in flagged_list:
            reason = p1_rationale.get(cat, "—")
            with st.expander(f"✅ **{cat}**"):
                st.write(reason)

        if unflagged_list:
            st.markdown("#### Unflagged — routed to Pass 3 recall probes")
            for cat in unflagged_list:
                st.markdown(f"- {cat}")


# ── Pass 2 ──────────────────────────────────────────────────────────────────
with t2:
    if not p2_instances:
        st.info("No instances identified in Pass 2.")
    else:
        c1, c2 = st.columns(2)
        c1.metric("Instances found", len(p2_instances))
        c2.metric("Categories with finds", len(p2_cats))

        # Empty categories (flagged but produced nothing)
        flagged_with_finds = {i.get("category") for i in p2_instances}
        empty_flagged = [c for c in flagged_cats if c not in flagged_with_finds]
        if empty_flagged:
            st.warning(f"Flagged but no instances found: {', '.join(sorted(empty_flagged))}")

        st.markdown("#### Instances by category")
        by_cat: dict[str, list] = {}
        for inst in p2_instances:
            by_cat.setdefault(inst.get("category", "?"), []).append(inst)

        for cat, cat_insts in sorted(by_cat.items()):
            st.markdown(f"**{cat}**")
            for inst in cat_insts:
                v = verdicts.get(inst["bias_id"], {})
                badge = {"confirmed": "✅", "suspect": "⚠️", "rejected": "❌"}.get(v.get("verdict", ""), "🔵")
                with st.expander(f"{badge} {inst['bias_name']}  ·  {len(inst.get('occurrences', []))} occurrence(s)"):
                    for occ in inst.get("occurrences", []):
                        conf = {"high": "🟢", "medium": "🟡", "low": "🔴"}.get(occ.get("confidence", ""), "")
                        st.markdown(f"{conf} **{occ.get('confidence','?').capitalize()} confidence**")
                        st.markdown(f"> *\"{occ.get('excerpt', '')}\"*")
                        st.caption(occ.get("explanation", ""))
                    if v:
                        st.markdown(f"**Judge: {v.get('verdict','').capitalize()}** — {v.get('rationale','')}")


# ── Pass 3 ──────────────────────────────────────────────────────────────────
with t3:
    probed_cats = sorted(all_cats_in_data - flagged_cats) if flagged_cats else []

    c1, c2 = st.columns(2)
    c1.metric("Categories probed", len(probed_cats) if probed_cats else "—")
    c2.metric("New instances found", len(p3_instances))

    if not probed_cats and not p3_instances:
        st.info(
            "Pass 3 data cannot be fully reconstructed — flagged category list unavailable. "
            "Showing recall-probe-flagged instances only."
            if not flagged_cats else
            "All categories were flagged by Pass 1; Pass 3 had nothing to probe."
        )

    if p3_instances:
        st.markdown("#### Instances surfaced by recall probes")
        for inst in p3_instances:
            v = verdicts.get(inst["bias_id"], {})
            badge = {"confirmed": "✅", "suspect": "⚠️", "rejected": "❌"}.get(v.get("verdict", ""), "🔵")
            with st.expander(f"{badge} {inst['bias_name']}  ·  category: {inst.get('category','?')}"):
                for occ in inst.get("occurrences", []):
                    st.markdown(f"> *\"{occ.get('excerpt', '')}\"*")
                    st.caption(occ.get("explanation", ""))
                if v:
                    st.markdown(f"**Judge: {v.get('verdict','').capitalize()}** — {v.get('rationale','')}")
    else:
        if probed_cats:
            st.success("Recall probes found no additional instances — Pass 1/2 coverage appears complete for these categories.")
            st.markdown("**Categories probed (all clean):**")
            for c in probed_cats:
                st.markdown(f"- {c}")


# ── Pass 4 ──────────────────────────────────────────────────────────────────
with t4:
    if not judge:
        st.info("No judge result available for this article.")
    else:
        judgments = judge.get("judgments", [])
        confirmed = [j for j in judgments if j.get("verdict") == "confirmed"]
        suspect   = [j for j in judgments if j.get("verdict") == "suspect"]
        rejected  = [j for j in judgments if j.get("verdict") == "rejected"]

        c1, c2, c3, c4 = st.columns(4)
        c1.metric("Overall quality", judge.get("overall_quality", "—").capitalize())
        c2.metric("✅ Confirmed", len(confirmed))
        c3.metric("⚠️ Suspect", len(suspect))
        c4.metric("❌ Rejected", len(rejected))

        if judge.get("notes"):
            st.info(judge["notes"])

        st.markdown("#### Per-bias verdicts")
        for verdict_label, group, color in [
            ("Confirmed", confirmed, "✅"),
            ("Suspect", suspect, "⚠️"),
            ("Rejected", rejected, "❌"),
        ]:
            if group:
                st.markdown(f"**{color} {verdict_label}**")
                for j in group:
                    bias_name = next(
                        (i["bias_name"] for i in instances if i["bias_id"] == j["bias_id"]),
                        j["bias_id"]
                    )
                    with st.expander(f"{bias_name}"):
                        st.write(j.get("rationale", "—"))


# ── Judge Summary ────────────────────────────────────────────────────────────
with tj:
    st.markdown("### Diagnostic questions")
    st.caption(
        "Three questions to assess pipeline quality end-to-end. "
        "Answers are derived from stored pass outputs — no additional LLM calls."
    )

    # Q2: Did Pass 1 triage lead to specific, grounded instances?
    st.markdown("---")
    st.markdown("#### Q2 — Did Pass 1 category triage lead to specific, well-grounded instances?")
    if not flagged_cats:
        st.info("Pass 1 data unavailable.")
    else:
        total_p2_occ = sum(len(i.get("occurrences", [])) for i in p2_instances)
        cats_with_finds = {i.get("category") for i in p2_instances}
        cats_empty      = flagged_cats - cats_with_finds
        p2_confirmed    = sum(1 for i in p2_instances if verdicts.get(i["bias_id"], {}).get("verdict") == "confirmed")
        p2_rejected     = sum(1 for i in p2_instances if verdicts.get(i["bias_id"], {}).get("verdict") == "rejected")
        hit_rate        = len(cats_with_finds) / len(flagged_cats) if flagged_cats else 0

        c1, c2, c3 = st.columns(3)
        c1.metric("Flagged cats with instances", f"{len(cats_with_finds)}/{len(flagged_cats)} ({hit_rate:.0%})")
        c2.metric("Pass 2 instances confirmed", p2_confirmed)
        c3.metric("Pass 2 instances rejected", p2_rejected)

        if cats_empty:
            st.warning(
                f"**Triage over-flagged:** {', '.join(sorted(cats_empty))} were flagged "
                f"but produced zero instances. Pass 1 may be too inclusive for these categories."
            )
        if hit_rate == 1.0 and p2_rejected == 0:
            st.success("Every flagged category produced at least one confirmed instance — triage well-calibrated.")
        elif p2_rejected > len(p2_instances) // 2:
            st.error("More than half of Pass 2 instances were rejected — identification criteria may be too loose.")

    # Q3: Did Pass 3 reveal systematic gaps?
    st.markdown("---")
    st.markdown("#### Q3 — Did Pass 3 reveal systematic gaps missed by Pass 1/2?")
    unflagged_count = len(all_cats_in_data - flagged_cats) if flagged_cats else "?"
    recall_finds    = summary.get("recall_probe_finds", len(p3_instances))
    p3_confirmed    = sum(1 for i in p3_instances if verdicts.get(i["bias_id"], {}).get("verdict") == "confirmed")

    c1, c2, c3 = st.columns(3)
    c1.metric("Categories sent to Pass 3", unflagged_count)
    c2.metric("New instances found", recall_finds)
    c3.metric("Confirmed by judge", p3_confirmed)

    if recall_finds == 0:
        st.success("Pass 3 found nothing new — Pass 1 triage covered the relevant categories.")
    elif p3_confirmed > 0:
        missed = sorted({i.get("category") for i in p3_instances})
        st.warning(
            f"**Pass 3 surfaced confirmed instances** in: {', '.join(missed)}. "
            f"These categories were missed or gated by Pass 1/Pass 0. "
            f"Consider loosening triage criteria or reviewing Pass 0 paragraph selection for these categories."
        )
    else:
        st.info(f"Pass 3 found {recall_finds} instance(s) but none were confirmed by the judge — likely noise.")

    # Q4: Were findings convincing or mostly false positives?
    st.markdown("---")
    st.markdown("#### Q4 — Were Pass 2/3 findings convincing, or mostly false positives?")
    judgments   = judge.get("judgments", [])
    n_judged    = len(judgments)
    n_confirmed = sum(1 for j in judgments if j.get("verdict") == "confirmed")
    n_suspect   = sum(1 for j in judgments if j.get("verdict") == "suspect")
    n_rejected  = sum(1 for j in judgments if j.get("verdict") == "rejected")
    precision   = n_confirmed / n_judged if n_judged else 0

    if not judgments:
        st.info("No judge verdicts available.")
    else:
        c1, c2, c3, c4 = st.columns(4)
        c1.metric("Judged", n_judged)
        c2.metric("Confirmed", n_confirmed)
        c3.metric("Suspect", n_suspect)
        c4.metric("Rejected", n_rejected)
        st.progress(precision, text=f"Confirmation rate: {precision:.0%}")

        if precision >= 0.75:
            st.success(f"**High precision ({precision:.0%})** — most detections were well-grounded.")
        elif precision >= 0.5:
            st.warning(
                f"**Medium precision ({precision:.0%})** — roughly half the detections are solid. "
                f"Review rejected bias types for over-broad identification criteria."
            )
        else:
            st.error(
                f"**Low precision ({precision:.0%})** — majority of detections rejected. "
                f"Identification criteria or Pass 0 paragraph selection likely too permissive."
            )

        rejected_biases = sorted({
            next((i["bias_name"] for i in instances if i["bias_id"] == j["bias_id"]), j["bias_id"])
            for j in judgments if j.get("verdict") == "rejected"
        })
        if rejected_biases:
            st.markdown(f"**Rejected bias types:** {', '.join(rejected_biases)}")

        if judge.get("notes"):
            st.markdown(f"**Judge notes:** {judge['notes']}")
