"""
Evidence scorecard: what the public evidence says about one stock, in a few transparent dimensions.

Not a buy/sell call. Each dimension shows its score (0-100, 50 = neutral), the facts behind it with
links, and — most important — whether stockproof's own history tests found that dimension useful.
Dimensions that were never tested say so. The LLM only reads the listed evidence and must cite it.

  fundamentals  whole-market percentile from `stockproof screen` (A-shares); SUE for other markets
  momentum      60-day return percentile (A-shares, when the market snapshot has it)
  report        the LLM's reading of the latest earnings report (tone, guidance)
  quality       is the profit growth from the core business and backed by cash, or one-off? (LLM)
  news          relevance-weighted mood of the last 14 days of headlines
  filings       important company announcements in the last 90 days (A-shares / HK): insider
                selling, regulator letters, buybacks, big contracts…

Cached per (ticker, day, model, language): one synthesis call per stock per day.
"""

from __future__ import annotations

import datetime as dt
import json
import math
import os

import pandas as pd

from stockproof import clock
from stockproof import announcements, cn

SCHEMA = """
CREATE TABLE IF NOT EXISTS scorecards (
    ticker TEXT NOT NULL,
    day TEXT NOT NULL,
    model TEXT NOT NULL,
    lang TEXT NOT NULL,
    result TEXT NOT NULL,
    made_at TEXT NOT NULL,
    PRIMARY KEY (ticker, day, model, lang)
);
"""
VERSION = 4
DIMS = ["fundamentals", "momentum", "report", "quality", "news", "filings", "policy"]
NAMES = {
    "en": {"fundamentals": "Fundamentals", "momentum": "Price trend", "report": "Latest report",
           "quality": "Earnings quality", "news": "News", "filings": "Announcements",
           "policy": "Industry policy"},
    "zh": {"fundamentals": "基本面", "momentum": "股价走势", "report": "最新财报", "quality": "盈利质量",
           "news": "新闻", "filings": "公告", "policy": "行业政策"},
}
DISCLAIMER = {
    "en": "Evidence summary from public data, not investment advice. stockproof's own tests found that public "
          "earnings data does not reliably beat the market after costs. Do your own research.",
    "zh": "基于公开数据的证据汇总，不构成投资建议。stockproof 自己的历史检验发现，公开的财报数据扣除交易成本后"
          "不能稳定跑赢市场。请独立判断。",
}
GUIDANCE_ADJ = {"raised": 15, "initiated": 5, "provided": 0, "maintained": 0, "none": 0,
                "lowered": -20, "withdrawn": -25}


def _clip(x: float) -> float:
    return max(0.0, min(100.0, float(x)))


def _norm_cdf(x: float) -> float:
    return 0.5 * (1 + math.erf(x / math.sqrt(2)))


# ---------------------------------------------------------------- what history says about each dimension

