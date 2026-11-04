"""
Margin financing (融资融券): is leveraged money adding to or leaving a stock, and the market as a whole?

The exchanges publish every stock's financing balance (融资余额) the next trading day. We cache one file
per exchange per day. Shanghai answers reliably from abroad; Shenzhen often resets the connection, so it
is retried, and a day with Shenzhen missing is marked as such rather than counted as zero.
"""

from __future__ import annotations

import datetime as dt
import os
import time

import pandas as pd

from stockproof import cn


def _dir(data_dir: str) -> str:
    from stockproof.flows import flows_dir
    d = os.path.join(flows_dir(data_dir), "margin")
    os.makedirs(d, exist_ok=True)
    return d


def _fetch(exchange: str, day: dt.date, tries: int = 3):
    fn = {"sse": "stock_margin_detail_sse", "szse": "stock_margin_detail_szse"}[exchange]
    last = None
    for attempt in range(tries):
        try:
            return getattr(cn._ak(), fn)(date=f"{day:%Y%m%d}")
        except Exception as e:                       # connection resets from Shenzhen are common
            last = e
            time.sleep(2 * (attempt + 1))
    raise last


def _normalize(raw: pd.DataFrame) -> pd.DataFrame:
    code = next(c for c in raw.columns if "代码" in c)
    name = next((c for c in raw.columns if "简称" in c), None)
    bal = next(c for c in raw.columns if c.startswith("融资余额"))
    buy = next((c for c in raw.columns if c.startswith("融资买入额")), None)
    df = pd.DataFrame({"code": raw[code].astype(str).str.zfill(6),
                       "name": raw[name].astype(str) if name else "",
                       "balance": pd.to_numeric(raw[bal], errors="coerce")})
    if buy:
        df["buy"] = pd.to_numeric(raw[buy], errors="coerce")
    return df[df["code"].str.match(r"^[036]\d{5}$")]            # stocks only, no ETFs / bonds


def day(data_dir: str, d: dt.date, exchange: str, fetch: bool = True) -> pd.DataFrame | None:
    """One exchange's margin table for one day (cached; an empty file marks a non-trading day)."""
    p = os.path.join(_dir(data_dir), f"{exchange}_{d:%Y%m%d}.csv")
    if os.path.exists(p):
        df = pd.read_csv(p, dtype={"code": str})
        return None if df.empty else df
    if not fetch:
        return None
    try:
        raw = _fetch(exchange, d)
    except Exception:
        return None
    if raw is None or not len(raw):
        if d < dt.date.today() - dt.timedelta(days=1):
            pd.DataFrame(columns=["code", "name", "balance"]).to_csv(p, index=False)
        return None
    df = _normalize(raw)
    df.to_csv(p, index=False)
    return df


def history(data_dir: str, days: int = 20, fetch: bool = True, end: dt.date | None = None) -> dict:
    """Financing balance per stock per day for the last `days` trading days, per exchange."""
    end = end or dt.date.today() - dt.timedelta(days=1)          # published the next day
    cal = [d.date() for d in pd.bdate_range(end - dt.timedelta(days=int(days * 1.6) + 7), end)][::-1]
    out = {}
    for ex in ("sse", "szse"):
        frames, misses = {}, 0
        for d in cal:
            df = day(data_dir, d, ex, fetch)
            if df is None:
                misses += 1
                if ex == "szse" and misses >= 3 and not frames:
                    break                                   # Shenzhen unreachable now: don't hammer it
                continue
            frames[pd.Timestamp(d)] = df.set_index("code")["balance"]
            if len(frames) >= days:
                break
        out[ex] = pd.DataFrame(frames).T.sort_index() if frames else pd.DataFrame()
    return out


def stock(data_dir: str, ticker: str, days: int = 20, fetch: bool = True, end: dt.date | None = None) -> dict | None:
    info = cn.parse(ticker)
    if not info or info["market"] not in ("SH", "SZ"):
        return None
    h = history(data_dir, days, fetch, end)[{"SH": "sse", "SZ": "szse"}[info["market"]]]
    if h.empty or info["code"] not in h.columns:
        return {"available": False, "note": ("深交所融资融券数据暂时拿不到" if info["market"] == "SZ" else "没有这只股票的融资数据")}
    s = h[info["code"]].dropna()
    if len(s) < 2:
        return {"available": False}
    return {"available": True, "from": s.index[0].date().isoformat(), "to": s.index[-1].date().isoformat(),
            "days": int(len(s)), "balance": float(s.iloc[-1]), "change": float(s.iloc[-1] - s.iloc[0]),
            "change_pct": float(s.iloc[-1] / s.iloc[0] - 1) if s.iloc[0] else None,
            "series": [[d.date().isoformat(), float(v)] for d, v in s.items()]}


def market(data_dir: str, days: int = 20, fetch: bool = True) -> dict:
    h = history(data_dir, days, fetch)
    out = {}
    for ex, df in h.items():
        if df.empty:
            out[ex] = {"available": False}
            continue
        tot = df.sum(axis=1)
        both = df.iloc[[0, -1]].dropna(axis=1)            # only stocks eligible on both days: names added to or
        a0, a1 = float(both.iloc[0].sum()), float(both.iloc[1].sum())   # dropped from the list aren't flows
        out[ex] = {"available": True, "from": tot.index[0].date().isoformat(), "to": tot.index[-1].date().isoformat(),
                   "balance": float(tot.iloc[-1]), "change": a1 - a0, "change_pct": a1 / a0 - 1 if a0 else None,
                   "stocks": int(both.shape[1]), "list_changes": int(df.shape[1] - both.shape[1]),
                   "daily": [[d.date().isoformat(), float(v)] for d, v in tot.items()]}
        chg = (df.iloc[-1] - df.iloc[0]).dropna().sort_values()
        out[ex]["top_add"] = [[c, float(v)] for c, v in chg.tail(10)[::-1].items()]
        out[ex]["top_cut"] = [[c, float(v)] for c, v in chg.head(10).items()]
    return out
