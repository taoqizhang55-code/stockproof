"""China research study: de-cumulation, dates, prices. Fake AKShare, no network."""

import datetime as dt
import sys
import types

import numpy as np
import pandas as pd
import pytest

from marketmood import research as rs
from marketmood import research_cn as rc
from marketmood.research_report import build_research_report


def test_period_ends():
    assert rc.period_ends("2024-01-01", dt.date(2024, 10, 1)) == ["20240331", "20240630", "20240930"]


def make_tables(code="000898", years=range(2018, 2025), eps_q=0.1, jump=None, noise=0.0):
    """Year-to-date EPS tables + disclosure dates for one company. `jump`: (period, extra EPS)."""
    tables = {}
    rng = np.random.default_rng(5)
    for y in years:
        ytd = 0.0
        for k, md in enumerate(["0331", "0630", "0930", "1231"], 1):
            date = f"{y}{md}"
            q = eps_q + (jump[1] if jump and jump[0] == date else 0.0) + noise * rng.normal()
            ytd += q
            disclosed = {"0331": f"{y}-04-25", "0630": f"{y}-08-20", "0930": f"{y}-10-28",
                         "1231": f"{y + 1}-03-28"}[md]
            tables[("yjbb", date)] = [{"code": code, "eps": round(ytd, 4), "date": disclosed},
                                      {"code": "999999", "eps": 1.0, "date": disclosed}]
            tables[("yysj", date)] = [{"code": code, "date": disclosed}]
            # preliminary results published earlier for the annual report only
            tables[("yjkb", date)] = [{"code": code, "date": f"{y + 1}-01-20"}] if md == "1231" else []
    return tables


def test_build_quarters_cn_decumulates_and_dates():
    tables = make_tables(jump=("20230630", 0.5))
    q = rc.build_quarters_cn(None, ["000898"], "2021-01-01", tables=tables, log=lambda m: None)
    assert set(q["ticker"]) == {"000898.SZ"}
    assert q["end"].min() >= pd.Timestamp("2021-01-01")
    assert np.allclose(q.loc[q["end"] != pd.Timestamp("2023-06-30"), "eps"], 0.1)
    row = q[q["end"] == pd.Timestamp("2023-06-30")].iloc[0]
    assert abs(row["eps"] - 0.6) < 1e-9 and row["ann_date"] == "2023-08-20"
    q4 = q[q["end"] == pd.Timestamp("2023-12-31")].iloc[0]
    assert q4["ann_date"] == "2024-01-20"                    # preliminary results came first
    assert q4["filed"] == pd.Timestamp("2024-04-30")         # legal deadline kept for comparison
    assert (q["date_source"] == "actual").all()


def test_china_events_and_report():
    tables = make_tables(years=range(2016, 2025), noise=0.02)
    q = rc.build_quarters_cn(None, ["000898"], "2019-01-01", tables=tables, log=lambda m: None)
    idx = pd.bdate_range("2018-06-01", "2025-12-31")
    rng = np.random.default_rng(0)
    prices = pd.DataFrame({"000898.SZ": 5 * np.exp(np.cumsum(rng.normal(0, 0.02, len(idx)))),
                           "CSI300": 4000 * np.exp(np.cumsum(rng.normal(0, 0.01, len(idx))))}, index=idx)
    ar = rs.abnormal_returns(prices)
    assert list(ar.columns) == ["000898.SZ"]                 # the index is the benchmark, not a stock
    ev = rc.summarize_by_actual(rs.earnings_events(q, ar))
    assert len(ev) and set(ev["date_source"]) == {"8-K"}
    s = rs.summarize_earnings(ev)
    s.update(market="cn", n_stocks=1)
    page = build_research_report({"prices": {"n": 1, "start": "2018", "end": "2025", "bench": "CSI300"},
                                  "earnings": s, "news": {"n": 0}}, lang="zh")
    assert "实际披露日" in page and "法定截止日" in page and "沪深 300" in page


