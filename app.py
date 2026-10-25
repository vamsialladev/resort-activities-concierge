"""Resort Activities Concierge: today's schedule, a concierge chat that can request bookings, and a staff side.

streamlit run app.py
"""

import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent
sys.path.insert(0, str(ROOT / "src"))

import streamlit as st

from concierge import chats, ui

st.set_page_config(page_title="Resort Activities Concierge", page_icon="🌴", layout="wide")


def shared_view(token: str):
    st.title("🌴 Concierge · shared conversation")
    st.caption("Read-only. Personal details were removed before this was saved. Synthetic data.")
    conv, msgs = chats.by_token(ui.engine(), token)
    if conv is None:
        st.warning(
            "This link is damaged or the conversation no longer exists.",
            icon=":material/link_off:",
        )
    for m in msgs:
        role = {"user": "user", "assistant": "assistant"}.get(m["role"], "assistant")
        with st.chat_message(role, avatar=":material/campaign:" if m["role"] == "notice" else None):
            st.text(m["content"])
            if m["meta"].get("sources"):
                st.caption("Sources: " + " · ".join(dict.fromkeys(m["meta"]["sources"])))
    st.link_button("Open the concierge", "/", icon=":material/chat:")


token = st.query_params.get("share")
if token:
    shared_view(token)
    st.stop()

pages = [
    st.Page(
        "pages/schedule.py",
        title="Today & Tomorrow",
        icon=":material/event:",
        default=True,
    ),
    st.Page("pages/concierge.py", title="Concierge chat", icon=":material/chat:"),
    st.Page("pages/staff.py", title="Staff", icon=":material/badge:"),
    st.Page("pages/about.py", title="About this project", icon=":material/info:"),
]
nav = st.navigation(pages)
ui.sidebar()
nav.run()
