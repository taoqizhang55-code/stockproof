"""
Whole-market stock screen (China A-shares), and a test of the screen on history.

Stage 1, every A-share, no LLM:
  filters   no ST / delisting names, market value >= min_cap, a report in the last ~5 months
  factors   earnings surprise (SUE), revenue growth, profit growth (year on year, as reported),
            annualized ROE, 60-day price momentum
  score     the average percentile rank of the available factors (0-100); outliers can't dominate
Stage 2 (optional) adds news, announcements and the latest report for the top names: see scorecard.py.

backtest() asks the honest question: if you had used this exact rule at each past checkpoint
(after the report deadlines: early May, early September, early November), with only the data
published by then, would the top picks have beaten the market after costs? Each factor is also
tested alone, so you can see which ones matter.

Data: Eastmoney via AKShare — 业绩报表 (all A-shares per report period) and the market snapshot
(price, 60-day / YTD returns, market value, P/E, P/B for every A-share in one table).
"""

from __future__ import annotations

import datetime as dt
import json
import math
import os
import re
import time

import numpy as np
import pandas as pd

from stockproof import cn
from stockproof import research_cn as rc

FACTORS = ["sue", "rev_yoy", "np_yoy", "roe", "mom60"]
FACTOR_NAMES = {
    "en": {"sue": "earnings surprise", "rev_yoy": "revenue growth", "np_yoy": "profit growth",
           "roe": "annualized ROE", "mom60": "60-day momentum"},
    "zh": {"sue": "业绩惊喜", "rev_yoy": "营收增长", "np_yoy": "利润增长", "roe": "年化 ROE", "mom60": "近 60 日走势"},
}


# ---------------------------------------------------------------- fundamentals for all A-shares

def _num(v):
    """A float, or None for anything that isn't one ("-", "", None, lists, ...)."""
    if v is None or isinstance(v, (list, tuple, dict, set, np.ndarray)):
        return None
    try:
        x = float(v)
    except (TypeError, ValueError):
        return None
    return x if math.isfinite(x) else None


def period_full(cache: cn.CNCache, date: str, max_age_days: float = 2) -> list[dict]:
    """业绩报表 for one report period with growth, ROE, margin and industry (cached; old periods kept)."""
    name = f"research_yjbb2_{date}.json"
    old = (dt.date.today() - dt.date(int(date[:4]), int(date[4:6]), int(date[6:]))).days > 400
    data = cache.load(name, None if old else max_age_days * 24)
    if data is not None:
        return data
    df = None
    for attempt in range(3):              # Eastmoney sometimes drops a connection mid-way
        try:
            df = cn._ak().stock_yjbb_em(date=date)
            break
        except (KeyError, TypeError):
            break                         # AKShare's way of saying "no rows for this period yet"
        except Exception:
            if attempt == 2:
                raise
            time.sleep(3 * (attempt + 1))
    out = []
    if df is None or not len(df):
        cache.save(name, out)
        return out
    col = lambda *k: rc._col(df, *k)
    c = {"code": col("股票代码"), "name": col("股票简称"), "eps": col("每股收益"),
         "rev_yoy": col("营业总收入-同比增长"), "np_yoy": col("净利润-同比增长"), "roe": col("净资产收益率"),
         "gm": col("销售毛利率"), "industry": col("所处行业"), "date": col("最新公告日期")}
    for _, r in df.iterrows():
        d = pd.to_datetime(r[c["date"]], errors="coerce") if c["date"] else None
        out.append({"code": rc._code6(r[c["code"]]), "name": str(r[c["name"]]) if c["name"] else "",
                    "eps": _num(r[c["eps"]]), "rev_yoy": _num(r[c["rev_yoy"]]), "np_yoy": _num(r[c["np_yoy"]]),
                    "roe": _num(r[c["roe"]]), "gm": _num(r[c["gm"]]) if c["gm"] else None,
                    "industry": str(r[c["industry"]]) if c["industry"] and pd.notna(r[c["industry"]]) else "",
                    "date": None if d is None or pd.isna(d) else d.strftime("%Y-%m-%d")})
    cache.save(name, out)
    return out