def validation(data_dir: str, market: str, lang: str = "zh") -> dict:
    """One line per dimension: was it tested, and what did the test find? From saved results."""
    zh = lang == "zh"
    out = {}
    bt = None
    p = os.path.join(data_dir, "screens", "cn_backtest.json")
    if os.path.exists(p):
        try:
            with open(p, encoding="utf-8") as f:
                bt = json.load(f)
        except (OSError, ValueError):
            bt = None

    def factor(fs):
        for r in (bt or {}).get("factors", []):
            if r.get("factors") == fs and r.get("n"):
                return r
        return None

    comp = factor(["sue", "rev_yoy", "np_yoy", "roe", "mom60"])
    if market == "cn" and comp:
        out["fundamentals"] = {"tested": True, "useful": abs(comp["t"]) >= 2,
                               "text": (f"已检验（沪深300，2016 起）：综合分前 30 名每年比同池多 {100 * comp['ann_excess']:+.1f}%，"
                                        f"t={comp['t']:.1f}，不显著" if zh else
                                        f"Tested (CSI300 since 2016): top 30 by score beat the same universe by "
                                        f"{100 * comp['ann_excess']:+.1f}%/yr, t={comp['t']:.1f} — not significant")}
    else:
        out["fundamentals"] = {"tested": True, "useful": False,
                               "text": ("已检验：业绩惊喜扣费后的回测几乎没有超额（美股 +0.3%/年）" if zh else
                                        "Tested: an earnings-surprise backtest earned ~nothing after costs (US +0.3%/yr)")}
    mom = factor(["mom60"])
    out["momentum"] = ({"tested": True, "useful": abs(mom["t"]) >= 2,
                        "text": (f"已检验：近 60 日走势前 30 名每年 {100 * mom['ann_excess']:+.1f}%，t={mom['t']:.1f}，"
                                 f"有迹象但不显著" if zh else
                                 f"Tested: top 30 by 60-day return {100 * mom['ann_excess']:+.1f}%/yr, t={mom['t']:.1f} — "
                                 f"a hint, not significant")}
                       if mom else {"tested": False, "useful": False, "text": "尚未检验" if zh else "not tested yet"})
    if market == "us":
        rep = ("已检验（美股 472 份财报）：负面语气公布两天平均 −3.1%（t=−4.0）；但不能预测之后 60 天" if zh else
               "Tested (472 US releases): negative tone → −3.1% in two days (t=−4.0); no prediction for the next 60 days")
    else:
        rep = ("已检验（A股 590 份财报）：负面语气公布两天 −1.3%（t=−4.2），与业绩惊喜高度重叠；不能预测之后 60 天" if zh else
               "Tested (590 A-share reports): negative tone → −1.3% in two days (t=−4.2), overlaps with SUE; "
               "no prediction for the next 60 days")
    out["report"] = {"tested": True, "useful": False, "text": rep}
    from stockproof import policy
    out["policy"] = {**policy.finding(data_dir, lang), "info_only": True}
    for k in ("quality", "news", "filings"):
        out[k] = {"tested": False, "useful": False,
                  "text": "尚未检验：仅供参考" if zh else "not tested yet: for information only"}
    return out


# ---------------------------------------------------------------- rule-based dimensions

def news_dim(headlines: list[dict], days: int = 14, min_relevance: float = 0.5, min_n: int = 3) -> dict:
    since = (clock.today() - dt.timedelta(days=days)).isoformat()
    hs = [h for h in headlines if (h.get("relevance") or 0) >= min_relevance and not h.get("dup")
          and (h.get("date") or "") >= since and h.get("score") is not None]
    if len(hs) < min_n:
        return {"score": None, "n": len(hs), "items": hs[:5]}
    w = sum(h["relevance"] for h in hs)
    mood = sum(h["score"] * h["relevance"] for h in hs) / w
    hs = sorted(hs, key=lambda h: -abs(h["score"]) * h["relevance"])
    return {"score": _clip(50 + 50 * mood), "mood": mood, "n": len(hs), "items": hs[:6]}


def filings_dim(items: list[dict]) -> dict:
    """Important announcements (importance >= 2): LLM impact when read, else the category's usual direction.
    One event produces many filings (a buyback: proposal, plan, progress x N; a restructuring: dozens), so
    each category counts once — its average effect, weighted by its highest importance."""
    imp = [a for a in items if (a.get("importance") or 0) >= 2]
    if not imp:
        return {"score": None, "n": 0, "items": []}
    groups: dict[str, list] = {}
    for a in imp:
        r = a.get("read") or {}
        d = r.get("impact") if isinstance(r.get("impact"), (int, float)) else (a.get("direction") or 0)
        groups.setdefault(a.get("category") or a.get("title", ""), []).append((float(d), a))
    total, used = 0.0, []
    for cat, rows in groups.items():
        eff = sum(d for d, _ in rows) / len(rows)
        weight = max(a["importance"] for _, a in rows) - 1          # importance 3 counts double
        total += eff * weight
        if eff:
            first = rows[0][1]
            used.append({**first, "effect": eff, "count": len(rows)})
    return {"score": _clip(50 + 12 * total), "n": len(imp), "events": len(groups),
            "items": sorted(used, key=lambda a: -abs(a["effect"]))[:8]}


def report_dim(read: dict | None) -> dict:
    if not read or read.get("tone") is None:
        return {"score": None}
    s = 50 + 40 * float(read["tone"]) + GUIDANCE_ADJ.get(str(read.get("guidance") or "none"), 0)
    return {"score": _clip(s), "tone": read.get("tone"), "guidance": read.get("guidance"),
            "filed": read.get("filed"), "url": read.get("url"), "summary": read.get("summary")}


