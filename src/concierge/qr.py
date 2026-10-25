"""QR codes for room cards: each one opens the app at that property and room (`?property=...&room=...`)."""

import io
from urllib.parse import urlencode

import segno


def room_url(base_url: str, prop: str, room: str) -> str:
    base = (base_url or "").split("?", 1)[0].split("#", 1)[0].rstrip("/")
    return f"{base}/?{urlencode({'property': prop, 'room': room})}"


def png(url: str, scale: int = 6) -> bytes:
    buf = io.BytesIO()
    segno.make(url, error="m").save(buf, kind="png", scale=scale, border=2)
    return buf.getvalue()


def svg(url: str, scale: int = 4) -> str:
    buf = io.BytesIO()
    segno.make(url, error="m").save(buf, kind="svg", scale=scale, border=2, xmldecl=False, svgns=True)
    return buf.getvalue().decode("utf-8")
