"""Business case calculator for the concierge: per-property SaaS, activity uplift, optional vendor commission, group
licence. Every input is an assumption (docs/BUSINESS_CASE.md says why); the result is a projection, not a measurement.

    python scripts/business_case.py               # base case, 2 properties
    python scripts/business_case.py --scenarios   # pessimistic / base / optimistic table
    python scripts/business_case.py --properties 40 --scenarios
"""

import argparse
import sys
from dataclasses import dataclass, replace


@dataclass(frozen=True)
class Assumptions:
    rooms: int = 180  # per property
    occupancy: float = 0.72
    guests_per_room: float = 2.3
    adoption: float = 0.20  # share of staying guests who open the concierge (room QR code)
    messages_per_user: float = 6.0
    paid_requests_per_user: float = 0.20  # paid activity requests per guest who uses it
    approval_rate: float = 0.85
    incremental_share: float = 0.25  # bookings that wouldn't have happened without the concierge
    avg_ticket_usd: float = 62.0  # average paid activity, per person
    party_size: float = 2.0
    activity_margin: float = 0.55  # contribution margin on activity revenue
    desk_minutes_saved_per_user: float = 2.5  # questions the activities desk no longer answers
    staff_cost_per_hour: float = 24.0
    saas_per_property_month: float = 450.0  # what the hotel group pays (cost to the hotel)
    vendor_commission: float = 0.0  # share of third-party activity revenue paid to the provider (option)
    ai_cost_per_message: float = 0.00066  # measured: $0.66 per 1,000 messages, dev eval 2026-10-25 (3 runs)
    hosting_per_month: float = 25.0  # Postgres + app hosting at pilot scale


SCENARIOS = {
    "pessimistic": dict(
        adoption=0.10, paid_requests_per_user=0.10, incremental_share=0.15, desk_minutes_saved_per_user=1.0
    ),
    "base": {},
    "optimistic": dict(
        adoption=0.35, paid_requests_per_user=0.35, incremental_share=0.40, desk_minutes_saved_per_user=4.0
    ),
}


def per_year(a: Assumptions, properties: int) -> dict:
    guests = a.rooms * a.occupancy * 365 / 3.0 * a.guests_per_room * properties  # 3-night average stay
    users = guests * a.adoption
    approved = users * a.paid_requests_per_user * a.approval_rate
    incremental_revenue = approved * a.incremental_share * a.avg_ticket_usd * a.party_size
    margin = incremental_revenue * a.activity_margin
    desk = users * a.desk_minutes_saved_per_user / 60 * a.staff_cost_per_hour
    ai = users * a.messages_per_user * a.ai_cost_per_message
    saas = a.saas_per_property_month * 12 * properties
    commission = incremental_revenue * a.vendor_commission
    hosting = a.hosting_per_month * 12
    net = margin + desk - ai - saas - commission - hosting
    return {
        "guests using it": users,
        "approved paid requests": approved,
        "incremental activity revenue": incremental_revenue,
        "margin on that revenue": margin,
        "desk time saved ($)": desk,
        "AI cost": ai,
        "SaaS fee": saas,
        "vendor commission": commission,
        "hosting": hosting,
        "net value": net,
    }


def money(v: float) -> str:
    return f"${v:,.0f}"


def main(argv=None) -> int:
    p = argparse.ArgumentParser(description=__doc__.split("\n\n")[0])
    p.add_argument("--properties", type=int, default=2)
    p.add_argument("--scenarios", action="store_true")
    p.add_argument("--ai-cost", type=float, default=None, help="measured AI cost per message (USD)")
    args = p.parse_args(argv)
    base = Assumptions() if args.ai_cost is None else Assumptions(ai_cost_per_message=args.ai_cost)
    names = list(SCENARIOS) if args.scenarios else ["base"]
    results = {n: per_year(replace(base, **SCENARIOS[n]), args.properties) for n in names}
    print(f"Projection per year, {args.properties} properties (assumptions, not measurements)\n")
    print("| Line | " + " | ".join(names) + " |")
    print("|---|" + "---|" * len(names))
    for key in results["base" if "base" in results else names[0]]:
        counts = key in ("guests using it", "approved paid requests")
        cells = [f"{results[n][key]:,.0f}" if counts else money(results[n][key]) for n in names]
        print(f"| {key} | " + " | ".join(cells) + " |")
    return 0


if __name__ == "__main__":
    sys.exit(main())