def fundamentals_dim(screen_rec: dict | None, sue: float | None) -> dict:
    if screen_rec and screen_rec.get("covered"):
        return {"score": _clip(screen_rec["score"]), "rank": screen_rec["rank"], "of": screen_rec["of"],
                "percentiles": {k: screen_rec.get(k) for k in ("sue", "rev_yoy", "np_yoy", "roe")
                                if screen_rec.get(k) is not None}, "source": "screen"}
    if sue is not None and math.isfinite(sue):
        return {"score": _clip(100 * _norm_cdf(max(-3, min(3, sue)) / 1.5)), "sue": sue, "source": "sue"}
    return {"score": None, "why": (screen_rec or {}).get("why")}


def policy_dim(data_dir: str, store, client, model_id: str | None, ticker: str) -> dict:
    """Recent 新闻联播 policy signals for the stock's Shenwan industry. Information only: no score, because the
    study found no tradable edge (see policy.finding)."""
    from stockproof import policy, screener
    info = cn.parse(ticker)
    if not info or info["market"] == "HK" or not model_id:
        return {"score": None}
    em = screener.industry_of(data_dir, info["code"])
    if not em:
        return {"score": None}
    try:
        sw = policy.industry_map(data_dir, client, [em]).get(em)
    except Exception:
        sw = None
    if not sw:
        return {"score": None, "industry": em}
    items = policy.recent_for(store, model_id, sw, days=90)
    return {"score": None, "industry": em, "sw": sw, "n": len(items), "items": items[:6]}


def momentum_dim(screen_rec: dict | None, price: dict | None) -> dict:
    p = (screen_rec or {}).get("mom60") if screen_rec and screen_rec.get("covered") else None
    out = {"score": _clip(p) if p is not None else None}
    if price:
        out.update({"m1": price.get("m1"), "ytd": price.get("ytd")})
    return out


# ---------------------------------------------------------------- the LLM part

def evidence_items(d: dict, filings: list[dict], max_news: int = 8) -> list[dict]:
    """Numbered evidence for the LLM: the earnings reading, important announcements, top headlines."""
    items = []
    e = d.get("earnings") or {}
    if e:
        pts = "; ".join(str(x) for x in (e.get("key_points") or [])[:5])
        risks = "; ".join(str(x) for x in (e.get("risks") or [])[:4])
        items.append({"kind": "report", "date": e.get("filed"), "link": e.get("url"),
                      "title": e.get("doc_title") or "latest earnings report",
                      "text": f"{e.get('summary') or ''} Key points: {pts}. Risks: {risks}. "
                              f"Revenue growth: {e.get('revenue_growth')}. Guidance: {e.get('guidance')}."[:1500]})
    for a in filings[:10]:
        r = a.get("read") or {}
        items.append({"kind": "announcement", "date": a.get("date"), "link": a.get("url"), "title": a.get("title"),
                      "text": (r.get("summary") or a.get("category_name") or "")[:400]})
    heads = [h for h in d.get("headlines", []) if (h.get("relevance") or 0) >= 0.5 and not h.get("dup")]
    for h in heads[:max_news]:
        items.append({"kind": "news", "date": h.get("date"), "link": h.get("link"), "title": h.get("title"),
                      "text": (h.get("reason") or "")[:300]})
    return items


