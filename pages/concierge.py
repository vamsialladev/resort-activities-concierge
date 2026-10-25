"""Concierge chat: streamed answers with a step timeline, saved conversations, a share link, staff updates."""

import time

import anthropic
import streamlit as st

from concierge import agent, analytics, chats, config, limits, suggest, tools, ui

ctx = ui.context()
engine = ui.engine()
prop, visitor = ctx["property"], ctx["visitor"]
s = st.session_state
st.query_params["v"] = visitor  # bookmark this address to come back to your conversations
s.setdefault("asked", 0)
s.setdefault("times", [])
FRIENDLY_ERROR = "The concierge didn't answer in time. Please try again in a minute."

st.title(f"{ui.ICONS[prop]} Concierge")
st.caption(
    f"Ask about activities at {config.PROPERTIES[prop]}, the kids club, the spa or the resort's policies. I can send a "
    "booking request; staff approve it. Synthetic data."
)

with st.sidebar:
    st.divider()
    if st.button("New conversation", icon=":material/add:", use_container_width=True):
        s.pop("conversation", None)
        s.pop("share", None)
        st.rerun()
    past = [c for c in chats.list_for(engine, visitor) if c["property"] == prop]
    if past:
        st.caption("Your conversations (saved with this page's address)")
    for c in past[:10]:
        label = ("▸ " if c["id"] == s.get("conversation") else "") + c["title"]
        if st.button(label, key=f"c-{c['id']}", use_container_width=True):
            s.conversation = c["id"]
            s.pop("share", None)
            st.rerun()


def show_steps(steps: list[dict]):
    for i, step in enumerate(steps, 1):
        st.markdown(f"**{i}. {step['name']}** · {step['seconds']:.2f} s")
        st.json({"input": step["input"], "result": step["result"]}, expanded=False)


def show(m: dict):
    if m["role"] == "notice":
        st.success(m["content"], icon=":material/campaign:")
        return
    with st.chat_message(m["role"]):
        if m["role"] == "user":
            st.markdown(m["content"])
            if m["meta"].get("understood_as"):
                st.caption(f"Understood as: {m['meta']['understood_as']}")
            return
        st.markdown(m["content"])
        meta = m["meta"]
        if meta.get("sources"):
            st.caption("Sources searched: " + " · ".join(dict.fromkeys(meta["sources"])))
        if meta.get("requests"):
            st.caption("Request sent: " + ", ".join(meta["requests"]) + " · PENDING until staff approve it")
        if meta.get("steps"):
            label = (
                f"Steps: {len(meta['steps'])} · {meta.get('seconds', 0):.1f} s · {meta.get('calls', 0)} model call(s)"
            )
            with st.expander(label):
                show_steps(meta["steps"])


conv, msgs = chats.load(engine, s.conversation, visitor) if s.get("conversation") else (None, [])
for m in msgs:
    show(m)


@st.fragment(run_every="20s")
def updates():
    """New staff decisions on this conversation appear without a page reload."""
    if not s.get("conversation"):
        return
    _, fresh = chats.load(engine, s.conversation, visitor)
    seen = {m["id"] for m in msgs}
    for m in fresh:
        if m["role"] == "notice" and m["id"] not in seen:
            show(m)


updates()


def answer(message: str):
    reason = limits.blocked(engine, s.times, s.asked, time.time())
    if reason:
        st.info(reason, icon=":material/hourglass:")
        return
    s.asked += 1
    s.times = [t for t in s.times if time.time() - t < 60] + [time.time()]
    if not s.get("conversation"):
        s.conversation = chats.create(engine, visitor, prop, ctx["room"], message)
    history = s.setdefault("live", {}).get(s.conversation) or chats.turns(msgs)
    tctx = tools.ToolContext(engine, prop, conversation_id=s.conversation)
    turn = agent.Turn(message, prop)
    with st.chat_message("user"):
        st.markdown(message)
    with st.chat_message("assistant"):
        try:
            status = st.status("Working on it...", expanded=False)
            st.write_stream(
                agent.respond(
                    message,
                    tctx,
                    history,
                    on_step=lambda step: status.write(f"✓ {step.name}"),
                    turn=turn,
                    room=ctx["room"],
                )
            )
            status.update(label=f"Done: {len(turn.steps)} steps", state="complete")
        except (
            anthropic.APIConnectionError,
            anthropic.APITimeoutError,
            anthropic.APIStatusError,
        ):
            st.error(FRIENDLY_ERROR, icon=":material/cloud_off:")
            return
        except Exception:  # noqa: BLE001 - never show a trace to a guest
            st.error(
                "Something went wrong on my side. Please try asking another way.",
                icon=":material/error:",
            )
            return
    limits.record(engine, turn.usage)
    chats.add_message(engine, s.conversation, "user", message, {"understood_as": turn.understood_as})
    chats.add_message(
        engine,
        s.conversation,
        "assistant",
        turn.answer,
        {
            "sources": turn.sources,
            "requests": turn.requests,
            "steps": [vars(x) for x in turn.steps],
            "seconds": round(turn.seconds, 2),
            "calls": turn.usage["calls"],
            "next": suggest.after(turn, {m["content"] for m in msgs} | {message}),
        },
    )
    s.live[s.conversation] = (history + [{"question": turn.understood_as or message, "answer": turn.answer}])[-6:]
    analytics.record_turn(engine, turn, visitor)
    for rid in turn.requests:
        analytics.log(engine, "request", visitor, prop, detail=rid)
    s.pop("share", None)
    st.rerun()


last = next((m for m in reversed(msgs) if m["role"] == "assistant"), None)
options = last["meta"].get("next", []) if last else suggest.first(prop)
picked = None
if options:
    st.caption("Try:" if not last else "Next:")
    for col, (i, q) in zip(st.columns(len(options)), enumerate(options), strict=True):
        if col.button(q, key=f"s-{len(msgs)}-{i}", use_container_width=True):
            picked = q

if msgs and st.button("Share this conversation", icon=":material/link:"):
    s.share = chats.share_token(engine, s.conversation)
if s.get("share"):
    st.caption("Read-only link (personal details were removed when the messages were saved):")
    st.code(chats.share_url(ui.base_url(), s.share), language=None, wrap_lines=True)

message = st.chat_input("Ask the concierge...") or picked or s.pop("prefill", None)
if message:
    answer(message)
