"""
The work itself, shared by the command line and the dashboard:
  scan_ticker      fetch one stock's news and score the new headlines (US or China)
  earnings_ticker  US: EPS history + SUE, and the LLM's reading of the latest 8-K release
  earnings_any     US or China, picks the right source by ticker

Both return plain dicts and never print, so any interface can show progress its own way.
"""

from __future__ import annotations

import os

from marketmood import cn
from marketmood.llm import LLMClient, LLMError
from marketmood.news import fetch_headlines
from marketmood.scoring import score_headlines
from marketmood.store import Store


def is_fatal(error: Exception) -> bool:
    """Errors that will fail for every stock (bad key, no balance): stop instead of continuing."""
    return any(code in str(error) for code in ("401", "402"))


def scan_ticker(store: Store, client: LLMClient, model_id: str, ticker: str, name: str,
                per_ticker: int, lang: str) -> dict:
    out = {"ticker": ticker, "headlines": 0, "scored": 0, "new": 0, "error": None, "fatal": False}
    info = cn.parse(ticker)
    if info:
        if not name or name == ticker:
            name = cn.resolve_name(info, cn.CNCache(os.path.dirname(store.path)))
        items, problems = cn.fetch_headlines(info, per_ticker, name)
    else:
        items, problems = fetch_headlines(ticker, name, per_ticker)
    if not items:
        out["error"] = "no news found (" + "; ".join(problems) + ")"
        return out
    out["headlines"] = len(items)
    ids = store.add_headlines(ticker, items)
    todo = store.unscored(ids, model_id, lang)
    out["new"] = len(todo)
    if not todo:
        return out
    try:
        # Chinese feeds also give a short summary; it helps the model judge relevance
        summary = {it["title"]: it.get("summary") for it in items}
        texts = [f"{t} —— {summary[t]}" if summary.get(t) else t for _, t in todo]
        results = score_headlines(client, ticker, name, texts, lang)
    except LLMError as e:
        out["error"], out["fatal"] = f"scoring failed: {e}", is_fatal(e)
        return out
    for (hid, _), res in zip(todo, results):
        if res is not None:
            if res.get("duplicate_of") is not None:
                res = {**res, "duplicate_of": todo[res["duplicate_of"]][0]}
            store.save_score(hid, model_id, lang, res)
            out["scored"] += 1
    return out


def earnings_ticker(store: Store, cache, client: LLMClient | None, model_id: str,
                    ticker: str, cik: int, name: str, lang: str) -> dict:
    """Returns {"ticker", "name", "read", "history", "errors", "fatal"}."""
    from marketmood import earnings as er
    from marketmood.eps import add_sue, quarterly_eps
    from marketmood.sec import SECError

    row = {"ticker": ticker, "name": name, "read": None, "history": None, "errors": [], "fatal": False}
    try:
        row["history"] = add_sue(quarterly_eps(cache.company_facts(cik)))
    except Exception as e:
        row["errors"].append(f"EPS history unavailable ({type(e).__name__}: {e})")
    try:
        subs = cache.submissions(cik)
        filings = er.earnings_filings(subs)
        f, text, url = (filings[0], None, None) if filings else (None, None, None)
        if f is None and client is not None and er.sixk_filings(subs):
            # foreign issuer: look for the earnings release among recent 6-K filings
            checked = cache.cached(f"sixk_{cik}.json") or {}
            hit = er.find_6k_release(cik, subs, checked)
            cache.save(f"sixk_{cik}.json", checked)
            if hit:
                f, text, url = hit
        if f is not None and client is not None:
            read_key = f"{model_id}#v{er.READ_VERSION}"
            read = store.earnings_read(f["accession"], read_key, lang)
            if read is None:
                if text is None:
                    text, url = er.fetch_release_text(cik, f)
                if text:
                    result = er.read_release(client, name, ticker, text, lang)
                    store.save_earnings_read(f["accession"], read_key, lang, ticker, f["filed"], url, result)
                    read = {**result, "url": url, "filed": f["filed"]}
            row["read"] = read
    except (LLMError, SECError) as e:
        row["errors"].append(f"release not read ({e})")
        row["fatal"] = is_fatal(e)
    except Exception as e:
        row["errors"].append(f"release not read ({type(e).__name__}: {e})")
    return row


def earnings_any(store: Store, data_dir: str, client: LLMClient | None, model_id: str,
                 ticker: str, lang: str, name: str | None = None, sec: tuple | None = None) -> dict:
    """US tickers go to SEC EDGAR (sec = (SECCache, ticker_map)); Chinese codes to cn.py."""
    info = cn.parse(ticker)
    if info:
        cache = cn.CNCache(data_dir)
        if not name or name == info["symbol"]:
            name = cn.resolve_name(info, cache)
        return cn.earnings_ticker(store, data_dir, client, model_id, info, name, lang)
    empty = {"ticker": ticker, "name": name or ticker, "read": None, "history": None,
             "errors": [], "fatal": False}
    if sec is None:
        empty["errors"].append("SEC data not available (set MARKETMOOD_SEC_CONTACT)")
        return empty
    cache, tmap = sec
    entry = tmap.get(ticker)
    if not entry:
        empty["errors"].append("not found in SEC's list (non-US companies may not file 10-Q/8-K)")
        return empty
    return earnings_ticker(store, cache, client, model_id, ticker, entry["cik"],
                           name if name and name != ticker else entry["name"], lang)
