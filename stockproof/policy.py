"""
Policy signals: does stronger official wording about an industry come before that industry beats the rest?

Chinese policy language moves along a ladder — 研究制定 → 稳步推进 → 加快推进 → 大力支持 — and investors
read every step. This module tests whether that reading is worth anything, before it can enter the scorecard:

  1. download  新闻联播 transcripts since 2016 (CCTV, via AKShare; cached per day)
  2. read      keyword filter, then the LLM marks, per item: Shenwan level-1 industry, stance
               (support / restrict) and strength on the ladder 1-4, with the exact quoted wording
  3. prices    the 31 Shenwan (申万) level-1 industry indices (open and close)
  4. study     event study on industry returns in excess of the equal-weighted 31 industries:
               entry at the next trading day's OPEN (the broadcast is at 19:00, after the close),
               reaction = that day, drift = days 2-20 and 21-60, plus the 20 days BEFORE (was it known?)
               and a simple backtest with costs.

Caveat kept in the results: the LLM was trained on later data; wording strength is a reading of the text,
but results are also shown for the period after the model's training data.
"""

from __future__ import annotations

import concurrent.futures as cf
import datetime as dt
import json
import math
import os
import re
import time

import numpy as np
import pandas as pd

SW_L1 = {
    "801010": "农林牧渔", "801030": "基础化工", "801040": "钢铁", "801050": "有色金属", "801080": "电子",
    "801110": "家用电器", "801120": "食品饮料", "801130": "纺织服饰", "801140": "轻工制造", "801150": "医药生物",
    "801160": "公用事业", "801170": "交通运输", "801180": "房地产", "801200": "商贸零售", "801210": "社会服务",
    "801230": "综合", "801710": "建筑材料", "801720": "建筑装饰", "801730": "电力设备", "801740": "国防军工",
    "801750": "计算机", "801760": "传媒", "801770": "通信", "801780": "银行", "801790": "非银金融",
    "801880": "汽车", "801890": "机械设备", "801950": "煤炭", "801960": "石油石化", "801970": "环保",
    "801980": "美容护理",
}
NAME_TO_CODE = {v: k for k, v in SW_L1.items()}
VERSION = 2

# An item is sent to the LLM only if it talks about policy AND about the economy (most items are diplomacy,
# meetings, people and foreign news).
POLICY_WORDS = ["政策", "规划", "意见", "方案", "措施", "部署", "国务院", "常务会议", "发改委", "工信部", "财政部",
                "央行", "人民银行", "证监会", "金融监管", "支持", "鼓励", "推进", "推动", "加快", "大力", "发展",
                "规范", "整治", "限制", "遏制", "治理", "补贴", "减税", "降费", "专项", "试点", "行动计划", "条例"]
ECON_WORDS = ["产业", "行业", "企业", "制造", "经济", "市场", "投资", "消费", "科技", "技术", "能源", "电力",
              "汽车", "芯片", "集成电路", "半导体", "医药", "医疗", "农业", "粮食", "房地产", "住房", "基建",
              "交通", "铁路", "航运", "通信", "5G", "算力", "人工智能", "数字", "软件", "新能源", "光伏", "风电",
              "储能", "电池", "钢铁", "煤炭", "石油", "化工", "有色", "稀土", "军工", "国防", "金融", "银行",
              "保险", "证券", "资本市场", "旅游", "文化", "传媒", "环保", "碳", "水利", "家电", "食品", "养老"]
SKIP_TITLES = ["国际联播快讯", "致电", "致贺电", "唁电", "会见", "会谈", "通电话", "出访", "国事访问"]


def policy_dir(data_dir: str) -> str:
    d = os.path.join(data_dir, "policy")
    os.makedirs(os.path.join(d, "cctv"), exist_ok=True)
    return d


# ---------------------------------------------------------------- 1. transcripts

def days_between(start: str, end: str) -> list[str]:
    a, b = pd.Timestamp(start), pd.Timestamp(end)
    return [d.strftime("%Y%m%d") for d in pd.date_range(a, b, freq="D")]


def _cctv_path(data_dir: str, day: str) -> str:
    return os.path.join(policy_dir(data_dir), "cctv", f"{day}.json")


def load_day(data_dir: str, day: str) -> list[dict] | None:
    p = _cctv_path(data_dir, day)
    if not os.path.exists(p):
        return None
    with open(p, encoding="utf-8") as f:
        return json.load(f)