def test_download_prices_cn_with_fake_akshare(tmp_path, monkeypatch):
    def hist(symbol, period, start_date, end_date, adjust):
        if symbol == "600519":
            raise ConnectionError("blocked")                  # forces the Sina fallback
        return pd.DataFrame({"日期": ["2024-01-02", "2024-01-03"], "收盘": [10.0, 11.0]})

    fake = types.SimpleNamespace(
        stock_zh_a_hist=hist,
        stock_zh_a_daily=lambda symbol, start_date, end_date, adjust:
            pd.DataFrame({"date": ["2024-01-02", "2024-01-03"], "close": [100.0, 99.0]}),
        stock_zh_index_daily=lambda symbol:
            pd.DataFrame({"date": ["2023-12-29", "2024-01-02", "2024-01-03"], "close": [1, 3500.0, 3510.0]}))
    monkeypatch.setitem(sys.modules, "akshare", fake)
    monkeypatch.setattr(rc.time, "sleep", lambda s: None)
    path = tmp_path / "p.csv"
    df = rc.download_prices_cn(["000898.SZ", "600519.SH", "00700.HK"], "2024-01-01", str(path), log=lambda m: None)
    assert list(df.columns) == ["000898.SZ", "600519.SH", "CSI300"]
    assert df.loc["2024-01-03", "600519.SH"] == 99.0
    assert len(rs.load_prices(str(path))) == 2


def test_period_table_retries(tmp_path, monkeypatch):
    from marketmood import cn
    calls = {"n": 0}

    def flaky(date):
        calls["n"] += 1
        if calls["n"] < 3:
            raise ConnectionError("Remote end closed connection")
        return pd.DataFrame({"股票代码": ["000898"], "每股收益": [0.1], "最新公告日期": ["2026-04-28"]})

    monkeypatch.setitem(sys.modules, "akshare", types.SimpleNamespace(stock_yjbb_em=flaky))
    monkeypatch.setattr(rc.time, "sleep", lambda s: None)
    recs = rc.period_table(cn.CNCache(str(tmp_path)), "yjbb", "20260331")
    assert calls["n"] == 3 and recs == [{"code": "000898", "eps": 0.1, "date": "2026-04-28"}]


ITEMS = [
    {"art_code": "A1", "title": "贵州茅台2025年年度报告摘要", "date": "2026-04-03", "column": "", "name": "贵州茅台"},
    {"art_code": "A2", "title": "贵州茅台2025年年度报告", "date": "2026-04-03", "column": "", "name": "贵州茅台"},
    {"art_code": "A3", "title": "贵州茅台2025年年度报告(英文版)", "date": "2026-04-03", "column": "", "name": "贵州茅台"},
    {"art_code": "A4", "title": "贵州茅台关于召开2025年度业绩说明会的公告", "date": "2026-04-03", "column": "", "name": "贵州茅台"},
    {"art_code": "B1", "title": "贵州茅台2025年半年度报告摘要", "date": "2025-08-13", "column": "", "name": "贵州茅台"},
    {"art_code": "C1", "title": "贵州茅台2026年第一季度报告", "date": "2026-04-28", "column": "", "name": "贵州茅台"},
    {"art_code": "D1", "title": "某银行2025年度业绩快报", "date": "2026-01-15", "column": "", "name": "某银行"},
    {"art_code": "D2", "title": "某公司2025年年度业绩预告", "date": "2026-01-15", "column": "", "name": "某公司"},
]


def test_report_doc_for_picks_the_right_document():
    assert rc.report_doc_for(ITEMS, "2025-12-31", "2026-04-03")["art_code"] == "A1"   # summary, not English
    assert rc.report_doc_for(ITEMS, "2025-06-30", "2025-08-13")["art_code"] == "B1"
    assert rc.report_doc_for(ITEMS, "2026-03-31", "2026-04-28")["art_code"] == "C1"
    assert rc.report_doc_for(ITEMS, "2025-12-31", "2026-01-15")["art_code"] == "D1"   # flash report, not forecast
    assert rc.report_doc_for(ITEMS, "2025-12-31", "2025-08-13") is None               # half-year ≠ annual
    assert rc.report_doc_for(ITEMS, "2024-12-31", "2026-04-03") is None               # wrong year


