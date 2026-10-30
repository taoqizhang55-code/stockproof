"""Offline tests for the earnings module, with fake SEC data shaped like the real API."""

import os
import shutil
import tempfile
import unittest
from unittest import mock

import pandas as pd

from stockproof import cli, earnings, eps, sec
from stockproof.earnings_report import build_earnings_report


def q(start, end, val, filed, fy, fp, form="10-Q"):
    return {"start": start, "end": end, "val": val, "filed": filed, "fy": fy, "fp": fp, "form": form}


def fake_facts():
    rows = []
    # quarterly EPS for calendar years 2022-2025 (Q1-Q3 in 10-Qs), full years in 10-Ks
    base = {2022: [1.00, 1.10, 1.20, 1.30], 2023: [1.05, 1.20, 1.15, 1.40],
            2024: [1.20, 1.25, 1.40, 1.50], 2025: [1.50, 1.45, 1.80]}
    ends = ["03-31", "06-30", "09-30"]
    starts = ["01-01", "04-01", "07-01"]
    for y, vals in base.items():
        for i in range(min(3, len(vals))):
            rows.append(q(f"{y}-{starts[i]}", f"{y}-{ends[i]}", vals[i], f"{y}-{ends[i][:2]}-28".replace("-03-28", "-04-28").replace("-06-28", "-07-28").replace("-09-28", "-10-28"), y, f"Q{i+1}"))
        if len(vals) == 4:
            rows.append(q(f"{y}-01-01", f"{y}-12-31", round(sum(vals), 2), f"{y + 1}-02-15", y, "FY", "10-K"))
    # a LATER filing restates 2023 Q1 (comparative column) -- must be ignored
    rows.append(q("2023-01-01", "2023-03-31", 9.99, "2024-04-28", 2024, "Q1"))
    return {"facts": {"us-gaap": {"EarningsPerShareDiluted": {"units": {"USD/shares": rows}}}}}


SUBMISSIONS = {"filings": {"recent": {
    "form": ["10-Q", "8-K", "8-K", "4", "8-K"],
    "items": ["", "5.02", "2.02,9.01", "", "2.02,9.01"],
    "accessionNumber": ["0001-25-1", "0001-25-2", "0001-25-3", "0001-25-4", "0001-25-5"],
    "filingDate": ["2025-10-30", "2025-10-29", "2025-10-28", "2025-10-01", "2025-07-28"],
    "reportDate": ["2025-09-30", "2025-10-29", "2025-10-28", "", "2025-07-28"],
    "primaryDocument": ["q.htm", "a.htm", "k8.htm", "f4.xml", "k8b.htm"],
}}}

INDEX = {"directory": {"item": [
    {"name": "k8.htm", "size": "5000"}, {"name": "R1.htm", "size": "900"},
    {"name": "acme-ex991_q3.htm", "size": "40000"}, {"name": "0001-25-3-index.htm", "size": "100"},
    {"name": "logo.jpg", "size": "3000"}]}}

RELEASE_HTML = """<html><head><style>.x{color:red}</style><script>var a=1;</script></head><body>
<p>ACME Reports Third Quarter 2025 Results</p><p>Revenue up 12% to $4.1 billion; raises full-year outlook.</p>
<table><tr><td>Revenue</td><td>4,100</td></tr><tr><td>EPS</td><td>1.80</td></tr></table></body></html>"""


class FakeLLM:
    model = "fake"

    def __init__(self):
        self.calls = 0

    def chat_json(self, prompt):
        self.calls += 1
        assert "raises full-year outlook" in prompt
        return {"period": "Q3 2025", "tone": 0.7, "summary": "Strong quarter.", "revenue_growth": "+12%",
                "eps": "1.80", "guidance": "RAISED", "key_points": ["a", "b", "c", "d"], "risks": ["r"]}


