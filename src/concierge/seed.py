"""Synthetic data: 14 days of activities for both properties, and a few guest stays. No real guests or prices.

Activities come from weekly templates, so the schedule never goes stale: `ensure_window(today)` adds any missing
day in the 14-day window (idempotent, safe to call on every app start). How full each session is comes from a
hash of its ID, so the same day always looks the same. Stays are re-dated around today the same way, so the demo
booking references always belong to someone currently staying.
"""

import hashlib
from datetime import date, timedelta

from sqlalchemy import select
from sqlalchemy.engine import Engine

from concierge import config
from concierge.db import activities, init, stays

ALL_DAYS = (0, 1, 2, 3, 4, 5, 6)  # Monday = 0

# (key, name, category, start, end, location, indoor, min_age, max_age, price, capacity, weekdays, description)
TEMPLATES = {
    "beach-resort": [
        ("yoga", "Sunrise yoga on the beach", "wellness", "07:00", "08:00", "North beach", False, 12, None, 20, 15,
         ALL_DAYS, "Gentle flow on the sand, mats provided. Ages 12 and up."),
        ("turtle", "Turtle talk with the marine team", "kids", "08:30", "09:15", "South beach hut", False, 0, None, 0,
         30, ALL_DAYS, "Meet the marine team and learn about the turtles that nest here. All ages; free."),
        ("kids", "Kids club: sandcastle morning", "kids", "09:30", "11:30", "Kids club pavilion", False, 4, 11, 0, 20,
         ALL_DAYS, "Sandcastles, shell hunts and beach games with our kids club team. Ages 4-11."),
        ("snorkel", "Reef snorkel tour", "water", "10:00", "12:00", "Dive shack", False, 8, None, 55, 10,
         (0, 2, 4, 5, 6), "Guided snorkel over the house reef. Gear included. Ages 8 and up; under-16s with an adult."),
        ("spa", "Spa: aromatherapy massage", "wellness", "14:00", "15:00", "Palm spa", True, 16, None, 120, 4,
         ALL_DAYS, "Sixty-minute aromatherapy massage. Ages 16 and up."),
        ("tea", "Afternoon high tea", "food", "15:30", "17:00", "Terrace lounge", True, 0, None, 35, 24,
         ALL_DAYS, "Scones, sandwiches and island teas. Children welcome; under-12s eat for half price."),
        ("cook", "Cooking class: island ceviche", "food", "17:00", "18:30", "Chef's kitchen", True, 12, None, 65, 12,
         (1, 3, 5), "Make ceviche and plantain chips with our chef. Ages 12 and up."),
        ("cruise", "Sunset cruise", "water", "18:00", "19:30", "Main pier", False, 0, None, 75, 30,
         (1, 2, 3, 4, 5, 6), "Catamaran cruise at sunset. All ages; children under 12 with an adult. Life jackets provided."),
        ("movie", "Kids movie night", "kids", "19:30", "21:00", "Kids club pavilion", True, 5, 12, 0, 25,
         (4, 5), "A family film and popcorn. Ages 5-12; parents can stay or pick up at 21:00."),
    ],
    "mountain-lodge": [
        ("yoga", "Yoga in the loft", "wellness", "07:30", "08:30", "Loft studio", True, 12, None, 20, 14,
         ALL_DAYS, "Morning yoga with mountain views. Ages 12 and up."),
        ("trek", "Guided morning trek", "adventure", "08:00", "11:00", "Trailhead lobby", False, 10, None, 40, 12,
         ALL_DAYS, "A 7 km guided hike with 350 m of climbing. Boots required. Ages 10 and up."),
        ("pond", "Family pond walk", "kids", "09:30", "10:30", "Meadow gate", False, 0, None, 10, 20,
         ALL_DAYS, "An easy 2 km walk to the beaver pond with a naturalist. All ages; strollers welcome."),
        ("kids", "Kids club: nature explorers", "kids", "09:00", "12:00", "Kids cabin", False, 5, 12, 0, 16,
         ALL_DAYS, "Bug hunts, trail games and a nature craft. Ages 5-12."),
        ("cook", "Cooking class: mountain breakfast", "food", "10:00", "11:30", "Lodge kitchen", True, 16, None, 60, 10,
         (5, 6), "Skillet breakfast with the lodge chef. Ages 16 and up."),
        ("spa", "Spa: hot stone massage", "wellness", "15:00", "16:00", "Cedar spa", True, 16, None, 130, 4,
         ALL_DAYS, "Sixty-minute hot stone massage. Ages 16 and up."),
        ("tea", "High tea by the fire", "food", "15:30", "17:00", "Great room", True, 0, None, 30, 20,
         ALL_DAYS, "Tea, cakes and hot chocolate by the fireplace. All ages."),
        ("firepit", "Fire pit s'mores evening", "evening", "19:00", "20:30", "Fire pit terrace", False, 0, None, 0, 40,
         ALL_DAYS, "S'mores and stories around the fire pit. All ages; free for guests."),
        ("stars", "Stargazing walk", "evening", "21:00", "22:00", "Meadow gate", False, 8, None, 15, 15,
         (0, 2, 4, 5), "A short guided night walk with telescopes. Ages 8 and up."),
    ],
}  # fmt: skip

