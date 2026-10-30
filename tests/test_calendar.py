"""Earnings calendar: periods, A-share appointments, Nasdaq rows, estimates. No network."""

import datetime as dt
import json
import sys
import types

import pandas as pd

from stockproof import earnings_calendar as cal


def test_open_periods():
    assert cal.open_periods(dt.date(2026, 10, 29)) == ["20260930"]
    assert cal.open_periods(dt.date(2026, 11, 15)) == []
    assert cal.open_periods(dt.date(2027, 1, 20)) == ["20261231"]
    assert cal.open_periods(dt.date(2027, 4, 10)) == ["20261231", "20270331"]


def test_a_share_calendar_uses_latest_change_and_skips_published(monkeypatch):
    df = pd.DataFrame({"股票代码": ["600519", "300750", "000001", "000002"],
                       "首次预约时间": ["2026-10-25", "2026-10-30", "2026-10-31", "2026-10-30"],
                       "一次变更日期": [None, "2026-10-31", None, None],
                       "二次变更日期": [None, None, None, None], "三次变更日期": [None, None, None, None],
                       "实际披露时间": ["2026-10-25", None, None, None]})
    monkeypatch.setitem(sys.modules, "akshare", types.SimpleNamespace(stock_yysj_em=lambda symbol, date: df))
    out = cal.a_share_calendar({"600519", "300750", "000001"}, dt.date(2026, 10, 29))
    by = {o["ticker"]: o for o in out}
    assert set(by) == {"300750.SZ", "000001.SZ"}                    # Moutai already published
    assert by["300750.SZ"]["date"] == "2026-10-31" and by["300750.SZ"]["changed"]
    assert by["000001.SZ"]["date"] == "2026-10-31" and not by["000001.SZ"]["changed"]


def test_nasdaq_rows_and_estimates(tmp_path, monkeypatch):
    class R:
        def raise_for_status(self): pass
        def json(self):
            return {"data": {"rows": [{"symbol": "AAPL", "time": "time-after-hours", "epsForecast": "$1.75",
                                       "fiscalQuarterEnding": "Sep/2026", "noOfEsts": "12"},
                                      {"symbol": "BRK.B", "time": "time-pre-market", "epsForecast": "($0.10)"}]}}
    monkeypatch.setattr(cal.requests, "get", lambda *a, **k: R())
    monkeypatch.setattr(cal.time, "sleep", lambda s: None)
    rows = cal.nasdaq_day(dt.date(2026, 10, 29))
    assert rows[0] == {"symbol": "AAPL", "time": "after_close", "eps_forecast": 1.75, "period": "Sep/2026",
                       "n_estimates": "12"}
    assert rows[1]["symbol"] == "BRK-B" and rows[1]["eps_forecast"] == -0.10
    found, errors = cal.us_calendar({"AAPL"}, dt.date(2026, 10, 30), 3)      # Fri + Mon (weekend skipped)
    assert [f["date"] for f in found] == ["2026-10-30", "2026-11-02"] and not errors

    sec = tmp_path / "sec"
    sec.mkdir()
    (sec / "submissions_1.json").write_text(json.dumps({"filings": {"recent": {
        "form": ["8-K", "8-K"], "items": ["2.02,9.01", "5.02"], "filingDate": ["2025-11-04", "2025-11-03"]}}}))
    est = cal.estimate_from_last_year(str(sec), {"XYZ": {"cik": 1}}, {"XYZ"}, dt.date(2026, 10, 29), 14)
    assert est == [{"ticker": "XYZ", "date": "2026-11-03", "period": None, "time": None,
                    "source": "estimate", "eps_forecast": None}]


def test_upcoming_filters_watchlist_and_dates(tmp_path):
    data = {"updated": "x", "errors": [], "items": [
        {"ticker": "AAPL", "date": "2026-10-30"}, {"ticker": "MSFT", "date": "2026-10-28"},
        {"ticker": "KO", "date": "2026-11-30"}, {"ticker": "NVDA", "date": "2026-11-05"}]}
    (tmp_path / "calendar.json").write_text(json.dumps(data))
    up = cal.upcoming(str(tmp_path), ["AAPL", "MSFT", "KO"], 14, today=dt.date(2026, 10, 29))
    assert [u["ticker"] for u in up] == ["AAPL"]