def build_prompt(name: str, ticker: str, numbers: dict, items: list[dict], lang: str) -> str:
    language = "Simplified Chinese" if lang == "zh" else "English"
    lines = [f"[{i}] ({it['kind']}, {it.get('date') or '?'}) {it.get('title') or ''} — {it.get('text') or ''}"
             for i, it in enumerate(items, 1)]
    return (
        "You review the public evidence on one listed company for an investor. You do NOT give buy/sell advice "
        "and do NOT predict the price.\n"
        f"Company: {name} ({ticker}).\n"
        f"Computed numbers (from data, trust them): {json.dumps(numbers, ensure_ascii=False)}\n\n"
        "Evidence (use ONLY this; cite by number):\n" + ("\n".join(lines) or "(none)") + "\n\n"
        "Judge earnings QUALITY from the evidence: is profit growth from the core business, backed by revenue "
        "and cash flow, or from one-off items (asset sales, subsidies, fair-value gains, a low base after a loss)? "
        "If the evidence doesn't say, give 0 and say it is unclear.\n"
        "Reply ONLY with JSON:\n"
        f'{{"summary": "2 sentences in {language}: what the evidence says overall, neutral wording",\n'
        f' "positives": [{{"text": "short, in {language}", "evidence": [numbers]}}] (at most 4),\n'
        f' "risks": [{{"text": "short, in {language}", "evidence": [numbers]}}] (at most 4),\n'
        f' "quality": {{"score": -1 to 1, "reason": "one sentence in {language}", "evidence": [numbers]}},\n'
        f' "watch": ["what to check next, in {language}"] (at most 3)}}\n'
        "Every positive and risk must cite at least one evidence number; drop points you cannot cite."
    )


def _cited(points, valid: set) -> list[dict]:
    out = []
    for p in (points or [])[:4]:
        if not isinstance(p, dict):
            continue
        refs = [int(x) for x in (p.get("evidence") or []) if str(x).strip().isdigit() and int(x) in valid]
        if refs and p.get("text"):
            out.append({"text": str(p["text"])[:240], "evidence": refs})
    return out


def synthesize(client, name: str, ticker: str, numbers: dict, items: list[dict], lang: str) -> dict:
    data = client.chat_json(build_prompt(name, ticker, numbers, items, lang))
    valid = set(range(1, len(items) + 1))
    q = data.get("quality") if isinstance(data.get("quality"), dict) else {}
    try:
        qs = max(-1.0, min(1.0, float(q.get("score", 0))))
    except (TypeError, ValueError):
        qs = 0.0
    qrefs = [int(x) for x in (q.get("evidence") or []) if str(x).strip().isdigit() and int(x) in valid]
    return {"summary": str(data.get("summary", ""))[:600],
            "positives": _cited(data.get("positives"), valid), "risks": _cited(data.get("risks"), valid),
            "quality": {"score": qs if qrefs else 0.0, "reason": str(q.get("reason", ""))[:300], "evidence": qrefs},
            "watch": [str(x)[:200] for x in (data.get("watch") or [])][:3]}


# ---------------------------------------------------------------- putting it together

def overall(dims: dict) -> dict:
    vals = [v["score"] for v in dims.values() if v.get("score") is not None]
    if len(vals) < 2:
        return {"score": None, "label": "insufficient", "n": len(vals)}
    s = sum(vals) / len(vals)
    spread = max(vals) - min(vals)
    label = "positive" if s >= 62 else "negative" if s <= 38 else ("mixed" if spread >= 40 else "neutral")
    return {"score": round(s, 1), "label": label, "n": len(vals)}


LABELS = {"en": {"positive": "evidence leans positive", "negative": "evidence leans negative",
                 "mixed": "mixed evidence", "neutral": "neutral", "insufficient": "not enough evidence"},
          "zh": {"positive": "证据偏正面", "negative": "证据偏负面", "mixed": "证据分歧", "neutral": "中性",
                 "insufficient": "证据不足"}}