def panel(cache: cn.CNCache, since: str = "2015-01-01", log=print, tables: dict | None = None) -> pd.DataFrame:
    """One row per (stock, report period): YTD EPS, growth, ROE, industry, and the date it became public
    (the actual disclosure date; preliminary results if earlier; else the table's own date)."""
    rows = []
    periods = rc.period_ends(since)
    for k, date in enumerate(periods, 1):
        get = (lambda kind: tables.get((kind, date), [])) if tables is not None else None
        try:
            full = get("yjbb2") if get else period_full(cache, date)
            actual = {r["code"]: r.get("date") for r in (get("yysj") if get else rc.period_table(cache, "yysj", date))}
            quick = {r["code"]: r.get("date") for r in (get("yjkb") if get else rc.period_table(cache, "yjkb", date))}
        except Exception as e:
            log(f"  period {date}: {type(e).__name__}: {str(e)[:80]}")
            continue
        end = pd.Timestamp(date)
        for r in full:
            dates = [d for d in (actual.get(r["code"]), quick.get(r["code"])) if d]
            public = min(dates) if dates else r.get("date")
            if not public:
                continue
            # "listed": the stock was in that period's disclosure schedule. Newly listed companies also show
            # older periods (from the prospectus), dated by their latest restatement — not real history.
            rows.append({**r, "end": end, "public": pd.Timestamp(public), "listed": bool(dates)})
        if tables is None and k % 10 == 0:
            log(f"  report periods: {k}/{len(periods)}")
    df = pd.DataFrame(rows)
    if not len(df):
        return df
    df = df.sort_values(["code", "end"]).drop_duplicates(["code", "end"], keep="last").reset_index(drop=True)
    return add_sue(df)


def add_sue(df: pd.DataFrame, window: int = 8, min_history: int = 4) -> pd.DataFrame:
    """Vectorized single-quarter EPS and SUE for many stocks (YTD figures de-cumulated within each year)."""
    df = df.sort_values(["code", "end"]).copy()
    df["year"] = df["end"].dt.year
    prev = df.groupby(["code", "year"])["eps"].shift(1)
    prev_end = df.groupby(["code", "year"])["end"].shift(1)
    first = prev_end.isna()
    gap_ok = (df["end"] - prev_end).dt.days.between(80, 100)
    df["eps_q"] = np.where(first & (df["end"].dt.month == 3), df["eps"],
                           np.where(gap_ok, df["eps"] - prev, np.nan))
    ago = df[["code", "end", "eps_q"]].copy()
    ago["end"] = ago["end"] + pd.DateOffset(years=1)
    df = df.merge(ago.rename(columns={"eps_q": "eps_q_ago"}), on=["code", "end"], how="left")
    df["change"] = df["eps_q"] - df["eps_q_ago"]
    g = df.groupby("code")["change"]
    sd = g.transform(lambda s: s.shift(1).rolling(window, min_periods=min_history).std())
    df["sue"] = np.where(sd > 1e-6, df["change"] / sd, np.nan)
    months = df["end"].dt.month.map({3: 3, 6: 6, 9: 9, 12: 12})
    df["roe_ann"] = df["roe"] * 12 / months                  # YTD ROE -> yearly rate, comparable across periods
    # growth from a loss (or into one) is not growth: "+237%" can mean a smaller loss
    df.loc[df["eps"] <= 0, ["np_yoy", "roe_ann"]] = np.nan
    return df.drop(columns=["year"])


# ---------------------------------------------------------------- market snapshot

SPOT_URL = "https://push2.eastmoney.com/api/qt/clist/get"
SPOT_FIELDS = {"f12": "code", "f14": "name", "f2": "price", "f24": "mom60", "f25": "ytd",
               "f20": "cap", "f9": "pe", "f23": "pb"}
