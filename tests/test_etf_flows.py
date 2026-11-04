import datetime as dt

import numpy as np
import pandas as pd

from stockproof import etf_flows


def test_flags_big_creation_on_a_down_day(tmp_path, monkeypatch):
    end = dt.date(2026, 10, 30)
    days = pd.bdate_range(end - dt.timedelta(days=260), end)
    rng = np.random.default_rng(0)
    base = {c: 1e10 + np.cumsum(rng.normal(0, 2e7, len(days))) for c in etf_flows.KEY_ETFS}
    spike = days[-5]
    for c in ("510300", "510310"):
        base[c][days.get_loc(spike):] += 1.5e9                     # 1.5B units each, NAV 4 -> 12B yuan

    class Ak:
        def fund_etf_scale_sse(self, date):
            d = pd.Timestamp(date)
            if d not in days:
                return pd.DataFrame()
            i = days.get_loc(d)
            return pd.DataFrame({"基金代码": list(base), "基金份额": [base[c][i] for c in base]})

        def fund_etf_fund_info_em(self, fund, start_date, end_date):
            nav = np.full(len(days), 4.0)
            nav[days.get_loc(spike):] = 3.88                          # the index fell 3% that day
            return pd.DataFrame({"净值日期": days.strftime("%Y-%m-%d"), "单位净值": nav})
    monkeypatch.setattr(etf_flows.cn, "_ak", lambda: Ak())
    q = tmp_path / "quotes"
    q.mkdir()
    idx = pd.Series(4000 * np.cumprod(1 + rng.normal(0, 0.005, len(days))), index=days)
    idx.loc[spike] = idx.iloc[days.get_loc(spike) - 1] * 0.97           # the index fell 3% that day
    idx.rename("close").rename_axis("date").to_frame().to_csv(q / "_CSI300.csv")
    monkeypatch.setattr("stockproof.quotes.update", lambda *a, **k: None)
    df = etf_flows.daily(str(tmp_path), days=60, log=lambda *a: None, start=days[0].date(), end=end)
    assert bool(df.loc[spike, "flag"]) and abs(df.loc[spike, "total"] - 1.5e9 * 2 * 3.88) < 1e9
    assert int(df["flag"].sum()) == 1
    s = etf_flows.summary(str(tmp_path), days=30, log=lambda *a: None) if False else None
    # cached: a second run needs no network
    monkeypatch.setattr(etf_flows.cn, "_ak", lambda: (_ for _ in ()).throw(RuntimeError("offline")))
    df2 = etf_flows.daily(str(tmp_path), days=60, fetch=False, log=lambda *a: None, start=days[0].date(), end=end)
    assert bool(df2.loc[spike, "flag"])
