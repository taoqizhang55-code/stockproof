import datetime as dt
import json
import sqlite3

import numpy as np
import pandas as pd
import pytest

from stockproof import team
from stockproof.store import Store


class FakeClient:
    """Plays every role; the PM claims high confidence and an off-chart level to test the guards."""
    def __init__(self):
        self.prompts = []

    def chat_json(self, prompt):
        self.prompts.append(prompt)
        if "analyst in a research team" in prompt:
            role = prompt.split("You are the ")[1].split(" analyst")[0]
            pre = team.PREFIX[role]
            return {"view": "bullish" if role == "technical" else "neutral", "strength": 0.7,
                    "points": [{"text": f"{role} point", "evidence": [f"{pre}1"]}, {"text": "made up", "evidence": ["Z9"]}],
                    "risks": [{"text": "a risk", "evidence": [f"{pre}1"]}], "unknowns": ["?"]}
        if "researcher for" in prompt:
            return {"case": [{"text": "case", "evidence": ["T1"]}], "other_side_weakest": "weak"}
        return {"stance": "bullish", "confidence": "high", "horizon_days": 20, "summary": "s",
                "reasons": [{"text": "trend up", "evidence": ["T1"]}, {"text": "uncited", "evidence": []}],
                "plan": [{"if": "holds support", "level": 10.0, "then": "view stands"},
                         {"if": "made-up level", "level": 99.0, "then": "x"}],
                "risks": [{"text": "r", "evidence": ["T2"]}], "would_change_view": ["break below support"]}


@pytest.fixture
def setup(tmp_path, monkeypatch):
    d = tmp_path
    (d / "quotes").mkdir()
    days = pd.bdate_range(end=dt.date.today() - dt.timedelta(days=40), periods=200)
    c = 10 + np.sin(np.arange(200) / 8)
    bars = pd.DataFrame({"close": c, "open": c, "high": c * 1.01, "low": c * 0.99, "volume": 1e6}, index=days)
    bars.rename_axis("date").to_csv(d / "quotes" / "600000.SH.csv")
    card = {"name": "浦发银行", "evidence": [{"kind": "news", "title": "headline", "text": "t", "date": "2026-10-01"}],
            "dimensions": [{"key": k, "score": 50, "validated": {"tested": k == "fundamentals", "useful": False, "text": "x"}}
                           for k in ("fundamentals", "momentum", "report", "quality", "news", "filings", "policy")]}
    monkeypatch.setattr("stockproof.scorecard.build", lambda *a, **k: card)
    monkeypatch.setattr("stockproof.flows.dragon_tiger", lambda *a, **k: [])

    class App:
        data_dir = str(d)
    return App(), Store(str(d))


def test_team_run_guards_and_forward_log(setup):
    app, store = setup
    fc = FakeClient()
    r = team.run(app, store, fc, "fake:m", "600000.SH", "zh", log=lambda *a: None)
    tech = r["analysts"]["technical"]
    assert tech["view"] == "bullish" and [p["evidence"] for p in tech["points"]] == [["T1"]]     # Z9 dropped
    f = r["final"]
    assert f["stance"] == "bullish" and f["confidence"] == "low" and f["confidence_capped"]      # nothing tested passed
    assert "历史检验" in f["cap_note"]
    assert len(f["reasons"]) == 1 and [p["level"] for p in f["plan"]] == [10.0] or len(f["plan"]) <= 1
    assert all(p["level"] != 99.0 for p in f["plan"])                                           # off-chart level removed
    assert sum("analyst in a research team" in p for p in fc.prompts) >= 2 and len(fc.prompts) >= 5
    # one call per stock per day
    again = team.run(app, store, fc, "fake:m", "600000.SH", "zh", log=lambda *a: None)
    assert again["cached"] and again["call_id"] == r["call_id"]
    # append-only
    with pytest.raises(sqlite3.DatabaseError, match="append-only"):
        store.conn.execute("UPDATE team_calls SET stance='bearish'")
    with pytest.raises(sqlite3.DatabaseError, match="append-only"):
        store.conn.execute("DELETE FROM team_calls")


def test_scoring_after_the_horizon(setup, monkeypatch):
    app, store = setup
    store.conn.executescript(team.SCHEMA)
    days = pd.bdate_range("2026-01-02", periods=80)
    stock = pd.Series(np.linspace(10, 12, 80), index=days)              # +20%
    bench = pd.Series(np.linspace(100, 105, 80), index=days)            # +5%
    loads = {"600000.SH": stock, "^CSI300": bench}
    monkeypatch.setattr(team.quotes, "load", lambda d, tk: loads[tk])
    monkeypatch.setattr(team.quotes, "update", lambda *a, **k: None)
    res = {"ticker": "600000.SH", "made_at": "2026-01-02T15:00:00", "day": "2026-01-02", "price": 10, "model": "m",
           "final": {"stance": "bullish", "confidence": "low", "horizon_days": 20}}
    team.record_call(store, res, "zh")
    team.record_call(store, {**res, "made_at": "2026-01-02T16:00:00", "final": {**res["final"], "stance": "bearish"}}, "zh")
    team.record_call(store, {**res, "day": "2026-01-05", "made_at": "2026-01-05T15:00:00",
                             "final": {**res["final"], "stance": "bearish"}}, "zh")
    assert team.score_calls(store, app.data_dir) == 2            # the second call on 01-02 doesn't count
    rec = team.track_record(store, "zh")
    assert rec["summary"]["scored"] == 2 and rec["summary"]["hit_rate"] == 0.5
    assert rec["summary"]["calls"] == 2 and rec["summary"]["discussions"] == 3
    assert team.score_calls(store, app.data_dir) == 0                    # scored once


def test_questions_and_resolver(setup, tmp_path):
    app, store = setup
    fc = FakeClient()
    a = team.run(app, store, fc, "fake:m", "600000.SH", "zh", log=lambda *x: None)
    b = team.run(app, store, fc, "fake:m", "600000.SH", "zh", log=lambda *x: None, question="分红能不能持续？")
    assert not b.get("cached") and b["question"] == "分红能不能持续？" and b["call_id"] != a["call_id"]
    assert any("分红能不能持续" in p for p in fc.prompts)
    c = team.run(app, store, fc, "fake:m", "600000.SH", "zh", log=lambda *x: None, question="分红能不能持续？")
    assert c["cached"] and c["call_id"] == b["call_id"]
    import json as _j
    import os
    os.makedirs(os.path.join(app.data_dir, "cn"), exist_ok=True)
    with open(os.path.join(app.data_dir, "cn", "research_yjbb2_20260930.json"), "w", encoding="utf-8") as f:
        _j.dump([{"code": "002230", "name": "科大讯飞"}, {"code": "300750", "name": "宁德时代"}], f, ensure_ascii=False)
    app.settings = {"watchlist": ["AAPL"], "names": {}}
    assert team.resolve(app, "分析一下科大讯飞，重点看扣非") == "002230.SZ"
    assert team.resolve(app, "300750 能买吗") == "300750.SZ"
    assert team.resolve(app, "AAPL 怎么样") == "AAPL"
    assert team.resolve(app, "随便聊聊") is None
