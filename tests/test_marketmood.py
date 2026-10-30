"""Offline tests: fake news feeds and a fake LLM, so no network or API key is needed.
Run:  python3 -m unittest discover tests     (or: pytest)"""

import json
import os
import shutil
import tempfile
import unittest
from unittest import mock

import pandas as pd

from marketmood import cli, core, news, scoring, summary
from marketmood.llm import LLMError, parse_json
from marketmood.report import build_report
from marketmood.store import Store

RSS = """<?xml version="1.0"?><rss><channel><title>feed</title>
<item><title>Merck beats estimates on Keytruda sales - Reuters</title><link>https://x/1</link>
<pubDate>Tue, 28 Oct 2026 13:05:00 GMT</pubDate></item>
<item><title>Merck beats estimates on Keytruda sales!</title><link>https://x/1b</link>
<pubDate>Tue, 28 Oct 2026 13:06:00 GMT</pubDate></item>
<item><title>Merck KGaA expands display materials unit</title><link>https://x/2</link>
<pubDate>Mon, 27 Oct 2026 09:00:00 +0000</pubDate></item>
<item><title>No date story</title><link>https://x/3</link><pubDate>garbage</pubDate></item>
</channel></rss>"""


class FakeClient:
    """Pretends to be the LLM: scores headlines by keywords."""
    model = "fake-model"

    def __init__(self):
        self.calls = 0

    def chat_json(self, prompt):
        self.calls += 1
        lines = prompt.split("Headlines:\n", 1)[1].split("\n\n", 1)[0].splitlines()
        items = []
        for line in lines:
            i, title = line.split(". ", 1)
            rel = 0.1 if "KGaA" in title else 0.9
            score = 0.6 if "beats" in title.lower() else (-0.5 if "falls" in title.lower() else 0.0)
            items.append({"i": int(i), "relevance": rel, "score": score, "reason": "test"})
        return {"items": items}


class TestParsing(unittest.TestCase):
    def test_parse_rss_dates_and_limit(self):
        items = news.parse_rss(RSS, "yahoo", limit=3)
        self.assertEqual(len(items), 3)
        self.assertEqual(items[0]["published"], "2026-10-28")
        self.assertEqual(items[2]["published"], "2026-10-27")

    def test_bad_date_becomes_empty(self):
        items = news.parse_rss(RSS, "yahoo", limit=10)
        self.assertEqual(items[3]["published"], "")

    def test_fetch_dedupes_and_falls_back(self):
        def broken(*a):
            raise ConnectionError("down")

        def ok(ticker, name, limit):
            return news.parse_rss(RSS, "google", limit)

        with mock.patch.object(news, "SOURCES", [("yahoo", broken), ("google", ok)]):
            items, problems = news.fetch_headlines("MRK", "Merck & Co.", 10)
        self.assertEqual(len(items), 3)                  # two Keytruda versions merged
        self.assertIn("yahoo: ConnectionError", problems[0])

    def test_parse_json_with_fences(self):
        self.assertEqual(parse_json('```json\n{"a": 1}\n```'), {"a": 1})
        with self.assertRaises(LLMError):
            parse_json("sorry, no json")


class TestScoring(unittest.TestCase):
    def test_batches_and_order(self):
        client = FakeClient()
        titles = [f"Story {i} beats" for i in range(23)]
        out = scoring.score_headlines(client, "AAPL", "Apple", titles)
        self.assertEqual(client.calls, 3)               # 10 + 10 + 3
        self.assertTrue(all(r["score"] == 0.6 for r in out))

    def test_missing_and_bad_items(self):
        class Partial:
            def chat_json(self, prompt):
                return {"items": [{"i": 1, "relevance": 5, "score": -9, "reason": "x"},
                                  {"i": "bad"}, "junk"]}
        out = scoring.score_headlines(Partial(), "A", "A", ["a", "b"])
        self.assertIsNone(out[0])
        self.assertEqual(out[1]["relevance"], 1.0)      # clipped
        self.assertEqual(out[1]["score"], -1.0)


class TestDuplicates(unittest.TestCase):
    def test_llm_duplicate_of_is_validated(self):
        class Dup:
            def chat_json(self, prompt):
                return {"items": [{"i": 0, "relevance": 1, "score": 0.5, "reason": "", "duplicate_of": None},
                                  {"i": 1, "relevance": 1, "score": 0.5, "reason": "", "duplicate_of": 0},
                                  {"i": 2, "relevance": 1, "score": 0.5, "reason": "", "duplicate_of": 2},
                                  {"i": 3, "relevance": 1, "score": 0.5, "reason": "", "duplicate_of": "null"}]}
        out = scoring.score_headlines(Dup(), "A", "A", ["a", "b", "c", "d"])
        self.assertEqual([r["duplicate_of"] for r in out], [None, 0, None, None])

    def test_duplicates_not_counted_and_stored(self):
        tmp = tempfile.mkdtemp()
        try:
            store = Store(tmp)
            items = [{"title": t, "link": "", "source": "x", "published": "2026-10-28"}
                     for t in ("Acme beats estimates", "Acme tops forecasts", "Acme falls")]

            class Fake:
                model = "f"

                def chat_json(self, prompt):
                    return {"items": [{"i": 0, "relevance": 1, "score": 0.8, "reason": ""},
                                      {"i": 1, "relevance": 1, "score": 0.8, "reason": "", "duplicate_of": 0},
                                      {"i": 2, "relevance": 1, "score": -0.4, "reason": ""}]}
            with mock.patch.object(core, "fetch_headlines", return_value=(items, [])):
                core.scan_ticker(store, Fake(), "m", "ACME", "Acme", 20, "en")
            df = store.scored(["ACME"], "m", "en")
            self.assertEqual(df["duplicate_of"].notna().sum(), 1)
            s = summary.summarize(df, ["ACME"], 0.5)
            self.assertAlmostEqual(s.iloc[0]["mood"], 0.2)    # (0.8 - 0.4) / 2, repeat not counted
            self.assertEqual(s.iloc[0]["relevant"], 2)
        finally:
            shutil.rmtree(tmp)

    def test_old_database_gets_new_column(self):
        import sqlite3
        tmp = tempfile.mkdtemp()
        try:
            conn = sqlite3.connect(os.path.join(tmp, "marketmood.db"))
            conn.execute("CREATE TABLE scores (headline_id TEXT NOT NULL, model TEXT NOT NULL, lang TEXT NOT NULL, "
                         "relevance REAL, score REAL, reason TEXT, scored_at TEXT NOT NULL, "
                         "PRIMARY KEY (headline_id, model, lang))")
            conn.commit(); conn.close()
            store = Store(tmp)
            cols = {r[1] for r in store.conn.execute("PRAGMA table_info(scores)")}
            self.assertIn("duplicate_of", cols)
        finally:
            shutil.rmtree(tmp)


