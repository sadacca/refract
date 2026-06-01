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
# Article selector  ("All Articles" aggregates across the full corpus)
# ---------------------------------------------------------------------------
ALL_LABEL = "📊 All Articles (aggregate)"
options = [ALL_LABEL] + list(results.keys())
selected_label = st.selectbox("Select article", options)
aggregate_mode = selected_label == ALL_LABEL

if aggregate_mode:
    all_results = list(results.values())
    st.caption(f"{len(all_results)} articles · aggregate view")
else:
    r = results[selected_label]
    all_results = [r]
    col1, col2, col3 = st.columns(3)
    col1.caption(f"Mode: {r.get('mode', '—')}")
    col2.caption(f"Model: {r.get('model', '—')}")
    col3.caption(f"Words: {r['_word_count']}")
    if r.get("source_url"):
        st.caption(r["source_url"])

st.divider()

# ---------------------------------------------------------------------------
# Helper: aggregate data across a list of results
# ---------------------------------------------------------------------------
def agg_data(result_list: list[dict]) -> dict:
    """Flatten and aggregate all pass data across multiple results."""
    all_instances, all_judgments = [], []
    p1_flag_counts: dict[str, int] = {}
    p1_unflag_counts: dict[str, int] = {}
    p0_cat_paras: dict[str, list[int]] = {}   # cat → list of selection counts
    p3_finds = 0

    for res in result_list:
        p0 = res.get("pass0_result") or {}
        p1 = res.get("pass1_result") or {}
        flagged = set(p1.get("flagged_categories", []))
        cat_paras = p0.get("category_paragraphs", {})

        for cat in flagged:
            p1_flag_counts[cat] = p1_flag_counts.get(cat, 0) + 1
        all_cats = flagged | {i.get("category","") for i in res.get("bias_instances",[])}
        for cat in all_cats - flagged:
            p1_unflag_counts[cat] = p1_unflag_counts.get(cat, 0) + 1

        for cat, idxs in cat_paras.items():
            p0_cat_paras.setdefault(cat, []).append(len(idxs))

        insts = res.get("bias_instances", [])
        all_instances.extend(insts)
        p3_finds += sum(1 for i in insts if i.get("recall_probe"))

        for j in res.get("judge_result", {}).get("judgments", []):
            all_judgments.append(j)

    return {
        "instances": all_instances,
        "judgments": all_judgments,
        "p1_flag_counts": p1_flag_counts,
        "p1_unflag_counts": p1_unflag_counts,
        "p0_cat_paras": p0_cat_paras,
        "p3_finds": p3_finds,
        "n_articles": len(result_list),
    }


# ---------------------------------------------------------------------------
# Pre-compute derived data (single article or aggregate)
# ---------------------------------------------------------------------------
if aggregate_mode:
    agg = agg_data(all_results)
    instances   = agg["instances"]
    all_judgments = agg["judgments"]
    p0 = p1 = judge = summary = {}
    flagged_cats = set()
    p1_rationale = {}
    cat_paragraphs = {}
else:
    agg = agg_data([r])
    p0          = r.get("pass0_result") or {}
    p1          = r.get("pass1_result") or {}
    instances   = r.get("bias_instances", [])
    judge       = r.get("judge_result", {})
    summary     = r.get("summary", {})
    flagged_cats   = set(p1.get("flagged_categories", []))
    p1_rationale   = p1.get("rationale", {})
    cat_paragraphs = p0.get("category_paragraphs", {})
    all_judgments  = judge.get("judgments", [])

