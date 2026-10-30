"""
"Why did this stock move?"

For a day with an unusual move, collect what was published around it — scored headlines, company
announcements, earnings releases — and let the LLM explain the move USING ONLY THAT EVIDENCE,
citing it by number. If nothing collected explains the move, it has to say so (sector or market
flows, or simply unknown) instead of inventing a reason. Every cited item links to the original.

Explanations are cached per (ticker, day, model, language).
"""

from __future__ import annotations

import datetime as dt
import json

import pandas as pd

from stockproof import announcements, cn, quotes

SCHEMA = """
CREATE TABLE IF NOT EXISTS move_explanations (
    ticker TEXT NOT NULL,
    day TEXT NOT NULL,
    model TEXT NOT NULL,
    lang TEXT NOT NULL,
    result TEXT NOT NULL,
    made_at TEXT NOT NULL,
    PRIMARY KEY (ticker, day, model, lang)
);
"""
VERSION = 1


def evidence(store, ticker: str, day: str, before: int = 3, after: int = 1,
             min_relevance: float = 0.5, limit: int = 15) -> list[dict]:
    """Items published from `before` days before to `after` days after `day`, newest first.
    Headlines dated the evening before often explain the next day's move; after-close news dated
    the same day may only show up in the next day's price, hence the small window after."""
    d = pd.Timestamp(day)
    lo, hi = (d - pd.Timedelta(days=before)).date().isoformat(), (d + pd.Timedelta(days=after)).date().isoformat()
    items = []
    df = store.scored([ticker], None, "en", any_lang=True)
    if len(df):
        df = df[(df["date"] >= lo) & (df["date"] <= hi) & (df["relevance"] >= min_relevance)
                & df["duplicate_of"].isna()]
        df = df.assign(_w=(df["score"].abs() * df["relevance"])).sort_values("_w", ascending=False).head(limit)
        for h in df.itertuples():
            items.append({"kind": "news", "date": h.date, "title": h.title, "link": h.link,
                          "score": float(h.score), "note": h.reason, "source": h.source})
    if cn.is_cn(ticker):
        for a in announcements.recent(store, [ticker], days=400, min_importance=1):
            if lo <= a["date"] <= hi:
                items.append({"kind": "announcement", "date": a["date"], "title": a["title"], "link": a["url"],
                              "score": (a["read"] or {}).get("impact", a["direction"] or 0.0),
                              "note": (a["read"] or {}).get("summary") or a["category"], "source": "eastmoney"})
    rows = store.conn.execute("SELECT result, url, filed FROM earnings_reads WHERE ticker = ? AND filed BETWEEN ? AND ? "
                              "ORDER BY read_at DESC", (ticker.upper(), lo, hi)).fetchall()
    seen = set()
    for res, url, filed in rows:
        if url in seen:
            continue
        seen.add(url)
        r = json.loads(res)
        items.append({"kind": "earnings", "date": filed, "title": r.get("doc_title") or r.get("period") or "earnings release",
                      "link": url, "score": r.get("tone", 0.0), "note": r.get("summary", ""), "source": "filing"})
    return sorted(items, key=lambda i: str(i["date"]), reverse=True)


def build_prompt(name: str, ticker: str, day: str, move: dict, items: list[dict], lang: str) -> str:
    language = "Simplified Chinese" if lang == "zh" else "English"
    lines = []
    for i, it in enumerate(items, 1):
        note = f" — {it['note']}" if it.get("note") else ""
        lines.append(f"[{i}] {it['date']} {it['kind']}: {it['title']}{note}")
    ev = "\n".join(lines) if lines else "(nothing found)"
    return (
        "You are a careful equity analyst explaining a stock's price move to an investor.\n"
        f"Company: {name} ({ticker}). Day: {day}.\n"
        f"Move: stock {quotes.fmt_pct(move.get('ret'))}, market {quotes.fmt_pct(move.get('market'))}, "
        f"difference {quotes.fmt_pct(move.get('excess'))}"
        + (f" (about {abs(move['z']):.1f} times this stock's usual daily difference)" if move.get("z") else "")
        + ".\n\nEvidence published around that day (the ONLY facts you may use):\n" + ev + "\n\n"
        "Rules: use only the evidence above and cite it like [2]. Do not invent news, numbers or reasons. "
        "If the evidence does not explain the move, say so plainly (e.g. no company-specific news was found; "
        "the move may reflect the sector, the market or flows) — that is a valid answer. "
        "If the market itself moved a lot, mention it.\n"
        "Reply ONLY with JSON:\n"
        f'{{"summary": "2-3 sentences in {language}, with citations like [1]",\n'
        ' "causes": [{"text": "one cause in ' + language + '", "evidence": [1, 3]}],\n'
        ' "confidence": "high | medium | low",\n'
        ' "explained": true or false (does the evidence explain most of the move?)}'
    )