A_SHARES = "m:0 t:6,m:0 t:80,m:1 t:2,m:1 t:23,m:0 t:81 s:2048"      # SZ main, ChiNext, SH main, STAR, BJ


SPOT_HOSTS = ["push2.eastmoney.com", "82.push2.eastmoney.com", "push2delay.eastmoney.com"]
SINA_URL = "https://vip.stock.finance.sina.com.cn/quotes_service/api/json_v2.php/Market_Center.getHQNodeData"


def _get(url: str, params: dict, headers: dict, tries: int = 3, gap: float = 0.6):
    import requests
    last = None
    for attempt in range(tries):
        time.sleep(gap if attempt == 0 else 3 * attempt)
        try:
            r = requests.get(url, params=params, headers=headers, timeout=20)
            r.raise_for_status()
            return r
        except requests.RequestException as e:          # resets, timeouts, 502 Bad Gateway ...
            last = e
    raise last


def _spot_pages(log=print) -> list[dict]:
    """Eastmoney's market list, 100 rows a page, slowly; tries a few mirror hosts."""
    last = None
    for host in SPOT_HOSTS:
        rows, page, total = [], 1, None
        try:
            while True:
                r = _get(f"https://{host}/api/qt/clist/get",
                         {"pn": page, "pz": 100, "po": 0, "np": 1, "fltt": 2, "invt": 2, "fid": "f12",
                          "fs": A_SHARES, "fields": ",".join(SPOT_FIELDS)}, cn.UA)
                data = (r.json() or {}).get("data") or {}
                diff = data.get("diff") or []
                if isinstance(diff, dict):
                    diff = list(diff.values())
                total = total or data.get("total") or 0
                rows += diff
                if not diff or len(rows) >= total:
                    return rows
                page += 1
                if page % 10 == 0:
                    log(f"  snapshot: {len(rows)}/{total}")
        except Exception as e:
            last = e
            log(f"  {host}: {type(e).__name__}; trying another source ...")
    raise last


SINA_COUNT = "https://vip.stock.finance.sina.com.cn/quotes_service/api/json_v2.php/Market_Center.getHQNodeStockCount"
SINA_NODES = ("sh_a", "sz_a", "bj_a")


class Incomplete(RuntimeError):
    """A market list came back with stocks missing (the source started refusing mid-way)."""


def _sina_json(r):
    text = (r.text or "").strip()
    if text in ("", "null"):
        return None
    try:
        return r.json()
    except ValueError:
        return json.loads(text.strip('"'))


def _sina_pages(log=print, retry_wait: float = 15) -> list[dict]:
    """Sina's market list as a fallback: price, P/E, P/B, market value — but no 60-day return.
    Board by board, checked against Sina's own stock count; an empty page early on means Sina is
    throttling, so wait and retry rather than silently returning half the market."""
    headers = {**cn.UA, "Referer": "https://finance.sina.com.cn"}
    rows = []
    for node in SINA_NODES:
        want = int(_num(_sina_json(_get(SINA_COUNT, {"node": node}, headers))) or 0)
        got, page, empty = [], 1, 0
        while len(got) < want:
            data = _sina_json(_get(SINA_URL, {"page": page, "num": 80, "sort": "symbol", "asc": 1, "node": node},
                                   headers, gap=1.5))
            data = [d for d in data if isinstance(d, dict) and d.get("code")] if isinstance(data, list) else []
            if not data:
                if len(got) >= want * 0.98:              # a few suspended / just-listed names
                    break
                empty += 1
                if empty > 3:
                    raise Incomplete(f"Sina stopped answering at {len(got)}/{want} ({node})")
                log(f"  Sina paused at {node} {len(got)}/{want}; waiting {retry_wait * empty:.0f}s ...")
                time.sleep(retry_wait * empty)
                continue
            empty = 0
            for d in data:
                cap = _num(d.get("mktcap"))
                got.append({"f12": str(d.get("code")), "f14": str(d.get("name") or ""), "f2": _num(d.get("trade")),
                            "f24": None, "f25": None, "f20": cap * 1e4 if cap else None,      # 万元 -> 元
                            "f9": _num(d.get("per")), "f23": _num(d.get("pb"))})
            page += 1
            if page % 10 == 0:
                log(f"  snapshot (Sina {node}): {len(got)}/{want}")
        rows += got
    return rows


