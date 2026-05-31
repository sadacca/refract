"""
Reusable components for rendering bias evaluation results.
"""
import streamlit as st

CATEGORY_COLORS = {
    "Confirmation & Belief Perseverance": "#e74c3c",
    "Framing & Anchoring": "#e67e22",
    "Availability & Salience": "#f39c12",
    "Attribution & Causation": "#27ae60",
    "In-Group & Social": "#2980b9",
    "Narrative & Pattern": "#8e44ad",
    "Authority & Social Proof": "#16a085",
    "Affect & Emotional Reasoning": "#c0392b",
    "Omission & Selective Emphasis": "#7f8c8d",
    "Temporal & Recency": "#2c3e50",
}

SEVERITY_COLORS = {"high": "🔴", "medium": "🟡", "low": "🟢"}
CONFIDENCE_LABELS = {"high": "High confidence", "medium": "Medium confidence", "low": "Low confidence"}


def render_summary_bar(summary: dict) -> None:
    cols = st.columns(4)
    cols[0].metric("Bias types detected", summary.get("bias_type_count", 0))
    cols[1].metric("Total occurrences", summary.get("total_occurrences", 0))
    cols[2].metric("Low confidence", summary.get("low_confidence_count", 0))
    cols[3].metric("Recall probe finds", summary.get("recall_probe_finds", 0))

    dominant = summary.get("dominant_categories", [])
    if dominant:
        st.markdown("**Dominant categories:** " + " · ".join(dominant))

    by_region = summary.get("by_region", {})
    if any(by_region.values()):
        region_str = " | ".join(
            f"{r.title()}: {n}" for r, n in by_region.items() if n > 0
        )
        st.caption(f"By text region — {region_str}")


def render_bias_card(instance: dict, index: int) -> None:
    category = instance.get("category", "")
    color = CATEGORY_COLORS.get(category, "#95a5a6")
    severity = instance.get("severity", "medium")
    recall = instance.get("recall_probe", False)
    author = instance.get("author_exhibiting", True)
    source = instance.get("source_reporting", False)

    with st.expander(
        f"{SEVERITY_COLORS.get(severity, '🟡')} **{instance.get('bias_name', 'Unknown')}**"
        f"  —  {category}"
        + (" *(recall probe)*" if recall else ""),
        expanded=(index == 0),
    ):
        label_parts = []
        if author:
            label_parts.append("Author exhibiting")
        if source:
            label_parts.append("Source reporting")
        if label_parts:
            st.caption(" · ".join(label_parts))

        occurrences = instance.get("occurrences", [])
        for i, occ in enumerate(occurrences, 1):
            excerpt = occ.get("excerpt", "")
            explanation = occ.get("explanation", "")
            confidence = occ.get("confidence", "medium")
            region = occ.get("text_region", "body")
            para = occ.get("paragraph_index")

            st.markdown(f"**Occurrence {i}** — {region.title()}"
                        + (f", paragraph {para}" if para is not None else ""))
            st.markdown(f"> {excerpt}")
            st.markdown(f"*{explanation}*")
            st.caption(CONFIDENCE_LABELS.get(confidence, confidence))
            if i < len(occurrences):
                st.divider()

        # Judge verdict
        # (verdict injected by caller if available)
        verdict = instance.get("_judge_verdict")
        if verdict:
            v = verdict.get("verdict", "")
            rationale = verdict.get("rationale", "")
            icon = {"confirmed": "✅", "suspect": "⚠️", "rejected": "❌"}.get(v, "")
            st.caption(f"Judge: {icon} {v.title()} — {rationale}")


def render_article_highlighted(article_text: str, bias_instances: list[dict]) -> None:
    """
    Render article text with bias excerpts highlighted.
    Uses simple markdown bold since Streamlit doesn't support inline HTML color spans
    without unsafe_allow_html.
    """
    if not bias_instances:
        st.text(article_text)
        return

    # Collect all (start, end, bias_name, category) tuples
    spans = []
    for inst in bias_instances:
        cat = inst.get("category", "")
        name = inst.get("bias_name", "")
        for occ in inst.get("occurrences", []):
            start = occ.get("char_start")
            end = occ.get("char_end")
            excerpt = occ.get("excerpt", "")
            if start is not None and end is not None:
                spans.append((start, end, name, cat, excerpt))

    if not spans:
        # Fall back to showing article with excerpts called out separately
        st.markdown(article_text)
        if any(occ.get("excerpt") for inst in bias_instances for occ in inst.get("occurrences", [])):
            st.caption("Detected excerpts (char offsets unavailable for inline highlighting):")
            for inst in bias_instances:
                for occ in inst.get("occurrences", []):
                    ex = occ.get("excerpt", "")
                    if ex:
                        st.markdown(f'> "{ex}" — *{inst.get("bias_name", "")}*')
        return

    # Sort by start position
    spans.sort(key=lambda x: x[0])

    # Build highlighted HTML
    parts = []
    pos = 0
    for start, end, name, cat, excerpt in spans:
        if start > pos:
            parts.append(article_text[pos:start])
        color = CATEGORY_COLORS.get(cat, "#95a5a6")
        parts.append(
            f'<mark style="background-color:{color}20; border-bottom: 2px solid {color}; '
            f'padding: 0 2px;" title="{name}">{article_text[start:end]}</mark>'
        )
        pos = end
    if pos < len(article_text):
        parts.append(article_text[pos:])

    st.markdown("".join(parts), unsafe_allow_html=True)
