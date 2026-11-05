"""
AI research team: five analysts, a bull/bear debate, and a portfolio manager with a risk check.

  analysts (fundamentals, technicals, news, capital flow, policy)
      each sees only its own numbered evidence (F1.., T1.., N1.., C1.., P1..) and must cite it
  bull and bear researchers
      the strongest case each way from the analysts' cited points
  portfolio manager + risk
      stance, confidence, horizon, a plan with levels taken from the computed zones, risks, and what
      would change the view

Rules enforced in code, not left to the model:
  * points that cite no valid evidence are dropped;
  * confidence is capped at "low" unless a dimension that PASSED a history test supports the stance
    (none has so far, so the team is honest that its views are opinions, not tested edges);
  * plan price levels must be within 1% of a computed zone or the 52-week high / low, otherwise removed;
  * every call is written to an append-only forward log (database triggers refuse UPDATE and DELETE)
    before the outcome is known, and scored after its horizon against the market.
"""

from __future__ import annotations

import datetime as dt
import json
import uuid
from concurrent.futures import ThreadPoolExecutor

import pandas as pd

from stockproof import clock, cn, quotes

VERSION = 1
HIT_MIN = 0.005          # excess return a bullish/bearish call must beat to count as a hit (one round trip of costs)
ANALYSTS = ["fundamentals", "technical", "news", "flow", "policy"]
PREFIX = {"fundamentals": "F", "technical": "T", "news": "N", "flow": "C", "policy": "P"}
NAMES = {"zh": {"fundamentals": "基本面分析师", "technical": "技术面分析师", "news": "新闻分析师", "flow": "资金面分析师",
                "policy": "政策分析师", "bull": "看多研究员", "bear": "看空研究员", "pm": "组合经理（含风控）"},
         "en": {"fundamentals": "Fundamentals analyst", "technical": "Technical analyst", "news": "News analyst",
                "flow": "Capital-flow analyst", "policy": "Policy analyst", "bull": "Bull researcher",
                "bear": "Bear researcher", "pm": "Portfolio manager (with risk check)"}}
STANCES = ("bullish", "bearish", "neutral", "no_view")
CONF = ("low", "medium", "high")

SCHEMA = """
CREATE TABLE IF NOT EXISTS team_calls (
    id TEXT PRIMARY KEY, ticker TEXT, made_at TEXT, day TEXT, price REAL, stance TEXT, confidence TEXT,
    horizon INTEGER, model TEXT, lang TEXT, result TEXT);
CREATE TABLE IF NOT EXISTS team_scores (
    call_id TEXT PRIMARY KEY, scored_at TEXT, end_day TEXT, ret REAL, bench REAL, excess REAL, hit INTEGER);
CREATE TRIGGER IF NOT EXISTS team_calls_append_only_u BEFORE UPDATE ON team_calls
    BEGIN SELECT RAISE(ABORT, 'the forward log is append-only'); END;
CREATE TRIGGER IF NOT EXISTS team_calls_append_only_d BEFORE DELETE ON team_calls
    BEGIN SELECT RAISE(ABORT, 'the forward log is append-only'); END;
"""


# ---------------------------------------------------------------- evidence for each analyst
def _item(kind: str, title: str, text: str, date: str | None = None, link: str | None = None) -> dict:
    return {"kind": kind, "title": str(title)[:160], "text": str(text)[:900], "date": date, "link": link}