# Synthetic stays: (ref, property, last_name, room, days from today to check-in, nights, adults, children)
STAYS = [
    ("BR-4821", "beach-resort", "Rivera", "214", -1, 5, 2, 2),
    ("BR-4822", "beach-resort", "Okafor", "118", 0, 3, 2, 0),
    ("BR-4823", "beach-resort", "Lindqvist", "305", -2, 7, 1, 1),
    ("BR-4824", "beach-resort", "Tanaka", "402", 1, 4, 2, 3),
    ("ML-7310", "mountain-lodge", "Moreau", "12", -1, 4, 2, 2),
    ("ML-7311", "mountain-lodge", "Haddad", "7", 0, 2, 2, 0),
    ("ML-7312", "mountain-lodge", "Kowalski", "21", -3, 6, 4, 0),
]


def fullness(activity_id: str, capacity: int) -> int:
    """How many places are already booked: 20-95% of capacity, fixed per session."""
    h = int(hashlib.sha256(activity_id.encode()).hexdigest()[:8], 16)
    return min(capacity, round(capacity * (0.2 + (h % 76) / 100)))


def activity_rows(day: date) -> list[dict]:
    rows = []
    prefix = {"beach-resort": "BR", "mountain-lodge": "ML"}
    for prop, templates in TEMPLATES.items():
        for (
            key,
            name,
            cat,
            start,
            end,
            loc,
            indoor,
            min_age,
            max_age,
            price,
            cap,
            days,
            desc,
        ) in templates:
            if day.weekday() not in days:
                continue
            aid = f"{prefix[prop]}-{day.strftime('%Y%m%d')}-{key}"
            rows.append(
                {
                    "id": aid,
                    "property": prop,
                    "date": day.isoformat(),
                    "start": start,
                    "end": end,
                    "name": name,
                    "category": cat,
                    "description": desc,
                    "location": loc,
                    "indoor": indoor,
                    "min_age": min_age,
                    "max_age": max_age,
                    "price_usd": float(price),
                    "capacity": cap,
                    "booked": fullness(aid, cap),
                }
            )
    return rows


def stay_rows(today: date) -> list[dict]:
    out = []
    for ref, prop, last, room, offset, nights, adults, children in STAYS:
        check_in = today + timedelta(days=offset)
        out.append(
            {
                "ref": ref,
                "property": prop,
                "last_name": last,
                "room": room,
                "check_in": check_in.isoformat(),
                "check_out": (check_in + timedelta(days=nights)).isoformat(),
                "adults": adults,
                "children": children,
            }
        )
    return out


def ensure_window(engine: Engine, today: date | None = None, days: int = config.SCHEDULE_DAYS) -> int:
    """Create tables if needed, add missing activity days in [today, today + days), re-date the stays. Returns the
    number of activities added."""
    today = today or config.today()
    init(engine)
    added = 0
    with engine.begin() as conn:
        have = {r[0] for r in conn.execute(select(activities.c.date).where(activities.c.date >= today.isoformat()))}
        for i in range(days):
            day = today + timedelta(days=i)
            if day.isoformat() in have:
                continue
            rows = activity_rows(day)
            conn.execute(activities.insert(), rows)
            added += len(rows)
        for row in stay_rows(today):
            exists = conn.execute(select(stays.c.ref).where(stays.c.ref == row["ref"])).first()
            if exists:
                conn.execute(stays.update().where(stays.c.ref == row["ref"]).values(**row))
            else:
                conn.execute(stays.insert().values(**row))
    return added
