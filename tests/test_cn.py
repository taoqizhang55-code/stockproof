"""China module tests. A fake `akshare` module and fake Eastmoney responses reproduce the
exact shapes recorded by tools/china_probe.py on a real machine (2026-10-28)."""

import datetime as dt
import os
import shutil
import sys
import tempfile
import types
import unittest
from unittest import mock

import pandas as pd

from stockproof import cli, cn, core
from stockproof.eps import add_sue
from stockproof.store import Store


# ---------------------------------------------------------------- fakes
def fake_news(symbol):
    return pd.DataFrame({
        "关键词": [symbol] * 3,
        "新闻标题": ["贵州茅台三季度营收增长", "贵州茅台三季度营收增长", "大盘午后走弱 千元股仅剩一只"],
        "新闻内容": ["公司公告三季度营收同比增长8%。", "重复", "A股市场走弱，千元股仅剩贵州茅台。"],
        "发布时间": ["2026-10-27 14:49:40", "2026-10-27 14:50:00", "2026-10-26 09:00:00"],
        "文章来源": ["21世纪经济报道"] * 3,
        "新闻链接": ["http://finance.eastmoney.com/a/1.html", "http://x/2", "http://x/3"],
    })


def fake_abstract(symbol):
    # year-to-date 基本每股收益, like Sina's 财务摘要 (columns = report dates, newest first)
    cols = {"选项": ["常用指标", "每股指标"], "指标": ["归母净利润", "基本每股收益"]}
    ytd = {"20260630": 35.5, "20260331": 21.6, "20251231": 65.0, "20250930": 51.0,
           "20250630": 34.0, "20250331": 20.0, "20241231": 60.0, "20240930": 46.0,
           "20240630": 31.0, "20240331": 18.0, "20231231": 55.0, "20230930": 41.0,
           "20230630": 28.0, "20230331": 16.0}
    for k, v in ytd.items():
        cols[k] = [1e10, v]
    return pd.DataFrame(cols)


def fake_hk(symbol, indicator):
    rows = []
    for (end, eps) in [("2026-06-30", 12.639), ("2026-03-31", 6.431), ("2025-12-31", 24.0),
                       ("2025-09-30", 17.5), ("2025-06-30", 11.4), ("2025-03-31", 5.8),
                       ("2024-12-31", 21.0), ("2024-06-30", 10.0)]:
        rows.append({"SECUCODE": "00700.HK", "REPORT_DATE": end + " 00:00:00", "BASIC_EPS": str(eps),
                     "START_DATE": end[:4] + "-01-01 00:00:00", "FISCAL_YEAR": "12-31"})
    return pd.DataFrame(rows)


def fake_yjyg(date):
    if date != "20260930":
        return pd.DataFrame(columns=["股票代码"])
    return pd.DataFrame({
        "股票代码": ["600519", "600519", "688410"],
        "股票简称": ["贵州茅台"] * 2 + ["山外山"],
        "预测指标": ["归属于上市公司股东的净利润", "扣除非经常性损益后的净利润", "归属于上市公司股东的净利润"],
        "业绩变动": ["预计增长", "预计增长", "预计增长"],
        "预测数值": [1.0, 1.0, 1.0],
        "业绩变动幅度": [12.5, 11.0, 51.8],
        "业绩变动原因": ["直销渠道放量", "同左", "产品放量"],
        "预告类型": ["预增", "预增", "预增"],
        "上年同期值": [1.0, 1.0, 1.0],
        "公告日期": ["2026-10-15", "2026-10-15", "2026-10-24"],
    })


def fake_akshare():
    m = types.ModuleType("akshare")
    m.__version__ = "test"
    m.stock_news_em = fake_news
    m.stock_financial_abstract = fake_abstract
    m.stock_financial_hk_analysis_indicator_em = fake_hk
    m.stock_yjyg_em = fake_yjyg
    return m


