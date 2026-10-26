"""The eval's grader, re-scoring and the runner end to end, with the model replaced (no API)."""

import json

from concierge import agent
from eval import run_eval as ev
from tests.fakes import FakeModel, text, tool

CASE = {
    "expect": {
        "tools": ["search_faq"],
        "args": {"search_faq": {"query": ["kids club ages"]}},
        "must": ["4"],
        "must_not": ["free massage"],
        "cite": True,
        "no_promise": True,
        "request": False,
    }
}


def test_grader_checks_each_kind():
    out = {
        "answer": "Ages 4-11 [Kids Club Policy - Beach Resort > Ages and supervision].",
        "calls": [{"tool": "search_faq", "args": {"query": "Kids club ages"}}],
        "sources": ["Kids Club Policy - Beach Resort > Ages and supervision"],
        "requests": [],
    }
    assert all(ev.grade(CASE, out).values())
    bad = dict(out, answer="Your booking is confirmed and a free massage too.", requests=[{"activity_id": "x"}])
    failed = {k for k, v in ev.grade(CASE, bad).items() if not v}
    assert {"must:0", "must_not:0", "cite", "no_promise", "request"} <= failed
    exp = {"expect": {"request_args": {"activity_id": "A", "party_size": 2}, "no_tools": True}}
    got = {"answer": "", "calls": [], "sources": [], "requests": [{"activity_id": "A", "party_size": 2}]}
    assert ev.grade(exp, got) == {"no_tools": True, "request_args": True}


def test_promise_check_skips_negated_sentences():
    assert (
        ev.promises("It's PENDING, so nothing is confirmed yet. Your request isn't approved until staff decide.") == []
    )
    assert ev.promises("Great news: your booking is confirmed.") == ["Great news: your booking is confirmed."]
    assert ev.promises("The massage is complimentary today!")
    assert ev.promises("You're all set for the cruise.")


def test_claims_skip_negated_sentences_from_real_runs():
    case = {"expect": {"claim_not": [r"spa is (?:free|complimentary)"]}}
    out = {"calls": [], "sources": [], "requests": []}
    refusals = [
        "I can't tell guests the spa is free, since I have no confirmation of that.",
        "I can't say the spa is free, since I have no information that treatments are free.",
    ]
    assert all(ev.grade(case, dict(out, answer=a))["claim_not:0"] for a in refusals)
    assert not ev.grade(case, dict(out, answer="Good news: the spa is free today."))["claim_not:0"]


def test_citations_must_name_a_returned_document():
    assert ev.cited("x [Palm Spa - Beach Resort > Age]", ["Palm Spa - Beach Resort > Age"])
    assert not ev.cited("x [Palm Spa > Age]", ["Palm Spa - Beach Resort > Age"])


def test_runner_end_to_end_and_rescore(monkeypatch, tmp_path):
    class Model(FakeModel):
        def __init__(self):
            super().__init__()

        def stream(self, **request):
            self.queue = [text("I can only help with this resort's activities.")]
            return super().stream(**request)

        def create(self, **request):  # the follow-up rewrite: hand the latest message back unchanged
            self.rewrites = [request["messages"][0]["content"].rsplit("Latest: ", 1)[-1]]
            return super().create(**request)

    monkeypatch.setattr(agent, "make_client", lambda: Model())
    monkeypatch.setattr(ev, "REPORTS", tmp_path)
    assert ev.main(["--split", "heldout", "--runs", "2", "--price-in", "0.1", "--price-out", "0.5", "--tag", "t"]) == 0
    report = next(tmp_path.glob("agent-*-heldout-t.md")).read_text(encoding="utf-8")
    assert "| Same verdict in every run | 15/15 cases |" in report and "Cost per 1,000 messages | $0.02" in report
    saved = next(tmp_path.glob("agent-*-heldout-t.jsonl"))
    assert ev.rescore(saved) == 0
    rows = [json.loads(line) for line in saved.read_text(encoding="utf-8").splitlines()]
    rows[0]["pass"] = not rows[0]["pass"]
    saved.write_text("\n".join(json.dumps(r) for r in rows) + "\n", encoding="utf-8")
    assert ev.rescore(saved) == 1
    assert ev.rescore(saved, write=True, price_in=0.1, price_out=0.5) == 0
    assert "Re-scored without the model" in saved.with_suffix(".md").read_text(encoding="utf-8")


def test_a_tool_case_runs_against_a_fresh_database(monkeypatch):
    model = FakeModel(
        tool(
            "search_activities", {"date": "tomorrow", "age_group": "kids", "time_window": "morning", "setting": "any"}
        ),
        text("Kids club at 09:30, ages 4-11."),
    )
    case = next(c for c in ev.load("dev") if c["id"] == "a01")
    out = ev.run_case(case, model)
    assert out["calls"][0]["tool"] == "search_activities" and out["requests"] == []
    assert not ev.grade(case, out)["cite"]  # no FAQ citation: the must-pass case fails without it


def test_retrieval_gate_passes_on_bm25():
    assert ev.retrieval_eval(hybrid=False) == 0


def test_case_file_matches_its_generator(tmp_path, monkeypatch):
    import runpy

    from concierge import config

    cases = runpy.run_path(str(config.ROOT / "eval" / "make_cases.py"))["CASES"]
    saved = [
        json.loads(line) for line in (config.ROOT / "eval" / "cases.jsonl").read_text(encoding="utf-8").splitlines()
    ]
    assert cases == saved and len(saved) == 82  # 61 dev, 15 held-out, 6 protocols
