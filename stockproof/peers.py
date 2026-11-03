"""
Peer comparison: how did the stock's industry peers move on the same day?

"Fell 5%" means one thing when every peer fell 4% and another when the peers were flat. The
attribution table gives the industry index; this gives named companies a reader recognises.

A-shares: peers are the largest members of the stock's Eastmoney industry board (by market cap,
cached a week). Same-day returns come from the research price file when it covers the day, otherwise
from a short download per peer (cached per day). Fully offline fallback: members of the same industry
in the 业绩报表 cache that are in the research price file.
"""

from __future__ import annotations

import json
import os
import statistics
from concurrent.futures import ThreadPoolExecutor

import pandas as pd

from stockproof import cn

N_PEERS = 8


def _ticker(code: str) -> str:
    info = cn.parse(code)
    return info["symbol"] if info else code


def members(data_dir: str, industry: str, fetch: bool = True) -> list[dict]:
    """[{ticker, name, mcap}] for one Eastmoney industry, largest first (mcap None when unknown)."""
    cache = cn.CNCache(data_dir)
    key = f"peers_{industry}.json"
    hit = cache.load(key, 7 * 24)
    if hit:
        return hit
    rows = []
    if fetch:
        try:
            df = cn._ak().stock_board_industry_cons_em(symbol=industry)
            code_c = next(c for c in df.columns if "代码" in c)
            name_c = next(c for c in df.columns if "名称" in c)
            cap_c = next((c for c in df.columns if "总市值" in c), None)
            for _, r in df.iterrows():
                cap = pd.to_numeric(r[cap_c], errors="coerce") if cap_c else None
                rows.append({"ticker": _ticker(str(r[code_c]).zfill(6)), "name": str(r[name_c]),
                             "mcap": None if cap is None or pd.isna(cap) else float(cap)})
            rows.sort(key=lambda x: -(x["mcap"] or 0))
        except Exception:
            rows = []
        if rows:
            cache.save(key, rows)
    if not rows:                                           # offline: the 业绩报表 cache knows each stock's industry
        rows = _members_offline(data_dir, industry)
    return rows


def _members_offline(data_dir: str, industry: str) -> list[dict]:
    import re
    d = os.path.join(data_dir, "cn")
    if not os.path.isdir(d):
        return []
    files = sorted((f for f in os.listdir(d) if re.fullmatch(r"research_yjbb2_\d{8}\.json", f)), reverse=True)
    seen, out = set(), []
    for f in files[:2]:
        try:
            with open(os.path.join(d, f), encoding="utf-8") as fh:
                for r in json.load(fh):
                    if r.get("industry") == industry and r.get("code") not in seen:
                        seen.add(r["code"])
                        out.append({"ticker": _ticker(r["code"]), "name": r.get("name", ""), "mcap": None})
        except (OSError, ValueError):
            continue
    return out


def _research_prices(data_dir: str) -> pd.DataFrame | None:
    from stockproof import lab
    try:
        return lab.stock_prices(data_dir, "cn")
    except Exception:
        return None


def day_return(data_dir: str, ticker: str, day: str, px: pd.DataFrame | None = None, fetch: bool = True) -> float | None:
    """Close-to-close return of `ticker` on `day`; None if it didn't trade or can't be found."""
    d = pd.Timestamp(day)
    if px is not None and ticker in px.columns and d in px.index:
        s = px[ticker].loc[:d].dropna()
        if len(s) >= 2 and s.index[-1] == d:
            return float(s.iloc[-1] / s.iloc[-2] - 1)
    cache = cn.CNCache(data_dir)
    rets = cache.load("peer_returns.json") or {}
    k = f"{ticker}|{day}"
    if k in rets:
        return rets[k]
    q = os.path.join(data_dir, "quotes", f"{ticker}.csv")              # the watchlist's own price files
    r = None
    try:
        if os.path.exists(q):
            s = pd.read_csv(q, index_col=0, parse_dates=True)["close"].loc[:d].dropna()
            if len(s) >= 2 and s.index[-1] == d:
                r = float(s.iloc[-1] / s.iloc[-2] - 1)
        if r is None and fetch:
            from stockproof import quotes
            s = quotes.download_bars(ticker, (d - pd.Timedelta(days=20)).date())["close"].loc[:d].dropna()
            if len(s) >= 2 and s.index[-1] == d:
                r = float(s.iloc[-1] / s.iloc[-2] - 1)
    except Exception:
        return None
    if r is not None:
        rets = cache.load("peer_returns.json") or {}
        rets[k] = r
        cache.save("peer_returns.json", rets)
    return r


def compare(data_dir: str, ticker: str, day: str, ret: float | None, n: int = N_PEERS, fetch: bool = True) -> dict | None:
    """The stock's same-day return next to its largest industry peers."""
    from stockproof import screener
    info = cn.parse(ticker)
    if not info or info["market"] == "HK":
        return None
    industry = screener.industry_of(data_dir, info["code"])
    if not industry:
        return None
    px = _research_prices(data_dir)
    pool = [m for m in members(data_dir, industry, fetch) if m["ticker"] != info["symbol"]]
    if not any(m.get("mcap") for m in pool) and px is not None:      # no sizes: prefer the large caps we hold
        pool.sort(key=lambda m: m["ticker"] not in px.columns)
    pool = pool[:n]
    if not pool:
        return None
    with ThreadPoolExecutor(max_workers=4) as ex:
        rs = list(ex.map(lambda m: day_return(data_dir, m["ticker"], day, px, fetch), pool))
    peers = [{"ticker": m["ticker"], "name": m["name"], "ret": r} for m, r in zip(pool, rs) if r is not None]
    if len(peers) < 2:
        return None
    vals = [p["ret"] for p in peers]
    med = statistics.median(vals)
    out = {"industry": industry, "day": day, "peers": sorted(peers, key=lambda p: -p["ret"]), "median": med,
           "up": sum(v > 0.001 for v in vals), "down": sum(v < -0.001 for v in vals), "n": len(peers),
           "rule": f"the {len(peers)} largest companies in Eastmoney's {industry} board with a price that day"}
    if ret is not None:
        out["ret"] = ret
        out["rank"] = 1 + sum(v > ret for v in vals)                  # 1 = best of n + 1
        out["vs_median"] = ret - med
    return out


def prompt_line(p: dict | None) -> str:
    if not p:
        return ""
    from stockproof.quotes import fmt_pct
    names = ", ".join(f"{x['name']} {fmt_pct(x['ret'])}" for x in p["peers"][:6])
    rank = f"; the stock ranks {p['rank']} of {p['n'] + 1}" if p.get("rank") else ""
    return (f"Peers ({p['industry']}, same day; computed, quote exactly): median {fmt_pct(p['median'])}, "
            f"{p['up']} up / {p['down']} down of {p['n']}{rank}. {names}.\n")
