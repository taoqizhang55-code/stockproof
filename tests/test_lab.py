import datetime as dt
import json
import os

import numpy as np
import pandas as pd
import pytest

from stockproof import lab


def _setup(tmp_path, effect=0.004, seed=0):
    """CSI300-like universe of 40 stocks, quarterly reports with SUE; high-SUE reports are followed by a drift."""
    d = tmp_path / "data"
    (d / "research").mkdir(parents=True)
    rng = np.random.default_rng(seed)
    days = pd.bdate_range("2016-01-01", dt.date.today())
    tickers = [f"600{i:03d}.SH" for i in range(40)]
    rets = rng.normal(0, 0.01, (len(days), len(tickers)))
    rows = []
    for j, tk in enumerate(tickers):
        for q in pd.date_range("2016-03-31", dt.date.today() - pd.Timedelta(days=60), freq="QE"):
            day0 = q + pd.Timedelta(days=25)
            i = days.searchsorted(day0)
            if i + 25 >= len(days):
                continue
            sue = float(rng.normal(0, 1.5))
            if sue >= 2:
                rets[i + 2:i + 22, j] += effect
            rows.append({"ticker": tk, "end": q.date(), "day0": days[i].date(), "sue": sue, "reaction": 0.0,
                         "pre": 0.0, "drift": 0.0, "tone": np.nan, "guidance": None, "date_source": "8-K"})
    px = pd.DataFrame(100 * np.cumprod(1 + rets, axis=0), index=days, columns=tickers)
    px.to_csv(d / "prices_cn.csv")
    pd.DataFrame(rows).to_csv(d / "research" / "cn_earnings.csv", index=False)
    (d / "research" / "cn_meta.json").write_text(json.dumps({"prices_path": str(d / "prices_cn.csv")}))
    lab._CACHE.clear()
    return str(d)


SPEC = {"type": "earnings", "market": "cn", "filters": [{"field": "sue", "op": ">=", "value": 2}],
        "hold_days": 20, "entry_lag": 1}


def test_validate_gives_fixable_errors():
    with pytest.raises(lab.SpecError, match="type must be"):
        lab.validate({"type": "magic"})
    with pytest.raises(lab.SpecError, match="unknown field 'pe'"):
        lab.validate({"type": "earnings", "filters": [{"field": "pe", "op": "<", "value": 20}]})
    with pytest.raises(lab.SpecError, match="hold_days"):
        lab.validate({**SPEC, "hold_days": 999})
    assert lab.validate(SPEC)["slots"] == 20


def test_explore_finds_planted_drift_and_logs_tries(tmp_path):
    d = _setup(tmp_path)
    r = lab.explore(d, SPEC, "zh", log=lambda *a: None)
    assert r["phase"] == "explore" and r["trades"] > 100
    assert r["ann_excess"] > 0.02 and r["t"] > 2
    assert r["verdict"]["code"] == "passes" and r["verdict"]["tries"] == 1
    assert os.path.exists(r["report"]) and "<svg" in open(r["report"], encoding="utf-8").read()
    # no trade ends inside the locked holdout
    assert all(t["exit"] < r["holdout_start"] for t in r["best_trades"] + r["worst_trades"])
    # the same spec again is not a new try; other variants are, and they raise the bar
    lab.explore(d, SPEC, "zh", log=lambda *a: None)
    for h in (5, 10, 40, 60):
        r2 = lab.explore(d, {**SPEC, "hold_days": h}, "zh", log=lambda *a: None)
    assert r2["verdict"]["tries"] == 5 and r2["verdict"]["t_needed"] > 2.5
    lab.reset(d)
    assert lab.explore(d, SPEC, "en", log=lambda *a: None)["verdict"]["tries"] == 1


def test_no_edge_and_luck_verdicts(tmp_path):
    d = _setup(tmp_path, effect=0.0, seed=3)
    r = lab.explore(d, SPEC, "zh", log=lambda *a: None)
    assert r["verdict"]["code"] in ("no_edge", "luck_risk")
    v = lab.verdict({"phase": "explore", "summary": {"n_trades": 50, "long_excess": {"t": 2.4, "ann_return": 0.05}}}, 20)
    assert v["code"] == "luck_risk" and "20" in v["text"]
    v = lab.verdict({"phase": "explore", "summary": {"n_trades": 900, "long_excess": {"t": -2.04, "ann_return": -0.036}}}, 1)
    assert v["code"] == "negative" and "跑输" in v["text"]


def test_confirm_runs_once_on_the_holdout(tmp_path):
    d = _setup(tmp_path)
    r = lab.explore(d, SPEC, "zh", log=lambda *a: None)
    c = lab.confirm(d, r["id"], "zh", log=lambda *a: None)
    assert c["phase"] == "confirm" and c["verdict"]["code"] in ("confirmed", "failed")
    assert all(t["entry"] >= c["holdout_start"] for t in c["best_trades"])
    with pytest.raises(lab.SpecError, match="only once"):
        lab.confirm(d, r["id"], "zh", log=lambda *a: None)
    with pytest.raises(lab.SpecError, match="no explored"):
        lab.confirm(d, "nope", "zh")