def build(app, store, client, model_id: str | None, ticker: str, lang: str = "zh",
          screen_rec: dict | None = None, force: bool = False) -> dict:
    """The scorecard of one stock from saved data (news, earnings reading, announcements, screen).
    `app` is a Dashboard (for its per-stock view); refresh the data first for a fresh card."""
    store.conn.executescript(SCHEMA)
    day = clock.today().isoformat()
    key = (ticker, day, f"{model_id}#s{VERSION}", lang)
    if not force and model_id:
        hit = store.conn.execute("SELECT result FROM scorecards WHERE ticker=? AND day=? AND model=? AND lang=?",
                                 key).fetchone()
        if hit:
            return json.loads(hit[0])
    from stockproof import screener
    d = app.stock(ticker, lang)
    market = "cn" if cn.is_cn(ticker) else "us"
    if screen_rec is None:
        screen_rec = screener.lookup(app.data_dir, ticker, lang)
    filings = announcements.recent(store, [ticker], days=90, min_importance=2, lang=lang) if cn.is_cn(ticker) else []
    rep = d.get("report") or {}
    dims = {"fundamentals": fundamentals_dim(screen_rec, rep.get("sue")),
            "momentum": momentum_dim(screen_rec, d.get("price")),
            "report": report_dim(d.get("earnings")),
            "news": news_dim(d.get("headlines") or []),
            "filings": filings_dim(filings)}
    items = evidence_items(d, filings)
    numbers = {k: round(v["score"]) for k, v in dims.items() if v.get("score") is not None}
    if rep.get("sue") is not None:
        numbers["sue"] = round(rep["sue"], 2)
    if screen_rec and screen_rec.get("covered"):
        numbers["market_rank"] = f"{screen_rec['rank']}/{screen_rec['of']}"
    synth = None
    if client is not None and items:
        synth = synthesize(client, d.get("name") or ticker, ticker, numbers, items, lang)
        if synth["quality"]["evidence"]:
            dims["quality"] = {"score": _clip(50 + 50 * synth["quality"]["score"]),
                               "reason": synth["quality"]["reason"], "evidence": synth["quality"]["evidence"]}
    dims.setdefault("quality", {"score": None})
    dims["policy"] = policy_dim(app.data_dir, store, client, model_id, ticker)
    checks = validation(app.data_dir, market, lang)
    names = NAMES.get(lang, NAMES["en"])
    dim_list = [{"key": k, "name": names[k], **dims[k], "validated": checks[k]} for k in DIMS]
    # only dimensions with a history test count toward the total; untested ones are shown for reference
    # until stockproof has checked them (news, announcements, earnings quality, policy signals)
    counts = lambda k: checks[k]["tested"] and not checks[k].get("info_only")
    ov = overall({k: v for k, v in dims.items() if counts(k)})
    ov["counted"] = [k for k in DIMS if counts(k) and dims[k].get("score") is not None]
    name = d.get("name")
    if not name or name == ticker:                     # not followed yet: take the name from the screen
        saved = screener.load_latest(app.data_dir) or {}
        name = next((r.get("name") for r in saved.get("results", []) if r.get("ticker") == ticker), name)
    out = {"ticker": ticker, "name": name, "day": day, "market": market,
           "overall": {**ov, "label_text": LABELS.get(lang, LABELS["en"])[ov["label"]]},
           "dimensions": dim_list, "evidence": items, "synthesis": synth,
           "screen": screen_rec, "disclaimer": DISCLAIMER.get(lang, DISCLAIMER["en"])}
    out = json.loads(json.dumps(out, ensure_ascii=False, default=_jsonable))
    if model_id and synth is not None:
        store.conn.execute("INSERT OR REPLACE INTO scorecards VALUES (?, ?, ?, ?, ?, ?)",
                           (*key, json.dumps(out, ensure_ascii=False), dt.datetime.now().isoformat(timespec="seconds")))
        store.conn.commit()
    return out


def _jsonable(v):
    if isinstance(v, (pd.Timestamp, dt.date)):
        return v.isoformat()
    try:
        f = float(v)
        return f if math.isfinite(f) else None
    except (TypeError, ValueError):
        return str(v)


def refresh_data(app, store, client, model_id: str, ticker: str, lang: str, log=print) -> list[str]:
    """Fetch news (+ LLM scores), the latest earnings reading, prices and announcements for one stock.
    Returns problems (non-fatal); raises on a rejected key / no balance."""
    from stockproof import core, quotes
    problems = []
    name = app.name_of(ticker)
    res = core.scan_ticker(store, client, model_id, ticker, name, app.per_ticker, lang)
    if res.get("error"):
        problems.append(f"news: {res['error']}")
    if res.get("fatal"):
        raise RuntimeError("the LLM provider rejected the key or the balance is too low")
    sec = None
    if not cn.is_cn(ticker):
        from stockproof.sec import SECCache, SECError, contact
        try:
            contact()
            c = SECCache(app.data_dir)
            sec = (c, c.ticker_map())
        except SECError as e:
            problems.append(f"earnings: {e}")
    row = core.earnings_any(store, app.data_dir, client, model_id, ticker, lang,
                            name=name if name != ticker else None, sec=sec)
    problems += [f"earnings: {e}" for e in row.get("errors", [])]
    if row.get("fatal"):
        raise RuntimeError("the LLM provider rejected the key or the balance is too low")
    try:
        quotes.update(app.data_dir, ticker)
    except Exception as e:
        problems.append(f"prices: {type(e).__name__}")
    if cn.is_cn(ticker):
        st = announcements.refresh(store, client, model_id, [ticker], {ticker: name}, lang, days=90,
                                   max_reads=6, log=lambda m: problems.append(m.strip()))
        if st.get("errors"):
            problems.append("announcements: some unavailable")
    return problems


