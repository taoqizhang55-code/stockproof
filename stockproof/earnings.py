"""
Earnings releases, read by the LLM.

When a US company reports quarterly results it files an 8-K with "Item 2.02
Results of Operations", and attaches the press release as exhibit 99.1.
That is the same text journalists read on earnings day, straight from the source.

We find the latest such filing, pull the press-release text, and ask the LLM for:
tone, a short summary, guidance direction, key points and risks.
"""

from __future__ import annotations

import re
from html.parser import HTMLParser

from stockproof.llm import LLMClient
from stockproof.sec import SECCache, get

READ_VERSION = 3          # bump when the prompt changes, so cached readings are redone
MAX_CHARS = 15000          # the headline numbers and outlook are almost always near the top
REASON_LANGUAGE = {"en": "English", "zh": "Simplified Chinese"}
GUIDANCE = {"raised", "maintained", "lowered", "provided", "initiated", "withdrawn", "none"}


class _TextExtractor(HTMLParser):
    def __init__(self):
        super().__init__()
        self.parts, self._skip = [], 0

    def handle_starttag(self, tag, attrs):
        if tag in ("script", "style"):
            self._skip += 1
        elif tag in ("p", "div", "br", "tr", "li", "h1", "h2", "h3", "table"):
            self.parts.append("\n")

    def handle_endtag(self, tag):
        if tag in ("script", "style") and self._skip:
            self._skip -= 1
        elif tag in ("td", "th"):
            self.parts.append(" | ")

    def handle_data(self, data):
        if not self._skip:
            self.parts.append(data)


def html_to_text(html_text: str) -> str:
    parser = _TextExtractor()
    parser.feed(html_text)
    text = "".join(parser.parts).replace("\xa0", " ")
    text = re.sub(r"[ \t]+", " ", text)
    text = re.sub(r"(\s*\|\s*)+\n", "\n", text)
    return re.sub(r"\n\s*\n+", "\n\n", text).strip()


def earnings_filings(submissions: dict, limit: int = 4) -> list[dict]:
    """Most recent 8-K filings with Item 2.02, newest first."""
    recent = submissions.get("filings", {}).get("recent", {})
    out = []
    for i, form in enumerate(recent.get("form", [])):
        items = (recent.get("items") or [""] * (i + 1))[i] or ""
        if form in ("8-K", "8-K/A") and "2.02" in items:
            out.append({"accession": recent["accessionNumber"][i],
                        "filed": recent["filingDate"][i],
                        "report_date": (recent.get("reportDate") or [""] * (i + 1))[i],
                        "primary": recent["primaryDocument"][i]})
        if len(out) >= limit:
            break
    return out


def sixk_filings(submissions: dict, limit: int = 20) -> list[dict]:
    """Most recent 6-K filings, newest first. Foreign companies listed in the US (Alibaba, PDD,
    NIO...) file 6-K instead of 8-K, with no item numbers, so earnings ones must be found by content."""
    recent = submissions.get("filings", {}).get("recent", {})
    out = []
    for i, form in enumerate(recent.get("form", [])):
        if form in ("6-K", "6-K/A"):
            out.append({"accession": recent["accessionNumber"][i], "filed": recent["filingDate"][i],
                        "report_date": (recent.get("reportDate") or [""] * (i + 1))[i],
                        "primary": recent["primaryDocument"][i]})
        if len(out) >= limit:
            break
    return out


def looks_like_results(text: str) -> bool:
    """Is this the earnings release itself (not a notice of an upcoming earnings date)?"""
    head = text[:6000].lower()
    period = any(w in head for w in ("quarter", "fiscal year", "half year", "interim", "six months"))
    numbers = any(w in head for w in ("revenue", "revenues", "net income", "net loss"))
    money = any(w in head for w in ("rmb", "us$", "hk$", "million", "billion"))
    notice = any(w in head[:800] for w in ("to report", "will report", "to announce", "will announce",
                                           "to release", "will release", "conference call to be held"))
    return "results" in head and period and numbers and money and not (notice and "revenue" not in head[800:])


