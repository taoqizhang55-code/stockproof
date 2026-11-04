"""
The national team's ETF channel: daily net creations in the big broad-index ETFs.

Since 2024 Central Huijin has mostly bought broad-index ETFs (CSI 300 and others) rather than single
stocks, so its buying never shows up in companies' top-10 holders. It does show up as sudden jumps in
those ETFs' share counts, typically on days the market falls. We track the daily share count of the key
Shanghai-listed broad ETFs (from the exchange), value the change at the day's NAV, and flag days with an
unusually large net creation while the index fell.

This is indirect evidence: anyone can create ETF units. Flags say "consistent with national-team
buying", never "the national team bought".
"""

from __future__ import annotations

import datetime as dt
import os

import pandas as pd

from stockproof import cn

# Shanghai-listed broad-index ETFs commonly used for market support (largest of each index).
KEY_ETFS = {
    "510300": "沪深300ETF华泰柏瑞", "510310": "沪深300ETF易方达", "510330": "沪深300ETF华夏",
    "510050": "上证50ETF华夏", "510500": "中证500ETF南方", "512100": "中证1000ETF南方",
    "588000": "科创50ETF华夏", "588080": "科创50ETF易方达", "510180": "上证180ETF华安",
}
FLAG_MIN = 3e9          # yuan: a flagged day needs at least this much net creation across the key ETFs
FLAG_Z = 3.0            # ... and this many standard deviations above the previous 60 days


def _dir(data_dir: str) -> str:
    from stockproof.flows import flows_dir
    d = os.path.join(flows_dir(data_dir), "etf")
    os.makedirs(d, exist_ok=True)
    return d


def shares_on(data_dir: str, day: dt.date, fetch: bool = True) -> pd.DataFrame | None:
    """Share counts of every SSE ETF on one day (cached; None on non-trading days / unavailable)."""
    p = os.path.join(_dir(data_dir), f"sse_{day:%Y%m%d}.csv")
    if os.path.exists(p):
        df = pd.read_csv(p, dtype={"code": str})
        return None if df.empty else df
    if not fetch:
        return None
    try:
        raw = cn._ak().fund_etf_scale_sse(date=f"{day:%Y%m%d}")
    except Exception:
        return None                                   # not cached: a later run retries
    if raw is None or not len(raw):
        if day < dt.date.today():
            pd.DataFrame(columns=["code", "shares"]).to_csv(p, index=False)   # holiday: remember
        return None
    df = pd.DataFrame({"code": raw["基金代码"].astype(str).str.zfill(6),
                       "shares": pd.to_numeric(raw["基金份额"], errors="coerce")})
    df.to_csv(p, index=False)
    return df


def nav(data_dir: str, code: str, start: dt.date, fetch: bool = True) -> pd.Series:
    """Daily unit NAV of one ETF (cached a day)."""
    p = os.path.join(_dir(data_dir), f"nav_{code}.csv")
    if os.path.exists(p) and (dt.date.fromtimestamp(os.path.getmtime(p)) >= dt.date.today() or not fetch):
        s = pd.read_csv(p, index_col=0, parse_dates=True).iloc[:, 0]
        if len(s) and s.index[0].date() <= start + dt.timedelta(days=7):
            return s
    if not fetch:
        return pd.Series(dtype=float)
    try:
        raw = cn._ak().fund_etf_fund_info_em(fund=code, start_date=f"{start:%Y%m%d}", end_date=f"{dt.date.today():%Y%m%d}")
        s = pd.Series(pd.to_numeric(raw["单位净值"], errors="coerce").to_numpy(), index=pd.to_datetime(raw["净值日期"]),
                      name="nav").dropna().sort_index()
    except Exception:
        return pd.Series(dtype=float)
    s.to_frame().to_csv(p)
    return s