class TestEPS(unittest.TestCase):
    def setUp(self):
        self.qe = eps.quarterly_eps(fake_facts())

    def test_point_in_time_ignores_restatement(self):
        q1_2023 = self.qe[self.qe["end"] == "2023-03-31"].iloc[0]
        self.assertAlmostEqual(q1_2023["eps"], 1.05)

    def test_q4_derived_from_full_year(self):
        q4 = self.qe[self.qe["end"] == "2024-12-31"].iloc[0]
        self.assertTrue(q4["q4_derived"])
        self.assertAlmostEqual(q4["eps"], 1.50, places=6)
        self.assertEqual(str(q4["filed"].date()), "2025-02-15")

    def test_quarter_count(self):
        self.assertEqual(len(self.qe), 15)              # 2022-2024: 12, 2025: 3

    def test_sue(self):
        s = eps.add_sue(self.qe)
        last = s.iloc[-1]                                # 2025 Q3: 1.80 vs 1.40
        self.assertAlmostEqual(last["change"], 0.40, places=6)
        self.assertTrue(pd.notna(last["sue"]) and last["sue"] > 0)
        self.assertTrue(pd.isna(s.iloc[0]["sue"]))       # no history yet

    def test_empty_facts(self):
        self.assertEqual(len(eps.quarterly_eps({"facts": {}})), 0)


class TestReleases(unittest.TestCase):
    def test_finds_only_item_202_newest_first(self):
        f = earnings.earnings_filings(SUBMISSIONS)
        self.assertEqual([x["accession"] for x in f], ["0001-25-3", "0001-25-5"])

    def test_picks_exhibit_99(self):
        self.assertEqual(earnings.pick_press_release(INDEX["directory"]["item"], "k8.htm"),
                         "acme-ex991_q3.htm")

    def test_html_to_text(self):
        text = earnings.html_to_text(RELEASE_HTML)
        self.assertIn("raises full-year outlook", text)
        self.assertNotIn("color:red", text)
        self.assertNotIn("var a", text)
        self.assertIn("Revenue | 4,100", text)

    def test_read_release_cleans_output(self):
        r = earnings.read_release(FakeLLM(), "ACME", "ACME", "Revenue up; raises full-year outlook", "en")
        self.assertEqual(r["guidance"], "raised")
        self.assertEqual(len(r["key_points"]), 3)

    def test_contact_required(self):
        with mock.patch.dict(os.environ, {sec.CONTACT_ENV: ""}):
            with self.assertRaises(sec.SECError):
                sec.contact()


class TestEarningsCLI(unittest.TestCase):
    def test_end_to_end_and_cache(self):
        tmp = tempfile.mkdtemp()
        llm = FakeLLM()

        def fake_fetch(self, name, url, max_age_hours):
            if name == "company_tickers.json":
                return {"0": {"cik_str": 1234, "ticker": "ACME", "title": "Acme Corp"}}
            if name.startswith("submissions"):
                return SUBMISSIONS
            return fake_facts()

        def fake_get(url, as_json=True):
            return INDEX if url.endswith("index.json") else RELEASE_HTML

        try:
            report, csv = os.path.join(tmp, "e.html"), os.path.join(tmp, "e.csv")
            argv = ["earnings", "ACME", "--data-dir", tmp, "--report", report, "--csv", csv]
            with mock.patch.dict(os.environ, {sec.CONTACT_ENV: "Test User test@example.com"}), \
                 mock.patch.object(sec.SECCache, "fetch", fake_fetch), \
                 mock.patch.object(earnings, "get", fake_get), \
                 mock.patch.object(cli.LLMClient, "from_provider", return_value=llm):
                for _ in range(2):
                    with self.assertRaises(SystemExit) as code:
                        cli.main(argv)
                    self.assertEqual(code.exception.code, 0)
            self.assertEqual(llm.calls, 1)               # second run used the saved reading
            page = open(report, encoding="utf-8").read()
            self.assertIn("Strong quarter.", page)
            self.assertIn("acme-ex991_q3.htm", page)
            hist = pd.read_csv(csv, encoding="utf-8-sig")
            self.assertEqual(len(hist), 15)
        finally:
            shutil.rmtree(tmp, ignore_errors=True)  # Windows keeps open SQLite files locked

    def test_report_both_languages(self):
        qe = eps.add_sue(eps.quarterly_eps(fake_facts()))
        read = {"period": "Q3", "tone": -0.4, "summary": "<b>x</b>", "revenue_growth": "-3%", "eps": "1",
                "guidance": "lowered", "key_points": ["k"], "risks": ["r"], "url": "https://sec.gov/x",
                "filed": "2025-10-28"}
        for lang in ("en", "zh"):
            page = build_earnings_report([{"ticker": "ACME", "name": "Acme", "read": read, "history": qe},
                                          {"ticker": "NONE", "name": "None", "read": None, "history": None}],
                                         lang=lang, model="m")
            self.assertIn("&lt;b&gt;x", page)
            self.assertIn("lowered", page)