def gather(app, store, client, model_id, ticker: str, lang: str = "zh") -> dict:
    """Numbered evidence and the history-test status per analyst, from saved data (no fresh downloads
    except the small 龙虎榜 / margin queries)."""
    from stockproof import flows, margin, scorecard, ta
    zh = lang == "zh"
    card = scorecard.build(app, store, client, model_id, ticker, lang)
    dims = {d["key"]: d for d in card["dimensions"]}
    ev = card.get("evidence") or []
    out = {a: {"items": [], "validated": []} for a in ANALYSTS}

    # fundamentals: screen rank, latest report, earnings quality
    f = dims.get("fundamentals", {})
    if f.get("score") is not None:
        txt = (f"market rank {f.get('rank')}/{f.get('of')}, percentiles {json.dumps(f.get('percentiles') or {}, ensure_ascii=False)}"
               if f.get("rank") else f"earnings surprise SUE {f.get('sue')}")
        out["fundamentals"]["items"].append(_item("computed", "fundamentals score " + str(round(f["score"])), txt))
    rep = dims.get("report", {})
    if rep.get("tone") is not None:
        out["fundamentals"]["items"].append(_item("computed", "latest report reading",
                                                  f"tone {rep.get('tone')}, guidance {rep.get('guidance')}. {rep.get('summary') or ''}",
                                                  rep.get("filed"), rep.get("url")))
    q = dims.get("quality", {})
    if q.get("reason"):
        out["fundamentals"]["items"].append(_item("computed", "earnings quality", q["reason"]))
    out["fundamentals"]["items"] += [_item(e["kind"], e.get("title") or "", e.get("text") or "", e.get("date"), e.get("link"))
                                     for e in ev if e["kind"] == "report"]
    out["fundamentals"]["validated"] = [{"dim": k, **dims[k]["validated"]} for k in ("fundamentals", "report", "quality") if k in dims]

    # technicals
    bars = quotes.load_bars(app.data_dir, ticker)
    if len(bars) < 60:                                     # a stock not followed yet: fetch its prices once
        try:
            quotes.update(app.data_dir, ticker)
            bars = quotes.load_bars(app.data_dir, ticker)
        except Exception:
            pass
    t = ta.analyze(bars, lang) if len(bars) else {"error": "no prices"}
    out["technical"]["facts"] = t
    if not t.get("error"):
        out["technical"]["items"].append(_item("computed", f"trend on {t['date']}",
                                               json.dumps(t["trend"], ensure_ascii=False, default=str)))
        for kind in ("nearest_support", "nearest_resistance"):
            z = t.get(kind)
            if z:
                out["technical"]["items"].append(_item("computed", kind.replace("_", " "),
                                                       f"zone {z['low']}–{z['high']}, touched {z['touches']} times, "
                                                       f"since {z.get('since')}, distance {z.get('distance')}"))
        out["technical"]["items"].append(_item("computed", "52-week range",
                                               f"close {t['close']}, 52w high {t['high_52w']}, low {t['low_52w']}, "
                                               f"from high {t['from_high_52w']:+.1%}"))
        for s in t.get("signals", [])[:6]:
            out["technical"]["items"].append(_item("computed", f"signal {s['kind']} on {s['date']}", s.get("rule", ""), s["date"]))
    m = dims.get("momentum", {})
    out["technical"]["validated"] = [{"dim": "momentum", **m.get("validated", {})},
                                     {"dim": "chart signals", "tested": False, "useful": False,
                                      "text": "图形信号尚未在实验室检验" if zh else "chart signals not tested in the lab yet"}]

    # news and announcements
    for e in ev:
        if e["kind"] in ("news", "announcement"):
            out["news"]["items"].append(_item(e["kind"], e.get("title") or "", e.get("text") or "", e.get("date"), e.get("link")))
    n = dims.get("news", {})
    if n.get("mood") is not None:
        out["news"]["items"].insert(0, _item("computed", "14-day news mood", f"{n['mood']:+.2f} from {n.get('n')} relevant headlines"))
    out["news"]["validated"] = [{"dim": k, **dims[k]["validated"]} for k in ("news", "filings") if k in dims]

    # capital flow (A-shares)
    info = cn.parse(ticker)
    if info and info["market"] in ("SH", "SZ"):
        try:
            sh = flows.stock_holders(app.data_dir, ticker, quarters=1, lang=lang, fetch=False)
            if not sh.get("error"):
                out["flow"]["items"].append(_item("computed", "smart money in the top-10 tradable holders", sh["summary"]))
        except Exception:
            pass
        try:
            mg = margin.stock(app.data_dir, ticker, 20, fetch=False)
            if mg and mg.get("available"):
                out["flow"]["items"].append(_item("computed", "margin financing balance (20 days)",
                                                  f"{mg['from']} to {mg['to']}: change {mg['change'] / 1e8:+.2f}亿 ({mg['change_pct']:+.1%})"))
        except Exception:
            pass
        for r in flows.dragon_tiger(app.data_dir, ticker, days=30, fetch=True)[:4]:
            out["flow"]["items"].append(_item("computed", f"龙虎榜 {r['day']}",
                                              f"{r.get('reason')}; {r.get('note')}; net buy {r.get('net_buy')}; "
                                              f"institutions net {r.get('inst_net')}", r["day"]))
        ht = flows.history_tests(app.data_dir, log=lambda *a: None) if hasattr(flows, "history_tests") else None
        if ht:
            txt = "; ".join(f"{c} {a}: {100 * (x['ann'] or 0):+.1f}%/yr t={x['t']:.1f}" for c, r in ht["results"].items()
                            for a, x in r.items() if x.get("t") is not None)
            out["flow"]["validated"].append({"dim": "smart money", "tested": True,
                                             "useful": any((x.get("ann") or 0) > 0 and (x.get("t") or 0) >= 2
                                                           for r in ht["results"].values() for x in r.values()),
                                             "text": "跟买公开披露的持仓变化：" + txt if zh else "following disclosed moves: " + txt})
    if not out["flow"]["validated"]:
        out["flow"]["validated"].append({"dim": "capital flow", "tested": False, "useful": False,
                                         "text": "尚未检验" if zh else "not tested"})

    # policy
    p = dims.get("policy", {})
    for it in (p.get("items") or [])[:5]:
        out["policy"]["items"].append(_item("policy", it.get("title") or it.get("industry") or "新闻联播",
                                            json.dumps({k: it.get(k) for k in ("stance", "strength", "kind", "quote")},
                                                       ensure_ascii=False), it.get("day") or it.get("date")))
    out["policy"]["validated"] = [{"dim": "policy", **(p.get("validated") or dims.get("policy", {}).get("validated") or {})}]

    for a in ANALYSTS:                                       # give every item its id
        for i, it in enumerate(out[a]["items"], 1):
            it["id"] = f"{PREFIX[a]}{i}"
    return {"card": card, "analysts": out, "technical": t, "name": card.get("name") or ticker}