def fetch_day(day: str, ak=None) -> list[dict]:
    if ak is None:
        import akshare as ak
    df = ak.news_cctv(date=day)
    if df is None or not len(df):
        return []
    return [{"title": str(r["title"]).strip(), "content": str(r["content"]).strip()} for _, r in df.iterrows()]


def download(data_dir: str, start: str, end: str | None = None, workers: int = 4, log=print,
             fetch=fetch_day, retry_wait: float = 2) -> dict:
    """Missing days only (resumable). Days within the last 3 days are re-fetched if empty."""
    end = end or dt.date.today().isoformat()
    todo = [d for d in days_between(start, end) if load_day(data_dir, d) is None]
    stats = {"days": len(days_between(start, end)), "todo": len(todo), "ok": 0, "empty": 0, "failed": 0}
    if not todo:
        return stats
    recent = (dt.date.today() - dt.timedelta(days=3)).strftime("%Y%m%d")
    t0 = time.time()

    def one(day):
        for attempt in range(3):
            try:
                return day, fetch(day), None
            except Exception as e:                       # network hiccup: retry, then give up for this run
                err = e
                time.sleep(retry_wait * (attempt + 1))
        return day, None, err

    # AKShare's CCTV requests have no timeout: after a network drop or the Mac waking from sleep they can wait
    # forever. A default socket timeout makes them fail (and retry) instead.
    import socket
    old_timeout = socket.getdefaulttimeout()
    socket.setdefaulttimeout(30)
    try:
        return _download_pool(data_dir, todo, workers, one, stats, recent, t0, log)
    finally:
        socket.setdefaulttimeout(old_timeout)


def _download_pool(data_dir, todo, workers, one, stats, recent, t0, log) -> dict:
    with cf.ThreadPoolExecutor(max_workers=workers) as pool:
        futures = [pool.submit(one, d) for d in todo]
        for k, fut in enumerate(cf.as_completed(futures), 1):      # progress in finishing order
            day, items, err = fut.result()
            if items is None:
                stats["failed"] += 1
            else:
                if items or day < recent:                 # an empty recent day may just not be online yet
                    with open(_cctv_path(data_dir, day), "w", encoding="utf-8") as f:
                        json.dump(items, f, ensure_ascii=False)
                stats["ok" if items else "empty"] += 1
            if k % 50 == 0 or k == len(todo):
                rate = k / max(1e-9, time.time() - t0)
                log(f"  新闻联播 {k}/{len(todo)} days · {stats['failed']} failed · "
                    f"~{(len(todo) - k) / max(rate, 1e-9) / 60:.0f} min left")
    return stats


def candidates(items: list[dict]) -> list[dict]:
    """Items that may announce an industry policy."""
    out = []
    for i, it in enumerate(items):
        t, c = it.get("title", ""), it.get("content", "")
        if any(w in t for w in SKIP_TITLES):
            continue
        text = t + c[:1500]
        if any(w in text for w in POLICY_WORDS) and any(w in text for w in ECON_WORDS):
            out.append({"i": i, "title": t, "content": c})
    return out


# ---------------------------------------------------------------- 2. LLM reading

SCHEMA = """
CREATE TABLE IF NOT EXISTS policy_reads (
    day TEXT NOT NULL,
    model TEXT NOT NULL,
    result TEXT NOT NULL,
    read_at TEXT NOT NULL,
    PRIMARY KEY (day, model)
);
"""

LADDER = """Strength ladder for SUPPORT (pick the highest that the wording reaches):
 1 = mentioned / studied / encouraged in general terms (研究, 探索, 鼓励, 引导, 关注)
 2 = steady promotion (稳步推进, 有序发展, 推动, 促进, 支持…发展 in passing)
 3 = accelerate / key support (加快, 积极推进, 重点支持, 着力, 抓紧, 部署 specific measures)
 4 = top priority with resources (大力, 全力, 国家战略, 专项资金/补贴/减税, 一系列政策出台, 头等大事)
For RESTRICT use the same 1-4 for how hard: 1 = 引导规范, 2 = 规范/加强监管, 3 = 整治/严控/限制,
 4 = 严厉打击/全面清理/去产能/叫停."""


KINDS = ("new_measure", "leader_directive", "report")