if __name__ == "__main__":
    unittest.main()


class TestSixK(unittest.TestCase):
    """Foreign issuers (Alibaba, PDD...) file 6-K: earnings releases must be found by content."""

    SUBS = {"filings": {"recent": {
        "form": ["6-K", "6-K", "20-F", "6-K"],
        "items": ["", "", "", ""],
        "accessionNumber": ["0002-26-9", "0002-26-8", "0002-26-7", "0002-26-6"],
        "filingDate": ["2026-10-30", "2026-10-20", "2026-07-10", "2026-08-28"],
        "reportDate": ["", "", "", ""],
        "primaryDocument": ["a.htm", "b.htm", "c.htm", "d.htm"],
    }}}
    NOTICE = ("<p>Alibaba Group to Announce September Quarter 2026 Results</p><p>Alibaba will release its "
              "results for the quarter ended September 30, 2026 on November 13. A conference call to be held...</p>")
    BUYBACK = "<p>Monthly return of equity issuer on movements in securities for the month ended September 30.</p>"
    RESULTS = ("<p>Alibaba Group Announces June Quarter 2026 Results</p><p>Revenue was RMB 247,652 million "
               "(US$34,120 million), an increase of 2% year-over-year. Net income attributable to ordinary "
               "shareholders was RMB 43,116 million.</p>")

    def fake_get(self, url, as_json=True):
        acc = url.split("/")[-2]                  # .../data/<cik>/<accession without dashes>/<file>
        if url.endswith("index.json"):
            return {"directory": {"item": [{"name": "ex99-1.htm", "size": "9000"}]}}
        return {"0002269": self.NOTICE, "0002268": self.BUYBACK, "0002266": self.RESULTS}.get(acc, "")

    def test_classifier(self):
        self.assertFalse(earnings.looks_like_results(earnings.html_to_text(self.NOTICE)))
        self.assertFalse(earnings.looks_like_results(earnings.html_to_text(self.BUYBACK)))
        self.assertTrue(earnings.looks_like_results(earnings.html_to_text(self.RESULTS)))

    def test_finds_newest_results_and_remembers_checks(self):
        calls = []

        def get(url, as_json=True):
            calls.append(url)
            return self.fake_get(url, as_json)
        checked = {}
        with mock.patch.object(earnings, "get", get):
            f, text, url = earnings.find_6k_release(1577552, self.SUBS, checked)
        self.assertEqual(f["accession"], "0002-26-6")
        self.assertIn("Revenue was RMB", text)
        self.assertEqual(checked, {"0002-26-9": False, "0002-26-8": False, "0002-26-6": True})
        n = len(calls)
        with mock.patch.object(earnings, "get", get):
            earnings.find_6k_release(1577552, self.SUBS, checked)
        self.assertEqual(len(calls) - n, 2)       # the two non-results filings are not fetched again

    def test_core_reads_6k_when_no_8k(self):
        from stockproof import core
        from stockproof.store import Store

        class Cache:
            def __init__(self):
                self.files = {}

            def company_facts(self, cik):
                return {"facts": {}}

            def submissions(self, cik):
                return TestSixK.SUBS

            def cached(self, name):
                return self.files.get(name)

            def save(self, name, data):
                self.files[name] = data

        class LLM:
            model = "x"

            def chat_json(self, prompt):
                assert "Revenue was RMB" in prompt
                return {"period": "June quarter 2026", "tone": 0.2, "summary": "s", "guidance": "none",
                        "key_points": [], "risks": []}
        tmp = tempfile.mkdtemp()
        try:
            with mock.patch.object(earnings, "get", self.fake_get):
                row = core.earnings_ticker(Store(tmp), Cache(), LLM(), "m", "BABA", 1577552, "Alibaba", "en")
            self.assertEqual(row["errors"], [])
            self.assertEqual(row["read"]["filed"], "2026-08-28")
            self.assertEqual(row["read"]["tone"], 0.2)
        finally:
            shutil.rmtree(tmp, ignore_errors=True)  # Windows keeps open SQLite files locked