# ---------------------------------------------------------------- the prompts
def _lang_name(lang: str) -> str:
    return "Simplified Chinese" if lang == "zh" else "English"


def _ask(question: str | None) -> str:
    return (f"The user asked the team: \"{question.strip()[:400]}\". Address it where your evidence allows; say plainly "
            "when the evidence can't answer it.\n") if question and question.strip() else ""


def analyst_prompt(role: str, name: str, ticker: str, items: list[dict], validated: list[dict], lang: str,
                   question: str | None = None) -> str:
    focus = {"fundamentals": "business results, growth, profitability and earnings quality",
             "technical": "trend, support/resistance zones and chart signals (describe; don't forecast)",
             "news": "what recent news and announcements say about the company",
             "flow": "who holds and trades the stock: national team, funds, northbound, margin, 龙虎榜",
             "policy": "government policy signals for the stock's industry"}[role]
    lines = [f"[{it['id']}] ({it['kind']}, {it.get('date') or '?'}) {it['title']} — {it['text']}" for it in items]
    return (f"You are the {role} analyst in a research team looking at {name} ({ticker}). Your area: {focus}.\n"
            + _ask(question) +
            "Use ONLY the evidence below and cite it by id. Do not invent facts or numbers.\n"
            "Evidence:\n" + ("\n".join(lines) or "(none)") + "\n\n"
            "History tests of this area (from stockproof's lab; untested = opinion only):\n"
            + json.dumps(validated, ensure_ascii=False) + "\n\n"
            "Reply ONLY with JSON:\n"
            f'{{"view": "bullish | bearish | neutral", "strength": 0 to 1,\n'
            f' "points": [{{"text": "short, in {_lang_name(lang)}", "evidence": ["{PREFIX[role]}1"]}}] (at most 4),\n'
            f' "risks": [{{"text": "short, in {_lang_name(lang)}", "evidence": ["..."]}}] (at most 3),\n'
            f' "unknowns": ["what the evidence does not tell, in {_lang_name(lang)}"] (at most 2)}}\n'
            "If there is little or no evidence, say neutral with strength 0.")


