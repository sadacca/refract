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

Refract identifies cognitive bias patterns in news articles using a taxonomy grounded
in cognitive psychology literature. Every bias found is documented with the exact excerpt,
location in the text, and an explanation of the mechanism — not a judgment of the source.

*Cognitive bias is a normal feature of human cognition, not an editorial sin.*

---

**Use the sidebar to navigate:**
- **Article Evaluation** — paste or fetch a news article URL for a full bias analysis
- **Article Reframe** — rewrite the evaluated article with identified biases reduced
- **Bias Index** — browse the full taxonomy of cognitive biases
- **Framework Dashboard** — evaluation quality metrics and taxonomy status
"""
)