def test_find_docs_and_backfill_with_fakes(tmp_path, monkeypatch):
    from marketmood import cn
    from marketmood import earnings as er
    from marketmood.store import Store
    pages = {1: ITEMS[:6], 2: []}
    monkeypatch.setattr(cn, "announcements", lambda info, page_size=50, page_index=1: pages.get(page_index, []))
    monkeypatch.setattr(cn, "announcement_text", lambda code: (f"报告正文 {code}", f"https://pdf/{code}"))
    monkeypatch.setattr(rc.time, "sleep", lambda s: None)

    class FakeClient:
        model = "m"
        def chat_json(self, prompt):
            return {"tone": -0.4, "guidance": "none", "summary": "s"}

    cache = cn.CNCache(str(tmp_path))
    ev = pd.DataFrame({"ticker": ["600519.SH"] * 3, "end": ["2025-06-30", "2025-12-31", "2026-03-31"],
                       "ann_date": ["2025-08-13", "2026-04-03", "2026-04-28"], "sue": [0.1, 1.0, -1.0],
                       "date_source": "8-K"})
    store = Store(str(tmp_path))
    stats = rc.backfill_reads_cn(store, FakeClient(), "p:m", ev, cache, per_ticker=2, log=lambda m: None)
    assert stats["read"] == 2 and stats["no_document"] == 0               # newest 2: annual + Q1
    again = rc.backfill_reads_cn(store, FakeClient(), "p:m", ev, cache, per_ticker=2, log=lambda m: None)
    assert again["read"] == 0 and again["cached"] == 2
    out = rs.attach_reads(rc.attach_docs(ev, cache), store, f"p:m#v{er.READ_VERSION}")
    assert pd.isna(out["accession"].iloc[0]) and out["accession"].tolist()[1:] == ["A1", "C1"]
    assert out["tone"].tolist()[1:] == [-0.4, -0.4] and pd.isna(out["tone"].iloc[0])


def test_notices_that_mention_a_report_are_not_the_report():
    items = [{"art_code": "X", "title": "万科A:关于计提和核销2025年第三季度减值准备的公告", "date": "2025-10-31"},
             {"art_code": "Y", "title": "万科A:关于召开2025年第三季度业绩说明会的公告", "date": "2025-10-31"}]
    assert rc.report_doc_for(items, "2025-09-30", "2025-10-31") is None
    items.append({"art_code": "Z", "title": "万科A:2025年第三季度报告", "date": "2025-10-31"})
    assert rc.report_doc_for(items, "2025-09-30", "2025-10-31")["art_code"] == "Z"
    assert rc.valid_report_title("平安银行:2025年年度报告摘要")
    assert rc.valid_report_title("某银行:2025年度业绩快报")
    assert not rc.valid_report_title("某公司:关于2025年年度报告的更正公告")
    assert not rc.valid_report_title("宁波银行:宁波银行股份有限公司2026年第一季度第三支柱报告")


def test_eastmoney_backoff_then_blocked(monkeypatch):
    import requests
    from marketmood import cn
    calls = {"n": 0}

    def refuse(*a, **k):
        calls["n"] += 1
        raise requests.ConnectionError("Connection reset by peer")
    monkeypatch.setattr(cn.requests, "get", refuse)
    sleeps = []
    monkeypatch.setattr(cn.time, "sleep", lambda s: sleeps.append(s))
    with pytest.raises(cn.Blocked):
        cn.announcement_text("X")
    assert calls["n"] == 4 and [s for s in sleeps if s >= 3] == [3, 6, 12, 24]


def test_backfill_stops_when_blocked(tmp_path, monkeypatch):
    from marketmood import cn
    from marketmood.store import Store
    monkeypatch.setattr(cn, "announcements", lambda info, page_size=50, page_index=1: ITEMS[:6] if page_index == 1 else [])
    calls = {"n": 0}

    def blocked(code):
        calls["n"] += 1
        raise cn.Blocked("refusing")
    monkeypatch.setattr(cn, "announcement_text", blocked)
    ev = pd.DataFrame({"ticker": ["600519.SH"] * 3, "end": ["2025-06-30", "2025-12-31", "2026-03-31"],
                       "ann_date": ["2025-08-13", "2026-04-03", "2026-04-28"], "sue": [0.1, 1.0, -1.0],
                       "date_source": "8-K"})

    class C:
        model = "m"
        def chat_json(self, p): raise AssertionError("LLM must not be called")
    with pytest.raises(cn.Blocked):
        rc.backfill_reads_cn(Store(str(tmp_path)), C(), "p:m", ev, cn.CNCache(str(tmp_path)), 3,
                             log=lambda m: None, workers=1)
    assert calls["n"] == 1                                   # stopped at the first block
