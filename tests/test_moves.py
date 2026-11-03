"""Prices, unusual moves and "why did it move". Synthetic data, fake LLM, no network."""

import datetime as dt
import json

import numpy as np
import pandas as pd
import pytest

from stockproof import explain, quotes
from stockproof.store import Store


def write(data_dir, ticker, closes, days):
    s = pd.Series(closes, index=days, name="close")
    p = quotes._path(str(data_dir), ticker)
    import os
    os.makedirs(os.path.dirname(p), exist_ok=True)
    s.to_frame().to_csv(p)


def setup_prices(tmp_path, jump_day=-2, jump=0.08):
    days = pd.bdate_range(end=pd.Timestamp(dt.date.today()), periods=120)
    rng = np.random.default_rng(0)
    m = 100 * np.cumprod(1 + rng.normal(0, 0.008, 120))
    r = rng.normal(0, 0.01, 120)
    r[jump_day] += jump
    write(tmp_path, "^CSI300", m, days)
    write(tmp_path, "300750.SZ", 200 * np.cumprod(1 + r + np.r_[0, np.diff(m) / m[:-1]]), days)
    return days


def test_moves_flags_the_jump(tmp_path):
    days = setup_prices(tmp_path)
    m = quotes.moves(str(tmp_path), "300750.SZ")
    flagged = m[m["unusual"]].index
    assert days[-2] in flagged
    assert m.loc[days[-2], "excess"] > 0.04
    s = quotes.summary(str(tmp_path), "300750.SZ")
    assert s["move"]["date"] == days[-2].date().isoformat() and len(s["spark"]) == 60
    u = explain.unusual_today(str(tmp_path), ["300750.SZ"])
    assert u and u[0]["day"] == days[-2].date().isoformat()


def test_market_of():
    assert quotes.market_of("600519.SH") == "A" and quotes.market_of("00700.HK") == "HK"
    assert quotes.market_of("AAPL") == "US" and quotes.market_of("^HSI") == "HK"


def test_explain_uses_only_collected_evidence(tmp_path):
    days = setup_prices(tmp_path)
    day = days[-2].date().isoformat()
    store = Store(str(tmp_path))
    ids = store.add_headlines("300750.SZ", [{"title": "宁德时代发布新电池，订单大增", "published": day, "link": "https://n/1"},
                                            {"title": "旧闻", "published": "2000-01-01", "link": "https://n/0"}])
    for hid in ids:
        store.save_score(hid, "m", "zh", {"relevance": 0.9, "score": 0.7, "reason": "利好"})
    prompts = []

    class FakeClient:
        model = "m"
        def chat_json(self, prompt):
            prompts.append(prompt)
            return {"summary": "新电池发布带动上涨 [1]。", "confidence": "medium", "explained": True,
                    "causes": [{"text": "新产品", "evidence": [1, 7]}]}

    out = explain.explain(store, FakeClient(), "p:m", str(tmp_path), "300750.SZ", day, "宁德时代", "zh")
    assert [e["title"] for e in out["evidence"]] == ["宁德时代发布新电池，订单大增"]   # old news left out
    assert out["causes"][0]["evidence"] == [1]                                       # [7] doesn't exist
    assert "ONLY facts" in prompts[0] and "宁德时代发布新电池" in prompts[0]
    again = explain.explain(store, FakeClient(), "p:m", str(tmp_path), "300750.SZ", day, "宁德时代", "zh")
    assert len(prompts) == 1 and again["summary"] == out["summary"]                  # cached
    none = explain.explain(store, None, "p:m", str(tmp_path), "300750.SZ", "2000-01-03", "x", "zh")
    assert none["error"] == "not_a_trading_day"


def test_explain_without_evidence_is_never_marked_explained(tmp_path):
    days = setup_prices(tmp_path)

    class Overconfident:
        model = "m"
        def chat_json(self, prompt):
            return {"summary": "x", "confidence": "high", "explained": True, "causes": []}
    out = explain.explain(Store(str(tmp_path)), Overconfident(), "p:m", str(tmp_path), "300750.SZ",
                          days[-2].date().isoformat(), "x", "en")
    assert out["evidence"] == [] and out["explained"] is False


def test_attribution_splits_market_and_own(tmp_path):
    import numpy as np
    import pandas as pd
    from stockproof import explain
    d = tmp_path / "quotes"
    d.mkdir()
    idx = pd.bdate_range("2026-01-01", periods=160)
    rng = np.random.default_rng(0)
    mkt = rng.normal(0, 0.01, len(idx))
    own = rng.normal(0, 0.005, len(idx))
    mkt[-1], own[-1] = -0.02, -0.01                       # last day: market -2%, own -1%
    stock = 1.5 * mkt + own
    pd.DataFrame({"close": 100 * np.cumprod(1 + stock)}, index=idx).to_csv(d / "AAPL.csv")
    pd.DataFrame({"close": 100 * np.cumprod(1 + mkt)}, index=idx).to_csv(d / "_SPX.csv")
    a = explain.attribution(str(tmp_path), "AAPL", idx[-1].date().isoformat(), fetch=False)
    assert abs(a["beta_market"] - 1.5) < 0.2 and abs(a["market_part"] - (-0.03)) < 0.005
    assert abs(a["own_part"] - (-0.01)) < 0.005 and a["industry_part"] is None
    p = explain.build_prompt("Apple", "AAPL", idx[-1].date().isoformat(), {"ret": a["ret"], "market": -0.02, "excess": 0.0},
                             [{"date": "2026-01-02", "kind": "news", "title": "old"}], "zh", a)
    assert "Attribution" in p and "background_" in p


def test_us_attribution_uses_sector_etf(tmp_path, monkeypatch):
    import numpy as np
    import pandas as pd
    from stockproof import explain
    assert explain.sector_etf(3674) == ("SMH", "Semiconductors")
    assert explain.sector_etf("7372")[0] == "XLK" and explain.sector_etf(6022)[0] == "XLF"
    assert explain.sector_etf(6798)[0] == "XLRE" and explain.sector_etf(None) is None
    d = tmp_path / "quotes"
    d.mkdir()
    idx = pd.bdate_range("2026-01-01", periods=160)
    rng = np.random.default_rng(1)
    mkt = rng.normal(0, 0.01, len(idx))
    sec = rng.normal(0, 0.008, len(idx))                  # sector beyond the market
    own = rng.normal(0, 0.004, len(idx))
    mkt[-1], sec[-1], own[-1] = -0.01, -0.04, -0.005      # a semiconductor sell-off
    etf = mkt + sec
    stock = mkt + sec + own
    pd.DataFrame({"close": 100 * np.cumprod(1 + stock)}, index=idx).to_csv(d / "NVDA.csv")
    pd.DataFrame({"close": 100 * np.cumprod(1 + mkt)}, index=idx).to_csv(d / "_SPX.csv")
    pd.DataFrame({"close": 100 * np.cumprod(1 + etf)}, index=idx).to_csv(d / "SMH.csv")
    monkeypatch.setattr(explain, "_us_sector", lambda *a, **k: ("SMH", "Semiconductors"))
    a = explain.attribution(str(tmp_path), "NVDA", idx[-1].date().isoformat(), fetch=False)
    assert a["industry"] == "Semiconductors (SMH)"
    assert abs(a["industry_part"] - (-0.04)) < 0.008 and abs(a["own_part"] - (-0.005)) < 0.008
