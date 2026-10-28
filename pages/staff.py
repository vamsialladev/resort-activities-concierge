"""Staff: approve or decline booking requests, see what guests ask and book, and print room QR codes."""

import time

import streamlit as st
from hotelplatform import admin_gate, admin_ui

from concierge import analytics, config, ops, qr, staff, ui

ctx = ui.context()
engine = ui.engine()
s = st.session_state
LOCK_AFTER_S = 30 * 60

st.title("🗂️ Staff")
if not config.staff_password():
    st.info(
        "Staff sign-in isn't set up on this deployment (ADMIN_PASSWORD). The README shows the staff side.",
        icon=":material/lock:",
    )
    st.stop()
# The shared gate (hotel-ai-platform): 5 wrong tries lock it for 15 minutes, counted per browser session and per
# server process, and 30 minutes without activity signs staff out.
gate = s.setdefault("staff_gate", admin_gate.SessionGate())
if gate.unlocked and not admin_gate.still_signed_in(gate, idle_s=LOCK_AFTER_S):
    st.info("Locked after 30 minutes. Please sign in again.", icon=":material/lock_clock:")
if not gate.unlocked:
    with st.form("signin"):
        password = st.text_input("Staff password", type="password")
        if st.form_submit_button("Sign in"):
            ok, problem = admin_gate.attempt(gate, password, config.staff_password(), scope="staff")
            if ok:
                st.rerun()
            time.sleep(config.GUESS_DELAY_S)  # slows guessing
            st.error(problem if problem != admin_gate.WRONG else "That password didn't work.")
    st.stop()
if st.sidebar.button("Sign out", icon=":material/logout:"):
    admin_gate.sign_out(gate)
    st.rerun()

prop = ctx["property"]
pending_tab, analytics_tab, qr_tab, traces_tab = st.tabs(["Pending requests", "Analytics", "Room QR codes", "Traces"])

with traces_tab:  # the shared ops view: every guest message's trace as a waterfall, errors, cost, guardrail blocks
    st.caption('Paste a guest\'s "Reference: ..." into Trace reference to find their message.')
    admin_ui.render(ops.store(), app_title="Concierge", version=ops.running_version(),
                    dependencies=ops.dependencies, require_gate=False, title="Traces", **ops.caps())  # fmt: skip

with pending_tab:
    pending = [r for r in staff.requests(engine) if r["property"] == prop]
    if not pending:
        st.write(f"No pending requests at {config.PROPERTIES[prop]}.")
    for r in pending:
        with st.container(border=True):
            left, right = st.columns([3, 2])
            left.markdown(f"**{r['name']}** · {r['date']} {r['start']} · party of {r['party_size']}")
            total = r["price_usd"] * r["party_size"]
            left.caption(
                f"{r['id']} · {'free' if not total else f'${total:.0f}'} · "
                f"{max(r['capacity'] - r['booked'], 0)} places left · stay {r['stay_ref'] or 'not given'} · "
                f"requested {r['created_at'][11:16]}"
            )
            if r["note"]:
                left.caption(f"Guest note: {r['note']}")
            note = right.text_input("Note to the guest (optional)", key=f"n-{r['id']}")
            a, d = right.columns(2)
            for col, approve, label in ((a, True, "Approve"), (d, False, "Decline")):
                if col.button(
                    label,
                    key=f"{label}-{r['id']}",
                    use_container_width=True,
                    type="primary" if approve else "secondary",
                ):
                    try:
                        staff.decide(engine, r["id"], approve, note)
                        st.toast(f"{label}d {r['id']}; the guest sees it in their chat.")
                    except staff.DecisionError as exc:
                        st.error(str(exc))
                    st.rerun()
    with st.expander("Recent decisions"):
        done = [r for r in staff.requests(engine, status=None) if r["status"] != "PENDING" and r["property"] == prop]
        st.dataframe(
            [
                {
                    k: r[k]
                    for k in (
                        "id",
                        "name",
                        "date",
                        "start",
                        "party_size",
                        "status",
                        "decided_at",
                    )
                }
                for r in done[:30]
            ],
            hide_index=True,
        )

with analytics_tab:
    st.caption(f"{config.PROPERTIES[prop]}, last 30 days, from this demo's real usage (questions are stored redacted).")
    c1, c2 = st.columns(2)
    with c1:
        st.subheader("Top questions")
        top = analytics.top_questions(engine, prop)
        st.dataframe(top, hide_index=True) if top else st.write("No questions yet.")
    with c2:
        st.subheader("Unanswered questions")
        st.caption("The FAQ search found nothing, or the answer said it didn't know: candidates for new FAQ entries.")
        un = analytics.unanswered_questions(engine, prop)
        st.dataframe(un, hide_index=True) if un else st.write("None so far.")
    st.subheader("Activities: viewed vs requested")
    vr = analytics.viewed_vs_requested(engine, prop)
    st.bar_chart(
        [{"activity": r["activity"], "views": r["views"], "requests": r["requests"]} for r in vr],
        x="activity",
        y=["views", "requests"],
        stack=False,
    )
    ignored = [r["activity"] for r in vr if r["ignored"]]
    st.caption("Ignored (no views, no requests): " + (", ".join(ignored) if ignored else "none"))
    st.subheader("Peak times")
    hours = analytics.peak_hours(engine, prop)
    st.bar_chart(
        [{"hour": f"{h:02d}:00", "questions": n} for h, n in hours.items()],
        x="hour",
        y="questions",
    )

with qr_tab:
    st.write("Print a card for each room: scanning it opens today's schedule with the property and room set.")
    room = st.text_input("Room number", value="214", max_chars=8)
    if room.isalnum():
        url = qr.room_url(ui.base_url(), prop, room)
        st.image(qr.png(url), width=220)
        st.code(url, language=None)
        st.download_button(
            "Download PNG",
            qr.png(url, scale=10),
            file_name=f"qr-{prop}-{room}.png",
            mime="image/png",
        )
    else:
        st.caption("Letters and numbers only.")