def debate_prompt(side: str, name: str, ticker: str, reports: dict, lang: str, question: str | None = None) -> str:
    return (f"You are the {side} researcher for {name} ({ticker}). " + _ask(question) + "Build the strongest honest {side} case from the "
            "analysts' cited points below, and name the weakest point of the other side. Cite evidence ids only "
            "from the analysts' points. No new facts.\n"
            "Analyst reports:\n" + json.dumps(reports, ensure_ascii=False) + "\n\n"
            "Reply ONLY with JSON:\n"
            f'{{"case": [{{"text": "short, in {_lang_name(lang)}", "evidence": ["T1"]}}] (at most 4),\n'
            f' "other_side_weakest": "one sentence in {_lang_name(lang)}"}}')


def pm_prompt(name: str, ticker: str, reports: dict, bull: dict, bear: dict, validated: dict, tech: dict,
              record: dict, lang: str, question: str | None = None) -> str:
    levels = {k: tech.get(k) for k in ("close", "nearest_support", "nearest_resistance", "high_52w", "low_52w")} \
        if not tech.get("error") else {}
    return (f"You are the portfolio manager of a research team on {name} ({ticker}), with the risk manager's duties.\n"
            + _ask(question) + ("Your summary must answer that question first.\n" if question else "") +
            "Decide a VIEW, not an order. Weigh the analysts and the debate. Rules:\n"
            "- Areas whose history test did not pass are opinions; say so, and don't let them alone justify confidence.\n"
            "- Price levels in the plan must be taken from these computed levels: "
            + json.dumps(levels, ensure_ascii=False, default=str) + "\n"
            "- Cite evidence ids from the analysts. Call explanations hypotheses.\n"
            "- 'no_view' is a valid answer when the evidence is thin or conflicting.\n"
            "Analysts: " + json.dumps(reports, ensure_ascii=False) + "\n"
            "Bull: " + json.dumps(bull, ensure_ascii=False) + "\nBear: " + json.dumps(bear, ensure_ascii=False) + "\n"
            "History tests: " + json.dumps(validated, ensure_ascii=False) + "\n"
            "This team's scored track record so far: " + json.dumps(record, ensure_ascii=False) + "\n\n"
            "Reply ONLY with JSON:\n"
            f'{{"stance": "bullish | bearish | neutral | no_view", "confidence": "low | medium | high",\n'
            f' "horizon_days": 20 or 60, "summary": "3 sentences in {_lang_name(lang)}",\n'
            f' "reasons": [{{"text": "in {_lang_name(lang)}", "evidence": ["F1"]}}] (at most 4),\n'
            f' "plan": [{{"if": "condition in {_lang_name(lang)} using the computed levels", "level": number or null,\n'
            f'            "then": "what that would mean, in {_lang_name(lang)} (not an order)"}}] (at most 3),\n'
            f' "risks": [{{"text": "in {_lang_name(lang)}", "evidence": ["..."]}}] (at most 4),\n'
            f' "would_change_view": ["in {_lang_name(lang)}"] (at most 3)}}')


# ---------------------------------------------------------------- cleaning what the model says
def _cite(points, valid: set, n: int = 4) -> list[dict]:
    out = []
    for p in (points or [])[:n]:
        if not isinstance(p, dict) or not p.get("text"):
            continue
        refs = [str(x).strip().upper() for x in (p.get("evidence") or []) if str(x).strip().upper() in valid]
        if refs:
            out.append({"text": str(p["text"])[:300], "evidence": refs})
    return out


def _view(data: dict, valid: set) -> dict:
    v = data.get("view") if data.get("view") in ("bullish", "bearish", "neutral") else "neutral"
    try:
        s = max(0.0, min(1.0, float(data.get("strength", 0))))
    except (TypeError, ValueError):
        s = 0.0
    pts = _cite(data.get("points"), valid)
    if not pts:
        v, s = "neutral", 0.0                                  # nothing citable: no view
    return {"view": v, "strength": s, "points": pts, "risks": _cite(data.get("risks"), valid, 3),
            "unknowns": [str(x)[:200] for x in (data.get("unknowns") or [])][:2]}


def _levels_ok(level, tech: dict) -> bool:
    if level is None:
        return True
    try:
        x = float(level)
    except (TypeError, ValueError):
        return False
    refs = [tech.get("high_52w"), tech.get("low_52w"), tech.get("close")]
    for z in tech.get("zones") or []:
        refs += [z["low"], z["high"], z["mid"]]
    return any(r and abs(x / float(r) - 1) <= 0.01 for r in refs)


