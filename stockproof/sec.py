"""
SEC EDGAR: free, official US company filings.

SEC rules: every request must say who is asking, in the User-Agent header
("Your Name your@email.com"), and stay under 10 requests per second.
Set it once:   export STOCKPROOF_SEC_CONTACT="Your Name your@email.com"

What we use:
  - company_tickers.json          ticker -> CIK (SEC's company number)
  - submissions/CIK##########.json  list of recent filings (to find earnings releases)
  - xbrl/companyfacts/...json     every number a company has reported, with the date it was filed
"""

from __future__ import annotations

import json
import os
import threading
import time

import requests

CONTACT_ENV = "STOCKPROOF_SEC_CONTACT"
_last_request = [0.0]
_rate_lock = threading.Lock()


class SECError(RuntimeError):
    pass


def contact() -> str:
    value = (os.environ.get(CONTACT_ENV) or "").strip()
    if not value or "@" not in value:
        raise SECError(
            f"SEC asks every user to identify themselves. Set it once, e.g.\n"
            f'  export {CONTACT_ENV}="Your Name your@email.com"\n'
            f"(add the line to ~/.zshrc to keep it)")
    return value


def get(url: str, as_json: bool = True):
    """GET from sec.gov politely: identified, and at most ~8 requests per second."""
    with _rate_lock:                      # several threads may share the limit
        wait = 0.125 - (time.time() - _last_request[0])
        if wait > 0:
            time.sleep(wait)
        _last_request[0] = time.time()
    resp = requests.get(url, headers={"User-Agent": f"stockproof {contact()}",
                                      "Accept-Encoding": "gzip, deflate"}, timeout=30)
    if resp.status_code == 403:
        raise SECError("SEC refused the request (403). Check STOCKPROOF_SEC_CONTACT has a real name and email.")
    if resp.status_code == 404:
        raise SECError(f"Not found on SEC: {url}")
    resp.raise_for_status()
    return resp.json() if as_json else resp.text


class SECCache:
    """Saves SEC JSON files on disk so we don't download them every run."""

    def __init__(self, data_dir: str):
        self.dir = os.path.join(data_dir, "sec")
        os.makedirs(self.dir, exist_ok=True)

    def fetch(self, name: str, url: str, max_age_hours: float):
        path = os.path.join(self.dir, name)
        if os.path.exists(path) and (time.time() - os.path.getmtime(path)) < max_age_hours * 3600:
            with open(path, encoding="utf-8") as f:
                return json.load(f)
        data = get(url)
        with open(path, "w", encoding="utf-8") as f:
            json.dump(data, f)
        return data

    def save(self, name: str, data) -> None:
        with open(os.path.join(self.dir, name), "w", encoding="utf-8") as f:
            json.dump(data, f)

    def cached(self, name: str):
        """A saved file, however old, or None. Never touches the network."""
        path = os.path.join(self.dir, name)
        if not os.path.exists(path):
            return None
        with open(path, encoding="utf-8") as f:
            return json.load(f)

    def ticker_map(self) -> dict:
        """{'AAPL': {'cik': 320193, 'name': 'Apple Inc.'}, ...}"""
        raw = self.fetch("company_tickers.json", "https://www.sec.gov/files/company_tickers.json", 24 * 7)
        out = {}
        for row in raw.values():
            out[str(row["ticker"]).upper().replace(".", "-")] = {"cik": int(row["cik_str"]),
                                                                 "name": row["title"]}
        return out

    def submissions(self, cik: int) -> dict:
        return self.fetch(f"submissions_{cik}.json",
                          f"https://data.sec.gov/submissions/CIK{cik:010d}.json", 12)

    def company_facts(self, cik: int) -> dict:
        return self.fetch(f"facts_{cik}.json",
                          f"https://data.sec.gov/api/xbrl/companyfacts/CIK{cik:010d}.json", 24)
