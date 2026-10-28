"""Hotel-wide policy questions answered by the stage 7 MCP server (hotel-tools-mcp), over MCP, as the guest role.

The concierge knows the resort's activities and its own FAQ. Questions about the hotel itself (pets, check-out times,
parking, the loyalty programme) belong to the hotel group's tool server. The concierge calls it the way any MCP client
would: an MCP session to the server, with the guest role's key, so the same role-based access applies. A guest's
server only has guest tools (search_policy, lookup_booking, list_activities, create_booking_request); the concierge
uses search_policy.

The server runs in-process (an in-memory MCP transport, the same client the stage 7 web demo uses), because Streamlit
Community Cloud can't run a second service. Results come back already quarantined by the server (planted
instructions removed). If the server fails, the tool returns an error and the concierge says it can't check.
"""

import tempfile
from functools import lru_cache
from pathlib import Path

ROLE = "guest"
TENANT = "hg-demo"
SUBJECT = "concierge@resort.test"  # a guest identity with no bookings: policy questions only


@lru_cache(maxsize=1)
def session():
    """One MCP session per app process, on its own runtime folder (the server's audit log of these calls)."""
    from hotel_tools.audit import AuditLog
    from hotel_tools.auth import Principal
    from hotel_tools.config import DATA_DIR
    from hotel_tools.demo.agent import McpSession
    from hotel_tools.ratelimit import RateLimiter
    from hotel_tools.store import Store
    from hotel_tools.tools import Context

    runtime = Path(tempfile.mkdtemp(prefix="concierge-mcp-"))
    ctx = Context(Principal(ROLE, TENANT, SUBJECT), Store(DATA_DIR, runtime), AuditLog(runtime / "audit.jsonl"),
                  RateLimiter({ROLE: 120}))  # fmt: skip
    return McpSession(ctx)


def tool_names() -> list[str]:
    return [t["name"] for t in session().tools]


def hotel_policy(prop: str, question: str) -> dict:
    """search_policy on the MCP server. Returns {"passages": [{cite_as, text}], "via": ...} or {"error": ...}."""
    try:
        result = session().call("search_policy", {"question": question[:300], "property": prop})
    except Exception as exc:  # noqa: BLE001 - a server problem is a tool error the model can explain
        return {"error": f"the hotel policy service didn't answer ({type(exc).__name__})"}
    if "error" in result:
        return {"error": str(result["error"])[:200]}
    passages = [{"cite_as": f"Hotel policy: {p.get('section') or p.get('source')}", "text": p.get("text", "")[:1500]}
                for p in result.get("passages", [])]  # fmt: skip
    return {"passages": passages, "via": "MCP: hotel-tools-mcp, guest role"}
