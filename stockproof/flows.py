"""
Smart-money map (A-shares): what the national team, social-security funds, insurers, QFII, northbound
money (香港中央结算) and mutual funds did each quarter, from every listed company's top-10 tradable
shareholders.

Source: Eastmoney's whole-market 十大流通股东 table (one request per quarter, ~56k rows), cached per
quarter. Every row carries the company's announcement date (公告日), so a holding counts as known
only from that day: nothing here peeks at reports that weren't out yet.

Honest limits, always stated in the output:
  * Only the top-10 tradable holders are disclosed, quarterly, up to ~4 months late. Small positions
    and intra-quarter trades are invisible.
  * Daily northbound flows by stock are no longer published (since Aug 2024); the quarterly 香港中央结算
    holding is the only per-stock northbound number.
  * "主力资金" daily flows are estimates from order sizes, not who traded; labelled as such.
"""

from __future__ import annotations

import datetime as dt
import os

import pandas as pd

from stockproof import cn

# (key, Chinese label, English label, name keywords). Checked in order; the first match wins.
CATEGORIES = [
    ("national", "国家队", "National team",
     ["中央汇金", "中国证券金融股份", "中证金融资产管理计划", "梧桐树投资平台", "国新投资", "国新发展投资",
      "国新宏盛", "国新央企运营", "诚通金控", "中国诚通", "国有企业结构调整基金", "国有企业混合所有制改革基金"]),
    ("social", "社保/养老金", "Social security & pensions",
     ["全国社保基金", "全国社会保障基金", "社保基金", "基本养老保险基金", "养老金产品"]),
    ("northbound", "北向资金（香港中央结算）", "Northbound (HKSCC)", ["香港中央结算有限公司"]),
    ("insurance", "保险资金", "Insurers", ["人寿保险", "财产保险", "保险股份有限公司", "保险有限公司", "保险资产管理"]),
    ("qfii", "QFII/外资机构", "QFII", []),
    ("fund", "公募基金", "Mutual funds", ["证券投资基金", "交易型开放式"]),
]
LABEL = {k: (zh, en) for k, zh, en, _ in CATEGORIES}
TYPE_HINT = {"QFII": "qfii", "保险产品": "insurance", "全国社保基金": "social", "基本养老基金": "social",
             "证券投资基金": "fund"}

ACTION = {"新进": "new", "增加": "add", "减少": "reduce", "不变": "same"}
COLS = {"股东名称": "holder", "股东类型": "htype", "股票代码": "code", "股票简称": "name", "报告期": "period",
        "期末持股-数量": "shares", "期末持股-数量变化": "change", "期末持股-数量变化比例": "change_pct",
        "期末持股-持股变动": "action", "期末持股-流通市值": "value", "公告日": "public"}


def classify(holder: str, htype: str = "") -> str | None:
    h = str(holder or "")
    for key, _, _, words in CATEGORIES:
        if any(w in h for w in words):
            return key
    return TYPE_HINT.get(str(htype or "").strip())


def display_name(holder: str, n: int = 26) -> str:
    """Funds are listed as '<custodian bank>-<fund>': show the fund."""
    h = str(holder or "")
    parts = h.split("-")
    if len(parts) > 1 and "银行" in parts[0]:
        h = "-".join(parts[1:])
    return h if len(h) <= n else h[:n] + "…"


def flows_dir(data_dir: str) -> str:
    d = os.path.join(data_dir, "flows")
    os.makedirs(d, exist_ok=True)
    return d