def test_policy_strategy(tmp_path):
    from stockproof import policy as pl
    from stockproof.store import Store
    d = tmp_path / "pd"
    d.mkdir()
    days = pd.bdate_range("2016-01-01", dt.date.today())
    rng = np.random.default_rng(1)
    cols, rows = {}, []
    boost = {}
    for k in range(120):
        day = days[50 + k * 20] if 50 + k * 20 < len(days) - 80 else None
        if day is None:
            break
        code = list(pl.SW_L1)[k % 31]
        boost.setdefault(code, []).append(day)
        rows.append((day.strftime("%Y%m%d"), pl.SW_L1[code]))
    for code in pl.SW_L1:
        r = rng.normal(0, 0.008, len(days))
        for dd in boost.get(code, []):
            i = days.searchsorted(dd, side="right")
            r[i + 1:i + 20] += 0.004
        c = 1000 * np.cumprod(1 + r)
        cols[f"{code}_c"], cols[f"{code}_o"] = c, c
    pd.DataFrame(cols, index=days).to_csv(pl.policy_dir(str(d)) + "/sw_l1.csv")
    st = Store(str(d))
    st.conn.executescript(pl.SCHEMA)
    for day, ind in rows:
        st.conn.execute("INSERT OR REPLACE INTO policy_reads VALUES (?,?,?,?)", (day, "deepseek:deepseek-chat#p2", json.dumps(
            {"signals": [{"item": 1, "industry": ind, "stance": "support", "strength": 4, "kind": "new_measure",
                          "central": True, "quote": "q", "title": "t"}]}), "x"))
    st.conn.commit()
    lab._CACHE.clear()
    spec = {"type": "policy", "filters": [{"field": "kind", "op": "==", "value": "new_measure"},
                                          {"field": "strength", "op": ">=", "value": 3}], "hold_days": 20}
    r = lab.explore(str(d), spec, "zh", log=lambda *a: None)
    assert r["trades"] > 50 and r["ann_excess"] > 0 and r["t"] > 2
    cap = lab.capabilities(str(d))
    assert "policy" in cap["types"] and cap["tries_since_reset"] == 1


def test_forecast_strategy(tmp_path, monkeypatch):
    d = _setup(tmp_path)
    ev = pd.read_csv(os.path.join(d, "research", "cn_earnings.csv"))
    recs = {}
    for r in ev.itertuples():
        end = pd.Timestamp(r.end).strftime("%Y%m%d")
        recs.setdefault(end, []).append({"code": r.ticker[:6], "type": "预增" if r.sue >= 2 else "略减",
                                         "change_pct": 80.0 if r.sue >= 2 else -10.0, "date": str(r.day0)})
    monkeypatch.setattr(lab, "forecast_table", lambda data_dir, date: recs.get(date, []))
    spec = {"type": "forecast", "filters": [{"field": "type", "op": "in", "value": ["预增"]},
                                            {"field": "change_pct", "op": ">=", "value": 50}], "hold_days": 20}
    r = lab.explore(d, spec, "zh", log=lambda *a: None)
    assert r["trades"] > 100 and r["t"] > 2
    assert "业绩预告" in r["description"]


def test_t_needed_grows_with_tries():
    assert abs(lab.t_needed(1) - 1.96) < 0.01
    assert lab.t_needed(10) > 2.7 and lab.t_needed(100) > lab.t_needed(10)


def test_similar_and_history(tmp_path):
    d = _setup(tmp_path)
    s = lab.similar(d, "600001", lang="zh")
    assert s["n"] >= 10 and "不是对这只股票的预测" in s["summary"]
    h = lab.similar(d, "600001", sue=3.0)
    assert h["latest"]["sue"] == 3.0
    assert "error" in lab.similar(d, "00700.HK")
    assert lab.list_experiments(d) == []
    lab.explore(d, SPEC, "zh", log=lambda *a: None)
    assert lab.list_experiments(d)[0]["phase"] == "explore"


def test_mcp_lab_tools(tmp_path, monkeypatch):
    from stockproof import mcp_server
    d = _setup(tmp_path)
    t = mcp_server.Tools(d)
    opened = []
    monkeypatch.setattr("webbrowser.open", lambda url: opened.append(url))
    cap = t.lab_capabilities()
    assert cap["types"]["earnings"]["markets"]["cn"]["stocks"] == 40
    r = t.lab_backtest(SPEC, open_report=True, lang="zh")
    assert r["verdict"]["code"] == "passes" and opened and opened[0].startswith("file://")
    bad = t.lab_backtest({"type": "earnings", "filters": [{"field": "pe", "op": "<", "value": 1}]}, open_report=False)
    assert "unknown field" in bad["error"]
    assert t.lab_experiments()["tries_since_reset"] == 1
    assert t.lab_experiments(new_question=True)["tries_since_reset"] == 0
    c = t.lab_confirm(r["id"], open_report=False)
    assert c["phase"] == "confirm"


def test_custom_screen(tmp_path, monkeypatch):
    from stockproof import screener
    import test_screener as ts
    codes = [f"6000{i:02d}" for i in range(20)]
    pan = screener.panel(None, "2018-01-01", log=lambda *a: None,
                         tables=ts._tables(codes, years=range(2022, 2027), growth={c: 0.002 * i for i, c in enumerate(codes)}))
    snap = pd.DataFrame({"code": codes, "name": [f"股票{i}" for i in range(20)], "price": 10.0, "mom60": 0.1, "ytd": 0.0,
                         "cap": np.linspace(20, 400, 20), "pe": np.linspace(10, 60, 20), "pb": 2.0})
    monkeypatch.setattr(screener, "panel", lambda *a, **k: pan)
    monkeypatch.setattr(screener, "snapshot", lambda *a, **k: snap)
    monkeypatch.setenv("STOCKPROOF_TODAY", "2026-11-06")
    lab._CACHE.clear()
    r = lab.custom_screen(str(tmp_path), [{"field": "cap", "op": ">=", "value": 100}, {"field": "pe", "op": "<", "value": 40}],
                          sort_by="rev_yoy", top=5)
    assert r["matched"] > 0 and all(x["cap"] >= 100 and x["pe"] < 40 for x in r["results"])
    with pytest.raises(lab.SpecError):
        lab.custom_screen(str(tmp_path), [{"field": "magic", "op": ">", "value": 1}])