ANN_LIST = {"data": {"list": [
    {"art_code": "AN1", "title": "贵州茅台:关于召开2026年半年度业绩说明会的公告", "notice_date": "2026-08-15 00:00:00",
     "columns": [{"column_name": "其他"}], "codes": [{"short_name": "贵州茅台", "stock_code": "600519"}]},
    {"art_code": "AN2", "title": "贵州茅台:2026年半年度报告", "notice_date": "2026-08-15 00:00:00",
     "columns": [{"column_name": "半年度报告全文"}], "codes": [{"short_name": "贵州茅台"}]},
    {"art_code": "AN3", "title": "贵州茅台:2026年半年度报告摘要", "notice_date": "2026-08-15 00:00:00",
     "columns": [{"column_name": "半年度报告摘要"}], "codes": [{"short_name": "贵州茅台"}]},
    {"art_code": "AN4", "title": "贵州茅台:2026年第一季度报告", "notice_date": "2026-04-25 00:00:00",
     "columns": [{"column_name": "一季度报告全文"}], "codes": [{"short_name": "贵州茅台"}]},
]}, "error": "", "success": 1}

ANN_TEXT = {"data": {"notice_content": "\n贵州茅台酒股份有限公司\n\n2026 年半年度报告摘要\n\n营业收入同比增长 1.3%……",
                     "attach_url": "https://pdf.dfcfw.com/pdf/H2_AN3_1.pdf"}}


GOOGLE_RSS = """<?xml version="1.0"?><rss><channel>
<item><title>贵州茅台三季度营收增长 - 新浪财经</title><link>https://g/1</link><pubDate>Tue, 27 Oct 2026 08:00:00 GMT</pubDate></item>
<item><title>贵州茅台直销渠道收入创新高 - 证券时报</title><link>https://g/2</link><pubDate>Wed, 28 Oct 2026 08:00:00 GMT</pubDate></item>
</channel></rss>"""

YAHOO_RSS = """<?xml version="1.0"?><rss><channel>
<item><title>Tencent shares rise after strong gaming quarter</title><link>https://y/1</link><pubDate>Wed, 28 Oct 2026 02:00:00 GMT</pubDate></item>
</channel></rss>"""


class FakeResp:
    def __init__(self, data, text=""):
        self.data = data
        self.text = text

    def raise_for_status(self):
        pass

    def json(self):
        return self.data


def fake_get(url, params=None, headers=None, timeout=None):
    if "news.google.com" in url:
        return FakeResp(None, GOOGLE_RSS)
    if "feeds.finance.yahoo.com" in url:
        assert "s=0700.HK" in url
        return FakeResp(None, YAHOO_RSS)
    if "content/ann" in url:
        return FakeResp(ANN_TEXT if params["art_code"] == "AN3" else {"data": {}})
    return FakeResp(ANN_LIST)


class FakeLLM:
    model = "fake"

    def __init__(self):
        self.prompts = []

    def chat_json(self, prompt):
        self.prompts.append(prompt)
        if "Headlines:" in prompt:
            lines = prompt.split("Headlines:\n")[1].split("\n\n")[0].splitlines()
            return {"items": [{"i": i, "relevance": 0.9 if "茅台" in l else 0.2, "score": 0.4, "reason": "测试"}
                              for i, l in enumerate(lines)]}
        return {"period": "2026年半年度", "tone": 0.3, "summary": "营收小幅增长。", "revenue_growth": "+1.3%",
                "eps": "35.5", "guidance": "none", "key_points": ["直销增长"], "risks": ["需求放缓"]}


class Base(unittest.TestCase):
    def setUp(self):
        self.dir = tempfile.mkdtemp()
        self.ak = mock.patch.dict(sys.modules, {"akshare": fake_akshare()})
        self.ak.start()
        self.req = mock.patch.object(cn.requests, "get", side_effect=fake_get)
        self.req.start()

    def tearDown(self):
        self.req.stop()
        self.ak.stop()
        shutil.rmtree(self.dir, ignore_errors=True)  # Windows keeps open SQLite files locked


