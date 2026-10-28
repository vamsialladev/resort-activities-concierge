"""What every page shares: the database (with a friendly "waking up" state), the visitor, property and room from
the address, and the sidebar links."""

import streamlit as st

from concierge import chats, config, db, retrieval, seed

ICONS = {"beach-resort": "🏖️", "mountain-lodge": "🏔️"}


@st.cache_resource(show_spinner=False)
def _engine():
    return db.make_engine()


@st.cache_resource(show_spinner=False)
def _ready(day: str) -> bool:
    """Tables exist and the 14-day schedule from `day` is filled. Runs once per day per app process."""
    seed.ensure_window(_engine(), config.today())
    retrieval.warm_up()
    return True


def engine():
    """The engine, after the schedule is ready. Neon's free tier sleeps; waking it takes a few seconds."""
    try:
        with st.spinner("Waking up the database (the free tier sleeps when nobody's around)..."):
            _ready(config.today().isoformat())
            conn = db.connect(_engine())
            conn.close()
    except db.WakingUp:
        st.warning(
            "The database is still waking up. Please refresh in a few seconds.",
            icon=":material/hourglass_top:",
        )
        st.stop()
    return _engine()


def context() -> dict:
    """Visitor, property and room: from the address the first time (a room QR code sets property and room), then
    from the session. The visitor ID is random and anonymous."""
    s = st.session_state
    qp = st.query_params
    if "visitor" not in s:
        s.visitor = qp.get("v") or chats.new_visitor_id()
    if "property" not in s:
        s.property = qp.get("property") if qp.get("property") in config.PROPERTIES else "beach-resort"
    if "room" not in s:
        room = (qp.get("room") or "")[:8]
        s.room = room if room.isalnum() else ""
    return {"visitor": s.visitor, "property": s.property, "room": s.room}


def sidebar():
    ctx = context()
    with st.sidebar:
        options = list(config.PROPERTIES)
        prop = st.selectbox(
            "You're staying at",
            options,
            index=options.index(ctx["property"]),
            format_func=lambda p: f"{ICONS[p]} {config.PROPERTIES[p]}",
        )
        if prop != ctx["property"]:
            st.session_state.property = prop
            st.session_state.pop("conversation", None)
            st.rerun()
        if ctx["room"]:
            st.caption(f"Room {ctx['room']} (from your room's QR code)")
        st.divider()
        if config.DEMO_VIDEO_URL:
            st.link_button(
                "Watch the 90-second demo",
                config.DEMO_VIDEO_URL,
                icon=":material/play_circle:",
            )
        st.link_button("GitHub", config.REPO_URL, icon=":material/code:")
        st.link_button("Portfolio", config.PORTFOLIO_URL, icon=":material/person:")
        st.caption("Stage 6 of a simulated client engagement. Synthetic data: no real guests, rooms or prices.")
        st.caption(
            "Privacy: questions, answers and each step's trace are logged to improve the service, with personal "
            "details removed first, and deleted after 30 days."
        )


def base_url() -> str:
    return config.APP_URL or (st.context.url or "").split("?", 1)[0]