# ---------------------------------------------------------------- output

def text(card: dict, lang: str = "zh") -> str:
    zh = lang == "zh"
    ov = card["overall"]
    head = f"{card['ticker']} {card.get('name') or ''} · " + (
        f"{ov['score']:.0f}/100 {ov['label_text']}" if ov.get("score") is not None else ov["label_text"])
    lines = [head]
    for dm in card["dimensions"]:
        s = "  —" if dm.get("score") is None else f"{dm['score']:4.0f}"
        mark = ("✓" if dm["validated"]["useful"] else "·") if dm["validated"]["tested"] else "?"
        if not dm["validated"]["tested"] or dm["validated"].get("info_only"):
            extra_tag = "（参考，不计入总分）" if zh else " (reference, not in total)"
        else:
            extra_tag = ""
        extra = ""
        if dm["key"] == "fundamentals" and dm.get("rank"):
            extra = f"全市场第 {dm['rank']}/{dm['of']}" if zh else f"rank {dm['rank']}/{dm['of']}"
        elif dm["key"] == "news" and dm.get("n") is not None:
            extra = f"{dm['n']} 条" if zh else f"{dm['n']} headlines"
        elif dm["key"] == "filings" and dm.get("n"):
            extra = (f"{dm['n']} 条重要公告（{dm.get('events', dm['n'])} 类事件）" if zh else
                     f"{dm['n']} important ({dm.get('events', dm['n'])} kinds of event)")
        elif dm["key"] == "report" and dm.get("filed"):
            extra = f"{dm['filed']} 语气 {dm['tone']:+.1f}" if zh else f"{dm['filed']} tone {dm['tone']:+.1f}"
        elif dm["key"] == "policy" and dm.get("sw"):
            extra = (f"{dm['sw']}：近 90 天 {dm['n']} 条新举措" if zh else f"{dm['sw']}: {dm['n']} new measures in 90 days")
            if dm.get("items"):
                extra += f" · {dm['items'][0]['date']} {dm['items'][0]['quote']}"
        elif dm["key"] == "quality" and dm.get("reason"):
            extra = dm["reason"] if len(dm["reason"]) <= 70 else dm["reason"][:68] + "…"
        lines.append(f"   {dm['name']:6s} {s}  {mark} {extra}{extra_tag}")
    sy = card.get("synthesis") or {}
    if sy.get("summary"):
        lines.append("   " + sy["summary"])
    for label, key in (("+ ", "positives"), ("- ", "risks")):
        for p in sy.get(key, []):
            lines.append(f"   {label}{p['text']} " + "".join(f"[{i}]" for i in p["evidence"]))
    return "\n".join(lines)


def save_batch(data_dir: str, cards: list[dict]) -> str:
    d = os.path.join(data_dir, "screens")
    os.makedirs(d, exist_ok=True)
    day = clock.today().isoformat()
    path = os.path.join(d, f"scorecards_{day}.json")
    old = {}
    if os.path.exists(path):
        try:
            with open(path, encoding="utf-8") as f:
                old = {c["ticker"]: c for c in json.load(f)}
        except (OSError, ValueError, KeyError, TypeError):
            old = {}
    for c in cards:
        old[c["ticker"]] = c
    with open(path, "w", encoding="utf-8") as f:
        json.dump(list(old.values()), f, ensure_ascii=False)
    return path


def load_batch(data_dir: str) -> list[dict]:
    d = os.path.join(data_dir, "screens")
    if not os.path.isdir(d):
        return []
    files = sorted(f for f in os.listdir(d) if f.startswith("scorecards_") and f.endswith(".json"))
    if not files:
        return []
    with open(os.path.join(d, files[-1]), encoding="utf-8") as f:
        return json.load(f)