def build_prompt(day: str, cands: list[dict]) -> str:
    sectors = "、".join(SW_L1.values())
    lines = [f"[{k}] {c['title']}\n{c['content'][:700]}" for k, c in enumerate(cands, 1)]
    return (
        "You read the Chinese state TV evening news (新闻联播) for industry policy signals.\n"
        f"Date: {day}.\n\n" + "\n\n".join(lines) + "\n\n"
        "For each item that states a policy toward specific industries (not general praise of the economy, "
        "not diplomacy, not a single company's news), list one signal per industry it clearly affects.\n"
        "Classify the item's KIND — this matters most:\n"
        " new_measure = a NEW central decision announced today: a State Council / ministry / central meeting "
        "deploys, issues or approves a document, plan, fund, subsidy, tax change or regulation;\n"
        " leader_directive = a top leader's speech, inspection or article that sets a direction, no concrete new measure;\n"
        " report = progress or achievement reporting, statistics, local practice, commentary, series features "
        "(e.g. 【新思想引领新征程】, \"上半年…增长\", \"各地…\"), or restating an existing policy.\n"
        f"Industries must be exactly one of these Shenwan names: {sectors}.\n{LADDER}\n"
        "Reply ONLY with JSON: {\"signals\": [{\"item\": number, \"industry\": \"name from the list\", "
        "\"stance\": \"support\" or \"restrict\", \"strength\": 1-4, "
        "\"kind\": \"new_measure\" | \"leader_directive\" | \"report\", \"central\": true/false, "
        "\"quote\": \"the exact words (≤ 30 characters) that show the stance and strength\"}]}. "
        "Empty list if no item qualifies. At most 3 industries per item; skip vague links."
    )


def clean_signals(data: dict, n_items: int) -> list[dict]:
    out = []
    for s in (data.get("signals") or [])[:30]:
        if not isinstance(s, dict):
            continue
        ind = str(s.get("industry", "")).strip()
        stance = str(s.get("stance", "")).strip().lower()
        try:
            item, strength = int(s.get("item")), int(s.get("strength"))
        except (TypeError, ValueError):
            continue
        if ind not in NAME_TO_CODE or stance not in ("support", "restrict") or not 1 <= strength <= 4 \
                or not 1 <= item <= n_items:
            continue
        kind = str(s.get("kind", "report")).strip().lower()
        out.append({"item": item, "industry": ind, "stance": stance, "strength": strength,
                    "kind": kind if kind in KINDS else "report", "central": bool(s.get("central", False)),
                    "quote": str(s.get("quote", ""))[:60]})
    return out


def read_days(store, client, model_id: str, data_dir: str, days: list[str], workers: int = 4,
              log=print) -> dict:
    """LLM reading of each downloaded day's candidate items (cached per day and model)."""
    store.conn.executescript(SCHEMA)
    key = f"{model_id}#p{VERSION}"
    done = {r[0] for r in store.conn.execute("SELECT day FROM policy_reads WHERE model = ?", (key,))}
    todo = []
    for d in days:
        if d in done:
            continue
        items = load_day(data_dir, d)
        if items is None:
            continue
        cands = candidates(items)
        todo.append((d, cands))
    stats = {"todo": len(todo), "read": 0, "no_candidates": 0, "failed": 0, "signals": 0}

    def one(job):
        d, cands = job
        if not cands:
            return d, cands, [], None
        try:
            return d, cands, clean_signals(client.chat_json(build_prompt(d, cands)), len(cands)), None
        except Exception as e:
            return d, cands, None, e

    t0 = time.time()
    with cf.ThreadPoolExecutor(max_workers=workers) as pool:
        for k, (d, cands, sig, err) in enumerate(pool.map(one, todo), 1):
            if sig is None:
                stats["failed"] += 1
                from stockproof.core import is_fatal
                if is_fatal(err):
                    raise err
                continue
            for s in sig:
                s["title"] = cands[s["item"] - 1]["title"]
            store.conn.execute("INSERT OR REPLACE INTO policy_reads VALUES (?, ?, ?, ?)",
                               (d, key, json.dumps({"signals": sig, "n_candidates": len(cands)}, ensure_ascii=False),
                                dt.datetime.now().isoformat(timespec="seconds")))
            stats["read" if cands else "no_candidates"] += 1
            stats["signals"] += len(sig)
            if k % 25 == 0 or k == len(todo):
                store.conn.commit()
                rate = k / max(1e-9, time.time() - t0)
                log(f"  read {k}/{len(todo)} days · {stats['signals']} signals · "
                    f"~{(len(todo) - k) / max(rate, 1e-9) / 60:.0f} min left")
    store.conn.commit()
    return stats


