import json
import sys
from pathlib import Path

import streamlit as st

ROOT = Path(__file__).parent.parent
sys.path.insert(0, str(ROOT))

st.set_page_config(page_title="Bias Index — Refract", layout="wide")
st.title("Cognitive Bias Index")

TAXONOMY_PATH = ROOT / "bias_index" / "taxonomy.json"

try:
    taxonomy = json.loads(TAXONOMY_PATH.read_text())
    biases = taxonomy["biases"]
except Exception as e:
    st.error(f"Could not load taxonomy: {e}")
    st.stop()

st.caption(f"Taxonomy {taxonomy.get('version')} · {len(biases)} entries")

# ---------------------------------------------------------------------------
# Filters
# ---------------------------------------------------------------------------
categories = sorted({b["category"] for b in biases})
statuses = sorted({b.get("status", "provisional") for b in biases})
example_statuses = sorted({b.get("examples_status", "pending") for b in biases})

col1, col2, col3, col4 = st.columns([3, 2, 2, 2])
with col1:
    search = st.text_input("Search", placeholder="name, alias, definition...")
with col2:
    cat_filter = st.multiselect("Category", categories)
with col3:
    status_filter = st.multiselect("Status", statuses)
with col4:
    ex_filter = st.multiselect("Examples", example_statuses)

# Apply filters
filtered = biases
if search:
    q = search.lower()
    filtered = [
        b for b in filtered
        if q in b["name"].lower()
        or any(q in a.lower() for a in b.get("aliases", []))
        or q in b.get("definition", "").lower()
    ]
if cat_filter:
    filtered = [b for b in filtered if b["category"] in cat_filter]
if status_filter:
    filtered = [b for b in filtered if b.get("status", "provisional") in status_filter]
if ex_filter:
    filtered = [b for b in filtered if b.get("examples_status", "pending") in ex_filter]

st.markdown(f"**{len(filtered)}** of {len(biases)} biases")
st.divider()

# ---------------------------------------------------------------------------
# Bias cards
# ---------------------------------------------------------------------------
STATUS_ICONS = {"canonical": "✅", "provisional": "🔶"}
EX_ICONS = {"verified": "✅", "pending": "⏳"}
SEVERITY_ICONS = {"high": "🔴", "medium": "🟡", "low": "🟢"}

for b in filtered:
    status_icon = STATUS_ICONS.get(b.get("status", "provisional"), "🔶")
    ex_icon = EX_ICONS.get(b.get("examples_status", "pending"), "⏳")
    severity_icon = SEVERITY_ICONS.get(b.get("severity_signal", "medium"), "🟡")

    with st.expander(
        f"{severity_icon} **{b['name']}**  ·  {b['category']}  "
        f"{status_icon}  {ex_icon}"
    ):
        cols = st.columns([2, 1])
        with cols[0]:
            st.markdown(f"**Definition:** {b['definition']}")
            if b.get("aliases"):
                st.caption("Also known as: " + ", ".join(b["aliases"]))

            st.markdown(f"**Mechanism:** {b.get('mechanism', '—')}")

            if b.get("literature_description"):
                st.markdown(f"**Literature:** {b['literature_description']}")

        with cols[1]:
            st.markdown(f"**Category:** {b['category']}")
            if b.get("subcategory"):
                st.caption(b["subcategory"])
            st.markdown(f"**Severity:** {b.get('severity_signal', '—').title()}")
            st.markdown(f"**Status:** {b.get('status', 'provisional').title()}")
            st.markdown(f"**Examples:** {b.get('examples_status', 'pending').title()}")

        st.markdown("**Identification criteria:**")
        for c in b.get("identification_criteria", []):
            st.markdown(f"- {c}")

        st.markdown("**Linguistic signals:**")
        for s in b.get("linguistic_signals", []):
            st.markdown(f"- {s}")

        if b.get("journalism_example"):
            st.markdown("**Journalism example:**")
            st.markdown(f"> {b['journalism_example']}")

        if b.get("reframing_strategy"):
            st.markdown("**Reframing strategy:**")
            st.markdown(b["reframing_strategy"])
            if b.get("reframing_example"):
                st.markdown(f"*Reframed: {b['reframing_example']}*")

        confusions = b.get("common_confusions", [])
        if confusions:
            st.markdown("**Commonly confused with:**")
            for c in confusions:
                st.markdown(f"- **{c['bias']}**: {c['distinction']}")

        sources = b.get("sources", [])
        if sources:
            st.markdown("**Sources:**")
            for s in sources:
                author = s.get("author", "")
                year = s.get("year", "")
                title = s.get("title", "")
                doi = s.get("doi", "")
                line = f"- {author} ({year}). *{title}*"
                if doi:
                    line += f" DOI: {doi}"
                st.markdown(line)

        ref = b.get("reference_examples", {})
        positives = ref.get("positive", [])
        if positives:
            st.markdown("**Reference examples (positive):**")
            for i, ex in enumerate(positives, 1):
                excerpt = ex.get("excerpt", ex) if isinstance(ex, dict) else str(ex)
                domain = ex.get("domain", "") if isinstance(ex, dict) else ""
                st.markdown(f"{i}. [{domain}] *{excerpt}*" if domain else f"{i}. *{excerpt}*")
