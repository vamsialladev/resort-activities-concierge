"""Today & Tomorrow: the schedule with filters, a "starting in the next hour" banner, and a way into the chat."""

from datetime import timedelta

import streamlit as st
from sqlalchemy import select

from concierge import analytics, config, tools, ui
from concierge.db import activities

ctx = ui.context()
engine = ui.engine()
prop = ctx["property"]
today = config.today()
now = config.now()

st.title(f"{ui.ICONS[prop]} What's on at {config.PROPERTIES[prop]}")
st.caption("Synthetic schedule for a simulated resort. Tap an activity to ask the concierge or request a place.")

kids = st.toggle("Good for kids (ages 4-11)", help="Only activities a child aged 4-11 can join")
c2, c3 = st.columns(2)
when = c2.segmented_control("Time of day", ["Any", "Morning", "Afternoon", "Evening"], default="Any")
setting = c3.segmented_control("Setting", ["Any", "Indoor", "Outdoor"], default="Any")


def rows_for(day):
    q = select(activities).where(activities.c.property == prop, activities.c.date == day.isoformat())
    with engine.connect() as conn:
        rows = list(conn.execute(q.order_by(activities.c.start)))
    out = []
    for r in rows:
        if kids and r.min_age > 11:
            continue
        window = tools.TIME_WINDOWS.get((when or "Any").lower())
        if window and not window[0] <= r.start < window[1]:
            continue
        if setting in ("Indoor", "Outdoor") and bool(r.indoor) != (setting == "Indoor"):
            continue
        out.append(r)
    return out


soon = [
    r
    for r in rows_for(today)
    if now.strftime("%H:%M") <= r.start <= (now + timedelta(hours=1)).strftime("%H:%M") and r.capacity > r.booked
]
if soon:
    names = ", ".join(f"**{r.name}** at {r.start}" for r in soon)
    st.info(f"Starting in the next hour: {names}", icon=":material/schedule:")


def card(r, key: str):
    v = tools.activity_view(r)
    with st.container(border=True):
        left, right = st.columns([3, 1])
        left.markdown(f"**{r.start}–{r.end} · {r.name}**")
        place = "Indoor" if r.indoor else "Outdoor"
        price = "Free" if not r.price_usd else f"${r.price_usd:.0f} per person"
        ages = "All ages" if v["ages"] == "all ages" else f"Ages {v['ages']}"
        left.caption(f"{r.location} · {place} · {ages} · {price}")
        spots = v["spots_left"]
        finished = r.date == today.isoformat() and r.end <= now.strftime("%H:%M")
        if finished:
            right.markdown("Finished")
        else:
            right.markdown(f"{'🟢' if spots > 3 else '🟠'} {spots} left" if spots else "🔴 Full")
        b1, b2 = st.columns(2)
        if b1.button("Details", key=f"d-{key}", use_container_width=True):
            analytics.log(engine, "view", ctx["visitor"], prop, activity_name=r.name)
            st.session_state[f"open-{key}"] = True
        if st.session_state.get(f"open-{key}"):
            st.write(r.description)
        if b2.button(
            "Ask the concierge",
            key=f"a-{key}",
            use_container_width=True,
            icon=":material/chat:",
            disabled=finished,
        ):
            analytics.log(engine, "view", ctx["visitor"], prop, activity_name=r.name)
            day = "today" if r.date == today.isoformat() else "tomorrow"
            st.session_state.prefill = f"Tell me about {r.name} {day} at {r.start}. Are there places?"
            st.switch_page("pages/concierge.py")


for tab, day in zip(st.tabs(["Today", "Tomorrow"]), (today, today + timedelta(days=1)), strict=True):
    with tab:
        st.caption(day.strftime("%A %d %B"))
        rows = rows_for(day)
        if not rows:
            st.write("Nothing matches those filters. Try another time of day.")
        for r in rows:
            card(r, r.id)
