import datetime as dt
import os

import numpy as np
import pandas as pd

from stockproof import market_scan, ta


def _range_bars(last_close, last_vol_mult=3.0, n=200):
    """Oscillates between ~10 and ~11 (a resistance zone near 11), then one final bar."""
    days = pd.bdate_range(end=dt.date.today(), periods=n)
    t = np.arange(n - 1)
    close = 10.5 + 0.5 * np.sin(2 * np.pi * t / 24)
    close = np.append(close, last_close)
    high, low = close * 1.004, close * 0.996
    vol = np.full(n, 1e6)
    vol[-1] *= last_vol_mult
    return pd.DataFrame({"close": close, "open": np.append(close[0], close[:-1]), "high": high, "low": low,
                         "volume": vol}, index=days)


def _cache(d, tk, bars):
    p = os.path.join(market_scan.scan_dir(d), "bars", f"{tk}.csv")
    bars.to_csv(p)


def _movers(rows):
    return market_scan._frame([{"f12": c, "f14": n, "f2": p, "f3": pct, "f6": amt, "f10": vr, "f8": 1.0, "f20": 1e10}
                               for c, n, p, pct, amt, vr in rows])


def test_candidates_filter():
    mv = _movers([("600001", "好公司", 10, 5.0, 5e8, 2.0), ("600002", "*ST差", 5, 5.0, 5e8, 2.0),
                  ("600003", "N新股", 30, 44.0, 9e8, 1.0), ("600004", "小票", 8, 6.0, 2e7, 3.0),
                  ("600005", "没动", 9, 0.5, 9e8, 1.0), ("600006", "大跌", 9, -6.0, 3e8, 2.0)])
    c = market_scan.candidates(mv)
    assert list(c["code"]) == ["600001", "600006"]                  # most traded first, junk removed


def test_scan_finds_breakout_and_breakdown(tmp_path):
    d = str(tmp_path)
    up, down, flat = _range_bars(11.9), _range_bars(9.3, 2.0), _range_bars(10.6, 1.0)
    assert any(s["kind"] == "breakout" for s in ta.signals(up, days=1))
    _cache(d, "600001.SH", up)
    _cache(d, "600006.SH", down)
    _cache(d, "600007.SH", flat)
    mv = _movers([("600001", "突破股", 11.9, 6.0, 5e8, 3.0), ("600006", "破位股", 9.3, -7.0, 3e8, 2.0),
                  ("600007", "平稳股", 10.6, 2.5, 2e8, 1.0)])
    r = market_scan.scan(d, mv=mv, fetch=False, log=lambda *a: None)
    kinds = {h["ticker"]: h["kind"] for h in r["hits"]}
    assert kinds == {"600001.SH": "breakout", "600006.SH": "breakdown"}
    hit = r["hits"][0]
    assert hit["kind"] == "breakout" and hit["zone"][0] is not None and hit["touches"] >= 2 and hit["rule"]
    assert "不是买卖指令" in r["note"] and r["breakouts"] == 1 and r["breakdowns"] == 1
    assert market_scan.latest(d)["day"] == r["day"]


def test_movers_falls_back_to_sina(monkeypatch):
    from stockproof import screener

    def em_down(*a, **k):
        raise RuntimeError("502 Bad Gateway")

    class R:
        def __init__(self, data):
            self.text = "x"
            self._d = data

        def json(self):
            return self._d

    def fake_get(url, params, headers, tries=3, gap=0.6):
        assert url == screener.SINA_URL and params["sort"] == "changepercent"
        if params["page"] > 1:
            return R([])
        sign = 1 if params["asc"] == 0 else -1
        return R([{"code": "600001", "name": "甲", "trade": "10.5", "changepercent": 5.0 * sign, "amount": 6e8,
                   "turnoverratio": 2.0, "mktcap": 1e6}])

    monkeypatch.setattr(market_scan, "_movers_em", em_down)
    monkeypatch.setattr(screener, "_get", fake_get)
    mv = market_scan.movers("up", log=lambda *a: None)
    assert list(mv["code"]) == ["600001"] and abs(mv["pct"].iloc[0] - 0.05) < 1e-9 and mv["amount"].iloc[0] == 6e8


def test_one_row_per_stock_when_two_zones_break(tmp_path):
    d = str(tmp_path)
    days = pd.bdate_range(end=dt.date.today(), periods=260)
    # two stacked ranges: 10-11 earlier, 12-13 later, then a jump through both
    t = np.arange(259)
    c = np.where(t < 130, 10.5 + 0.5 * np.sin(2 * np.pi * t / 24), 12.5 + 0.5 * np.sin(2 * np.pi * t / 24))
    c = np.append(c[:-20], np.full(20, 10.6))        # back down into the low range before the jump
    c = np.append(c, 13.9)
    v = np.full(260, 1e6); v[-1] = 4e6
    b = pd.DataFrame({"close": c, "open": np.append(c[0], c[:-1]), "high": c * 1.004, "low": c * 0.996, "volume": v},
                     index=days)
    _cache(d, "600001.SH", b)
    r = market_scan.scan(d, mv=_movers([("600001", "两连破", 13.9, 20.0, 9e8, None)]), fetch=False, log=lambda *a: None)
    rows = [h for h in r["hits"] if h["ticker"] == "600001.SH"]
    assert len(rows) == 1 and rows[0]["vol_ratio"] and rows[0]["vol_ratio"] > 1.5
    assert rows[0]["zones_crossed"] >= 2 and rows[0]["zone"][1] > 12