def _supports(stance: str, analysts: dict, validated: dict) -> list[str]:
    """Areas that passed a history test AND lean the same way as the stance."""
    want = {"bullish": "bullish", "bearish": "bearish"}.get(stance)
    if not want:
        return []
    return [a for a in ANALYSTS if analysts[a]["view"] == want and any(v.get("useful") for v in validated.get(a, []))]


# ---------------------------------------------------------------- the run
def run(app, store, client, model_id: str, ticker: str, lang: str = "zh", log=print, force: bool = False,
        question: str | None = None) -> dict:
    zh = lang == "zh"
    question = (question or "").strip()[:400] or None
    store.conn.executescript(SCHEMA)
    for (raw,) in store.conn.execute("SELECT result FROM team_calls WHERE ticker=? AND day=? AND lang=? ORDER BY made_at DESC",
                                     (ticker, clock.today().isoformat(), lang)).fetchall():
        old = json.loads(raw)
        if (old.get("question") or None) == question and not force:   # same question today: no new log entry
            return {**old, "cached": True}
    g = gather(app, store, client, model_id, ticker, lang)
    name, tech = g["name"], g["technical"]
    validated = {a: g["analysts"][a]["validated"] for a in ANALYSTS}
    all_ids = {it["id"] for a in ANALYSTS for it in g["analysts"][a]["items"]}

    def one(a):
        items = g["analysts"][a]["items"]
        if not items:
            return a, {"view": "neutral", "strength": 0.0, "points": [], "risks": [], "unknowns":
                       ["没有这方面的数据" if zh else "no data in this area"]}
        data = client.chat_json(analyst_prompt(a, name, ticker, items, validated[a], lang, question))
        return a, _view(data, {it["id"] for it in items})
    log("  analysts ...")
    with ThreadPoolExecutor(max_workers=5) as ex:
        analysts = dict(ex.map(one, ANALYSTS))
    reports = {a: {"view": r["view"], "strength": r["strength"], "points": r["points"], "risks": r["risks"]}
               for a, r in analysts.items()}
    log("  debate ...")
    with ThreadPoolExecutor(max_workers=2) as ex:
        bull_raw, bear_raw = ex.map(lambda s: client.chat_json(debate_prompt(s, name, ticker, reports, lang, question)),
                                    ("bull", "bear"))
    bull = {"case": _cite(bull_raw.get("case"), all_ids), "other_side_weakest": str(bull_raw.get("other_side_weakest", ""))[:300]}
    bear = {"case": _cite(bear_raw.get("case"), all_ids), "other_side_weakest": str(bear_raw.get("other_side_weakest", ""))[:300]}
    log("  portfolio manager ...")
    record = track_record(store, lang)["summary"]
    pm = client.chat_json(pm_prompt(name, ticker, reports, bull, bear, validated, tech, record, lang, question))
    stance = pm.get("stance") if pm.get("stance") in STANCES else "no_view"
    conf = pm.get("confidence") if pm.get("confidence") in CONF else "low"
    support = _supports(stance, analysts, validated)
    capped = conf != "low" and stance in ("bullish", "bearish") and not support
    if capped:
        conf = "low"
    try:
        horizon = 60 if int(pm.get("horizon_days", 20)) >= 40 else 20
    except (TypeError, ValueError):
        horizon = 20
    plan = []
    for p in (pm.get("plan") or [])[:3]:
        if isinstance(p, dict) and p.get("if") and _levels_ok(p.get("level"), tech if not tech.get("error") else {}):
            plan.append({"if": str(p["if"])[:240], "level": p.get("level"), "then": str(p.get("then", ""))[:240]})
    final = {"stance": stance, "confidence": conf, "horizon_days": horizon, "summary": str(pm.get("summary", ""))[:800],
             "reasons": _cite(pm.get("reasons"), all_ids), "plan": plan, "risks": _cite(pm.get("risks"), all_ids),
             "would_change_view": [str(x)[:200] for x in (pm.get("would_change_view") or [])][:3],
             "confidence_capped": capped, "supported_by_tested": support}
    final["cap_note"] = ((("置信度被限制为“低”：支持这个观点的方面都还没有通过历史检验，只能算观点。" if zh else
                           "Confidence capped at low: no area supporting this view has passed a history test.")
                          if capped else "") or
                         ("" if support else ("目前没有任何方面通过了历史检验，所以这是有依据的观点，不是经过验证的优势。" if zh else
                                               "No area has passed a history test yet: a reasoned view, not a tested edge.")))
    evidence = {it["id"]: it for a in ANALYSTS for it in g["analysts"][a]["items"]}
    price = tech.get("close") if not tech.get("error") else None
    out = {"ticker": ticker, "name": name, "question": question, "made_at": dt.datetime.now().isoformat(timespec="seconds"),
           "day": clock.today().isoformat(), "price": price, "price_date": tech.get("date"), "model": model_id,
           "version": VERSION, "analysts": analysts, "roles": NAMES.get(lang, NAMES["en"]), "bull": bull, "bear": bear,
           "final": final, "validated": validated, "evidence": evidence,
           "disclaimer": ("这是 AI 团队基于公开数据的观点，不是投资建议，也不是买卖指令。每次判断都记入不可修改的前瞻日志，到期后用实际涨跌打分。"
                          if zh else "An AI team's view from public data: not advice and not an order. Every call goes "
                          "into an append-only forward log and is scored against the market after its horizon.")}
    out["call_id"] = f"{out['day']}-{ticker}-{uuid.uuid4().hex[:6]}"
    record_call(store, out, lang)
    return out


