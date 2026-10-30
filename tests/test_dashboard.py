"""Dashboard tests: a real local server on a free port, seeded with fake data. No internet needed."""

import datetime as dt
import json
import os
import shutil
import socket
import tempfile
import threading
import time
import unittest
import urllib.error
import urllib.request
from http.server import ThreadingHTTPServer
from unittest import mock

from stockproof import core
from stockproof.dashboard import Dashboard, make_handler
from stockproof.store import Store

from test_earnings import fake_facts


def seed(data_dir):
    """Headlines over the last 10 days for two stocks, one earnings reading, SEC cache files."""
    store = Store(data_dir)
    today = dt.date.today()
    for tk, base in (("MRK", 0.4), ("INTC", -0.3)):
        for d in range(10):
            day = (today - dt.timedelta(days=d)).isoformat()
            items = [{"title": f"{tk} story {d}-{i}", "link": "https://example.com", "source": "yahoo",
                      "published": day} for i in range(3)]
            ids = store.add_headlines(tk, items)
            for j, hid in enumerate(ids):
                rel = 0.2 if j == 2 else 0.9
                store.save_score(hid, "deepseek:deepseek-chat", "en",
                                 {"relevance": rel, "score": base + 0.05 * (d % 3), "reason": f"reason {j}"})
    store.save_earnings_read("0001-26-1", "deepseek:deepseek-chat#v3", "en", "MRK", "2026-08-04",
                             "https://www.sec.gov/Archives/edgar/data/1/x.htm",
                             {"period": "Q2 2026", "tone": -0.2, "summary": "Sales up 5%, one-time charge.",
                              "revenue_growth": "+5%", "eps": "-0.54", "guidance": "raised",
                              "key_points": ["Oncology growth"], "risks": ["Acquisition charge"]})
    sec_dir = os.path.join(data_dir, "sec")
    os.makedirs(sec_dir, exist_ok=True)
    with open(os.path.join(sec_dir, "company_tickers.json"), "w") as f:
        json.dump({"0": {"cik_str": 310158, "ticker": "MRK", "title": "Merck & Co., Inc."},
                   "1": {"cik_str": 50863, "ticker": "INTC", "title": "INTEL CORP"}}, f)
    with open(os.path.join(sec_dir, "facts_310158.json"), "w") as f:
        json.dump(fake_facts(), f)


def free_port():
    with socket.socket() as s:
        s.bind(("127.0.0.1", 0))
        return s.getsockname()[1]


class DashboardServer(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.dir = tempfile.mkdtemp()
        seed(cls.dir)
        cls.app = Dashboard(cls.dir, "deepseek", None, None)
        cls.app.set_watchlist(["MRK", "INTC", "T=AT&T"])
        cls.port = free_port()
        cls.server = ThreadingHTTPServer(("127.0.0.1", cls.port), make_handler(cls.app, cls.port))
        threading.Thread(target=cls.server.serve_forever, daemon=True).start()

    @classmethod
    def tearDownClass(cls):
        cls.server.shutdown()
        cls.server.server_close()
        shutil.rmtree(cls.dir)

    def get(self, path):
        with urllib.request.urlopen(f"http://127.0.0.1:{self.port}{path}") as r:
            return json.loads(r.read())

    def post(self, path, body, origin=None, ctype="application/json"):
        req = urllib.request.Request(f"http://127.0.0.1:{self.port}{path}", data=json.dumps(body).encode(),
                                     headers={"Content-Type": ctype, **({"Origin": origin} if origin else {})})
        try:
            with urllib.request.urlopen(req) as r:
                return r.status, json.loads(r.read())
        except urllib.error.HTTPError as e:
            return e.code, json.loads(e.read())

    def test_page_and_state(self):
        with urllib.request.urlopen(f"http://127.0.0.1:{self.port}/") as r:
            self.assertIn("stockproof", r.read().decode())
        s = self.get("/api/state")
        self.assertEqual(s["watchlist"], ["MRK", "INTC", "T"])
        self.assertEqual(s["names"]["T"], "AT&T")

    def test_overview_combines_news_and_earnings(self):
        rows = {r["ticker"]: r for r in self.get("/api/overview?lang=en")}
        self.assertGreater(rows["MRK"]["mood"], 0)
        self.assertLess(rows["INTC"]["mood"], 0)
        self.assertEqual(rows["MRK"]["e_guidance"], "raised")
        self.assertIsNotNone(rows["MRK"]["sue"])        # from the cached SEC file
        self.assertIsNone(rows["T"]["mood"])            # no news yet

    def test_stock_detail_and_language_fallback(self):
        d = self.get("/api/stock?ticker=MRK&lang=zh")   # no zh scores: falls back to en
        self.assertTrue(d["headlines"])
        self.assertTrue(all(h["lang"] == "en" for h in d["headlines"]))
        self.assertEqual(len(d["history"]), 10)
        self.assertEqual(len(d["eps"]), 8)
        self.assertEqual(d["earnings"]["guidance"], "raised")

    def test_stock_not_in_watchlist(self):
        with self.assertRaises(urllib.error.HTTPError) as e:
            self.get("/api/stock?ticker=ZZZZ")
        self.assertEqual(e.exception.code, 404)

    def test_rejects_other_websites_and_non_json(self):
        code, _ = self.post("/api/watchlist", {"tickers": []}, origin="https://evil.example")
        self.assertEqual(code, 403)
        code, _ = self.post("/api/watchlist", {"tickers": []}, ctype="text/plain")
        self.assertEqual(code, 415)
        self.assertEqual(self.get("/api/state")["watchlist"], ["MRK", "INTC", "T"])   # unchanged

    def test_bad_tickers_are_dropped(self):
        app = Dashboard(tempfile.mkdtemp(), "deepseek", None, None)
        app.set_watchlist(["aapl", "<script>", "AAPL", "BRK-B", "x" * 40])
        self.assertEqual(app.settings["watchlist"], ["AAPL", "BRK-B"])


class RefreshJob(unittest.TestCase):
    def test_background_news_refresh(self):
        tmp = tempfile.mkdtemp()
        try:
            app = Dashboard(tmp, "deepseek", None, None)
            app.set_watchlist(["AAPL", "MSFT"])

            class FakeLLM:
                model = "fake"

                def chat_json(self, prompt):
                    n = prompt.count("\n") and len(prompt.split("Headlines:\n")[1].split("\n\n")[0].splitlines())
                    return {"items": [{"i": i, "relevance": 0.9, "score": 0.3, "reason": "ok"} for i in range(n)]}

            items = [{"title": f"story {i}", "link": "", "source": "yahoo",
                      "published": dt.date.today().isoformat()} for i in range(4)]
            with mock.patch.object(core, "fetch_headlines", return_value=(items, [])), \
                 mock.patch("stockproof.dashboard.LLMClient.from_provider", return_value=FakeLLM()):
                ok, _ = app.start_refresh("news")
                self.assertTrue(ok)
                self.assertFalse(app.start_refresh("news")[0])      # one job at a time
                for _ in range(100):
                    if not app.state()["job"]["running"]:
                        break
                    time.sleep(0.05)
            job = app.state()["job"]
            self.assertIsNone(job["error"])
            self.assertEqual(job["done"], 2)
            rows = {r["ticker"]: r for r in app.overview("en")}
            self.assertAlmostEqual(rows["AAPL"]["mood"], 0.3)
        finally:
            shutil.rmtree(tmp)


if __name__ == "__main__":
    unittest.main()
