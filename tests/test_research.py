"""Research toolkit: dates, windows, matching, statistics, report. No network."""

import json

import numpy as np
import pandas as pd
import pytest

from stockproof import research as rs
from stockproof.research_report import build_research_report
from stockproof.store import Store


def make_prices(days=200, tickers=("AAA", "BBB", "CCC", "DDD")):
    idx = pd.bdate_range("2024-01-01", periods=days)
    rng = np.random.default_rng(1)
    rets = rng.normal(0, 0.01, (days, len(tickers)))
    return pd.DataFrame(100 * np.exp(np.cumsum(rets, axis=0)), index=idx, columns=list(tickers))


class FakeCache:
    def __init__(self, files):
        self.files = dict(files)
        self.saved = {}

    def cached(self, name):
        return self.files.get(name)

    def save(self, name, data):
        self.saved[name] = data
        self.files[name] = data

    def submissions(self, cik):
        return self.files[f"submissions_{cik}.json"]


def block(rows):
    keys = ["form", "items", "accessionNumber", "filingDate", "acceptanceDateTime", "primaryDocument"]
    return {k: [r[i] for r in rows] for i, k in enumerate(keys)}


def test_event_index_after_close_moves_to_next_day():
    days = pd.bdate_range("2024-01-01", periods=10)       # Mon 1 Jan ...
    assert rs.event_index(days, "2024-01-03") == 2
    assert rs.event_index(days, "2024-01-03", after_close=True) == 3
    assert rs.event_index(days, "2024-01-06") == 5          # Saturday -> Monday
    assert rs.event_index(days, "2024-01-06", after_close=True) == 5   # not a trading day: no extra shift
    assert rs.event_index(days, "2030-01-01") is None


def test_window_sum_is_nan_when_the_window_is_in_the_future():
    v = np.array([0.01, 0.02, 0.03, 0.04])
    assert rs.window_sum(v, 1, 0, 1) == pytest.approx(0.05)
    assert np.isnan(rs.window_sum(v, 3, 0, 1))
    assert np.isnan(rs.window_sum(v, 0, -1, -1))


def test_after_close_reads_new_york_time():
    assert rs.after_close("2024-01-25T16:05:12.000Z")
    assert not rs.after_close("2024-01-25T08:30:00.000Z")
    assert not rs.after_close("")


def test_announcement_filings_uses_older_pages_and_skips_too_old_ones():
    recent = block([("8-K", "2.02,9.01", "a-3", "2024-04-25", "2024-04-25T16:30:00.000Z", "x.htm"),
                    ("8-K", "5.02", "a-x", "2024-03-01", "", "y.htm"),
                    ("10-Q", "", "q-1", "2024-04-30", "", "q.htm")])
    old_page = block([("8-K", "2.02", "a-2", "2024-01-25", "2024-01-25T07:00:00.000Z", "z.htm")])
    ancient = block([("8-K", "2.02", "a-0", "2010-01-25", "", "w.htm")])
    subs = {"filings": {"recent": recent, "files": [
        {"name": "CIK1-submissions-001.json", "filingFrom": "2023-06-01", "filingTo": "2024-02-01"},
        {"name": "CIK1-submissions-002.json", "filingFrom": "2009-01-01", "filingTo": "2011-01-01"}]}}
    cache = FakeCache({"submissions_1.json": subs, "CIK1-submissions-001.json": old_page,
                       "CIK1-submissions-002.json": ancient})
    out = rs.announcement_filings(cache, 1, "2016-01-01", fetch=False)
    assert [f["accession"] for f in out] == ["a-2", "a-3"]   # oldest first; 5.02 and 2010 left out


def test_match_announcements_prefers_8k_and_falls_back_to_10q():
    q = pd.DataFrame({"end": pd.to_datetime(["2023-12-31", "2024-03-31", "2024-06-30"]),
                      "filed": pd.to_datetime(["2024-02-01", "2024-05-01", "2024-08-01"]),
                      "eps": [1.0, 1.1, 1.2], "sue": [0.5, 1.0, -1.0]})
    filings = [{"accession": "a-2", "filed": "2024-01-25", "accepted": "2024-01-25T07:00:00.000Z",
                "primary": "z.htm", "form": "8-K"},
               {"accession": "a-3", "filed": "2024-04-25", "accepted": "2024-04-25T16:30:00.000Z",
                "primary": "x.htm", "form": "8-K"}]
    m = rs.match_announcements(q, filings)
    assert m["date_source"].tolist() == ["8-K", "8-K", "10-Q"]
    assert m["ann_after_close"].tolist() == [False, True, True]
    assert m.loc[2, "ann_date"] == "2024-08-01"