def signals_frame(store, model_id: str) -> pd.DataFrame:
    store.conn.executescript(SCHEMA)
    rows = []
    for day, res in store.conn.execute("SELECT day, result FROM policy_reads WHERE model = ?",
                                       (f"{model_id}#p{VERSION}",)):
        for s in json.loads(res).get("signals", []):
            rows.append({"day": pd.Timestamp(day), **s})
    df = pd.DataFrame(rows, columns=["day", "item", "industry", "stance", "strength", "kind", "central", "quote", "title"])
    if len(df):
        df["signed"] = np.where(df["stance"] == "support", 1, -1) * df["strength"]
    return df


# ---------------------------------------------------------------- 3. industry prices

def download_prices(data_dir: str, log=print, ak=None) -> pd.DataFrame:
    """Open and close of the 31 Shenwan level-1 indices -> policy/sw_l1.csv (columns <code>_o / <code>_c)."""
    if ak is None:
        import akshare as ak
    cols = {}
    for k, (code, name) in enumerate(SW_L1.items(), 1):
        for attempt in range(3):
            try:
                df = ak.index_hist_sw(symbol=code, period="day")
                break
            except Exception as e:
                if attempt == 2:
                    raise RuntimeError(f"{code} {name}: {type(e).__name__}: {e}")
                time.sleep(3)
        d = pd.to_datetime(df["日期"])
        cols[f"{code}_c"] = pd.Series(pd.to_numeric(df["收盘"], errors="coerce").to_numpy(), index=d)
        cols[f"{code}_o"] = pd.Series(pd.to_numeric(df["开盘"], errors="coerce").to_numpy(), index=d)
        if k % 10 == 0:
            log(f"  industry indices {k}/{len(SW_L1)}")
        time.sleep(0.5)
    out = pd.DataFrame(cols).sort_index()
    out = out[~out.index.duplicated()]
    out.to_csv(os.path.join(policy_dir(data_dir), "sw_l1.csv"))
    return out


def load_prices(data_dir: str) -> pd.DataFrame | None:
    p = os.path.join(policy_dir(data_dir), "sw_l1.csv")
    if not os.path.exists(p):
        return None
    return pd.read_csv(p, index_col=0, parse_dates=True)


# ---------------------------------------------------------------- 4. the study

def events(sig: pd.DataFrame, fresh_days: int = 60, kinds: tuple | None = None) -> pd.DataFrame:
    """One row per (day, industry, stance) with the strongest wording that day; `escalation` = stronger than
    anything said about that industry (same stance) in the previous `fresh_days` calendar days."""
    if kinds is not None and "kind" in sig:
        sig = sig[sig["kind"].isin(kinds)]
    if not len(sig):
        return pd.DataFrame()
    ev = (sig.sort_values("strength", ascending=False)
             .groupby(["day", "industry", "stance"], as_index=False)
             .agg(strength=("strength", "max"), n=("item", "size"), quote=("quote", "first"), title=("title", "first")))
    ev = ev.sort_values("day").reset_index(drop=True)
    prior = []
    for r in ev.itertuples():
        past = ev[(ev["industry"] == r.industry) & (ev["stance"] == r.stance) &
                  (ev["day"] < r.day) & (ev["day"] >= r.day - pd.Timedelta(days=fresh_days))]
        prior.append(int(past["strength"].max()) if len(past) else 0)
    ev["prior_max"] = prior
    ev["escalation"] = ev["strength"] > ev["prior_max"]
    return ev


def attach_returns(ev: pd.DataFrame, px: pd.DataFrame) -> pd.DataFrame:
    """Industry returns in excess of the equal-weighted 31 industries, entry at the next day's open."""
    closes = px[[c for c in px.columns if c.endswith("_c")]].rename(columns=lambda c: c[:-2])
    opens = px[[c for c in px.columns if c.endswith("_o")]].rename(columns=lambda c: c[:-2])
    days = closes.index
    out = []
    for r in ev.itertuples():
        code = NAME_TO_CODE[r.industry]
        if code not in closes or pd.isna(closes[code]).all():
            continue
        t = int(days.searchsorted(r.day, side="right"))       # first trading day after the broadcast
        if t >= len(days) or t < 21:
            continue
        o, c = opens.iloc[t], closes.iloc[t]

        def rel(a, b):                                     # industry minus average industry, from a to b
            x = (b / a - 1).dropna()
            return float(x.get(code, np.nan) - x.mean()) if code in x else np.nan

        rec = {"pre20": rel(closes.iloc[t - 21], closes.iloc[t - 1]),      # the 20 days before: already known?
               "gap": rel(closes.iloc[t - 1], o),                           # overnight: priced before anyone can trade
               "react": rel(o, c),                                          # entry day, open to close
               "d2_20": rel(c, closes.iloc[t + 19]) if t + 19 < len(days) else np.nan,
               "d21_60": rel(closes.iloc[t + 19], closes.iloc[t + 59]) if t + 59 < len(days) else np.nan}
        out.append({**r._asdict(), "trade_day": days[t], **rec})
    return pd.DataFrame(out).drop(columns=["Index"], errors="ignore")


