import numpy as np
import pandas as pd

from stockproof import nt_research as nr


def test_bonferroni_bar():
    assert nr.bonferroni_t(1) == 1.96
    assert 3.0 < nr.bonferroni_t(24) < 3.2


def test_vs_others_uses_same_month_baseline():
    rng = np.random.default_rng(0)
    days = pd.to_datetime(np.repeat(pd.date_range("2018-01-31", periods=40, freq="ME"), 50))
    month_effect = np.repeat(rng.normal(0, 0.05, 40), 50)      # report-season swings hit everyone
    g = np.tile([True] * 10 + [False] * 40, 40)
    ex = month_effect + rng.normal(0, 0.02, len(days)) + np.where(g, 0.03, 0.0)
    ev = pd.DataFrame({"day0": days, "ex": ex})
    r = nr._vs_others(ev, pd.Series(g))
    assert abs(r["diff"] - 0.03) < 0.01 and r["t"] > 5 and r["months"] == 40
    null = nr._vs_others(ev.assign(ex=month_effect + rng.normal(0, 0.02, len(days))), pd.Series(g))
    assert abs(null["t"]) < 3


def test_logit_and_auc_find_the_signal():
    rng = np.random.default_rng(1)
    x = rng.normal(size=(4000, 2))
    y = (rng.random(4000) < 1 / (1 + np.exp(-(-3 + 1.5 * x[:, 0])))).astype(float)
    w = nr._logit_fit(np.c_[np.ones(4000), x], y)
    assert w[1] > 1.0 and abs(w[2]) < 0.3
    assert nr._auc(x[:, 0], y) > 0.75 and abs(nr._auc(x[:, 1], y) - 0.5) < 0.06


def test_predict_walk_forward_never_trains_on_the_future(monkeypatch):
    rng = np.random.default_rng(2)
    qs = [d.strftime("%Y%m%d") for d in pd.date_range("2016-03-31", periods=16, freq="QE")]
    tks = [f"{600000 + i}.SH" for i in range(60)]
    rows = []
    for q in qs + ["20200331"]:
        for t in tks:
            f = {k: rng.normal() for k in nr.FEATURES}
            y = np.nan if q == "20200331" else float(rng.random() < (0.5 if f["ever_national"] > 1 else 0.02))
            rows.append({"quarter": q, "ticker": t, "code": t[:6], **f, "y": y, "public": None})
    panel = pd.DataFrame(rows)
    days = pd.bdate_range("2016-01-01", "2020-12-31")
    px = pd.DataFrame(100.0, index=days, columns=tks)
    monkeypatch.setattr("stockproof.lab.stock_prices", lambda d, m: px)
    r = nr.predict_test("/x", panel, k=5)
    assert r["available"] and r["lift"] > 2 and r["quarters"][0]["quarter"] == qs[8]
    assert r["latest_quarter"] == "20200331" and len(r["latest_picks"]) == 5
    assert r["excess_per_quarter"] == 0.0                         # flat prices: no fake profit
