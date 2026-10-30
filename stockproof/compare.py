"""
"What changed since the last report?"

Investors care about change more than levels: a raised outlook, a new risk, a business line that
stopped being mentioned. This finds a company's latest two earnings documents (US: the 8-K press
releases on SEC EDGAR; China / Hong Kong: periodic reports or results announcements on Eastmoney),
and has the LLM read them side by side and list only the changes the documents actually state.

Cached per pair of documents, model and language: each comparison is paid for once.
"""

from __future__ import annotations

import datetime as dt
import json

from stockproof import cn

SCHEMA = """
CREATE TABLE IF NOT EXISTS report_comparisons (
    doc_now TEXT NOT NULL,
    doc_prev TEXT NOT NULL,
    model TEXT NOT NULL,
    lang TEXT NOT NULL,
    ticker TEXT NOT NULL,
    result TEXT NOT NULL,
    made_at TEXT NOT NULL,
    PRIMARY KEY (doc_now, doc_prev, model, lang)
);
"""
VERSION = 1
PER_DOC = 9000
AREAS = {"results", "guidance", "risks", "business", "capital", "other"}


class NotEnough(RuntimeError):
    pass


def _cn_docs(info: dict) -> list[dict]:
    """The two newest earnings documents of a Chinese company (one per day; summaries preferred)."""
    from stockproof.research_cn import valid_report_title
    items = cn.announcements(info, page_size=100)
    by_day = {}
    for a in items:
        t = a["title"]
        if not any(w in t for w in cn.EARN_WORDS) or any(w in t for w in cn.SKIP_WORDS):
            continue
        if "预告" in t or "盈利警告" in t or "profit warning" in t.lower():
            continue                                  # a forecast, not the results
        if info["market"] != "HK" and not valid_report_title(t):
            continue
        rank = 0 if ("摘要" in t or "快报" in t) else 1
        cur = by_day.get(a["date"])
        if cur is None or rank < cur[0]:
            by_day[a["date"]] = (rank, a)
    docs = [by_day[d][1] for d in sorted(by_day, reverse=True)[:2]]
    return [{"id": a["art_code"], "date": a["date"], "title": a["title"].split(":", 1)[-1],
             "fetch": (lambda code=a["art_code"]: cn.announcement_text(code))} for a in docs]


def _us_docs(sec_cache, cik: int) -> list[dict]:
    from stockproof import earnings as er
    filings = er.earnings_filings(sec_cache.submissions(cik), limit=2)
    return [{"id": f["accession"], "date": f["filed"], "title": f"8-K {f['filed']}",
             "fetch": (lambda f=f: er.fetch_release_text(cik, f))} for f in filings]


def build_prompt(name: str, ticker: str, prev: dict, now: dict, lang: str) -> str:
    language = "Simplified Chinese" if lang == "zh" else "English"
    return (
        "You are an equity analyst comparing a company's two latest earnings documents.\n"
        f"Company: {name} ({ticker}).\n\n"
        f"--- PREVIOUS ({prev['date']}, {prev['title']}; may be cut off) ---\n{prev['text']}\n--- END ---\n\n"
        f"--- LATEST ({now['date']}, {now['title']}; may be cut off) ---\n{now['text']}\n--- END ---\n\n"
        "List what CHANGED from the previous document to the latest one, using only what the documents say "
        "(numbers, outlook, risks named, business lines, dividends/buybacks). Ignore differences that only come "
        "from one document being longer or cut off. Do not guess analyst expectations.\n"
        "Reply ONLY with JSON:\n"
        f'{{"headline": "one sentence in {language}: the most important change",\n'
        f' "changes": [{{"area": "results | guidance | risks | business | capital | other",\n'
        f'               "before": "short, in {language}", "now": "short, in {language}",\n'
        '               "direction": "better | worse | neutral"}}] (at most 6, most important first),\n'
        f' "new_risks": [risks named only in the latest document, in {language}],\n'
        ' "tone_shift": -1 to 1 (is the latest document more negative or more positive than the previous one?)}'
    )


def _clean(data: dict) -> dict:
    changes = []
    for c in (data.get("changes") or [])[:6]:
        if not isinstance(c, dict):
            continue
        area = str(c.get("area", "other")).lower().strip()
        direction = str(c.get("direction", "neutral")).lower().strip()
        changes.append({"area": area if area in AREAS else "other",
                        "before": str(c.get("before", ""))[:200], "now": str(c.get("now", ""))[:200],
                        "direction": direction if direction in ("better", "worse", "neutral") else "neutral"})
    try:
        shift = max(-1.0, min(1.0, float(data.get("tone_shift", 0))))
    except (TypeError, ValueError):
        shift = 0.0
    return {"headline": str(data.get("headline", ""))[:300], "changes": changes,
            "new_risks": [str(x)[:200] for x in (data.get("new_risks") or [])][:4], "tone_shift": shift}


def compare(store, client, model_id: str, ticker: str, name: str, lang: str = "en",
            sec: tuple | None = None, docs: list[dict] | None = None) -> dict:
    """Comparison of the latest two earnings documents. `sec` = (SECCache, ticker_map) for US stocks;
    `docs` lets callers (and tests) pass the two documents directly, newest first."""
    store.conn.executescript(SCHEMA)
    if docs is None:
        info = cn.parse(ticker)
        if info:
            docs = _cn_docs(info)
        else:
            if sec is None:
                raise NotEnough("SEC data not available (set STOCKPROOF_SEC_CONTACT)")
            cache, tmap = sec
            entry = tmap.get(ticker)
            if not entry:
                raise NotEnough("not found in SEC's list")
            docs = _us_docs(cache, entry["cik"])
    if len(docs) < 2:
        raise NotEnough("fewer than two earnings documents found")
    now, prev = docs[0], docs[1]
    key = (now["id"], prev["id"], f"{model_id}#c{VERSION}", lang)
    hit = store.conn.execute("SELECT result FROM report_comparisons WHERE doc_now=? AND doc_prev=? AND model=? "
                             "AND lang=?", key).fetchone()
    if hit:
        return json.loads(hit[0])
    for d in (now, prev):
        if "text" not in d:
            text, url = d["fetch"]()
            d["text"], d["url"] = text[:PER_DOC], url
    if not now["text"] or not prev["text"]:
        raise NotEnough("could not read the documents")
    result = _clean(client.chat_json(build_prompt(name, ticker, prev, now, lang)))
    result.update({"ticker": ticker,
                   "now": {"date": now["date"], "title": now["title"], "url": now.get("url")},
                   "prev": {"date": prev["date"], "title": prev["title"], "url": prev.get("url")}})
    store.conn.execute("INSERT OR REPLACE INTO report_comparisons VALUES (?, ?, ?, ?, ?, ?, ?)",
                       (*key, ticker, json.dumps(result, ensure_ascii=False),
                        dt.datetime.now().isoformat(timespec="seconds")))
    store.conn.commit()
    return result