def _mean_t(x: pd.Series, by: pd.Series | None = None) -> dict:
    """Mean and t-stat; with `by` (dates), average per date first so same-day events don't count as independent."""
    x = x.dropna()
    if by is not None:
        x = x.groupby(by.loc[x.index]).mean()
    n = len(x)
    if n < 3:
        return {"n": n, "mean": float(x.mean()) if n else None, "t": None}
    sd = x.std(ddof=1)
    return {"n": n, "mean": float(x.mean()), "t": float(x.mean() / (sd / math.sqrt(n))) if sd > 0 else None}


def study(ev: pd.DataFrame) -> dict:
    """Tables: by stance x strength, escalations, and by period."""
    if not len(ev):
        return {"n": 0}
    cols = ["pre20", "gap", "react", "d2_20", "d21_60"]
    by = ev["trade_day"]

    def row(sub):
        return {c: _mean_t(sub[c], by) for c in cols} | {"events": len(sub)}
    tables = {"all": row(ev)}
    for stance in ("support", "restrict"):
        s = ev[ev["stance"] == stance]
        tables[stance] = row(s)
        for k in (1, 2, 3, 4):
            tables[f"{stance}_{k}"] = row(s[s["strength"] == k])
        tables[f"{stance}_escalation_3plus"] = row(s[s["escalation"] & (s["strength"] >= 3)])
    strong = ev[(ev["stance"] == "support") & (ev["strength"] >= 3) & ev["escalation"]]
    halves = {}
    if len(strong):
        mid = strong["trade_day"].sort_values().iloc[len(strong) // 2]
        halves = {"first_half": row(strong[strong["trade_day"] < mid]),
                  "second_half": row(strong[strong["trade_day"] >= mid]),
                  "since_2025": row(strong[strong["trade_day"] >= "2025-01-01"])}
    return {"n": len(ev), "tables": tables, "halves": halves,
            "start": str(ev["trade_day"].min().date()), "end": str(ev["trade_day"].max().date())}


def backtest(ev: pd.DataFrame, px: pd.DataFrame, hold: int = 20, min_strength: int = 3,
             cost_per_side: float = 0.001) -> dict:
    """Hold industries (equal weight) for `hold` days after a fresh strong-support signal, entering at the
    next open; otherwise hold the equal-weighted 31 industries. Costs per side on each switch (ETF-like)."""
    closes = px[[c for c in px.columns if c.endswith("_c")]].rename(columns=lambda c: c[:-2])
    ret = closes.pct_change(fill_method=None)
    mkt = ret.mean(axis=1)
    sig = ev[(ev["stance"] == "support") & (ev["strength"] >= min_strength) & ev["escalation"]]
    days = closes.index
    hold_until: dict[str, int] = {}
    port, held_prev = [], set()
    entries = {}
    for r in sig.itertuples():
        t = int(days.searchsorted(r.day, side="right"))
        entries.setdefault(t, set()).add(NAME_TO_CODE[r.industry])
    for i in range(1, len(days)):
        for code in entries.get(i, ()):
            hold_until[code] = i + hold - 1
        held = {c for c, until in hold_until.items() if until >= i and c in ret.columns}
        r_today = ret.iloc[i][list(held)].mean() if held else mkt.iloc[i]
        if pd.isna(r_today):
            r_today = mkt.iloc[i]
        turnover = len(held ^ held_prev) / max(1, len(held | held_prev)) if (held or held_prev) else 0
        port.append(r_today - turnover * cost_per_side * 2 - mkt.iloc[i])
        held_prev = held
    x = pd.Series(port, index=days[1:]).dropna()
    x = x[x.index >= (sig["day"].min() if len(sig) else x.index[0])]
    if len(x) < 60:
        return {"n_days": len(x)}
    ann = (1 + x).prod() ** (252 / len(x)) - 1
    t = x.mean() / (x.std(ddof=1) / math.sqrt(len(x))) if x.std(ddof=1) > 0 else float("nan")
    return {"hold": hold, "min_strength": min_strength, "signals": int(len(sig)), "n_days": int(len(x)),
            "ann_excess": float(ann), "t": float(t),
            "years": {int(k): float(v) for k, v in ((1 + x).groupby(x.index.year).prod() - 1).items()}}


def save_results(data_dir: str, res: dict) -> str:
    p = os.path.join(policy_dir(data_dir), "results.json")
    res = {**res, "updated": dt.datetime.now().isoformat(timespec="seconds")}
    with open(p, "w", encoding="utf-8") as f:
        json.dump(res, f, ensure_ascii=False, default=str)
    return p


# ---------------------------------------------------------------- for the scorecard

def industry_map(data_dir: str, client, names: list[str]) -> dict:
    """Eastmoney industry names (e.g. 半导体, 元件, 通信设备) -> Shenwan level-1 names, asked once and cached."""
    p = os.path.join(policy_dir(data_dir), "industry_map.json")
    try:
        with open(p, encoding="utf-8") as f:
            cached = json.load(f)
    except (OSError, ValueError):
        cached = {}
    todo = [n for n in names if n and n not in cached]
    if todo and client is not None:
        sectors = "、".join(SW_L1.values())
        data = client.chat_json(
            "Map each Chinese industry name to the single best Shenwan (申万) level-1 industry.\n"
            f"Shenwan names: {sectors}\nIndustries: {json.dumps(todo, ensure_ascii=False)}\n"
            'Reply ONLY with JSON: {"map": {"industry": "Shenwan name"}}')
        for k, v in (data.get("map") or {}).items():
            if k in todo and v in NAME_TO_CODE:
                cached[k] = v
        with open(p, "w", encoding="utf-8") as f:
            json.dump(cached, f, ensure_ascii=False)
    return cached


def recent_for(store, model_id: str, industry: str, days: int = 90, kinds=("new_measure",)) -> list[dict]:
    """Policy signals about one Shenwan industry in the last `days` (newest first, strongest per day)."""
    sig = signals_frame(store, model_id)
    if not len(sig):
        return []
    from stockproof import clock
    since = pd.Timestamp(clock.today() - dt.timedelta(days=days))
    s = sig[(sig["industry"] == industry) & (sig["day"] >= since) & sig["kind"].isin(kinds)]
    s = s.sort_values(["day", "strength"], ascending=[False, False]).drop_duplicates(["day", "stance"])
    return [{"date": r.day.date().isoformat(), "stance": r.stance, "strength": int(r.strength),
             "quote": r.quote, "title": r.title} for r in s.itertuples()]


def finding(data_dir: str, lang: str = "zh") -> dict:
    """The saved study's verdict for the scorecard's validation line."""
    zh = lang == "zh"
    p = os.path.join(policy_dir(data_dir), "results.json")
    try:
        with open(p, encoding="utf-8") as f:
            res = json.load(f)
        t = res["study"]["tables"]
        sup, bt = t["support"], (res.get("backtest") or {}).get("20") or (res.get("backtest") or {}).get(20) or {}
        g, d2, d3 = sup["gap"], sup["d2_20"], sup["d21_60"]
        text = (f"已检验（新闻联播 {res['study']['start'][:4]}–{res['study']['end'][:4]}，{sup['events']} 次新举措）："
                f"开盘前已反映 {100 * g['mean']:+.2f}%，之后第 2–20 天 {100 * d2['mean']:+.2f}%、21–60 天 "
                f"{100 * d3['mean']:+.2f}%，没有可交易的超额" if zh else
                f"Tested (新闻联播 {res['study']['start'][:4]}-{res['study']['end'][:4]}, {sup['events']} new measures): "
                f"{100 * g['mean']:+.2f}% priced in by the open, then {100 * d2['mean']:+.2f}% (days 2-20) and "
                f"{100 * d3['mean']:+.2f}% (days 21-60): no tradable edge")
        if bt.get("ann_excess") is not None:
            text += (f"；回测 {100 * bt['ann_excess']:+.1f}%/年" if zh else f"; backtest {100 * bt['ann_excess']:+.1f}%/yr")
        return {"tested": True, "useful": False, "text": text}
    except (OSError, ValueError, KeyError, TypeError):
        return {"tested": False, "useful": False, "text": "尚未检验" if zh else "not tested yet"}
