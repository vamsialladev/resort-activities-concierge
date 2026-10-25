"""About this project: what it is, how to try it, and the measured results (read from the saved eval reports)."""

import streamlit as st

from concierge import config, ui

ui.context()
REPORTS = config.ROOT / "eval" / "reports"

st.title("About this project")
st.markdown(
    """
**Stage 6 of a simulated client engagement** for a fictional hotel group with two properties, Beach Resort and
Mountain Lodge. Guests scan a QR code in their room, see what's on today, and chat with a concierge that knows the
schedule and the resort's policies, and can send a booking request that staff approve. Everything here is
synthetic: activities, prices, policies and stays.

**How to try it**

- *Today & Tomorrow*: filter by kids, time of day and indoor/outdoor; "Ask the concierge" opens a chat about it.
- *Concierge chat*: try "My family has two kids. What can we do tomorrow morning?", then "Yes, please request the
  kids club for our two kids." Open "Steps" under an answer to see each tool call and its result.
- To try the stay lookup, use booking reference **BR-4821** with last name **Rivera** (Beach Resort) or
  **ML-7310** / **Moreau** (Mountain Lodge). They're made up.
- *Staff*: approving or declining a request posts an update into the guest's chat. It needs the staff password.

**What it won't do**: confirm, charge, refund or make anything free. Requests stay PENDING until a person decides.
"""
)
for name in sorted(REPORTS.glob("*.md"), reverse=True)[:2]:
    with st.expander(f"Eval report: {name.name}"):
        st.markdown(name.read_text(encoding="utf-8"))
st.link_button(
    "Code, architecture and decisions on GitHub",
    config.REPO_URL,
    icon=":material/code:",
)