def _from_rows(rows: list[dict]) -> pd.DataFrame:
    df = pd.DataFrame(rows).rename(columns=SPOT_FIELDS)
    for c in ("price", "mom60", "ytd", "cap", "pe", "pb"):
        df[c] = pd.to_numeric(df.get(c), errors="coerce")          # "-" for suspended stocks
    df["mom60"] /= 100
    df["ytd"] /= 100
    df["cap"] /= 1e8
    df["code"] = df["code"].map(rc._code6)
    df["name"] = df["name"].astype(str)
    return df[list(SPOT_FIELDS.values())].drop_duplicates("code").query("price > 0")


def snapshot(cache: cn.CNCache | None = None, max_age_hours: float = 6, log=print) -> pd.DataFrame:
    """Every A-share now: name, price, 60-day and YTD return, market value (亿元), P/E, P/B.
    Fetched slowly page by page (cached a few hours); AKShare's fast version as a fallback."""
    if cache is not None:
        saved = cache.load("screen_snapshot2.json", max_age_hours)
        if saved:
            return _from_rows(saved)
    try:
        rows = _spot_pages(log)
    except Exception:
        log("  Eastmoney is not answering; using Sina (no 60-day return, so momentum is left out) ...")
        rows = _sina_pages(log)
    rows = [{k: (None if isinstance(v, float) and math.isnan(v) else v) for k, v in r.items()} for r in rows]
    if cache is not None and len(rows) > 4000:
        cache.save("screen_snapshot2.json", rows)
    return _from_rows(rows)


# ---------------------------------------------------------------- the screen

def latest_known(pan: pd.DataFrame, as_of, max_age_days: int = 150) -> pd.DataFrame:
    """Each stock's newest report that was public by `as_of` (and is not too old)."""
    as_of = pd.Timestamp(as_of)
    known = pan[(pan["public"] <= as_of) & (pan["end"] >= as_of - pd.Timedelta(days=max_age_days + 120))]
    known = known.sort_values(["code", "end"]).groupby("code").tail(1)
    return known[(as_of - known["public"]).dt.days <= max_age_days]


def score(df: pd.DataFrame, factors=FACTORS) -> pd.DataFrame:
    """Percentile rank (0-100) per factor, and their average as the score."""
    df = df.copy()
    src = {"sue": "sue", "rev_yoy": "rev_yoy", "np_yoy": "np_yoy", "roe": "roe_ann", "mom60": "mom60"}
    used = []
    for f in factors:
        c = src[f]
        if c in df and df[c].notna().sum() >= 10:
            df[f"p_{f}"] = df[c].rank(pct=True) * 100
            used.append(f"p_{f}")
    df["n_factors"] = df[used].notna().sum(axis=1) if used else 0
    df["score"] = df[used].mean(axis=1) if used else np.nan
    return df[df["n_factors"] >= max(1, len(used) - 2)]


def screen(pan: pd.DataFrame, snap: pd.DataFrame, as_of=None, top: int | None = 30, min_cap: float = 50.0,
           factors=FACTORS, min_reports: int = 8, per_industry: int | None = None) -> pd.DataFrame:
    """Today's screen: every eligible A-share ranked by score (`rank`), and the top `top` of them.
    min_reports  skip recent listings (fewer than this many reports, ~2 years): tiny pre-IPO equity makes
                 their ROE and growth look absurd (ROE 160%, profit +3000%)
    per_industry at most this many names per industry in the top list, so one hot sector can't fill it"""
    as_of = pd.Timestamp(as_of or dt.date.today())
    listed = pan["listed"] if "listed" in pan else True
    history = pan[(pan["public"] <= as_of) & listed].groupby("code").size()
    fund = latest_known(pan, as_of).drop(columns=["name"], errors="ignore")
    fund = fund[fund["code"].map(history).fillna(0) >= min_reports]
    df = snap.merge(fund, on="code", how="inner")
    df = df[~df["name"].str.contains(r"ST|退", regex=True) & (df["cap"] >= min_cap)]
    df = score(df, factors)
    df = df.sort_values("score", ascending=False).reset_index(drop=True)
    df["rank"] = np.arange(1, len(df) + 1)
    df["ticker"] = [cn.canonical(c) for c in df["code"]]
    if top:
        if per_industry:
            n = df.groupby(df["industry"].fillna("").replace("", "?")).cumcount()
            df = df[n < per_industry]
        df = df.head(top)
    return df.copy()