p2_instances = [i for i in instances if not i.get("recall_probe")]
p3_instances = [i for i in instances if i.get("recall_probe")]
p2_cats      = sorted({i.get("category", "?") for i in p2_instances})
verdicts     = {j["bias_id"]: j for j in all_judgments}
all_cats_in_data = (
    set(cat_paragraphs.keys()) if cat_paragraphs
    else flagged_cats | {i.get("category", "") for i in instances}
)

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
    if aggregate_mode:
        p0_cat_paras = agg["p0_cat_paras"]
        if not p0_cat_paras:
            st.info("No Pass 0 data in corpus — articles were evaluated before paragraph triage was introduced.")
        else:
            st.markdown("#### Average paragraphs selected per category across all articles")
            st.caption("Higher = more text sent to Pass 2. Zero = category consistently gated.")
            max_avg = max((sum(v)/len(v) for v in p0_cat_paras.values()), default=1)
            for cat, counts in sorted(p0_cat_paras.items(), key=lambda x: -sum(x[1])/len(x[1])):
                avg = sum(counts) / len(counts)
                zeros = sum(1 for c in counts if c == 0)
                label = f"{cat}  —  avg {avg:.1f} para(s)  ·  gated {zeros}/{len(counts)} articles"
                if avg == 0:
                    st.warning(f"⛔ {label}")
                else:
                    st.progress(avg / max(max_avg, 1), text=label)
    elif not p0:
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
    if aggregate_mode:
        flag_counts   = agg["p1_flag_counts"]
        unflag_counts = agg["p1_unflag_counts"]
        n_arts        = agg["n_articles"]
        all_cats      = sorted(set(flag_counts) | set(unflag_counts))
        if not all_cats:
            st.info("No Pass 1 data in corpus.")
        else:
            st.markdown("#### Category flagging frequency across all articles")
            st.caption("How often each category was flagged by Pass 1 vs. left to Pass 3.")
            for cat in sorted(all_cats, key=lambda c: -flag_counts.get(c, 0)):
                flagged_n   = flag_counts.get(cat, 0)
                unflagged_n = unflag_counts.get(cat, 0)
                total_seen  = flagged_n + unflagged_n
                flag_pct    = flagged_n / n_arts if n_arts else 0
                st.progress(flag_pct, text=f"{cat}  —  flagged {flagged_n}/{n_arts} articles ({flag_pct:.0%})")
    elif not p1:
        st.info("Pass 1 data not present for this article.")
    else:
        flagged_list   = sorted(flagged_cats)
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
    if aggregate_mode and not p2_instances:
        st.info("No Pass 2 instances across corpus.")
    elif aggregate_mode:
        st.markdown("#### Pass 2 instance counts by bias across all articles")
        bias_occ: dict[str, dict] = {}
        for inst in p2_instances:
            bid = inst["bias_id"]
            if bid not in bias_occ:
                bias_occ[bid] = {"name": inst["bias_name"], "cat": inst.get("category","?"),
                                 "occ": 0, "confirmed": 0, "rejected": 0}
            bias_occ[bid]["occ"] += len(inst.get("occurrences", []))
            v = verdicts.get(bid, {}).get("verdict", "")
            if v == "confirmed": bias_occ[bid]["confirmed"] += 1
            elif v == "rejected": bias_occ[bid]["rejected"] += 1
        rows = sorted(bias_occ.values(), key=lambda x: -x["occ"])
        st.dataframe(
            [{"Bias": b["name"], "Category": b["cat"], "Occurrences": b["occ"],
              "Confirmed": b["confirmed"], "Rejected": b["rejected"]} for b in rows],
            use_container_width=True, hide_index=True,
        )
    elif not p2_instances:
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
    if aggregate_mode:
        unflag_counts = agg["p1_unflag_counts"]
        n_arts        = agg["n_articles"]
        recall_finds  = agg["p3_finds"]
        p3_confirmed  = sum(1 for i in p3_instances if verdicts.get(i["bias_id"], {}).get("verdict") == "confirmed")

        c1, c2, c3 = st.columns(3)
        c1.metric("Total recall-probe finds", recall_finds)
        c2.metric("Confirmed by judge", p3_confirmed)
        c3.metric("Articles with P3 finds", len({i.get("article_id","") for i in p3_instances if i.get("article_id")}))

        if unflag_counts:
            st.markdown("#### Categories most often left to Pass 3")
            max_u = max(unflag_counts.values())
            for cat, cnt in sorted(unflag_counts.items(), key=lambda x: -x[1]):
                st.progress(cnt / max_u, text=f"{cat}  —  unflagged {cnt}/{n_arts} articles")

        if p3_instances:
            st.markdown("#### Pass 3 finds (all articles)")
            bias_p3: dict[str, dict] = {}
            for inst in p3_instances:
                bid = inst["bias_id"]
                bias_p3.setdefault(bid, {"name": inst["bias_name"], "count": 0, "confirmed": 0})
                bias_p3[bid]["count"] += 1
                if verdicts.get(bid, {}).get("verdict") == "confirmed":
                    bias_p3[bid]["confirmed"] += 1
            for info in sorted(bias_p3.values(), key=lambda x: -x["count"]):
                badge = "✅" if info["confirmed"] else "🔵"
                st.markdown(f"- {badge} **{info['name']}** — found {info['count']}x, confirmed {info['confirmed']}x")
        else:
            st.success("No recall-probe finds across corpus — Pass 1/2 coverage appears complete.")
        # skip the rest of the tab's single-article block
    else:
        probed_cats = sorted(all_cats_in_data - flagged_cats) if flagged_cats else []

        c1, c2 = st.columns(2)
        c1.metric("Categories probed", len(probed_cats) if probed_cats else "—")
        c2.metric("New instances found", len(p3_instances))

        if not probed_cats and not p3_instances:
            st.info(
                "Pass 3 data cannot be fully reconstructed — flagged category list unavailable."
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
                st.success("Recall probes found no additional instances — Pass 1/2 coverage appears complete.")
                for c in probed_cats:
                    st.markdown(f"- {c}")


# ── Pass 4 ──────────────────────────────────────────────────────────────────
with t4:
    if aggregate_mode:
        confirmed_agg = [j for j in all_judgments if j.get("verdict") == "confirmed"]
        suspect_agg   = [j for j in all_judgments if j.get("verdict") == "suspect"]
        rejected_agg  = [j for j in all_judgments if j.get("verdict") == "rejected"]
        n_judged      = len(all_judgments)
        precision     = len(confirmed_agg) / n_judged if n_judged else 0

        c1, c2, c3, c4 = st.columns(4)
        c1.metric("Total judgments", n_judged)
        c2.metric("✅ Confirmed", len(confirmed_agg))
        c3.metric("⚠️ Suspect", len(suspect_agg))
        c4.metric("❌ Rejected", len(rejected_agg))
        st.progress(precision, text=f"Corpus confirmation rate: {precision:.0%}")

        st.markdown("#### Verdict breakdown by bias type")
        bias_verdict: dict[str, dict] = {}
        for j in all_judgments:
            bid = j["bias_id"]
            bias_name = next((i["bias_name"] for i in instances if i["bias_id"] == bid), bid)
            if bid not in bias_verdict:
                bias_verdict[bid] = {"name": bias_name, "confirmed": 0, "suspect": 0, "rejected": 0}
            v = j.get("verdict", "")
            if v in bias_verdict[bid]:
                bias_verdict[bid][v] += 1
        rows = sorted(bias_verdict.values(), key=lambda x: -(x["confirmed"]))
        st.dataframe(
            [{"Bias": b["name"], "✅ Confirmed": b["confirmed"],
              "⚠️ Suspect": b["suspect"], "❌ Rejected": b["rejected"]} for b in rows],
            use_container_width=True, hide_index=True,
        )
    elif not judge:
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
        + (" Showing aggregate across all articles." if aggregate_mode else "")
    )

    # Aggregate-mode uses combined data; single-article mode uses per-article data
    _p2_inst  = p2_instances
    _p3_inst  = p3_instances
    _verdicts = verdicts
    _flagged  = flagged_cats if not aggregate_mode else set(agg["p1_flag_counts"].keys())
    _all_jdg  = all_judgments

    # Q2: Did Pass 1 triage lead to specific, grounded instances?
    st.markdown("---")
    st.markdown("#### Q2 — Did Pass 1 category triage lead to specific, well-grounded instances?")
    if not _flagged:
        st.info("Pass 1 data unavailable.")
    else:
        cats_with_finds = {i.get("category") for i in _p2_inst}
        cats_empty      = _flagged - cats_with_finds
        p2_confirmed    = sum(1 for i in _p2_inst if _verdicts.get(i["bias_id"], {}).get("verdict") == "confirmed")
        p2_rejected     = sum(1 for i in _p2_inst if _verdicts.get(i["bias_id"], {}).get("verdict") == "rejected")
        hit_rate        = len(cats_with_finds) / len(_flagged) if _flagged else 0

        c1, c2, c3 = st.columns(3)
        c1.metric("Flagged cats with instances", f"{len(cats_with_finds)}/{len(_flagged)} ({hit_rate:.0%})")
        c2.metric("Pass 2 instances confirmed", p2_confirmed)
        c3.metric("Pass 2 instances rejected", p2_rejected)

        if cats_empty:
            st.warning(
                f"**Triage over-flagged:** {', '.join(sorted(cats_empty))} were flagged "
                f"but produced zero instances. Pass 1 may be too inclusive for these categories."
            )
        if hit_rate == 1.0 and p2_rejected == 0:
            st.success("Every flagged category produced at least one confirmed instance — triage well-calibrated.")
        elif p2_rejected > len(_p2_inst) // 2:
            st.error("More than half of Pass 2 instances were rejected — identification criteria may be too loose.")

    # Q3: Did Pass 3 reveal systematic gaps?
    st.markdown("---")
    st.markdown("#### Q3 — Did Pass 3 reveal systematic gaps missed by Pass 1/2?")
    recall_finds = agg["p3_finds"] if aggregate_mode else summary.get("recall_probe_finds", len(_p3_inst))
    p3_confirmed = sum(1 for i in _p3_inst if _verdicts.get(i["bias_id"], {}).get("verdict") == "confirmed")

    c1, c2 = st.columns(2)
    c1.metric("Recall-probe finds", recall_finds)
    c2.metric("Confirmed by judge", p3_confirmed)

    if recall_finds == 0:
        st.success("Pass 3 found nothing new — Pass 1/2 coverage appears complete.")
    elif p3_confirmed > 0:
        missed = sorted({i.get("category") for i in _p3_inst})
        st.warning(
            f"**Pass 3 surfaced confirmed instances** in: {', '.join(missed)}. "
            f"Consider loosening triage criteria or reviewing Pass 0 paragraph selection for these categories."
        )
    else:
        st.info(f"Pass 3 found {recall_finds} instance(s) but none confirmed — likely noise.")

    # Q4: Were findings convincing or mostly false positives?
    st.markdown("---")
    st.markdown("#### Q4 — Were Pass 2/3 findings convincing, or mostly false positives?")
    n_judged    = len(_all_jdg)
    n_confirmed = sum(1 for j in _all_jdg if j.get("verdict") == "confirmed")
    n_suspect   = sum(1 for j in _all_jdg if j.get("verdict") == "suspect")
    n_rejected  = sum(1 for j in _all_jdg if j.get("verdict") == "rejected")
    precision   = n_confirmed / n_judged if n_judged else 0

    if not _all_jdg:
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
            for j in _all_jdg if j.get("verdict") == "rejected"
        })
        if rejected_biases:
            st.markdown(f"**Rejected bias types:** {', '.join(rejected_biases)}")

        if not aggregate_mode and judge.get("notes"):
            st.markdown(f"**Judge notes:** {judge['notes']}")