# ---------------------------------------------------------------- tests
class TestCodes(unittest.TestCase):
    def test_parse(self):
        cases = {"600519": "600519.SH", "600519.SS": "600519.SH", "688981": "688981.SH",
                 "000001": "000001.SZ", "300750.sz": "300750.SZ", "920001": "920001.BJ",
                 "430047": "430047.BJ", "700": "00700.HK", "0700.HK": "00700.HK", "09988": "09988.HK"}
        for raw, sym in cases.items():
            self.assertEqual(cn.parse(raw)["symbol"], sym, raw)

    def test_not_chinese(self):
        for t in ("AAPL", "BRK-B", "T", "1234567"):
            self.assertIsNone(cn.parse(t), t)

    def test_cli_canonicalizes(self):
        args = cli.build_parser().parse_args(["scan", "600519", "0700.hk", "AAPL", "600519.SH"])
        tickers, _ = cli.parse_tickers(args)
        self.assertEqual(tickers, ["600519.SH", "00700.HK", "AAPL"])


class TestEPS(Base):
    def test_a_share_decumulation_and_deadlines(self):
        q = cn.eps_history(cn.parse("600519"), cn.CNCache(self.dir))
        by_end = {str(e.date()): (round(v, 6), str(f.date())) for e, v, f in zip(q["end"], q["eps"], q["filed"])}
        self.assertEqual(by_end["2026-03-31"], (21.6, "2026-04-30"))      # Q1 as reported
        self.assertEqual(by_end["2026-06-30"], (13.9, "2026-08-31"))      # H1 - Q1
        self.assertEqual(by_end["2025-12-31"], (14.0, "2026-04-30"))      # FY - 9M, deadline next April
        self.assertFalse(q[q["end"] == "2026-03-31"]["q4_derived"].iloc[0])
        self.assertTrue(q[q["end"] == "2025-12-31"]["q4_derived"].iloc[0])
        s = add_sue(q)
        self.assertTrue(s["sue"].notna().any())

    def test_cached_on_disk(self):
        info, cache = cn.parse("600519"), cn.CNCache(self.dir)
        cn.eps_history(info, cache)
        with mock.patch.dict(sys.modules, {"akshare": None}):          # no akshare: must use the cache
            q = cn.eps_history(info, cache)
        self.assertEqual(len(q), 14)

    def test_hk_mixed_quarterly_and_interim(self):
        q = cn.eps_history(cn.parse("00700"), cn.CNCache(self.dir))
        v = {str(e.date()): round(x, 3) for e, x in zip(q["end"], q["eps"])}
        self.assertAlmostEqual(v["2026-06-30"], 6.208)                    # 12.639 - 6.431
        self.assertAlmostEqual(v["2024-12-31"], 11.0)                     # FY 21.0 - H1 10.0
        filed = {str(e.date()): str(f.date()) for e, f in zip(q["end"], q["filed"])}
        self.assertEqual(filed["2025-12-31"], "2026-03-31")              # derived Q4 waits for the annual report
        self.assertEqual(filed["2026-06-30"], "2026-08-29")              # interim: +60 days


