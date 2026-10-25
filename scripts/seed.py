"""Create the tables and fill the 14-day schedule and the demo stays (idempotent; safe to run any time).

    python scripts/seed.py            # uses DATABASE_URL (Neon) if set, else data/concierge.db
    python scripts/seed.py --check    # print what's there, change nothing

The app also does this on start, so Streamlit Cloud needs no manual step.
"""

import argparse
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "src"))

from sqlalchemy import func, inspect, select  # noqa: E402

from concierge import config, db, seed  # noqa: E402


def main(argv=None) -> int:
    parser = argparse.ArgumentParser(description=__doc__.split("\n\n")[0])
    parser.add_argument("--check", action="store_true")
    args = parser.parse_args(argv)
    engine = db.make_engine()
    kind = "Postgres (DATABASE_URL)" if engine.dialect.name == "postgresql" else f"SQLite ({config.SQLITE_PATH})"
    conn = db.connect(engine)  # retries while Neon wakes up
    conn.close()
    added = 0 if args.check else seed.ensure_window(engine)
    if not inspect(engine).has_table("activities"):
        print(f"{kind}: no tables yet (run without --check to create them)")
        return 0
    with engine.connect() as c:
        n = c.execute(select(func.count()).select_from(db.activities)).scalar_one()
        stays = c.execute(select(func.count()).select_from(db.stays)).scalar_one()
    print(f"{kind}: {n} activities ({added} added now), {stays} stays")
    return 0


if __name__ == "__main__":
    sys.exit(main())