class TestStoreSummaryReport(unittest.TestCase):
    def setUp(self):
        self.dir = tempfile.mkdtemp()

    def tearDown(self):
        shutil.rmtree(self.dir)

    def test_store_never_rescores(self):
        store = Store(self.dir)
        items = news.parse_rss(RSS, "yahoo", 10)
        ids = store.add_headlines("MRK", items)
        todo = store.unscored(ids, "m", "en")
        self.assertEqual(len(todo), 3)                   # duplicate story stored once
        for hid, _ in todo:
            store.save_score(hid, "m", "en", {"relevance": 1, "score": 0.1, "reason": ""})
        self.assertEqual(store.unscored(ids, "m", "en"), [])
        self.assertEqual(len(store.unscored(ids, "m", "zh")), 3)   # other language: separate

    def test_summary_ignores_low_relevance(self):
        df = pd.DataFrame({"ticker": ["MRK"] * 3, "relevance": [1.0, 0.6, 0.1],
                           "score": [0.6, 0.0, -1.0], "title": ["a", "b", "c"]})
        s = summary.summarize(df, ["MRK", "XYZ"], min_relevance=0.5)
        mrk = s[s.ticker == "MRK"].iloc[0]
        self.assertAlmostEqual(mrk["mood"], 0.6 * 1.0 / 1.6)
        self.assertEqual(mrk["relevant"], 2)
        self.assertEqual(s[s.ticker == "XYZ"].iloc[0]["label"], "none")
        self.assertTrue(mrk["few"])                      # 2 relevant < 5
        self.assertFalse(s[s.ticker == "XYZ"].iloc[0]["few"])   # no news is not "few"

    def test_report_escapes_html(self):
        df = pd.DataFrame({"ticker": ["A"], "relevance": [1.0], "score": [0.2],
                           "title": ["<script>x</script>"], "link": ["https://a"],
                           "reason": ["r"], "date": ["2026-10-28"], "source": ["yahoo"]})
        s = summary.summarize(df, ["A"], 0.5)
        for lang in ("en", "zh"):
            page = build_report(s, df, {"A": "Co"}, lang=lang, model="m", days=7, min_relevance=0.5)
            self.assertNotIn("<script>x", page)
            self.assertIn("&lt;script&gt;", page)
            self.assertIn('class="few"', page)


class TestCLI(unittest.TestCase):
    def test_end_to_end_with_fakes(self):
        tmp = tempfile.mkdtemp()
        try:
            fake = FakeClient()
            items = news.parse_rss(RSS, "yahoo", 10)
            with mock.patch.object(core, "fetch_headlines", return_value=(items, [])), \
                 mock.patch.object(cli.LLMClient, "from_provider", return_value=fake), \
                 mock.patch("marketmood.store.dt") as fake_dt:
                import datetime as real_dt
                fake_dt.datetime.now.return_value = real_dt.datetime(2026, 10, 28, 14, 0)
                report = os.path.join(tmp, "r.html")
                csv = os.path.join(tmp, "d.csv")
                argv = ["scan", "MRK", "T=AT&T", "--data-dir", tmp, "--report", report,
                        "--csv", csv, "--days", "36500"]
                with self.assertRaises(SystemExit) as code:
                    cli.main(argv)
                self.assertEqual(code.exception.code, 0)
                calls_first = fake.calls
                with self.assertRaises(SystemExit):
                    cli.main(argv)                       # second run: everything cached
                self.assertEqual(fake.calls, calls_first)
            self.assertTrue(os.path.exists(report))
            data = pd.read_csv(csv, encoding="utf-8-sig")
            self.assertEqual(set(data.ticker), {"MRK", "T"})
        finally:
            shutil.rmtree(tmp)

    def test_watchlist_parsing(self):
        tmp = tempfile.mkdtemp()
        try:
            path = os.path.join(tmp, "w.txt")
            with open(path, "w") as f:
                f.write("ticker,name\naapl\nT,AT&T  # phone company\nC=Citigroup\n\n")
            args = cli.build_parser().parse_args(["scan", "MSFT", "--watchlist", path])
            tickers, names = cli.parse_tickers(args)
            self.assertEqual(tickers, ["MSFT", "AAPL", "T", "C"])
            self.assertEqual(names, {"T": "AT&T", "C": "Citigroup"})
        finally:
            shutil.rmtree(tmp)


if __name__ == "__main__":
    unittest.main()
