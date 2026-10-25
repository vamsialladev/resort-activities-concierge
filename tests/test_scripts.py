"""The seed and business-case scripts (no network, no Neon)."""

import importlib.util

from concierge import config

ROOT = config.ROOT


def load(name):
    spec = importlib.util.spec_from_file_location(name, ROOT / "scripts" / f"{name}.py")
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def test_business_case_scenarios_are_ordered_and_labelled(capsys):
    bc = load("business_case")
    rows = {n: bc.per_year(bc.replace(bc.Assumptions(), **bc.SCENARIOS[n]), 2) for n in bc.SCENARIOS}
    assert rows["pessimistic"]["net value"] < rows["base"]["net value"] < rows["optimistic"]["net value"]
    assert rows["pessimistic"]["net value"] < 0  # the pessimistic case doesn't pay back: that's the no-go line
    assert bc.main(["--scenarios", "--properties", "2"]) == 0
    out = capsys.readouterr().out
    assert "assumptions, not measurements" in out and "| net value |" in out
    more = bc.per_year(bc.Assumptions(), 40)
    assert more["SaaS fee"] == 450 * 12 * 40


def test_seed_script_on_sqlite(tmp_path, monkeypatch, capsys):
    url = f"sqlite:///{(tmp_path / 's.db').as_posix()}"
    monkeypatch.setattr(config, "database_url", lambda: url)
    seed = load("seed")
    assert seed.main(["--check"]) == 0 and "no tables yet" in capsys.readouterr().out
    assert seed.main([]) == 0 and "activities" in capsys.readouterr().out
