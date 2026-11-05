import numpy as np
import pandas as pd
import pytest

from stockproof import forecast as fc


def _px(signal: bool, n=80, days=1500, seed=0):
    rng = np.random.default_rng(seed)
    idx = pd.bdate_range("2015-01-01", periods=days)
    quality = rng.normal(size=n)                                  # a persistent trait
    drift = (0.0006 * quality) if signal else np.zeros(n)
    r = rng.normal(0, 0.015, (days, n)) + drift
    return pd.DataFrame(100 * np.cumprod(1 + r, axis=0), index=idx, columns=[f"{600000 + i}.SH" for i in range(n)])


@pytest.mark.parametrize("signal", [True, False])
def test_walk_forward_finds_planted_signal_and_not_noise(tmp_path, monkeypatch, signal):
    px = _px(signal)
    monkeypatch.setattr(fc, "prices", lambda d: (px, "test"))
    F, p, _ = fc.panel(str(tmp_path), log=lambda *a: None)
    r = fc.walk_forward(F, p, 63, pd.Timestamp("2050-01-01"))
    e = r["explore"]
    if signal:                                                    # momentum carries the persistent drift
        assert e["ic"] > 0.05 and r["weights"]["mom_12_1"] > 0
    else:
        assert abs(e["ic"]) < 0.08 and not r["passes"]
    assert e["periods"] >= 10 and len(r["latest"]) == px.shape[1]


def test_no_lookahead_in_training(tmp_path, monkeypatch):
    """A forecast made on day d must be the same whether or not later prices exist."""
    px = _px(True)
    monkeypatch.setattr(fc, "prices", lambda d: (px, "test"))
    F, p, _ = fc.panel(str(tmp_path), log=lambda *a: None)
    full = fc.walk_forward(F, p, 63, keep_preds=True)["_preds"]
    d = sorted(full)[10]
    cut = px[px.index <= d]
    monkeypatch.setattr(fc, "prices", lambda _: (cut, "test"))
    F2, p2, _ = fc.panel(str(tmp_path), log=lambda *a: None)
    part = fc.walk_forward(F2, p2, 63, keep_preds=True)["_preds"]
    pd.testing.assert_series_equal(full[d], part[d], check_names=False)


def test_stock_view_and_text():
    res = {"universe": "csi300", "stocks": 2, "cost": 0.0035, "horizons": {"3m": {
        "as_of": "2026-10-30", "passes": False, "explore": {"periods": 30, "ic": 0.02, "ic_t": 1.1, "net_per_year": 0.01,
                                                             "t": 0.6, "hit": 0.55},
        "holdout": {"periods": 4, "net": 0.002, "t": 0.3}, "stocks": {"600519.SH": {"pct": 0.91, "expected": 0.012}}}}}
    v = fc.stock_view(res, "600519.SH")
    assert v["horizons"][0]["pct"] == 0.91 and "没通过" in v["horizons"][0]["text"]
    assert fc.stock_view(res, "AAPL") is None
    assert any("3 个月" in x for x in fc.summary_text(res))