class TestNewsAndAnnouncements(Base):
    def test_news_without_name_uses_eastmoney_only(self):
        items, problems = cn.fetch_headlines(cn.parse("600519"), 20)
        self.assertEqual(len(items), 2)                      # repeated title dropped
        self.assertEqual(items[0]["published"], "2026-10-27")
        self.assertIn("同比增长8%", items[0]["summary"])

    def test_news_merges_google_and_drops_same_story(self):
        items, _ = cn.fetch_headlines(cn.parse("600519"), 20, name="贵州茅台")
        titles = [it["title"] for it in items]
        self.assertEqual(titles[0], "贵州茅台直销渠道收入创新高")    # newest first, publisher removed
        self.assertEqual(titles.count("贵州茅台三季度营收增长"), 1)     # same story from 2 sources
        self.assertEqual(len(items), 3)

    def test_hk_gets_yahoo_too(self):
        items, _ = cn.fetch_headlines(cn.parse("00700"), 20, name="腾讯控股")
        self.assertIn("yahoo", {it["source"] for it in items})

    def test_pick_report_prefers_summary_and_skips_meetings(self):
        ann = cn.pick_earnings_announcement(cn.announcements(cn.parse("600519")))
        self.assertEqual(ann["art_code"], "AN3")

    def test_name_from_announcements_cached(self):
        cache = cn.CNCache(self.dir)
        self.assertEqual(cn.resolve_name(cn.parse("600519"), cache), "贵州茅台")
        self.assertEqual(cache.names()["600519.SH"], "贵州茅台")

    def test_forecast_prefers_net_profit_row(self):
        with mock.patch.object(cn.dt, "date", wraps=dt.date) as d:
            d.today.return_value = dt.date(2026, 10, 28)
            fc = cn.latest_forecast(cn.parse("600519"), cn.CNCache(self.dir))
        self.assertEqual(fc["type"], "预增")
        self.assertEqual(fc["change_pct"], 12.5)
        self.assertIsNone(cn.latest_forecast(cn.parse("00700"), cn.CNCache(self.dir)))

    def test_missing_akshare_gives_clear_message(self):
        with mock.patch.dict(sys.modules, {"akshare": None}):
            items, problems = cn.fetch_headlines(cn.parse("600519"), 5)
        self.assertEqual(items, [])
        self.assertIn("pip install akshare", problems[0])


class TestPipelines(Base):
    def test_scan_chinese_stock(self):
        store, llm = Store(self.dir), FakeLLM()
        res = core.scan_ticker(store, llm, "m", "600519.SH", "600519.SH", 20, "zh")
        self.assertIsNone(res["error"])
        self.assertEqual(res["scored"], 3)                                 # eastmoney 2 + google 1 new story
        self.assertIn("贵州茅台", llm.prompts[0])                         # name resolved
        self.assertIn("同比增长8%", llm.prompts[0])                       # summary sent to the model
        df = store.scored(["600519.SH"], "m", "zh")
        self.assertEqual(sorted(df["relevance"]), [0.9, 0.9, 0.9])

    def test_earnings_chinese_stock_and_cache(self):
        store, llm = Store(self.dir), FakeLLM()
        with mock.patch.object(cn.dt, "date", wraps=dt.date) as d:
            d.today.return_value = dt.date(2026, 10, 28)
            row = core.earnings_any(store, self.dir, llm, "m", "600519.SH", "zh")
            self.assertEqual(row["errors"], [])
            self.assertEqual(row["read"]["tone"], 0.3)
            self.assertEqual(row["read"]["doc_title"], "贵州茅台:2026年半年度报告摘要")
            self.assertEqual(row["forecast"]["type"], "预增")
            self.assertIn("2026 年半年度报告摘要", llm.prompts[-1])
            calls = len(llm.prompts)
            core.earnings_any(store, self.dir, llm, "m", "600519.SH", "zh")
        self.assertEqual(len(llm.prompts), calls)                          # reading reused

    def test_cli_earnings_china_needs_no_sec_contact(self):
        report = os.path.join(self.dir, "e.html")
        with mock.patch.dict(os.environ, {"STOCKPROOF_SEC_CONTACT": ""}), \
             mock.patch.object(cli.LLMClient, "from_provider", return_value=FakeLLM()):
            with self.assertRaises(SystemExit) as code:
                cli.main(["earnings", "600519", "00700", "--data-dir", self.dir, "--report", report, "--lang", "zh"])
        self.assertEqual(code.exception.code, 0)
        page = open(report, encoding="utf-8").read()
        self.assertIn("贵州茅台", page)
        self.assertIn("pdf.dfcfw.com", page)


if __name__ == "__main__":
    unittest.main()
