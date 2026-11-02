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
import os

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
VERSION = 2                      # 2: attribution table + evidence dated against the move day


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


# ---------------------------------------------------------------- attribution: market / industry / own
def _industry_code(data_dir: str, ticker: str) -> tuple[str | None, str | None]:
    """Shenwan level-1 (code, name) for an A-share, from cached data only (no LLM, little network)."""
    import os
    from stockproof import policy, screener
    info = cn.parse(ticker)
    if not info or info["market"] == "HK":
        return None, None
    em = screener.industry_of(data_dir, info["code"])
    try:
        with open(os.path.join(policy.policy_dir(data_dir), "industry_map.json"), encoding="utf-8") as f:
            mp = json.load(f)
    except (OSError, ValueError):
        mp = {}
    sw = mp.get(em) if em else None
    if sw is None and em in policy.NAME_TO_CODE:
        sw = em
    return (policy.NAME_TO_CODE.get(sw), sw) if sw else (None, None)


def _industry_series(data_dir: str, code: str, day: pd.Timestamp, fetch: bool = True) -> pd.Series | None:
    """Daily close of one Shenwan index; topped up from AKShare when the saved file stops before `day`."""
    import os
    from stockproof import policy
    px = policy.load_prices(data_dir)
    col = f"{code}_c"
    s = px[col].dropna() if px is not None and col in px else pd.Series(dtype=float)
    if (s.empty or s.index[-1] < day) and fetch:
        try:
            df = cn._ak().index_hist_sw(symbol=code, period="day")
            new = pd.Series(pd.to_numeric(df["收盘"], errors="coerce").to_numpy(), index=pd.to_datetime(df["日期"]))
            s = pd.concat([s[~s.index.isin(new.index)], new]).sort_index().dropna()
            if px is not None:
                px = px.reindex(px.index.union(s.index))
                px[col] = s.reindex(px.index)
                px.to_csv(os.path.join(policy.policy_dir(data_dir), "sw_l1.csv"))
        except Exception:
            pass
    return s if len(s) else None


def attribution(data_dir: str, ticker: str, day: str, window: int = 120, fetch: bool = True) -> dict | None:
    """Split the day's return into market, industry and the stock's own part, using betas estimated
    on the previous `window` trading days:  ret = a + b_m·market + b_i·(industry − market) + own."""
    import numpy as np
    m = quotes.moves(data_dir, ticker)
    d = pd.Timestamp(day)
    if m.empty or d not in m.index:
        return None
    df = pd.DataFrame({"ret": m["ret"], "mkt": m["market"]})
    code, sw = _industry_code(data_dir, ticker)
    ind = _industry_series(data_dir, code, d, fetch) if code else None
    if ind is not None:
        df["ind"] = ind.pct_change().reindex(df.index)
    hist = df[df.index < d].dropna().iloc[-window:]
    if len(hist) < 30 or pd.isna(df.loc[d, "mkt"]):
        return None
    use_ind = "ind" in df and pd.notna(df.loc[d, "ind"]) and hist["ind"].notna().sum() >= 30
    X = np.column_stack([np.ones(len(hist)), hist["mkt"]] + ([hist["ind"] - hist["mkt"]] if use_ind else []))
    beta, *_ = np.linalg.lstsq(X, hist["ret"].to_numpy(), rcond=None)
    r, mk = float(df.loc[d, "ret"]), float(df.loc[d, "mkt"])
    market_part = float(beta[1] * mk)
    industry_part = float(beta[2] * (df.loc[d, "ind"] - mk)) if use_ind else None
    own = r - market_part - (industry_part or 0.0)
    resid_sd = float(np.std(hist["ret"].to_numpy() - X @ beta, ddof=X.shape[1]))
    return {"ret": r, "market_ret": mk, "industry": sw if use_ind else None,
            "industry_ret": float(df.loc[d, "ind"]) if use_ind else None,
            "beta_market": round(float(beta[1]), 2), "beta_industry": round(float(beta[2]), 2) if use_ind else None,
            "market_part": market_part, "industry_part": industry_part, "own_part": own,
            "own_z": round(own / resid_sd, 2) if resid_sd > 0 else None, "window": len(hist),
            "rule": f"betas from the previous {len(hist)} trading days; own = return − market part − industry part"}


def _date_label(item_date: str, day: str) -> str:
    gap = (pd.Timestamp(day) - pd.Timestamp(str(item_date)[:10])).days
    return "same_day" if gap <= 0 else ("day_before" if gap == 1 else f"background_{gap}d")


def build_prompt(name: str, ticker: str, day: str, move: dict, items: list[dict], lang: str,
                 attr: dict | None = None) -> str:
    language = "Simplified Chinese" if lang == "zh" else "English"
    lines = []
    for i, it in enumerate(items, 1):
        note = f" — {it['note']}" if it.get("note") else ""
        lines.append(f"[{i}] {it['date']} ({_date_label(it['date'], day)}) {it['kind']}: {it['title']}{note}")
    if attr:
        parts = [f"market part {quotes.fmt_pct(attr['market_part'])} (market {quotes.fmt_pct(attr['market_ret'])}, beta {attr['beta_market']})"]
        if attr.get("industry_part") is not None:
            parts.append(f"industry part {quotes.fmt_pct(attr['industry_part'])} ({attr['industry']} index "
                         f"{quotes.fmt_pct(attr['industry_ret'])})")
        parts.append(f"stock's own part {quotes.fmt_pct(attr['own_part'])}"
                     + (f" ({abs(attr['own_z']):.1f}× its usual own move)" if attr.get("own_z") is not None else ""))
        att = ("Attribution (computed; state these numbers first, exactly as written, do not re-round): "
               + "; ".join(parts) + ".\n")
    else:
        att = ""
    ev = "\n".join(lines) if lines else "(nothing found)"
    return (
        "You are a careful equity analyst explaining a stock's price move to an investor.\n"
        f"Company: {name} ({ticker}). Day: {day}.\n"
        f"Move: stock {quotes.fmt_pct(move.get('ret'))}, market {quotes.fmt_pct(move.get('market'))}, "
        f"difference {quotes.fmt_pct(move.get('excess'))}"
        + (f" (about {abs(move['z']):.1f} times this stock's usual daily difference)" if move.get("z") else "")
        + ".\n" + att + "\nEvidence published around that day (the ONLY facts you may use):\n" + ev + "\n\n"
        "Rules: use only the evidence above and cite it like [2]. Do not invent news, numbers or reasons. "
        "If the evidence does not explain the move, say so plainly (e.g. no company-specific news was found; "
        "the move may reflect the sector, the market or flows) — that is a valid answer. "
        "If the market itself moved a lot, mention it. Start from the attribution: if the market and industry "
        "parts explain most of the move, say so; then explain only the stock's own part with the evidence. "
        "Items labelled background_Nd were published N days before the move: they are context, never call them "
        "news of that day ('当日'/'today').\n"
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
    if os.environ.get("STOCKPROOF_RESOLVE_LINKS", "1") != "0":
        from stockproof import links            # cite the publisher, not a news.google.com redirect
        links.resolve_items(items, data_dir, store=store, budget=10)
    for it in items:
        it["timing"] = _date_label(it["date"], day)
    try:
        attr = attribution(data_dir, ticker, day)
    except Exception:
        attr = None
    out = {"ticker": ticker, "day": day, "move": move, "attribution": attr, "evidence": items}
    if client is None:
        return out
    data = client.chat_json(build_prompt(name, ticker, day, move, items, lang, attr))
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