def test_earnings_events_measures_the_announcement_return():
    prices = make_prices()
    # plant a +10% jump in AAA on the day after an after-close announcement on 2024-03-05 (Tue)
    day0 = prices.index.get_loc(pd.Timestamp("2024-03-06"))
    prices.iloc[day0:, 0] *= 1.10
    ar = rs.abnormal_returns(prices)
    q = pd.DataFrame([{"ticker": "AAA", "end": pd.Timestamp("2023-12-31"), "eps": 1.0, "sue": 2.5,
                       "ann_date": "2024-03-05", "ann_after_close": True, "date_source": "8-K",
                       "accession": "a-1"}])
    ev = rs.earnings_events(q, ar)
    assert ev.loc[0, "day0"] == "2024-03-06"
    assert ev.loc[0, "reaction"] > 0.06            # ~ +10% minus a quarter of it via the market average
    assert not np.isnan(ev.loc[0, "drift"])


def test_bucket_table_and_ols():
    rng = np.random.default_rng(0)
    x = rng.normal(0, 1, 400)
    df = pd.DataFrame({"sue": x, "reaction": 0.01 * x + rng.normal(0, 0.01, 400),
                       "drift": rng.normal(0, 0.05, 400)})
    tab = rs.bucket_table(df, "sue", rs.SUE_EDGES, rs.SUE_LABELS)
    assert tab["bucket"].tolist()[-1] == "top − bottom"
    assert tab.iloc[-1]["reaction"] > 0 and tab.iloc[-1]["reaction_t"] > 5
    fit = rs.ols(df["reaction"], df[["sue"]])
    assert fit["coef"]["sue"] == pytest.approx(0.01, abs=0.002)
    assert fit["t"]["sue"] > 10 and 0 < fit["r2"] < 1


def test_news_events_and_report(tmp_path):
    prices = make_prices()
    ar = rs.abnormal_returns(prices)
    store = Store(str(tmp_path))
    ids = store.add_headlines("AAA", [{"title": "AAA beats", "published": "2024-03-05"},
                                      {"title": "AAA beats again", "published": "2024-03-05"},
                                      {"title": "Market news", "published": "2024-03-05"},
                                      {"title": "AAA tomorrow", "published": "2030-01-01"}])
    store.save_score(ids[0], "m", "en", {"relevance": 0.9, "score": 0.6, "reason": ""})
    store.save_score(ids[1], "m", "en", {"relevance": 0.9, "score": 0.6, "reason": "", "duplicate_of": ids[0]})
    store.save_score(ids[2], "m", "en", {"relevance": 0.1, "score": 0.6, "reason": ""})
    store.save_score(ids[3], "m", "en", {"relevance": 0.9, "score": -0.6, "reason": ""})
    nv = rs.news_events(store, ar)
    assert len(nv) == 2                                   # duplicate and irrelevant ones left out
    future = nv[nv["published"] == "2030-01-01"].iloc[0]
    assert pd.isna(future["day0"]) and np.isnan(future["d1"])
    summ = rs.summarize_news(nv)
    assert summ["n_d1"] == 1

    res = {"prices": {"n": 4, "start": "2024-01-01", "end": "2024-10-01", "spy": False},
           "earnings": {"n": 0}, "news": summ}
    for lang in ("en", "zh"):
        page = build_research_report(res, lang=lang, files=["x.csv"])
        assert "<table>" in page and "x.csv" in page


def test_summarize_earnings_with_tone(tmp_path):
    rng = np.random.default_rng(3)
    n = 120
    sue = rng.normal(0, 1.5, n)
    tone = np.clip(rng.normal(0, 0.5, n), -1, 1)
    ev = pd.DataFrame({"ticker": [f"T{i % 10}" for i in range(n)], "sue": sue, "tone": tone,
                       "guidance": rng.choice(["raised", "none", "provided"], n),
                       "date_source": ["8-K"] * 100 + ["10-Q"] * 20,
                       "day0": pd.date_range("2020-01-01", periods=n, freq="W").strftime("%Y-%m-%d"),
                       "reaction": 0.005 * sue + 0.02 * tone + rng.normal(0, 0.01, n),
                       "drift": rng.normal(0, 0.05, n)})
    s = rs.summarize_earnings(ev)
    assert s["n_8k"] == 100 and s["n_tone"] == 100
    with_tone = s["reg_tone"]["reaction"]["sue+tone"]
    assert with_tone["r2"] > s["reg_tone"]["reaction"]["sue"]["r2"]
    page = build_research_report({"earnings": {**s, "n_stocks": 10}, "news": {"n": 0}}, lang="en")
    assert "sue+tone" in page


