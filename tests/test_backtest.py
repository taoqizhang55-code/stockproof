"""Backtest: trading rules, costs, slots. Synthetic prices, no network."""

import numpy as np
import pandas as pd
import pytest

from marketmood import backtest as bt


def prices_with(days=120, tickers=("600001.SH", "000002.SZ", "300003.SZ", "000004.SZ")):
    idx = pd.bdate_range("2024-01-01", periods=days)
    return pd.DataFrame(10.0, index=idx, columns=list(tickers))


def test_price_limits():
    assert bt.price_limit("600519.SH", "2024-01-02") == 0.10
    assert bt.price_limit("300750.SZ", "2020-01-02") == 0.10
    assert bt.price_limit("300750.SZ", "2021-01-04") == 0.20
    assert bt.price_limit("688981.SH", "2019-08-01") == 0.20
    assert bt.price_limit("AAPL", "2024-01-02") is None


def test_costs_follow_the_stamp_duty_cut():
    c = bt.Costs()
    assert c.sell("2023-08-25") == pytest.approx(0.00025 + 0.001 + 0.001)
    assert c.sell("2023-08-28") == pytest.approx(0.00025 + 0.001 + 0.0005)
    assert c.buy("2023-08-28") == pytest.approx(0.00125)


def test_limit_up_blocks_buying_and_the_order_waits():
    p = prices_with()
    day0 = p.index[10]
    p.iloc[11:, 0] = 11.0             # day 1 closes +10%: locked at limit-up, can't buy
    ev = pd.DataFrame({"ticker": ["600001.SH"], "sue": [3.0], "day0": [day0.date().isoformat()]})
    tr = bt.make_trades(ev, p, 2.0, -2.0, hold=20)
    assert tr.loc[0, "entry"] == 12   # bought the next day instead
    assert tr.loc[0, "exit"] == 32


def test_suspended_stock_waits_to_be_sold():
    p = prices_with()
    p.iloc[30:35, 1] = np.nan         # suspended on the planned exit day
    ev = pd.DataFrame({"ticker": ["000002.SZ"], "sue": [3.0], "day0": [p.index[10].date().isoformat()]})
    tr = bt.make_trades(ev, p, 2.0, -2.0, hold=20)
    assert tr.loc[0, "entry"] == 11 and tr.loc[0, "exit"] == 35


def test_returns_costs_and_slots():
    p = prices_with()
    # the bought stock gains 1% a day for 20 days; the others are flat
    for i in range(12, 32):
        p.iloc[i:, 0] *= 1.01
    ev = pd.DataFrame({"ticker": ["600001.SH"], "sue": [3.0], "day0": [p.index[10].date().isoformat()]})
    free = bt.Costs(commission=0, slippage=0, stamp_duty=0, stamp_duty_cut=None, stamp_duty_after=0)
    r = bt.run(ev, p, "cn", hold=20, costs=free, slots=1)
    gross = (1 + r["long"]).prod() - 1
    assert gross == pytest.approx(1.01 ** 20 - 1, rel=1e-6)
    r_cost = bt.run(ev, p, "cn", hold=20, slots=1)
    assert (1 + r_cost["long"]).prod() - 1 < gross - 0.002          # buy + sell costs taken
    r20 = bt.run(ev, p, "cn", hold=20, costs=free, slots=20)
    # one position in 20 slots: 1/20 of the stock, the rest in the (equal-weighted) market
    day = 15
    assert r20["long"].iloc[day] == pytest.approx(0.05 * r["long"].iloc[day] + 0.95 * r20["bench"].iloc[day])
    assert r20["trades"]["side"].tolist() == [1]


def test_full_is_json_safe_and_has_the_sweep():
    import json
    rng = np.random.default_rng(0)
    idx = pd.bdate_range("2020-01-01", periods=600)
    tick = [f"{600000 + i}.SH" for i in range(30)]
    p = pd.DataFrame(10 * np.exp(np.cumsum(rng.normal(0, 0.01, (600, 30)), axis=0)), index=idx, columns=tick)
    ev = pd.DataFrame({"ticker": rng.choice(tick, 300), "sue": rng.normal(0, 2, 300),
                       "day0": rng.choice(idx[:500], 300).astype("datetime64[ns]").astype(str)})
    out = bt.full(ev, p, "cn")
    json.dumps(out)
    assert out["n_long"] > 0 and len(out["sweep"]) == 6
    assert "long_excess_gross" in out and out["curve"]["dates"]
    from marketmood.research_report import build_research_report
    for lang, word in (("en", "before costs"), ("zh", "扣成本前")):
        page = build_research_report({"earnings": {"n": 0}, "news": {"n": 0}, "backtest": out}, lang=lang)
        assert word in page and "<polyline" in page