def quarter_ends(n: int = 8, today: dt.date | None = None) -> list[str]:
    """The last `n` quarter ends as YYYYMMDD, newest first (including the current, still-filling one)."""
    today = today or dt.date.today()
    out, y, m = [], today.year, today.month
    q_end = [(3, 31), (6, 30), (9, 30), (12, 31)]
    cands = [dt.date(yy, mm, dd) for yy in range(y - n // 4 - 2, y + 1) for mm, dd in q_end]
    cands = sorted((c for c in cands if c <= today), reverse=True)
    return [c.strftime("%Y%m%d") for c in cands[:n]]


def latest_quarter(today: dt.date | None = None) -> str:
    """The newest quarter whose reports are mostly out (the deadline has passed)."""
    today = today or dt.date.today()
    deadline = {"0331": (4, 30), "0630": (8, 31), "0930": (10, 31), "1231": (4, 30)}
    for q in quarter_ends(8, today):
        mm, dd = deadline[q[4:]]
        yy = int(q[:4]) + (1 if q[4:] == "1231" else 0)
        if today >= dt.date(yy, mm, dd):
            return q
    return quarter_ends(8, today)[-1]


def _normalize(df: pd.DataFrame) -> pd.DataFrame:
    df = df.rename(columns=COLS)
    keep = [c for c in COLS.values() if c in df.columns]
    df = df[keep].copy()
    df["code"] = df["code"].astype(str).str.zfill(6)
    for c in ("shares", "change", "change_pct", "value"):
        if c in df:
            df[c] = pd.to_numeric(df[c], errors="coerce")
    df["action"] = df["action"].map(ACTION).fillna(df["action"])
    df["public"] = pd.to_datetime(df["public"], errors="coerce").dt.date.astype(str)
    df["category"] = [classify(h, t) for h, t in zip(df["holder"], df.get("htype", ""))]
    return df


def holders(data_dir: str, quarter: str | None = None, fetch: bool = True, log=print) -> pd.DataFrame:
    """Every company's top-10 tradable holders for one quarter, classified. Cached; the quarter still
    being reported is re-downloaded at most once a day."""
    quarter = quarter or latest_quarter()
    p = os.path.join(flows_dir(data_dir), f"holders_{quarter}.csv")
    fresh = os.path.exists(p) and (
        dt.date.fromtimestamp(os.path.getmtime(p)) >= dt.date.today() or _complete(quarter))
    if os.path.exists(p) and (fresh or not fetch):
        df = pd.read_csv(p, dtype={"code": str})
        df["category"] = [classify(h, t) for h, t in zip(df["holder"], df.get("htype", ""))]   # rules may have improved
        return df
    if not fetch:
        return pd.DataFrame(columns=list(COLS.values()) + ["category"])
    log(f"  downloading every company's top-10 tradable holders for {quarter} (about 2 minutes) ...")
    df = _normalize(cn._ak().stock_gdfx_free_holding_detail_em(date=quarter))
    df.to_csv(p, index=False)
    return df


def download_history(data_dir: str, since: str = "2016", log=print, pause: float = 5.0) -> dict:
    """Fetch every quarter from `since` to the latest (skipping ones already saved). Safe to stop and rerun."""
    import time
    qs = sorted(q for q in quarter_ends(4 * (dt.date.today().year - int(since[:4]) + 2)) if q[:4] >= since[:4])
    done, failed = [], []
    for i, q in enumerate(qs, 1):
        p = os.path.join(flows_dir(data_dir), f"holders_{q}.csv")
        if os.path.exists(p) and _complete(q):
            continue
        for attempt in range(3):
            try:
                t0 = time.time()
                df = holders(data_dir, q, fetch=True, log=lambda *a: None)
                log(f"  [{i}/{len(qs)}] {q}: {len(df)} rows ({time.time() - t0:.0f}s)")
                done.append(q)
                break
            except Exception as e:
                log(f"  [{i}/{len(qs)}] {q}: {type(e).__name__}: {str(e)[:80]} (try {attempt + 1}/3)")
                time.sleep(20 * (attempt + 1))
        else:
            failed.append(q)
        time.sleep(pause)
    try:
        history_tests(data_dir, log=log, refresh=True)
    except Exception as e:
        log(f"  history test skipped: {type(e).__name__}")
    return {"quarters": len(qs), "downloaded": done, "failed": failed}


def _complete(quarter: str) -> bool:
    """A quarter more than ~5 months old won't get new reports."""
    end = dt.datetime.strptime(quarter, "%Y%m%d").date()
    return (dt.date.today() - end).days > 150


def _industry_map(data_dir: str) -> dict:
    import json
    import re
    d = os.path.join(data_dir, "cn")
    out = {}
    if not os.path.isdir(d):
        return out
    for f in sorted((f for f in os.listdir(d) if re.fullmatch(r"research_yjbb2_\d{8}\.json", f)))[-3:]:
        try:
            with open(os.path.join(d, f), encoding="utf-8") as fh:
                for r in json.load(fh):
                    if r.get("industry"):
                        out[r["code"]] = r["industry"]
        except (OSError, ValueError):
            continue
    return out


def _value_change(df: pd.DataFrame) -> pd.Series:
    """Approximate value of the share change at the period-end price: value × change / shares."""
    px = df["value"] / df["shares"].where(df["shares"] > 0)
    ch = df["change"].fillna(0.0)
    ch = ch.where(df["action"] != "new", df["shares"])          # a new entry: the whole position is the change
    return (ch * px).fillna(0.0)


def prev_quarter(q: str) -> str:
    y, md = int(q[:4]), q[4:]
    return {"0331": f"{y - 1}1231", "0630": f"{y}0331", "0930": f"{y}0630", "1231": f"{y}0930"}[md]


def exits(cur: pd.DataFrame, prev: pd.DataFrame, category: str | None = None) -> pd.DataFrame:
    """Positions in last quarter's top-10 that are gone this quarter, for companies that have reported.

    Inference with the 10th holder: if the old holding is larger than this quarter's 10th-largest holding,
    the holder must have sold at least the difference (otherwise it would still rank in the top 10):
    confidence 'inferred'. If it is smaller, it may simply have been pushed out by others buying:
    confidence 'possible'."""
    cols = ["code", "name", "holder", "category", "prev_shares", "tenth", "sold_at_least", "confidence", "price",
            "sold_value_at_least", "public"]
    if prev is None or prev.empty or cur.empty:
        return pd.DataFrame(columns=cols)
    p = prev if category is None else prev[prev["category"] == category]
    reported = cur.groupby("code").agg(tenth=("shares", "min"), n=("shares", "size"), public=("public", "max"),
                                      value=("value", "sum"), shares=("shares", "sum"))
    reported["price"] = reported["value"] / reported["shares"].where(reported["shares"] > 0)
    p = p[p["code"].isin(reported.index)]
    now = set(zip(cur["code"], cur["holder"]))
    gone = p[[(c, h) not in now for c, h in zip(p["code"], p["holder"])]].copy()
    # the same holding under another name (e.g. 香港中央结算有限公司 vs ...(代理人)有限公司 in A+H companies):
    # a current holder of the same company with almost the same share count is not an exit
    by_code = cur.groupby("code")["shares"].apply(list).to_dict()
    renamed = [any(abs(x - s) <= 0.02 * s for x in by_code.get(c, [])) for c, s in zip(gone["code"], gone["shares"])]
    gone = gone[[not r for r in renamed]]
    if gone.empty:
        return pd.DataFrame(columns=cols)
    gone = gone.join(reported[["tenth", "n", "public", "price"]], on="code", rsuffix="_cur")
    gone["prev_shares"] = gone["shares"]
    full = gone["n"] >= 10                                       # a short list means fewer than 10 holders shown
    gone["sold_at_least"] = (gone["prev_shares"] - gone["tenth"]).where(full & (gone["prev_shares"] > gone["tenth"]), 0.0)
    gone["confidence"] = ["inferred" if s > 0 else "possible" for s in gone["sold_at_least"]]
    gone["sold_value_at_least"] = (gone["sold_at_least"] * gone["price"]).fillna(0.0)
    gone["public"] = gone["public_cur"] if "public_cur" in gone else gone["public"]
    return gone[cols].sort_values("sold_value_at_least", ascending=False)


def upper_bound(cur: pd.DataFrame, code: str) -> float | None:
    """Anyone not in a company's top-10 tradable holders holds fewer shares than its 10th holder."""
    rows = cur[cur["code"] == code]
    return float(rows["shares"].min()) if len(rows) >= 10 else None


def money_map(data_dir: str, category: str = "national", quarter: str | None = None, as_of: str | None = None,
              top: int = 15, lang: str = "zh", fetch: bool = True, log=print) -> dict:
    """What one kind of investor did in a quarter: new / added / reduced / unchanged positions, by industry
    and by stock. `as_of` (YYYY-MM-DD) keeps only reports announced by then (point-in-time)."""
    zh = lang == "zh"
    quarter = quarter or latest_quarter()
    df = holders(data_dir, quarter, fetch, log)
    if df.empty:
        return {"error": "no holder data for this quarter yet" if not zh else "这个季度还没有股东数据"}
    if as_of:
        df = df[df["public"] <= as_of]
    sub = df[df["category"] == category].copy()
    reported = int(df["code"].nunique())
    if sub.empty:
        return {"category": category, "quarter": quarter, "reported_companies": reported, "positions": 0}
    sub["value_change"] = _value_change(sub)
    ind = _industry_map(data_dir)
    sub["industry"] = sub["code"].map(ind).fillna("其他" if zh else "other")
    # one row per stock (several entities of the same group can hold one stock)
    per = sub.groupby(["code", "name", "industry"], as_index=False).agg(
        holders=("holder", lambda s: sorted(set(s))), value=("value", "sum"), value_change=("value_change", "sum"),
        actions=("action", lambda s: sorted(set(s))), public=("public", "max"))
    per["ticker"] = per["code"].map(lambda c: (cn.parse(c) or {}).get("symbol", c))
    counts = sub["action"].value_counts().to_dict()
    by_ind = (per.groupby("industry").agg(stocks=("code", "count"), value=("value", "sum"),
                                          value_change=("value_change", "sum"))
              .sort_values("value_change", ascending=False))

    def rows(frame, n):
        return [{"ticker": r.ticker, "name": r.name, "industry": r.industry, "holders": r.holders,
                 "actions": r.actions, "value": float(r.value), "value_change": float(r.value_change),
                 "public": r.public} for r in frame.head(n).itertuples()]
    new_mask = per["actions"].map(lambda a: "new" in a)
    label = LABEL.get(category, (category, category))[0 if zh else 1]
    pq = prev_quarter(quarter)
    prev = holders(data_dir, pq, fetch=False) if os.path.exists(
        os.path.join(flows_dir(data_dir), f"holders_{pq}.csv")) else None
    ex = exits(df, prev, category) if prev is not None else None
    ex_rows = [] if ex is None else [
        {"ticker": (cn.parse(r.code) or {}).get("symbol", r.code), "name": r.name, "holder": display_name(r.holder),
         "industry": ind.get(r.code, "其他" if zh else "other"), "prev_shares": float(r.prev_shares),
         "sold_at_least": float(r.sold_at_least), "value_change": -float(r.sold_value_at_least),
         "confidence": r.confidence, "public": r.public} for r in ex.head(top * 2).itertuples()]
    return {
        "category": category, "label": label, "quarter": quarter, "as_of": as_of,
        "reported_companies": reported, "positions": int(len(sub)), "stocks": int(len(per)),
        "counts": {k: int(counts.get(k, 0)) for k in ("new", "add", "reduce", "same")},
        "total_value": float(per["value"].sum()), "net_value_change": float(per["value_change"].sum()),
        "industries": [{"industry": i, "stocks": int(r.stocks), "value": float(r.value),
                        "value_change": float(r.value_change)} for i, r in by_ind.iterrows()][:12],
        "new": rows(per[new_mask].sort_values("value", ascending=False), top),
        "added": rows(per[~new_mask & (per["value_change"] > 0)].sort_values("value_change", ascending=False), top),
        "reduced": rows(per[per["value_change"] < 0].sort_values("value_change"), top),
        "previous_quarter": pq if prev is not None else None,
        "exits": ex_rows,
        "exit_counts": None if ex is None else {"inferred": int((ex["confidence"] == "inferred").sum()),
                                                "possible": int((ex["confidence"] == "possible").sum())},
        "inferred_reduction": None if ex is None else -float(ex["sold_value_at_least"].sum()),
        "confidence_note": ("确定＝公司直接披露；推断＝用第十名门槛推出至少卖了多少（否则仍会在前十）；"
                            "可能＝跌出前十，可能卖了、也可能被别人买得更多挤出。" if zh else
                            "disclosed = reported by the company; inferred = must have sold at least this much (else it "
                            "would still rank top 10); possible = fell out of the top 10, sold or pushed out."),
        "limits": ("只覆盖十大流通股东、按季度披露、最晚滞后约 4 个月；看不到小仓位和季度中的买卖。"
                   f"本季度已有 {reported} 家公司披露。" if zh else
                   "Top-10 tradable holders only, quarterly, up to ~4 months late; small positions and intra-quarter "
                   f"trades are invisible. {reported} companies have reported this quarter."),
    }


def stock_holders(data_dir: str, ticker: str, quarters: int = 2, lang: str = "zh", fetch: bool = True,
                  log=print) -> dict:
    """Who among the tracked investor kinds sits in one stock's top-10 tradable holders, last quarters."""
    info = cn.parse(ticker)
    if not info or info["market"] == "HK":
        return {"error": "A-shares only"}
    zh = lang == "zh"
    out, name = [], ""
    for q in [latest_quarter()] + [x for x in quarter_ends(8) if x < latest_quarter()][:quarters - 1]:
        df = holders(data_dir, q, fetch=fetch and q == latest_quarter(), log=log)
        if df.empty:
            continue
        rows = df[df["code"] == info["code"]]
        if len(rows) and not name:
            name = str(rows["name"].iloc[0])
        for r in rows.itertuples():
            cat = r.category if isinstance(r.category, str) else None
            out.append({"quarter": q, "holder": r.holder, "display": display_name(r.holder), "category": cat,
                        "label": LABEL[cat][0 if zh else 1] if cat in LABEL else None,
                        "shares": None if pd.isna(r.shares) else float(r.shares), "action": r.action,
                        "change_pct": None if pd.isna(r.change_pct) else float(r.change_pct),
                        "value": None if pd.isna(r.value) else float(r.value), "public": r.public})
    tracked = [x for x in out if x["category"]]
    # quarter-on-quarter: tracked holders that left the top 10, and the most they can still hold
    q = latest_quarter()
    cur = holders(data_dir, q, fetch=False)
    pq = prev_quarter(q)
    gone = []
    if os.path.exists(os.path.join(flows_dir(data_dir), f"holders_{pq}.csv")) and not cur.empty:
        prev = holders(data_dir, pq, fetch=False)
        ex = exits(cur[cur["code"] == info["code"]], prev[prev["code"] == info["code"]])
        cap = upper_bound(cur, info["code"])
        for r in ex[ex["category"].map(lambda c: isinstance(c, str))].itertuples():
            gone.append({"holder": r.holder, "display": display_name(r.holder), "category": r.category,
                         "label": LABEL[r.category][0 if zh else 1], "prev_shares": float(r.prev_shares),
                         "sold_at_least": float(r.sold_at_least), "confidence": r.confidence,
                         "now_at_most": cap})
    return {"ticker": info["symbol"], "stock_name": name, "holders": out, "tracked": tracked, "exits": gone,
            "previous_quarter": pq if gone or os.path.exists(os.path.join(flows_dir(data_dir), f"holders_{pq}.csv")) else None,
            "summary": _summary(tracked, zh) + _exit_text(gone, zh)}


def _exit_text(gone: list[dict], zh: bool) -> str:
    if not gone:
        return ""
    def one(g):
        cap = f"，现在最多持有 {g['now_at_most'] / 1e4:,.0f} 万股" if zh and g.get("now_at_most") else ""
        if g["confidence"] == "inferred":
            return (f"{g['label']}·{g['display']} 跌出前十，推断至少卖出 {g['sold_at_least'] / 1e4:,.0f} 万股{cap}" if zh else
                    f"{g['label']} {g['display']} left the top 10: sold at least {g['sold_at_least']:,.0f} shares")
        return (f"{g['label']}·{g['display']} 跌出前十（可能卖出，也可能被挤出）{cap}" if zh else
                f"{g['label']} {g['display']} left the top 10 (sold, or pushed out)")
    return ("；上季度对比：" if zh else "; vs last quarter: ") + "；".join(one(g) for g in gone)


def _summary(rows: list[dict], zh: bool) -> str:
    if not rows:
        return "十大流通股东里没有国家队、社保、险资、QFII、北向或公募基金。" if zh else \
            "No national team, pension, insurer, QFII, northbound or mutual fund among the top-10 tradable holders."
    latest = max(r["quarter"] for r in rows)
    word = {"new": "新进" if zh else "new", "add": "增持" if zh else "added", "reduce": "减持" if zh else "reduced",
            "same": "不变" if zh else "unchanged"}
    parts = [f"{r['label']}·{r['display']} {word.get(r['action'], r['action'])}"
             for r in rows if r["quarter"] == latest]
    return (f"{latest[:4]}-{latest[4:6]}-{latest[6:]} 季度：" if zh else f"Quarter {latest}: ") + "；".join(parts)


# ---------------------------------------------------------------- 龙虎榜 and the daily (estimated) flows
def dragon_tiger(data_dir: str, ticker: str | None = None, days: int = 30, fetch: bool = True) -> list[dict]:
    """Recent 龙虎榜 appearances with the institutions' net buy (from Eastmoney's institution table)."""
    end = dt.date.today()
    start = end - dt.timedelta(days=days)
    cache = cn.CNCache(data_dir)
    key = f"lhb_{start:%Y%m%d}_{end:%Y%m%d}.json"
    rows = cache.load(key, 6)
    if rows is None and fetch:
        try:
            det = cn._ak().stock_lhb_detail_em(start_date=f"{start:%Y%m%d}", end_date=f"{end:%Y%m%d}")
            inst = cn._ak().stock_lhb_jgmmtj_em(start_date=f"{start:%Y%m%d}", end_date=f"{end:%Y%m%d}")
        except Exception:
            det, inst = None, None
        rows = []
        if det is not None and len(det):
            inst_net = {}
            if inst is not None and len(inst):
                for r in inst.itertuples(index=False):
                    d = dict(zip(inst.columns, r))
                    k = (str(d.get("代码")).zfill(6), str(d.get("上榜日期"))[:10])
                    inst_net[k] = inst_net.get(k, 0.0) + float(pd.to_numeric(d.get("机构买入净额"), errors="coerce") or 0)
            for r in det.itertuples(index=False):
                d = dict(zip(det.columns, r))
                code, day = str(d.get("代码")).zfill(6), str(d.get("上榜日"))[:10]
                num = lambda k: None if pd.isna(pd.to_numeric(d.get(k), errors="coerce")) else float(pd.to_numeric(d.get(k), errors="coerce"))
                rows.append({"code": code, "name": str(d.get("名称")), "day": day, "pct": num("涨跌幅"),
                             "net_buy": num("龙虎榜净买额"), "turnover": num("市场总成交额"),
                             "reason": str(d.get("上榜原因") or ""), "note": str(d.get("解读") or ""),
                             "inst_net": inst_net.get((code, day))})
        cache.save(key, rows)
    rows = rows or []
    if ticker:
        info = cn.parse(ticker)
        rows = [r for r in rows if info and r["code"] == info["code"]]
    return sorted(rows, key=lambda r: r["day"], reverse=True)


def main_force(data_dir: str, ticker: str, days: int = 20, fetch: bool = True) -> dict | None:
    """Eastmoney's 'main force' net inflow over the last `days` trading days. An ESTIMATE from order
    sizes (large orders are assumed to be institutions), not a record of who traded."""
    info = cn.parse(ticker)
    if not info or info["market"] == "HK" or not fetch:
        return None
    try:
        df = cn._ak().stock_individual_fund_flow(stock=info["code"], market=info["market"].lower())
    except Exception:
        return None
    if df is None or not len(df):
        return None
    df = df.tail(days)
    net = pd.to_numeric(df["主力净流入-净额"], errors="coerce")
    return {"days": int(len(df)), "from": str(df["日期"].iloc[0])[:10], "to": str(df["日期"].iloc[-1])[:10],
            "net": float(net.sum()), "positive_days": int((net > 0).sum()),
            "note": "估算：按单笔成交金额大小推断，大单不等于机构，仅供参考。"}


# ---------------------------------------------------------------- events for the quant lab
def events(data_dir: str, log=print) -> pd.DataFrame:
    """One row per (company, investor kind, quarter) from every saved quarter: what that kind did in the stock,
    dated by the company's announcement (公告日), so a backtest can only act after it was public.

    action: new / add / reduce / same from the disclosed changes; exit when the kind left the top 10 since the
    previous quarter (confidence 'inferred' = must have sold, 'possible' = sold or pushed out)."""
    import re
    d = flows_dir(data_dir)
    qs = sorted(f[8:16] for f in os.listdir(d) if re.fullmatch(r"holders_\d{8}\.csv", f))
    ind = _industry_map(data_dir)
    out, prev = [], None
    for q in qs:
        cur = holders(data_dir, q, fetch=False)
        if cur.empty:
            prev = cur
            continue
        cur = cur.copy()
        public = cur.groupby("code")["public"].max()
        t = cur[cur["category"].map(lambda c: isinstance(c, str))].copy()
        if len(t):
            t["value_change"] = _value_change(t)
            g = t.groupby(["code", "category"]).agg(
                acts=("action", lambda s: set(s)), value=("value", "sum"), value_change=("value_change", "sum"),
                change_pct=("change_pct", "mean"), holders=("holder", "nunique")).reset_index()
            g["action"] = ["new" if "new" in a else ("add" if v > 0 else ("reduce" if v < 0 else "same"))
                           for a, v in zip(g["acts"], g["value_change"])]
            g["confidence"] = "disclosed"
            out.append(g.drop(columns="acts").assign(end=q))
        if prev is not None and not prev.empty:
            ex = exits(cur, prev)
            ex = ex[ex["category"].map(lambda c: isinstance(c, str))]
            if len(ex):
                ge = ex.groupby(["code", "category"]).agg(
                    value_change=("sold_value_at_least", lambda s: -float(s.sum())),
                    confidence=("confidence", lambda s: "inferred" if (s == "inferred").any() else "possible"),
                    holders=("holder", "nunique")).reset_index()
                ge["action"], ge["value"], ge["change_pct"] = "exit", 0.0, -100.0
                out.append(ge.assign(end=q))
        for frame in out:
            if "public" not in frame and frame["end"].iloc[0] == q:
                frame["public"] = frame["code"].map(public)
        prev = cur
    if not out:
        return pd.DataFrame()
    ev = pd.concat(out, ignore_index=True)
    ev = ev.dropna(subset=["public"])
    ev["day0"] = pd.to_datetime(ev["public"], errors="coerce")
    ev = ev.dropna(subset=["day0"])
    ev["ticker"] = [(cn.parse(c) or {}).get("symbol", c) for c in ev["code"]]
    ev["industry"] = ev["code"].map(ind)
    ev["quarter"] = pd.to_datetime(ev["end"]).dt.quarter
    ev["value_yi"] = ev["value"] / 1e8
    ev["value_change_yi"] = ev["value_change"] / 1e8
    log(f"  smart-money events: {len(ev)} from {len(qs)} quarters")
    return ev.reset_index(drop=True)


# ---------------------------------------------------------------- history test shown next to the map
def history_tests(data_dir: str, hold: int = 60, log=print, refresh: bool = False) -> dict | None:
    """'Buy after the disclosure' tested on the lab's explore period for each kind × (new, add), saved to
    flows/history_tests.json. Recomputed when the set of saved quarters changes."""
    import json
    import re
    d = flows_dir(data_dir)
    qs = sorted(f for f in os.listdir(d) if re.fullmatch(r"holders_\d{8}\.csv", f))
    p = os.path.join(d, "history_tests.json")
    if os.path.exists(p) and not refresh:
        try:
            with open(p, encoding="utf-8") as f:
                old = json.load(f)
            if old.get("quarters") == len(qs):
                return old
        except (OSError, ValueError):
            pass
    if len(qs) < 8:
        return None
    from stockproof import lab
    out = {"quarters": len(qs), "hold_days": hold, "holdout_start": lab.holdout_start().date().isoformat(),
           "made": dt.date.today().isoformat(), "results": {}}
    for cat in LABEL:
        for act in ("new", "add"):
            spec = {"type": "smart_money", "market": "cn", "hold_days": hold, "entry_lag": 1,
                    "filters": [{"field": "category", "op": "==", "value": cat}, {"field": "action", "op": "==", "value": act}]}
            try:
                r = lab.run_spec(data_dir, spec, "explore", log=lambda *a: None)
                r2 = lab.run_spec(data_dir, spec, "explore", log=lambda *a: None, cost_mult=lab.STRESS_MULT)
            except Exception as e:
                log(f"  history test {cat}/{act}: {type(e).__name__}: {str(e)[:80]}")
                continue
            a, t = lab._le(r)
            a2, _ = lab._le(r2)
            out["results"].setdefault(cat, {})[act] = {"events": int(r["n_events"]), "ann": a, "t": t, "ann_2x": a2}
    with open(p, "w", encoding="utf-8") as f:
        json.dump(out, f, ensure_ascii=False)
    return out