def test_backfill_reads_saves_and_skips_cached(tmp_path, monkeypatch):
    from stockproof import earnings as er

    class FakeClient:
        model = "fake"
        def chat_json(self, prompt):
            return {"tone": 0.5, "guidance": "raised", "summary": "ok"}

    calls = []
    def fake_fetch(cik, filing):
        calls.append(filing["accession"])
        return ("Results for the quarter. Revenue up.", f"https://sec/{filing['accession']}")
    monkeypatch.setattr(er, "fetch_release_text", fake_fetch)
    store = Store(str(tmp_path))
    ev = pd.DataFrame({"ticker": ["AAA"] * 3 + ["BBB"], "cik": [1, 1, 1, 2],
                       "accession": ["a1", "a2", "a3", None], "primary": ["x"] * 4,
                       "ann_date": ["2024-01-01", "2024-04-01", "2024-07-01", "2024-07-01"]})
    stats = rs.backfill_reads(store, FakeClient(), "p:fake", ev, {}, per_ticker=2, log=lambda m: None)
    assert stats == {"read": 2, "cached": 0, "failed": 0}
    assert sorted(calls) == ["a2", "a3"]                  # newest 2; no accession -> skipped
    again = rs.backfill_reads(store, FakeClient(), "p:fake", ev, {}, per_ticker=2, log=lambda m: None)
    assert again == {"read": 0, "cached": 2, "failed": 0}
    out = rs.attach_reads(ev, store, f"p:fake#v{er.READ_VERSION}")
    assert out["tone"].tolist()[1:3] == [0.5, 0.5] and out["guidance"].iloc[2] == "raised"


def test_saved_results_feed_the_dashboard(tmp_path):
    from stockproof.dashboard import Dashboard
    d = str(tmp_path)
    app = Dashboard(d, "deepseek", None, None)
    assert app.research_page("us", "en") is None and app.state()["research"] == {"us": None, "cn": None}
    rng = np.random.default_rng(2)
    n = 60
    ev = pd.DataFrame({"ticker": ["AAA"] * n, "sue": rng.normal(0, 1, n), "date_source": "8-K",
                       "day0": pd.date_range("2018-01-01", periods=n, freq="QS").strftime("%Y-%m-%d"),
                       "reaction": rng.normal(0, 0.02, n), "drift": rng.normal(0, 0.05, n),
                       "reaction_10q": rng.normal(0, 0.02, n), "drift_10q": rng.normal(0, 0.05, n),
                       "accession": None, "primary": None})
    rs.save_results(d, "us", ev, pd.DataFrame(), {"n": 1, "start": "2018", "end": "2026"}, "p.csv")
    assert app.state()["research"]["us"] is not None
    page = app.research_page("us", "zh")
    assert "财报惊喜" in page and "<table>" in page


def test_benchmark_choice():
    idx = pd.bdate_range("2024-01-01", periods=3)
    p = pd.DataFrame({"A": [1, 1.1, 1.1], "B": [1, 1.0, 1.1], "SPY": [1, 1.05, 1.05]}, index=idx)
    ew = rs.abnormal_returns(p)
    assert list(ew.columns) == ["A", "B"] and ew.iloc[1]["A"] == pytest.approx(0.05)
    ix = rs.abnormal_returns(p, use_index=True)
    assert ix.iloc[1]["A"] == pytest.approx(0.05) and ix.iloc[1]["B"] == pytest.approx(-0.05)


def test_history_for_and_dashboard_alerts(tmp_path):
    import datetime as dt
    from stockproof.dashboard import Dashboard
    rng = np.random.default_rng(4)
    n = 400
    ev = pd.DataFrame({"ticker": "AAA", "sue": rng.normal(0, 1.5, n), "tone": rng.uniform(-1, 1, n),
                       "date_source": "8-K", "day0": "2020-01-02",
                       "reaction": rng.normal(0, 0.02, n), "drift": rng.normal(0, 0.05, n)})
    h = rs.history_for(ev, sue=1.0, tone=0.5)
    assert h["sue"]["bucket"] == "0.5 to 2" and h["sue"]["n"] == int(((ev.sue > 0.5) & (ev.sue <= 2)).sum())
    assert h["tone"]["bucket"] == "positive"
    assert rs.history_for(ev.iloc[:5], sue=1.0) == {}                     # too few to say anything

    d = str(tmp_path)
    rs.save_results(d, "us", ev, pd.DataFrame(), {"n": 1}, "p.csv")
    app = Dashboard(d, "deepseek", None, None)
    app.set_watchlist(["MSFT", "00700"])
    store = app._store()
    today = dt.date.today().isoformat()
    store.save_earnings_read("acc-1", "deepseek:deepseek-chat#v3", "en", "MSFT", today, "https://x",
                             {"tone": 0.6, "guidance": "raised", "summary": "s"})
    store.save_earnings_read("acc-2", "deepseek:deepseek-chat#v3", "en", "00700.HK", "2020-01-01", "https://y",
                             {"tone": 0.1, "guidance": "none", "summary": "s"})
    al = app.alerts("en")
    assert [a["ticker"] for a in al] == ["MSFT"]                           # the old HK report is not recent
    assert al[0]["sue"] is None and al[0]["history"]["tone"]["bucket"] == "positive"
    stock = app.stock("00700.HK", "en")
    assert stock["history_like"] == {"market": None}                       # no Hong Kong study