# ---------------------------------------------------------------- the forward log
def record_call(store, res: dict, lang: str) -> str:
    store.conn.executescript(SCHEMA)
    cid = res.get("call_id") or f"{res['day']}-{res['ticker']}-{uuid.uuid4().hex[:6]}"
    store.conn.execute("INSERT INTO team_calls VALUES (?,?,?,?,?,?,?,?,?,?,?)",
                       (cid, res["ticker"], res["made_at"], res["day"], res["price"], res["final"]["stance"],
                        res["final"]["confidence"], res["final"]["horizon_days"], res["model"], lang,
                        json.dumps(res, ensure_ascii=False, default=str)))
    store.conn.commit()
    return cid


def score_calls(store, data_dir: str, fetch: bool = True) -> int:
    """Score every call whose horizon has passed: stock vs its market index from the close of the day it
    was made to `horizon` trading days later. Writes to team_scores; calls are never touched."""
    store.conn.executescript(SCHEMA)
    rows = store.conn.execute(
        "SELECT id, ticker, day, stance, horizon FROM team_calls c WHERE id NOT IN (SELECT call_id FROM team_scores) "
        "AND stance IN ('bullish','bearish','neutral') AND made_at = (SELECT MIN(made_at) FROM team_calls x "
        "WHERE x.ticker = c.ticker AND x.day = c.day)").fetchall()       # one scored call per stock per day
    n = 0
    for cid, tk, day, stance, horizon in rows:
        try:
            if fetch:
                quotes.update(data_dir, tk)
            px = quotes.load(data_dir, tk)
            bm_tk = quotes.BENCH[quotes.market_of(tk)]
            if fetch:
                quotes.update(data_dir, bm_tk)
            bm = quotes.load(data_dir, bm_tk)
        except Exception:
            continue
        px, bm = px.loc[day:], bm.loc[day:]
        if len(px) <= horizon or len(bm) <= horizon:
            continue
        r = float(px.iloc[horizon] / px.iloc[0] - 1)
        end = px.index[horizon]
        b = float(bm.loc[:end].iloc[-1] / bm.iloc[0] - 1)
        ex = r - b
        # a hit has to beat one round trip of costs: a 0.1% "win" isn't worth trading
        hit = int(ex > HIT_MIN) if stance == "bullish" else int(ex < -HIT_MIN) if stance == "bearish" else int(abs(ex) < 0.05)
        store.conn.execute("INSERT INTO team_scores VALUES (?,?,?,?,?,?,?)",
                           (cid, dt.datetime.now().isoformat(timespec="seconds"), end.date().isoformat(), r, b, ex, hit))
        n += 1
    store.conn.commit()
    return n


