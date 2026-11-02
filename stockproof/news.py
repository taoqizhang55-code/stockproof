"""
Free news sources (no API key needed), tried in order:
  1. Yahoo Finance RSS, by ticker
  2. Google News RSS, by company name (backup)

Each headline is returned as a dict:
  {"title", "link", "published" (YYYY-MM-DD or ""), "source"}
"""

from __future__ import annotations

import re
import xml.etree.ElementTree as ET
from email.utils import parsedate_to_datetime

import requests

HEADERS = {"User-Agent": "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) stockproof"}


def parse_rss(xml_text: str, source: str, limit: int) -> list[dict]:
    root = ET.fromstring(xml_text)
    out = []
    for item in root.iter("item"):
        title = (item.findtext("title") or "").strip()
        if not title:
            continue
        raw_date = item.findtext("pubDate") or ""
        try:
            published = parsedate_to_datetime(raw_date).strftime("%Y-%m-%d")
        except Exception:
            published = ""
        src = item.find("source")             # Google News names the publisher here
        publisher = (src.text or "").strip() if src is not None else ""
        it = {"title": title, "link": (item.findtext("link") or "").strip(),
              "published": published, "source": publisher or source}
        if src is not None and src.get("url"):
            it["site"] = src.get("url")
        out.append(it)
        if len(out) >= limit:
            break
    return out


def yahoo_rss(ticker: str, name: str, limit: int) -> list[dict]:
    url = f"https://feeds.finance.yahoo.com/rss/2.0/headline?s={ticker}&region=US&lang=en-US"
    resp = requests.get(url, headers=HEADERS, timeout=20)
    resp.raise_for_status()
    return parse_rss(resp.text, "yahoo", limit)


def google_news(ticker: str, name: str, limit: int) -> list[dict]:
    resp = requests.get("https://news.google.com/rss/search",
                        params={"q": f'"{name}" stock', "hl": "en-US", "gl": "US", "ceid": "US:en"},
                        headers=HEADERS, timeout=20)
    resp.raise_for_status()
    items = parse_rss(resp.text, "google", limit)
    for it in items:                       # Google appends " - Publisher" to titles
        it["title"] = it["title"].rsplit(" - ", 1)[0]
    return items


SOURCES = [("yahoo", yahoo_rss), ("google", google_news)]


def normalize(title: str) -> str:
    """Used to spot the same story with slightly different punctuation,
    or with a publisher name added at the end ("... - Reuters")."""
    title = re.sub(r"\s+[-–—|]\s+[^-–—|]{1,40}$", "", title.strip())
    # Keep a-z, 0-9, spaces, and letters of non-Latin scripts (Chinese etc.).
    # For any title without such scripts this is exactly the original rule, so the
    # ids of headlines already in people's databases do not change.
    return "".join(c for c in title.lower()
                    if ("a" <= c <= "z") or ("0" <= c <= "9") or c == " "
                    or (ord(c) > 0x24F and c.isalnum())).strip()


def fetch_headlines(ticker: str, name: str, limit: int = 10) -> tuple[list[dict], list[str]]:
    """Returns (headlines, problems). Uses the first source that returns anything."""
    problems = []
    for source_name, source in SOURCES:
        try:
            items = source(ticker, name, limit)
        except Exception as e:
            problems.append(f"{source_name}: {type(e).__name__}: {str(e)[:80]}")
            continue
        if items:
            seen, unique = set(), []
            for it in items:
                key = normalize(it["title"])
                if key not in seen:
                    seen.add(key)
                    unique.append(it)
            return unique, problems
        problems.append(f"{source_name}: 0 items")
    return [], problems
