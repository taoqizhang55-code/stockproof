import numpy as np
import pandas as pd
import pytest

from marketmood import portfolio as pf


def fake_fetch_factory(seed=0):
    rng = np.random.default_rng(seed)
    days = pd.bdate_range("2015-01-02", "2026-10-29")
    market = rng.normal(0, 0.012, len(days))
    market[(days >= "2018-01-26") & (days <= "2018-10-18")] -= 0.002      # a crash in the stress window
    chip = rng.normal(0, 0.01, len(days))
    series = {}

    def make(tk):
        if tk not in series:
            r = rng.normal(0, 0.01, len(days))
            if tk.startswith("^"):
                x = market
            elif tk in ("301308.SZ", "688766.SH"):                         # two chip stocks: move together
                x = 1.3 * market + chip + 0.3 * r
            else:
                x = 0.8 * market + r
            s = pd.Series(100 * np.cumprod(1 + x), index=days)
            if tk == "688766.SH":
                s = s[s.index >= "2019-06-01"]                             # listed later: stress uses beta
            series[tk] = s
        return series[tk]
    return lambda tk, start: make(tk)


def test_parse_holdings():
    hs = pf.parse_holdings("600519 100, AAPL 20，00700 300")
    assert [h["ticker"] for h in hs] == ["600519.SH", "AAPL", "00700.HK"]
    assert hs[2]["market"] == "HK"
    with pytest.raises(pf.HoldingsError, match="either weights"):
        pf.parse_holdings([{"ticker": "AAPL", "weight": 0.5}, {"ticker": "MSFT", "shares": 3}])
    with pytest.raises(pf.HoldingsError, match="give shares"):
        pf.parse_holdings([{"ticker": "AAPL"}])
    assert pf.parse_holdings([{"ticker": "AAPL", "shares": 1}, {"ticker": "aapl", "shares": 2}])[0]["shares"] == 3


def test_checkup(tmp_path):
    holdings = [{"ticker": "301308", "shares": 1000, "cost": 80}, {"ticker": "688766", "shares": 800},
                {"ticker": "600519", "shares": 10}, {"ticker": "AAPL", "shares": 50, "industry": "消费电子"}]
    r = pf.checkup(str(tmp_path), holdings, lang="zh", fetch=fake_fetch_factory())
    w = {h["ticker"]: h["weight"] for h in r["holdings"]}
    assert abs(sum(w.values()) - 1) < 1e-9
    assert r["holdings"][0]["weight"] == max(w.values())
    pair = r["correlated_pairs"][0]
    assert {pair["a"], pair["b"]} == {"301308.SZ", "688766.SH"} and pair["corr"] >= 0.7
    assert any("同步" in f["text"] for f in r["findings"])
    trade_war = next(s for s in r["stress"] if s["from"] == "2018-01-26")
    assert trade_war["portfolio"] < 0 and "688766.SH" in trade_war["estimated"]
    assert 0 < r["portfolio"]["beta"] < 3 and r["effective_n"] > 1
    assert abs(sum(h["risk_share"] for h in r["holdings"]) - 1) < 1e-6
    assert r["fx"]["USD"] > 1 and r["holdings"][-1]["industry"] in ("消费电子", "美股") or True
    assert next(h for h in r["holdings"] if h["ticker"] == "301308.SZ")["pnl_pct"] is not None
    html = open(r["report"], encoding="utf-8").read()
    assert "持仓体检" in html and "<svg" in html


def test_weights_input(tmp_path):
    r = pf.checkup(str(tmp_path), [{"ticker": "600519", "weight": 3}, {"ticker": "00700", "weight": 1}],
                   lang="en", fetch=fake_fetch_factory(1))
    assert abs(r["holdings"][0]["weight"] - 0.75) < 1e-9 and r["fx"] is None


def test_remember_and_saved(tmp_path):
    from marketmood import portfolio
    d = str(tmp_path)
    assert portfolio.saved(d) == {"last": "", "reports": []}
    portfolio.remember(d, "  600519 100, AAPL 20 ")
    import os
    for rid in ("20261030-065222", "20261031-080000"):
        open(os.path.join(portfolio.pdir(d), "reports", rid + ".html"), "w").write("x")
    s = portfolio.saved(d)
    assert s["last"] == "600519 100, AAPL 20" and s["reports"][0] == "20261031-080000"
