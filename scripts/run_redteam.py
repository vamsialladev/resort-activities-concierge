"""Red-team suite for the concierge: the shared corpus (hotel-ai-platform) plus this app's own cases
(redteam/cases.jsonl), through the concierge's real defences. No API calls; runs in CI.

    python scripts/run_redteam.py                 print the summary, exit 1 on any new miss
    python scripts/run_redteam.py --report        also rewrite docs/redteam-report.md

Layers:
    input      a guest message -> the shared input check (src/concierge/ops.py)
    output     an answer -> the shared output check, grounded on the turn's tool results
    retrieved  an FAQ passage -> the quarantine search_faq applies (src/concierge/guard.py)
    tool       a create_booking_request call the model might make -> the real tool on a seeded temporary database
"""

import argparse
import io
import json
import sys
import tempfile
from datetime import date
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "src"))

from hotelplatform import jsonlog, redteam  # noqa: E402

from concierge import db, guard, ops, seed, tools  # noqa: E402

CASES = ROOT / "redteam" / "cases.jsonl"
OVERRIDES = ROOT / "redteam" / "overrides.json"
REPORT = ROOT / "docs" / "redteam-report.md"
TODAY = date(2026, 11, 2)


def input_layer(case):
    v = ops.check_message(case.text)
    if not v.allowed:
        return redteam.Outcome("block", v.reason, ", ".join(v.reasons))
    if any(f.startswith("injection_removed") for f in v.flags):
        return redteam.Outcome("quarantine", None, v.text[:100])
    if any(f.startswith("pii_redacted") for f in v.flags):
        return redteam.Outcome("redact")
    return redteam.Outcome("allow")


def output_layer(case):
    v = ops.check_answer(case.text, case.context.get("sources", []), case.context.get("input", ""))
    if not v.allowed:
        return redteam.Outcome("block", v.reason)
    return redteam.Outcome("redact" if v.text != case.text else "allow", None, ", ".join(v.flags))


def retrieved_layer(case):
    _, removed = guard.quarantine(case.text)
    return redteam.Outcome("quarantine" if removed else "allow")


def tool_layer_for(engine):
    def tool_layer(case):
        spec = json.loads(case.text)
        ctx = tools.ToolContext(engine, "beach-resort")
        ctx.last_user_message = spec["last_message"]
        result = tools.call(ctx, spec["tool"], spec["args"])
        # Blocked: refused outright, or only a PENDING request (nothing booked or charged until staff approve).
        stopped = "error" in result or result.get("status") == "PENDING"
        return redteam.Outcome("block" if stopped else "allow", None, json.dumps(result)[:100])

    return tool_layer


def shared_cases_for_this_app() -> list:
    """Shared cases whose safe outcome differs in this app, with the reason in redteam/overrides.json."""
    overrides = json.loads(OVERRIDES.read_text(encoding="utf-8"))["expect"]
    cases = redteam.shared_cases()
    for c in cases:
        if c.id in overrides:
            c.expect, c.reason = overrides[c.id], None
    return cases


def run():
    jsonlog.configure("redteam", "ci", stream=io.StringIO())
    with tempfile.TemporaryDirectory() as tmp:
        engine = db.make_engine(f"sqlite:///{(Path(tmp) / 'redteam.db').as_posix()}")
        seed.ensure_window(engine, TODAY)
        handlers = {"input": input_layer, "output": output_layer, "retrieved": retrieved_layer,
                    "tool": tool_layer_for(engine)}  # fmt: skip
        shared = redteam.run(shared_cases_for_this_app(), handlers)
        own = redteam.run(redteam.load_cases(CASES), handlers)
        engine.dispose()
    return shared, own


def known_gaps() -> set[str]:
    lines = (ROOT / "redteam" / "known_gaps.txt").read_text(encoding="utf-8").splitlines()
    return {ln.split()[0] for ln in lines if ln.strip() and not ln.startswith("#")}


def main(argv=None) -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--report", action="store_true")
    args = ap.parse_args(argv)
    shared, own = run()
    for name, results in (("shared corpus", shared), ("this app's cases", own)):
        s = redteam.score(results)
        print(f"{name}: {s['passed']}/{s['cases']} passed; attacks stopped {s['attacks_stopped']}/{s['attacks']}; "
              f"false alarms {s['false_alarms']}/{s['controls']}")  # fmt: skip
        for r in results:
            if not r.passed:
                print(f"  FAIL {r.case.id} [{r.case.category}] expected {r.case.expect}, got {r.outcome.verdict}")
    if args.report:
        REPORT.write_text(
            redteam.report_markdown(shared, "Red-team report: shared corpus through the concierge")
            + "\n"
            + redteam.report_markdown(own, "Red-team report: the concierge's own cases (held out)"),
            encoding="utf-8",
            newline="\n",
        )
    new_failures = [r.case.id for r in shared + own if not r.passed and r.case.id not in known_gaps()]
    if new_failures:
        print("GATE FAILED: new red-team failures:", ", ".join(new_failures))
    return 1 if new_failures else 0


if __name__ == "__main__":
    sys.exit(main())