def explain(store, client, model_id: str, data_dir: str, ticker: str, day: str | None, name: str,
            lang: str = "en", force: bool = False) -> dict:
    """Explanation of the move on `day` (default: the latest unusual move in the last 10 days)."""
    store.conn.executescript(SCHEMA)
    m = quotes.moves(data_dir, ticker)
    if m.empty:
        return {"error": "no_prices"}
    if day is None:
        recent = m[m["unusual"] & (m.index >= m.index[-1] - pd.Timedelta(days=10))]
        day = (recent.index[-1] if len(recent) else m.index[-1]).date().isoformat()
    if pd.Timestamp(day) not in m.index:
        return {"error": "not_a_trading_day", "day": day}
    row = m.loc[pd.Timestamp(day)]
    move = {"ret": float(row["ret"]), "market": None if pd.isna(row["market"]) else float(row["market"]),
            "excess": float(row["excess"]), "z": None if pd.isna(row["z"]) else float(row["z"]),
            "unusual": bool(row["unusual"])}
    key = (ticker, day, f"{model_id}#e{VERSION}", lang)
    if not force:
        hit = store.conn.execute("SELECT result FROM move_explanations WHERE ticker=? AND day=? AND model=? AND lang=?",
                                 key).fetchone()
        if hit:
            return json.loads(hit[0])
    items = evidence(store, ticker, day)
    out = {"ticker": ticker, "day": day, "move": move, "evidence": items}
    if client is None:
        return out
    data = client.chat_json(build_prompt(name, ticker, day, move, items, lang))
    valid = set(range(1, len(items) + 1))
    causes = []
    for c in (data.get("causes") or [])[:4]:
        if isinstance(c, dict):
            refs = [int(x) for x in (c.get("evidence") or []) if str(x).isdigit() and int(x) in valid]
            causes.append({"text": str(c.get("text", ""))[:240], "evidence": refs})
    conf = str(data.get("confidence", "low")).lower()
    out.update({"summary": str(data.get("summary", ""))[:700], "causes": causes,
                "confidence": conf if conf in ("high", "medium", "low") else "low",
                "explained": bool(data.get("explained", False)) and bool(items)})
    store.conn.execute("INSERT OR REPLACE INTO move_explanations VALUES (?, ?, ?, ?, ?, ?)",
                       (*key, json.dumps(out, ensure_ascii=False), dt.datetime.now().isoformat(timespec="seconds")))
    store.conn.commit()
    return out


def unusual_today(data_dir: str, tickers: list[str], days: int = 3) -> list[dict]:
    """Watchlist stocks with an unusual move in the last `days` trading days (latest first)."""
    out = []
    for tk in tickers:
        m = quotes.moves(data_dir, tk)
        if m.empty:
            continue
        recent = m.iloc[-days:]
        hits = recent[recent["unusual"]]
        if len(hits):
            r = hits.iloc[-1]
            out.append({"ticker": tk, "day": hits.index[-1].date().isoformat(), "ret": float(r["ret"]),
                        "excess": float(r["excess"]), "z": None if pd.isna(r["z"]) else float(r["z"])})
    return sorted(out, key=lambda x: (x["day"], abs(x["excess"])), reverse=True)