def find_6k_release(cik: int, submissions: dict, checked: dict, max_checks: int = 20):
    """(filing, text, url) of the newest 6-K that is an earnings release, or None.
    `checked` remembers which filings were already found not to be results (saves requests).
    20 because some companies file a 6-K every few days (Alibaba mirrors its Hong Kong notices),
    so the last results release can be 10-15 filings back."""
    for f in sixk_filings(submissions)[:max_checks]:
        if checked.get(f["accession"]) is False:
            continue
        text, url = fetch_release_text(cik, f)
        is_results = bool(text) and looks_like_results(text)
        checked[f["accession"]] = is_results
        if is_results:
            return f, text, url
    return None


def pick_press_release(index_items: list[dict], primary: str) -> str | None:
    """Choose the press-release file from a filing's file list (exhibit 99.x)."""
    htm = [it for it in index_items
           if str(it.get("name", "")).lower().endswith((".htm", ".html"))
           and not re.match(r"r\d+\.htm", str(it.get("name", "")).lower())   # XBRL viewer pages
           and "index" not in str(it.get("name", "")).lower()]
    for it in htm:
        name = it["name"].lower()
        if re.search(r"ex[-_]?99", name) or "pressrelease" in name or "earnings" in name:
            return it["name"]
    others = [it for it in htm if it["name"] != primary]
    if others:
        return max(others, key=lambda it: int(it.get("size") or 0))["name"]
    return primary if htm else None


def fetch_release_text(cik: int, filing: dict) -> tuple[str, str]:
    """Returns (text, url) of the press release in an earnings 8-K."""
    acc = filing["accession"].replace("-", "")
    base = f"https://www.sec.gov/Archives/edgar/data/{cik}/{acc}"
    index = get(f"{base}/index.json")
    name = pick_press_release(index.get("directory", {}).get("item", []), filing["primary"])
    if not name:
        return "", base
    url = f"{base}/{name}"
    return html_to_text(get(url, as_json=False))[:MAX_CHARS], url


def build_prompt(name: str, ticker: str, text: str, lang: str, doc_kind: str = "earnings press release") -> str:
    language = REASON_LANGUAGE.get(lang, "English")
    return (
        f"You are an equity analyst reading a company's own {doc_kind}.\n"
        f"Company: {name} ({ticker}).\n\n"
        f"--- DOCUMENT (may be cut off; may be in Chinese) ---\n{text}\n--- END ---\n\n"
        "Report only what the release says. Do not guess analyst expectations.\n"
        "Reply ONLY with JSON:\n"
        '{"period": "e.g. Q3 fiscal 2026",\n'
        ' "tone": -1 to 1 (how good the results and outlook are for the stock),\n'
        f' "summary": "2 sentences in {language}",\n'
        ' "revenue_growth": "year-over-year revenue change as stated, e.g. +8%, or unknown",\n'
        ' "eps": "reported EPS as stated, or unknown",\n'
        ' "guidance": one of:\n'
        '    raised | lowered | maintained  (the release compares the outlook with the previous one)\n'
        '    provided   (gives an outlook, e.g. next quarter, without saying whether it changed)\n'
        '    initiated  (says this is the FIRST outlook it has ever given, or for a new period type)\n'
        '    withdrawn  (removes an earlier outlook)\n'
        '    none       (no forward-looking outlook in the release),\n'
        f' "key_points": [up to 3 short points in {language}],\n'
        f' "risks": [up to 2 short points in {language}]}}'
    )


def read_release(client: LLMClient, name: str, ticker: str, text: str, lang: str,
                 doc_kind: str = "earnings press release") -> dict:
    data = client.chat_json(build_prompt(name, ticker, text, lang, doc_kind))
    try:
        tone = max(-1.0, min(1.0, float(data.get("tone", 0))))
    except (TypeError, ValueError):
        tone = 0.0
    guidance = str(data.get("guidance", "none")).lower().strip()
    return {
        "period": str(data.get("period", ""))[:60],
        "tone": tone,
        "summary": str(data.get("summary", ""))[:600],
        "revenue_growth": str(data.get("revenue_growth", "unknown"))[:40],
        "eps": str(data.get("eps", "unknown"))[:40],
        "guidance": guidance if guidance in GUIDANCE else "none",
        "key_points": [str(x)[:200] for x in (data.get("key_points") or [])][:3],
        "risks": [str(x)[:200] for x in (data.get("risks") or [])][:2],
    }
