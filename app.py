import streamlit as st

st.set_page_config(
    page_title="Refract",
    page_icon="🔍",
    layout="wide",
    initial_sidebar_state="expanded",
)

st.title("Refract")
st.markdown(
    """
**Cognitive bias analysis and reframing for written text.**

Refract identifies cognitive bias patterns in news articles using a multi-pass LLM evaluation
pipeline grounded in cognitive psychology literature. Every detection is documented with the
exact excerpt, its location in the text, and an explanation of the bias mechanism.

*Cognitive bias is a normal feature of human cognition, not an editorial sin.*

---

### Pages

| Page | Description |
|---|---|
| **Bias Analysis** | Three-tab dashboard: per-article detections, cross-article corpus stats, and per-bias drill-down across all evaluated articles |
| **Bias Index** | Browse the full cognitive bias taxonomy — definitions, identification criteria, linguistic signals, and reference examples |
| **Article Evaluation** | Submit a URL or paste text to run a live full-pipeline evaluation |
| **Article Reframe** | Rewrite an evaluated article with identified biases reduced |
| **Framework Dashboard** | Taxonomy status, precomputed artifact health, pending example review queue, and corpus-level quality metrics |
| **Pipeline Inspector** | Per-pass output viewer for any evaluated article — Pass 0 through Pass 4 tabs plus a Judge Summary answering three diagnostic questions about triage quality, recall gaps, and false positive rate |

---

### How the pipeline works

Each article passes through up to four LLM stages:

1. **Pass 0 — Paragraph triage** *(small model)*
   Chunks the article and maps each bias category to the paragraphs worth deep review.
   Categories with zero relevant paragraphs are routed to a lightweight recall probe instead of a full identification call.

2. **Pass 1 — Category triage** *(small model, deep mode only)*
   Flags which broad bias categories are plausibly present, narrowing the scope for Pass 2.

3. **Pass 2 — Bias identification** *(large model)*
   For each flagged category, identifies specific bias instances using the taxonomy's identification criteria, linguistic signals, and few-shot reference examples — operating only on the paragraphs selected in Pass 0.

4. **Pass 3 — Recall probes** *(small model, deep mode only)*
   Batched yes/no sweep across unflagged categories to surface any instances Pass 1 missed.

5. **Pass 4 — LLM judge** *(large model)*
   Independent pointwise review of all detected instances; rejected instances are filtered from the final output.

---

*Framework v0.1.0 · Taxonomy v0.1.0*
"""
)