def _pct(v: float, zh: bool) -> str:
    if v >= 1000:
        return "超过 +1000%" if zh else "over +1000%"
    return f"{v:+.0f}%"


def reasons(row: pd.Series, lang: str = "zh", n: int = 3) -> list[str]:
    """The strongest factors of one result, in plain words."""
    names = FACTOR_NAMES.get(lang, FACTOR_NAMES["en"])
    zh = lang == "zh"
    vals = {"sue": lambda r: f"SUE {r['sue']:+.1f}", "rev_yoy": lambda r: _pct(r["rev_yoy"], zh),
            "np_yoy": lambda r: _pct(r["np_yoy"], zh), "roe": lambda r: f"{r['roe_ann']:.1f}%",
            "mom60": lambda r: f"{100 * r['mom60']:+.0f}%"}
    ps = sorted(((row.get(f"p_{f}"), f) for f in FACTORS if pd.notna(row.get(f"p_{f}"))), reverse=True)[:n]
    top = (lambda p: f"前 {max(1, round(100 - p))}%") if lang == "zh" else (lambda p: f"top {max(1, round(100 - p))}%")
    out = []
    for p, f in ps:
        try:
            out.append(f"{names[f]} {vals[f](row)}（{top(p)}）" if lang == "zh" else f"{names[f]} {vals[f](row)} ({top(p)})")
        except (TypeError, ValueError, KeyError):
            continue
    return out


# ---------------------------------------------------------------- does the rule work? (history)

def checkpoints(start: str, end: str) -> list[pd.Timestamp]:
    """A few trading days after each report deadline (Apr 30, Aug 31, Oct 31)."""
    out = []
    for y in range(int(start[:4]), int(end[:4]) + 1):
        for m, d in ((5, 6), (9, 6), (11, 6)):
            t = pd.Timestamp(y, m, d)
            if pd.Timestamp(start) <= t <= pd.Timestamp(end):
                out.append(t)
    return out


