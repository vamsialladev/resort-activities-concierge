"""Suggested next messages after an answer: picked from what the turn did, no model call.

Each one is something the concierge can actually do (eval cases cover each kind), so a click never dead-ends.
"""

FIRST = {
    "beach-resort": [
        "My family has two kids. What can we do tomorrow morning?",
        "What's on this evening for adults?",
        "What's the spa's cancellation policy?",
    ],
    "mountain-lodge": [
        "My family has two kids. What can we do tomorrow morning?",
        "How hard is the guided morning trek?",
        "Is anything on indoors this afternoon?",
    ],
}
AFTER_ACTIVITIES = [
    "What should the kids bring?",
    "What about the afternoon?",
    "Is anything indoors?",
]
AFTER_FAQ = ["What can we do this afternoon?", "What's on tomorrow evening?"]
AFTER_REQUEST = ["What happens next with my request?", "Can I cancel it later?"]


def first(prop: str) -> list[str]:
    return FIRST[prop]


def after(turn, asked: set[str], n: int = 3) -> list[str]:
    tools_used = {s.name.removeprefix("Tool: ") for s in turn.steps}
    if turn.requests:
        pool = AFTER_REQUEST
    elif "search_activities" in tools_used:
        pool = AFTER_ACTIVITIES
    elif "search_faq" in tools_used:
        pool = AFTER_FAQ
    else:
        pool = FIRST.get(turn.property, [])
    return [q for q in pool if q not in asked][:n]