def track_record(store, lang: str = "zh", limit: int = 20) -> dict:
    zh = lang == "zh"
    store.conn.executescript(SCHEMA)
    df = pd.read_sql_query("SELECT c.id, c.ticker, c.day, c.made_at, c.stance, c.confidence, c.horizon, c.price, "
                           "json_extract(c.result, '$.name') AS name, json_extract(c.result, '$.question') AS question, "
                           "s.excess, s.hit, s.end_day FROM team_calls c LEFT JOIN team_scores s ON s.call_id = c.id "
                           "ORDER BY c.made_at DESC", store.conn)
    df["counted"] = ~df.duplicated(["ticker", "day"], keep="last")         # the earliest call of the day counts
    scored = df[df["counted"]].dropna(subset=["hit"])
    counted = int(df["counted"].sum())
    summ = {"calls": counted, "discussions": int(len(df)), "scored": int(len(scored)), "pending": counted - int(len(scored))}
    if len(scored):
        summ["hit_rate"] = float(scored["hit"].mean())
        summ["avg_excess_when_bullish"] = float(scored.loc[scored["stance"] == "bullish", "excess"].mean()) \
            if (scored["stance"] == "bullish").any() else None
        summ["by_confidence"] = {c: {"n": int(len(g)), "hit_rate": float(g["hit"].mean())}
                                 for c, g in scored.groupby("confidence")}
        recent = scored.head(20)
        summ["decaying"] = bool(len(scored) >= 30 and len(recent) >= 20 and recent["hit"].mean() < scored["hit"].mean() - 0.15)
    summ["note"] = (("命中率基于到期后的实际超额收益（相对大盘），而且要跑赢（或跑输）大盘超过 0.5%（一次买卖的成本）才算命中；样本还少，仅供参考。" if zh else
                     "Hit rate from realised excess returns after each horizon; a hit must beat the market by more than "
                     "0.5% (one round trip of costs); small sample.") if len(scored) else
                    ("还没有到期的判断，暂无战绩。" if zh else "No call has reached its horizon yet."))
    return {"summary": summ, "recent": json.loads(df.head(limit).to_json(orient="records", force_ascii=False))}


def resolve(app, text: str) -> str | None:
    """Find the stock a free-text request is about: a code (600519, 002230.SZ, 00700.HK, NVDA) or a name
    (科大讯飞, 宁德时代) from the watchlist and the whole-market A-share list."""
    import os
    import re
    t = str(text or "")
    m = re.search(r"(?<!\d)(\d{6})(?:\.(SH|SZ|BJ))?(?!\d)", t, re.I) or re.search(r"(?<!\d)(\d{4,5})\.HK", t, re.I)
    if m:
        info = cn.parse(m.group(0))
        if info:
            return info["symbol"]
    names = {}
    for tk, nm in (getattr(app, "settings", {}).get("names") or {}).items():
        if nm:
            names[str(nm)] = tk
    for tk in getattr(app, "settings", {}).get("watchlist", []):
        nm = app.name_of(tk) if hasattr(app, "name_of") else None
        if nm and nm != tk:
            names[nm] = tk
    d = os.path.join(app.data_dir, "cn")
    if os.path.isdir(d):
        files = sorted(f for f in os.listdir(d) if re.fullmatch(r"research_yjbb2_\d{8}\.json", f))
        if files:
            try:
                with open(os.path.join(d, files[-1]), encoding="utf-8") as fh:
                    for r in json.load(fh):
                        if r.get("name") and r.get("code"):
                            names.setdefault(str(r["name"]).replace(" ", ""), (cn.parse(r["code"]) or {}).get("symbol"))
            except (OSError, ValueError):
                pass
    hits = [(len(nm), tk) for nm, tk in names.items() if tk and len(nm) >= 2 and nm in t.replace(" ", "")]
    if hits:
        return max(hits)[1]
    for w in re.findall(r"\b[A-Z]{1,5}(?:[.-][A-Z])?\b", t):
        if w in getattr(app, "settings", {}).get("watchlist", []):
            return w
        try:
            from stockproof.sec import SECCache
            if w.replace(".", "-") in (SECCache(app.data_dir).cached("company_tickers.json") and
                                       {str(r["ticker"]).upper() for r in SECCache(app.data_dir).cached("company_tickers.json").values()} or set()):
                return w
        except Exception:
            pass
    return None
