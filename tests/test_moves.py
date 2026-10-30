"""Prices, unusual moves and "why did it move". Synthetic data, fake LLM, no network."""

import datetime as dt
import json

import numpy as np
import pandas as pd
import pytest

from marketmood import explain, quotes
from marketmood.store import Store


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