def daily(data_dir: str, days: int = 60, fetch: bool = True, log=print, start: dt.date | None = None,
          end: dt.date | None = None) -> pd.DataFrame:
    """Per trading day: net creation (yuan) in each key ETF and in total, and the CSI 300's return."""
    end = end or dt.date.today()
    start = start or end - dt.timedelta(days=int((days + 70) * 1.45))          # 60 more trading days for the z-score
    cal = pd.bdate_range(start, end)
    rows, missing = {}, 0
    for i, d in enumerate(cal):
        df = shares_on(data_dir, d.date(), fetch)
        if df is None:
            missing += 1
            continue
        rows[d] = df.set_index("code")["shares"].reindex(list(KEY_ETFS))
        if fetch and i % 20 == 0:
            log(f"  ETF shares: {d.date()}")
    if not rows:
        return pd.DataFrame()
    sh = pd.DataFrame(rows).T.sort_index()
    navs = pd.DataFrame({c: nav(data_dir, c, start, fetch) for c in KEY_ETFS}).reindex(sh.index).ffill()
    flow = sh.diff() * navs                                                    # yuan created (+) / redeemed (-)
    out = flow.rename(columns=lambda c: f"flow_{c}")
    out["total"] = flow.sum(axis=1, min_count=1)
    # the market: the CSI 300 ETF's own NAV tracks the index and covers any period we have shares for
    px = navs["510300"] if "510300" in navs else pd.Series(index=out.index, dtype=float)
    out["csi300"] = px.pct_change()
    out["csi300_5d"] = px.pct_change(5)
    sd = out["total"].rolling(60, min_periods=20).std().shift(1)
    out["z"] = out["total"] / sd
    falling = (out["csi300"].fillna(0) < 0) | (out["csi300_5d"].fillna(0) <= -0.03)
    out["flag"] = (out["total"] >= FLAG_MIN) & (out["z"] >= FLAG_Z) & falling
    return out.iloc[1:]


def summary(data_dir: str, days: int = 60, lang: str = "zh", fetch: bool = True, log=print) -> dict:
    zh = lang == "zh"
    df = daily(data_dir, days, fetch, log)
    if df.empty:
        return {"error": "ETF share data unavailable" if not zh else "暂时拿不到 ETF 份额数据"}
    recent = df.iloc[-days:]
    yi = 1e8

    def day_row(d, r):
        return {"date": d.date().isoformat(), "net_creation": None if pd.isna(r["total"]) else float(r["total"]),
                "csi300": None if pd.isna(r["csi300"]) else float(r["csi300"]),
                "csi300_5d": None if pd.isna(r["csi300_5d"]) else float(r["csi300_5d"]),
                "z": None if pd.isna(r["z"]) else round(float(r["z"]), 1), "flag": bool(r["flag"]),
                "by_etf": {KEY_ETFS[c]: float(r[f"flow_{c}"]) for c in KEY_ETFS if pd.notna(r.get(f"flow_{c}"))}}
    flagged = [day_row(d, r) for d, r in recent[recent["flag"]].iterrows()]
    return {
        "days": int(len(recent)), "from": recent.index[0].date().isoformat(), "to": recent.index[-1].date().isoformat(),
        "net_creation": float(recent["total"].sum()),
        "down_day_creation": float(recent.loc[recent["csi300"] < 0, "total"].sum()),
        "flagged_days": flagged,
        "daily": [day_row(d, r) for d, r in recent.iterrows()],
        "etfs": KEY_ETFS,
        "rule": (f"疑似托底日：重点宽基 ETF 当天净申购至少 {FLAG_MIN / yi:.0f} 亿、是过去 60 个交易日波动的 {FLAG_Z:.0f} 倍以上，"
                 "且沪深300 当天下跌或近 5 个交易日累计跌超 3%。" if zh else
                 f"Flagged: key broad ETFs saw at least {FLAG_MIN / 1e9:.0f}B yuan of net creations, {FLAG_Z:.0f}+ standard "
                 "deviations above the previous 60 days, when the CSI 300 fell that day or 3%+ over 5 days."),
        "caveat": ("这是间接迹象：任何人都可以申购 ETF，标记只表示“符合国家队托底的特征”，不等于确认是国家队。"
                   "目前只覆盖上交所上市的宽基 ETF（深交所的嘉实沪深300、创业板 ETF 暂未接入）。" if zh else
                   "Indirect evidence: anyone can create ETF units; a flag means 'consistent with national-team buying', "
                   "not confirmed. Shanghai-listed ETFs only for now."),
    }
