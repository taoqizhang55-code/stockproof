import datetime as dt

import pandas as pd

from stockproof import margin


def test_margin_history_and_stock(tmp_path, monkeypatch):
    days = pd.bdate_range(end=dt.date(2026, 10, 30), periods=40)

    class Ak:
        def stock_margin_detail_sse(self, date):
            d = pd.Timestamp(date)
            if d not in days:
                return pd.DataFrame()
            i = days.get_loc(d)
            return pd.DataFrame({"信用交易日期": date, "标的证券代码": ["600519", "510050"], "标的证券简称": ["茅台", "50ETF"],
                                 "融资余额": [1e10 + i * 1e8, 5e9], "融资买入额": [1e8, 1e7]})

        def stock_margin_detail_szse(self, date):
            raise ConnectionResetError("reset by peer")
    monkeypatch.setattr(margin.cn, "_ak", lambda: Ak())
    monkeypatch.setattr(margin.time, "sleep", lambda s: None)
    end = days[-1].date()
    h = margin.history(str(tmp_path), 20, end=end)
    assert len(h["sse"]) == 20 and list(h["sse"].columns) == ["600519"]        # ETFs dropped
    assert h["szse"].empty                                                     # unreachable, not zeros
    s = margin.stock(str(tmp_path), "600519.SH", 20, end=end)
    assert s["available"] and abs(s["change"] - 19e8) < 1 and s["days"] == 20
    assert not margin.stock(str(tmp_path), "000001.SZ", 20, end=end)["available"]


def test_market_ignores_stocks_leaving_the_list(tmp_path, monkeypatch):
    days = pd.bdate_range(end=dt.date(2026, 10, 30), periods=25)

    class Ak:
        def stock_margin_detail_sse(self, date):
            i = days.get_loc(pd.Timestamp(date)) if pd.Timestamp(date) in days else None
            if i is None:
                return pd.DataFrame()
            codes = ["600519", "600000"] + (["600001"] if i < 10 else [])     # 600001 dropped from the list
            return pd.DataFrame({"标的证券代码": codes, "标的证券简称": codes, "融资余额": [1e10, 2e10, 5e10][:len(codes)]})

        def stock_margin_detail_szse(self, date):
            raise ConnectionResetError()
    monkeypatch.setattr(margin.cn, "_ak", lambda: Ak())
    monkeypatch.setattr(margin.time, "sleep", lambda s: None)
    monkeypatch.setattr(margin, "history", (lambda f: lambda d, n=20, fetch=True, end=None: f(d, n, fetch, days[-1].date()))(margin.history))
    m = margin.market(str(tmp_path), 20)
    assert m["sse"]["change"] == 0 and m["sse"]["list_changes"] == 1 and not m["szse"]["available"]
