import numpy as np
import pandas as pd
import pytest

from stockproof import plan


def _px(seed=0, n=240):
    rng = np.random.default_rng(seed)
    idx = pd.period_range("2005-01", periods=n, freq="M")
    cols = {}
    for a, (mu, sd) in {"hs300": (0.005, 0.08), "zz500": (0.006, 0.09), "bond": (0.003, 0.005),
                        "gold": (0.006, 0.05), "spx": (0.007, 0.045)}.items():
        cols[a] = 100 * np.cumprod(1 + rng.normal(mu, sd, n))
    return pd.DataFrame(cols, index=idx)


def test_tilt_buys_more_when_cheap():
    s = pd.Series(np.r_[np.linspace(100, 200, 60), [90.0]])
    assert plan.tilt(s, len(s) - 1) > 2.2                        # at the 5-year low
    s2 = pd.Series(np.r_[np.linspace(100, 200, 60), [300.0]])
    assert plan.tilt(s2, len(s2) - 1) == 0.25                    # at the 5-year high


def test_simulate_lump_and_dca():
    px = _px()
    lump = plan.simulate(px, {"hs300": 1.0}, "2005-01", initial=1.0, rebalance_months=0)
    assert lump["final"] == pytest.approx(px["hs300"].iloc[-1] / px["hs300"].iloc[0])
    dca = plan.simulate(px, plan.PROFILES["balanced"]["w"], "2005-01", monthly_amount=100.0)
    assert dca["contributed"] == 100.0 * len(px) and dca["irr"] is not None
    flat = pd.DataFrame(100.0, index=px.index, columns=px.columns)
    r = plan.simulate(flat, plan.PROFILES["balanced"]["w"], "2005-01", monthly_amount=100.0, use_tilt=False)
    assert abs(r["irr"]) < 1e-6                                  # flat prices, no tilt: no gain


def test_diversified_rebalanced_has_smaller_drawdown():
    px = _px(1)
    a = plan.simulate(px, {"hs300": 1.0}, "2005-01", initial=1.0)
    b = plan.simulate(px, plan.PROFILES["conservative"]["w"], "2005-01", initial=1.0)
    assert b["max_drawdown"] > a["max_drawdown"]


def test_this_month(tmp_path, monkeypatch):
    px = _px(2)
    monkeypatch.setattr(plan, "monthly", lambda d, fetch=True: px)
    r = plan.this_month(str(tmp_path), "balanced", 1000, holdings={"hs300": 100, "bond": 900})
    assert {x["asset"] for x in r["rows"]} == set(plan.PROFILES["balanced"]["w"])
    assert r["rebalance"] and 0.25 <= r["a_multiplier"] <= 2.25
    other = sum(x["buy"] for x in r["rows"] if not plan.ASSETS[x["asset"]]["a"])
    assert other == pytest.approx(750)