def backtest(pan: pd.DataFrame, prices: pd.DataFrame, top: int = 30, factors=FACTORS,
             cost_per_side: float = 0.0015, start: str = "2016-01-01") -> dict:
    """Hold the top `top` names (equal weight) from each checkpoint to the next, among stocks with prices.
    Costs: `cost_per_side` on the traded fraction (commission + slippage + average stamp duty)."""
    from stockproof.research import BENCHMARKS
    px = prices.drop(columns=[c for c in BENCHMARKS if c in prices.columns])
    ret = px.pct_change(fill_method=None)
    days = px.index
    codes = {c: c[:6] for c in px.columns}
    pts = [t for t in checkpoints(start, days[-1].date().isoformat()) if t > days[0] + pd.Timedelta(days=90)]
    port, bench, rows, prev = [], [], [], set()
    for k, t in enumerate(pts):
        i = int(days.searchsorted(t))
        if i >= len(days) - 1:
            break
        j = int(days.searchsorted(pts[k + 1])) if k + 1 < len(pts) else len(days) - 1
        fund = latest_known(pan, days[i - 1]).set_index("code")
        mom = (px.iloc[i - 1] / px.iloc[max(0, i - 61)] - 1)
        uni = pd.DataFrame({"ticker": px.columns, "code": [codes[c] for c in px.columns],
                            "mom60": mom.to_numpy()}).dropna(subset=["mom60"])
        uni = uni.join(fund, on="code", how="inner")
        sc = score(uni, factors).sort_values("score", ascending=False)
        picks = list(sc["ticker"].head(top))
        if len(picks) < max(5, top // 3):
            continue
        window = ret.iloc[i + 1:j + 1]
        p = window[picks].mean(axis=1).fillna(0.0)
        b = window.mean(axis=1).fillna(0.0)
        turnover = 1.0 if not prev else len(set(picks) - prev) / len(picks)
        p.iloc[0] -= turnover * cost_per_side * 2                   # sell old + buy new names
        prev = set(picks)
        port.append(p)
        bench.append(b)
        rows.append({"date": days[i].date().isoformat(), "picks": len(picks), "turnover": turnover,
                     "return": float((1 + p).prod() - 1), "market": float((1 + b).prod() - 1)})
    if not port:
        return {"n": 0}
    p, b = pd.concat(port), pd.concat(bench)
    x = p - b
    n = len(x)
    ann = (1 + x).prod() ** (252 / n) - 1
    t = x.mean() / (x.std(ddof=1) / math.sqrt(n)) if x.std(ddof=1) > 0 else float("nan")
    per = pd.DataFrame(rows)
    years = ((1 + x).groupby(x.index.year).prod() - 1).to_dict()
    curve = (1 + x).cumprod()
    return {"n": len(per), "top": top, "factors": list(factors), "ann_excess": float(ann), "t": float(t),
            "ann_return": float((1 + p).prod() ** (252 / n) - 1), "ann_market": float((1 + b).prod() ** (252 / n) - 1),
            "hit_rate": float((per["return"] > per["market"]).mean()), "avg_turnover": float(per["turnover"].mean()),
            "max_dd": float((curve / curve.cummax() - 1).min()), "years": {int(k): float(v) for k, v in years.items()},
            "periods": per.to_dict("records")}


def factor_test(pan: pd.DataFrame, prices: pd.DataFrame, top: int = 30) -> list[dict]:
    """The same backtest with all factors, and with each factor alone."""
    out = []
    for fs in [FACTORS] + [[f] for f in FACTORS]:
        r = backtest(pan, prices, top, fs)
        out.append({"factors": fs, **{k: r.get(k) for k in ("n", "ann_excess", "t", "hit_rate", "max_dd")}})
    return out


# ---------------------------------------------------------------- saving

def screens_dir(data_dir: str) -> str:
    d = os.path.join(data_dir, "screens")
    os.makedirs(d, exist_ok=True)
    return d


def to_records(df: pd.DataFrame, lang: str = "zh") -> list[dict]:
    keep = ["ticker", "code", "name", "industry", "rank", "score", "price", "cap", "pe", "pb", "mom60", "ytd",
            "sue", "rev_yoy", "np_yoy", "roe_ann", "gm", "end", "public"] + [f"p_{f}" for f in FACTORS]
    out = []
    for _, r in df.iterrows():
        rec = {}
        for k in keep:
            v = r.get(k)
            if isinstance(v, pd.Timestamp):
                v = v.date().isoformat()
            elif isinstance(v, (float, np.floating)):
                v = None if not np.isfinite(v) else round(float(v), 4)
            elif isinstance(v, np.integer):
                v = int(v)
            rec[k] = v
        rec["reasons"] = reasons(r, lang)
        out.append(rec)
    return out


def compact_all(full: pd.DataFrame) -> dict:
    """Score and rank of every screened stock, so any stock (e.g. one on the watchlist) can be looked up."""
    out = {}
    for _, r in full.iterrows():
        rec = {"rank": int(r["rank"]), "score": round(float(r["score"]), 1)}
        for f in FACTORS:
            v = r.get(f"p_{f}")
            if pd.notna(v):
                rec[f] = round(float(v))
        out[r["ticker"]] = rec
    return out


def save(data_dir: str, records: list[dict], meta: dict, everyone: dict | None = None) -> str:
    day = meta.get("as_of") or dt.date.today().isoformat()
    path = os.path.join(screens_dir(data_dir), f"cn_{day}.json")
    with open(path, "w", encoding="utf-8") as f:
        json.dump({"meta": meta, "results": records, "all": everyone or {}}, f, ensure_ascii=False, default=str)
    return path


def lookup(data_dir: str, ticker: str, lang: str = "zh") -> dict:
    """Where one stock stands in the latest screen, or why it isn't in it."""
    zh = lang == "zh"
    saved = load_latest(data_dir)
    if not saved:
        return {"covered": False, "why": "还没有运行过选股（stockproof screen）" if zh else "no screen has been run yet"}
    t = cn.canonical(ticker)
    info = cn.parse(t)
    if not info or info["market"] == "HK":
        return {"covered": False, "why": "选股目前只覆盖 A 股" if zh else "the screen covers China A-shares only"}
    rec = saved.get("all", {}).get(t)
    meta = saved.get("meta", {})
    if not rec:
        why = (f"不在选股范围内（ST、市值低于 {meta.get('min_cap', 50):g} 亿、停牌或财报过旧）" if zh else
               f"not screened (ST, market value under {meta.get('min_cap', 50):g} 亿 yuan, suspended or no recent report)")
        return {"covered": False, "why": why, "as_of": meta.get("as_of")}
    return {"covered": True, "as_of": meta.get("as_of"), "of": len(saved.get("all", {})), **rec}


def load_latest(data_dir: str) -> dict | None:
    d = os.path.join(data_dir, "screens")
    if not os.path.isdir(d):
        return None
    # only dated screens (cn_2026-10-29.json), not cn_backtest.json
    files = sorted(f for f in os.listdir(d) if re.fullmatch(r"cn_\d{4}-\d{2}-\d{2}\.json", f))
    if not files:
        return None
    with open(os.path.join(d, files[-1]), encoding="utf-8") as f:
        return json.load(f)


def run(data_dir: str, top: int = 30, min_cap: float = 50.0, per_industry: int | None = 3, lang: str = "zh",
        since: str | None = None, log=print) -> dict:
    """The whole stage-1 screen (tables, snapshot, scoring, save) for callers like the dashboard."""
    cache = cn.CNCache(data_dir)
    since = since or f"{dt.date.today().year - 4}-01-01"
    log("screen 1/3: earnings tables")
    pan = panel(cache, since, log=log)
    if not len(pan):
        raise RuntimeError("no earnings data")
    log("screen 2/3: market snapshot")
    snap = snapshot(cache, log=log)
    if len(snap) < 4500:
        log(f"  warning: only {len(snap)} stocks in the snapshot")
    log("screen 3/3: scoring")
    full = screen(pan, snap, top=None, min_cap=min_cap)
    out = screen(pan, snap, top=top, min_cap=min_cap, per_industry=per_industry or None)
    recs = to_records(out, lang)
    meta = {"as_of": dt.date.today().isoformat(), "universe": int(len(snap)), "min_cap": min_cap, "top": top,
            "per_industry": per_industry, "since": since, "factors": FACTORS, "screened": int(len(full)),
            "momentum": bool(snap["mom60"].notna().any())}
    path = save(data_dir, recs, meta, compact_all(full))
    return {"meta": meta, "results": recs, "path": path}


def industry_of(data_dir: str, code: str) -> str | None:
    """A stock's Eastmoney industry from the newest cached 业绩报表 (no network)."""
    d = os.path.join(data_dir, "cn")
    if not os.path.isdir(d):
        return None
    files = sorted((f for f in os.listdir(d) if re.fullmatch(r"research_yjbb2_\d{8}\.json", f)), reverse=True)
    for f in files[:3]:
        try:
            with open(os.path.join(d, f), encoding="utf-8") as fh:
                for r in json.load(fh):
                    if r.get("code") == code and r.get("industry"):
                        return r["industry"]
        except (OSError, ValueError):
            continue
    return None
